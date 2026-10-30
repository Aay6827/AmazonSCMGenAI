from prometheus_client import Counter, Histogram

# Illustrative USD per 1M tokens (input, output). Replace with real model pricing in phase 3.
PRICING = {"small": (0.25, 1.25), "large": (3.0, 15.0)}

REQS = Counter("llm_requests_total", "LLM gateway requests", ["provider", "tier", "outcome"])
TOKENS = Counter("llm_tokens_total", "Tokens processed", ["direction", "tier"])
COST = Counter("llm_cost_usd_total", "Estimated spend in USD", ["tier"])
LAT = Histogram("llm_latency_seconds", "Provider latency", ["provider"])


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def cost_usd(tier: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICING[tier]
    return round((tokens_in * price_in + tokens_out * price_out) / 1_000_000, 8)