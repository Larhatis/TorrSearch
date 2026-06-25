from torsearch.web.auth import LoginThrottle


def test_not_blocked_initially():
    t = LoginThrottle(max_attempts=3, window_seconds=100, clock=lambda: 0.0)
    assert t.is_blocked("ip") is False


def test_blocks_after_max_failures():
    now = [0.0]
    t = LoginThrottle(max_attempts=3, window_seconds=100, clock=lambda: now[0])
    for _ in range(3):
        t.record_failure("ip")
    assert t.is_blocked("ip") is True
    assert t.is_blocked("other") is False  # per-key


def test_reset_clears_failures():
    t = LoginThrottle(max_attempts=2, window_seconds=100, clock=lambda: 0.0)
    t.record_failure("ip")
    t.record_failure("ip")
    assert t.is_blocked("ip") is True
    t.reset("ip")
    assert t.is_blocked("ip") is False


def test_old_failures_fall_out_of_window():
    now = [0.0]
    t = LoginThrottle(max_attempts=2, window_seconds=100, clock=lambda: now[0])
    t.record_failure("ip")
    t.record_failure("ip")
    assert t.is_blocked("ip") is True
    now[0] = 101  # past the window
    assert t.is_blocked("ip") is False
