import pytest
from fastapi.testclient import TestClient

from app.main import app, store

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh():
    store.reset()


def propose(sid, action, **kw):
    return client.post("/v1/actions", json={"shipment_id": sid, "action_type": action,
                                            "proposed_by": "agent-service", **kw})


def approve(aid, role, who="ops.alice"):
    return client.post(f"/v1/actions/{aid}/approve", json={"approver": who, "role": role})


def execute(aid):
    return client.post(f"/v1/actions/{aid}/execute", json={"executed_by": "ops.alice"})


def test_health_and_listing():
    assert client.get("/health").json()["status"] == "ok"
    items = client.get("/v1/shipments").json()["shipments"]
    assert len(items) == 11
    assert {i["exception_type"] for i in items} == {"DELAYED", "NO_SCAN", "ADDRESS_FAILURE", "DAMAGED", "NONE"}


def test_get_shipment_masks_pii():
    body = client.get("/v1/shipments/SHP-1001").json()
    assert body["order"]["customer_email_masked"] == "c***@example.com"
    assert "customer1001@example.com" not in str(body)
    assert body["assessment"]["band"] == "24-48"


def test_unknown_resources_404():
    assert client.get("/v1/shipments/NOPE").status_code == 404
    assert client.get("/v1/inventory/nope").status_code == 404
    assert client.get("/v1/actions/ACT-9999").status_code == 404
    assert client.get("/v1/carriers/Nobody/sla", params={"lane_type": "metro"}).status_code == 404


def test_sla_inventory_and_lane_endpoints():
    assert client.get("/v1/carriers/SwiftPost/sla", params={"lane_type": "metro"}).json()["sla_hours"] == 48
    assert client.get("/v1/carriers/SwiftPost/sla", params={"lane_type": "bad"}).status_code == 422
    assert client.get("/v1/inventory/sku-A").json()["units"] == 5
    lane = client.get("/v1/lane-status", params={"origin": "Chennai", "destination": "Madurai"}).json()
    assert lane["hub_issue_suspected"] is True


def test_full_lifecycle_reship_decrements_inventory():
    r = propose("SHP-1007", "reship")
    assert r.status_code == 201 and r.json()["required_role"] == "TEAM_LEAD" and r.json()["amount_inr"] == 3500
    aid = r.json()["action_id"]
    assert approve(aid, "L1").status_code == 403
    assert approve(aid, "TEAM_LEAD").status_code == 200
    done = execute(aid).json()
    assert done["status"] == "EXECUTED" and done["result"]["reship_ref"] == "RSH-SHP-1007"
    assert client.get("/v1/inventory/sku-A").json()["units"] == 4


def test_execute_requires_approval_and_runs_once():
    aid = propose("SHP-1001", "carrier_escalation").json()["action_id"]
    assert execute(aid).status_code == 409
    assert approve(aid, "L1").status_code == 200
    assert execute(aid).status_code == 200
    assert execute(aid).status_code == 409


def test_four_eyes_rule():
    aid = propose("SHP-1001", "notify_customer").json()["action_id"]
    r = approve(aid, "MANAGER", who="agent-service")
    assert r.status_code == 403 and "four-eyes" in r.json()["detail"]


def test_reject_blocks_execution():
    aid = propose("SHP-1001", "notify_customer").json()["action_id"]
    assert client.post(f"/v1/actions/{aid}/reject", json={"approver": "ops.bob", "role": "L1"}).status_code == 200
    assert execute(aid).status_code == 409


def test_refund_manager_threshold_and_execution():
    r = propose("SHP-1009", "refund")
    assert r.json()["required_role"] == "MANAGER"
    aid = r.json()["action_id"]
    assert approve(aid, "TEAM_LEAD").status_code == 403
    assert approve(aid, "MANAGER").status_code == 200
    assert execute(aid).json()["result"]["refunded_inr"] == 15000
    assert client.get("/v1/shipments/SHP-1009").json()["shipment"]["refunded_inr"] == 15000


def test_refund_blocked_during_investigation_hold():
    r = propose("SHP-1002", "refund")
    assert r.status_code == 409 and "investigation hold" in r.json()["detail"]


def test_refund_allowed_when_presumed_lost():
    assert propose("SHP-1007", "refund").status_code == 201


def test_refund_blocked_before_return_to_origin():
    assert propose("SHP-1003", "refund").status_code == 409
    assert propose("SHP-1010", "refund").status_code == 409


def test_refund_after_rto_and_no_double_refund():
    r = propose("SHP-1011", "refund")
    assert r.status_code == 201 and r.json()["required_role"] == "TEAM_LEAD"
    aid = r.json()["action_id"]
    approve(aid, "TEAM_LEAD")
    assert execute(aid).status_code == 200
    again = propose("SHP-1011", "refund")
    assert again.status_code == 409 and "already been refunded" in again.json()["detail"]


def test_refund_amount_cannot_exceed_order_value():
    assert propose("SHP-1007", "refund", amount_inr=99999).status_code == 409


def test_reship_blocked_when_out_of_stock():
    r = propose("SHP-1002", "reship")
    assert r.status_code == 409 and "no inventory" in r.json()["detail"]


def test_damage_claim_rules():
    r = propose("SHP-1004", "damage_claim")
    assert r.status_code == 201 and r.json()["required_role"] == "TEAM_LEAD"
    assert propose("SHP-1005", "damage_claim").status_code == 409


def test_address_update_flow_and_second_update_blocked():
    aid = propose("SHP-1003", "address_update").json()["action_id"]
    approve(aid, "L1")
    assert execute(aid).status_code == 200
    ship = client.get("/v1/shipments/SHP-1003").json()["shipment"]
    assert ship["status"] == "IN_TRANSIT" and ship["address_updates"] == 1
    assert propose("SHP-1003", "address_update").status_code == 409


def test_validation_errors():
    assert propose("SHP-1001", "launch_rocket").status_code == 422
    assert propose("SHP-1001", "refund", amount_inr=0).status_code == 422
    aid = propose("SHP-1001", "notify_customer").json()["action_id"]
    assert client.post(f"/v1/actions/{aid}/approve", json={"approver": "x", "role": "CEO"}).status_code == 422


def test_metrics_exposed():
    client.get("/v1/shipments/SHP-1001")
    text = client.get("/metrics").text
    assert "ops_tool_calls_total" in text and "ops_actions_total" in text

def test_admin_reset_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_TEST_ENDPOINTS", raising=False)
    assert client.post("/v1/admin/reset").status_code == 404


def test_admin_reset_restores_seed_state(monkeypatch):
    monkeypatch.setenv("ENABLE_TEST_ENDPOINTS", "1")
    aid = propose("SHP-1007", "reship").json()["action_id"]
    approve(aid, "TEAM_LEAD")
    execute(aid)
    assert client.get("/v1/inventory/sku-A").json()["units"] == 4
    assert client.post("/v1/admin/reset").json() == {"reset": True}
    assert client.get("/v1/inventory/sku-A").json()["units"] == 5
    assert client.get("/v1/actions").json()["actions"] == []