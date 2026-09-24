import pytest
from playwright.sync_api import Error as PlaywrightError

from clicktrader.browser import driver


class FakePage:
    """Just enough of a Page for call_with_reconnect's own recovery steps to run."""

    def __init__(self) -> None:
        self.load_state_waits = 0

    def wait_for_load_state(self, *args, **kwargs) -> None:
        self.load_state_waits += 1


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(driver.time, "sleep", lambda _seconds: None)


@pytest.fixture(autouse=True)
def _already_logged_in(monkeypatch):
    monkeypatch.setattr(driver, "is_logged_in", lambda page: True)


def test_returns_the_first_success():
    page = FakePage()
    assert driver.call_with_reconnect(page, lambda: 42) == 42
    assert page.load_state_waits == 0


def test_retries_through_a_destroyed_context():
    page = FakePage()
    calls = iter([PlaywrightError("Execution context was destroyed"), PlaywrightError("still gone"), "ok"])

    def flaky():
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    assert driver.call_with_reconnect(page, flaky, retries=5, backoff=0) == "ok"
    assert page.load_state_waits == 2


def test_gives_up_after_the_last_retry():
    page = FakePage()

    def always_fails():
        raise PlaywrightError("gone for good")

    with pytest.raises(PlaywrightError):
        driver.call_with_reconnect(page, always_fails, retries=3, backoff=0)
    assert page.load_state_waits == 2  # settles between attempts, but not after the final one


def test_non_playwright_errors_are_not_retried():
    page = FakePage()

    def broken():
        raise ValueError("a real bug, not a flaky page")

    with pytest.raises(ValueError):
        driver.call_with_reconnect(page, broken, retries=5, backoff=0)
    assert page.load_state_waits == 0


def test_logs_back_in_if_the_navigation_landed_on_the_login_screen(monkeypatch):
    page = FakePage()
    login_calls = []
    monkeypatch.setattr(driver, "is_logged_in", lambda page: False)
    monkeypatch.setattr(driver, "wait_for_login", lambda page: login_calls.append(page))

    calls = iter([PlaywrightError("Execution context was destroyed"), "ok"])

    def flaky():
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    assert driver.call_with_reconnect(page, flaky, retries=3, backoff=0) == "ok"
    assert login_calls == [page]


def test_retries_must_be_at_least_one():
    with pytest.raises(ValueError):
        driver.call_with_reconnect(FakePage(), lambda: 1, retries=0)
