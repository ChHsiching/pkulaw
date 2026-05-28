"""Re-fetch failed cases and update the output files."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.exporter import export_excel, export_json
from src.parser import parse_case

RESULTS_FILE = Path("output/pkulaw_cases.json")
EXCEL_FILE = Path("output/pkulaw_cases.xlsx")
PROGRESS_FILE = Path("output/progress.json")
REFETCH_FILE = Path("output/refetch_gids.json")
REQUEST_DELAY = 1.5


def refetch():
    with open(RESULTS_FILE) as f:
        cases = json.load(f)
    with open(REFETCH_FILE) as f:
        bad_gids = set(json.load(f))

    # Build title lookup
    title_map = {c["gid"]: c["title"] for c in cases}

    print(f"Re-fetching {len(bad_gids)} failed cases...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )
        page = context.new_page()

        # Auth
        page.goto(
            "https://www.pkulaw.com/advanced/case", wait_until="commit", timeout=120000
        )
        for _ in range(60):
            page.wait_for_timeout(1000)
            token = page.evaluate("() => localStorage.getItem('access_token') || ''")
            if token:
                print("Authenticated.")
                break

        updated = 0
        remaining = []

        for i, gid in enumerate(sorted(bad_gids)):
            url = f"https://www.pkulaw.com/pfnl/{gid}.html"
            title = title_map.get(gid, gid[:20])

            try:
                for attempt in range(2):
                    try:
                        page.goto(url, wait_until="commit", timeout=120000)
                        break
                    except Exception:
                        if attempt == 1:
                            raise
                        page.wait_for_timeout(5000)

                page.wait_for_timeout(5000)  # longer wait for content
                html = page.content()
                parsed = parse_case(html, gid)

                if not parsed["title"] or parsed["title"] in ("已进入法宝V6", ""):
                    parsed["title"] = title

                ft_len = len(parsed.get("full_text", ""))

                if ft_len > 100:
                    # Update the case in the list
                    for j, c in enumerate(cases):
                        if c["gid"] == gid:
                            cases[j] = parsed
                            break
                    updated += 1
                    print(f"[{i+1}/{len(bad_gids)}] OK: {title[:50]} ({ft_len} chars)")
                else:
                    remaining.append(gid)
                    print(
                        f"[{i+1}/{len(bad_gids)}] STILL BAD: {title[:50]} ({ft_len} chars)"
                    )

            except Exception as e:
                remaining.append(gid)
                print(f"[{i+1}/{len(bad_gids)}] ERROR: {title[:50]} - {e}")
                continue

            import time

            time.sleep(REQUEST_DELAY)

        browser.close()

    # Save results
    print(f"\nUpdated {updated} cases. {len(remaining)} still failed.")
    export_json(cases, RESULTS_FILE)
    export_excel(cases, EXCEL_FILE)

    # Update progress
    fetched = {c["gid"] for c in cases if len(c.get("full_text", "")) > 100}
    PROGRESS_FILE.write_text(
        json.dumps({"fetched_gids": sorted(fetched)}, ensure_ascii=False, indent=2)
    )

    if remaining:
        with open(REFETCH_FILE, "w") as f:
            json.dump(remaining, f)
        print(f"Remaining failures saved to {REFETCH_FILE}")

    # Print stats
    good = sum(1 for c in cases if len(c.get("full_text", "")) > 500)
    print(f"\nTotal cases: {len(cases)}")
    print(f"Good (>500 chars): {good}")
    print(f"Still bad: {len(cases) - good}")


if __name__ == "__main__":
    refetch()
