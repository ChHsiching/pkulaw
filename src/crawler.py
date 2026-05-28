"""Crawler for PKULaw cases — incremental search + fetch."""

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.exporter import export_excel, export_json
from src.parser import parse_case

OUTPUT_DIR = Path("output")
PROGRESS_FILE = OUTPUT_DIR / "progress.json"
SEARCH_CACHE = OUTPUT_DIR / "search_results.json"
RESULTS_FILE = OUTPUT_DIR / "pkulaw_cases.json"
EXCEL_FILE = OUTPUT_DIR / "pkulaw_cases.xlsx"
INTERMEDIATE_INTERVAL = 500
REQUEST_DELAY = 0.3
PAGE_SIZE = 100
MAX_PAGES = 10

SORT_ORDERS = [
    "LastInstanceDate Desc",
    "LastInstanceDate Asc",
    "SortNum Desc",
    "SortNum Asc",
]

BASE_SEARCH_BODY = {
    "orderbyExpression": "LastInstanceDate Desc",
    "fieldNodes": [
        {
            "type": "text",
            "order": 1,
            "combineAs": 2,
            "fieldName": "FullText",
            "showText": "全文",
            "subCombineAs": 2,
            "fieldItems": [
                {
                    "values": "抗诉",
                    "valuesCombineAs": 2,
                    "extra": {"values": "", "combineAs": 2},
                    "matchType": 1,
                    "matchSpan": 1,
                    "matchSpanGap": 0,
                    "fieldScope": {"fieldName": "", "showText": ""},
                    "order": 0,
                    "filterNodes": [],
                }
            ],
            "matchTypeEnabled": False,
            "matchSpanEnabled": True,
            "matchSpans": None,
        },
        {
            "type": "select",
            "order": 6,
            "combineAs": 2,
            "fieldName": "TrialStep",
            "showText": "审理程序",
            "fieldItems": [
                {
                    "items": [
                        {"text": "二审", "path": "002", "name": "二审", "value": "002"},
                        {"text": "再审", "path": "003", "name": "再审", "value": "003"},
                    ],
                    "combineAs": 2,
                    "order": 0,
                    "filterNodes": [],
                }
            ],
        },
    ],
    "clusterFilters": {"CategoryNew": "001"},
    "groupBy": {},
}


def _load_progress() -> set[str]:
    if PROGRESS_FILE.exists():
        data = json.loads(PROGRESS_FILE.read_text())
        return set(data.get("fetched_gids", []))
    return set()


def _save_progress(fetched_gids: set[str]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(
        json.dumps({"fetched_gids": sorted(fetched_gids)}, ensure_ascii=False, indent=2)
    )


def _save_search(results: list[dict], last_year: int) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SEARCH_CACHE.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"  Saved search cache: {len(results)} cases (through year {last_year})")


