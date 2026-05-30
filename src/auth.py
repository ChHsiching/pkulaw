"""Browser-based authentication and PKULaw API calls."""

from dataclasses import dataclass

from playwright.sync_api import Page, sync_playwright

API_URL = "/searchingapi/adv/list/pfnl"

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class TokenContext:
    token: str


def launch_browser(
    browser_path: str = "/usr/bin/chromium",
    headless: bool = True,
):
    """Launch Playwright browser. Returns (playwright, browser, context, page)."""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        executable_path=browser_path,
        headless=headless,
        args=["--no-sandbox", "--disable-setuid-sandbox"],
    )
    context = browser.new_context(
        user_agent=_USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        ignore_https_errors=True,
    )
    page = context.new_page()
    return pw, browser, context, page


def close_browser(pw, browser) -> None:
    """Clean up browser resources."""
    browser.close()
    pw.stop()


def authenticate(page: Page) -> str:
    """Authenticate with PKULaw via school intranet. Returns access token."""
    for attempt in range(3):
        try:
            page.goto(
                "https://www.pkulaw.com/advanced/case",
                wait_until="commit",
                timeout=120000,
            )
            for _ in range(60):
                page.wait_for_timeout(1000)
                token = page.evaluate(
                    "() => localStorage.getItem('access_token') || ''"
                )
                if (
                    token
                    and page.evaluate(
                        "() => document.getElementById('app')?.innerHTML?.length || 0"
                    )
                    > 10000
                ):
                    return token
            if token:
                return token
        except Exception:
            if attempt < 2:
                page.wait_for_timeout(5000)
    raise RuntimeError("Authentication failed")


def reauthenticate(page: Page) -> str:
    """Re-authenticate after session expiry. Returns access token."""
    page.goto(
        "https://www.pkulaw.com/advanced/case",
        wait_until="commit",
        timeout=120000,
    )
    for _ in range(60):
        page.wait_for_timeout(1000)
        token = page.evaluate("() => localStorage.getItem('access_token') || ''")
        if (
            token
            and page.evaluate(
                "() => document.getElementById('app')?.innerHTML?.length || 0"
            )
            > 10000
        ):
            return token
    raise RuntimeError("Re-authentication failed")


def search_api(page: Page, token: str, body: dict) -> dict:
    """Send a search request to PKULaw API. Returns response dict.

    Retries once on auth errors (re-authenticates and retries).
    """
    for attempt in range(2):
        try:
            data = page.evaluate(
                """async ([body, token]) => {
                    const resp = await fetch('/searchingapi/adv/list/pfnl', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json', 'Authorization': token},
                        body: JSON.stringify(body)
                    });
                    const text = await resp.text();
                    try { return JSON.parse(text); }
                    catch(e) { return {_error: 'not_json'}; }
                }""",
                [body, token],
            )
            if data.get("_error"):
                token = reauthenticate(page)
                continue
            return data
        except Exception as e:
            if "Execution context" in str(e):
                token = reauthenticate(page)
                continue
            raise
    return {}
