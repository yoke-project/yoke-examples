//! hello-plugin-rust is a minimal reference Yoke plugin built on the Rust SDK
//! (yoke_sdk_rust::pluginapi). It is the Rust member of a family of equivalent
//! "hello" plugins (Go/Rust/Python) that all register the same surface under
//! distinct plugin IDs. It demonstrates the full plugin lifecycle against a
//! running Core:
//!
//!   - dial core.sock and register (bootstrap-token auth)
//!   - open the bidirectional session and send heartbeats
//!   - serve a structured stream "hello.tick" that emits a JSON tick once a
//!     second while Core has started the stream
//!   - answer the point-in-time query "hello.echo"
//!
//! Configuration comes from the environment the supervisor sets when it launches
//! a plugin (YOKE_CORE_SOCKET, YOKE_PLUGIN_ID, YOKE_BOOTSTRAP_TOKEN,
//! YOKE_PLUGIN_SOCKET); each has a sensible default so the binary can also be run
//! by hand against a dev Core.

use std::sync::Arc;
use tokio::sync::Mutex as AsyncMutex;
use tokio::time::{interval, Duration};
use yoke_sdk_rust::pluginapi::{
    AckType, Bytes, CancellationToken, Client, IncomingCommand, QueryHandler,
    QueryHandlerResult, RegistrationConfig, StreamEmitter, StreamProducer,
};

const STREAM_ID: &str = "hello.tick";
const QUERY_TYPE: &str = "hello.echo";

fn env(key: &str, def: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| def.to_string())
}

fn now_ms() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}

/// Structured stream producer: emits a JSON tick every second until Core stops it.
struct HelloTick {
    plugin_id: String,
}

impl StreamProducer for HelloTick {
    fn on_start(&self, emitter: Arc<dyn StreamEmitter>, token: CancellationToken) {
        let plugin_id = self.plugin_id.clone();
        tokio::spawn(async move {
            println!("[hello-plugin-rust] stream {STREAM_ID} started");
            let mut ticker = interval(Duration::from_secs(1));
            let mut seq: u64 = 0;
            loop {
                tokio::select! {
                    _ = token.cancelled() => break,
                    _ = ticker.tick() => {
                        seq += 1;
                        let payload = serde_json::json!({
                            "seq": seq,
                            "ts":  now_ms(),
                            "msg": format!("hello from {plugin_id}"),
                        });
                        let bytes = serde_json::to_vec(&payload).unwrap_or_default();
                        if let Err(e) = emitter.emit_data(Bytes::from(bytes)) {
                            eprintln!("[hello-plugin-rust] emit: {e}");
                            break;
                        }
                    }
                }
            }
        });
    }

    fn on_stop(&self) {
        println!("[hello-plugin-rust] stream {STREAM_ID} stopped");
    }
}

/// Point-in-time query handler: echoes the params back.
struct EchoQuery;

impl QueryHandler for EchoQuery {
    fn handle(&self, query_type: &str, params: &[u8]) -> QueryHandlerResult {
        let obj = serde_json::json!({
            "query": query_type,
            "echo":  String::from_utf8_lossy(params),
        });
        match serde_json::to_vec(&obj) {
            Ok(bytes) => QueryHandlerResult::ok("hello", "v1", bytes),
            Err(_) => QueryHandlerResult::err("QUERY.HANDLER_ERROR"),
        }
    }
}

#[tokio::main]
async fn main() {
    let core_sock = std::env::var("YOKE_CORE_SOCKET")
        .or_else(|_| std::env::var("YOKE_CORE_SOCK"))
        .unwrap_or_else(|_| "/run/yoke/core.sock".to_string());
    let plugin_id = env("YOKE_PLUGIN_ID", "hello-plugin-rust");
    // The supervisor injects a real token; for hand-launched dev runs Core
    // accepts any non-empty token (no token was issued), so default to "dev".
    let token = env("YOKE_BOOTSTRAP_TOKEN", "dev");

    let cfg = RegistrationConfig {
        plugin_id: plugin_id.clone(),
        instance_id: uuid::Uuid::new_v4().to_string(),
        plugin_version: "0.1.0".to_string(),
        protocol_version: "1.0".to_string(),
        language: "rust".to_string(),
        sdk_version: "0.1.0".to_string(),
        bootstrap_token: token,
        capabilities: vec!["hello".to_string()],
        streams: vec![STREAM_ID.to_string()],
        commands: vec!["StartStream".to_string(), "StopStream".to_string()],
        pid: std::process::id(),
        endpoint: std::env::var("YOKE_PLUGIN_SOCKET").unwrap_or_default(),
        media_socket_paths: std::collections::HashMap::new(),
    };

    println!("[hello-plugin-rust] connecting to Core at {core_sock}");

    let mut client = match Client::dial(&core_sock, cfg).await {
        Ok(c) => c,
        Err(e) => {
            eprintln!("[hello-plugin-rust] dial failed: {e}");
            std::process::exit(1);
        }
    };

    if let Err(e) = client.register().await {
        eprintln!("[hello-plugin-rust] registration failed: {e}");
        std::process::exit(1);
    }

    client.register_stream_producer(
        STREAM_ID,
        "hello",
        "v1",
        HelloTick { plugin_id: plugin_id.clone() },
    );
    client.register_query_handler(QUERY_TYPE, EchoQuery);

    if let Err(e) = client.open_session().await {
        eprintln!("[hello-plugin-rust] session open failed: {e}");
        std::process::exit(1);
    }

    let _ = client
        .send_event("plugin.started", "hello-plugin-rust started")
        .await;
    println!(
        "[hello-plugin-rust] registered and running (session={}); Ctrl-C to stop",
        client.session_id
    );

    let cmd_rx = client.take_command_receiver().await;
    let hb_interval = client.heartbeat_interval;
    let client = Arc::new(AsyncMutex::new(client));

    // Heartbeat task: report Streaming while a stream is active.
    let client_hb = client.clone();
    let hb_task = tokio::spawn(async move {
        let mut ticker = interval(hb_interval);
        loop {
            ticker.tick().await;
            let c = client_hb.lock().await;
            let active = c.active_stream_count();
            let state = if active > 0 { "Streaming" } else { "Idle" };
            if let Err(e) = c.send_heartbeat(state, active, false).await {
                eprintln!("[hello-plugin-rust] heartbeat error: {e}");
                break;
            }
        }
    });

    // Command loop — the SDK already intercepts StartStream/StopStream (handled
    // by the producer) and QueryRequest (handled by the query handler).
    if let Some(mut rx) = cmd_rx {
        loop {
            tokio::select! {
                _ = tokio::signal::ctrl_c() => {
                    println!("[hello-plugin-rust] Ctrl-C — exiting");
                    break;
                }
                maybe = rx.recv() => {
                    let Some(cmd) = maybe else { break };
                    let cmd_id = cmd.command_id().to_string();
                    match cmd {
                        IncomingCommand::Shutdown { .. } | IncomingCommand::Restart { .. } => {
                            let c = client.lock().await;
                            let _ = c.send_ack(&cmd_id, AckType::Accepted as i32, "").await;
                            let _ = c.send_ack(&cmd_id, AckType::Completed as i32, "").await;
                            println!("[hello-plugin-rust] shutdown/restart — exiting");
                            break;
                        }
                        other => println!("[hello-plugin-rust] unhandled command: {other:?}"),
                    }
                }
            }
        }
    }

    hb_task.abort();
    client.lock().await.close().await;
}
