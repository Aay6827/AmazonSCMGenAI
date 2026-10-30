import pytest

from app.planner import PLANS, QUERIES, key_for, plan_for, query_for

ALLOWED = {"notify_customer", "carrier_escalation", "carrier_trace", "reship", "refund", "damage_claim", "address_update"}


def a(et, band=None, **kw):
    return {"exception_type": et, "band": band, **kw}


def test_every_query_key_has_a_plan_and_vice_versa():
    assert set(QUERIES) == set(PLANS)


def test_all_plan_actions_are_known_types():
    for steps in PLANS.values():
        for s in steps:
            assert s.action_type in ALLOWED
            assert s.fallback is None or s.fallback in ALLOWED


def test_key_normalisation():
    assert key_for(a("ADDRESS_FAILURE", "ATTEMPT_2")) == ("ADDRESS_FAILURE", "ATTEMPT")
    assert key_for(a("DAMAGED", None, within_claim_window=True)) == ("DAMAGED", "within")
    assert key_for(a("DAMAGED", None, within_claim_window=False)) == ("DAMAGED", "outside")
    assert key_for(a("DELAYED", "24-48")) == ("DELAYED", "24-48")


def test_unknown_situation_gets_generic_query_and_no_plan():
    assert query_for(a("WEIRD", "x")) == "shipment exception triage guidance"
    assert plan_for(a("WEIRD", "x")) == []
    assert plan_for(a("NONE")) == []


@pytest.mark.parametrize("et,band", [
    ("NO_SCAN", "72-96"), ("ADDRESS_FAILURE", "ATTEMPT_1"), ("ADDRESS_FAILURE", "RTO_PENDING"),
    ("DELAYED", "0-24"), ("DELAYED", "24-48"), ("DELAYED", "48+"), ("NO_SCAN", "48-72"),
])
def test_planner_never_proposes_refund_where_sops_forbid_it(et, band):
    assert all(s.action_type != "refund" for s in plan_for(a(et, band)))


def test_refund_is_only_planned_after_rto_or_as_fallback():
    assert [s.action_type for s in plan_for(a("ADDRESS_FAILURE", "RETURNED_TO_ORIGIN"))][0] == "refund"
    for key, steps in PLANS.items():
        for s in steps:
            if s.action_type == "refund":
                assert key == ("ADDRESS_FAILURE", "RETURNED_TO_ORIGIN")


def test_only_reship_has_a_fallback_and_it_is_refund():
    for steps in PLANS.values():
        for s in steps:
            if s.fallback:
                assert s.action_type == "reship" and s.fallback == "refund"


def test_queries_carry_the_band_wording_from_the_sops():
    assert "72 to 96" in query_for(a("NO_SCAN", "72-96"))
    assert "24 to 48" in query_for(a("DELAYED", "24-48"))
    assert "return to origin" in query_for(a("ADDRESS_FAILURE", "RETURNED_TO_ORIGIN"))