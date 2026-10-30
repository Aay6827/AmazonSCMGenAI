import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SAMPLE = [
    {"chunk_id": "d1#1", "doc_id": "d1", "title": "Delayed shipment", "section": "Actions",
     "text": "Escalate to the carrier account manager when the delay exceeds 48 hours."},
    {"chunk_id": "d2#1", "doc_id": "d2", "title": "Address failure", "section": "Steps",
     "text": "Verify the delivery address with the customer and reattempt delivery."},
    {"chunk_id": "d3#1", "doc_id": "d3", "title": "Damaged parcel", "section": "Claims",
     "text": "Collect customer photos and file a carrier damage claim."},
]


@pytest.fixture(autouse=True)
def fresh_index():
    r = client.post("/v1/index", json={"chunks": SAMPLE, "replace": True})
    assert r.status_code == 200


def test_health_and_stats():
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/v1/stats").json() == {"chunks": 3, "docs": 3}


def test_search_returns_best_passage_with_citation():
    r = client.post("/v1/search", json={"query": "customer address wrong, reattempt"})
    top = r.json()["results"][0]
    assert top["chunk_id"] == "d2#1"
    assert top["citation"] == "[SOURCE:d2#1]"
    assert top["score"] > 0


def test_search_damage_claim():
    top = client.post("/v1/search", json={"query": "damage claim photos"}).json()["results"][0]
    assert top["doc_id"] == "d3"


def test_k_limits_results():
    r = client.post("/v1/search", json={"query": "carrier", "k": 1})
    assert len(r.json()["results"]) == 1


def test_no_match_returns_empty():
    r = client.post("/v1/search", json={"query": "zeppelin"})
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_replace_false_adds_to_existing():
    extra = {"chunk_id": "d4#1", "doc_id": "d4", "title": "Policy", "text": "Refund limits apply."}
    r = client.post("/v1/index", json={"chunks": [extra], "replace": False})
    assert r.json()["total"] == 4


def test_validation():
    assert client.post("/v1/search", json={"query": ""}).status_code == 422
    assert client.post("/v1/search", json={"query": "x", "k": 99}).status_code == 422
    assert client.post("/v1/index", json={"chunks": []}).status_code == 422


def test_metrics_exposed():
    client.post("/v1/search", json={"query": "carrier"})
    assert "retrieval_searches_total" in client.get("/metrics").text