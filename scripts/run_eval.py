import json
import sys
from pathlib import Path

import httpx

BASE = "http://localhost:40005"
OUT = Path(__file__).resolve().parents[1] / "docs" / "eval" / "latest.json"

try:
    resp = httpx.post(f"{BASE}/v1/run", json={}, timeout=180)
except httpx.HTTPError as exc:
    print(f"eval-service unreachable on 40005 ({type(exc).__name__}). Run: powershell -ExecutionPolicy Bypass -File scripts\\dev_up.ps1")
    sys.exit(2)
if resp.status_code != 200:
    print(f"eval-service returned {resp.status_code}: {resp.text}")
    sys.exit(2)

rep = resp.json()
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(rep, indent=2), encoding="utf-8")

print(f"{'case':<6}{'shipment':<10}{'status':<18}{'result':<7}{'ms':<9}{'ctx prec'}")
for c in rep["cases"]:
    prec = "-" if c["context_precision"] is None else f"{c['context_precision']:.2f}"
    print(f"{c['id']:<6}{c['shipment_id']:<10}{str(c['status']):<18}{'PASS' if c['passed'] else 'FAIL':<7}{c['latency_ms']:<9}{prec}")
    for f in c["failures"]:
        print(f"      FAIL: {f}")
    for w in c["warnings"]:
        print(f"      warn: {w}")

m = rep["metrics"]
print("\nMetrics")
for k in ("cases", "cases_passed", "status_accuracy", "action_precision", "action_recall", "forbidden_violations",
          "role_accuracy", "section_hit_rate", "grounded_rate", "citation_valid_rate", "degraded_cases",
          "context_precision", "latency_ms_p50", "latency_ms_p95", "avg_cost_usd"):
    print(f"  {k:<22}{m[k]}")

print("\nGates")
for g in rep["gates"]:
    print(f"  {'PASS' if g['passed'] else 'FAIL':<6}{g['metric']:<22}{g['value']}  (need {g['rule']})")

print(f"\nRESULT: {'PASSED' if rep['passed'] else 'FAILED'}  (report saved to docs\\eval\\latest.json)")
sys.exit(0 if rep["passed"] else 1)