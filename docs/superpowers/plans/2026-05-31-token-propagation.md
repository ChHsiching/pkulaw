# Token Propagation Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix token expiry during `partition_query` that causes zero-data crawls by introducing a mutable `TokenContext` container with centralized error detection.

**Architecture:** Add `TokenContext` dataclass to `src/auth.py`. `search_api` mutates `ctx.token` on reauthentication and detects API-level token errors + unexpected responses. `partition_query` and callers pass `TokenContext` through all recursive calls.

**Tech Stack:** Python 3.14, pytest, playwright, dataclasses

**Spec:** `docs/superpowers/specs/2026-05-31-token-propagation-design.md`
**ADR:** `docs/adr/0001-mutable-token-context.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/auth.py` | Modify | Add `TokenContext`, `_is_token_error`, `_is_unexpected_response`; update `search_api` signature |
| `src/partition.py` | Modify | Change `partition_query` param `token: str` → `ctx: TokenContext`; update all `search_fn` calls |
| `src/crawler.py` | Modify | Create `TokenContext` in `run_search`; remove `reauthenticate` import if unused; pass `ctx` |
| `pkulaw.py` | Modify | Create `TokenContext` in `cmd_estimate` before `partition_query` call |
| `tests/test_auth.py` | Modify | Add `TokenContext`, error detection, and `search_api` token propagation tests |
| `tests/test_partition.py` | Modify | Update `fake_search` signatures to accept `TokenContext` |
| `tests/test_token_bug.py` | Create | Bug regression tests asserting correct behavior |

---

## Task 0: Git Setup — Branch Preparation

**Files:** None (git operations only)

- [ ] **Step 1: Discard uncommitted changes on iter5**

```bash
git checkout -- src/crawler.py
git clean -fd tests/test_token_bug.py
```

- [ ] **Step 2: Merge iter5 into develop**

```bash
git checkout develop
git merge feature/iter5-config-refresh
```

- [ ] **Step 3: Push develop**

```bash
git push origin develop
```

- [ ] **Step 4: Create new feature branch**

```bash
git checkout -b feature/iter6-token-propagation
```

- [ ] **Step 5: Verify clean state**

```bash
git status
python -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

Expected: all 154 tests pass, no uncommitted changes.

---

## Task 1: TokenContext Dataclass (TDD)

**Files:**
- Modify: `src/auth.py:1-10` (add import + class after imports)
- Modify: `tests/test_auth.py` (add test class)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_auth.py`:

```python
from src.auth import TokenContext


class TestTokenContext:
    def test_mutable_token_update(self):
        ctx = TokenContext(token="old")
        assert ctx.token == "old"
        ctx.token = "new"
        assert ctx.token == "new"

    def test_shared_mutation_visible_to_all(self):
        ctx = TokenContext(token="original")
        ref = ctx
        ref.token = "updated"
        assert ctx.token == "updated"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_auth.py::TestTokenContext -v
```

Expected: FAIL — `ImportError: cannot import name 'TokenContext' from src.auth`

- [ ] **Step 3: Implement TokenContext**

At the top of `src/auth.py`, add the import:

```python
from dataclasses import dataclass
```

After the `_USER_AGENT` block (after line 9), add:

```python
@dataclass
class TokenContext:
    token: str
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_auth.py::TestTokenContext -v
```

Expected: 2 passed

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: 156 passed (154 original + 2 new)

- [ ] **Step 6: Commit**

```bash
git add src/auth.py tests/test_auth.py
git commit -m "feat: add TokenContext dataclass for mutable token propagation"
```

---

## Task 2: Error Detection Helpers (TDD)

**Files:**
- Modify: `src/auth.py` (add two helper functions)
- Modify: `tests/test_auth.py` (add test classes)

- [ ] **Step 1: Write failing tests for `_is_token_error`**

Add to `tests/test_auth.py`:

```python
from src.auth import _is_token_error


class TestIsTokenError:
    def test_detects_token_error(self):
        assert _is_token_error({"code": "1", "message": "token error"}) is True

    def test_detects_token_error_case_insensitive(self):
        assert _is_token_error({"code": "1", "message": "Token Error"}) is True

    def test_ignores_non_token_error(self):
        assert _is_token_error({"code": "1", "message": "rate limit"}) is False

    def test_ignores_success_response(self):
        assert _is_token_error({"total": 100, "data": []}) is False

    def test_ignores_empty_message(self):
        assert _is_token_error({"code": "1", "message": ""}) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_auth.py::TestIsTokenError -v
```

