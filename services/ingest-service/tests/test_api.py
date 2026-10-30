import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ingest_all_real_documents(monkeypatch):
    captured = {}

    def fake_push(chunks, replace):
        captured["chunks"], captured["replace"] = chunks, replace
        return {"indexed": len(chunks), "total": len(chunks)}

    monkeypatch.setattr("app.main.push_chunks", fake_push)
    r = client.post("/v1/ingest")
    data = r.json()
    assert r.status_code == 200
    assert len(data["documents"]) == 6
    assert "sop-delay-01" in {d["doc_id"] for d in data["documents"]}
    assert data["total_chunks"] == len(captured["chunks"])
    assert captured["replace"] is True
    ids = [c["chunk_id"] for c in captured["chunks"]]
    assert len(ids) == len(set(ids))
    assert all(c["text"].strip() for c in captured["chunks"])


def test_retrieval_down_returns_502(monkeypatch):
    def boom(chunks, replace):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("app.main.push_chunks", boom)
    assert client.post("/v1/ingest").status_code == 502


def test_empty_data_dir_returns_404(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert client.post("/v1/ingest").status_code == 404


def test_ingest_text(monkeypatch):
    monkeypatch.setattr("app.main.push_chunks", lambda chunks, replace: {"indexed": len(chunks), "total": 9})
    r = client.post("/v1/ingest/text", json={"doc_id": "x1", "title": "X", "text": "## A\nSome guidance."})
    assert r.status_code == 200
    assert r.json()["document"]["chunks"] == 1
    assert r.json()["indexed_total"] == 9


def test_health():
    assert client.get("/health").json()["status"] == "ok"