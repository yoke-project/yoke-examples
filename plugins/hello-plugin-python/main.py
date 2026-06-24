"""hello-plugin-python is a minimal reference Yoke plugin built on the Python SDK
(yoke_sdk_python.pluginapi). It is the Python member of a family of equivalent
"hello" plugins (Go/Rust/Python) that all register the same surface under
distinct plugin IDs. It demonstrates the full plugin lifecycle against a running
Core:

  - dial core.sock and register (bootstrap-token auth)
  - open the bidirectional session and send heartbeats
  - serve a structured stream "hello.tick" that emits a JSON tick once a second
    while Core has started the stream
  - answer the point-in-time query "hello.echo"

Configuration comes from the environment the supervisor sets when it launches a
plugin (YOKE_CORE_SOCKET, YOKE_PLUGIN_ID, YOKE_BOOTSTRAP_TOKEN,
YOKE_PLUGIN_SOCKET); each has a sensible default so the binary can also be run by
hand against a dev Core.
"""

import asyncio
import json
import os
import signal
import time
import uuid

from yoke_sdk_python.pluginapi import (
    AckType,
    Client,
    QueryHandler,
    QueryHandlerResult,
    RegistrationConfig,
    StreamProducer,
)

STREAM_ID = "hello.tick"
QUERY_TYPE = "hello.echo"


def env(key: str, default: str) -> str:
    return os.environ.get(key) or default


def now_ms() -> int:
    return int(time.time() * 1000)


class HelloTick(StreamProducer):
    """Structured stream producer: emits a JSON tick every second until stopped."""

    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id

    async def on_start(self, emitter, stop) -> None:
        print(f"[hello-plugin-python] stream {STREAM_ID} started", flush=True)
        seq = 0
        while not stop.is_set():
            seq += 1
            payload = json.dumps(
                {"seq": seq, "ts": now_ms(), "msg": f"hello from {self.plugin_id}"}
            ).encode()
            await emitter.emit_data(payload)
            try:
                await asyncio.wait_for(stop.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

    def on_stop(self) -> None:
        print(f"[hello-plugin-python] stream {STREAM_ID} stopped", flush=True)


class EchoQuery(QueryHandler):
    """Point-in-time query handler: echoes the params back."""

    def handle(self, query_type: str, params: bytes) -> QueryHandlerResult:
        out = json.dumps(
            {"query": query_type, "echo": params.decode("utf-8", "replace")}
        ).encode()
        return QueryHandlerResult.ok("hello", "v1", out)


async def main() -> None:
    core_sock = env("YOKE_CORE_SOCKET", env("YOKE_CORE_SOCK", "/run/yoke/core.sock"))
    plugin_id = env("YOKE_PLUGIN_ID", "hello-plugin-python")
    # The supervisor injects a real token; for hand-launched dev runs Core accepts
    # any non-empty token (no token was issued), so default to "dev".
    token = env("YOKE_BOOTSTRAP_TOKEN", "dev")

    cfg = RegistrationConfig(
        plugin_id=plugin_id,
        instance_id=str(uuid.uuid4()),
        plugin_version="0.1.0",
        protocol_version="1.0",
        language="python",
        sdk_version="0.1.0",
        bootstrap_token=token,
        capabilities=["hello"],
        streams=[STREAM_ID],
        commands=["StartStream", "StopStream"],
        pid=os.getpid(),
        endpoint=os.environ.get("YOKE_PLUGIN_SOCKET", ""),
    )

    print(f"[hello-plugin-python] connecting to Core at {core_sock}", flush=True)
    client = await Client.dial(core_sock, cfg)
    await client.register()

    client.register_stream_producer(STREAM_ID, "hello", "v1", HelloTick(plugin_id))
    client.register_query_handler(QUERY_TYPE, EchoQuery())

    await client.open_session()
    await client.send_event("plugin.started", "hello-plugin-python started")
    print(
        f"[hello-plugin-python] registered and running (session={client.session_id}); "
        "Ctrl-C to stop",
        flush=True,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - non-Unix fallback
            pass

    hb_task = asyncio.create_task(client.run_heartbeat_loop())
    cmd_queue = client.take_command_receiver()

    async def command_loop() -> None:
        # The SDK already intercepts StartStream/StopStream (producer) and
        # QueryRequest (query handler); only other commands arrive here.
        while True:
            cmd = await cmd_queue.get()
            if cmd.kind in ("shutdown", "restart"):
                await client.send_ack(cmd.command_id, AckType.ACK_TYPE_ACCEPTED)
                await client.send_ack(cmd.command_id, AckType.ACK_TYPE_COMPLETED)
                print(f"[hello-plugin-python] {cmd.kind} — exiting", flush=True)
                stop.set()
                return
            print(f"[hello-plugin-python] unhandled command: {cmd.kind}", flush=True)

    cmd_task = asyncio.create_task(command_loop())

    await stop.wait()

    hb_task.cancel()
    cmd_task.cancel()
    await client.close()
    print("[hello-plugin-python] shutting down", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
