import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.clients import UpstreamError

PASSAGES = [
    {"chunk_id": "sop-x-01#2", "doc_id": "sop-x-01", "title": "Guidance X", "section": "Actions",
     "text": "Do the thing.", "score": 3.0},
    {"chunk_id": "sop-approval-05#2", "doc_id": "sop-approval-05", "title": "Approval", "section": "Refunds",
     "text": "Refund levels.", "score": 2.0},
]


def assess(et, band=None, **kw):
    base = {"shipment_id": "SHP-1", "carrier": "ExpressOne", "lane_type": "metro", "sla_hours": 24,
            "hours_in_transit": 54.0, "hours_since_last_scan": 6.0, "hours_past_sla": 30.0,
            "band": band, "exception_type": et}
    base.update(kw)
    return base


class Fake:
    def __init__(self, assessment, *, lane=None, passages=PASSAGES, llm="cite", refuse=None, deny=False):
        self.assessment = assessment
        self.lane = lane if lane is not None else {"hub_issue_suspected": False, "silent_48h_plus": []}
        self.passages, self.llm, self.refuse, self.deny = passages, llm, refuse or {}, deny
        self.queries, self.created, self.accepted, self.llm_calls, self.calls = [], [], [], [], []

    def get_shipment(self, sid):
        if sid == "MISSING":
            raise UpstreamError("ops-tools", 404, "shipment MISSING not found")
        if sid == "OPSDOWN":
            raise UpstreamError("ops-tools", 502, "ops-tools unreachable: ConnectError")
        return {
            "shipment": {"shipment_id": sid, "carrier": "ExpressOne", "origin": "A", "destination": "B"},
            "order": {"order_id": "ORD-1", "sku": "sku-A", "value_inr": 1200},
            "assessment": dict(self.assessment, shipment_id=sid),
        }

    def lane_status(self, origin, destination):
        self.calls.append(("lane",))
        if self.lane == "down":
            raise UpstreamError("ops-tools", 502, "unreachable")
        return self.lane

    def search(self, query, k=4):
        self.queries.append(query)
        if self.passages == "down":
            raise UpstreamError("retrieval-service", 502, "retrieval-service unreachable")
        return self.passages

    def generate(self, messages, max_tokens=400, tier="small"):
        self.llm_calls.append(messages)
        if self.llm == "down":
            raise UpstreamError("llm-gateway", 502, "llm-gateway unreachable")
        meta = {"provider": "stub", "model": "stub-small", "tokens_in": 10, "tokens_out": 5,
                "cost_usd": 0.0001, "cache_hit": False}
        if self.llm == "blocked":
            return {**meta, "text": "blocked", "blocked": True}
        text = {"hallucinate": "Do X per sop-fake-99#1.", "nocite": "Just do it."}.get(
            self.llm, "Based on sop-x-01#2 and sop-approval-05#2, proceed.")
        return {**meta, "text": text, "blocked": False}

    def create_action(self, payload):
        self.created.append(payload)
        t = payload["action_type"]
        if t in self.refuse:
            raise UpstreamError("ops-tools", 409, self.refuse[t])
        self.accepted.append(t)
        return {"action_id": f"ACT-{len(self.accepted):04d}", "shipment_id": payload["shipment_id"],
                "action_type": t, "status": "PENDING_APPROVAL", "required_role": "L1"}

    def approve(self, aid, approver, role):
        self.calls.append(("approve", aid, approver, role))
        if self.deny:
            raise UpstreamError("ops-tools", 403, "role L1 is insufficient; TEAM_LEAD or higher required")
        return {"action_id": aid, "status": "APPROVED"}

    def reject(self, aid, approver, role):
        self.calls.append(("reject", aid, approver, role))
        return {"action_id": aid, "status": "REJECTED"}

    def execute(self, aid, by):
        self.calls.append(("execute", aid, by))
        return {"action_id": aid, "status": "EXECUTED", "result": {"executed": "x"}}


@pytest.fixture
def run(monkeypatch):
    def _run(fake, sid="SHP-1"):
        monkeypatch.setattr(main, "backends", fake)
        main.RESULTS.clear()
        client = TestClient(main.app)
        return client, client.post("/v1/triage", json={"shipment_id": sid})
    return _run


