"""End-to-end test of the status dashboard with Playwright.

Spins up the real API with uvicorn in a background thread, serves the dashboard,
and drives a headless browser to confirm the migrated metrics render. Skips
cleanly if the Playwright browser binary isn't installed in the environment.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def live_server(migrated):
    import uvicorn
    from cutover.cloud.api import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_dashboard_shows_migrated_metrics(live_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"chromium not available: {exc}")
        page = browser.new_page()
        page.goto(live_server, wait_until="networkidle")
        count = page.get_by_test_id("property-count").inner_text()
        status = page.get_by_test_id("status").inner_text()
        assert int(count) > 0
        assert status == "Migration loaded"
        browser.close()