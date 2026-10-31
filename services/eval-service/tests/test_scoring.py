from app.runner import load_golden
from app.scoring import aggregate, evaluate_gates, percentile, score_case

CASE = {
    "id": "c1", "shipment_id": "SHP-1", "expect_status": "PENDING_APPROVAL",
    "expect_actions": ["carrier_escalation", "notify_customer"], "forbid_actions": ["refund"],
    "expect_roles": {"carrier_escalation": "L1", "notify_customer": "L1"},
    "expect_sections": [["sop-delay-01", "Actions by delay"]],
    "relevant_docs": ["sop-delay-01", "sop-approval-05"],
}
ESC = {"action_type": "carrier_escalation", "required_role": "L1"}
NOTE = {"action_type": "notify_customer", "required_role": "L1"}
REFUND = {"action_type": "refund", "required_role": "L1"}


def result(**over):
    base = {
        "status": "PENDING_APPROVAL",
        "proposed_actions": [ESC, NOTE],
        "passages": [
            {"chunk_id": "sop-delay-01#3", "doc_id": "sop-delay-01", "section": "Actions by delay"},
            {"chunk_id": "sop-approval-05#4", "doc_id": "sop-approval-05", "section": "Carrier tickets"},
        ],
        "citations": ["sop-delay-01#3"], "grounded": True, "lane": None, "degraded": [],
        "trace": [{"step": "get_shipment", "ms": 5.0}, {"step": "llm_generate", "ms": 10.0}],
        "llm": {"cost_usd": 0.0002},
    }
    base.update(over)
    return base


def test_perfect_case_passes():
    s = score_case(CASE, result())
    assert s["passed"] is True and s["failures"] == []
    assert (s["tp"], s["fp"], s["fn"]) == (2, 0, 0)
    assert s["section_ok"] is True and s["grounded_ok"] is True and s["context_precision"] == 1.0
    assert s["latency_ms"] == 15.0 and s["cost_usd"] == 0.0002


def test_extra_and_missing_actions_are_scored():
    s = score_case(CASE, result(proposed_actions=[ESC, {"action_type": "reship", "required_role": "L1"}]))
    assert s["passed"] is False and (s["tp"], s["fp"], s["fn"]) == (1, 1, 1)


def test_forbidden_action_is_flagged():
    s = score_case(CASE, result(proposed_actions=[ESC, NOTE, REFUND]))
    assert s["violations"] == ["refund"] and s["passed"] is False


def test_wrong_approval_role_fails():
    s = score_case(CASE, result(proposed_actions=[{"action_type": "carrier_escalation", "required_role": "MANAGER"}, NOTE]))
    assert s["role_checked"] == 2 and s["role_correct"] == 1 and s["passed"] is False


def test_missing_section_is_a_warning_not_a_failure():
    r = result(passages=[{"chunk_id": "sop-delay-01#1", "doc_id": "sop-delay-01", "section": "Scope"}],
               citations=["sop-delay-01#1"])
    s = score_case(CASE, r)
    assert s["section_ok"] is False and s["passed"] is True
    assert s["missing_sections"] == [["sop-delay-01", "Actions by delay"]] and s["warnings"]


def test_ungrounded_explanation_fails():
    s = score_case(CASE, result(grounded=False, citations=[]))
    assert s["grounded_ok"] is False and s["passed"] is False


def test_citation_not_in_retrieved_context_fails():
    s = score_case(CASE, result(citations=["sop-fake-99#1"]))
    assert s["citations_valid"] is False and s["passed"] is False


def test_hub_expectation():
    case = {**CASE, "expect_hub": True}
    assert score_case(case, result(lane={"hub_issue_suspected": True}))["hub_ok"] is True
    bad = score_case(case, result(lane={"hub_issue_suspected": False}))
    assert bad["hub_ok"] is False and bad["passed"] is False
    assert score_case(case, result(lane=None))["hub_ok"] is False


def test_degraded_run_fails():
    s = score_case(CASE, result(degraded=["llm-gateway unavailable"]))
    assert s["passed"] is False and s["degraded"] == ["llm-gateway unavailable"]


def test_request_error_is_a_failed_case():
    s = score_case(CASE, None, error="ConnectError")
    assert s["passed"] is False and s["fn"] == 2 and s["status"] is None
    assert any("ConnectError" in f for f in s["failures"])


