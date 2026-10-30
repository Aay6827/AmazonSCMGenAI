import json
import sys
from pathlib import Path

import httpx

BASE = "http://localhost:40001"
GOLDEN = Path(__file__).resolve().parents[1] / "data" / "golden" / "retrieval.jsonl"
DEPTH = 10

rows = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
ranks = []
print(f"{'id':<5}{'rank':<6}{'top result':<40}query")
for row in rows:
    results = httpx.post(f"{BASE}/v1/search", json={"query": row["query"], "k": DEPTH}, timeout=10).json()["results"]
    rank = next(
        (i + 1 for i, p in enumerate(results) if p["doc_id"] == row["doc_id"] and p["section"] == row["section"]),
        None,
    )
    ranks.append(rank)
    top = f'{results[0]["doc_id"]} / {results[0]["section"]}' if results else "-"
    print(f"{row['id']:<5}{str(rank or 'MISS'):<6}{top:<40}{row['query'][:55]}")

n = len(ranks)
def recall(k):
    return sum(1 for r in ranks if r and r <= k) / n

mrr = sum(1 / r for r in ranks if r) / n
print(f"\nrecall@1={recall(1):.2f}  recall@3={recall(3):.2f}  recall@4={recall(4):.2f}  MRR={mrr:.2f}  (n={n})")
sys.exit(0)