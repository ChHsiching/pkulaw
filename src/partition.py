"""Recursive partitioning algorithm for PKULaw estimate command."""

import copy
import time

from src.auth import TokenContext, reauthenticate
from src.config import CATEGORY_VALUES
from src.query import build_api_body

SORT_ORDERS = [
    "LastInstanceDate Desc",
    "LastInstanceDate Asc",
    "SortNum Desc",
    "SortNum Asc",
]

_DIMENSION_PRIORITY = [
    "LastInstanceDate",
    "CaseGrade",
    "CategoryNew",
    "CourtGrade",
    "TrialStep",
    "DocumentAttr",
    "TrialStepCount",
]

_GROUP_BY_DIMENSIONS = {"LastInstanceDate"}


def _get_available_dimensions(search_config: dict) -> list[str]:
    """Return partition dimensions not already constrained in the query."""
    constrained = {node["field"] for node in search_config.get("fieldNodes", [])}
    constrained.update(search_config.get("_groupBy", {}).keys())
    return [d for d in _DIMENSION_PRIORITY if d not in constrained]


def _get_partition_values(dimension: str) -> list[str]:
    """Return list of partition values (API IDs) for a dimension."""
    values = CATEGORY_VALUES.get(dimension, {})
    if dimension == "LastInstanceDate":
        years = [v for v in values.values() if v.isdigit() and int(v) >= 2000]
        return sorted(years, reverse=True)
    if dimension == "CaseGrade":
        # Use only top-level IDs (length 2)
        return sorted({v for v in values.values() if len(v) == 2})
    return list(values.values())


def _add_dimension_filter(search_config: dict, dimension: str, value: str) -> dict:
    """Return a new SearchConfig with an additional dimension filter."""
    new_config = copy.deepcopy(search_config)

    if dimension in _GROUP_BY_DIMENSIONS:
        new_config.setdefault("_groupBy", {})[dimension] = value
    elif dimension == "CategoryNew":
        new_config["fieldNodes"] = [
            n for n in new_config.get("fieldNodes", []) if n["field"] != "CategoryNew"
        ]
        new_config["fieldNodes"].append({"field": "CategoryNew", "values": [value]})
    else:
        new_config["fieldNodes"].append({"field": dimension, "values": [value]})

    return new_config


def partition_query(
    page,
    ctx: TokenContext,
    search_config: dict,
    search_fn=None,
    max_pages: int | None = None,
    page_size: int = 100,
    depth: int = 0,
    max_depth: int = 4,
    _refresh_interval: float = 180.0,
    _last_refresh: float | None = None,
) -> dict:
    """Recursively partition a query to estimate crawlable data.

    Returns a tree:
    {
        "label": str,
        "total": int,
        "crawlable": int,
        "groups": int,
        "dimension": str | None,
        "children": list | None,
    }
    """
    if search_fn is None:
        from src.auth import search_api

        search_fn = search_api
    if max_pages is None:
        max_pages = search_config.get("settings", {}).get("max_pages", 10)

    if _last_refresh is None:
        _last_refresh = time.time()

    if (
        _refresh_interval > 0
        and page is not None
        and time.time() - _last_refresh > _refresh_interval
    ):
        ctx.token = reauthenticate(page)
        _last_refresh = time.time()

    threshold = max_pages * page_size

    body = build_api_body(search_config)
    result = search_fn(page, ctx, body)
    total = result.get("total", 0)

    if total <= threshold or depth >= max_depth:
        groups = len(SORT_ORDERS) if total > 0 else 0
        return {
            "label": "全部",
            "total": total,
            "crawlable": total,
            "groups": groups,
            "dimension": None,
            "children": None,
        }

    available = _get_available_dimensions(search_config)
    for dim in available:
        values = _get_partition_values(dim)
        if len(values) < 2:
            continue

        children = []
        for val in values:
            child_config = _add_dimension_filter(search_config, dim, val)
            child_body = build_api_body(child_config)
            child_result = search_fn(page, ctx, child_body)
            child_total = child_result.get("total", 0)

            if child_total == 0:
                continue

            if child_total <= threshold:
                groups = len(SORT_ORDERS) if child_total > 0 else 0
                children.append(
                    {
                        "label": val,
                        "total": child_total,
                        "crawlable": child_total,
                        "groups": groups,
                        "dimension": None,
                        "children": None,
                    }
                )
            else:
                sub = partition_query(
                    page,
                    ctx,
                    child_config,
                    search_fn,
                    max_pages,
                    page_size,
                    depth + 1,
                    max_depth,
                    _refresh_interval,
                    _last_refresh,
                )
                sub["label"] = val
                children.append(sub)

        if children:
            total_crawlable = sum(c["crawlable"] for c in children)
            total_groups = sum(c["groups"] for c in children)
            return {
                "label": "全部",
                "total": total,
                "crawlable": total_crawlable,
                "groups": total_groups,
                "dimension": dim,
                "children": children,
            }

    groups = len(SORT_ORDERS) if total > 0 else 0
    return {
        "label": "全部",
        "total": total,
        "crawlable": min(total, threshold * len(SORT_ORDERS)),
        "groups": groups,
        "dimension": None,
        "children": None,
    }