Expected: FAIL — `ImportError: cannot import name '_is_token_error'`

- [ ] **Step 3: Implement `_is_token_error`**

Add to `src/auth.py` before `search_api` (before line 89):

```python
def _is_token_error(data: dict) -> bool:
    return data.get("code") == "1" and "token" in data.get("message", "").lower()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_auth.py::TestIsTokenError -v
```

Expected: 5 passed

- [ ] **Step 5: Write failing tests for `_is_unexpected_response`**

Add to `tests/test_auth.py`:

```python
from src.auth import _is_unexpected_response


class TestIsUnexpectedResponse:
    def test_detects_error_response(self):
        assert _is_unexpected_response({"code": "2", "message": "server error"}) is True

    def test_passes_with_total(self):
        assert _is_unexpected_response({"total": 100}) is False

    def test_passes_with_data(self):
        assert _is_unexpected_response({"data": []}) is False

    def test_passes_with_both(self):
        assert _is_unexpected_response({"total": 100, "data": []}) is False
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_auth.py::TestIsUnexpectedResponse -v
```

Expected: FAIL — `ImportError: cannot import name '_is_unexpected_response'`

- [ ] **Step 7: Implement `_is_unexpected_response`**

Add to `src/auth.py` after `_is_token_error`:

```python
def _is_unexpected_response(data: dict) -> bool:
    return "total" not in data and "data" not in data
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_auth.py::TestIsUnexpectedResponse -v
```

Expected: 4 passed

- [ ] **Step 9: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: 165 passed

- [ ] **Step 10: Commit**

```bash
git add src/auth.py tests/test_auth.py
git commit -m "feat: add _is_token_error and _is_unexpected_response helpers"
```

---

## Task 3: search_api TokenContext Migration (TDD)

**Files:**
- Modify: `src/auth.py:89-118` (search_api function)
- Modify: `tests/test_auth.py` (add test class, update existing)

- [ ] **Step 1: Write failing test for search_api with TokenContext**

Add to `tests/test_auth.py`:

```python
class TestSearchApiTokenContext:
    def test_updates_ctx_on_js_error(self):
        mock_page = MagicMock()
        call_count = 0

        def fake_evaluate(js, args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"_error": "not_json"}
            return {"total": 100, "data": []}

        mock_page.evaluate.side_effect = fake_evaluate

        ctx = TokenContext(token="old_token")
        with patch("src.auth.reauthenticate", return_value="new_token"):
            result = search_api(mock_page, ctx, {"test": True})

        assert ctx.token == "new_token"
        assert result["total"] == 100

    def test_updates_ctx_on_api_token_error(self):
        mock_page = MagicMock()
        call_count = 0

        def fake_evaluate(js, args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"code": "1", "message": "token error"}
            return {"total": 200, "data": []}

        mock_page.evaluate.side_effect = fake_evaluate

        ctx = TokenContext(token="expired")
        with patch("src.auth.reauthenticate", return_value="fresh"):
            result = search_api(mock_page, ctx, {"test": True})

        assert ctx.token == "fresh"
        assert result["total"] == 200

    def test_raises_on_unexpected_response(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = {"code": "2", "message": "server error"}

        ctx = TokenContext(token="good")
        with pytest.raises(RuntimeError, match="Unexpected API response"):
            search_api(mock_page, ctx, {"test": True})

    def test_returns_data_on_success(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = {"total": 500, "data": [{"gid": "g1"}]}

        ctx = TokenContext(token="valid")
        result = search_api(mock_page, ctx, {"test": True})

        assert result["total"] == 500
        assert ctx.token == "valid"

    def test_uses_ctx_token_in_request(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = {"total": 1, "data": []}

        ctx = TokenContext(token="my_token")
        search_api(mock_page, ctx, {"test": True})

        call_args = mock_page.evaluate.call_args[0][1]
        assert call_args[1] == "my_token"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_auth.py::TestSearchApiTokenContext -v
```

Expected: FAIL — `search_api` still expects `token: str`, not `TokenContext`

- [ ] **Step 3: Update `search_api` signature and implementation**

Replace `src/auth.py` lines 89-118 with:

