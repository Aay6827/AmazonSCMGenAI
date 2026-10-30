from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from app.logic import (MONETARY, ROLE_RANK, SLA_HOURS, assess, check_preconditions, get_now,
                       lane_status, required_role)
from app.models import ActionCreate, ApproveRequest, ExecuteRequest
from app.store import Store

app = FastAPI(title="ops-tools-service", version="0.1.0")
store = Store()

TOOL_CALLS = Counter("ops_tool_calls_total", "Read tool calls", ["tool"])
ACTIONS = Counter("ops_actions_total", "Action lifecycle events", ["action_type", "outcome"])


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _view(s: dict) -> dict:
    return {k: _iso(v) for k, v in s.items()}


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def _ship(sid: str) -> dict:
    s = store.shipments.get(sid)
    if not s:
        raise HTTPException(404, f"shipment {sid} not found")
    return s


def _act(aid: str) -> dict:
    a = store.actions.get(aid)
    if not a:
        raise HTTPException(404, f"action {aid} not found")
    return a


@app.get("/health")
def health():
    return {"status": "ok", "service": "ops-tools-service", "now": get_now().isoformat()}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/shipments")
def list_shipments():
    TOOL_CALLS.labels("list_shipments").inc()
    now = get_now()
    return {"shipments": [
        {"shipment_id": s["shipment_id"], "carrier": s["carrier"], "status": s["status"],
         "exception_type": assess(s, now)["exception_type"]}
        for s in store.shipments.values()
    ]}


@app.get("/v1/shipments/{sid}")
def get_shipment(sid: str):
    TOOL_CALLS.labels("get_shipment").inc()
    s = _ship(sid)
    o = store.orders[s["order_id"]]
    return {
        "shipment": _view(s),
        "order": {"order_id": o["order_id"], "sku": o["sku"], "value_inr": o["value_inr"],
                  "customer_email_masked": _mask(o["customer_email"])},
        "assessment": assess(s, get_now()),
    }


@app.get("/v1/shipments/{sid}/assessment")
def get_assessment(sid: str):
    TOOL_CALLS.labels("get_assessment").inc()
    return assess(_ship(sid), get_now())


@app.get("/v1/lane-status")
def get_lane_status(origin: str = Query(min_length=1), destination: str = Query(min_length=1)):
    TOOL_CALLS.labels("lane_status").inc()
    return lane_status(store.shipments.values(), origin, destination, get_now())


@app.get("/v1/inventory/{sku}")
def get_inventory(sku: str):
    TOOL_CALLS.labels("get_inventory").inc()
    if sku not in store.inventory:
        raise HTTPException(404, f"sku {sku} not found")
    return {"sku": sku, "units": store.inventory[sku]}


@app.get("/v1/carriers/{carrier}/sla")
def get_sla(carrier: str, lane_type: str = Query(pattern="^(metro|non_metro|remote)$")):
    TOOL_CALLS.labels("get_sla").inc()
    if carrier not in SLA_HOURS:
        raise HTTPException(404, f"carrier {carrier} not found")
    return {"carrier": carrier, "lane_type": lane_type, "sla_hours": SLA_HOURS[carrier][lane_type]}


@app.post("/v1/actions", status_code=201)
def create_action(req: ActionCreate):
    with store.lock:
        s = _ship(req.shipment_id)
        o = store.orders[s["order_id"]]
        amount = None
        if req.action_type in MONETARY:
            amount = req.amount_inr if req.amount_inr is not None else o["value_inr"]
        err = check_preconditions(req.action_type, s, assess(s, get_now()),
                                  store.inventory.get(o["sku"], 0), amount, o["value_inr"])
        if err:
            ACTIONS.labels(req.action_type, "refused").inc()
            raise HTTPException(409, err)
        action = {
            "action_id": store.next_action_id(), "shipment_id": s["shipment_id"],
            "action_type": req.action_type, "amount_inr": amount, "note": req.note,
            "proposed_by": req.proposed_by, "status": "PENDING_APPROVAL",
            "required_role": required_role(req.action_type, amount, s["address_updates"]),
            "approved_by": None, "approver_role": None, "executed_by": None, "result": None,
            "created_at": get_now().isoformat(),
        }
        store.actions[action["action_id"]] = action
        ACTIONS.labels(req.action_type, "proposed").inc()
        return action


@app.get("/v1/actions")
def list_actions():
    return {"actions": list(store.actions.values())}


@app.get("/v1/actions/{aid}")
def get_action(aid: str):
    return _act(aid)


@app.post("/v1/actions/{aid}/approve")
def approve_action(aid: str, req: ApproveRequest):
    with store.lock:
        a = _act(aid)
        if a["status"] != "PENDING_APPROVAL":
            raise HTTPException(409, f"action is {a['status']}, not pending approval")
        if req.approver == a["proposed_by"]:
            raise HTTPException(403, "approver must differ from the proposer (four-eyes rule)")
        if ROLE_RANK[req.role] < ROLE_RANK[a["required_role"]]:
            ACTIONS.labels(a["action_type"], "approval_denied").inc()
            raise HTTPException(403, f"role {req.role} is insufficient; {a['required_role']} or higher required")
        a.update(status="APPROVED", approved_by=req.approver, approver_role=req.role)
        ACTIONS.labels(a["action_type"], "approved").inc()
        return a


@app.post("/v1/actions/{aid}/reject")
def reject_action(aid: str, req: ApproveRequest):
    with store.lock:
        a = _act(aid)
        if a["status"] != "PENDING_APPROVAL":
            raise HTTPException(409, f"action is {a['status']}, not pending approval")
        a.update(status="REJECTED", approved_by=req.approver, approver_role=req.role)
        ACTIONS.labels(a["action_type"], "rejected").inc()
        return a


@app.post("/v1/actions/{aid}/execute")
def execute_action(aid: str, req: ExecuteRequest):
    with store.lock:
        a = _act(aid)
        if a["status"] != "APPROVED":
            raise HTTPException(409, f"action is {a['status']}; only APPROVED actions can execute")
        s = _ship(a["shipment_id"])
        o = store.orders[s["order_id"]]
        err = check_preconditions(a["action_type"], s, assess(s, get_now()),
                                  store.inventory.get(o["sku"], 0), a["amount_inr"], o["value_inr"])
        if err:
            raise HTTPException(409, f"state changed since approval: {err}")
        t = a["action_type"]
        result = {"executed": t}
        if t == "reship":
            store.inventory[o["sku"]] -= 1
            result["reship_ref"] = f"RSH-{s['shipment_id']}"
        elif t == "refund":
            s["refunded_inr"] = a["amount_inr"]
            result["refunded_inr"] = a["amount_inr"]
        elif t == "address_update":
            s["address_updates"] += 1
            s["status"] = "IN_TRANSIT"
            s["failure_reason"] = None
            s["last_scan_at"] = get_now()
        s["log"].append(f"{t} executed ({a['action_id']}) by {req.executed_by}")
        a.update(status="EXECUTED", executed_by=req.executed_by, result=result)
        ACTIONS.labels(t, "executed").inc()
        return a