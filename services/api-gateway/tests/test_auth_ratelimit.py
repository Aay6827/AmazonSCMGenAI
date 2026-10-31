import pytest

from app.auth import Principal, load_keys
from app.ratelimit import TokenBucket


def test_load_keys_parses_entries():
    keys = load_keys("l1-key-0001:ops.alice:L1, lead-key-001:lead.bob:TEAM_LEAD ,")
    assert keys == {"l1-key-0001": Principal("ops.alice", "L1"), "lead-key-001": Principal("lead.bob", "TEAM_LEAD")}
    assert load_keys(None) == {} and load_keys("") == {}


@pytest.mark.parametrize("raw", ["only:two", "tiny:ident:L1", "longenough1:ident:ROOT"])
def test_load_keys_rejects_bad_config_without_echoing_keys(raw):
    with pytest.raises(ValueError) as exc:
        load_keys(raw)
    assert "longenough1" not in str(exc.value) and "tiny" not in str(exc.value)


def test_token_bucket_burst_refill_and_isolation():
    now = [0.0]
    bucket = TokenBucket(2, clock=lambda: now[0])
    assert bucket.allow("a")[0] and bucket.allow("a")[0]
    ok, retry = bucket.allow("a")
    assert ok is False and retry == 30.0
    assert bucket.allow("b")[0] is True
    now[0] = 30.0
    assert bucket.allow("a")[0] is True
    assert bucket.allow("a")[0] is False