def test_no_action_case_needs_no_grounding():
    case = {"id": "c5", "shipment_id": "SHP-5", "expect_status": "NO_ACTION_NEEDED", "expect_actions": [],
            "forbid_actions": ["refund"], "expect_roles": {}, "expect_sections": [], "relevant_docs": []}
    r = {"status": "NO_ACTION_NEEDED", "proposed_actions": [], "passages": [], "citations": [],
         "grounded": None, "degraded": [], "trace": [], "llm": None}
    s = score_case(case, r)
    assert s["passed"] is True and s["grounded_ok"] is None and s["section_ok"] is None
    assert s["context_precision"] is None


def test_context_precision_counts_irrelevant_passages():
    r = result(passages=[
        {"chunk_id": "sop-delay-01#3", "doc_id": "sop-delay-01", "section": "Actions by delay"},
        {"chunk_id": "sop-stuck-02#1", "doc_id": "sop-stuck-02", "section": "Scope"},
    ], citations=[])
    assert score_case(CASE, r)["context_precision"] == 0.5


def test_aggregate_metrics():
    good = score_case(CASE, result())
    bad = score_case(CASE, result(proposed_actions=[ESC, REFUND]))
    m = aggregate([good, bad])
    assert m["cases"] == 2 and m["cases_passed"] == 1 and m["forbidden_violations"] == 1
    assert m["action_precision"] == 0.75 and m["action_recall"] == 0.75
    assert m["status_accuracy"] == 1.0 and m["role_accuracy"] == 1.0
    assert m["latency_ms_p50"] == 15.0 and m["avg_cost_usd"] == 0.0002


def test_gates_pass_and_fail():
    assert all(g["passed"] for g in evaluate_gates(aggregate([score_case(CASE, result())])))
    bad = aggregate([score_case(CASE, result(proposed_actions=[ESC, NOTE, REFUND]))])
    failed = {g["metric"] for g in evaluate_gates(bad) if not g["passed"]}
    assert {"forbidden_violations", "action_precision"} <= failed


def test_percentile_nearest_rank():
    assert percentile([], 50) is None
    assert percentile([10, 20, 30, 40], 50) == 20
    assert percentile([10, 20, 30, 40], 95) == 40


def test_golden_file_is_well_formed():
    valid = {"notify_customer", "carrier_escalation", "carrier_trace", "reship", "refund", "damage_claim", "address_update"}
    cases = load_golden()
    assert len(cases) == 11
    assert len({c["id"] for c in cases}) == 11 and len({c["shipment_id"] for c in cases}) == 11
    for c in cases:
        assert set(c["expect_actions"]) <= valid and set(c["forbid_actions"]) <= valid
        assert not set(c["expect_actions"]) & set(c["forbid_actions"])
        assert set(c.get("expect_roles", {})) <= set(c["expect_actions"])
        assert c["expect_status"] in {"PENDING_APPROVAL", "NO_ACTION_NEEDED", "NEEDS_HUMAN", "INSUFFICIENT_CONTEXT"}

def test_slow_triage_fails_latency_gate():
    slow = result(trace=[{"step": "llm_generate", "ms": 3000.0}])
    failed = {g["metric"] for g in evaluate_gates(aggregate([score_case(CASE, slow)])) if not g["passed"]}
    assert failed == {"latency_ms_p95"}

def test_slow_triage_fails_latency_gate():
    slow = result(trace=[{"step": "llm_generate", "ms": 3000.0}])
    failed = {g["metric"] for g in evaluate_gates(aggregate([score_case(CASE, slow)])) if not g["passed"]}
    assert failed == {"latency_ms_p95"}

def test_latency_gate_threshold_can_be_overridden_by_env(monkeypatch):
    monkeypatch.delenv("EVAL_LATENCY_P95_MS", raising=False)
    slow = aggregate([score_case(CASE, result(trace=[{"step": "x", "ms": 400.0}]))])
    assert {g["metric"] for g in evaluate_gates(slow) if not g["passed"]} == {"latency_ms_p95"}
    monkeypatch.setenv("EVAL_LATENCY_P95_MS", "1000")
    gates = evaluate_gates(slow)
    assert all(g["passed"] for g in gates)
    assert next(g for g in gates if g["metric"] == "latency_ms_p95")["rule"] == "<= 1000.0"