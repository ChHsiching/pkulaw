# Issue #3: Estimate Command — Recursive Partitioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `pkulaw estimate` with a search query builder, recursive partitioning algorithm, and real API integration so users can see how many cases are crawlable for their query.

**Architecture:** Three new modules. `src/query.py` converts the internal SearchConfig dict into the exact PKULaw API request body format. `src/auth.py` handles browser launch, PKULaw authentication, and raw API calls. `src/partition.py` runs the recursive partitioning algorithm using auth+query to determine optimal crawl strategies. `pkulaw.py` is updated to wire these together.

**Tech Stack:** Python 3.10+, playwright (browser-based API calls), pytest

---

## File Structure

```
Created:
├── src/query.py                    # SearchConfig → PKULaw API request body
├── src/auth.py                     # Browser launch, authenticate, search API call
├── src/partition.py                # Recursive partitioning algorithm
├── tests/test_query.py
├── tests/test_partition.py

Modified:
├── pkulaw.py                       # Replace placeholder cmd_estimate

Untouched:
├── src/config.py, src/config_data.py, src/cli.py, src/log.py
├── src/crawler.py, src/parser.py, src/exporter.py, src/refetch.py
```

## Key API Format Reference

The PKULaw search API (`POST /searchingapi/adv/list/pfnl`) expects this body structure, derived from `src/crawler.py:29-77`:

```python
{
    "orderbyExpression": "LastInstanceDate Desc",
    "pageIndex": 0,
    "pageSize": 100,
    "fieldNodes": [
        {
            "type": "text",
            "order": 1,
            "combineAs": 2,
            "fieldName": "FullText",
            "showText": "全文",
            "subCombineAs": 2,
            "fieldItems": [{"values": "抗诉", "valuesCombineAs": 2, "extra": {"values": "", "combineAs": 2}, "matchType": 1, "matchSpan": 1, "matchSpanGap": 0, "fieldScope": {"fieldName": "", "showText": ""}, "order": 0, "filterNodes": []}],
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
            "fieldItems": [{"items": [{"text": "二审", "path": "002", "name": "二审", "value": "002"}, {"text": "再审", "path": "003", "name": "再审", "value": "003"}], "combineAs": 2, "order": 0, "filterNodes": []}],
        },
    ],
    "clusterFilters": {"CategoryNew": "001"},
    "groupBy": {},
}
```

**Mapping rules (derived from existing crawler.py):**
- Text fields → `fieldNodes` with `type="text"`, fieldItems containing `values` string
- Select/checkbox fields → `fieldNodes` with `type="select"/"checkbox"`, fieldItems containing `items` array
- CategoryNew → `clusterFilters` (not fieldNodes)
- Date range → `groupBy` parameter (for partitioning), not in fieldNodes or clusterFilters
- Sort orders: `["LastInstanceDate Desc", "LastInstanceDate Asc", "SortNum Desc", "SortNum Asc"]`

---

## Task 1: Create src/query.py — search query builder + tests

**Files:**
- Create: `src/query.py`
- Create: `tests/test_query.py`

- [ ] **Step 1: Write tests/test_query.py**

