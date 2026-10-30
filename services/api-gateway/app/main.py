import math
import os
import re
import secrets
import time
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from app import upstream
from app.auth import Principal, load_keys
from app.ratelimit import TokenBucket

app = FastAPI(title="api-gateway", version="0.1.0")

KEYS = load_keys(os.getenv("API_KEYS"))  # fails fast on a malformed config
LIMITER = TokenBucket(int(os.getenv("RATE_LIMIT_PER_MIN", "120")))

ID_PATTERN = r"^[A-Za-z0-9-]{1,40}$"
REQ_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")

REQS = Counter("gateway_requests_total", "Gateway requests", ["method", "route", "status"])
LAT = Histogram("gateway_request_seconds", "Gateway request latency")


@app.middleware("http")
async def request_context(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    rid = incoming if REQ_ID_RE.match(incoming) else uuid.uuid4().hex
    request.state.request_id = rid
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    REQS.labels(request.method, route.path if route else "unmatched", str(response.status_code)).inc()
    LAT.observe(time.perf_counter() - start)
    response.headers["X-Request-ID"] = rid
    return response


def authenticate(x_api_key: str | None = Header(default=None)) -> Principal:
    if not x_api_key:
        raise HTTPException(401, "invalid or missing API key")
    supplied = x_api_key.encode()
    match = None
    for key, principal in KEYS.items():  # no early exit: same work for every key
        if secrets.compare_digest(key.encode(), supplied):
            match = principal
    if match is None:
        raise HTTPException(401, "invalid or missing API key")
    allowed, retry = LIMITER.allow(match.identity)
    if not allowed:
        raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(max(1, math.ceil(retry)))})
    return match


class TriageIn(BaseModel):
    shipment_id: str = Field(pattern=r"^[A-Za-z0-9-]{1,32}$")


def _headers(request: Request) -> dict:
    return {"X-Request-ID": request.state.request_id}


def _agent(path: str) -> str:
    return f"{upstream.url_for('agent-service')}{path}"


@app.get("/health")
def health():
    return {"status": "ok", "service": "api-gateway", "auth_configured": bool(KEYS)}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/status")
def status(who: Principal = Depends(authenticate)):
    services = {name: ("up" if upstream.is_up(name) else "down") for name in upstream.SERVICES}
    return {"status": "ok" if all(v == "up" for v in services.values()) else "degraded", "services": services}


@app.post("/v1/triage")
def triage(body: TriageIn, request: Request, who: Principal = Depends(authenticate)):
    return upstream.forward("POST", _agent("/v1/triage"),
                            json={"shipment_id": body.shipment_id, "requested_by": who.identity},
                            headers=_headers(request))


@app.get("/v1/triage/{triage_id}")
def get_triage(request: Request, triage_id: str = Path(pattern=ID_PATTERN), who: Principal = Depends(authenticate)):
    return upstream.forward("GET", _agent(f"/v1/triage/{triage_id}"), headers=_headers(request))


@app.post("/v1/triage/{triage_id}/actions/{action_id}/approve")
def approve(request: Request, triage_id: str = Path(pattern=ID_PATTERN), action_id: str = Path(pattern=ID_PATTERN),
            who: Principal = Depends(authenticate)):
    # identity and role come from the API key; any body the client sends is ignored
    return upstream.forward("POST", _agent(f"/v1/triage/{triage_id}/actions/{action_id}/approve"),
                            json={"approver": who.identity, "role": who.role}, headers=_headers(request))


@app.post("/v1/triage/{triage_id}/actions/{action_id}/reject")
def reject(request: Request, triage_id: str = Path(pattern=ID_PATTERN), action_id: str = Path(pattern=ID_PATTERN),
           who: Principal = Depends(authenticate)):
    return upstream.forward("POST", _agent(f"/v1/triage/{triage_id}/actions/{action_id}/reject"),
                            json={"approver": who.identity, "role": who.role}, headers=_headers(request))