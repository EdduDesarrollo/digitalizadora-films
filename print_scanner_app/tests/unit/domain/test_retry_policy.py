import pytest

from print_scanner_app.domain.policies.retry_policy import RetryConfig, run_with_retries


def test_run_with_retries_ok():
    n = {"c": 0}

    def fn():
        n["c"] += 1
        return 42

    assert run_with_retries(fn, should_retry=lambda e: False) == 42
    assert n["c"] == 1


def test_run_with_retries_eventually():
    n = {"c": 0}

    def fn():
        n["c"] += 1
        if n["c"] < 3:
            raise TimeoutError("x")
        return "ok"

    r = run_with_retries(
        fn,
        should_retry=lambda e: isinstance(e, TimeoutError),
        config=RetryConfig(max_attempts=4, delay_seconds=0),
        sleep_fn=lambda _: None,
    )
    assert r == "ok"
    assert n["c"] == 3


def test_run_with_retries_stops():
    def fn():
        raise ValueError("no retry")

    with pytest.raises(ValueError):
        run_with_retries(
            fn,
            should_retry=lambda e: isinstance(e, TimeoutError),
            config=RetryConfig(max_attempts=3, delay_seconds=0),
            sleep_fn=lambda _: None,
        )
