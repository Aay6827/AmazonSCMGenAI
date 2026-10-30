# ADR-001: Use RAG with a tool-using agent instead of fine-tuning

Status: Accepted
Date: 2026-10-30

## Context
SOPs and carrier SLAs change weekly. The system must cite sources and explain why it recommended an action.

## Options
1. Fine-tune a model on historical tickets and SOPs.
2. RAG over a versioned document store, plus an agent with tools for live shipment data.
3. A fixed rules engine with no LLM.

## Decision
Option 2.

## Rationale
- Knowledge updates by re-ingesting documents, not retraining.
- Citations come naturally from retrieved passages, giving auditability.
- Live facts (shipment state) come from tools, not model memory.
- Lower cost and faster iteration than fine-tuning.

## Consequences
- Retrieval quality becomes the main quality lever, so eval-service measures it.
- Added latency from the retrieval hop; mitigated by caching.
- Rules engine stays as a fallback for the highest-risk actions.