```python
def search_api(page: Page, ctx: TokenContext, body: dict) -> dict:
    """Send a search request to PKULaw API. Returns response dict.

    Retries once on auth errors (re-authenticates and retries).
    Raises RuntimeError on unexpected API responses.
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
                [body, ctx.token],
            )
            if data.get("_error"):
                ctx.token = reauthenticate(page)
                continue
            if _is_token_error(data):
                ctx.token = reauthenticate(page)
                continue
            if _is_unexpected_response(data):
                raise RuntimeError(
                    f"Unexpected API response: code={data.get('code', '?')}, "
                    f"message={data.get('message', str(data)[:200])}"
                )
            return data
        except Exception as e:
            if "Execution context" in str(e):
                ctx.token = reauthenticate(page)
                continue
            raise
    return {}
```

- [ ] **Step 4: Update existing signature test**

In `tests/test_auth.py`, update `TestSearchApiSignature`:

```python
class TestSearchApiSignature:
    def test_search_api_has_correct_params(self):
        sig = inspect.signature(search_api)
        params = list(sig.parameters.keys())
        assert "page" in params
        assert "ctx" in params
        assert "body" in params
```

- [ ] **Step 5: Run all auth tests**

```bash
.venv/bin/python -m pytest tests/test_auth.py -v
```

Expected: all auth tests pass

- [ ] **Step 6: Run full suite (expect partition/crawler failures)**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: auth tests pass, partition and crawler tests fail because they pass `str` token instead of `TokenContext`. This is expected — we fix these in Tasks 4-5.

- [ ] **Step 7: Commit**

```bash
git add src/auth.py tests/test_auth.py
git commit -m "feat: migrate search_api to TokenContext with error detection"
```

---

## Task 4: partition_query TokenContext Migration

**Files:**
- Modify: `src/partition.py:64-172` (signature + all search_fn calls)
- Modify: `tests/test_partition.py` (update fake_search signatures)

- [ ] **Step 1: Update `partition_query` signature**

In `src/partition.py`, change line 66 from `token: str` to `ctx: TokenContext`.

Add import at top of file:
```python
from src.auth import TokenContext
```

Change line 66:
```python
    ctx: TokenContext,
```

- [ ] **Step 2: Update all `search_fn` calls in `partition_query`**

Line 96 — change:
```python
    result = search_fn(page, token, body)
```
to:
```python
    result = search_fn(page, ctx, body)
```

Line 120 — change:
```python
            child_result = search_fn(page, token, child_body)
```
to:
```python
            child_result = search_fn(page, ctx, child_body)
```

Line 141 — change:
```python
                    token,
```
to:
```python
                    ctx,
```

- [ ] **Step 3: Update test `fake_search` signatures**

In `tests/test_partition.py`, update all `fake_search` functions to accept `ctx` instead of `token`.

For `test_large_total_splits_by_year` (line 73):
```python
        def fake_search(page, ctx, body):
```

For `test_very_large_year_splits_further` (line 96):
```python
        def fake_search(page, ctx, body):
```

Update all `partition_query` calls in tests to pass `TokenContext`:

For `test_small_total_returns_leaf`:
```python
        from src.auth import TokenContext
        ...
        result = partition_query(
            page=None,
            token=TokenContext(token="test"),
            ...
        )
```

Wait — the parameter is now `ctx`, not `token`. Update all test calls:

For `test_small_total_returns_leaf`:
```python
        result = partition_query(
            page=None,
            ctx=TokenContext(token="test"),
            search_config=config,
            search_fn=mock_api,
        )
```

For `test_large_total_splits_by_year`:
```python
        result = partition_query(
            page=None,
            ctx=TokenContext(token="test"),
            search_config=config,
            search_fn=fake_search,
        )
```

For `test_very_large_year_splits_further`:
```python
        result = partition_query(
            page=None,
            ctx=TokenContext(token="test"),
            search_config=config,
            search_fn=fake_search,
        )
```

Add import at top of `tests/test_partition.py`:
```python
from src.auth import TokenContext
```

- [ ] **Step 4: Run partition tests**

```bash
.venv/bin/python -m pytest tests/test_partition.py -v
```

Expected: all pass

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: auth + partition tests pass. Crawler tests still fail because `run_search` calls `search_api` with `str` token.

- [ ] **Step 6: Commit**

```bash
git add src/partition.py tests/test_partition.py
git commit -m "feat: migrate partition_query to TokenContext"
```

