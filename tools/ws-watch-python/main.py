"""ws-watch-python is a minimal reference Yoke tool: a CLI that CONSUMES a running
Core over its public Gateway surface (REST login + WebSocket), rather than
registering as a plugin. It is a scriptable stand-in for a graphical panel: it
logs in, opens the /ws WebSocket, and prints the live frames Core pushes (the
"connected" greeting, cached stream snapshots, and stream.data updates), decoding
each stream payload from base64.

It is the Python member of a family of equivalent ws-watch tools (Go/Rust/Python).
A Gateway tool speaks REST + WebSocket and does not use the plugin SDK.

Flags (each with a dev-friendly default):
  --addr      Gateway host:port (dev TCP listener; default localhost:8765)
  --user      login username (must exist in Core's auth.users)
  --password  login password
  --subscribe optional comma-separated categories to subscribe to
  --json      print raw JSON frames instead of the formatted view
"""

import argparse
import base64
import json
import sys
import urllib.request
from http.cookies import SimpleCookie

from websockets.sync.client import connect


def login(addr: str, user: str, password: str) -> str:
    """POST /api/v1/auth/login and return the yoke_session JWT from Set-Cookie."""
    url = f"http://{addr}/api/v1/auth/login"
    data = json.dumps({"username": user, "password": password}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        set_cookie = resp.headers.get("Set-Cookie")
    if not set_cookie:
        raise RuntimeError("no Set-Cookie in login response")
    jar = SimpleCookie()
    jar.load(set_cookie)
    if "yoke_session" not in jar:
        raise RuntimeError("no yoke_session cookie in login response")
    return jar["yoke_session"].value


def print_frame(txt: str, json_out: bool) -> None:
    if json_out:
        print(txt)
        return
    try:
        v = json.loads(txt)
    except json.JSONDecodeError:
        print(f"[?] {txt}")
        return

    kind = v.get("type")
    if kind == "stream.data":
        enc = v.get("payload", "")
        try:
            decoded = base64.b64decode(enc).decode("utf-8", "replace")
        except (ValueError, TypeError):
            decoded = enc
        print(
            f"[stream.data] {v.get('plugin_id')}/{v.get('stream_id')} "
            f"seq={v.get('sequence')}: {decoded}"
        )
    elif kind == "connected":
        print(f"[connected] core_version={v.get('core_version')}")
    elif kind == "subscribe_ack":
        print(f"[subscribe_ack] active={v.get('active_categories')}")
    else:
        print(f"[{kind}] {txt}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="ws-watch-python")
    ap.add_argument("--addr", default="localhost:8765", help="Gateway host:port")
    ap.add_argument("--user", default="dev", help="login username")
    ap.add_argument("--password", default="dev", help="login password")
    ap.add_argument("--subscribe", default="", help="comma-separated categories")
    ap.add_argument("--json", action="store_true", help="print raw JSON frames")
    args = ap.parse_args()

    # Line-buffer stdout so frames appear promptly when piped to a file/pager,
    # not only when attached to a TTY.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass

    token = login(args.addr, args.user, args.password)
    print(f"ws-watch-python: logged in as {args.user!r}", file=sys.stderr)

    uri = f"ws://{args.addr}/ws"
    with connect(uri, additional_headers={"Cookie": f"yoke_session={token}"}) as ws:
        print(f"ws-watch-python: connected to {uri}; Ctrl-C to stop", file=sys.stderr)
        if args.subscribe:
            cats = args.subscribe.split(",")
            ws.send(json.dumps({"type": "subscribe", "categories": cats}))
        try:
            for message in ws:
                if isinstance(message, bytes):
                    message = message.decode("utf-8", "replace")
                print_frame(message, args.json)
        except KeyboardInterrupt:
            print("ws-watch-python: shutting down", file=sys.stderr)


if __name__ == "__main__":
    main()
