# Issue #10: --max-cases Crawl Limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--max-cases N` CLI flag to the crawl subcommand that stops fetching after N total cases (including resume progress).

**Architecture:** Add `--max-cases` to the crawl subparser in `cli.py`, pass it through `settings["max_cases"]`, and add a limit check in `crawler.py`'s `run_fetch` — both an early-exit check after loading progress and a break inside the fetch loop.

**Tech Stack:** Python, pytest, unittest.mock

---

### Task 1: TDD — Write CLI tests for --max-cases (RED)

**Files:**
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add these tests in `tests/test_cli.py` in the `TestParserCrawlArgs` class (after `test_crawl_has_output_options`):

```python
    def test_crawl_accepts_max_cases(self):
        parser = create_parser()
        args = parser.parse_args(["crawl", "--max-cases", "2000"])
        assert args.max_cases == 2000

    def test_max_cases_default_is_zero(self):
        parser = create_parser()
        args = parser.parse_args(["crawl"])
        assert args.max_cases == 0
```

Add this test in the `TestBuildSearchConfig` class (after `test_settings_custom`):

```python
    def test_max_cases_in_settings(self):
        parser = create_parser()
        args = parser.parse_args(["crawl", "--max-cases", "100"])
        config = build_search_config(args)
        assert config["settings"]["max_cases"] == 100

    def test_max_cases_default_in_settings(self):
        parser = create_parser()
        args = parser.parse_args(["crawl"])
        config = build_search_config(args)
        assert config["settings"]["max_cases"] == 0
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestParserCrawlArgs::test_crawl_accepts_max_cases tests/test_cli.py::TestBuildSearchConfig::test_max_cases_in_settings -v`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'max_cases'`

---

### Task 2: Implement --max-cases in CLI + settings (GREEN)

**Files:**
- Modify: `src/cli.py:69-71` (crawl subparser) and `src/cli.py:162-186` (settings flow)

- [ ] **Step 1: Add --max-cases argument to crawl subcommand**

In `src/cli.py`, after the `--chunk-size` line (line 71):

```python
    crawl.add_argument(
        "--max-cases", type=int, default=0,
        help="Stop after fetching N total cases (0=unlimited)",
    )
```

- [ ] **Step 2: Add max_cases to settings flow**

In `src/cli.py`, inside `build_search_config`, in the `if not args.query:` branch (around line 173), add:

```python
            settings["max_cases"] = getattr(args, "max_cases", 0)
```

And in the `else:` branch (around line 178), add:

```python
            settings.setdefault("max_cases", getattr(args, "max_cases", 0))
```

Also add to `_SETTINGS_DEFAULTS` dict:

```python
    _SETTINGS_DEFAULTS = {
        "delay": 0.5,
        "max_pages": 10,
        "format": ["json", "xlsx"],
        "output_dir": "output",
        "max_cases": 0,
    }
```

- [ ] **Step 3: Run CLI tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: All tests PASS

---

### Task 3: TDD — Write run_fetch test for max_cases limit (RED)

**Files:**
- Modify: `tests/test_crawler.py`

- [ ] **Step 1: Write the failing test**

Add this test in `tests/test_crawler.py` in the `TestRunFetch` class (after `test_handles_new_dict_format`):

```python
    @patch("src.crawler.time.sleep")
    @patch("src.crawler.parse_case")
    @patch("src.crawler.authenticate", return_value="token123")
    @patch("src.crawler.launch_browser")
    def test_max_cases_stops_at_limit(
        self, mock_launch, mock_auth, mock_parse, mock_sleep, tmp_path
    ):
        """run_fetch stops when total fetched count reaches max_cases."""
        from unittest.mock import MagicMock as MM

        # 10 cases in search results
        cases_meta = [{"gid": f"g{i}", "title": f"t{i}"} for i in range(10)]
        (tmp_path / "search_results.json").write_text(
            json.dumps({"query": {"fieldNodes": []}, "results": cases_meta})
        )
        (tmp_path / "pkulaw_cases.json").write_text("[]")

        mock_parse.side_effect = [
            {"gid": f"g{i}", "title": f"t{i}", "full_text": "x" * 600}
            for i in range(10)
        ]

        mock_pw, mock_browser, mock_ctx, mock_page = MM(), MM(), MM(), MM()
        mock_page.evaluate.return_value = 2000
        mock_page.content.return_value = (
            "<html><body><div class='fulltext-wrap'>text</div></body></html>"
        )
        mock_launch.return_value = (mock_pw, mock_browser, mock_ctx, mock_page)

        with patch("src.crawler.close_browser"):
            config = {
                "fieldNodes": [],
                "settings": {
                    "delay": 0.1,
                    "browser_path": "/usr/bin/chromium",
                    "headless": True,
                    "max_cases": 5,
                },
            }
            logger = MM()
            result = run_fetch(config, tmp_path, logger)

        assert len(result) == 5
        assert mock_launch.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails (RED)**

