# Issue #11: Ctrl+C Interrupt Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the minimal "Interrupted." message with a structured crawl progress summary when Ctrl+C is pressed during fetch.

**Architecture:** Add `_print_interrupt_summary(output_dir, initial_fetched)` helper that reads stats from data files. Wrap `run_fetch` call in `cmd_crawl` with try/except `KeyboardInterrupt`, tracking initial fetched count to compute "本次新增". The main() handler remains as fallback for other commands.

**Tech Stack:** Python, pytest, capsys

---

### Task 1: TDD — Write test for _print_interrupt_summary (RED)

**Files:**
- Modify: `tests/test_crawler.py` (add after `TestCmdCrawl` class)

- [ ] **Step 1: Write the failing test**

Add in `tests/test_crawler.py` after the `TestCmdCrawl` class:

```python


class TestInterruptSummary:
    def test_prints_interrupt_summary(self, tmp_path, capsys):
        from pkulaw import _print_interrupt_summary

        # Mock search_results.json (new format)
        cache = {
            "total_unique": 2716683,
            "results": [{"gid": f"g{i}"} for i in range(100)],
        }
        (tmp_path / "search_results.json").write_text(json.dumps(cache))

        # Mock progress.json
        progress = {"fetched_gids": [f"g{i}" for i in range(1500)]}
        (tmp_path / "progress.json").write_text(json.dumps(progress))

        # Mock pkulaw_cases.json
        cases = [
            {"full_text": "x" * 600} if i < 1203 else {"full_text": "short"}
            for i in range(1500)
        ]
        (tmp_path / "pkulaw_cases.json").write_text(json.dumps(cases))

        _print_interrupt_summary(tmp_path, initial_fetched=0)

        captured = capsys.readouterr()
        assert "=== 采集中断 ===" in captured.out
        assert "2,716,683" in captured.out
        assert "1,500 / 2,716,683" in captured.out
        assert "0.1%" in captured.out
        assert "1,203" in captured.out
        assert "本次新增：1,500" in captured.out
        assert "重新运行相同命令即可继续采集" in captured.out

    def test_shows_new_count_from_initial(self, tmp_path, capsys):
        from pkulaw import _print_interrupt_summary

        cache = {"total_unique": 100, "results": [{"gid": "g1"}]}
        (tmp_path / "search_results.json").write_text(json.dumps(cache))
        (tmp_path / "progress.json").write_text(
            json.dumps({"fetched_gids": [f"g{i}" for i in range(10)]})
        )
        (tmp_path / "pkulaw_cases.json").write_text("[]")

        _print_interrupt_summary(tmp_path, initial_fetched=7)

        captured = capsys.readouterr()
        assert "本次新增：3" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `.venv/bin/python -m pytest tests/test_crawler.py::TestInterruptSummary -v`
Expected: FAIL — `ImportError: cannot import name '_print_interrupt_summary' from 'pkulaw'`

---

### Task 2: Implement _print_interrupt_summary (GREEN)

**Files:**
- Modify: `pkulaw.py` (add helper function after `cmd_status`)

- [ ] **Step 1: Add the _print_interrupt_summary function**

Add in `pkulaw.py` after the `cmd_status` function (before `_format_query`):

```python
def _print_interrupt_summary(output_dir: Path, initial_fetched: int) -> None:
    """Print crawl progress summary after Ctrl+C interrupt."""
    import json as _json

    total_unique = 0
    cache_file = output_dir / "search_results.json"
    if cache_file.exists():
        raw = _json.loads(cache_file.read_text())
        if isinstance(raw, dict):
            total_unique = raw.get("total_unique", len(raw.get("results", [])))
        elif isinstance(raw, list):
            total_unique = len(raw)

    fetched_count = 0
    progress_file = output_dir / "progress.json"
    if progress_file.exists():
        fetched_count = len(
            _json.loads(progress_file.read_text()).get("fetched_gids", [])
        )

    valid_count = 0
    results_file = output_dir / "pkulaw_cases.json"
    if results_file.exists():
        cases = _json.loads(results_file.read_text())
        valid_count = sum(1 for c in cases if len(c.get("full_text", "")) > 500)

    new_count = fetched_count - initial_fetched
    pct = (fetched_count / total_unique * 100) if total_unique > 0 else 0

    print("\n")
    print("=== 采集中断 ===")
    print(f"已搜索：{total_unique:,} 条")
    print(f"已采集：{fetched_count:,} / {total_unique:,} ({pct:.1f}%)")
    print(f"有效数据：{valid_count:,} 条 (>500字)")
    print(f"本次新增：{new_count:,} 条")
    print(f"输出：{results_file}")
    print()
    print("重新运行相同命令即可继续采集。")
