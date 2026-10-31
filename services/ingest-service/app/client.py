import os

import httpx


# Shared client: a new one per call costs ~220 ms here (TLS context setup).
CLIENT = httpx.Client(timeout=10)


def push_chunks(chunks: list[dict], replace: bool) -> dict:
    base = os.getenv("RETRIEVAL_URL", "http://127.0.0.1:40001")
    resp = CLIENT.post(f"{base}/v1/index", json={"chunks": chunks, "replace": replace})
    resp.raise_for_status()
    return resp.json()