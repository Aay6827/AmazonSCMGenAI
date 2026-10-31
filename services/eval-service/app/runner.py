import json
import os
from pathlib import Path

import httpx

from app.scoring import score_case

# repo root is parents[3] on a checkout; too shallow inside a container, so fall back to / (GOLDEN_PATH points at the mount there)
_PARENTS = Path(__file__).resolve().parents
DEFAULT_GOLDEN = (_PARENTS[3] if len(_PARENTS) > 3 else Path("/")) / "data" / "golden" / "agent.jsonl"

# Shared client: a new one per call costs ~220 ms here (TLS context setup).
CLIENT = httpx.Client(timeout=30)


class ResetUnavailable(Exception):
    pass


def load_golden() -> list[dict]:
    path = Path(os.getenv("GOLDEN_PATH", str(DEFAULT_GOLDEN)))
    return [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]


def execute_run(reset: bool = True, case_ids: list[str] | None = None) -> list[dict]:
    agent = os.getenv("AGENT_URL", "http://127.0.0.1:40004")
    ops = os.getenv("OPS_URL", "http://127.0.0.1:40003")
    llm = os.getenv("LLM_URL", "http://127.0.0.1:40002")
    cases = load_golden()
    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if c["id"] in wanted]
    if reset:
        # cold state every run: ops-tools data and the llm response cache (cost depends on cache hits)
        for name, base in (("ops-tools-service", ops), ("llm-gateway", llm)):
            try:
                resp = CLIENT.post(f"{base}/v1/admin/reset")
            except httpx.HTTPError as exc:
                raise ResetUnavailable(f"{name} unreachable: {type(exc).__name__}")
            if resp.status_code != 200:
                raise ResetUnavailable(f"{name} refused the reset; start it with ENABLE_TEST_ENDPOINTS=1")
    scores = []
    for case in cases:
        result, error = None, None
        try:
            resp = CLIENT.post(f"{agent}/v1/triage",
                               json={"shipment_id": case["shipment_id"], "requested_by": "eval-service"})
            if resp.status_code == 200:
                result = resp.json()
            else:
                error = f"HTTP {resp.status_code}: {resp.text[:120]}"
        except httpx.HTTPError as exc:
            error = type(exc).__name__
        scores.append(score_case(case, result, error))
    return scores