"""CLI argument parsing and SearchConfig builder for PKULaw crawler."""

import argparse
import json
from pathlib import Path

from src.config import (
    CLI_TO_FIELD_MAP,
    FIELD_CLI_NAMES,
    FIELD_DEFINITIONS,
    resolve_value,
    resolve_values,
)

_TEXT_FIELDS = {f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "text"}
_DATE_RANGE_FIELDS = {
    f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "daterange"
}


def _add_search_args(parser: argparse.ArgumentParser) -> None:
    """Add shared search/field arguments to a subparser."""
    for cli_flag, field_name in CLI_TO_FIELD_MAP.items():
        attr = FIELD_CLI_NAMES[field_name]
        if field_name in _TEXT_FIELDS:
            parser.add_argument(
                cli_flag, dest=attr, default=None, help=f"Filter by {field_name}"
            )
        elif field_name in _DATE_RANGE_FIELDS:
            parser.add_argument(
                cli_flag,
                dest=attr,
                default=None,
                help=f"Date range for {field_name} (e.g. 2020-2025)",
            )
        else:
            parser.add_argument(
                cli_flag,
                dest=attr,
                default=None,
                help=f"Comma-separated values for {field_name}",
            )

    parser.add_argument("--query", default=None, help="Path to JSON query file")
    parser.add_argument(
        "--delay", type=float, default=0.5, help="Delay between requests in seconds"
    )
    parser.add_argument(
        "--max-pages", type=int, default=10, help="Maximum pages to crawl"
    )
    parser.add_argument(
        "--format", default="json,xlsx", help="Output format(s), comma-separated"
    )
    parser.add_argument("--output-dir", default="output", help="Output directory")


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser with subcommands."""
    main = argparse.ArgumentParser(prog="pkulaw", description="PKULaw case crawler")
    sub = main.add_subparsers(dest="command")

    # estimate subcommand
    est = sub.add_parser("estimate", help="Estimate result count without crawling")
    _add_search_args(est)

    # crawl subcommand
    crawl = sub.add_parser("crawl", help="Crawl cases matching search criteria")
    _add_search_args(crawl)
    crawl.add_argument(
        "--chunk-size", type=int, default=500, help="Records per output chunk"
    )
    crawl.add_argument(
        "--max-cases",
        type=int,
        default=0,
        help="Stop after fetching N total cases (0=unlimited)",
    )
    crawl.add_argument(
        "--no-headless",
        action="store_true",
        default=False,
        help="Show browser window (for solving CAPTCHAs interactively)",
    )

    # status subcommand
    status = sub.add_parser("status", help="Show crawl status")
    status.add_argument("--output-dir", default="output", help="Output directory")

    return main


def _set_field_node(nodes: list[dict], new_node: dict) -> None:
    """Replace existing node by field name, or append if not present."""
    field = new_node["field"]
    for i, n in enumerate(nodes):
        if n["field"] == field:
            nodes[i] = new_node
            return
    nodes.append(new_node)


def _build_field_node_from_cli(field_name: str, raw_value: str) -> dict:
    """Convert a single CLI argument value into a fieldNode dict."""
    if field_name in _TEXT_FIELDS:
        return {"field": field_name, "value": raw_value}

    if field_name in _DATE_RANGE_FIELDS:
        parts = raw_value.split("-", 1)
        return {"field": field_name, "range": parts}

    resolved = resolve_values(field_name, raw_value)
    return {"field": field_name, "values": resolved}


def _resolve_json_field_node(raw: dict) -> dict:
    """Resolve a fieldNode loaded from JSON, resolving Chinese names to IDs."""
    field = raw["field"]

    # Text field: pass through as-is
    if field in _TEXT_FIELDS:
        return {"field": field, "value": raw["value"]}

    # Date range: pass through as-is
    if "range" in raw:
        return {"field": field, "range": raw["range"]}

    # Multi-value field with potential children (hierarchical)
    if "children" in raw:
        values = [resolve_value(field, v) for v in raw["values"]]
        parent_to_children = raw["children"]
        resolved_children: dict[str, list[str]] = {}
        for parent_name, child_names in parent_to_children.items():
            parent_id = resolve_value(field, parent_name)
            child_ids = [
                resolve_value(field, f"{parent_name}>{c}") for c in child_names
            ]
            resolved_children[parent_id] = child_ids
        return {"field": field, "values": values, "children": resolved_children}

    # Multi-value field (plain select/checkbox/pickselect)
    if "values" in raw:
        values = [resolve_value(field, v) for v in raw["values"]]
        return {"field": field, "values": values}

    # Single value (shouldn't normally occur in JSON, but handle it)
    if "value" in raw:
        return {"field": field, "value": raw["value"]}

    return raw


def build_search_config(args: argparse.Namespace) -> dict:
    """Convert parsed CLI args (+ optional JSON file) into a unified search config."""
    nodes: list[dict] = []
    settings: dict = {}

    # Load JSON query file if provided
    if args.query:
        data = json.loads(Path(args.query).read_text(encoding="utf-8"))
        for raw_node in data.get("fieldNodes", []):
            resolved = _resolve_json_field_node(raw_node)
            nodes.append(resolved)
        settings.update(data.get("settings", {}))

    # CLI flags override JSON values
    for cli_flag, field_name in CLI_TO_FIELD_MAP.items():
        attr = FIELD_CLI_NAMES[field_name]
        raw = getattr(args, attr, None)
        if raw is not None:
            node = _build_field_node_from_cli(field_name, raw)
            _set_field_node(nodes, node)

    # Build settings: JSON values first, then CLI defaults fill gaps
    _SETTINGS_DEFAULTS = {
        "delay": 0.5,
        "max_pages": 10,
        "format": ["json", "xlsx"],
        "output_dir": "output",
        "max_cases": 0,
    }

    # When no JSON query file, CLI defaults apply directly
    # When JSON query file IS present, JSON settings take priority over CLI defaults
    if not args.query:
        settings["delay"] = args.delay
        settings["max_pages"] = args.max_pages
        settings["format"] = [f.strip() for f in args.format.split(",")]
        settings["output_dir"] = args.output_dir
        settings["max_cases"] = getattr(args, "max_cases", 0)
        settings["headless"] = not getattr(args, "no_headless", False)
    else:
        # JSON settings already loaded above; only override if CLI explicitly differs
        settings.setdefault("delay", args.delay)
        settings.setdefault("max_pages", args.max_pages)
        settings.setdefault("format", [f.strip() for f in args.format.split(",")])
        settings.setdefault("output_dir", args.output_dir)
        settings.setdefault("max_cases", getattr(args, "max_cases", 0))

    # Fill any remaining gaps with hardcoded defaults
    for key, val in _SETTINGS_DEFAULTS.items():
        settings.setdefault(key, val)

    return {"fieldNodes": nodes, "settings": settings}
