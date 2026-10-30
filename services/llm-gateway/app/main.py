import hashlib
import json
import time

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.cache import LRUCache
from app.guardrails import is_injection, redact
from app.metering import COST, LAT, REQS, TOKENS, cost_usd, estimate_tokens
from app.models import GenerateRequest, GenerateResponse
from app.providers import get_provider

app = FastAPI(title="llm-gateway", version="0.1.0")
_cache = LRUCache(256)
_provider = get_provider()


@app.get("/health")
def health():
    return {"status": "ok", "service": "llm-gateway", "provider": _provider.name}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _cache_key(msgs: list[dict], tier: str, max_tokens: int) -> str:
    raw = json.dumps([msgs, tier, max_tokens], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


@app.post("/v1/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    start = time.perf_counter()

    msgs: list[dict] = []
    redactions = 0
    for m in req.messages:
        clean, n = redact(m.content)
        redactions += n
        msgs.append({"role": m.role, "content": clean})

    if any(is_injection(m["content"]) for m in msgs if m["role"] != "assistant"):
        REQS.labels(_provider.name, req.tier, "blocked").inc()
        return GenerateResponse(
            text="Request blocked by guardrails: possible prompt injection.",
            provider=_provider.name,
            model="none",
            tier=req.tier,
            tokens_in=0,
            tokens_out=0,
            latency_ms=round((time.perf_counter() - start) * 1000, 3),
            cost_usd=0.0,
            cache_hit=False,
            redactions=redactions,
            blocked=True,
        )

    key = _cache_key(msgs, req.tier, req.max_tokens)
    cached = _cache.get(key)
    if cached is not None:
        REQS.labels(_provider.name, req.tier, "cache_hit").inc()
        return cached.model_copy(
            update={
                "cache_hit": True,
                "cost_usd": 0.0,
                "latency_ms": round((time.perf_counter() - start) * 1000, 3),
            }
        )

    try:
        result = _provider.generate(msgs, req.max_tokens, req.tier)
    except Exception as exc:
        REQS.labels(_provider.name, req.tier, "error").inc()
        raise HTTPException(status_code=502, detail=f"provider error: {type(exc).__name__}")

    text, out_redactions = redact(result.text)
    redactions += out_redactions
    tokens_in = (
        result.tokens_in
        if result.tokens_in is not None
        else sum(estimate_tokens(m["content"]) for m in msgs)
    )
    tokens_out = result.tokens_out if result.tokens_out is not None else estimate_tokens(text)
    spend = cost_usd(req.tier, tokens_in, tokens_out)
    elapsed = time.perf_counter() - start

    REQS.labels(_provider.name, req.tier, "ok").inc()
    TOKENS.labels("in", req.tier).inc(tokens_in)
    TOKENS.labels("out", req.tier).inc(tokens_out)
    COST.labels(req.tier).inc(spend)
    LAT.labels(_provider.name).observe(elapsed)

    resp = GenerateResponse(
        text=text,
        provider=_provider.name,
        model=result.model,
        tier=req.tier,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=round(elapsed * 1000, 3),
        cost_usd=spend,
        cache_hit=False,
        redactions=redactions,
        blocked=False,
    )
    _cache.put(key, resp)
    return resp