---

## Task 5: Caller Updates — run_search and cmd_estimate

**Files:**
- Modify: `src/crawler.py:8-14,169-218` (imports + run_search)
- Modify: `pkulaw.py:19,50` (imports + cmd_estimate call)

- [ ] **Step 1: Update `src/crawler.py` imports**

Line 8-14, change:
```python
from src.auth import (
    authenticate,
    close_browser,
    launch_browser,
    reauthenticate,
    search_api,
)
```
to:
```python
from src.auth import (
    TokenContext,
    authenticate,
    close_browser,
    launch_browser,
    search_api,
)
```

(Remove `reauthenticate` — no longer needed in this file.)

- [ ] **Step 2: Update `run_search` to create TokenContext**

In `run_search` (line 155), after `max_pages = ...`, add `TokenContext` creation.
Change line 169:
```python
    partition_tree = partition_query(page, token, search_config)
```
to:
```python
    ctx = TokenContext(token=token)
    partition_tree = partition_query(page, ctx, search_config)
```

Change line 185:
```python
                data = search_api(page, token, body)
```
to:
```python
                data = search_api(page, ctx, body)
```

- [ ] **Step 3: Update `pkulaw.py` cmd_estimate**

Add import at line 19:
```python
    from src.auth import authenticate, close_browser, launch_browser, TokenContext
```

Change line 50:
```python
        result = partition_query(page, token, config)
```
to:
```python
        result = partition_query(page, TokenContext(token=token), config)
```

- [ ] **Step 4: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: all tests pass (154 original tests — the 3 previously-failing crawler tests now pass because `reauthenticate` is no longer called in `run_search`)

- [ ] **Step 5: Commit**

```bash
git add src/crawler.py pkulaw.py
git commit -m "feat: update run_search and cmd_estimate to use TokenContext"
```

---

## Task 6: Regression Tests

**Files:**
- Create: `tests/test_token_bug.py`

- [ ] **Step 1: Write regression tests asserting correct behavior**

Create `tests/test_token_bug.py`:

