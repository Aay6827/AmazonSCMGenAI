import os
import sys
import time

import httpx

GW = "http://127.0.0.1:40006"
OPS = "http://127.0.0.1:40003"
L1 = {"X-API-Key": "dev-l1-key-01"}
LEAD = {"X-API-Key": "dev-lead-key-1"}
C = httpx.Client(timeout=30)  # shared client: a new one per call costs ~220 ms here

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed += bool(ok)
    failed += (not ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   -> {detail}"))


try:
    C.get(f"{GW}/health").raise_for_status()
    None if os.getenv("SKIP_OPS_RESET") == "1" else C.post(f"{OPS}/v1/admin/reset").raise_for_status()
except Exception as exc:
    print(f"setup failed ({type(exc).__name__}). Run: powershell -ExecutionPolicy Bypass -File scripts\\dev_up.ps1")
    sys.exit(2)

print("Authentication")
body = {"shipment_id": "SHP-1007"}
check("no key -> 401", C.post(f"{GW}/v1/triage", json=body).status_code == 401)
check("wrong key -> 401", C.post(f"{GW}/v1/triage", json=body, headers={"X-API-Key": "wrong-key-0000"}).status_code == 401)

print("Triage through the gateway")
t0 = time.perf_counter()
r = C.post(f"{GW}/v1/triage", json=body, headers=L1)
ms = round((time.perf_counter() - t0) * 1000)
d = r.json()
check("200 and pending approval", r.status_code == 200 and d.get("status") == "PENDING_APPROVAL", r.text[:200])
check("requester comes from the API key", d.get("requested_by") == "ops.alice", d.get("requested_by"))
check("request id returned", len(r.headers.get("x-request-id", "")) >= 8)
check(f"triage latency under 500 ms ({ms} ms)", ms < 500, f"{ms} ms")

aid = next(a["action_id"] for a in d["proposed_actions"] if a["action_type"] == "reship")
base = f"{GW}/v1/triage/{d['triage_id']}/actions/{aid}"

print("Approval roles come from the key")
r = C.post(f"{base}/approve", headers=L1, json={"approver": "mgr.carol", "role": "MANAGER"})
check("L1 key cannot approve a reship even if the body claims MANAGER", r.status_code == 403, f"{r.status_code} {r.text}")
r = C.post(f"{base}/approve", headers=LEAD)
check("TEAM_LEAD key approves and executes", r.status_code == 200 and r.json().get("status") == "EXECUTED", f"{r.status_code} {r.text[:200]}")
r = C.post(f"{base}/approve", headers=LEAD)
check("second approval is rejected", r.status_code == 409, f"{r.status_code}")

print("Operations")
r = C.get(f"{GW}/v1/status", headers=L1)
check("all services up", r.status_code == 200 and r.json().get("status") == "ok", r.text[:200])

print(f"\n{passed} checks passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)