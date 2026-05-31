"""Tests for pkulaw.py cmd_status -- enhanced status command."""

import json
from pathlib import Path

from pkulaw import cmd_status


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


class TestCmdStatusNoData:
    def test_shows_no_active_task(self, tmp_path, capsys):
        cmd_status(output_dir=tmp_path / "nonexistent")
        output = capsys.readouterr().out
        assert "无活跃任务" in output

    def test_empty_output_dir(self, tmp_path, capsys):
        (tmp_path / "output").mkdir()
        cmd_status(output_dir=tmp_path / "output")
        output = capsys.readouterr().out
        assert "PKULaw 爬取状态" in output


class TestCmdStatusSearchResults:
    def test_shows_query_from_new_format(self, tmp_path, capsys):
        d = tmp_path / "out"
        _write_json(
            d / "search_results.json",
            {
                "query": {"fieldNodes": [{"field": "FullText", "value": "抗诉"}]},
                "total_unique": 500,
                "results": [],
            },
        )
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "全文" in output
        assert "抗诉" in output
        assert "500" in output

    def test_handles_old_list_format(self, tmp_path, capsys):
        d = tmp_path / "out"
        results = [{"gid": f"g{i}", "title": f"C{i}"} for i in range(200)]
        _write_json(d / "search_results.json", results)
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "200" in output

    def test_shows_select_field_names(self, tmp_path, capsys):
        d = tmp_path / "out"
        _write_json(
            d / "search_results.json",
            {
                "query": {
                    "fieldNodes": [
                        {"field": "FullText", "value": "抗诉"},
                        {"field": "TrialStep", "values": ["002", "003"]},
                    ]
                },
                "total_unique": 100,
                "results": [],
            },
        )
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "审理程序" in output
        assert "二审" in output


class TestCmdStatusProgress:
    def test_shows_fetch_progress(self, tmp_path, capsys):
        d = tmp_path / "out"
        _write_json(
            d / "search_results.json",
            {
                "query": {"fieldNodes": []},
                "total_unique": 1000,
                "results": [],
            },
        )
        _write_json(
            d / "progress.json",
            {
                "fetched_gids": [f"g{i}" for i in range(500)],
            },
        )
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "500" in output
        assert "1,000" in output
        assert "50.0%" in output


class TestCmdStatusResultsFile:
    def test_shows_valid_data_count(self, tmp_path, capsys):
        d = tmp_path / "out"
        _write_json(
            d / "search_results.json",
            {
                "query": {"fieldNodes": []},
                "total_unique": 10,
                "results": [],
            },
        )
        _write_json(d / "progress.json", {"fetched_gids": [f"g{i}" for i in range(5)]})
        cases = [
            {"gid": f"g{i}", "full_text": "x" * 600 if i < 3 else "short"}
            for i in range(5)
        ]
        _write_json(d / "pkulaw_cases.json", cases)
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "有效数据" in output
        assert "60.0%" in output

    def test_shows_file_size(self, tmp_path, capsys):
        d = tmp_path / "out"
        _write_json(
            d / "search_results.json",
            {
                "query": {"fieldNodes": []},
                "total_unique": 5,
                "results": [],
            },
        )
        _write_json(d / "progress.json", {"fetched_gids": ["g1"]})
        _write_json(d / "pkulaw_cases.json", [{"gid": "g1", "full_text": "t"}])
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "输出文件" in output


class TestCmdStatusLog:
    def test_shows_last_log_lines(self, tmp_path, capsys):
        d = tmp_path / "out"
        d.mkdir(parents=True, exist_ok=True)
        (d / "search_results.json").write_text("[]")
        log_lines = [f"[2026-05-29 01:28:{i:02d}] INFO line {i}" for i in range(25)]
        (d / "crawl.log").write_text("\n".join(log_lines))
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "最近日志" in output
        assert "line 24" in output

    def test_no_log_shows_nothing(self, tmp_path, capsys):
        d = tmp_path / "out"
        d.mkdir(parents=True, exist_ok=True)
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "最近日志" not in output


class TestCmdStatusProcess:
    def test_shows_stopped_when_no_process(self, tmp_path, capsys):
        d = tmp_path / "out"
        d.mkdir(parents=True, exist_ok=True)
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "已停止" in output
