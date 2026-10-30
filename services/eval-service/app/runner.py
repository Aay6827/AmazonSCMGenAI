import json
import os
from pathlib import Path

import httpx

from app.scoring import score_case

DEFAULT_GOLDEN = Path(__file__).resolve().parents[3] / "data" / "golden" / "agent.jsonl"


class ResetUnavailable(Exception):
    pass


def load_golden() -> list[dict]:
    path = Path(os.getenv("GOLDEN_PATH", str(DEFAULT_GOLDEN)))
    return [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]


def execute_run(reset: bool = True, case_ids: list[str] | None = None) -> list[dict]:
    agent = os.getenv("AGENT_URL", "http://localhost:40004")
    ops = os.getenv("OPS_URL", "http://localhost:40003")
    cases = load_golden()
    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if c["id"] in wanted]
    if reset:
        try:
            resp = httpx.post(f"{ops}/v1/admin/reset", timeout=10)
        except httpx.HTTPError as exc:
            raise ResetUnavailable(f"ops-tools-service unreachable: {type(exc).__name__}")
        if resp.status_code != 200:
            raise ResetUnavailable("ops-tools-service refused the reset; start it with ENABLE_TEST_ENDPOINTS=1")
    scores = []
    for case in cases:
        result, error = None, None
        try:
            resp = httpx.post(f"{agent}/v1/triage",
                              json={"shipment_id": case["shipment_id"], "requested_by": "eval-service"}, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
            else:
                error = f"HTTP {resp.status_code}: {resp.text[:120]}"
        except httpx.HTTPError as exc:
            error = type(exc).__name__
        scores.append(score_case(case, result, error))
    return scores