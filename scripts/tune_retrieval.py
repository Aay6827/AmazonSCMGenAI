import importlib.util
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bm25 = load("rt_bm25", ROOT / "services" / "retrieval-service" / "app" / "bm25.py")
chunker = load("rt_chunker", ROOT / "services" / "ingest-service" / "app" / "chunker.py")

CHUNKS = []
for f in sorted((ROOT / "data" / "sops").glob("*.md")):
    _, cs = chunker.chunk_document(f.stem, f.read_text(encoding="utf-8-sig"))
    CHUNKS.extend(cs)
BY_ID = {c.chunk_id: c for c in CHUNKS}


def read_golden(name):
    path = ROOT / "data" / "golden" / name
    return [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]


DEV = read_golden("retrieval.jsonl")
HOLD = read_golden("retrieval_holdout.jsonl")

ORIG_TOKENIZE = bm25.tokenize
ALIASES = {"rupees": "inr", "rupee": "inr", "rs": "inr"}


def alias_tokenize(text):
    return [ALIASES.get(t, t) for t in ORIG_TOKENIZE(text)]


def evaluate(rows, idx):
    ranks = []
    for row in rows:
        hits = idx.search(row["query"], 10)
        rank = None
        for i, (cid, _) in enumerate(hits):
            c = BY_ID[cid]
            if c.doc_id == row["doc_id"] and c.section == row["section"]:
                rank = i + 1
                break
        ranks.append(rank)
    n = len(ranks)
    r1 = sum(1 for r in ranks if r == 1) / n
    r3 = sum(1 for r in ranks if r and r <= 3) / n
    mrr = sum(1 / r for r in ranks if r) / n
    return r1, r3, mrr


def run(b, boost, expand):
    bm25.tokenize = alias_tokenize if expand else ORIG_TOKENIZE
    idx = bm25.BM25Index(k1=1.5, b=b)
    idx.build([(c.chunk_id, f"{c.title} {(c.section + ' ') * boost} {c.text}") for c in CHUNKS])
    return evaluate(DEV, idx), evaluate(HOLD, idx)


results = []
for b, boost, expand in itertools.product([0.75, 0.5, 0.3], [1, 2, 3], [False, True]):
    dev, hold = run(b, boost, expand)
    results.append((b, boost, expand, dev, hold, (dev[2] + hold[2]) / 2))

results.sort(key=lambda r: -r[5])
header = f"{'b':<6}{'boost':<7}{'alias':<7}{'dev R@1':<9}{'dev R@3':<9}{'dev MRR':<9}{'hold R@1':<10}{'hold R@3':<10}{'hold MRR':<10}{'avg MRR'}"
print(header)
for b, boost, expand, dev, hold, avg in results[:8]:
    print(f"{b:<6}{boost:<7}{str(expand):<7}{dev[0]:<9.2f}{dev[1]:<9.2f}{dev[2]:<9.2f}{hold[0]:<10.2f}{hold[1]:<10.2f}{hold[2]:<10.2f}{avg:.2f}")

print("\nbaseline (b=0.75, boost=1, alias=False):")
for b, boost, expand, dev, hold, avg in results:
    if (b, boost, expand) == (0.75, 1, False):
        print(f"{b:<6}{boost:<7}{str(expand):<7}{dev[0]:<9.2f}{dev[1]:<9.2f}{dev[2]:<9.2f}{hold[0]:<10.2f}{hold[1]:<10.2f}{hold[2]:<10.2f}{avg:.2f}")
print(f"\nchunks={len(CHUNKS)}  dev n={len(DEV)}  holdout n={len(HOLD)}")