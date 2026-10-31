import httpx
import pytest

from app import clients
from app.clients import Backends, UpstreamError


class Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def test_success_returns_json(monkeypatch):
    monkeypatch.setattr(clients.CLIENT, "request", lambda *a, **k: Resp(200, {"ok": True}))
    assert Backends().get_shipment("SHP-1") == {"ok": True}


def test_error_status_keeps_status_and_detail(monkeypatch):
    monkeypatch.setattr(clients.CLIENT, "request", lambda *a, **k: Resp(409, {"detail": "Refund blocked"}))
    with pytest.raises(UpstreamError) as exc:
        Backends().create_action({})
    assert exc.value.status == 409 and exc.value.detail == "Refund blocked"


def test_connection_error_becomes_502(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(clients.CLIENT, "request", boom)
    with pytest.raises(UpstreamError) as exc:
        Backends().search("q", 3)
    assert exc.value.status == 502 and "unreachable" in exc.value.detail


def test_path_parameters_are_quoted(monkeypatch):
    seen = {}

    def fake(method, url, **kwargs):
        seen["url"] = url
        return Resp(200, {})

    monkeypatch.setattr(clients.CLIENT, "request", fake)
    Backends().get_shipment("../etc/passwd")
    assert "/v1/shipments/..%2Fetc%2Fpasswd" in seen["url"]

def test_calls_use_the_shared_client_not_a_new_one_per_call(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("a new httpx client was built per call")

    monkeypatch.setattr(clients.httpx, "request", forbidden)
    monkeypatch.setattr(clients.CLIENT, "request", lambda *a, **k: Resp(200, {"ok": True}))
    assert Backends().get_shipment("SHP-1") == {"ok": True}