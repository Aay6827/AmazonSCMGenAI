import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.runner import ResetUnavailable
from app.scoring import score_case
from test_scoring import CASE, ESC, NOTE, REFUND, result

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clean():
    main.LATEST.clear()


def good_run(reset=True, case_ids=None):
    return [score_case(CASE, result())]


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "eval-service"}


def test_run_returns_report_and_stores_latest(monkeypatch):
    monkeypatch.setattr(main, "execute_run", good_run)
    r = client.post("/v1/run")
    data = r.json()
    assert r.status_code == 200 and data["passed"] is True
    assert data["metrics"]["cases"] == 1 and len(data["gates"]) == 9 and data["run_id"].startswith("EVAL-")
    assert client.get("/v1/report/latest").json()["run_id"] == data["run_id"]


def test_latest_is_404_before_any_run():
    assert client.get("/v1/report/latest").status_code == 404


def test_reset_unavailable_is_409(monkeypatch):
    def refuse(reset=True, case_ids=None):
        raise ResetUnavailable("start it with ENABLE_TEST_ENDPOINTS=1")

    monkeypatch.setattr(main, "execute_run", refuse)
    r = client.post("/v1/run")
    assert r.status_code == 409 and "ENABLE_TEST_ENDPOINTS" in r.json()["detail"]


def test_empty_selection_is_422(monkeypatch):
    monkeypatch.setattr(main, "execute_run", lambda reset=True, case_ids=None: [])
    assert client.post("/v1/run", json={"case_ids": ["nope"]}).status_code == 422


def test_failing_gate_marks_run_failed_but_returns_200(monkeypatch):
    monkeypatch.setattr(main, "execute_run",
                        lambda reset=True, case_ids=None: [score_case(CASE, result(proposed_actions=[ESC, NOTE, REFUND]))])
    r = client.post("/v1/run")
    assert r.status_code == 200 and r.json()["passed"] is False
    assert r.json()["metrics"]["forbidden_violations"] == 1


def test_run_forwards_options(monkeypatch):
    seen = {}

    def spy(reset=True, case_ids=None):
        seen.update(reset=reset, case_ids=case_ids)
        return [score_case(CASE, result())]

    monkeypatch.setattr(main, "execute_run", spy)
    client.post("/v1/run", json={"reset": False, "case_ids": ["e01"]})
    assert seen == {"reset": False, "case_ids": ["e01"]}


def test_golden_endpoint_lists_cases():
    cases = client.get("/v1/golden").json()["cases"]
    assert len(cases) == 11 and cases[0]["shipment_id"] == "SHP-1001"


def test_metrics_exposed(monkeypatch):
    monkeypatch.setattr(main, "execute_run", good_run)
    client.post("/v1/run")
    text = client.get("/metrics").text
    assert "eval_runs_total" in text and "eval_metric" in text