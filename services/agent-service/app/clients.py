import os
from urllib.parse import quote

import httpx
from prometheus_client import Counter

UPSTREAM_ERRORS = Counter("agent_upstream_errors_total", "Failed upstream calls", ["service"])


class UpstreamError(Exception):
    def __init__(self, service: str, status: int, detail: str):
        super().__init__(f"{service}: {status} {detail}")
        self.service = service
        self.status = status
        self.detail = detail


def _call(service: str, method: str, url: str, **kwargs):
    try:
        resp = httpx.request(method, url, timeout=10, **kwargs)
    except httpx.HTTPError as exc:
        UPSTREAM_ERRORS.labels(service).inc()
        raise UpstreamError(service, 502, f"{service} unreachable: {type(exc).__name__}")
    if resp.status_code >= 400:
        UPSTREAM_ERRORS.labels(service).inc()
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise UpstreamError(service, resp.status_code, str(detail))
    return resp.json()


class Backends:
    def __init__(self):
        self.ops = os.getenv("OPS_URL", "http://127.0.0.1:40003")
        self.retrieval = os.getenv("RETRIEVAL_URL", "http://127.0.0.1:40001")
        self.llm = os.getenv("LLM_URL", "http://127.0.0.1:40002")

    def get_shipment(self, sid: str):
        return _call("ops-tools", "GET", f"{self.ops}/v1/shipments/{quote(sid, safe='')}")

    def lane_status(self, origin: str, destination: str):
        return _call("ops-tools", "GET", f"{self.ops}/v1/lane-status",
                     params={"origin": origin, "destination": destination})

    def search(self, query: str, k: int = 4):
        data = _call("retrieval-service", "POST", f"{self.retrieval}/v1/search",
                     json={"query": query, "k": k})
        return data["results"]

    def generate(self, messages: list[dict], max_tokens: int = 400, tier: str = "small"):
        return _call("llm-gateway", "POST", f"{self.llm}/v1/generate",
                     json={"messages": messages, "max_tokens": max_tokens, "tier": tier})

    def create_action(self, payload: dict):
        return _call("ops-tools", "POST", f"{self.ops}/v1/actions", json=payload)

    def approve(self, action_id: str, approver: str, role: str):
        return _call("ops-tools", "POST", f"{self.ops}/v1/actions/{quote(action_id, safe='')}/approve",
                     json={"approver": approver, "role": role})

    def reject(self, action_id: str, approver: str, role: str):
        return _call("ops-tools", "POST", f"{self.ops}/v1/actions/{quote(action_id, safe='')}/reject",
                     json={"approver": approver, "role": role})

    def execute(self, action_id: str, executed_by: str):
        return _call("ops-tools", "POST", f"{self.ops}/v1/actions/{quote(action_id, safe='')}/execute",
                     json={"executed_by": executed_by})