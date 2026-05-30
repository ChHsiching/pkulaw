# Token Propagation Fix — Design Spec

**Date**: 2026-05-31
**Branch**: new feature branch from develop (after merging feature/iter5-config-refresh)
**Status**: Draft

## Problem

Running `pkulaw crawl` with multi-value CategoryNew over 20 criminal offense types returns
2,716,683 total results, but `partition_query` creates 976 leaf nodes that all return 0 gids.
The crawl produces zero data.

### Root Causes

Three bugs compound into complete search failure:

1. **H1 — search_api ignores API-level token errors**: When the PKULaw API returns
   `{"code": "1", "message": "token error"}`, `search_api` treats it as valid data (no `_error`
   key). It never triggers reauthentication.

2. **H2 — Token refresh doesn't propagate**: `search_api` calls `reauthenticate(page)` and
   stores the new token in a local variable. Since `str` is immutable and `search_api` returns
   `dict`, callers keep using the expired token.

3. **H3 — partition_query passes stale token for 7+ minutes**: `partition_query` binds `token`
   to `search_fn` calls and recursively makes hundreds of API calls. The token expires mid-way,
   and the stale token corrupts the partition tree.

4. **H4 — Silent error swallowing**: `partition_query` uses `result.get("total", 0)` which
   treats ANY response without a "total" key as "empty partition", silently skipping valid data.

### Bug Reproduction Tests

`tests/test_token_bug.py` contains 6 tests that confirm all four bugs:

| Test | Bug Confirmed |
|------|---------------|
| `test_returns_api_error_as_valid_data` | H1: search_api returns token error as valid data |
| `test_refreshed_token_not_returned` | H2: new token lost as local variable |
| `test_token_expiry_corrupts_partition_tree` | H3+H4: all children skipped as empty |
| `test_partial_token_expiry_skips_valid_partitions` | H3+H4: later partitions silently dropped |
| `test_partitioning_by_year_keeps_category_new` | multi-value CategoryNew preserved correctly |
| `test_partitioning_by_category_replaces_values` | single-value replacement works correctly |

## Design

### Approach: Mutable TokenContext dataclass

Introduce a `TokenContext` dataclass that wraps the token string. `search_api` mutates
`ctx.token` on reauthentication, so all holders of the same `TokenContext` instance see
the updated token.

### Components

#### 1. TokenContext dataclass (`src/auth.py`)

```python
from dataclasses import dataclass

@dataclass
class TokenContext:
    token: str
```

Mutable, type-safe, minimal. Created once per crawl session, passed through all API calls.

#### 2. search_api updates (`src/auth.py`)

**Signature change**: `(page, token: str, body)` → `(page, ctx: TokenContext, body)`

**Token error detection**: New `_is_token_error(data)` helper checks for API-level errors.

```python
def _is_token_error(data: dict) -> bool:
    return data.get("code") == "1" and "token" in data.get("message", "").lower()

def search_api(page: Page, ctx: TokenContext, body: dict) -> dict:
    for attempt in range(2):
        try:
            data = page.evaluate(fetch_js, [body, ctx.token])
            if data.get("_error"):
                ctx.token = reauthenticate(page)
                continue
            if _is_token_error(data):
                ctx.token = reauthenticate(page)
                continue
            return data
        except Exception as e:
            if "Execution context" in str(e):
                ctx.token = reauthenticate(page)
                continue
            raise
    return {}
```

Key changes:
- All `token = reauthenticate(page)` → `ctx.token = reauthenticate(page)` (mutates the container)
- Added `_is_token_error` check as second error detection path
- `data.get("_error")` remains for JS parse failures

#### 3. partition_query updates (`src/partition.py`)

**Signature change**: `(page, token: str, ...)` → `(page, ctx: TokenContext, ...)`

**search_fn calls**: `(page, token, body)` → `(page, ctx, body)`

**H4 — Error response detection**: New `_check_api_response` raises on unexpected responses.

```python
def _check_api_response(result: dict, context: str = "API call") -> None:
    if "total" not in result and "data" not in result:
        raise RuntimeError(
            f"{context} returned unexpected response: "
            f"code={result.get('code', '?')}, message={result.get('message', str(result)[:200])}"
        )
```

Called after every `search_fn` invocation:
- After initial query (line ~96)
- After each child dimension query (line ~120)

#### 4. run_search updates (`src/crawler.py`)

- Creates `TokenContext(token=token)` at entry
- Removes the uncommitted `token = reauthenticate(page)` line (line 173)
- Passes `ctx` to `partition_query` and `search_api`

```python
def run_search(search_config, page, token, output_dir, logger):
    ctx = TokenContext(token=token)

    partition_tree = partition_query(page, ctx, search_config)
    leaves = _collect_leaf_searches(partition_tree, search_config)

    # No reauthenticate needed — ctx.token is kept fresh by search_api

    for label, leaf_config in leaves:
        for sort_order in SORT_ORDERS:
            ...
            data = search_api(page, ctx, body)
```

#### 5. cmd_estimate updates (`pkulaw.py`)

```python
# Before:
result = partition_query(page, token, config)

# After:
result = partition_query(page, TokenContext(token=token), config)
```

### File change summary

| File | Changes |
|------|---------|
| `src/auth.py` | Add `TokenContext`, `_is_token_error`; update `search_api` signature + error handling |
| `src/partition.py` | Add `_check_api_response`; update `partition_query` signature + all `search_fn` calls |
| `src/crawler.py` | Create `TokenContext` in `run_search`; remove uncommitted reauthenticate; pass `ctx` |
| `pkulaw.py` | Create `TokenContext` in `cmd_estimate` |
| `tests/test_auth.py` | Update signature test; add token error detection test |
| `tests/test_partition.py` | Update all mocks to pass `TokenContext` instead of string |
| `tests/test_crawler.py` | Update `run_search` test mocks for new signatures |
| `tests/test_token_bug.py` | Convert to regression tests against `TokenContext` |

### Git workflow

1. Discard uncommitted changes on `feature/iter5-config-refresh`
2. Merge `feature/iter5-config-refresh` into `develop`
3. Create new feature branch `feature/iter6-token-propagation` from `develop`
4. TDD: write failing tests → implement → verify pass
5. Commit + merge to `develop`

### Success criteria

- [ ] All existing tests pass (151 + new regression tests)
- [ ] `test_token_bug.py` tests pass with `TokenContext` (confirming bugs are fixed)
- [ ] `partition_query` with simulated token expiry produces correct partition tree
- [ ] `search_api` detects and recovers from API-level token errors
- [ ] `_check_api_response` raises on unexpected API responses
- [ ] No uncommitted changes remain
- [ ] Pre-commit hooks pass (black, isort, Git Flow)
