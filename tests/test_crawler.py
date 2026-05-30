"""Tests for src/crawler.py and pkulaw.py — search, fetch, and cmd_crawl pipeline."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.crawler import (
    _excel_file,
    _load_progress,
    _matches_query,
    _progress_file,
    _results_file,
    _save_all,
    _save_progress,
    _save_search_results,
    _search_cache_file,
    run_fetch,
    run_search,
)

# ---------------------------------------------------------------------------
# Helper path functions
# ---------------------------------------------------------------------------


class TestProgressFile:
    def test_returns_progress_json(self, tmp_path):
        assert _progress_file(tmp_path) == tmp_path / "progress.json"


class TestSearchCacheFile:
    def test_returns_search_results_json(self, tmp_path):
        assert _search_cache_file(tmp_path) == tmp_path / "search_results.json"


class TestResultsFile:
    def test_returns_pkulaw_cases_json(self, tmp_path):
        assert _results_file(tmp_path) == tmp_path / "pkulaw_cases.json"


class TestExcelFile:
    def test_returns_pkulaw_cases_xlsx(self, tmp_path):
        assert _excel_file(tmp_path) == tmp_path / "pkulaw_cases.xlsx"


# ---------------------------------------------------------------------------
# Progress I/O
# ---------------------------------------------------------------------------


class TestLoadProgress:
    def test_returns_empty_when_no_file(self, tmp_path):
        assert _load_progress(tmp_path) == set()

    def test_returns_fetched_gids(self, tmp_path):
        progress_file = tmp_path / "progress.json"
        progress_file.write_text(json.dumps({"fetched_gids": ["gid1", "gid2"]}))
        assert _load_progress(tmp_path) == {"gid1", "gid2"}

    def test_returns_empty_when_empty_list(self, tmp_path):
        progress_file = tmp_path / "progress.json"
        progress_file.write_text(json.dumps({"fetched_gids": []}))
        assert _load_progress(tmp_path) == set()


class TestSaveProgress:
    def test_creates_dir_and_saves(self, tmp_path):
        out = tmp_path / "sub"
        _save_progress(out, {"a", "b"})
        data = json.loads((out / "progress.json").read_text())
        assert set(data["fetched_gids"]) == {"a", "b"}

    def test_overwrites_existing(self, tmp_path):
        _save_progress(tmp_path, {"old"})
        _save_progress(tmp_path, {"new"})
        data = json.loads((tmp_path / "progress.json").read_text())
        assert data["fetched_gids"] == ["new"]


# ---------------------------------------------------------------------------
# _matches_query
# ---------------------------------------------------------------------------


class TestMatchesQuery:
    def test_true_when_identical(self):
        nodes = [{"field": "FullText", "value": "test"}]
        cached = {"query": {"fieldNodes": nodes}}
        config = {"fieldNodes": nodes}
        assert _matches_query(cached, config) is True

    def test_false_when_different(self):
        cached = {"query": {"fieldNodes": [{"field": "FullText", "value": "old"}]}}
        config = {"fieldNodes": [{"field": "FullText", "value": "new"}]}
        assert _matches_query(cached, config) is False

    def test_false_when_no_query_key(self):
        cached = {"results": []}
        config = {"fieldNodes": []}
        assert _matches_query(cached, config) is False

    def test_false_when_empty_nodes(self):
        cached = {"query": {"fieldNodes": []}}
        config = {"fieldNodes": [{"field": "FullText", "value": "test"}]}
        assert _matches_query(cached, config) is False


# ---------------------------------------------------------------------------
# _save_search_results
# ---------------------------------------------------------------------------


class TestSaveSearchResults:
    def test_saves_enhanced_format(self, tmp_path):
        results = [{"gid": "g1", "title": "t1"}]
        config = {"fieldNodes": [{"field": "FullText", "value": "test"}]}
        now = datetime(2026, 1, 1)
        _save_search_results(
            tmp_path,
            results,
            config,
            started_at=now,
            completed_at=now,
        )
        data = json.loads((tmp_path / "search_results.json").read_text())
        assert "query" in data
        assert "total_unique" in data
        assert data["total_unique"] == 1
        assert data["results"] == results

    def test_includes_query_metadata(self, tmp_path):
        config = {"fieldNodes": [{"field": "FullText", "value": "抗诉"}]}
        _save_search_results(
            tmp_path,
            [],
            config,
            started_at=datetime(2026, 1, 1),
            completed_at=datetime(2026, 1, 2),
        )
        data = json.loads((tmp_path / "search_results.json").read_text())
        assert data["query"]["fieldNodes"] == config["fieldNodes"]


# ---------------------------------------------------------------------------
# _save_all
# ---------------------------------------------------------------------------


class TestSaveAll:
    @patch("src.crawler.export_excel")
    @patch("src.crawler.export_json")
    def test_saves_json_and_progress(self, mock_json, mock_excel, tmp_path):
        logger = MagicMock()
        results = [{"gid": "g1", "full_text": "x" * 600}]
        fetched = {"g1"}
        _save_all(results, fetched, tmp_path, logger)
        mock_json.assert_called_once()
        mock_excel.assert_called_once()

    @patch("src.crawler.export_excel", side_effect=Exception("boom"))
    @patch("src.crawler.export_json")
    def test_handles_excel_failure(self, mock_json, mock_excel, tmp_path):
        logger = MagicMock()
        results = [{"gid": "g1", "full_text": "x" * 600}]
        fetched = {"g1"}
        # Should not raise
        _save_all(results, fetched, tmp_path, logger)
        mock_json.assert_called_once()

    @patch("src.crawler.export_excel")
    @patch("src.crawler.export_json")
    def test_saves_progress_file(self, mock_json, mock_excel, tmp_path):
        logger = MagicMock()
        _save_all([{"gid": "g1", "full_text": "short"}], {"g1"}, tmp_path, logger)
        progress = json.loads((tmp_path / "progress.json").read_text())
        assert "g1" in progress["fetched_gids"]


# ---------------------------------------------------------------------------
# run_search — year-by-year pagination
# ---------------------------------------------------------------------------


class TestRunSearch:
    @patch("src.crawler.time.sleep")
    @patch("src.crawler.search_api")
    def test_collects_unique_gids(self, mock_api, mock_sleep, tmp_path):
        """Year-by-year pagination deduplicates gids across sort orders."""

        def api_side_effect(page, ctx, body):
            gb = body.get("groupBy", {})
            year = gb.get("LastInstanceDate", "")
            if year == "2025":
                return {
                    "data": [
                        {"gid": "g1", "title": "t1"},
                        {"gid": "g2", "title": "t2"},
                    ],
                    "total": 2,
                }
            if year == "2024":
                return {
                    "data": [
                        {"gid": "g2", "title": "t2"},
                        {"gid": "g3", "title": "t3"},
                    ],
                    "total": 2,
                }
            return {"data": [], "total": 0}

        mock_api.side_effect = api_side_effect
        config = {
            "fieldNodes": [{"field": "FullText", "value": "test"}],
            "settings": {"max_pages": 1},
        }
        logger = MagicMock()
        results = run_search(config, "fake_page", "fake_token", tmp_path, logger)

        gids = {r["gid"] for r in results}
        assert gids == {"g1", "g2", "g3"}
        assert len(results) == 3

    @patch("src.crawler.time.sleep")
    @patch("src.crawler.search_api")
    def test_saves_search_results(self, mock_api, mock_sleep, tmp_path):
        """Verify search_results.json has query and total_unique."""
        mock_api.return_value = {"data": [], "total": 0}

        config = {
            "fieldNodes": [{"field": "FullText", "value": "抗诉"}],
            "settings": {"max_pages": 1},
        }
        logger = MagicMock()
        run_search(config, "fake_page", "fake_token", tmp_path, logger)

        cache_file = tmp_path / "search_results.json"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert "query" in data
        assert "total_unique" in data

    @patch("src.crawler.time.sleep")
    @patch("src.crawler.search_api")
    def test_skips_when_cache_matches_and_complete(
        self, mock_api, mock_sleep, tmp_path
    ):
        """Pre-write complete cache with matching fieldNodes → search_api NOT called."""
        config = {
            "fieldNodes": [{"field": "FullText", "value": "抗诉"}],
            "settings": {"max_pages": 1},
        }
        # Write matching complete cache (last year = 2000)
        cache = {
            "query": {"fieldNodes": config["fieldNodes"]},
            "results": [
                {"gid": "g1", "title": "t1", "search_year": 2000},
            ],
        }
        (tmp_path / "search_results.json").write_text(json.dumps(cache))

        logger = MagicMock()
        results = run_search(config, "fake_page", "fake_token", tmp_path, logger)

        mock_api.assert_not_called()
        assert len(results) == 1

    @patch("src.crawler.time.sleep")
    @patch("src.crawler.search_api")
    def test_resumes_when_cache_incomplete(self, mock_api, mock_sleep, tmp_path):
        """Partial cache with last_year > 2000 → search_api IS called for remaining years."""
        config = {
            "fieldNodes": [{"field": "FullText", "value": "抗诉"}],
            "settings": {"max_pages": 1},
        }
        # Write matching but incomplete cache (last year = 2024, so resumes from 2023)
        cache = {
            "query": {"fieldNodes": config["fieldNodes"]},
            "results": [
                {"gid": "g1", "title": "t1", "search_year": 2024},
            ],
        }
        (tmp_path / "search_results.json").write_text(json.dumps(cache))

        mock_api.return_value = {"data": [], "total": 0}
        logger = MagicMock()
        run_search(config, "fake_page", "fake_token", tmp_path, logger)

        mock_api.assert_called()

    @patch("src.crawler.time.sleep")
    @patch("src.crawler.search_api")
    def test_passes_group_by_year(self, mock_api, mock_sleep, tmp_path):
        """Each search_api call should include groupBy with LastInstanceDate."""
        call_bodies = []

        def capture_api(page, ctx, body):
            call_bodies.append(body)
            return {"data": [], "total": 0}

        mock_api.side_effect = capture_api
        config = {
            "fieldNodes": [{"field": "FullText", "value": "test"}],
            "settings": {"max_pages": 1},
        }
        logger = MagicMock()
        run_search(config, "fake_page", "fake_token", tmp_path, logger)

        for body in call_bodies:
            assert "LastInstanceDate" in body.get("groupBy", {})

    @patch("src.crawler.time.sleep")
    @patch("src.crawler.search_api")
    def test_uses_all_sort_orders(self, mock_api, mock_sleep, tmp_path):
        """For each year, all 4 sort orders should be tried."""
        years_seen = set()

        def track_api(page, ctx, body):
            gb = body.get("groupBy", {})
            year = gb.get("LastInstanceDate", "")
            if year == "2025":
                years_seen.add(body.get("orderbyExpression"))
            return {"data": [], "total": 0}

        mock_api.side_effect = track_api
        config = {
            "fieldNodes": [{"field": "FullText", "value": "test"}],
            "settings": {"max_pages": 1},
        }
        logger = MagicMock()
        run_search(config, "fake_page", "fake_token", tmp_path, logger)

        assert len(years_seen) == 4


# ---------------------------------------------------------------------------
# run_fetch
# ---------------------------------------------------------------------------


class TestRunFetch:
    @patch("src.crawler.time.sleep")
    @patch("src.crawler.parse_case")
    @patch("src.crawler.authenticate", return_value="token123")
    @patch("src.crawler.launch_browser")
    def test_handles_old_list_format(
        self,
        mock_launch,
        mock_auth,
        mock_parse,
        mock_sleep,
        tmp_path,
    ):
        """run_fetch handles old-format search_results.json (plain list)."""
        from unittest.mock import MagicMock as MM

        # Write old-format cache (plain list)
        cases_meta = [
            {"gid": "g1", "title": "t1"},
        ]
        (tmp_path / "search_results.json").write_text(json.dumps(cases_meta))

        # Write empty results
        (tmp_path / "pkulaw_cases.json").write_text("[]")

        mock_parse.return_value = {"gid": "g1", "title": "t1", "full_text": "x" * 600}

        # Mock browser — evaluate must return int for HTML length checks
        mock_pw, mock_browser, mock_ctx, mock_page = MM(), MM(), MM(), MM()
        mock_page.evaluate.return_value = 2000  # > 1000, breaks inner wait loop
        mock_page.content.return_value = (
            "<html><body><div class='fulltext-wrap'>text</div></body></html>"
        )
        mock_launch.return_value = (mock_pw, mock_browser, mock_ctx, mock_page)

        # Mock close_browser
        with patch("src.crawler.close_browser"):
            config = {
                "fieldNodes": [],
                "settings": {
                    "delay": 0.1,
                    "browser_path": "/usr/bin/chromium",
                    "headless": True,
                },
            }
            logger = MM()
            result = run_fetch(config, tmp_path, logger)

        assert len(result) == 1
        assert result[0]["gid"] == "g1"

    @patch("src.crawler.time.sleep")
    @patch("src.crawler.parse_case")
    @patch("src.crawler.authenticate", return_value="token123")
    @patch("src.crawler.launch_browser")
    def test_handles_new_dict_format(
        self,
        mock_launch,
        mock_auth,
        mock_parse,
        mock_sleep,
        tmp_path,
    ):
        """run_fetch handles new-format search_results.json (dict with 'results' key)."""
        from unittest.mock import MagicMock as MM

        # Write new-format cache
        cache = {
            "query": {"fieldNodes": []},
            "results": [{"gid": "g1", "title": "t1"}],
        }
        (tmp_path / "search_results.json").write_text(json.dumps(cache))
        (tmp_path / "pkulaw_cases.json").write_text("[]")

        mock_parse.return_value = {"gid": "g1", "title": "t1", "full_text": "x" * 600}

        mock_pw, mock_browser, mock_ctx, mock_page = MM(), MM(), MM(), MM()
        mock_page.evaluate.return_value = 2000  # > 1000, breaks inner wait loop
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
                },
            }
            logger = MM()
            result = run_fetch(config, tmp_path, logger)

        assert len(result) == 1

    @patch("src.crawler.time.sleep")
    @patch("src.crawler.parse_case")
    @patch("src.crawler.authenticate", return_value="token123")
    @patch("src.crawler.launch_browser")
    def test_max_cases_stops_at_limit(
        self, mock_launch, mock_auth, mock_parse, mock_sleep, tmp_path
    ):
        """run_fetch stops when total fetched count reaches max_cases."""
        from unittest.mock import MagicMock as MM

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

    @patch("src.crawler.time.sleep")
    @patch("src.crawler.parse_case")
    @patch("src.crawler.authenticate", return_value="token123")
    @patch("src.crawler.launch_browser")
    def test_max_cases_with_resume(
        self, mock_launch, mock_auth, mock_parse, mock_sleep, tmp_path
    ):
        """run_fetch respects max_cases including already-fetched progress."""
        from unittest.mock import MagicMock as MM

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


# ---------------------------------------------------------------------------
# cmd_crawl — integration of search → fetch → export
# ---------------------------------------------------------------------------


class TestCmdCrawl:
    def test_calls_search_fetch_export(self, tmp_path):
        config = {
            "fieldNodes": [{"field": "FullText", "value": "test"}],
            "settings": {
                "output_dir": str(tmp_path),
                "format": ["json", "csv"],
                "delay": 0,
                "browser": "/usr/bin/chromium",
                "headless": True,
            },
        }
        with (
            patch(
                "pkulaw.launch_browser",
                return_value=(MagicMock(), MagicMock(), MagicMock(), MagicMock()),
            ),
            patch("pkulaw.authenticate", return_value="fake_token"),
            patch("pkulaw.close_browser"),
            patch(
                "pkulaw.run_search", return_value=[{"gid": "g1", "title": "C1"}]
            ) as mock_search,
            patch(
                "pkulaw.run_fetch",
                return_value=[{"gid": "g1", "title": "C1", "full_text": "text"}],
            ) as mock_fetch,
            patch("pkulaw.export_json") as mock_ej,
            patch("pkulaw.export_csv") as mock_ec,
        ):
            from pkulaw import cmd_crawl

            cmd_crawl(config)

        mock_search.assert_called_once()
        mock_fetch.assert_called_once()
        mock_ej.assert_called_once()
        mock_ec.assert_called_once()


class TestInterruptSummary:
    def test_prints_interrupt_summary(self, tmp_path, capsys):
        from pkulaw import _print_interrupt_summary

        cache = {
            "total_unique": 2716683,
            "results": [{"gid": f"g{i}"} for i in range(100)],
        }
        (tmp_path / "search_results.json").write_text(json.dumps(cache))
        (tmp_path / "progress.json").write_text(
            json.dumps({"fetched_gids": [f"g{i}" for i in range(1500)]})
        )
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

        cache = {"total_unique": 500, "results": [{"gid": "g1"}]}
        (tmp_path / "search_results.json").write_text(json.dumps(cache))
        (tmp_path / "progress.json").write_text(json.dumps({"fetched_gids": ["g1"]}))
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
