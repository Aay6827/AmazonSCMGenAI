import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from app.clients import Backends, UpstreamError
from app.triage import run_triage

app = FastAPI(title="agent-service", version="0.1.0")
backends = Backends()
RESULTS: dict[str, dict] = {}

TRIAGES = Counter("agent_triage_total", "Triage runs", ["status"])
TRIAGE_SECONDS = Histogram("agent_triage_seconds", "End-to-end triage latency")


class TriageRequest(BaseModel):
    shipment_id: str = Field(min_length=1)
    requested_by: str = Field(default="ops.user", min_length=1)


class Decision(BaseModel):
    approver: str = Field(min_length=1)
    role: Literal["L1", "TEAM_LEAD", "MANAGER"]


def _raise(exc: UpstreamError):
    status = exc.status if exc.status in (403, 404, 409) else 502
    raise HTTPException(status_code=status, detail=exc.detail)


@app.get("/health")
def health():
    return {"status": "ok", "service": "agent-service"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/triage")
def triage(req: TriageRequest):
    t0 = time.perf_counter()
    try:
        result = run_triage(backends, req.shipment_id, req.requested_by)
    except UpstreamError as exc:
        _raise(exc)
    TRIAGE_SECONDS.observe(time.perf_counter() - t0)
    TRIAGES.labels(result["status"]).inc()
    RESULTS[result["triage_id"]] = result
    return result


@app.get("/v1/triage/{triage_id}")
def get_triage(triage_id: str):
    result = RESULTS.get(triage_id)
    if not result:
        raise HTTPException(404, f"triage {triage_id} not found")
    return result


def _find_action(triage_id: str, action_id: str) -> dict:
    result = RESULTS.get(triage_id)
    if not result:
        raise HTTPException(404, f"triage {triage_id} not found")
    action = next((a for a in result["proposed_actions"] if a["action_id"] == action_id), None)
    if not action:
        raise HTTPException(404, f"action {action_id} was not proposed by triage {triage_id}")
    return action


@app.post("/v1/triage/{triage_id}/actions/{action_id}/approve")
def approve(triage_id: str, action_id: str, decision: Decision):
    action = _find_action(triage_id, action_id)
    try:
        backends.approve(action_id, decision.approver, decision.role)
        done = backends.execute(action_id, decision.approver)
    except UpstreamError as exc:
        _raise(exc)
    action.update(done)
    return action


@app.post("/v1/triage/{triage_id}/actions/{action_id}/reject")
def reject(triage_id: str, action_id: str, decision: Decision):
    action = _find_action(triage_id, action_id)
    try:
        done = backends.reject(action_id, decision.approver, decision.role)
    except UpstreamError as exc:
        _raise(exc)
    action.update(done)
    return action