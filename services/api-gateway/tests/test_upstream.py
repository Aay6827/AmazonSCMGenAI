import httpx
import pytest
from fastapi import HTTPException

from app import upstream


class Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


def test_forward_returns_json_and_sends_headers(monkeypatch):
    seen = {}

    def fake(method, url, **kw):
        seen.update(method=method, url=url, **kw)
        return Resp(200, {"ok": 1})

    monkeypatch.setattr(upstream.httpx, "request", fake)
    assert upstream.forward("POST", "http://x/y", json={"a": 1}, headers={"X-Request-ID": "abc"}) == {"ok": 1}
    assert seen["json"] == {"a": 1} and seen["headers"] == {"X-Request-ID": "abc"}


def test_client_errors_pass_through_with_safe_detail(monkeypatch):
    monkeypatch.setattr(upstream.httpx, "request", lambda *a, **k: Resp(409, {"detail": "Refund blocked"}))
    with pytest.raises(HTTPException) as exc:
        upstream.forward("POST", "http://x")
    assert exc.value.status_code == 409 and exc.value.detail == "Refund blocked"
    monkeypatch.setattr(upstream.httpx, "request", lambda *a, **k: Resp(422, {"detail": [{"loc": "x"}]}))
    with pytest.raises(HTTPException) as exc:
        upstream.forward("POST", "http://x")
    assert exc.value.status_code == 422 and exc.value.detail == "request failed"


def test_server_errors_become_502_without_leaking_the_body(monkeypatch):
    monkeypatch.setattr(upstream.httpx, "request", lambda *a, **k: Resp(500, {"detail": "secret stack trace"}))
    with pytest.raises(HTTPException) as exc:
        upstream.forward("GET", "http://x")
    assert exc.value.status_code == 502 and "secret" not in exc.value.detail


def test_timeout_is_504(monkeypatch):
    def slow(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(upstream.httpx, "request", slow)
    with pytest.raises(HTTPException) as exc:
        upstream.forward("GET", "http://x")
    assert exc.value.status_code == 504


def test_connection_error_is_502(monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(upstream.httpx, "request", down)
    with pytest.raises(HTTPException) as exc:
        upstream.forward("GET", "http://x")
    assert exc.value.status_code == 502


def test_is_up(monkeypatch):
    monkeypatch.setattr(upstream.httpx, "get", lambda *a, **k: Resp(200, {}))
    assert upstream.is_up("agent-service") is True
    monkeypatch.setattr(upstream.httpx, "get", lambda *a, **k: Resp(503, {}))
    assert upstream.is_up("agent-service") is False

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(upstream.httpx, "get", boom)
    assert upstream.is_up("agent-service") is False