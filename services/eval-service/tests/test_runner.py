import pytest

from app import runner

NO_ACTION = {"status": "NO_ACTION_NEEDED", "proposed_actions": [], "passages": [], "citations": [],
             "grounded": None, "degraded": [], "trace": [], "llm": None}


class R:
    def __init__(self, status=200, body=None):
        self.status_code, self._body, self.text = status, body or {}, "err"

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def urls(monkeypatch):
    monkeypatch.setenv("OPS_URL", "http://ops:1")
    monkeypatch.setenv("LLM_URL", "http://llm:2")
    monkeypatch.setenv("AGENT_URL", "http://agent:3")


def test_run_resets_ops_and_llm_then_triages(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw.get("json")))
        return R(200, NO_ACTION if url.endswith("/v1/triage") else {"reset": True})

    monkeypatch.setattr(runner.CLIENT, "post", fake_post)
    scores = runner.execute_run(True, ["e05"])
    assert [u for u, _ in calls] == ["http://ops:1/v1/admin/reset", "http://llm:2/v1/admin/reset", "http://agent:3/v1/triage"]
    assert calls[2][1] == {"shipment_id": "SHP-1005", "requested_by": "eval-service"}
    assert scores[0]["passed"] is True


def test_reset_false_skips_the_resets(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        return R(200, NO_ACTION)

    monkeypatch.setattr(runner.CLIENT, "post", fake_post)
    runner.execute_run(False, ["e05"])
    assert calls == ["http://agent:3/v1/triage"]


def test_refused_reset_names_the_service(monkeypatch):
    monkeypatch.setattr(runner.CLIENT, "post", lambda url, **kw: R(404) if "llm" in url else R(200, {}))
    with pytest.raises(runner.ResetUnavailable) as exc:
        runner.execute_run(True, ["e05"])
    assert "llm-gateway" in str(exc.value) and "ENABLE_TEST_ENDPOINTS" in str(exc.value)


def test_triage_http_error_becomes_a_failed_case(monkeypatch):
    monkeypatch.setattr(runner.CLIENT, "post", lambda url, **kw: R(502) if url.endswith("/v1/triage") else R(200, {}))
    s = runner.execute_run(False, ["e05"])[0]
    assert s["passed"] is False and any("HTTP 502" in f for f in s["failures"])