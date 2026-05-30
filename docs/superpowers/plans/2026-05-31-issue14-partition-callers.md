# Issue #14: partition_query + 调用方 TokenContext 适配

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate partition_query and all callers to use TokenContext, completing the token propagation pipeline end-to-end.

**Architecture:** partition_query accepts TokenContext, all search_fn calls pass ctx. run_search and cmd_estimate create TokenContext from raw token string. External interfaces unchanged.

**Tech Stack:** Python 3.14, pytest, dataclasses

**Spec:** `docs/superpowers/specs/2026-05-31-token-propagation-design.md`
**ADR:** `docs/adr/0001-mutable-token-context.md`
**Parent Issue:** #12
**Depends on:** #13 (completed — TokenContext + search_api in auth.py)

**verify_command:** `.venv/bin/python -m pytest tests/ -v --tb=short`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/partition.py` | Modify | Signature `token: str` → `ctx: TokenContext`, update 3 search_fn calls, add import |
| `src/crawler.py` | Modify | Create TokenContext in run_search, pass ctx, remove reauthenticate import |
| `pkulaw.py` | Modify | Create TokenContext in cmd_estimate |
| `tests/test_partition.py` | Modify | Update fake_search signatures, add TokenContext import |

---

## Task 1: partition_query TokenContext Migration

**Files:**
- Modify: `src/partition.py:3,66,96,120,141`
- Modify: `tests/test_partition.py`

**Why:** partition_query is the main consumer of search_fn — it must accept and propagate TokenContext through recursive calls.

- [ ] **Step 1: Write failing test for partition_query accepting TokenContext**

Add to `tests/test_partition.py`:

```python
from src.auth import TokenContext
```

Add new test class:

```python
class TestPartitionQueryTokenContext:
    def test_accepts_token_context(self):
        mock_api = MagicMock(return_value={"total": 500, "data": []})
        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        ctx = TokenContext(token="test")
        result = partition_query(
            page=None,
            ctx=ctx,
            search_config=config,
            search_fn=mock_api,
        )
        assert result["total"] == 500
        # Verify ctx was passed to search_fn
        call_args = mock_api.call_args
        assert call_args[0][1] is ctx

    def test_propagates_context_through_recursion(self):
        """Token refreshed mid-partition is visible to subsequent calls."""
        tokens_seen = []

        def tracking_search(page, ctx, body):
            tokens_seen.append(ctx.token)
            gb = body.get("groupBy", {})
            if gb.get("LastInstanceDate"):
                return {"total": 100, "data": []}
            return {"total": 3000, "data": []}

        ctx = TokenContext(token="initial")
        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        partition_query(page=None, ctx=ctx, search_config=config, search_fn=tracking_search)

        assert all(t == "initial" for t in tokens_seen)

        ctx.token = "refreshed"
        tokens_seen.clear()
        partition_query(page=None, ctx=ctx, search_config=config, search_fn=tracking_search)

        assert all(t == "refreshed" for t in tokens_seen)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_partition.py::TestPartitionQueryTokenContext -v
```

Expected: FAIL — `partition_query()` got unexpected keyword argument `ctx`

- [ ] **Step 3: Update partition_query signature + all search_fn calls**

In `src/partition.py`, add import at top:
```python
from src.auth import TokenContext
```

Change line 66: `token: str,` → `ctx: TokenContext,`

Change line 96: `result = search_fn(page, token, body)` → `result = search_fn(page, ctx, body)`

Change line 120: `child_result = search_fn(page, token, child_body)` → `child_result = search_fn(page, ctx, child_body)`

Change line 141: `token,` → `ctx,`

- [ ] **Step 4: Update existing test fake_search signatures**

In `tests/test_partition.py`, change all `fake_search(page, token, body)` → `fake_search(page, ctx, body)`.

Update all `partition_query` calls to pass `ctx=TokenContext(token="test")` instead of `token="test"`.

Add `from src.auth import TokenContext` at top.

- [ ] **Step 5: Run all partition tests**

```bash
.venv/bin/python -m pytest tests/test_partition.py -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/partition.py tests/test_partition.py
git commit -m "feat: migrate partition_query to TokenContext"
```

---

## Task 2: Caller Updates — run_search and cmd_estimate

**Files:**
- Modify: `src/crawler.py:8-14,169,185`
- Modify: `pkulaw.py:19,50`

**Why:** Callers must create TokenContext and pass it to partition_query and search_api.

- [ ] **Step 1: Update src/crawler.py imports**

Change:
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

- [ ] **Step 2: Update run_search to create TokenContext**

After `max_pages = search_config.get("settings", {}).get("max_pages", 10)`, add:

```python
    ctx = TokenContext(token=token)
```

Change partition_query call:
```python
    partition_tree = partition_query(page, ctx, search_config)
```

Change search_api call:
```python
                data = search_api(page, ctx, body)
```

- [ ] **Step 3: Update pkulaw.py cmd_estimate**

Add `TokenContext` to the import in cmd_estimate function:
```python
    from src.auth import authenticate, close_browser, launch_browser, TokenContext
```

Change:
```python
        result = partition_query(page, token, config)
```
to:
```python
        result = partition_query(page, TokenContext(token=token), config)
```

- [ ] **Step 4: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: all 170+ tests pass

- [ ] **Step 5: Commit**

```bash
git add src/crawler.py pkulaw.py
git commit -m "feat: update run_search and cmd_estimate to use TokenContext"
```

---

## Task 3: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 2: Run pre-commit hooks**

```bash
pre-commit run --all-files
```

Expected: all pass

- [ ] **Step 3: Verify no uncommitted changes**

```bash
git status
```

Expected: clean working tree (except untracked input/)
