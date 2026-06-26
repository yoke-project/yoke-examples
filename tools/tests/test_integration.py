"""Integration tests: run each built ws-watch tool against a live Core.

These exercise the full Gateway consumer path (REST login -> JWT cookie ->
WebSocket -> stream.data) for every language twin. Each parametrization skips if
that tool's binary is not built; the whole module skips (via the core_gateway
fixture) if the Core or plugin binaries are missing.
"""

import subprocess
import threading
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parent.parent.parent / "build"

TOOLS = ["ws-watch-go", "ws-watch-rust", "ws-watch-python"]


@pytest.mark.parametrize("tool", TOOLS)
def test_tool_receives_stream_data(core_gateway, tool):
    binary = BUILD / tool
    if not binary.exists():
        pytest.skip(f"{tool} not built: {binary} (run `just build`)")

    proc = subprocess.Popen(
        [str(binary), "--addr", core_gateway, "--user", "dev", "--password", "dev"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # The tools run until the connection drops; terminate after a short window
    # and inspect whatever they printed.
    timer = threading.Timer(6.0, proc.terminate)
    timer.start()
    try:
        out, _ = proc.communicate(timeout=20)
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
            out, _ = proc.communicate()

    assert "[stream.data]" in out, f"{tool} output:\n{out}"
    assert "hello.tick" in out, f"{tool} output:\n{out}"