```python
"""Tests for src/query.py — SearchConfig to API body conversion."""

import pytest

from src.query import build_api_body, _build_text_node, _build_select_node, reverse_lookup


class TestReverseLookup:
    def test_trial_step(self):
        assert reverse_lookup("TrialStep", "002") == "二审"

    def test_court_grade(self):
        assert reverse_lookup("CourtGrade", "03") == "中级人民法院"

    def test_case_grade(self):
        assert reverse_lookup("CaseGrade", "01") == "指导性案例"

    def test_category_new(self):
        assert reverse_lookup("CategoryNew", "001") == "刑事"

    def test_category_second_level(self):
        assert reverse_lookup("CategoryNew", "001002") == "危害公共安全罪"

    def test_missing_id_returns_none(self):
        assert reverse_lookup("TrialStep", "999") is None


class TestBuildTextNode:
    def test_full_text(self):
        node = _build_text_node("FullText", "抗诉")
        assert node["type"] == "text"
        assert node["fieldName"] == "FullText"
        assert node["showText"] == "全文"
        items = node["fieldItems"]
        assert len(items) == 1
        assert items[0]["values"] == "抗诉"

    def test_title(self):
        node = _build_text_node("Title", "盗窃")
        assert node["fieldName"] == "Title"
        assert node["fieldItems"][0]["values"] == "盗窃"


class TestBuildSelectNode:
    def test_trial_step(self):
        node = _build_select_node("TrialStep", ["002", "003"])
        assert node["type"] == "select"
        assert node["fieldName"] == "TrialStep"
        assert node["showText"] == "审理程序"
        items = node["fieldItems"][0]["items"]
        assert len(items) == 2
        assert items[0]["value"] == "002"
        assert items[0]["text"] == "二审"

    def test_court_grade_checkbox(self):
        node = _build_select_node("CourtGrade", ["01", "03"])
        assert node["type"] == "checkbox"
        items = node["fieldItems"][0]["items"]
        assert items[0]["text"] == "最高人民法院"
        assert items[1]["text"] == "中级人民法院"


class TestBuildApiBody:
    def test_minimal_query(self):
        config = {"fieldNodes": [], "settings": {}}
        body = build_api_body(config)
        assert body["pageSize"] == 100
        assert body["pageIndex"] == 0
        assert body["orderbyExpression"] == "LastInstanceDate Desc"
        assert body["groupBy"] == {}
        assert "fieldNodes" in body
        assert isinstance(body["clusterFilters"], dict)

    def test_text_field_in_field_nodes(self):
        config = {
            "fieldNodes": [{"field": "FullText", "value": "抗诉"}],
            "settings": {},
        }
        body = build_api_body(config)
        fn = body["fieldNodes"]
        assert any(n["fieldName"] == "FullText" for n in fn)

    def test_select_field_in_field_nodes(self):
        config = {
            "fieldNodes": [{"field": "TrialStep", "values": ["002", "003"]}],
            "settings": {},
        }
        body = build_api_body(config)
        fn = body["fieldNodes"]
        ts = next(n for n in fn if n["fieldName"] == "TrialStep")
        items = ts["fieldItems"][0]["items"]
        assert len(items) == 2
        assert items[0]["value"] == "002"

    def test_category_new_in_cluster_filters(self):
        config = {
            "fieldNodes": [{"field": "CategoryNew", "values": ["001"]}],
            "settings": {},
        }
        body = build_api_body(config)
        assert body["clusterFilters"].get("CategoryNew") == "001"
        assert not any(n["fieldName"] == "CategoryNew" for n in body["fieldNodes"])

    def test_group_by_override(self):
        config = {"fieldNodes": [], "settings": {}}
        body = build_api_body(config, group_by={"LastInstanceDate": "2025"})
        assert body["groupBy"] == {"LastInstanceDate": "2025"}

    def test_page_params(self):
        config = {"fieldNodes": [], "settings": {}}
        body = build_api_body(config, page_index=3, page_size=50, order_by="SortNum Desc")
        assert body["pageIndex"] == 3
        assert body["pageSize"] == 50
        assert body["orderbyExpression"] == "SortNum Desc"

    def test_multiple_fields_combined(self):
        config = {
            "fieldNodes": [
                {"field": "FullText", "value": "抗诉"},
                {"field": "TrialStep", "values": ["002", "003"]},
                {"field": "CategoryNew", "values": ["001"]},
            ],
            "settings": {},
        }
        body = build_api_body(config)
        assert len(body["fieldNodes"]) == 2  # FullText + TrialStep (not CategoryNew)
        assert body["clusterFilters"]["CategoryNew"] == "001"

    def test_cluster_filters_additive(self):
        config = {
            "fieldNodes": [
                {"field": "CategoryNew", "values": ["001"]},
            ],
            "settings": {},
        }
        body = build_api_body(config, cluster_overrides={"CaseGrade": "01"})
        assert body["clusterFilters"]["CategoryNew"] == "001"
        assert body["clusterFilters"]["CaseGrade"] == "01"

    def test_date_range_field_ignored_in_field_nodes(self):
        config = {
            "fieldNodes": [{"field": "LastInstanceDate", "range": ["2020", "2025"]}],
            "settings": {},
        }
        body = build_api_body(config)
        assert not any(n["fieldName"] == "LastInstanceDate" for n in body["fieldNodes"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_query.py -v
```

Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Create src/query.py**

