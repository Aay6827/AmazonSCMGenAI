import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as main
from app import upstream
from app.auth import load_keys
from app.ratelimit import TokenBucket

client = TestClient(main.app)
L1 = {"X-API-Key": "l1-key-0001"}
LEAD = {"X-API-Key": "lead-key-001"}
APPROVE = "/v1/triage/TRI-abc12345/actions/ACT-0001/approve"


class Recorder:
    def __init__(self):
        self.calls, self.reply = [], {"ok": True}

    def __call__(self, method, url, *, json=None, headers=None):
        self.calls.append({"method": method, "url": url, "json": json, "headers": headers})
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setattr(main, "KEYS", load_keys("l1-key-0001:ops.alice:L1,lead-key-001:lead.bob:TEAM_LEAD"))
    monkeypatch.setattr(main, "LIMITER", TokenBucket(1000))


@pytest.fixture
def fwd(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(upstream, "forward", rec)
    return rec


def test_health_is_public_and_reports_auth_state():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "api-gateway", "auth_configured": True}


def test_missing_or_wrong_key_is_401(fwd):
    body = {"shipment_id": "SHP-1001"}
    assert client.post("/v1/triage", json=body).status_code == 401
    assert client.post("/v1/triage", json=body, headers={"X-API-Key": "nope-nope-nope"}).status_code == 401
    assert fwd.calls == []


def test_no_keys_configured_rejects_everything(fwd, monkeypatch):
    monkeypatch.setattr(main, "KEYS", {})
    assert client.post("/v1/triage", json={"shipment_id": "SHP-1001"}, headers=L1).status_code == 401
    assert client.get("/health").json()["auth_configured"] is False


def test_triage_forwards_identity_and_request_id(fwd):
    r = client.post("/v1/triage", json={"shipment_id": "SHP-1001"}, headers={**L1, "X-Request-ID": "req-12345678"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    call = fwd.calls[0]
    assert call["method"] == "POST" and call["url"].endswith("/v1/triage")
    assert call["json"] == {"shipment_id": "SHP-1001", "requested_by": "ops.alice"}
    assert call["headers"] == {"X-Request-ID": "req-12345678"}
    assert r.headers["x-request-id"] == "req-12345678"


def test_request_id_is_generated_when_missing_or_invalid():
    r = client.get("/health", headers={"X-Request-ID": "bad id!"})
    assert r.headers["x-request-id"] != "bad id!" and len(r.headers["x-request-id"]) == 32
    assert len(client.get("/health").headers["x-request-id"]) == 32


def test_triage_body_is_validated_after_auth(fwd):
    assert client.post("/v1/triage", json={"shipment_id": "../etc"}, headers=L1).status_code == 422
    assert client.post("/v1/triage", json={"shipment_id": ""}, headers=L1).status_code == 422
    assert client.post("/v1/triage", json={}, headers=L1).status_code == 422
    assert fwd.calls == []


def test_get_triage_is_proxied(fwd):
    fwd.reply = {"triage_id": "TRI-abc12345"}
    r = client.get("/v1/triage/TRI-abc12345", headers=L1)
    assert r.json() == {"triage_id": "TRI-abc12345"}
    assert fwd.calls[0]["method"] == "GET" and fwd.calls[0]["url"].endswith("/v1/triage/TRI-abc12345")


def test_approve_uses_identity_and_role_from_the_key_not_the_body(fwd):
    client.post(APPROVE, headers=L1, json={"approver": "someone.else", "role": "MANAGER"})
    client.post(APPROVE, headers=LEAD)
    assert fwd.calls[0]["json"] == {"approver": "ops.alice", "role": "L1"}
    assert fwd.calls[1]["json"] == {"approver": "lead.bob", "role": "TEAM_LEAD"}
    assert fwd.calls[0]["url"].endswith("/v1/triage/TRI-abc12345/actions/ACT-0001/approve")


def test_reject_uses_identity_and_role_from_the_key(fwd):
    client.post(APPROVE.replace("approve", "reject"), headers=LEAD, json={"role": "MANAGER"})
    assert fwd.calls[0]["json"] == {"approver": "lead.bob", "role": "TEAM_LEAD"}
    assert fwd.calls[0]["url"].endswith("/actions/ACT-0001/reject")


def test_upstream_client_error_passes_through(fwd):
    fwd.reply = HTTPException(403, "role L1 is insufficient; TEAM_LEAD or higher required")
    r = client.post(APPROVE, headers=L1)
    assert r.status_code == 403 and "insufficient" in r.json()["detail"]


def test_path_ids_are_validated(fwd):
    assert client.post("/v1/triage/TRI-abc12345/actions/ACT_0001/approve", headers=L1).status_code == 422
    assert client.get("/v1/triage/TRI.abc", headers=L1).status_code == 422
    assert fwd.calls == []


def test_rate_limit_returns_429_with_retry_after(fwd, monkeypatch):
    monkeypatch.setattr(main, "LIMITER", TokenBucket(2, clock=lambda: 0.0))
    url = "/v1/triage/TRI-abc12345"
    assert client.get(url, headers=L1).status_code == 200
    assert client.get(url, headers=L1).status_code == 200
    r = client.get(url, headers=L1)
    assert r.status_code == 429 and r.headers["retry-after"] == "30"
    assert client.get(url, headers=LEAD).status_code == 200


def test_status_aggregates_downstream_health(monkeypatch):
    monkeypatch.setattr(upstream, "is_up", lambda name: name != "eval-service")
    d = client.get("/v1/status", headers=L1).json()
    assert d["status"] == "degraded" and d["services"]["eval-service"] == "down"
    monkeypatch.setattr(upstream, "is_up", lambda name: True)
    assert client.get("/v1/status", headers=L1).json()["status"] == "ok"
    assert client.get("/v1/status").status_code == 401


def test_metrics_exposed_and_unmatched_paths_share_one_label():
    client.get("/nope-1234")
    text = client.get("/metrics").text
    assert "gateway_requests_total" in text and 'route="unmatched"' in text and "nope-1234" not in text