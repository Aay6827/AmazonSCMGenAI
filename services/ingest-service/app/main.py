import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from pydantic import BaseModel, Field

from app.chunker import chunk_document
from app.client import push_chunks

app = FastAPI(title="ingest-service", version="0.1.0")

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "data" / "sops"
INGESTED = Counter("ingest_chunks_total", "Chunks produced", ["mode"])


class TextDoc(BaseModel):
    doc_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    version: str = "1"
    text: str = Field(min_length=1)


@app.get("/health")
def health():
    return {"status": "ok", "service": "ingest-service"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _push(chunks: list[dict], replace: bool) -> dict:
    try:
        return push_chunks(chunks, replace)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"retrieval-service unavailable: {type(exc).__name__}")


@app.post("/v1/ingest")
def ingest_all():
    data_dir = Path(os.getenv("DATA_DIR", str(DEFAULT_DIR)))
    files = sorted(data_dir.glob("*.md"))
    if not files:
        raise HTTPException(status_code=404, detail="no .md documents found in DATA_DIR")
    docs, all_chunks = [], []
    for f in files:
        meta, chunks = chunk_document(f.stem, f.read_text(encoding="utf-8-sig"))
        docs.append({**meta, "chunks": len(chunks)})
        all_chunks.extend(c.to_dict() for c in chunks)
    result = _push(all_chunks, replace=True)
    INGESTED.labels("batch").inc(len(all_chunks))
    return {"documents": docs, "total_chunks": len(all_chunks), "indexed_total": result.get("total")}


@app.post("/v1/ingest/text")
def ingest_text(doc: TextDoc):
    raw = f"---\nid: {doc.doc_id}\ntitle: {doc.title}\nversion: {doc.version}\n---\n{doc.text}"
    meta, chunks = chunk_document(doc.doc_id, raw)
    result = _push([c.to_dict() for c in chunks], replace=False)
    INGESTED.labels("single").inc(len(chunks))
    return {"document": {**meta, "chunks": len(chunks)}, "indexed_total": result.get("total")}