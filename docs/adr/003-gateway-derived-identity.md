# ADR-003: Identity and approval role are derived at the gateway

Status: Accepted
Date: 2026-10-30

## Context
agent-service forwards approve and reject calls to ops-tools with an approver name and a role taken from
its request body. Any caller that can reach agent-service could claim the MANAGER role.

## Decision
- api-gateway is the only public entry point. Callers authenticate with an API key.
- The key maps to an identity and a role. The gateway sets requested_by, approver and role itself and
  ignores any identity or role in the client body.
- Internal services are not published outside the private network (compose network now, private
  subnets and security groups on AWS).
- ops-tools keeps enforcing the approval matrix and the four-eyes rule, so there are two independent checks.

## Consequences
- Keys are static for now. On AWS this becomes Cognito or an IAM-authorised API Gateway with the role in
  a signed claim; the gateway code path that reads the principal stays the same.
- agent-service must never be exposed directly. Compose and Terraform will enforce that.
- Rate limiting is per identity and in-memory; behind several replicas it needs a shared store or the
  API Gateway usage plan.