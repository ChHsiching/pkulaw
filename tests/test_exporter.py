"""Tests for src/exporter.py — export functions."""

import csv

from src.exporter import _build_column_order, export_csv


class TestExportCsv:
    def test_creates_file_with_utf8_bom(self, tmp_path):
        cases = [{"gid": "abc", "title": "Test", "full_text": "text"}]
        path = tmp_path / "out.csv"
        export_csv(cases, path)
        raw = path.read_bytes()
        assert raw[:3] == b"\xef\xbb\xbf"

    def test_dynamic_columns(self, tmp_path):
        cases = [
            {"gid": "1", "title": "A", "custom_col": "x"},
            {"gid": "2", "title": "B", "other_col": "y"},
        ]
        export_csv(cases, tmp_path / "out.csv")
        lines = (
            (tmp_path / "out.csv").read_text(encoding="utf-8-sig").strip().split("\n")
        )
        header = lines[0]
        assert "custom_col" in header
        assert "other_col" in header

    def test_sanitizes_newlines(self, tmp_path):
        cases = [{"gid": "1", "title": "Line1\nLine2\rLine3", "full_text": "t"}]
        export_csv(cases, tmp_path / "out.csv")
        reader = csv.reader((tmp_path / "out.csv").open(encoding="utf-8-sig"))
        rows = list(reader)
        assert len(rows) == 2
        data_row = rows[1]
        title_val = data_row[rows[0].index("title")]
        assert "\n" not in title_val
        assert "\r" not in title_val

    def test_empty_cases(self, tmp_path):
        export_csv([], tmp_path / "out.csv")
        content = (tmp_path / "out.csv").read_text(encoding="utf-8-sig").strip()
        assert content == ""

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "out.csv"
        export_csv([{"gid": "1", "title": "T"}], path)
        assert path.exists()
