"""Unit tests for ws-watch-python's pure helpers (no Core, no websockets)."""

import base64
import json

import pytest


def test_print_frame_stream_data(py_tool_module, capsys):
    payload = base64.b64encode(b'{"x":1}').decode()
    frame = json.dumps(
        {
            "type": "stream.data",
            "plugin_id": "p",
            "stream_id": "s",
            "sequence": 3,
            "payload": payload,
        }
    )
    py_tool_module.print_frame(frame, False)
    out = capsys.readouterr().out
    assert "[stream.data] p/s seq=3" in out
    assert '{"x":1}' in out  # payload decoded from base64


def test_print_frame_connected(py_tool_module, capsys):
    py_tool_module.print_frame('{"type":"connected","core_version":"1.0.0"}', False)
    assert "[connected] core_version=1.0.0" in capsys.readouterr().out


def test_print_frame_subscribe_ack(py_tool_module, capsys):
    py_tool_module.print_frame(
        '{"type":"subscribe_ack","active_categories":["stream.data"]}', False
    )
    assert "[subscribe_ack]" in capsys.readouterr().out


def test_print_frame_unknown_type(py_tool_module, capsys):
    py_tool_module.print_frame('{"type":"weird","a":1}', False)
    assert "[weird]" in capsys.readouterr().out


def test_print_frame_invalid_json(py_tool_module, capsys):
    py_tool_module.print_frame("not json", False)
    assert "[?] not json" in capsys.readouterr().out


def test_print_frame_json_passthrough(py_tool_module, capsys):
    raw = '{"type":"connected"}'
    py_tool_module.print_frame(raw, True)
    assert capsys.readouterr().out.strip() == raw


class _Resp:
    """Minimal stand-in for the urlopen() context manager."""

    def __init__(self, cookie):
        self._cookie = cookie

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def headers(self):
        cookie = self._cookie

        class _H:
            @staticmethod
            def get(name):
                return cookie if name == "Set-Cookie" else None

        return _H()


def test_login_parses_cookie(py_tool_module, monkeypatch):
    monkeypatch.setattr(
        py_tool_module.urllib.request,
        "urlopen",
        lambda req, timeout=10: _Resp(
            "yoke_session=THE.JWT.TOKEN; Path=/; HttpOnly; SameSite=Strict"
        ),
    )
    token = py_tool_module.login("localhost:8765", "dev", "dev")
    assert token == "THE.JWT.TOKEN"


def test_login_missing_cookie(py_tool_module, monkeypatch):
    monkeypatch.setattr(
        py_tool_module.urllib.request,
        "urlopen",
        lambda req, timeout=10: _Resp(None),
    )
    with pytest.raises(RuntimeError):
        py_tool_module.login("localhost:8765", "dev", "dev")