def test_delayed_24_48_proposes_escalation_and_notice(run):
    f = Fake(assess("DELAYED", "24-48"))
    c, r = run(f)
    d = r.json()
    assert r.status_code == 200 and d["status"] == "PENDING_APPROVAL"
    assert f.accepted == ["carrier_escalation", "notify_customer"]
    assert [x["action_type"] for x in d["proposed_actions"]] == ["carrier_escalation", "notify_customer"]
    assert f.created[0]["proposed_by"] == "agent-service"
    assert d["grounded"] is True and set(d["citations"]) == {"sop-x-01#2", "sop-approval-05#2"}
    assert "24 to 48" in f.queries[0] and len(f.queries) == 2
    assert d["llm"]["provider"] == "stub" and d["degraded"] == []
    assert {t["step"] for t in d["trace"]} >= {"get_shipment", "search", "llm_generate"}


def test_no_scan_72_96_holds_refund_and_surfaces_hub_issue(run):
    f = Fake(assess("NO_SCAN", "72-96"), lane={"hub_issue_suspected": True, "silent_48h_plus": ["a", "b", "c"]})
    c, r = run(f)
    d = r.json()
    assert f.accepted == ["carrier_escalation"]
    assert d["lane"]["hub_issue_suspected"] is True
    assert "hub issue suspected" in f.llm_calls[0][1]["content"].lower()
    assert "72 to 96" in f.queries[0]


def test_presumed_lost_falls_back_from_reship_to_refund(run):
    f = Fake(assess("NO_SCAN", "96+"), refuse={"reship": "Reship blocked: no inventory available for this SKU."})
    c, r = run(f)
    d = r.json()
    assert f.accepted == ["refund", "notify_customer"]
    assert d["blocked_actions"] == [{"action_type": "reship", "reason": "Reship blocked: no inventory available for this SKU."}]
    assert d["status"] == "PENDING_APPROVAL"


def test_both_reship_and_refund_refused_still_notifies(run):
    f = Fake(assess("NO_SCAN", "96+"), refuse={"reship": "no inventory", "refund": "already refunded"})
    c, r = run(f)
    d = r.json()
    assert f.accepted == ["notify_customer"]
    assert [b["action_type"] for b in d["blocked_actions"]] == ["reship", "refund"]


def test_damaged_within_window(run):
    f = Fake(assess("DAMAGED", None, within_claim_window=True))
    c, r = run(f)
    assert f.accepted == ["reship", "damage_claim"]


def test_damaged_outside_window_needs_human(run):
    f = Fake(assess("DAMAGED", None, within_claim_window=False))
    c, r = run(f)
    d = r.json()
    assert d["status"] == "NEEDS_HUMAN" and f.accepted == [] and d["proposed_actions"] == []
    assert len(f.llm_calls) == 1


def test_returned_to_origin_refunds_and_pending_rto_does_not(run):
    f = Fake(assess("ADDRESS_FAILURE", "RETURNED_TO_ORIGIN"))
    run(f)
    assert f.accepted == ["refund", "notify_customer"]
    f2 = Fake(assess("ADDRESS_FAILURE", "RTO_PENDING"))
    run(f2)
    assert f2.accepted == ["notify_customer"]
    f3 = Fake(assess("ADDRESS_FAILURE", "ATTEMPT_2"))
    run(f3)
    assert f3.accepted == ["notify_customer"]


def test_healthy_shipment_needs_no_action_and_no_model_calls(run):
    f = Fake(assess("NONE"))
    c, r = run(f)
    d = r.json()
    assert d["status"] == "NO_ACTION_NEEDED"
    assert f.queries == [] and f.llm_calls == [] and f.created == []


def test_no_passages_means_no_recommendation(run):
    f = Fake(assess("DELAYED", "24-48"), passages=[])
    c, r = run(f)
    d = r.json()
    assert d["status"] == "INSUFFICIENT_CONTEXT"
    assert f.created == [] and f.llm_calls == [] and d["proposed_actions"] == []


def test_retrieval_down_is_insufficient_context_not_an_error(run):
    f = Fake(assess("DELAYED", "24-48"), passages="down")
    c, r = run(f)
    d = r.json()
    assert r.status_code == 200 and d["status"] == "INSUFFICIENT_CONTEXT"
    assert any("retrieval" in x for x in d["degraded"]) and f.created == []