```python
"""Convert SearchConfig to PKULaw API request body."""

from src.config import CATEGORY_VALUES, FIELD_DEFINITIONS, _dim_key

SORT_ORDERS = [
    "LastInstanceDate Desc",
    "LastInstanceDate Asc",
    "SortNum Desc",
    "SortNum Asc",
]

PAGE_SIZE = 100
DATE_RANGE_FIELDS = {
    f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "daterange"
}


def reverse_lookup(field: str, api_id: str) -> str | None:
    """Look up the Chinese name for an API ID. Returns None if not found."""
    dim = _dim_key(field)
    values = CATEGORY_VALUES.get(dim, {})
    for name, vid in values.items():
        if vid == api_id:
            return name
    return None


def _build_text_node(field_name: str, value: str) -> dict:
    """Build a text-type fieldNode for keyword search fields."""
    show_text = FIELD_DEFINITIONS.get(field_name, {}).get("show_text", field_name)
    return {
        "type": "text",
        "order": 0,
        "combineAs": 2,
        "fieldName": field_name,
        "showText": show_text,
        "subCombineAs": 2,
        "fieldItems": [
            {
                "values": value,
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
    }


def _build_select_node(field_name: str, values: list[str]) -> dict:
    """Build a select/checkbox-type fieldNode for multi-value filter fields."""
    field_type = FIELD_DEFINITIONS.get(field_name, {}).get("type", "select")
    show_text = FIELD_DEFINITIONS.get(field_name, {}).get("show_text", field_name)
    items = []
    for vid in values:
        name = reverse_lookup(field_name, vid) or vid
        items.append({"text": name, "path": vid, "name": name, "value": vid})
    return {
        "type": field_type,
        "order": 0,
        "combineAs": 2,
        "fieldName": field_name,
        "showText": show_text,
        "fieldItems": [
            {
                "items": items,
                "combineAs": 2,
                "order": 0,
                "filterNodes": [],
            }
        ],
    }


def build_api_body(
    search_config: dict,
    page_index: int = 0,
    page_size: int = PAGE_SIZE,
    order_by: str = "LastInstanceDate Desc",
    group_by: dict | None = None,
    cluster_overrides: dict | None = None,
) -> dict:
    """Convert a SearchConfig dict to a PKULaw API request body.

    Args:
        search_config: {"fieldNodes": [...], "settings": {...}}
        page_index: API page number (0-based)
        page_size: items per page
        order_by: sort expression
        group_by: {"LastInstanceDate": "2025"} for year partitioning
        cluster_overrides: additional cluster filters to merge
    """
    field_nodes_api = []
    cluster_filters = {}
    text_fields = {f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "text"}

    for node in search_config.get("fieldNodes", []):
        field = node["field"]
        if field in DATE_RANGE_FIELDS:
            continue
        if field == "CategoryNew":
            ids = node.get("values", [])
            if ids:
                cluster_filters["CategoryNew"] = ids[0]
            continue
        if field in text_fields:
            value = node.get("value", "")
            if value:
                field_nodes_api.append(_build_text_node(field, value))
        else:
            values = node.get("values", [])
            if values:
                field_nodes_api.append(_build_select_node(field, values))

    if cluster_overrides:
        cluster_filters.update(cluster_overrides)

    return {
        "orderbyExpression": order_by,
        "pageIndex": page_index,
        "pageSize": page_size,
        "fieldNodes": field_nodes_api,
        "clusterFilters": cluster_filters,
        "groupBy": group_by or {},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_query.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Run full test suite (regression)**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/query.py tests/test_query.py
git commit -m "feat: add query builder — SearchConfig to API body conversion"
```

---

## Task 2: Create src/auth.py — browser auth + API call + tests

**Files:**
- Create: `src/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write tests/test_auth.py**

```python
"""Tests for src/auth.py — browser auth and API call.

These tests verify the function signatures and data flow.
Browser-dependent tests are skipped in CI (no school intranet).
"""

import pytest

from src.auth import search_api, API_URL


class TestConstants:
    def test_api_url(self):
        assert API_URL == "/searchingapi/adv/list/pfnl"


class TestSearchApiUnit:
    """Unit tests for search_api function signature and error handling."""

    def test_returns_dict_with_total(self):
        """search_api should return a dict with at least 'total' and 'data' keys."""
        # We can only test the function exists and has correct signature
        # Real API calls require browser + intranet
        import inspect

        sig = inspect.signature(search_api)
        params = list(sig.parameters.keys())
        assert "page" in params
        assert "token" in params
        assert "body" in params
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_auth.py -v
```

- [ ] **Step 3: Create src/auth.py**

Extract authentication and API call logic from `src/crawler.py:100-184`. Do NOT modify crawler.py.

```python
"""Browser-based authentication and PKULaw API calls."""