def _authenticate(page) -> str:
    print("=== Authentication ===")
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
                    break
            if token:
                print(f"Authenticated ({token[:40]}...)")
                return token
        except Exception as e:
            print(f"Auth attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                page.wait_for_timeout(5000)
    raise RuntimeError("Authentication failed")


def _reauth(page) -> str:
    print("  Re-authenticating...")
    page.goto(
        "https://www.pkulaw.com/advanced/case", wait_until="commit", timeout=120000
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
            print(f"  Re-authenticated ({token[:30]}...)")
            return token
    raise RuntimeError("Re-authentication failed")


def _search_one(page, token, year, sort_order, page_idx) -> tuple[dict, str]:
    body = {
        **BASE_SEARCH_BODY,
        "orderbyExpression": sort_order,
        "pageIndex": page_idx,
        "pageSize": PAGE_SIZE,
        "groupBy": {"LastInstanceDate": str(year)},
    }
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
                token = _reauth(page)
                continue
            return data, token
        except Exception as e:
            if "Execution context" in str(e):
                token = _reauth(page)
                continue
            raise
    return {}, token


def run_search() -> None:
    """Search and cache gids. Incremental — resumes from last saved year."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    seen_gids = set()
    start_year = 2026

    if SEARCH_CACHE.exists():
        results = json.loads(SEARCH_CACHE.read_text())
        for r in results:
            seen_gids.add(r["gid"])
        if results:
            start_year = results[-1].get("search_year", 2026) - 1
        print(f"Search cache: {len(results)} cases. Resuming from year {start_year}.")

    if start_year < 2000:
        print(f"Search complete: {len(results)} total cases.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )
        page = context.new_page()

        token = _authenticate(page)
        print(f"\n=== Searching (year {start_year} → 2000) ===")

        try:
            for year in range(start_year, 1999, -1):
                for sort_order in SORT_ORDERS:
                    page_idx = 0
                    while page_idx < MAX_PAGES:
                        data, token = _search_one(
                            page, token, year, sort_order, page_idx
                        )
                        items = data.get("data", [])

                        if not items:
                            break

                        new_count = 0
                        for item in items:
                            gid = item["gid"]
                            if gid in seen_gids:
                                continue
                            seen_gids.add(gid)
                            results.append(
                                {
                                    "gid": gid,
                                    "title": item.get("title", ""),
                                    "search_year": year,
                                }
                            )
                            new_count += 1

                        if page_idx == 0:
                            total = data.get("total", 0)
                            print(
                                f"  {year} [{sort_order}]: total={total}, +{new_count}"
                            )

                        if new_count == 0:
                            break

                        page_idx += 1
                        time.sleep(REQUEST_DELAY)

                print(f"  Year {year}: {len(results)} total unique")
                _save_search(results, year)

        except Exception as e:
            print(f"Search interrupted: {e}")
            _save_search(results, year if "year" in dir() else start_year)

        browser.close()

    print(f"\nTotal unique cases: {len(results)}")


def _save_all(results: list[dict], fetched_gids: set[str]) -> None:
    export_json(results, RESULTS_FILE)
    try:
        export_excel(results, EXCEL_FILE)
    except Exception as e:
        print(f"  Excel export failed: {e}")
    _save_progress(fetched_gids)
    good = sum(1 for c in results if len(c.get("full_text", "")) > 500)
    print(
        f"  -> Saved ({len(results)} cases, {len(fetched_gids)} fetched, {good} loaded)"
    )


def run_fetch() -> None:
    """Fetch detail pages for cached search results. Auto-restarts on session failure."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not SEARCH_CACHE.exists():
        print("No search cache. Run run_search() first.")
        return

    cases_meta = json.loads(SEARCH_CACHE.read_text())

    while True:
        fetched_gids = _load_progress()
        results = []
        if RESULTS_FILE.exists():
            results = json.loads(RESULTS_FILE.read_text())

        remaining = [c for c in cases_meta if c["gid"] not in fetched_gids]
        print(f"\n{'='*50}")
        print(
            f"Remaining: {len(remaining)}/{len(cases_meta)} ({len(fetched_gids)} fetched)"
        )

        if not remaining:
            print("All fetched!")
            _save_all(results, fetched_gids)
            break

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path="/usr/bin/chromium",
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    ignore_https_errors=True,
                )
                page = context.new_page()

                token = _authenticate(page)
                print(f"=== Fetching {len(remaining)} cases ===")

                consecutive_errors = 0
                for i, case in enumerate(remaining):
                    gid = case["gid"]
                    title = case["title"]
                    url = f"https://www.pkulaw.com/pfnl/{gid}.html"

                    try:
                        for nav_attempt in range(3):
                            try:
                                page.goto(url, wait_until="commit", timeout=60000)
                                break
                            except Exception:
                                if nav_attempt == 2:
                                    raise
                                page.wait_for_timeout(5000)

                        for _ in range(16):
                            page.wait_for_timeout(500)
                            html_len = page.evaluate(
                                "() => document.querySelector('.fulltext-wrap')?.innerHTML?.length || 0"
                            )
                            if html_len > 1000:
                                break

                        html = page.content()
                        parsed = parse_case(html, gid)
                        if not parsed["title"] or parsed["title"] in (
                            "已进入法宝V6",
                            "",
                        ):
                            parsed["title"] = title

                        results.append(parsed)
                        fetched_gids.add(gid)
                        consecutive_errors = 0

                        if (i + 1) % 50 == 0:
                            print(f"[{i+1}/{len(remaining)}] ({title[:40]})")

                    except Exception as e:
                        err_str = str(e)[:80]
                        consecutive_errors += 1
                        print(f"[{i+1}/{len(remaining)}] ERR: {err_str}")

                        if "Execution context" in err_str or "Target closed" in err_str:
                            try:
                                page = context.new_page()
                                page.goto(
                                    "https://www.pkulaw.com/advanced/case",
                                    wait_until="commit",
                                    timeout=60000,
                                )
                                page.wait_for_timeout(3000)
                                page.evaluate(
                                    "() => localStorage.getItem('access_token') || ''"
                                )
                            except Exception:
                                print("  Page recovery failed, restarting browser...")
                                break

                        if consecutive_errors >= 5:
                            print("  Too many errors, restarting browser...")
                            break

                    if len(fetched_gids) % INTERMEDIATE_INTERVAL == 0:
                        _save_all(results, fetched_gids)

                    time.sleep(REQUEST_DELAY)

                browser.close()

        except Exception as e:
            print(f"Session crashed: {e}")

        _save_all(results, fetched_gids)
        print(f"Restart in 15s...")
        time.sleep(15)

    good = sum(1 for c in results if len(c.get("full_text", "")) > 500)
    print(
        f"\nTotal: {len(results)} cases, {good} loaded ({100*good//max(len(results),1)}%)"
    )


def run() -> list[dict]:
    run_search()
    run_fetch()
    return json.loads(RESULTS_FILE.read_text()) if RESULTS_FILE.exists() else []
