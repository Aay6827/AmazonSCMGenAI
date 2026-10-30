import os
from datetime import datetime

SLA_HOURS = {
    "ExpressOne": {"metro": 24, "non_metro": 48, "remote": 72},
    "RoadRunner Logistics": {"metro": 36, "non_metro": 60, "remote": 96},
    "SwiftPost": {"metro": 48, "non_metro": 72, "remote": 120},
}
CLAIM_WINDOW_HOURS = 168  # 7 days (sop-damaged-04)
ROLE_RANK = {"L1": 1, "TEAM_LEAD": 2, "MANAGER": 3}  # SOP "supervisor" maps to TEAM_LEAD
MONETARY = {"refund", "reship", "damage_claim"}


def get_now() -> datetime:
    return datetime.fromisoformat(os.getenv("NOW_OVERRIDE", "2026-10-30T12:00:00+00:00"))


def hours_between(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 3600, 1)


def assess(s: dict, now: datetime) -> dict:
    """Deterministic exception classification following sop-delay-01, sop-stuck-02, sop-address-03, sop-damaged-04."""
    sla = SLA_HOURS[s["carrier"]][s["lane_type"]]
    since_scan = hours_between(s["last_scan_at"], now)
    in_transit = hours_between(s["picked_up_at"], now)
    past_sla = max(0.0, round(in_transit - sla, 1))
    base = {
        "shipment_id": s["shipment_id"],
        "carrier": s["carrier"],
        "lane_type": s["lane_type"],
        "sla_hours": sla,
        "hours_in_transit": in_transit,
        "hours_since_last_scan": since_scan,
        "hours_past_sla": past_sla,
        "band": None,
    }
    if s["status"] == "DELIVERED":
        if s["damage_reported"]:
            since_delivery = hours_between(s["delivered_at"], now)
            return {**base, "exception_type": "DAMAGED", "hours_since_delivery": since_delivery,
                    "within_claim_window": since_delivery <= CLAIM_WINDOW_HOURS}
        return {**base, "exception_type": "NONE"}
    if s["status"] == "RETURNED_TO_ORIGIN":
        return {**base, "exception_type": "ADDRESS_FAILURE", "band": "RETURNED_TO_ORIGIN"}
    if s["status"] == "DELIVERY_FAILED":
        band = "RTO_PENDING" if s["delivery_attempts"] >= 3 else f"ATTEMPT_{s['delivery_attempts']}"
        return {**base, "exception_type": "ADDRESS_FAILURE", "band": band}
    if since_scan >= 48:
        band = "48-72" if since_scan < 72 else "72-96" if since_scan < 96 else "96+"
        return {**base, "exception_type": "NO_SCAN", "band": band}
    if past_sla > 0:
        band = "0-24" if past_sla < 24 else "24-48" if past_sla <= 48 else "48+"
        return {**base, "exception_type": "DELAYED", "band": band}
    return {**base, "exception_type": "NONE"}


def lane_status(shipments, origin: str, destination: str, now: datetime) -> dict:
    on_lane = [s for s in shipments if s["origin"] == origin and s["destination"] == destination
               and s["status"] == "IN_TRANSIT"]
    silent = [s["shipment_id"] for s in on_lane if hours_between(s["last_scan_at"], now) >= 48]
    return {
        "origin": origin,
        "destination": destination,
        "in_transit": len(on_lane),
        "silent_48h_plus": silent,
        "hub_issue_suspected": len(silent) >= 3,
    }


def required_role(action_type: str, amount_inr: int | None, address_updates: int = 0) -> str:
    """Approval levels from sop-approval-05 and the SOP-specific rules."""
    a = amount_inr or 0
    if action_type == "refund":
        return "L1" if a <= 2000 else "TEAM_LEAD" if a <= 10000 else "MANAGER"
    if action_type == "reship":
        return "L1" if a <= 3000 else "TEAM_LEAD"
    if action_type == "damage_claim":
        return "TEAM_LEAD" if a > 5000 else "L1"
    if action_type == "address_update":
        return "L1" if address_updates == 0 else "TEAM_LEAD"
    return "L1"


def check_preconditions(action_type, s, assessment, units, amount, order_value) -> str | None:
    """Return a reason string if the action must be refused, else None."""
    et, band = assessment["exception_type"], assessment["band"]
    if action_type == "refund":
        if s["refunded_inr"] > 0:
            return "Refund blocked: this shipment has already been refunded."
        if amount is None or amount > order_value:
            return "Refund blocked: amount must be set and cannot exceed the order value."
        if et == "ADDRESS_FAILURE" and band != "RETURNED_TO_ORIGIN":
            return "Refund blocked: for delivery failures, refund is processed only after the return-to-origin scan (sop-address-03)."
        if et == "NO_SCAN" and band == "72-96":
            return "Refund blocked: shipment is under a lost-shipment investigation hold (sop-stuck-02)."
    elif action_type == "reship":
        if units <= 0:
            return "Reship blocked: no inventory available for this SKU."
    elif action_type == "damage_claim":
        if et != "DAMAGED":
            return "Damage claim blocked: no damage was reported on this shipment."
        if not assessment.get("within_claim_window"):
            return "Damage claim blocked: reported outside the 7-day claim window (sop-damaged-04)."
    elif action_type == "address_update":
        if s["status"] != "DELIVERY_FAILED":
            return "Address update blocked: shipment is not in a delivery-failed state."
    return None