"""Crawler for PKULaw cases — incremental search + fetch using partitioning."""

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
from src.partition import SORT_ORDERS, _add_dimension_filter, partition_query
from src.query import PAGE_SIZE, build_api_body

INTERMEDIATE_INTERVAL = 500


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
# Query matching and partition tree helpers
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


def _collect_leaf_searches(tree: dict, base_config: dict) -> list[tuple[str, dict]]:
    """Flatten partition tree to leaf (label, config) pairs.

    At each non-leaf level, applies the dimension filter to derive a child
    search config before recursing.
    """
    if tree.get("children") is None:
        # Leaf node
        return [(tree["label"], base_config)]

    dimension = tree.get("dimension")
    children = tree.get("children", [])
    leaves: list[tuple[str, dict]] = []

    for child in children:
        child_config = _add_dimension_filter(base_config, dimension, child["label"])
        leaves.extend(_collect_leaf_searches(child, child_config))

    return leaves


# ---------------------------------------------------------------------------
# Search results save
# ---------------------------------------------------------------------------


def _save_search_results(
    output_dir: Path,
    results: list[dict],
    search_config: dict,
    partition_tree: dict,
    started_at: datetime,
    completed_at: datetime,
) -> None:
    """Save enhanced search_results.json with query metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "query": {"fieldNodes": search_config.get("fieldNodes", [])},
        "partition_strategy": {
            "dimension": partition_tree.get("dimension"),
            "total": partition_tree.get("total"),
            "crawlable": partition_tree.get("crawlable"),
            "groups": partition_tree.get("groups"),
        },
        "total_unique": len(results),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "results": results,
    }
    _search_cache_file(output_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2)
    )


# ---------------------------------------------------------------------------
# run_search — partitioning-based search
# ---------------------------------------------------------------------------


def run_search(
    search_config: dict,
    page,
    token: str,
    output_dir: Path,
    logger,
) -> list[dict]:
    """Search using partitioning to collect all gids. Returns list of {gid, title}.

    1. Check cache — skip if query matches
    2. Partition the query space
    3. For each leaf, for each sort order, paginate through results
    4. Deduplicate by gid
    5. Save enhanced search_results.json
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    max_pages = search_config.get("settings", {}).get("max_pages", 10)

    # Check if cached results match current query
    cache_file = _search_cache_file(output_dir)
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if _matches_query(cached, search_config):
            logger.info("Search cache matches current query, skipping search.")
            return cached.get("results", [])

    started_at = datetime.now()

    # Partition the query
    ctx = TokenContext(token=token)
    partition_tree = partition_query(page, ctx, search_config)
    leaves = _collect_leaf_searches(partition_tree, search_config)

    results: list[dict] = []
    seen_gids: set[str] = set()

    for label, leaf_config in leaves:
        for sort_order in SORT_ORDERS:
            page_idx = 0
            while page_idx < max_pages:
                body = build_api_body(
                    leaf_config, page_index=page_idx, order_by=sort_order
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
                    results.append({"gid": gid, "title": item.get("title", "")})
                    new_count += 1

                if new_count == 0:
                    break

                page_idx += 1
                time.sleep(search_config.get("settings", {}).get("delay", 0.3))

        # Save incrementally after each leaf
        completed_at = datetime.now()
        _save_search_results(
            output_dir,
            results,
            search_config,
            partition_tree,
            started_at=started_at,
            completed_at=completed_at,
        )
        logger.info(f"Leaf '{label}': {len(results)} total unique gids")

    return results


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
# run_fetch — parameterized detail page fetcher
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

                    for _ in range(16):
                        page.wait_for_timeout(500)
                        html_len = page.evaluate(
                            "() => document.querySelector('.fulltext-wrap')?.innerHTML?.length || 0"
                        )
                        if html_len > 1000:
                            break

                    html = page.content()
                    parsed = parse_case(html, gid)
                    if not parsed["title"] or parsed["title"] in ("已进入法宝V6", ""):
                        parsed["title"] = title

                    results.append(parsed)
                    fetched_gids.add(gid)
                    consecutive_errors = 0

                    if max_cases > 0 and len(fetched_gids) >= max_cases:
                        break

                    if (i + 1) % 50 == 0:
                        logger.info(f"[{i+1}/{len(remaining)}] ({title[:40]})")

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
