"""Shared pytest fixtures.

The clipboard fixtures serve the rendered table over http://127.0.0.1 rather than
using page.set_content(). set_content() runs on about:blank, which is not a secure
context, so navigator.clipboard is undefined there and no real clipboard assertion
is possible. Serving over loopback gives a secure context, matching how Streamlit
itself is reached in development.

Note: this module deliberately does not importorskip playwright. A skip raised while
importing conftest would skip the whole suite, including the tests that need no
browser at all. The browser test module does its own importorskip instead.
"""

import http.server
import socket
import threading

import pytest


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture(scope="module", autouse=True)
def _require_browser_support(request):
    """Skip browser-marked tests before the page fixture is ever set up.

    Module-level importorskip in the test modules cannot see this: a missing
    plugin makes the ``page`` fixture unavailable and pytest would report errors
    rather than skips. Module-scoped autouse fixtures are set up ahead of the
    function-scoped page fixture, so skipping here keeps the suite green on a
    machine without the browser extra.
    """
    if request.node.get_closest_marker("browser") is None:
        return
    if not request.config.pluginmanager.hasplugin("playwright"):
        pytest.skip("pytest-playwright is not installed; install the 'browser-tests' extra")


@pytest.fixture(scope="session")
def table_server():
    """Serve arbitrary HTML fragments over loopback for the lifetime of the session."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = self.server.payload
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", _free_port()), Handler)
    server.payload = b""
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def serve_table(page, table_server):
    """Return a callable that serves HTML and navigates the page to it."""

    def _serve(html):
        table_server.payload = (
            "<!DOCTYPE html><html><body>" + html + "</body></html>"
        ).encode("utf-8")
        page.goto(f"http://127.0.0.1:{table_server.server_address[1]}/")
        return page

    return _serve


@pytest.fixture
def clipboard(page, serve_table):
    """Clipboard test harness.

    Permissions are granted without an ``origin`` argument on purpose: granting for
    an origin that does not exactly match the served URL (including its port) fails
    with NotAllowedError on both read and write. After loading, the clipboard is set
    to a sentinel so tests can prove a click did or did not write to it.

    Usage::

        def test_x(clipboard):
            clipboard.load(render_summary_table_html(df))
            clipboard.page.locator(...).click()
            assert clipboard.read() == "1000.00"
    """
    return ClipboardHarness(page, serve_table)


class ClipboardHarness:
    """Loads rendered HTML into a page and inspects the real system clipboard."""

    def __init__(self, page, serve_table):
        # Imported lazily so a missing pytest-playwright only affects browser tests.
        from playwright.sync_api import expect

        self.page = page
        self.expect = expect
        self._serve_table = serve_table

        # Permissions are granted without an ``origin`` argument on purpose:
        # granting for an origin that does not exactly match the served URL
        # (including its port) fails with NotAllowedError on read and write.
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    def load(self, html):
        """Serve the HTML, then reset the clipboard to a known sentinel value."""
        self._serve_table(html)
        self.page.evaluate("() => navigator.clipboard.writeText('CLIPBOARD_UNTOUCHED')")
        return self.page

    def read(self):
        return self.page.evaluate("() => navigator.clipboard.readText()")

    def expect_written(self, value, timeout=4000):
        """Poll until the clipboard equals value, so timing is not asserted on."""
        return _poll_clipboard(self.page, value, timeout)

    def watch_writes(self):
        """Start counting clipboard writes without breaking them.

        Asserting only the resulting clipboard value cannot detect a double write,
        and asserting only a CSS class passes even when nothing was copied. Call
        this before clicking.
        """
        self.page.evaluate(
            """() => {
                window.__writes = [];
                const original = navigator.clipboard.writeText.bind(navigator.clipboard);
                navigator.clipboard.writeText = (text) => {
                    window.__writes.push(text);
                    return original(text);
                };
            }"""
        )

    def writes(self):
        """Clipboard writes recorded since the last watch_writes() call."""
        return self.page.evaluate("() => window.__writes")


def _poll_clipboard(page, expected, timeout):
    """Poll clipboard contents until they match, then return them.

    Deliberately polls instead of sleeping a fixed interval so the suite does not
    depend on how quickly a given clipboard path resolves.
    """
    import time

    deadline = time.time() + timeout / 1000.0
    contents = None
    while time.time() < deadline:
        contents = page.evaluate("() => navigator.clipboard.readText()")
        if contents == expected:
            return contents
        page.wait_for_timeout(50)
    return contents
