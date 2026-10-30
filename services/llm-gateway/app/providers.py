import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderResult:
    text: str
    model: str
    tokens_in: int | None = None
    tokens_out: int | None = None


class Provider(ABC):
    name: str

    @abstractmethod
    def generate(self, messages: list[dict], max_tokens: int, tier: str) -> ProviderResult: ...


class StubProvider(Provider):
    """Deterministic provider for local dev and CI. Cites any [SOURCE:id] markers it sees."""

    name = "stub"

    def generate(self, messages, max_tokens, tier):
        joined = "\n".join(m["content"] for m in messages)
        sources = sorted(set(re.findall(r"\[SOURCE:([^\]\s]+)\]", joined)))
        if sources:
            text = f"Recommended action drawn from retrieved guidance. Sources: {', '.join(sources)}."
        else:
            text = "Insufficient context to answer. No sources were provided."
        return ProviderResult(text=text[: max_tokens * 4], model=f"stub-{tier}")


class BedrockProvider(Provider):
    """Amazon Bedrock via the Converse API. Model IDs come from env vars, never hard-coded."""

    name = "bedrock"

    def __init__(self, region: str | None = None):
        import boto3  # imported lazily so local dev needs no AWS SDK

        self._client = boto3.client(
            "bedrock-runtime", region_name=region or os.getenv("AWS_REGION", "ap-south-1")
        )
        self._models = {
            "small": os.getenv("BEDROCK_MODEL_SMALL", ""),
            "large": os.getenv("BEDROCK_MODEL_LARGE", ""),
        }

    def generate(self, messages, max_tokens, tier):
        model_id = self._models.get(tier, "")
        if not model_id:
            raise RuntimeError(f"BEDROCK_MODEL_{tier.upper()} is not set")
        system = [{"text": m["content"]} for m in messages if m["role"] == "system"]
        convo = [
            {"role": m["role"], "content": [{"text": m["content"]}]}
            for m in messages
            if m["role"] != "system"
        ]
        kwargs = {
            "modelId": model_id,
            "messages": convo,
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if system:
            kwargs["system"] = system
        resp = self._client.converse(**kwargs)
        usage = resp.get("usage", {})
        return ProviderResult(
            text=resp["output"]["message"]["content"][0]["text"],
            model=model_id,
            tokens_in=usage.get("inputTokens"),
            tokens_out=usage.get("outputTokens"),
        )


def get_provider() -> Provider:
    if os.getenv("LLM_PROVIDER", "stub").lower() == "bedrock":
        return BedrockProvider()
    return StubProvider()