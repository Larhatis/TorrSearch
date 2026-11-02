from torsearch.claude.limits import HourlyLimit


def test_hourly_limit():
    now = [0.0]
    limit = HourlyLimit(2, clock=lambda: now[0])
    assert limit.allow() and limit.allow()
    assert not limit.allow()
    now[0] = 3601
    assert limit.allow()