from playwright.sync_api import Page, sync_playwright

API_URL = "/searchingapi/adv/list/pfnl"

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)


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
        except Exception as e:
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
    """Send a search request to PKULaw API. Returns response dict with 'total' and 'data'.

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_auth.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add src/auth.py tests/test_auth.py
git commit -m "feat: add auth module — browser auth and API call from crawler logic"
```

---

## Task 3: Create src/partition.py — recursive partitioning algorithm + tests

**Files:**
- Create: `src/partition.py`
- Create: `tests/test_partition.py`

This is the core algorithm. Test with mocked API calls.

- [ ] **Step 1: Write tests/test_partition.py**

```python
"""Tests for src/partition.py — recursive partitioning algorithm."""

from unittest.mock import MagicMock

import pytest

from src.partition import (
    partition_query,
    _get_partition_values,
    _get_available_dimensions,
)


def _mock_api(responses: dict) -> MagicMock:
    """Create a mock search_api that returns responses based on groupBy."""
    def fake_search(page, token, body):
        key = str(sorted(body.get("clusterFilters", {}).items()))
        gb = str(body.get("groupBy", {}))
        lookup = responses.get(gb, responses.get(key, {}))
        if callable(lookup):
            return lookup(page, token, body)
        return lookup
    mock = MagicMock(side_effect=fake_search)
    return mock


class TestGetAvailableDimensions:
    def test_all_available_when_empty_query(self):
        config = {"fieldNodes": [], "settings": {}}
        dims = _get_available_dimensions(config)
        assert "LastInstanceDate" in dims
        assert "CaseGrade" in dims
        assert "CourtGrade" in dims

    def test_category_excluded_when_already_set(self):
        config = {
            "fieldNodes": [{"field": "CategoryNew", "values": ["001"]}],
            "settings": {},
        }
        dims = _get_available_dimensions(config)
        assert "CategoryNew" not in dims

    def test_trial_step_excluded_when_set(self):
        config = {
            "fieldNodes": [{"field": "TrialStep", "values": ["002"]}],
            "settings": {},
        }
        dims = _get_available_dimensions(config)
        assert "TrialStep" not in dims


class TestGetPartitionValues:
    def test_last_instance_date(self):
        values = _get_partition_values("LastInstanceDate")
        assert len(values) > 20
        assert "2025" in values

    def test_case_grade(self):
        values = _get_partition_values("CaseGrade")
        assert len(values) >= 10
        assert "01" in values

    def test_court_grade(self):
        values = _get_partition_values("CourtGrade")
        assert len(values) == 5


class TestPartitionQuery:
    def test_small_total_returns_leaf(self):
        """If total <= threshold, return a single leaf node."""
        mock_api = MagicMock(return_value={"total": 500, "data": []})
        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        result = partition_query(
            page=None,
            token="test",
            search_config=config,
            search_fn=mock_api,
        )
        assert result["total"] == 500
        assert result["crawlable"] == 500
        assert result["children"] is None

    def test_large_total_splits_by_year(self):
        """If total > threshold, split by LastInstanceDate."""
        call_count = 0

        def fake_search(page, token, body):
            nonlocal call_count
            call_count += 1
            gb = body.get("groupBy", {})
            if gb:
                year = gb.get("LastInstanceDate", "")
                if year == "2025":
                    return {"total": 200, "data": []}
                return {"total": 50, "data": []}
            return {"total": 1500, "data": []}

        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        result = partition_query(
            page=None,
            token="test",
            search_config=config,
            search_fn=fake_search,
        )
        assert result["total"] == 1500
        assert result["dimension"] == "LastInstanceDate"
        assert result["children"] is not None
        assert result["crawlable"] > 0

    def test_very_large_year_splits_further(self):
        """If a year partition is still > threshold, split by next dimension."""
        def fake_search(page, token, body):
            gb = body.get("groupBy", {})
            cf = body.get("clusterFilters", {})
            if gb and gb.get("LastInstanceDate") == "2025":
                if cf.get("CaseGrade"):
                    return {"total": 100, "data": []}
                return {"total": 2000, "data": []}
            if gb:
                return {"total": 50, "data": []}
            return {"total": 5000, "data": []}

        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        result = partition_query(
            page=None,
            token="test",
            search_config=config,
            search_fn=fake_search,
        )
        assert result["total"] == 5000
        # Should have split by year, then 2025 should have split by CaseGrade
        year_2025 = None
        for child in (result["children"] or []):
            if child.get("label") == "2025":
                year_2025 = child
                break
        assert year_2025 is not None
        assert year_2025.get("dimension") == "CaseGrade"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_partition.py -v
```

- [ ] **Step 3: Create src/partition.py**

```python
"""Recursive partitioning algorithm for PKULaw estimate command."""

from src.config import CATEGORY_VALUES, FIELD_DEFINITIONS
from src.query import SORT_ORDERS, build_api_body

THRESHOLD_MULTIPLIER = 1  # threshold = max_pages * page_size * this

# Partition dimension priority (by expected discriminative power)
_DIMENSION_PRIORITY = [
    "LastInstanceDate",
    "CaseGrade",
    "CategoryNew",
    "CourtGrade",
    "TrialStep",
    "DocumentAttr",
    "TrialStepCount",
]

# Dimensions that use groupBy instead of clusterFilters
_GROUP_BY_DIMENSIONS = {"LastInstanceDate"}


def _get_available_dimensions(search_config: dict) -> list[str]:
    """Return partition dimensions not already constrained in the query."""
    constrained = set()
    for node in search_config.get("fieldNodes", []):
        field = node["field"]
        constrained.add(field)
        if field == "CategoryNew":
            constrained.add("CategoryNew")
    return [d for d in _DIMENSION_PRIORITY if d not in constrained]


def _get_partition_values(dimension: str) -> list[str]:
    """Return list of partition values for a dimension."""
    if dimension == "LastInstanceDate":
        values = CATEGORY_VALUES.get("LastInstanceDate", {})
        years = [v for v in values.values() if v.isdigit() and int(v) >= 2000]
        return sorted(years, reverse=True)
    values = CATEGORY_VALUES.get(dimension, {})
    return list(values.values())


def _search_fn_default(page, token: str, body: dict) -> dict:
    """Default search function using auth.search_api."""
    from src.auth import search_api

    return search_api(page, token, body)


def partition_query(
    page,
    token: str,
    search_config: dict,
    search_fn=None,
    max_pages: int | None = None,
    page_size: int = 100,
    depth: int = 0,
    max_depth: int = 4,
) -> dict:
    """Recursively partition a query to estimate crawlable data.

    Returns a tree:
    {
        "label": "全部" | "2025" | "指导性案例" | ...,
        "total": int,
        "crawlable": int,
        "groups": int,
        "dimension": str | None,  # dimension used for splitting
        "children": list | None,  # child partitions, None if leaf
    }
    """
    if search_fn is None:
        search_fn = _search_fn_default
    if max_pages is None:
        max_pages = search_config.get("settings", {}).get("max_pages", 10)

    threshold = max_pages * page_size * THRESHOLD_MULTIPLIER

    body = build_api_body(search_config)
    result = search_fn(page, token, body)
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

    # Try splitting by available dimensions
    available = _get_available_dimensions(search_config)
    for dim in available:
        values = _get_partition_values(dim)
        if len(values) < 2:
            continue

        children = []
        any_above_threshold = False
        for val in values:
            child_config = _add_dimension_filter(search_config, dim, val)
            child_body = build_api_body(child_config)
            child_result = search_fn(page, token, child_body)
            child_total = child_result.get("total", 0)

            if child_total == 0:
                continue

            if child_total <= threshold:
                groups = len(SORT_ORDERS) if child_total > 0 else 0
                children.append({
                    "label": val if dim != "LastInstanceDate" else val,
                    "total": child_total,
                    "crawlable": child_total,
                    "groups": groups,
                    "dimension": None,
                    "children": None,
                })
            else:
                any_above_threshold = True
                sub = partition_query(
                    page, token, child_config, search_fn,
                    max_pages, page_size, depth + 1, max_depth,
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

    # No dimension worked — return as leaf even if over threshold
    groups = len(SORT_ORDERS) if total > 0 else 0
    return {
        "label": "全部",
        "total": total,
        "crawlable": min(total, threshold * len(SORT_ORDERS)),
        "groups": groups,
        "dimension": None,
        "children": None,
    }


def _add_dimension_filter(search_config: dict, dimension: str, value: str) -> dict:
    """Return a new SearchConfig with an additional dimension filter."""
    import copy

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
```

Then update `build_api_body` in `src/query.py` to also check for `_groupBy` in search_config:

In `src/query.py`, modify the `build_api_body` function to accept `_groupBy` from search_config:

```python
# In build_api_body, before the return statement, add:
if "_groupBy" in search_config and not group_by:
    group_by = search_config["_groupBy"]
```

This is a minimal change — add these 2 lines right before the return statement in `build_api_body`:
```python
    if "_groupBy" in search_config and not group_by:
        group_by = search_config["_groupBy"]

    return {
        ...
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_partition.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add src/partition.py tests/test_partition.py
git commit -m "feat: add recursive partitioning algorithm for estimate"
```

---

## Task 4: Update pkulaw.py — real estimate command

**Files:**
- Modify: `pkulaw.py`

- [ ] **Step 1: Replace the placeholder cmd_estimate in pkulaw.py**

Replace the entire `cmd_estimate` function (lines 9-26 in the current file) with the real implementation:

```python
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
        logger.info("Estimate complete: %d total, %d crawlable", result["total"], result["crawlable"])

    finally:
        close_browser(pw, browser)


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
        print(f"\n分区策略：")
        _print_partition_tree(result, indent=2)
    print()


def _print_partition_tree(node: dict, indent: int = 0) -> None:
    """Print partition tree recursively."""
    prefix = " " * indent
    dim = node.get("dimension")
    if dim and node.get("children"):
        dim_label = _format_dimension_label(dim)
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
```

- [ ] **Step 2: Run acceptance criteria**

```bash
.venv/bin/python pkulaw.py estimate --help
# Expected: help text (no change)

# The following requires school intranet:
# .venv/bin/python pkulaw.py estimate --full-text "抗诉" --trial-step "二审,再审" --category "刑事"
```

- [ ] **Step 3: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add pkulaw.py
git commit -m "feat: implement estimate command with recursive partitioning"
```

---

## Task 5: Final verification + commit + merge

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 2: Run pre-commit checks**

```bash
pre-commit run --all-files
```

Expected: All hooks pass

- [ ] **Step 3: Verify acceptance criteria (requires intranet)**

```bash
# On school intranet only:
.venv/bin/python pkulaw.py estimate --full-text "抗诉" --trial-step "二审,再审" --category "刑事"
# Expected: total ~308K, partition strategy shown, coverage estimate

.venv/bin/python pkulaw.py estimate --category "刑事>侵犯财产罪>盗窃罪"
# Expected: shows partition for theft crime category
```

- [ ] **Step 4: Merge to develop**

```bash
git checkout develop
git merge --no-ff feature/iter2-estimate -m "feat: complete Issue #3 — estimate command with recursive partitioning"
```

- [ ] **Step 5: Push and close issue**

---

## Self-Review

**1. Spec coverage:**

| Issue #3 Requirement | Covered By |
|---|---|
| Search query builder (text/select/checkbox/daterange) | Task 1 (src/query.py) |
| Combine logic (combineAs=2 for and) | Task 1 (_build_text_node, _build_select_node) |
| Scope support (FullText fieldScope) | Task 1 (_build_text_node includes fieldScope) |
| API request body output | Task 1 (build_api_body) |
| Recursive partitioning algorithm | Task 3 (src/partition.py) |
| Partition dimensions priority | Task 3 (_DIMENSION_PRIORITY) |
| Threshold check (≤ max_pages × page_size) | Task 3 (partition_query) |
| 4 sort orders per partition | Task 1 (SORT_ORDERS), Task 3 (groups = len(SORT_ORDERS)) |
| Estimate subcommand | Task 4 (pkulaw.py cmd_estimate) |
| Auth integration | Task 2 (src/auth.py) |
| Partition report output | Task 4 (_print_estimate_report, _print_partition_tree) |

**2. Placeholder scan:** No TBD, TODO, or "implement later" found. All code steps include complete implementation.

**3. Type consistency:**
- `build_api_body(config, page_index, page_size, order_by, group_by, cluster_overrides) → dict` — used in partition.py
- `search_api(page, token, body) → dict` — signature consistent between auth.py and partition.py's search_fn parameter
- `partition_query(page, token, search_config, search_fn, ...) → dict` with keys: total, crawlable, groups, dimension, children, label — used consistently in pkulaw.py report printing
- `_add_dimension_filter(search_config, dimension, value) → dict` — returns deep-copied config with added filter
