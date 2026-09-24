"""Launch a real, visible browser with a profile that remembers your login.

Nothing here ever sees a password: the profile directory is a persistent Chromium user-data-dir, you log
in by hand the first time in the window this opens, and every later run reuses those cookies. Requires
the optional `browser` extra (`pip install -e ".[browser]"` then `playwright install chromium`).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, TypeVar

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, sync_playwright
except ImportError as exc:  # pragma: no cover - exercised only when the extra isn't installed
    raise ImportError(
        "the 'browser' extra is required: pip install -e '.[browser]' && playwright install chromium"
    ) from exc

T = TypeVar("T")

DEFAULT_PROFILE_DIR = Path.home() / ".clicktrader" / "browser-profile"


def open_page(url: str, *, profile_dir: Path = DEFAULT_PROFILE_DIR, headless: bool = False) -> Page:
    """Open ``url`` in a persistent Chromium profile and return its page.

    The caller owns the returned page's lifetime; there is no context manager here because the whole
    point is that the window stays open across many calls (and the user may keep using it by hand).
    """
    profile_dir.mkdir(parents=True, exist_ok=True)
    playwright = sync_playwright().start()
    context = playwright.chromium.launch_persistent_context(str(profile_dir), headless=headless)
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(url)
    return page


def is_logged_in(page: Page) -> bool:
    """Best-effort check: the trade page has a "Deposit" button and no password field.

    Deliberately requires the *positive* signal (Deposit present), not just the negative one (no
    password field) — right after `page.goto()` the React app may not have mounted anything yet, and a
    blank page has no password field either. Checking absence alone raced this into a false "logged in"
    the first time this ran live.
    """
    return page.get_by_role("button", name="Deposit").count() > 0 and page.locator('input[type="password"]').count() == 0


def wait_for_login(page: Page, *, poll_seconds: float = 2.0, timeout_seconds: float = 600.0) -> None:
    """Block until `is_logged_in` — i.e. until a human has finished logging in in this same window.

    Called once per session, not per tick: after login, cookies persist in the profile and later runs
    skip straight past this.
    """
    deadline = time.monotonic() + timeout_seconds
    if is_logged_in(page):
        return
    print("waiting for login — sign in in the browser window that just opened...")
    while time.monotonic() < deadline:
        if is_logged_in(page):
            print("logged in.")
            return
        time.sleep(poll_seconds)
    raise TimeoutError(f"still not logged in after {timeout_seconds:.0f}s")


def call_with_reconnect(page: Page, fn: Callable[[], T], *, retries: int = 5, backoff: float = 1.0) -> T:
    """Call `fn()` (a DOM read against `page`), recovering from a navigation mid-read.

    A page reload, a client-side redirect, or a session refresh destroys the JS execution context while
    a read is in flight — Playwright raises "Execution context was destroyed" for exactly this, and it
    happened live in the first long recording run. This waits for the page to settle, logs back in if
    the navigation landed back on the login screen (session expired), and retries. Only Playwright's own
    transient errors are caught here; anything else (e.g. a parsing `ValueError`) is a real bug in the
    adapter, not a flaky page, and propagates immediately.
    """
    if retries < 1:
        raise ValueError("retries must be at least 1")
    for attempt in range(retries):
        try:
            return fn()
        except PlaywrightError:
            if attempt == retries - 1:
                raise
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
            except PlaywrightError:
                pass
            try:
                logged_in = is_logged_in(page)
            except PlaywrightError:
                logged_in = True  # page still settling; don't force a login wait on top of that
            if not logged_in:
                wait_for_login(page)
            time.sleep(backoff)
