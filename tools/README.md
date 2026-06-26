# tools

Standalone command-line tools that *consume* a running Yoke Core over its
public surfaces — primarily the Gateway's REST + WebSocket API. They play the
role a graphical panel would, but as scriptable CLIs: log in, open the
WebSocket, and render the live frames Core pushes (stream data, lifecycle
events) in the terminal.

Each tool lives in its own directory and may be written in any of the supported
toolchains (a `main.go`, a `Cargo.toml`, or a `main.py` + `requirements.txt`),
exactly like the plugins. `just build` discovers every `tools/<name>/` and emits
`build/<name>`; `just list` shows the toolchain. Add a tool by creating a new
subdirectory — no justfile change required.

Unlike the plugins, these tools speak the **Gateway** (REST + WebSocket), not
the plugin protocol, so they do not use the plugin SDK — a Gateway tool only
needs an HTTP + WebSocket client. They exercise a running Core at run time.

## ws-watch

A live watcher for the Gateway WebSocket: it logs in
(`POST /api/v1/auth/login`), opens `/ws` with the returned `yoke_session`
cookie, and prints each frame — the `connected` greeting, the cached stream
snapshots replayed on connect, and live `stream.data` updates (decoding the
base64 payload). It is provided as a family, one per toolchain:

| Tool | Toolchain | Status |
| --- | --- | --- |
| `ws-watch-go` | Go (`gorilla/websocket`) | available |
| `ws-watch-rust` | Rust | planned |
| `ws-watch-python` | Python | planned |

Usage (dev, against a Core with a matching `auth.users` entry and the Gateway
dev TCP listener on `localhost:8765`):

```sh
just build
./build/ws-watch-go --addr localhost:8765 --user dev --password dev
# --subscribe stream.data   subscribe to categories (optional; data is broadcast anyway)
# --json                    print raw JSON frames
```
