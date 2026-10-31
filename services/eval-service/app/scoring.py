import math
import os

# Hard gates for a clean deterministic run. ("min" = value must be >= limit, "max" = value must be <= limit)
DEFAULT_GATES = {
    "status_accuracy": ("min", 1.0),
    "action_precision": ("min", 1.0),
    "action_recall": ("min", 1.0),
    "forbidden_violations": ("max", 0),
    "role_accuracy": ("min", 1.0),
    "grounded_rate": ("min", 1.0),
    "citation_valid_rate": ("min", 1.0),
    "degraded_cases": ("max", 0),
    "section_hit_rate": ("min", 0.8),
    "latency_ms_p95": ("max", 250),
    "latency_ms_p95": ("max", 250),
}


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def score_case(case: dict, result: dict | None, error: str | None = None) -> dict:
    r = result or {}
    failures: list = []
    warnings: list = []
    if error:
        failures.append(f"request failed: {error}")

    status = r.get("status")
    status_ok = status == case["expect_status"]
    if not status_ok:
        failures.append(f"status {status} != expected {case['expect_status']}")

    actions = r.get("proposed_actions", [])
    proposed = {a["action_type"] for a in actions}
    expected = set(case["expect_actions"])
    forbidden = set(case.get("forbid_actions", []))
    tp, fp, fn = len(proposed & expected), len(proposed - expected), len(expected - proposed)
    if fp or fn:
        failures.append(f"actions {sorted(proposed)} != expected {sorted(expected)}")
    violations = sorted(proposed & forbidden)
    if violations:
        failures.append(f"forbidden actions proposed: {violations}")

    expect_roles = case.get("expect_roles", {})
    role_checked = role_correct = 0
    for a in actions:
        want = expect_roles.get(a["action_type"])
        if want is None:
            continue
        role_checked += 1
        if a.get("required_role") == want:
            role_correct += 1
        else:
            failures.append(f"{a['action_type']} requires {a.get('required_role')}, expected {want}")

    passages = r.get("passages", [])
    have = {(p["doc_id"], p["section"]) for p in passages}
    wanted = [tuple(x) for x in case.get("expect_sections", [])]
    missing = [list(w) for w in wanted if w not in have]
    section_ok = None if not wanted else not missing
    if missing:
        warnings.append(f"governing sections not retrieved: {missing}")

    relevant = set(case.get("relevant_docs", []))
    context_precision = None
    if passages and relevant:
        context_precision = round(sum(1 for p in passages if p["doc_id"] in relevant) / len(passages), 3)

    grounded_ok = None
    if case["expect_status"] in ("PENDING_APPROVAL", "NEEDS_HUMAN"):
        grounded_ok = r.get("grounded") is True
        if not grounded_ok:
            failures.append("explanation not grounded")
    chunk_ids = {p["chunk_id"] for p in passages}
    citations_valid = set(r.get("citations", [])) <= chunk_ids
    if not citations_valid:
        failures.append("citation refers to a chunk that was not retrieved")

    hub_ok = None
    if case.get("expect_hub") is not None:
        lane = r.get("lane") or {}
        hub_ok = lane.get("hub_issue_suspected") is case["expect_hub"]
        if not hub_ok:
            failures.append(f"hub detection mismatch (expected {case['expect_hub']})")

    degraded = r.get("degraded", [])
    if degraded:
        failures.append(f"degraded: {degraded}")

    latency_ms = round(sum(t.get("ms", 0) for t in r.get("trace", [])), 1)
    cost_usd = (r.get("llm") or {}).get("cost_usd") or 0.0

    return {
        "id": case["id"], "shipment_id": case["shipment_id"], "status": status, "status_ok": status_ok,
        "passed": not failures, "failures": failures, "warnings": warnings,
        "proposed": sorted(proposed), "tp": tp, "fp": fp, "fn": fn, "violations": violations,
        "role_checked": role_checked, "role_correct": role_correct,
        "section_ok": section_ok, "missing_sections": missing, "context_precision": context_precision,
        "grounded_ok": grounded_ok, "citations_valid": citations_valid, "hub_ok": hub_ok,
        "degraded": degraded, "latency_ms": latency_ms, "cost_usd": cost_usd,
    }


def _rate(num, den, empty=1.0):
    return round(num / den, 3) if den else empty


def aggregate(scores: list[dict]) -> dict:
    n = len(scores)
    tp, fp, fn = (sum(s[k] for s in scores) for k in ("tp", "fp", "fn"))
    sections = [s["section_ok"] for s in scores if s["section_ok"] is not None]
    grounded = [s["grounded_ok"] for s in scores if s["grounded_ok"] is not None]
    precisions = [s["context_precision"] for s in scores if s["context_precision"] is not None]
    latencies = [s["latency_ms"] for s in scores]
    return {
        "cases": n,
        "cases_passed": sum(1 for s in scores if s["passed"]),
        "status_accuracy": _rate(sum(1 for s in scores if s["status_ok"]), n),
        "action_precision": _rate(tp, tp + fp),
        "action_recall": _rate(tp, tp + fn),
        "forbidden_violations": sum(len(s["violations"]) for s in scores),
        "role_accuracy": _rate(sum(s["role_correct"] for s in scores), sum(s["role_checked"] for s in scores)),
        "section_hit_rate": _rate(sum(1 for x in sections if x), len(sections)),
        "grounded_rate": _rate(sum(1 for x in grounded if x), len(grounded)),
        "citation_valid_rate": _rate(sum(1 for s in scores if s["citations_valid"]), n),
        "degraded_cases": sum(1 for s in scores if s["degraded"]),
        "context_precision": round(sum(precisions) / len(precisions), 3) if precisions else None,
        "latency_ms_p50": percentile(latencies, 50),
        "latency_ms_p95": percentile(latencies, 95),
        "avg_cost_usd": round(sum(s["cost_usd"] for s in scores) / n, 8) if n else 0.0,
    }


def _effective(gates: dict) -> dict:
    """CI runners are slower than a dev machine: allow the p95 latency limit to be raised via env."""
    gates = dict(gates)
    override = os.getenv("EVAL_LATENCY_P95_MS")
    if override:
        gates["latency_ms_p95"] = ("max", float(override))
    return gates


def evaluate_gates(metrics: dict, gates: dict = DEFAULT_GATES) -> list[dict]:
    out = []
    for name, (kind, limit) in _effective(gates).items():
        value = metrics[name]
        ok = value >= limit if kind == "min" else value <= limit
        out.append({"metric": name, "value": value, "rule": f"{'>=' if kind == 'min' else '<='} {limit}", "passed": ok})
    return out