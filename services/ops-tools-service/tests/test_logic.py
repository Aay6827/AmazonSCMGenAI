import pytest

from app.data import seed
from app.logic import assess, get_now, lane_status, required_role

D = seed()
NOW = get_now()


def a(sid):
    return assess(D["shipments"][sid], NOW)


def test_delayed_24_to_48():
    r = a("SHP-1001")
    assert r["exception_type"] == "DELAYED" and r["band"] == "24-48"
    assert (r["sla_hours"], r["hours_in_transit"], r["hours_past_sla"], r["hours_since_last_scan"]) == (24, 54.0, 30.0, 6.0)


def test_delayed_under_24():
    r = a("SHP-1006")
    assert r["exception_type"] == "DELAYED" and r["band"] == "0-24" and r["hours_past_sla"] == 10.0


def test_no_scan_bands():
    assert a("SHP-1002")["band"] == "72-96" and a("SHP-1002")["exception_type"] == "NO_SCAN"
    assert a("SHP-1007")["band"] == "96+"
    assert a("SHP-1008")["band"] == "48-72"
    assert a("SHP-1009")["band"] == "48-72"


def test_no_scan_takes_priority_over_delay():
    assert a("SHP-1002")["hours_past_sla"] > 0
    assert a("SHP-1002")["exception_type"] == "NO_SCAN"


def test_address_failure_states():
    assert a("SHP-1003")["band"] == "ATTEMPT_1"
    assert a("SHP-1010")["band"] == "RTO_PENDING"
    assert a("SHP-1011")["band"] == "RETURNED_TO_ORIGIN"
    assert all(a(s)["exception_type"] == "ADDRESS_FAILURE" for s in ("SHP-1003", "SHP-1010", "SHP-1011"))


def test_damaged_and_healthy():
    r = a("SHP-1004")
    assert r["exception_type"] == "DAMAGED" and r["within_claim_window"] is True
    assert a("SHP-1005")["exception_type"] == "NONE"


def test_lane_hub_detection():
    hub = lane_status(D["shipments"].values(), "Chennai", "Madurai", NOW)
    assert hub["hub_issue_suspected"] is True and len(hub["silent_48h_plus"]) == 3
    single = lane_status(D["shipments"].values(), "Hyderabad", "Nagpur", NOW)
    assert single["hub_issue_suspected"] is False and single["silent_48h_plus"] == ["SHP-1002"]
    ok = lane_status(D["shipments"].values(), "Bengaluru", "Mumbai", NOW)
    assert ok["silent_48h_plus"] == []


@pytest.mark.parametrize("action,amount,updates,expected", [
    ("refund", 2000, 0, "L1"), ("refund", 2001, 0, "TEAM_LEAD"),
    ("refund", 10000, 0, "TEAM_LEAD"), ("refund", 10001, 0, "MANAGER"),
    ("reship", 3000, 0, "L1"), ("reship", 3001, 0, "TEAM_LEAD"),
    ("damage_claim", 5000, 0, "L1"), ("damage_claim", 5001, 0, "TEAM_LEAD"),
    ("address_update", None, 0, "L1"), ("address_update", None, 1, "TEAM_LEAD"),
    ("carrier_escalation", None, 0, "L1"), ("notify_customer", None, 0, "L1"),
])
def test_required_role_thresholds(action, amount, updates, expected):
    assert required_role(action, amount, updates) == expected