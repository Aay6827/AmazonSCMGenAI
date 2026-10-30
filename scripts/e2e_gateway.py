import sys
import time

import httpx

GW = "http://127.0.0.1:40006"
OPS = "http://127.0.0.1:40003"
L1 = {"X-API-Key": "dev-l1-key-01"}
LEAD = {"X-API-Key": "dev-lead-key-1"}

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed += bool(ok)
    failed += (not ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   -> {detail}"))


try:
    httpx.get(f"{GW}/health", timeout=5).raise_for_status()
    httpx.post(f"{OPS}/v1/admin/reset", timeout=10).raise_for_status()
except Exception as exc:
    print(f"setup failed ({type(exc).__name__}). Run: powershell -ExecutionPolicy Bypass -File scripts\\dev_up.ps1")
    sys.exit(2)

print("Authentication")
body = {"shipment_id": "SHP-1007"}
check("no key -> 401", httpx.post(f"{GW}/v1/triage", json=body, timeout=10).status_code == 401)
check("wrong key -> 401", httpx.post(f"{GW}/v1/triage", json=body, headers={"X-API-Key": "wrong-key-0000"}, timeout=10).status_code == 401)

print("Triage through the gateway")
t0 = time.perf_counter()
r = httpx.post(f"{GW}/v1/triage", json=body, headers=L1, timeout=30)
ms = round((time.perf_counter() - t0) * 1000)
d = r.json()
check("200 and pending approval", r.status_code == 200 and d.get("status") == "PENDING_APPROVAL", r.text[:200])
check("requester comes from the API key", d.get("requested_by") == "ops.alice", d.get("requested_by"))
check("request id returned", len(r.headers.get("x-request-id", "")) >= 8)
check(f"triage latency under 2000 ms ({ms} ms)", ms < 2000, f"{ms} ms")

aid = next(a["action_id"] for a in d["proposed_actions"] if a["action_type"] == "reship")
base = f"{GW}/v1/triage/{d['triage_id']}/actions/{aid}"

print("Approval roles come from the key")
r = httpx.post(f"{base}/approve", headers=L1, json={"approver": "mgr.carol", "role": "MANAGER"}, timeout=20)
check("L1 key cannot approve a reship even if the body claims MANAGER", r.status_code == 403, f"{r.status_code} {r.text}")
r = httpx.post(f"{base}/approve", headers=LEAD, timeout=20)
check("TEAM_LEAD key approves and executes", r.status_code == 200 and r.json().get("status") == "EXECUTED", f"{r.status_code} {r.text[:200]}")
r = httpx.post(f"{base}/approve", headers=LEAD, timeout=20)
check("second approval is rejected", r.status_code == 409, f"{r.status_code}")

print("Operations")
r = httpx.get(f"{GW}/v1/status", headers=L1, timeout=20)
check("all services up", r.status_code == 200 and r.json().get("status") == "ok", r.text[:200])

print(f"\n{passed} checks passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)