def test_hallucinated_citation_is_discarded(run):
    f = Fake(assess("DELAYED", "24-48"), llm="hallucinate")
    c, r = run(f)
    d = r.json()
    assert d["grounded"] is False and d["citations"] == []
    assert "unverified" in d["summary"].lower() and "sop-fake-99#1" not in d["summary"]
    assert any("sop-fake-99#1" in x for x in d["degraded"])
    assert d["status"] == "PENDING_APPROVAL" and len(d["proposed_actions"]) == 2


def test_missing_citations_are_ungrounded(run):
    f = Fake(assess("DELAYED", "24-48"), llm="nocite")
    c, r = run(f)
    assert r.json()["grounded"] is False


def test_llm_down_degrades_but_still_proposes(run):
    f = Fake(assess("DELAYED", "24-48"), llm="down")
    c, r = run(f)
    d = r.json()
    assert r.status_code == 200 and d["llm"] is None and d["status"] == "PENDING_APPROVAL"
    assert any("llm-gateway" in x for x in d["degraded"]) and "Proposed for approval" in d["summary"]


def test_llm_blocked_by_guardrails_degrades(run):
    f = Fake(assess("DELAYED", "24-48"), llm="blocked")
    c, r = run(f)
    d = r.json()
    assert d["grounded"] is False and any("blocked" in x for x in d["degraded"])


def test_lane_status_failure_is_non_fatal(run):
    f = Fake(assess("NO_SCAN", "48-72"), lane="down")
    c, r = run(f)
    d = r.json()
    assert r.status_code == 200 and d["lane"] is None
    assert any("lane_status" in x for x in d["degraded"])


def test_unknown_shipment_is_404_and_ops_down_is_502(run):
    c, r = run(Fake(assess("NONE")), sid="MISSING")
    assert r.status_code == 404
    c, r = run(Fake(assess("NONE")), sid="OPSDOWN")
    assert r.status_code == 502


def test_approve_executes_and_updates_stored_result(run):
    f = Fake(assess("DELAYED", "0-24"))
    c, r = run(f)
    tid, aid = r.json()["triage_id"], r.json()["proposed_actions"][0]["action_id"]
    a = c.post(f"/v1/triage/{tid}/actions/{aid}/approve", json={"approver": "ops.alice", "role": "L1"})
    assert a.status_code == 200 and a.json()["status"] == "EXECUTED"
    assert ("approve", aid, "ops.alice", "L1") in f.calls and ("execute", aid, "ops.alice") in f.calls
    assert c.get(f"/v1/triage/{tid}").json()["proposed_actions"][0]["status"] == "EXECUTED"


def test_insufficient_role_is_403_and_nothing_executes(run):
    f = Fake(assess("DELAYED", "0-24"), deny=True)
    c, r = run(f)
    tid, aid = r.json()["triage_id"], r.json()["proposed_actions"][0]["action_id"]
    a = c.post(f"/v1/triage/{tid}/actions/{aid}/approve", json={"approver": "ops.alice", "role": "L1"})
    assert a.status_code == 403 and "insufficient" in a.json()["detail"]
    assert not any(call[0] == "execute" for call in f.calls)


def test_reject_flow_and_unknown_ids(run):
    f = Fake(assess("DELAYED", "0-24"))
    c, r = run(f)
    tid, aid = r.json()["triage_id"], r.json()["proposed_actions"][0]["action_id"]
    j = c.post(f"/v1/triage/{tid}/actions/{aid}/reject", json={"approver": "ops.bob", "role": "L1"})
    assert j.status_code == 200 and j.json()["status"] == "REJECTED"
    assert c.post(f"/v1/triage/{tid}/actions/ACT-9999/approve", json={"approver": "x", "role": "L1"}).status_code == 404
    assert c.post("/v1/triage/TRI-nope/actions/ACT-0001/approve", json={"approver": "x", "role": "L1"}).status_code == 404
    assert c.get("/v1/triage/TRI-nope").status_code == 404


def test_validation_health_metrics(run):
    c, _ = run(Fake(assess("NONE")))
    assert c.post("/v1/triage", json={"shipment_id": ""}).status_code == 422
    assert c.post("/v1/triage/t/actions/a/approve", json={"approver": "x", "role": "CEO"}).status_code == 422
    assert c.get("/health").json()["status"] == "ok"
    text = c.get("/metrics").text
    assert "agent_triage_total" in text and "agent_triage_seconds" in text