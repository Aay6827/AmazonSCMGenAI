from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

from app.models import IndexRequest, SearchRequest
from app.store import ChunkStore

app = FastAPI(title="retrieval-service", version="0.1.0")
store = ChunkStore()

SEARCHES = Counter("retrieval_searches_total", "Search requests", ["outcome"])
CHUNKS = Gauge("retrieval_index_chunks", "Chunks currently indexed")


@app.get("/health")
def health():
    return {"status": "ok", "service": "retrieval-service", "chunks": len(store)}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/stats")
def stats():
    return {"chunks": len(store), "docs": store.doc_count()}


@app.post("/v1/index")
def index(req: IndexRequest):
    indexed = store.add(req.chunks, req.replace)
    CHUNKS.set(len(store))
    return {"indexed": indexed, "total": len(store)}


@app.post("/v1/search")
def search(req: SearchRequest):
    hits = store.search(req.query, req.k)
    SEARCHES.labels("hit" if hits else "miss").inc()
    return {"query": req.query, "results": hits}