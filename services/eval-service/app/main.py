import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel

from app.runner import ResetUnavailable, execute_run, load_golden
from app.scoring import aggregate, evaluate_gates

app = FastAPI(title="eval-service", version="0.1.0")
LATEST: dict = {}

RUNS = Counter("eval_runs_total", "Evaluation runs", ["outcome"])
METRIC = Gauge("eval_metric", "Latest evaluation metric", ["name"])


class RunRequest(BaseModel):
    reset: bool = True
    case_ids: list[str] | None = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "eval-service"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/golden")
def golden():
    return {"cases": [{"id": c["id"], "shipment_id": c["shipment_id"], "expect_status": c["expect_status"]}
                      for c in load_golden()]}


@app.post("/v1/run")
def run(req: RunRequest | None = None):
    req = req or RunRequest()
    try:
        scores = execute_run(req.reset, req.case_ids)
    except ResetUnavailable as exc:
        RUNS.labels("error").inc()
        raise HTTPException(409, str(exc))
    if not scores:
        raise HTTPException(422, "no golden cases selected")
    summary = aggregate(scores)
    gates = evaluate_gates(summary)
    passed = all(g["passed"] for g in gates)
    report = {
        "run_id": f"EVAL-{uuid.uuid4().hex[:8]}",
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed, "metrics": summary, "gates": gates, "cases": scores,
    }
    LATEST.clear()
    LATEST.update(report)
    RUNS.labels("passed" if passed else "failed").inc()
    for name, value in summary.items():
        if isinstance(value, (int, float)):
            METRIC.labels(name).set(value)
    return report


@app.get("/v1/report/latest")
def latest():
    if not LATEST:
        raise HTTPException(404, "no evaluation has been run yet")
    return LATEST