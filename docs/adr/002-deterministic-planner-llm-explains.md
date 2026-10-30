# ADR-002: Deterministic action planner; the LLM explains, it does not choose actions

Status: Accepted
Date: 2026-10-30

## Context
The agent can propose write actions (refunds, reships, carrier tickets) on customer orders.
A wrong action costs money and trust, and model output is not guaranteed to be consistent.

## Options
1. LLM chooses tools and actions freely (fully agentic loop).
2. Rule-based planner chooses actions from computed facts; the LLM writes the cited explanation.
3. LLM proposes actions, a rule layer validates them against an allow-list.

## Decision
Option 2 for phase 1. Option 3 is planned for the Bedrock phase, with the planner kept as the validator.

## Rationale
- Facts such as the SLA band are computed by ops-tools, so the model never does date arithmetic.
- Action choice is reproducible and unit-testable; the planner is tested never to propose an action the SOPs forbid.
- Policy is enforced twice: the planner avoids forbidden actions, ops-tools refuses them anyway.
- Every action still requires human approval with a four-eyes rule.
- The LLM output is verified: every cited chunk must have been retrieved, otherwise it is discarded.

## Consequences
- Less flexible than a free agent; novel situations return NEEDS_HUMAN instead of improvising.
- This deliberately differs from the first sketch in ARCHITECTURE.md, where the LLM received tools.
- The eval-service can score the planner and the explanations separately.