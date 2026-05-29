"""PKULaw CLI crawler — entry point."""

import sys

from src.cli import build_search_config, create_parser
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
    """Execute crawl (placeholder)."""
    from pathlib import Path

    logger = setup_logger(Path(config["settings"]["output_dir"]) / "crawl.log")
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
    print("\n（采集功能将在 Phase 3 实现）\n")


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


def cmd_status() -> None:
    """Show crawl status from existing data files."""
    import json
    from pathlib import Path

    output_dir = Path("output")

    print("\n=== PKULaw 爬取状态 ===")

    if not output_dir.exists():
        print("\n无活跃任务（output/ 目录不存在）\n")
        return

    # Check for log file
    log_file = output_dir / "crawl.log"
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        print(f"\n最近日志 ({log_file}):")
        for line in lines[-20:]:
            print(f"  {line}")
    else:
        print("\n无日志文件")

    # Check for progress
    progress_file = output_dir / "progress.json"
    if progress_file.exists():
        data = json.loads(progress_file.read_text(encoding="utf-8"))
        fetched = data.get("fetched_gids", [])
        print(f"\n进度：已采集 {len(fetched)} 条")
    else:
        print("\n无进度文件")

    # Check for search cache
    cache_file = output_dir / "search_results.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            print(f"搜索缓存：{len(data)} 条")
        elif isinstance(data, dict):
            total = data.get("total_unique", len(data.get("results", [])))
            print(f"搜索缓存：{total} 条")

    # Check for results
    results_file = output_dir / "pkulaw_cases.json"
    if results_file.exists():
        data = json.loads(results_file.read_text(encoding="utf-8"))
        size_mb = results_file.stat().st_size / 1024 / 1024
        print(f"结果文件：{len(data)} 条 ({size_mb:.1f} MB)")

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
            cmd_status()
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
