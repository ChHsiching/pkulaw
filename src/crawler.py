"""Crawler for PKULaw cases — unified search+fetch per year."""

import json
import time
from datetime import datetime
from pathlib import Path

from src.auth import (
    TokenContext,
    authenticate,
    close_browser,
    launch_browser,
    search_api,
)
from src.exporter import export_excel, export_json
from src.parser import parse_case
from src.partition import SORT_ORDERS
from src.query import PAGE_SIZE, build_api_body

INTERMEDIATE_INTERVAL = 50


def _wait_for_content(page, min_chars=5000, attempts=30, interval_ms=500) -> None:
    """Wait for .fulltext-wrap to have enough content."""
    for _ in range(attempts):
        page.wait_for_timeout(interval_ms)
        html_len = page.evaluate(
            "() => document.querySelector('.fulltext-wrap')?.innerHTML?.length || 0"
        )
        if html_len > min_chars:
            return
    page.wait_for_timeout(2000)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _progress_file(output_dir: Path) -> Path:
    return output_dir / "progress.json"


def _search_cache_file(output_dir: Path) -> Path:
    return output_dir / "search_results.json"


def _results_file(output_dir: Path) -> Path:
    return output_dir / "pkulaw_cases.json"


def _excel_file(output_dir: Path) -> Path:
    return output_dir / "pkulaw_cases.xlsx"


# ---------------------------------------------------------------------------
# Progress I/O
# ---------------------------------------------------------------------------


def _load_progress(output_dir: Path) -> set[str]:
    pf = _progress_file(output_dir)
    if pf.exists():
        data = json.loads(pf.read_text())
        return set(data.get("fetched_gids", []))
    return set()


