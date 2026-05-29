"""PKULaw CLI crawler — entry point."""

import sys
from pathlib import Path

from src.auth import authenticate, close_browser, launch_browser
from src.cli import build_search_config, create_parser
from src.crawler import run_fetch, run_search
from src.exporter import export_csv, export_excel, export_json
from src.log import setup_logger


def cmd_estimate(config: dict) -> None:
    """Estimate crawlable data volume using recursive partitioning."""
    import time
    from pathlib import Path

    from src.auth import authenticate, close_browser, launch_browser
    from src.partition import partition_query

    output_dir = Path(config["settings"]["output_dir"])
    logger = setup_logger(output_dir / "crawl.log")

    logger.info("Estimate command started")
    logger.info("Query: %s", _format_query(config))

    print("\n=== PKULaw 数据量估算 ===")
    print("\n检索条件：")
    for node in config["fieldNodes"]:
        field = node["field"]
        if "value" in node:
            print(f"  {field}: {node['value']}")
        elif "values" in node:
            print(f"  {field}: {', '.join(node['values'])}")
        elif "range" in node:
            print(f"  {field}: {node['range'][0]} ~ {node['range'][1]}")

    print("\n正在连接 PKULaw...")
    pw, browser, context, page = launch_browser(
        browser_path=config["settings"].get("browser", "/usr/bin/chromium"),
        headless=config["settings"].get("headless", True),
    )
    try:
        token = authenticate(page)
        logger.info("Authenticated (%s...)", token[:30])
        print(f"认证成功 ({token[:30]}...)")

        print("正在估算数据量（递归分区）...\n")
        start_time = time.time()
        result = partition_query(page, token, config)
        elapsed = time.time() - start_time

        _print_estimate_report(result, config, elapsed)
        logger.info(
            "Estimate complete: %d total, %d crawlable",
            result["total"],
            result["crawlable"],
        )

    finally:
        close_browser(pw, browser)


def cmd_crawl(config: dict) -> None:
    """Execute crawl: search → fetch → export."""
    from pathlib import Path

    output_dir = Path(config["settings"]["output_dir"])
    logger = setup_logger(output_dir / "crawl.log")

    logger.info("Crawl command started")
    logger.info("Query: %s", _format_query(config))

    print("\n=== PKULaw 采集 ===")
    print("\n检索条件：")
    for node in config["fieldNodes"]:
        field = node["field"]
        if "value" in node:
            print(f"  {field}: {node['value']}")
        elif "values" in node:
            print(f"  {field}: {', '.join(node['values'])}")
        elif "range" in node:
            print(f"  {field}: {node['range'][0]} ~ {node['range'][1]}")

    # Phase 1 — Search
    print("\n[Phase 1/3] 搜索中...")
    pw, browser, context, page = launch_browser(
        browser_path=config["settings"].get("browser", "/usr/bin/chromium"),
        headless=config["settings"].get("headless", True),
    )
    try:
        token = authenticate(page)
        logger.info("Authenticated (%s...)", token[:30])
        print(f"认证成功 ({token[:30]}...)")
        search_results = run_search(config, page, token, output_dir, logger)
    finally:
        close_browser(pw, browser)

    print(f"搜索完成，找到 {len(search_results)} 条结果")

    # Phase 2 — Fetch
    print("\n[Phase 2/3] 采集全文...")
    fetched = run_fetch(config, output_dir, logger)
    print(f"采集完成，共 {len(fetched)} 条")

    # Phase 3 — Export
    print("\n[Phase 3/3] 导出中...")
    formats = config["settings"].get("format", ["json"])
    if "json" in formats:
        export_json(fetched, output_dir / "pkulaw_cases.json")
        logger.info("Exported JSON")
    if "excel" in formats or "xlsx" in formats:
        export_excel(fetched, output_dir / "pkulaw_cases.xlsx")
        logger.info("Exported Excel")
    if "csv" in formats:
        export_csv(fetched, output_dir / "pkulaw_cases.csv")
        logger.info("Exported CSV")

    print(f"\n导出完成：{', '.join(formats)}")
    print(f"输出目录：{output_dir}\n")


def _print_estimate_report(result: dict, config: dict, elapsed: float) -> None:
    """Print the estimate report to stdout."""
    delay = config["settings"].get("delay", 0.5)
    total = result["total"]
    crawlable = result["crawlable"]
    coverage = (crawlable / total * 100) if total > 0 else 0
    groups = result["groups"]
    estimated_hours = groups * 10 * delay / 3600 if groups > 0 else 0

    print(f"数据库总量：{total:,} 篇")
    print(f"预计可爬取：{crawlable:,} / {total:,} ({coverage:.1f}%)")
    print(f"分组总数：{groups} 组")
    print(f"耗时预估：{estimated_hours:.1f} 小时（@{delay}s/请求）")
    print(f"估算用时：{elapsed:.1f} 秒")

    if result.get("children"):
        print("\n分区策略：")
        _print_partition_tree(result, indent=2)
    print()


def _print_partition_tree(node: dict, indent: int = 0) -> None:
    """Print partition tree recursively."""
    prefix = " " * indent
    if node.get("children") is not None:
        dim = node.get("dimension")
        dim_label = _format_dimension_label(dim) if dim else ""
        if dim_label:
            print(f"{prefix}按 {dim_label} 分区：")
        for child in node["children"]:
            label = child.get("label", "?")
            total = child.get("total", 0)
            crawlable = child.get("crawlable", 0)
            if child.get("children") is None:
                status = "✓" if crawlable >= total else f"{crawlable}/{total}"
                print(f"{prefix}  {label}: {total:,} → {status}")
            else:
                print(f"{prefix}  {label}: {total:,} → 需要进一步分区")
                _print_partition_tree(child, indent + 4)


