from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    action_type: str
    note: str
    fallback: str | None = None


GENERIC_QUERY = "shipment exception triage guidance"
APPROVAL_QUERY = "approval thresholds who can approve refund reship carrier ticket"

# Situation-specific retrieval queries. The band is computed by ops-tools, so the query
# never depends on the model doing date arithmetic.
QUERIES = {
    ("DELAYED", "0-24"): "delay under 24 hours beyond SLA notify customer revised ETA",
    ("DELAYED", "24-48"): "delay 24 to 48 hours beyond SLA carrier escalation ticket proactive delay notice",
    ("DELAYED", "48+"): "delay over 48 hours beyond SLA escalate carrier account manager offer reship",
    ("NO_SCAN", "48-72"): "no scan 48 to 72 hours request trace from carrier notify customer",
    ("NO_SCAN", "72-96"): "no scan 72 to 96 hours lost shipment investigation hold refund",
    ("NO_SCAN", "96+"): "no scan over 96 hours presumed lost reship or refund",
    ("ADDRESS_FAILURE", "ATTEMPT"): "incorrect address verify with customer update address reattempt delivery",
    ("ADDRESS_FAILURE", "RTO_PENDING"): "3 failed delivery attempts return to origin refund after return scan",
    ("ADDRESS_FAILURE", "RETURNED_TO_ORIGIN"): "return to origin refund processed after return to origin scan received",
    ("DAMAGED", "within"): "damaged item customer photos reship refund carrier damage claim",
    ("DAMAGED", "outside"): "damaged item claim must be reported within 7 days of delivery",
}

# Deterministic action plans. Invariant (tested): the planner never proposes an action the
# SOPs forbid, e.g. no refund during an investigation hold or before return-to-origin.
PLANS = {
    ("DELAYED", "0-24"): [Step("notify_customer", "Send the customer a revised ETA")],
    ("DELAYED", "24-48"): [
        Step("carrier_escalation", "Raise a carrier escalation ticket"),
        Step("notify_customer", "Send a proactive delay notice"),
    ],
    ("DELAYED", "48+"): [
        Step("carrier_escalation", "Escalate to the carrier account manager"),
        Step("reship", "Offer a reship if inventory is available"),
        Step("notify_customer", "Send a delay notice with the new ETA"),
    ],
    ("NO_SCAN", "48-72"): [
        Step("carrier_trace", "Request a trace from the carrier"),
        Step("notify_customer", "Notify the customer"),
    ],
    ("NO_SCAN", "72-96"): [
        Step("carrier_escalation", "Open a lost-shipment investigation; hold any refund"),
    ],
    ("NO_SCAN", "96+"): [
        Step("reship", "Shipment presumed lost: reship", fallback="refund"),
        Step("notify_customer", "Tell the customer the shipment is presumed lost"),
    ],
    ("ADDRESS_FAILURE", "ATTEMPT"): [
        Step("notify_customer", "Contact the customer to verify the address; propose an address update once confirmed"),
    ],
    ("ADDRESS_FAILURE", "RTO_PENDING"): [
        Step("notify_customer", "Inform the customer; refund only after the return-to-origin scan"),
    ],
    ("ADDRESS_FAILURE", "RETURNED_TO_ORIGIN"): [
        Step("refund", "Return-to-origin scan received: refund"),
        Step("notify_customer", "Confirm the refund to the customer"),
    ],
    ("DAMAGED", "within"): [
        Step("reship", "Reship the damaged item", fallback="refund"),
        Step("damage_claim", "File a carrier damage claim with the customer photos"),
    ],
    ("DAMAGED", "outside"): [],
}


def key_for(a: dict) -> tuple:
    et, band = a["exception_type"], a.get("band")
    if et == "DAMAGED":
        return (et, "within" if a.get("within_claim_window") else "outside")
    if et == "ADDRESS_FAILURE" and band and band.startswith("ATTEMPT_"):
        return (et, "ATTEMPT")
    return (et, band)


def query_for(a: dict) -> str:
    return QUERIES.get(key_for(a), GENERIC_QUERY)


def plan_for(a: dict) -> list[Step]:
    return list(PLANS.get(key_for(a), []))