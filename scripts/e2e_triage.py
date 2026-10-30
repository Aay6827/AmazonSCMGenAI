import sys

import httpx

AGENT = "http://localhost:40004"
OPS = "http://localhost:40003"

# shipment -> (status, expected action types, expected source doc, hub issue expected)
EXPECT = {
    "SHP-1001": ("PENDING_APPROVAL", {"carrier_escalation", "notify_customer"}, "sop-delay-01", None),
    "SHP-1002": ("PENDING_APPROVAL", {"carrier_escalation"}, "sop-stuck-02", False),
    "SHP-1003": ("PENDING_APPROVAL", {"notify_customer"}, "sop-address-03", None),
    "SHP-1004": ("PENDING_APPROVAL", {"reship", "damage_claim"}, "sop-damaged-04", None),
    "SHP-1005": ("NO_ACTION_NEEDED", set(), None, None),
    "SHP-1006": ("PENDING_APPROVAL", {"notify_customer"}, "sop-delay-01", None),
    "SHP-1007": ("PENDING_APPROVAL", {"reship", "notify_customer"}, "sop-stuck-02", True),
    "SHP-1008": ("PENDING_APPROVAL", {"carrier_trace", "notify_customer"}, "sop-stuck-02", True),
    "SHP-1009": ("PENDING_APPROVAL", {"carrier_trace", "notify_customer"}, "sop-stuck-02", True),
    "SHP-1010": ("PENDING_APPROVAL", {"notify_customer"}, "sop-address-03", None),
    "SHP-1011": ("PENDING_APPROVAL", {"refund", "notify_customer"}, "sop-address-03", None),
}

try:
    httpx.get(f"{AGENT}/health", timeout=5).raise_for_status()
except Exception:
    print("agent-service is not reachable on 40004. Run: powershell -ExecutionPolicy Bypass -File scripts\\dev_up.ps1")
    sys.exit(2)

passed = failed = 0
results = {}


def check(name, ok, detail=""):
    global passed, failed
    passed += ok
    failed += (not ok)
    if not ok:
        print(f"    FAIL {name} {detail}")


print(f"{'shipment':<10}{'exception':<18}{'band':<20}{'status':<18}{'grounded':<10}actions")
for sid, (status, actions, doc, hub) in EXPECT.items():
    d = httpx.post(f"{AGENT}/v1/triage", json={"shipment_id": sid}, timeout=30).json()
    results[sid] = d
    a = d["assessment"]
    got = {x["action_type"] for x in d["proposed_actions"]}
    print(f"{sid:<10}{a['exception_type']:<18}{str(a.get('band')):<20}{d['status']:<18}{str(d['grounded']):<10}{sorted(got)}")
    check(f"{sid} status", d["status"] == status, f"got {d['status']}")
    check(f"{sid} actions", got == actions, f"got {sorted(got)} expected {sorted(actions)}")
    if doc:
        docs = [p["doc_id"] for p in d["passages"]]
        check(f"{sid} retrieved {doc}", doc in docs, f"got {docs}")
        check(f"{sid} grounded", d["grounded"] is True, f"degraded={d['degraded']}")
    if hub is not None:
        check(f"{sid} hub flag", d["lane"] and d["lane"]["hub_issue_suspected"] is hub, f"lane={d['lane']}")

print("\nApproval flow on SHP-1007 (reship needs TEAM_LEAD):")
tri = results["SHP-1007"]
aid = next(x["action_id"] for x in tri["proposed_actions"] if x["action_type"] == "reship")
before = httpx.get(f"{OPS}/v1/inventory/sku-A").json()["units"]
base = f"{AGENT}/v1/triage/{tri['triage_id']}/actions/{aid}"
r1 = httpx.post(f"{base}/approve", json={"approver": "ops.alice", "role": "L1"}, timeout=20)
print(f"  L1 approve        -> {r1.status_code} {r1.json().get('detail', '')}")
check("L1 cannot approve reship", r1.status_code == 403)
r2 = httpx.post(f"{base}/approve", json={"approver": "ops.alice", "role": "TEAM_LEAD"}, timeout=20)
print(f"  TEAM_LEAD approve -> {r2.status_code} status={r2.json().get('status')}")
check("TEAM_LEAD approves and executes", r2.status_code == 200 and r2.json().get("status") == "EXECUTED")
after = httpx.get(f"{OPS}/v1/inventory/sku-A").json()["units"]
check("inventory decremented", after == before - 1, f"{before} -> {after}")
r3 = httpx.post(f"{base}/approve", json={"approver": "ops.alice", "role": "TEAM_LEAD"}, timeout=20)
check("cannot execute twice", r3.status_code == 409, f"got {r3.status_code}")

print("\nSample explanation (SHP-1002):")
print(" ", results["SHP-1002"]["summary"])
print(f"\n{passed} checks passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)