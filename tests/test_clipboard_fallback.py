"""Regression guard for the synchronous clipboard fallback path.

copyToClipboard() tries navigator.clipboard.writeText() first and falls back to
document.execCommand('copy') inside the .catch(). That catch runs as a microtask,
after the synchronous click handler has returned, so in principle the fallback no
longer holds user activation and execCommand('copy') is permitted to fail silently.

Concerns have been raised that this ordering silently breaks copying when the
browser window is unfocused ("Document is not focused") or write permission is
denied. That could NOT be reproduced here: as of this writing the fallback still
delivers the value in headless Chromium even when it runs from a microtask.

So this is a guard, not a reproduction. It pins the observable contract that
matters either way, and it fails loudly if a future refactor drops or reorders the
fallback. If the ordering does turn out to break real headed browsers, the fix is
to run execCommand synchronously inside the click gesture as the primary path.

Deliberately stubs only writeText, keeping readText real, so the assertion is on
actual clipboard contents. Asserting merely that the fallback was attempted would
pass even when nothing was copied.
"""

import pandas as pd
import pytest

from tax_tools.formatter import render_summary_table_html

pytest.importorskip(
    "playwright.sync_api",
    reason="playwright is not installed; install the 'browser-tests' extra",
)
pytest.importorskip(
    "pytest_playwright",
    reason="pytest-playwright is not installed; install the 'browser-tests' extra",
)

pytestmark = pytest.mark.browser


@pytest.fixture
def df():
    return pd.DataFrame(
        [
            {
                "Brokerage Name": "BBAE -3240",
                "Account #": "***-3240",
                "ST Proceeds": "$1,000.00",
                "ST Basis": "$800.00",
                "ST Wash Sale": "$25.00",
                "ST Net": "$175.00",
                "LT Proceeds": "$0.00",
                "LT Basis": "$0.00",
                "LT Wash Sale": "$0.00",
                "LT Net": "$0.00",
            }
        ]
    )


def test_copy_survives_a_rejected_async_clipboard_write(clipboard, df):
    """When writeText() rejects, the synchronous fallback must still copy.

    Simulates the real-world rejection seen when the browser window is not focused
    ("Document is not focused") and when write permission is denied. Only
    writeText is stubbed, so readText stays real and the clipboard contents can
    actually be asserted rather than merely checking the fallback was attempted.
    """
    clipboard.load(render_summary_table_html(df))

    # Force the async path to reject, leaving only the execCommand fallback.
    clipboard.page.evaluate(
        """() => {
            const real = navigator.clipboard;
            real.writeText = () => Promise.reject(new Error('Document is not focused'));
            window.__execCommands = [];
            const original = document.execCommand.bind(document);
            document.execCommand = (command, ...rest) => {
                window.__execCommands.push(command);
                return original(command, ...rest);
            };
        }"""
    )

    clipboard.page.locator(".summary-table tbody .cell-text").first.click()
    clipboard.page.wait_for_timeout(500)

    attempted = clipboard.page.evaluate("() => window.__execCommands")
    assert attempted, "fallbackCopy() was never reached after writeText() rejected"
    assert attempted == ["copy"]

    # The decisive assertion: did the value actually reach the clipboard?
    assert clipboard.read() == "BBAE -3240"