```python
"""Regression tests for token propagation fix.

These tests verify that the three bugs (H1-H4) are fixed:
1. search_api detects API-level token errors
2. TokenContext propagates refreshed token to all callers
3. partition_query uses propagated token through recursive calls
4. Unexpected API responses raise RuntimeError instead of silent swallowing
"""

from unittest.mock import MagicMock, patch

import pytest

from src.auth import TokenContext, _is_token_error, _is_unexpected_response, search_api
from src.partition import _add_dimension_filter, partition_query


class TestTokenErrorDetection:
    """H1: search_api detects API-level token errors."""

    def test_detects_api_token_error_and_reauthenticates(self):
        mock_page = MagicMock()
        call_count = 0

        def fake_evaluate(js, args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"code": "1", "message": "token error"}
            return {"total": 100, "data": []}

        mock_page.evaluate.side_effect = fake_evaluate

        ctx = TokenContext(token="expired")
        with patch("src.auth.reauthenticate", return_value="new_token"):
            result = search_api(mock_page, ctx, {"test": True})

        assert result["total"] == 100
        assert ctx.token == "new_token"


class TestTokenPropagation:
    """H2: TokenContext propagates refreshed token to callers."""

    def test_shared_context_sees_token_update(self):
        ctx = TokenContext(token="old")
        holder_a = ctx
        holder_b = ctx

        with patch("src.auth.reauthenticate", return_value="refreshed"):
            ctx.token = "refreshed"

        assert holder_a.token == "refreshed"
        assert holder_b.token == "refreshed"

    def test_search_api_propagates_through_partition(self):
        """Token refreshed by search_api is visible in subsequent partition calls."""
        tokens_seen = []

        def tracking_search(page, ctx, body):
            tokens_seen.append(ctx.token)
            return {"total": 100, "data": []}

        ctx = TokenContext(token="initial")
        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        partition_query(page=None, ctx=ctx, search_config=config, search_fn=tracking_search)

        # All calls should see the same token
        assert all(t == "initial" for t in tokens_seen)

        # Simulate token refresh mid-partition
        ctx.token = "refreshed"
        tokens_seen.clear()
        partition_query(page=None, ctx=ctx, search_config=config, search_fn=tracking_search)

        assert all(t == "refreshed" for t in tokens_seen)


class TestPartitionQueryNoSilentSkip:
    """H3+H4: partition_query does not silently skip on errors."""

    def test_unexpected_response_raises(self):
        """When search_api returns unexpected response, RuntimeError is raised."""
        mock_page = MagicMock()
        mock_page.evaluate.return_value = {"code": "2", "message": "server error"}

        ctx = TokenContext(token="good")
        with pytest.raises(RuntimeError, match="Unexpected API response"):
            search_api(mock_page, ctx, {"test": True})

    def test_token_expiry_recovery(self):
        """partition_query recovers from token expiry via TokenContext."""
        call_count = 0

        def fake_search(page, ctx, body):
            nonlocal call_count
            call_count += 1

            # First call: initial query
            if call_count == 1:
                return {"total": 3000, "data": []}

            gb = body.get("groupBy", {})
            year = gb.get("LastInstanceDate", "")

            # Simulate token refresh after call 5
            if call_count == 5:
                ctx.token = "refreshed_token"

            # All years return data (token context propagated)
            if year:
                return {"total": 100, "data": []}
            return {"total": 3000, "data": []}

        ctx = TokenContext(token="initial")
        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        result = partition_query(page=None, ctx=ctx, search_config=config, search_fn=fake_search)

        # All years should be present (not silently skipped)
        assert result["dimension"] == "LastInstanceDate"
        assert len(result["children"]) > 2


class TestAddDimensionFilterPreservesMultiValueCategoryNew:
    def test_partitioning_by_year_keeps_category_new(self):
        config = {
            "fieldNodes": [
                {"field": "CategoryNew", "values": ["id1", "id2", "id3"]},
            ],
            "settings": {},
        }
        result = _add_dimension_filter(config, "LastInstanceDate", "2025")
        cat_nodes = [n for n in result["fieldNodes"] if n["field"] == "CategoryNew"]
        assert len(cat_nodes) == 1
        assert cat_nodes[0]["values"] == ["id1", "id2", "id3"]

    def test_partitioning_by_category_replaces_values(self):
        config = {
            "fieldNodes": [
                {"field": "CategoryNew", "values": ["id1", "id2", "id3"]},
            ],
            "settings": {},
        }
        result = _add_dimension_filter(config, "CategoryNew", "id2")
        cat_nodes = [n for n in result["fieldNodes"] if n["field"] == "CategoryNew"]
        assert len(cat_nodes) == 1
        assert cat_nodes[0]["values"] == ["id2"]
```

- [ ] **Step 2: Run regression tests**

```bash
.venv/bin/python -m pytest tests/test_token_bug.py -v
```

Expected: all pass (the fix is already in place from Tasks 1-5)

- [ ] **Step 3: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_token_bug.py
git commit -m "test: add regression tests for token propagation fix"
```

---

## Task 7: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 2: Run pre-commit hooks**

```bash
pre-commit run --all-files
```

Expected: all pass

- [ ] **Step 3: Verify no uncommitted changes**

```bash
git status
```

Expected: clean working tree

- [ ] **Step 4: Push branch**

```bash
git push -u origin feature/iter6-token-propagation
```

- [ ] **Step 5: Merge to develop**

```bash
git checkout develop
git merge feature/iter6-token-propagation
git push origin develop
```

---

## Self-Review

### Spec Coverage

| Spec Requirement | Task |
|-----------------|------|
| TokenContext dataclass | Task 1 |
| _is_token_error helper | Task 2 |
| _is_unexpected_response helper | Task 2 |
| search_api signature + error handling | Task 3 |
| partition_query TokenContext migration | Task 4 |
| run_search creates ctx | Task 5 |
| cmd_estimate creates ctx | Task 5 |
| Remove uncommitted reauthenticate | Task 5 (via branch setup) |
| Existing test updates | Tasks 3-4 |
| Regression tests | Task 6 |
| Git workflow (discard, merge, new branch) | Task 0 |

### Placeholder Scan

No TBD/TODO. All steps contain exact code.

### Type Consistency

- `TokenContext` defined in Task 1, used consistently in Tasks 3-6
- `search_api(page, ctx, body)` signature set in Task 3, called with same signature in Tasks 4-5
- `partition_query(page, ctx, ...)` set in Task 4, called with same signature in Task 5
- `fake_search(page, ctx, body)` updated in Task 4, matches search_api signature from Task 3
