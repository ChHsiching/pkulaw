from playwright.sync_api import sync_playwright


def get_auth_session():
    """Launch headless browser, authenticate via IP, extract token and cookies."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )
        page = context.new_page()

        page.goto(
            "https://www.pkulaw.com/advanced/case",
            wait_until="domcontentloaded",
            timeout=60000,
        )

        token = ""
        for _ in range(30):
            page.wait_for_timeout(1000)
            token = page.evaluate(
                "() => localStorage.getItem('access_token') || ''"
            )
            if token:
                break

        if not token:
            raise RuntimeError("Failed to extract access token from localStorage")

        cookies = context.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}

        browser.close()
        return token, cookie_dict


if __name__ == "__main__":
    token, cookies = get_auth_session()
    print(f"Token: {token[:80]}...")
    print(f"Cookies: {len(cookies)} items")