```

- [ ] **Step 2: Run tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_crawler.py::TestInterruptSummary -v`
Expected: All tests PASS

---

### Task 3: TDD — Write test for KeyboardInterrupt in cmd_crawl (RED)

**Files:**
- Modify: `tests/test_crawler.py` (add in `TestInterruptSummary` class)

- [ ] **Step 1: Write the failing integration test**

Add in `tests/test_crawler.py` in the `TestInterruptSummary` class:

```python
    def test_ctrl_c_in_cmd_crawl_prints_summary(self, tmp_path, capsys):
        from unittest.mock import MagicMock, patch

        from pkulaw import cmd_crawl

        config = {
            "fieldNodes": [{"field": "FullText", "value": "test"}],
            "settings": {
                "output_dir": str(tmp_path),
                "format": ["json"],
                "delay": 0,
                "browser": "/usr/bin/chromium",
                "headless": True,
            },
        }

        # Set up data files for summary
        cache = {"total_unique": 500, "results": [{"gid": "g1"}]}
        (tmp_path / "search_results.json").write_text(json.dumps(cache))
        (tmp_path / "progress.json").write_text(
            json.dumps({"fetched_gids": ["g1"]})
        )
        (tmp_path / "pkulaw_cases.json").write_text(
            json.dumps([{"full_text": "x" * 600}])
        )

        with (
            patch(
                "pkulaw.launch_browser",
                return_value=(MagicMock(), MagicMock(), MagicMock(), MagicMock()),
            ),
            patch("pkulaw.authenticate", return_value="fake_token"),
            patch("pkulaw.close_browser"),
            patch("pkulaw.run_search", return_value=[{"gid": "g1", "title": "C1"}]),
            patch("pkulaw.run_fetch", side_effect=KeyboardInterrupt),
        ):
            cmd_crawl(config)

        captured = capsys.readouterr()
        assert "=== 采集中断 ===" in captured.out
        assert "重新运行相同命令即可继续采集" in captured.out
```

- [ ] **Step 2: Run test to verify it fails (RED)**

Run: `.venv/bin/python -m pytest tests/test_crawler.py::TestInterruptSummary::test_ctrl_c_in_cmd_crawl_prints_summary -v`
Expected: FAIL — `KeyboardInterrupt` propagates to `main()` which prints "Interrupted." instead of the summary

---

### Task 4: Implement KeyboardInterrupt handler in cmd_crawl (GREEN)

**Files:**
- Modify: `pkulaw.py:64-120` (the `cmd_crawl` function)

- [ ] **Step 1: Wrap run_fetch with try/except KeyboardInterrupt**

In `pkulaw.py`, replace the Phase 2 section in `cmd_crawl` (lines 101-104):

```python
    # Phase 2 — Fetch
    print("\n[Phase 2/3] 采集全文...")
    fetched = run_fetch(config, output_dir, logger)
    print(f"采集完成，共 {len(fetched)} 条")
```

with:

```python
    # Track initial fetch count for "本次新增"
    import json as _json

    progress_file = output_dir / "progress.json"
    initial_fetched = 0
    if progress_file.exists():
        initial_fetched = len(
            _json.loads(progress_file.read_text()).get("fetched_gids", [])
        )

    # Phase 2 — Fetch
    print("\n[Phase 2/3] 采集全文...")
    try:
        fetched = run_fetch(config, output_dir, logger)
    except KeyboardInterrupt:
        _print_interrupt_summary(output_dir, initial_fetched)
        return
    print(f"采集完成，共 {len(fetched)} 条")
```

- [ ] **Step 2: Run the integration test to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_crawler.py::TestInterruptSummary::test_ctrl_c_in_cmd_crawl_prints_summary -v`
Expected: PASS

---

### Task 5: Full suite + commit

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS (151 previous + 3 new = 154 total)

- [ ] **Step 2: Run pre-commit checks**

Run: `pre-commit run --files pkulaw.py tests/test_crawler.py`
Expected: All hooks pass

- [ ] **Step 3: Commit**

```bash
git add pkulaw.py tests/test_crawler.py
git commit -m "feat: show structured progress summary on Ctrl+C during crawl

Replaces the generic 'Interrupted.' message with a crawl-specific
summary showing total searched, fetched count, valid cases, and
new cases this session. Reads stats from existing data files.

Closes #11"
```
