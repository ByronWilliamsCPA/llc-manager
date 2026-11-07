"""Tests for the break-glass failure throttle."""

import pytest

from llc_manager.auth.throttle import LoginThrottle

pytestmark = [pytest.mark.unit, pytest.mark.security]


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def throttle(clock: _Clock) -> LoginThrottle:
    return LoginThrottle(max_failures=5, window_seconds=900, clock=clock)


def _fail(throttle: LoginThrottle, key: str, times: int) -> None:
    for _ in range(times):
        throttle.record_failure(key)


def test_blocks_on_the_fifth_failure(throttle: LoginThrottle) -> None:
    _fail(throttle, "1.2.3.4", 4)
    assert not throttle.is_blocked("1.2.3.4")

    throttle.record_failure("1.2.3.4")

    assert throttle.is_blocked("1.2.3.4")


def test_defaults_are_five_failures_per_fifteen_minutes() -> None:
    default = LoginThrottle()

    _fail(default, "k", 4)
    assert not default.is_blocked("k")
    default.record_failure("k")
    assert default.is_blocked("k")
    assert default.retry_after("k") <= 15 * 60 + 1


def test_clients_are_tracked_separately(throttle: LoginThrottle) -> None:
    _fail(throttle, "1.2.3.4", 5)

    assert throttle.is_blocked("1.2.3.4")
    assert not throttle.is_blocked("5.6.7.8")


def test_failures_expire_after_the_window(
    throttle: LoginThrottle, clock: _Clock
) -> None:
    _fail(throttle, "1.2.3.4", 5)
    clock.now += 899
    assert throttle.is_blocked("1.2.3.4")

    clock.now += 2

    assert not throttle.is_blocked("1.2.3.4")


def test_window_slides_rather_than_resetting(
    throttle: LoginThrottle, clock: _Clock
) -> None:
    _fail(throttle, "k", 3)
    clock.now += 600
    _fail(throttle, "k", 2)
    assert throttle.is_blocked("k")

    clock.now += 301  # the first three age out, the last two remain

    assert not throttle.is_blocked("k")
    _fail(throttle, "k", 3)
    assert throttle.is_blocked("k")


def test_reset_forgets_the_client(throttle: LoginThrottle) -> None:
    _fail(throttle, "k", 5)

    throttle.reset("k")

    assert not throttle.is_blocked("k")
    throttle.reset("never-seen")  # must not raise


def test_reset_affects_only_that_client(throttle: LoginThrottle) -> None:
    _fail(throttle, "a", 5)
    _fail(throttle, "b", 5)

    throttle.reset("a")

    assert not throttle.is_blocked("a")
    assert throttle.is_blocked("b")


def test_retry_after_counts_down(throttle: LoginThrottle, clock: _Clock) -> None:
    assert throttle.retry_after("k") == 0
    _fail(throttle, "k", 5)
    assert throttle.retry_after("k") == 901

    clock.now += 600

    assert throttle.retry_after("k") == 301


def test_retry_after_is_zero_below_the_limit(throttle: LoginThrottle) -> None:
    _fail(throttle, "k", 4)

    assert throttle.retry_after("k") == 0


def test_memory_is_bounded(clock: _Clock) -> None:
    small = LoginThrottle(max_failures=1, max_tracked=3, clock=clock)
    for index in range(10):
        small.record_failure(f"client-{index}")

    assert small.is_blocked("client-9")
    assert not small.is_blocked("client-0")
    assert small.tracked_clients == 3
