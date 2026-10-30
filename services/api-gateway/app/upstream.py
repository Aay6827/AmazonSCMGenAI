import os

import httpx
from fastapi import HTTPException

SERVICES = {
    "ingest-service": ("INGEST_URL", "http://127.0.0.1:40000"),
    "retrieval-service": ("RETRIEVAL_URL", "http://127.0.0.1:40001"),
    "llm-gateway": ("LLM_URL", "http://127.0.0.1:40002"),
    "ops-tools-service": ("OPS_URL", "http://127.0.0.1:40003"),
    "agent-service": ("AGENT_URL", "http://127.0.0.1:40004"),
    "eval-service": ("EVAL_URL", "http://127.0.0.1:40005"),
}


def url_for(name: str) -> str:
    env, default = SERVICES[name]
    return os.getenv(env, default)


def is_up(name: str) -> bool:
    try:
        return httpx.get(f"{url_for(name)}/health", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def forward(method: str, url: str, *, json=None, headers=None):
    try:
        resp = httpx.request(method, url, json=json, headers=headers, timeout=httpx.Timeout(30.0, connect=3.0))
    except httpx.TimeoutException:
        raise HTTPException(504, "upstream timed out")
    except httpx.HTTPError:
        raise HTTPException(502, "upstream unavailable")
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 500:
        raise HTTPException(502, "upstream error")
    if resp.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else None
        raise HTTPException(resp.status_code, detail if isinstance(detail, str) else "request failed")
    return body