import os

import httpx


def push_chunks(chunks: list[dict], replace: bool) -> dict:
    base = os.getenv("RETRIEVAL_URL", "http://localhost:40001")
    resp = httpx.post(f"{base}/v1/index", json={"chunks": chunks, "replace": replace}, timeout=10)
    resp.raise_for_status()
    return resp.json()