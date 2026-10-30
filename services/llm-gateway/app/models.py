from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class GenerateRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    tier: Literal["small", "large"] = "small"


class GenerateResponse(BaseModel):
    text: str
    provider: str
    model: str
    tier: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    cost_usd: float
    cache_hit: bool
    redactions: int
    blocked: bool