def _save_progress(output_dir: Path, fetched_gids: set[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _progress_file(output_dir).write_text(
        json.dumps({"fetched_gids": sorted(fetched_gids)}, ensure_ascii=False, indent=2)
    )


# ---------------------------------------------------------------------------
# Query matching
# ---------------------------------------------------------------------------


def _matches_query(cached: dict, search_config: dict) -> bool:
    """Check if cached search_results matches current query by comparing fieldNodes."""
    query = cached.get("query")
    if not query:
        return False
    cached_nodes = query.get("fieldNodes", [])
    config_nodes = search_config.get("fieldNodes", [])
    if not cached_nodes or not config_nodes:
        return False
    return cached_nodes == config_nodes


# ---------------------------------------------------------------------------
# Search results save
# ---------------------------------------------------------------------------


def _save_search_results(
    output_dir: Path,
    results: list[dict],
    search_config: dict,
    started_at: datetime,
    completed_at: datetime,
) -> None:
    """Save search_results.json with query metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "query": {"fieldNodes": search_config.get("fieldNodes", [])},
        "total_unique": len(results),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "results": results,
    }
    _search_cache_file(output_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2)
    )


# ---------------------------------------------------------------------------
# _save_all — save results and progress
# ---------------------------------------------------------------------------


def _save_all(
    results: list[dict], fetched_gids: set[str], output_dir: Path, logger
) -> None:
    """Save results to JSON/Excel and update progress file."""
    export_json(results, _results_file(output_dir))
    try:
        export_excel(results, _excel_file(output_dir))
    except Exception as e:
        logger.warning(f"Excel export failed: {e}")
    _save_progress(output_dir, fetched_gids)
    good = sum(1 for c in results if len(c.get("full_text", "")) > 500)
    logger.info(
        f"Saved ({len(results)} cases, {len(fetched_gids)} fetched, {good} loaded)"
    )


# ---------------------------------------------------------------------------
# run_search — year-by-year pagination (for estimate command)
# ---------------------------------------------------------------------------


def run_search(
    search_config: dict,
    page,
    token: str,
    output_dir: Path,
    logger,
) -> list[dict]:
    """Search using year-by-year pagination. Returns list of {gid, title}.

    Iterates years from current down to 2000, for each sort order,
    paginating through results. Resumes from last saved year on restart.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    max_pages = search_config.get("settings", {}).get("max_pages", 10)
    delay = search_config.get("settings", {}).get("delay", 0.3)
    ctx = TokenContext(token=token)

    # Check if cached results match current query and are complete
    cache_file = _search_cache_file(output_dir)
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if _matches_query(cached, search_config):
            results = cached.get("results", [])
            if results:
                last_year = results[-1].get("search_year", 2026)
                if last_year <= 2000:
                    logger.info("Search cache complete, skipping search.")
                    return results

    started_at = datetime.now()
    results: list[dict] = []
    seen_gids: set[str] = set()
    start_year = 2026

    # Resume from partial cache
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        cached_results = (
            cached.get("results", []) if isinstance(cached, dict) else cached
        )
        for r in cached_results:
            seen_gids.add(r["gid"])
        results = list(cached_results)
        if cached_results:
            last_year = cached_results[-1].get("search_year", 2026)
            start_year = last_year
        logger.info(f"Resuming from year {start_year}, {len(results)} existing gids")

    for year in range(start_year, 1999, -1):
        for sort_order in SORT_ORDERS:
            page_idx = 0
            while page_idx < max_pages:
                body = build_api_body(
                    search_config,
                    page_index=page_idx,
                    order_by=sort_order,
                    group_by={"LastInstanceDate": str(year)},
                )
                data = search_api(page, ctx, body)
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
                logger.info(
                    f"  {year} [{sort_order}] p{page_idx+1}: "
                    f"+{new_count} new ({len(seen_gids)} total)"
                )

                if new_count == 0:
                    break

                page_idx += 1
                time.sleep(delay)

        # Save incrementally after each year
        completed_at = datetime.now()
        _save_search_results(
            output_dir,
            results,
            search_config,
            started_at=started_at,
            completed_at=completed_at,
        )
        logger.info(f"Year {year}: {len(seen_gids)} total unique gids")

    return results


# ---------------------------------------------------------------------------
# run_fetch — parameterized detail page fetcher (standalone, for resuming)
# ---------------------------------------------------------------------------


def run_fetch(search_config: dict, output_dir: Path, logger) -> list[dict]:
    """Fetch detail pages for cached search results. Auto-restarts on session failure.

    Args:
        search_config: SearchConfig dict with 'settings' containing delay, browser_path, headless.
        output_dir: Directory for progress, results, and cache files.
        logger: Logger instance.

    Returns:
        List of parsed case dicts.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = search_config.get("settings", {})
    delay = settings.get("delay", 0.3)
    browser_path = settings.get("browser_path", "/usr/bin/chromium")
    headless = settings.get("headless", True)
    max_cases = settings.get("max_cases", 0)

    cache_file = _search_cache_file(output_dir)
    if not cache_file.exists():
        logger.error("No search cache. Run run_search() first.")
        return []

    # Handle both old (list) and new (dict with "results" key) formats
    raw = json.loads(cache_file.read_text())
    if isinstance(raw, dict):
        cases_meta = raw.get("results", [])
    else:
        cases_meta = raw

    if not cases_meta:
        logger.info("No cases to fetch.")
        return []

    while True:
        fetched_gids = _load_progress(output_dir)
        results = []
        results_file = _results_file(output_dir)
        if results_file.exists():
            results = json.loads(results_file.read_text())

        remaining = [c for c in cases_meta if c["gid"] not in fetched_gids]
        logger.info(
            f"Remaining: {len(remaining)}/{len(cases_meta)} ({len(fetched_gids)} fetched)"
        )

        if not remaining:
            logger.info("All fetched!")
            _save_all(results, fetched_gids, output_dir, logger)
            return results

        if max_cases > 0 and len(fetched_gids) >= max_cases:
            logger.info(f"Max cases limit reached ({max_cases})")
            _save_all(results, fetched_gids, output_dir, logger)
            return results

        try:
            pw, browser, context, page = launch_browser(
                browser_path=browser_path,
                headless=headless,
            )
            token = authenticate(page)
            logger.info(f"Fetching {len(remaining)} cases")

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

                    _wait_for_content(page)

                    html = page.content()
                    parsed = parse_case(html, gid)
                    if not parsed["title"] or parsed["title"] in ("已进入法宝V6", ""):
                        parsed["title"] = title

                    if "法宝" in parsed.get("full_text", ""):
                        logger.warning(
                            f"  [{i+1}/{len(to_fetch)}] BAD DATA: '{title[:40]}' "
                            f"contains '法宝' — page did not load correctly, skipping"
                        )
                        consecutive_errors += 1
                        if consecutive_errors >= 5:
                            logger.warning("Too many bad pages, stopping fetch")
                            break
                        continue

                    results.append(parsed)
                    fetched_gids.add(gid)
                    consecutive_errors = 0

                    if max_cases > 0 and len(fetched_gids) >= max_cases:
                        break

                    logger.info(
                        f"[{i+1}/{len(remaining)}] ({title[:40]}) "
                        f"{len(fetched_gids)} fetched"
                    )

                except Exception as e:
                    err_str = str(e)[:80]
                    consecutive_errors += 1
                    logger.warning(f"[{i+1}/{len(remaining)}] ERR: {err_str}")

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
                            logger.warning(
                                "Page recovery failed, restarting browser..."
                            )
                            break

                    if consecutive_errors >= 5:
                        logger.warning("Too many errors, restarting browser...")
                        break

                if len(fetched_gids) % INTERMEDIATE_INTERVAL == 0:
                    _save_all(results, fetched_gids, output_dir, logger)

                time.sleep(delay)

            close_browser(pw, browser)

        except Exception as e:
            logger.error(f"Session crashed: {e}")

        _save_all(results, fetched_gids, output_dir, logger)

        if max_cases > 0 and len(fetched_gids) >= max_cases:
            logger.info(f"Max cases limit reached ({max_cases})")
            return results

        logger.info("Restart in 15s...")
        time.sleep(15)


# ---------------------------------------------------------------------------
# run_crawl — unified search+fetch per year
# ---------------------------------------------------------------------------


def run_crawl(
    search_config: dict,
    page,
    token: str,
    output_dir: Path,
    logger,
) -> list[dict]:
    """Search and fetch year by year. After each year's gids are collected,
    immediately fetch those cases and save xlsx. Data appears incrementally.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    max_pages = search_config.get("settings", {}).get("max_pages", 10)
    delay = search_config.get("settings", {}).get("delay", 0.3)
    ctx = TokenContext(token=token)

    # Load existing progress
    cache_file = _search_cache_file(output_dir)
    all_search_gids: list[dict] = []
    seen_gids: set[str] = set()
    start_year = 2026

    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        cached_results = (
            cached.get("results", []) if isinstance(cached, dict) else cached
        )
        for r in cached_results:
            seen_gids.add(r["gid"])
        all_search_gids = list(cached_results)
        if cached_results:
            last_year = cached_results[-1].get("search_year", 2026)
            start_year = last_year
        logger.info(f"Resuming from year {start_year}, {len(seen_gids)} existing gids")

    fetched_gids = _load_progress(output_dir)
    results: list[dict] = []
    results_file = _results_file(output_dir)
    if results_file.exists():
        results = json.loads(results_file.read_text())

    started_at = datetime.now()

    for year in range(start_year, 1999, -1):
        # --- Search this year ---
        year_new_gids: list[dict] = []
        for sort_order in SORT_ORDERS:
            page_idx = 0
            while page_idx < max_pages:
                body = build_api_body(
                    search_config,
                    page_index=page_idx,
                    order_by=sort_order,
                    group_by={"LastInstanceDate": str(year)},
                )
                data = search_api(page, ctx, body)
                items = data.get("data", [])

                if not items:
                    break

                new_count = 0
                for item in items:
                    gid = item["gid"]
                    if gid in seen_gids:
                        continue
                    seen_gids.add(gid)
                    entry = {
                        "gid": gid,
                        "title": item.get("title", ""),
                        "search_year": year,
                    }
                    all_search_gids.append(entry)
                    year_new_gids.append(entry)
                    new_count += 1

                if page_idx == 0:
                    total = data.get("total", 0)
                logger.info(
                    f"  {year} [{sort_order}] p{page_idx+1}: "
                    f"+{new_count} new ({len(seen_gids)} total gids)"
                )

                if new_count == 0:
                    break

                page_idx += 1
                time.sleep(delay)

            # Save search results after each sort order to preserve progress
            completed_at = datetime.now()
            _save_search_results(
                output_dir,
                all_search_gids,
                search_config,
                started_at=started_at,
                completed_at=completed_at,
            )

        # Save search results after all sort orders for the year
        completed_at = datetime.now()
        _save_search_results(
            output_dir,
            all_search_gids,
            search_config,
            started_at=started_at,
            completed_at=completed_at,
        )
        logger.info(f"Year {year} search done: {len(year_new_gids)} new gids")

        # --- Fetch this year's new cases immediately ---
        to_fetch = [g for g in year_new_gids if g["gid"] not in fetched_gids]
        if to_fetch:
            logger.info(f"Fetching {len(to_fetch)} cases for year {year}...")
            consecutive_errors = 0
            for i, case in enumerate(to_fetch):
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

                    _wait_for_content(page)

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

                    logger.info(
                        f"  [{i+1}/{len(to_fetch)}] ({title[:40]}) "
                        f"{len(fetched_gids)} total fetched"
                    )

                except Exception as e:
                    err_str = str(e)[:80]
                    consecutive_errors += 1
                    logger.warning(f"  [{i+1}/{len(to_fetch)}] ERR: {err_str}")

                    if "Execution context" in err_str or "Target closed" in err_str:
                        try:
                            page.goto(
                                "https://www.pkulaw.com/advanced/case",
                                wait_until="commit",
                                timeout=60000,
                            )
                            page.wait_for_timeout(3000)
                        except Exception:
                            logger.warning("Page recovery failed")
                            break

                    if consecutive_errors >= 5:
                        logger.warning("Too many errors, stopping fetch for this year")
                        break

                if len(fetched_gids) % INTERMEDIATE_INTERVAL == 0:
                    _save_all(results, fetched_gids, output_dir, logger)

                time.sleep(delay)

        # Save xlsx + json after each year
        _save_all(results, fetched_gids, output_dir, logger)
        logger.info(
            f"Year {year} done: {len(fetched_gids)} total fetched, "
            f"{len(seen_gids)} total gids"
        )

    return results
