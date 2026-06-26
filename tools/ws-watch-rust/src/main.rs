//! ws-watch-rust is a minimal reference Yoke tool: a CLI that CONSUMES a running
//! Core over its public Gateway surface (REST login + WebSocket), rather than
//! registering as a plugin. It is a scriptable stand-in for a graphical panel:
//! it logs in, opens the /ws WebSocket, and prints the live frames Core pushes
//! (the "connected" greeting, cached stream snapshots, and stream.data updates),
//! decoding each stream payload from base64.
//!
//! It is the Rust member of a family of equivalent ws-watch tools (Go/Rust/Python).
//! A Gateway tool speaks REST + WebSocket and does not use the plugin SDK.
//!
//! Flags (each with a dev-friendly default):
//!   --addr      Gateway host:port (dev TCP listener; default localhost:8765)
//!   --user      login username (must exist in Core's auth.users)
//!   --password  login password
//!   --subscribe optional comma-separated categories to subscribe to
//!   --json      print raw JSON frames instead of the formatted view

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use tungstenite::client::IntoClientRequest;
use tungstenite::Message;

struct Args {
    addr: String,
    user: String,
    password: String,
    subscribe: String,
    json: bool,
}

fn parse_args() -> Args {
    let mut a = Args {
        addr: "localhost:8765".to_string(),
        user: "dev".to_string(),
        password: "dev".to_string(),
        subscribe: String::new(),
        json: false,
    };
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--addr" => {
                a.addr = argv.get(i + 1).cloned().unwrap_or_default();
                i += 2;
            }
            "--user" => {
                a.user = argv.get(i + 1).cloned().unwrap_or_default();
                i += 2;
            }
            "--password" => {
                a.password = argv.get(i + 1).cloned().unwrap_or_default();
                i += 2;
            }
            "--subscribe" => {
                a.subscribe = argv.get(i + 1).cloned().unwrap_or_default();
                i += 2;
            }
            "--json" => {
                a.json = true;
                i += 1;
            }
            other => {
                eprintln!("ws-watch-rust: ignoring unknown argument {other}");
                i += 1;
            }
        }
    }
    a
}

/// POST /api/v1/auth/login and return the yoke_session JWT from the Set-Cookie.
fn login(addr: &str, user: &str, password: &str) -> Result<String, Box<dyn std::error::Error>> {
    let url = format!("http://{addr}/api/v1/auth/login");
    let body = serde_json::json!({ "username": user, "password": password }).to_string();
    let resp = ureq::post(&url)
        .set("Content-Type", "application/json")
        .send_string(&body)?;

    let raw = resp
        .header("set-cookie")
        .ok_or("no set-cookie in login response")?;
    // raw looks like: "yoke_session=<jwt>; Path=/; HttpOnly; ..."
    let first = raw.split(';').next().unwrap_or("").trim();
    let token = first
        .strip_prefix("yoke_session=")
        .ok_or("no yoke_session cookie in login response")?;
    Ok(token.to_string())
}

fn print_frame(txt: &str, json_out: bool) {
    if json_out {
        println!("{txt}");
        return;
    }
    let v: serde_json::Value = match serde_json::from_str(txt) {
        Ok(v) => v,
        Err(_) => {
            println!("[?] {txt}");
            return;
        }
    };
    match v.get("type").and_then(|t| t.as_str()) {
        Some("stream.data") => {
            let enc = v.get("payload").and_then(|p| p.as_str()).unwrap_or("");
            let decoded = STANDARD
                .decode(enc)
                .ok()
                .and_then(|b| String::from_utf8(b).ok())
                .unwrap_or_else(|| enc.to_string());
            println!(
                "[stream.data] {}/{} seq={}: {}",
                v["plugin_id"].as_str().unwrap_or(""),
                v["stream_id"].as_str().unwrap_or(""),
                v["sequence"].as_u64().unwrap_or(0),
                decoded
            );
        }
        Some("connected") => {
            println!(
                "[connected] core_version={}",
                v["core_version"].as_str().unwrap_or("")
            );
        }
        Some("subscribe_ack") => {
            println!("[subscribe_ack] active={}", v["active_categories"]);
        }
        Some(other) => println!("[{other}] {txt}"),
        None => println!("[?] {txt}"),
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = parse_args();

    let token = login(&args.addr, &args.user, &args.password)?;
    eprintln!("ws-watch-rust: logged in as {:?}", args.user);

    let mut request = format!("ws://{}/ws", args.addr).into_client_request()?;
    request
        .headers_mut()
        .insert("Cookie", format!("yoke_session={token}").parse()?);

    let (mut socket, _resp) = tungstenite::connect(request)?;
    eprintln!(
        "ws-watch-rust: connected to ws://{}/ws; Ctrl-C to stop",
        args.addr
    );

    if !args.subscribe.is_empty() {
        let cats: Vec<&str> = args.subscribe.split(',').collect();
        let sub = serde_json::json!({ "type": "subscribe", "categories": cats }).to_string();
        socket.send(Message::Text(sub))?;
    }

    loop {
        match socket.read() {
            Ok(Message::Text(txt)) => print_frame(&txt, args.json),
            Ok(Message::Binary(b)) => println!("[binary {} bytes]", b.len()),
            Ok(Message::Close(_)) => {
                eprintln!("ws-watch-rust: connection closed by server");
                break;
            }
            Ok(_) => {} // ping/pong/frame — ignore
            Err(e) => {
                eprintln!("ws-watch-rust: read error: {e}");
                break;
            }
        }
    }

    Ok(())
}
