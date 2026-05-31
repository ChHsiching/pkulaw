# Issue #9: Fix Multi-Value CategoryNew — query builder + test

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `src/query.py:97` so all CategoryNew IDs are sent as a comma-separated string instead of only the first one.

**Architecture:** One-line change in `build_api_body`: `ids[0]` → `",".join(ids)`. Verified against live PKULaw API (2026-05-30): comma-separated clusterFilters returns OR-union results.

**Tech Stack:** Python, pytest

---

### Task 1: TDD — Write failing test for multi-value CategoryNew (RED)

**Files:**
- Modify: `tests/test_query.py` (add test after `test_category_new_in_cluster_filters` at line 108)

- [ ] **Step 1: Write the failing test**

Add this test in `tests/test_query.py` after `test_category_new_in_cluster_filters` (line 107):

```python
    def test_multi_value_category_new_joins_with_commas(self):
        config = {
            "fieldNodes": [
                {"field": "CategoryNew", "values": ["001002050", "001005002"]},
            ],
            "settings": {},
        }
        body = build_api_body(config)
        assert body["clusterFilters"]["CategoryNew"] == "001002050,001005002"
        assert not any(n["fieldName"] == "CategoryNew" for n in body["fieldNodes"])
```

- [ ] **Step 2: Run test to verify it fails (RED)**

Run: `.venv/bin/python -m pytest tests/test_query.py::TestBuildApiBody::test_multi_value_category_new_joins_with_commas -v`
Expected: FAIL — `AssertionError: assert '001002050' == '001002050,001005002'` (only first ID sent)

---

### Task 2: Fix query.py (GREEN)

**Files:**
- Modify: `src/query.py:97`

- [ ] **Step 1: Change ids[0] to ",".join(ids)**

In `src/query.py`, line 97, change:

```python
                cluster_filters["CategoryNew"] = ids[0]
```

to:

```python
                cluster_filters["CategoryNew"] = ",".join(ids)
```

- [ ] **Step 2: Run the new test to verify it passes (GREEN)**

Run: `.venv/bin/python -m pytest tests/test_query.py::TestBuildApiBody::test_multi_value_category_new_joins_with_commas -v`
Expected: PASS

---

### Task 3: Full suite + commit

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS (144 + 1 new = 145 total)

- [ ] **Step 2: Run pre-commit checks**

Run: `pre-commit run --files src/query.py tests/test_query.py`
Expected: All hooks pass

- [ ] **Step 3: Commit**

```bash
git add src/query.py tests/test_query.py
git commit -m "fix: send all CategoryNew IDs as comma-separated string

Previously only the first crime type ID was sent in clusterFilters,
silently dropping all others. Now all IDs are joined with commas,
which the PKULaw API correctly handles as OR-union.

Closes #9"
```
