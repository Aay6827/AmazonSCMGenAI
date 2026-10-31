import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# measured when tuned: dev MRR 0.88, holdout MRR 1.00, recall@4 1.00 on both
THRESHOLDS = {
    "retrieval.jsonl": {"mrr": 0.85, "recall@4": 1.0},
    "retrieval_holdout.jsonl": {"mrr": 0.95, "recall@4": 1.0},
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bm25 = load("rq_bm25", ROOT / "services" / "retrieval-service" / "app" / "bm25.py")
chunker = load("rq_chunker", ROOT / "services" / "ingest-service" / "app" / "chunker.py")

chunks = []
for f in sorted((ROOT / "data" / "sops").glob("*.md")):
    _, cs = chunker.chunk_document(f.stem, f.read_text(encoding="utf-8-sig"))
    chunks.extend(cs)
by_id = {c.chunk_id: c for c in chunks}

index = bm25.BM25Index()  # production defaults
index.build([(c.chunk_id, f"{c.title} {c.section} {c.text}") for c in chunks])

failed = False
for name, limits in THRESHOLDS.items():
    rows = [json.loads(x) for x in (ROOT / "data" / "golden" / name).read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    ranks = []
    for row in rows:
        rank = None
        for i, (cid, _) in enumerate(index.search(row["query"], 10)):
            c = by_id[cid]
            if c.doc_id == row["doc_id"] and c.section == row["section"]:
                rank = i + 1
                break
        ranks.append(rank)
    n = len(ranks)
    mrr = sum(1 / r for r in ranks if r) / n
    r4 = sum(1 for r in ranks if r and r <= 4) / n
    ok = mrr >= limits["mrr"] and r4 >= limits["recall@4"]
    failed = failed or not ok
    print(f"{name:<26} n={n:<3} MRR={mrr:.2f} (min {limits['mrr']})  recall@4={r4:.2f} (min {limits['recall@4']})  {'PASS' if ok else 'FAIL'}")
    for row, rank in zip(rows, ranks):
        if rank is None or rank > 1:
            print(f"    {row['id']}: rank {rank or 'MISS'} for: {row['query'][:60]}")
sys.exit(1 if failed else 0)