def _format_dimension_label(dimension: str) -> str:
    """Return a Chinese label for a dimension."""
    labels = {
        "LastInstanceDate": "年份",
        "CaseGrade": "参照级别",
        "CategoryNew": "案由分类",
        "CourtGrade": "法院级别",
        "TrialStep": "审理程序",
        "DocumentAttr": "文书类型",
        "TrialStepCount": "终审结果",
    }
    return labels.get(dimension, dimension)


def cmd_status(output_dir: Path | None = None) -> None:
    """Show crawl status from existing data files."""
    import json
    import subprocess
    from datetime import datetime

    from src.config import FIELD_DEFINITIONS
    from src.query import reverse_lookup

    if output_dir is None:
        output_dir = Path("output")
    else:
        output_dir = Path(output_dir)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n=== PKULaw 爬取状态 ===")
    print(f"时间：{now}")

    if not output_dir.exists():
        print("\n无活跃任务\n")
        return

    # Search results
    cache_file = output_dir / "search_results.json"
    total_unique = 0
    if cache_file.exists():
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            # Old format: flat list of results
            total_unique = len(raw)
            print(f"\n搜索缓存：{total_unique:,} 条")
        elif isinstance(raw, dict):
            total_unique = raw.get("total_unique", len(raw.get("results", [])))
            status_mark = "✓" if raw.get("results") is not None else "..."
            print(f"\n搜索缓存：{total_unique:,} 条（已完成 {status_mark}）")

            # Show query conditions
            query = raw.get("query", {})
            if isinstance(query, dict) and query.get("fieldNodes"):
                print("\n检索条件：")
                for node in query["fieldNodes"]:
                    field = node.get("field", "")
                    label = FIELD_DEFINITIONS.get(field, {}).get("show_text", field)
                    if "value" in node:
                        print(f"  {label}：{node['value']}")
                    elif "values" in node:
                        names = []
                        for v in node["values"]:
                            name = reverse_lookup(field, v) or v
                            names.append(name)
                        print(f"  {label}：{', '.join(names)}")
    else:
        print("\n搜索缓存：无")

    # Progress
    progress_file = output_dir / "progress.json"
    fetched_count = 0
    if progress_file.exists():
        data = json.loads(progress_file.read_text(encoding="utf-8"))
        fetched_count = len(data.get("fetched_gids", []))

    if total_unique > 0 and fetched_count > 0:
        pct = fetched_count / total_unique * 100
        print(f"\n已采集：{fetched_count:,} / {total_unique:,} ({pct:.1f}%)")
    elif fetched_count > 0:
        print(f"\n已采集：{fetched_count:,}")

    # Results file
    results_file = output_dir / "pkulaw_cases.json"
    if results_file.exists():
        cases = json.loads(results_file.read_text(encoding="utf-8"))
        total_cases = len(cases)
        valid_cases = sum(1 for c in cases if len(c.get("full_text", "")) > 500)
        size_mb = results_file.stat().st_size / 1024 / 1024

        if total_cases > 0:
            valid_pct = valid_cases / total_cases * 100
            remaining = total_unique - fetched_count
            print(f"\n有效数据：{valid_cases:,} 条 (>500字, {valid_pct:.1f}%)")
            print(f"剩余：{remaining:,} 条")
            print(f"输出文件：{total_cases:,} 条 ({results_file}, {size_mb:.1f}MB)")
        else:
            print(f"\n输出文件：0 条 ({results_file})")

    # Process detection
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pkulaw_lines = [
            line
            for line in result.stdout.strip().split("\n")
            if "pkulaw" in line and "grep" not in line
        ]
        if pkulaw_lines:
            parts = pkulaw_lines[0].split()
            pid = parts[1] if len(parts) > 1 else "?"
            rss_kb = int(parts[5]) if len(parts) > 5 else 0
            rss_mb = rss_kb / 1024
            print(f"\n进程：运行中 (PID: {pid}, 内存: {rss_mb:.0f}MB)")
        else:
            print("\n进程：已停止")
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        print("\n进程：已停止")

    # Log
    log_file = output_dir / "crawl.log"
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        last_lines = lines[-20:]
        print(f"\n最近日志（{log_file} 最后 {len(last_lines)} 行）：")
        for line in last_lines:
            print(f"  {line}")

    print()


def _format_query(config: dict) -> str:
    """Format field nodes as a readable string."""
    parts = []
    for node in config["fieldNodes"]:
        field = node["field"]
        if "value" in node:
            parts.append(f"{field}={node['value']}")
        elif "values" in node:
            parts.append(f"{field}={','.join(node['values'])}")
        elif "range" in node:
            parts.append(f"{field}={node['range'][0]}~{node['range'][1]}")
    return " | ".join(parts)


def main() -> None:
    """CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "status":
            cmd_status(output_dir=args.output_dir)
        elif args.command in ("estimate", "crawl"):
            config = build_search_config(args)
            if args.command == "estimate":
                cmd_estimate(config)
            else:
                cmd_crawl(config)
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
