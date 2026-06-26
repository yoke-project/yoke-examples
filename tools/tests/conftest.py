"""Fixtures for the tools test suite.

Two kinds of tests:
- unit: import ws-watch-python's pure helpers and test them in isolation;
- integration: start a real Core + hello-plugin-go and run the built ws-watch
  tool binaries against the Gateway, asserting they receive stream.data.

The integration fixture skips automatically when the required binaries are not
built (the Core binary and the example binaries via `just build`).
"""

import importlib.util
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
REPO = TOOLS.parent                       # yoke-examples
BUILD = REPO / "build"
WORKSPACE = REPO.parent                   # workspace/
CORE_BIN = WORKSPACE / "yoke-core" / "build" / "yoke-core"
PLUGIN_BIN = BUILD / "hello-plugin-go"
PLUGIN_MANIFEST = REPO / "plugins" / "hello-plugin-go" / "manifest.json"


@pytest.fixture(scope="session")
def py_tool_module():
    """Load tools/ws-watch-python/main.py as an importable module."""
    path = TOOLS / "ws-watch-python" / "main.py"
    spec = importlib.util.spec_from_file_location("ws_watch_python_main", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


@pytest.fixture(scope="session")
def core_gateway(tmp_path_factory):
    """Start Core + hello-plugin-go; yield the Gateway TCP address (host:port)."""
    if not CORE_BIN.exists():
        pytest.skip(f"core binary not built: {CORE_BIN}")
    if not PLUGIN_BIN.exists():
        pytest.skip(f"hello-plugin-go not built: {PLUGIN_BIN} (run `just build`)")

    base = tmp_path_factory.mktemp("core")
    (base / "run").mkdir()
    (base / "lib").mkdir()
    mdir = base / "etc" / "plugins.d" / "hello-plugin-go"
    mdir.mkdir(parents=True)
    shutil.copy(PLUGIN_MANIFEST, mdir / "manifest.json")

    port = _free_port()
    core_sock = base / "run" / "core.sock"
    cfg = base / "core.test.yaml"
    cfg.write_text(
        f"""\
core: {{id: yoke-core-test, log_level: warn, log_format: text, log_path: stderr}}
transport:
  sock_dir: {base}/run/
  core_sock: {core_sock}
  operator_sock: {base}/run/operator.sock
  shell_sock: {base}/run/shell.sock
  frontend_sock: {base}/run/frontend.sock
registry: {{db_path: {base}/lib/registry.db}}
log_store: {{db_path: {base}/lib/logs.db}}
discovery: {{manifest_dir: {base}/etc/plugins.d/}}
gateway: {{dev_addr: 127.0.0.1:{port}}}
auth:
  jwt_secret: "test-secret-0123456789abcdef0123456789abcdef"
  users:
    - username: dev
      password: dev
"""
    )

    core = subprocess.Popen(
        [str(CORE_BIN), "--config", str(cfg)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    plugin = None
    try:
        if not _wait_port("127.0.0.1", port):
            raise RuntimeError("Core gateway did not come up")
        for _ in range(40):
            if core_sock.exists():
                break
            time.sleep(0.1)
        env = dict(os.environ, YOKE_CORE_SOCKET=str(core_sock))
        plugin = subprocess.Popen(
            [str(PLUGIN_BIN)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2.0)  # let it register and start streaming
        yield f"127.0.0.1:{port}"
    finally:
        if plugin is not None:
            plugin.terminate()
        core.terminate()
        try:
            core.wait(timeout=5)
        except subprocess.TimeoutExpired:
            core.kill()