Run: `.venv/bin/python -m pytest tests/test_crawler.py::TestRunFetch::test_max_cases_stops_at_limit -v`
Expected: FAIL — fetches all 10 instead of stopping at 5

---

### Task 4: Implement max_cases limit in run_fetch (GREEN)

**Files:**
- Modify: `src/crawler.py:257-378`

- [ ] **Step 1: Read max_cases from settings**

In `src/crawler.py`, in `run_fetch`, after `headless = settings.get("headless", True)` (line 260), add:

```python
    max_cases = settings.get("max_cases", 0)
```

- [ ] **Step 2: Add early-exit check after loading progress**

In the `while True` loop, after the `remaining = [...]` line and the `if not remaining:` check (around line 290), add:

```python
        if max_cases > 0 and len(fetched_gids) >= max_cases:
            logger.info(f"Max cases limit reached ({max_cases})")
            _save_all(results, fetched_gids, output_dir, logger)
            return results
```

- [ ] **Step 3: Add break inside fetch loop**

Inside the `for i, case in enumerate(remaining):` loop, after `fetched_gids.add(gid)` (around line 333), add:

```python
                    if max_cases > 0 and len(fetched_gids) >= max_cases:
                        break
```

- [ ] **Step 4: Add return check after save_all at end of while loop**

After `_save_all(results, fetched_gids, output_dir, logger)` at the end of the while loop (around line 376), before `logger.info("Restart in 15s...")`, add:

```python
        if max_cases > 0 and len(fetched_gids) >= max_cases:
            logger.info(f"Max cases limit reached ({max_cases})")
            return results
```

- [ ] **Step 5: Run test to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_crawler.py::TestRunFetch::test_max_cases_stops_at_limit -v`
Expected: PASS

---

### Task 5: TDD — Write run_fetch resume + max_cases test (RED + GREEN)

**Files:**
- Modify: `tests/test_crawler.py`

- [ ] **Step 1: Write the resume test**

Add this test in `tests/test_crawler.py` in the `TestRunFetch` class:

```python
    @patch("src.crawler.time.sleep")
    @patch("src.crawler.parse_case")
    @patch("src.crawler.authenticate", return_value="token123")
    @patch("src.crawler.launch_browser")
    def test_max_cases_with_resume(
        self, mock_launch, mock_auth, mock_parse, mock_sleep, tmp_path
    ):
        """run_fetch respects max_cases including already-fetched progress."""
        from unittest.mock import MagicMock as MM

        # 12 total cases, 7 already fetched
        cases_meta = [{"gid": f"g{i}", "title": f"t{i}"} for i in range(12)]
        (tmp_path / "search_results.json").write_text(
            json.dumps({"query": {"fieldNodes": []}, "results": cases_meta})
        )
        (tmp_path / "progress.json").write_text(
            json.dumps({"fetched_gids": [f"g{i}" for i in range(7)]})
        )
        (tmp_path / "pkulaw_cases.json").write_text("[]")

        mock_parse.side_effect = [
            {"gid": f"g{i}", "title": f"t{i}", "full_text": "x" * 600}
            for i in range(7, 12)
        ]

        mock_pw, mock_browser, mock_ctx, mock_page = MM(), MM(), MM(), MM()
        mock_page.evaluate.return_value = 2000
        mock_page.content.return_value = (
            "<html><body><div class='fulltext-wrap'>text</div></body></html>"
        )
        mock_launch.return_value = (mock_pw, mock_browser, mock_ctx, mock_page)

        with patch("src.crawler.close_browser"):
            config = {
                "fieldNodes": [],
                "settings": {
                    "delay": 0.1,
                    "browser_path": "/usr/bin/chromium",
                    "headless": True,
                    "max_cases": 10,
                },
            }
            logger = MM()
            result = run_fetch(config, tmp_path, logger)

        # 7 already fetched + 3 more to reach max_cases=10
        assert len(result) == 3
        assert mock_launch.call_count == 1
```

- [ ] **Step 2: Run the resume test**

Run: `.venv/bin/python -m pytest tests/test_crawler.py::TestRunFetch::test_max_cases_with_resume -v`
Expected: PASS (implementation from Task 4 handles this case)

---

### Task 6: Full suite + commit

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS (145 previous + 7 new = 152 total)

- [ ] **Step 2: Run pre-commit checks**

Run: `pre-commit run --files src/cli.py src/crawler.py tests/test_cli.py tests/test_crawler.py`
Expected: All hooks pass

- [ ] **Step 3: Commit**

```bash
git add src/cli.py src/crawler.py tests/test_cli.py tests/test_crawler.py
git commit -m "feat: add --max-cases flag to limit crawl fetch count

--max-cases N stops the fetch phase after N total cases (including
resume progress). Default 0 means unlimited. Only limits fetching,
search phase always runs fully.

Closes #10"
```
