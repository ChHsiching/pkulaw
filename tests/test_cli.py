"""Tests for src/cli.py — argument parsing and SearchConfig building."""

import json
from pathlib import Path

import pytest

from src.cli import build_search_config, create_parser


class TestParserHelp:
    def test_main_help(self):
        parser = create_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_estimate_help(self):
        parser = create_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["estimate", "--help"])
        assert exc_info.value.code == 0

    def test_crawl_help(self):
        parser = create_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["crawl", "--help"])
        assert exc_info.value.code == 0

    def test_status_no_help_needed(self):
        parser = create_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"


class TestParserEstimateArgs:
    def test_full_text(self):
        parser = create_parser()
        args = parser.parse_args(["estimate", "--full-text", "抗诉"])
        assert args.full_text == "抗诉"

    def test_trial_step(self):
        parser = create_parser()
        args = parser.parse_args(["estimate", "--trial-step", "二审,再审"])
        assert args.trial_step == "二审,再审"

    def test_category(self):
        parser = create_parser()
        args = parser.parse_args(["estimate", "--category", "刑事"])
        assert args.category == "刑事"

    def test_multiple_flags(self):
        parser = create_parser()
        args = parser.parse_args(
            [
                "estimate",
                "--full-text",
                "抗诉",
                "--trial-step",
                "二审,再审",
                "--category",
                "刑事",
            ]
        )
        assert args.full_text == "抗诉"
        assert args.trial_step == "二审,再审"
        assert args.category == "刑事"

    def test_query_file(self):
        parser = create_parser()
        args = parser.parse_args(["estimate", "--query", "query.json"])
        assert args.query == "query.json"

    def test_date_range(self):
        parser = create_parser()
        args = parser.parse_args(["estimate", "--date-range", "2020-2025"])
        assert args.date_range == "2020-2025"

    def test_defaults(self):
        parser = create_parser()
        args = parser.parse_args(["estimate"])
        assert args.full_text is None
        assert args.delay == 0.5
        assert args.max_pages == 10
        assert args.format == "json,xlsx"
        assert args.output_dir == "output"


class TestParserCrawlArgs:
    def test_crawl_accepts_same_args_as_estimate(self):
        parser = create_parser()
        args = parser.parse_args(
            [
                "crawl",
                "--full-text",
                "抗诉",
                "--trial-step",
                "二审,再审",
            ]
        )
        assert args.command == "crawl"
        assert args.full_text == "抗诉"

    def test_crawl_has_output_options(self):
        parser = create_parser()
        args = parser.parse_args(
            [
                "crawl",
                "--format",
                "json,csv",
                "--output-dir",
                "/tmp/out",
                "--chunk-size",
                "500",
            ]
        )
        assert args.format == "json,csv"
        assert args.output_dir == "/tmp/out"
        assert args.chunk_size == 500

    def test_crawl_accepts_max_cases(self):
        parser = create_parser()
        args = parser.parse_args(["crawl", "--max-cases", "2000"])
        assert args.max_cases == 2000

    def test_max_cases_default_is_zero(self):
        parser = create_parser()
        args = parser.parse_args(["crawl"])
        assert args.max_cases == 0


class TestBuildSearchConfig:
    def test_text_field(self):
        parser = create_parser()
        args = parser.parse_args(["estimate", "--full-text", "抗诉"])
        config = build_search_config(args)
        assert any(
            n["field"] == "FullText" and n["value"] == "抗诉"
            for n in config["fieldNodes"]
        )

    def test_select_field_resolves_ids(self):
        parser = create_parser()
        args = parser.parse_args(["estimate", "--trial-step", "二审,再审"])
        config = build_search_config(args)
        ts = next(n for n in config["fieldNodes"] if n["field"] == "TrialStep")
        assert ts["values"] == ["002", "003"]

    def test_hierarchical_field(self):
        parser = create_parser()
        args = parser.parse_args(["estimate", "--category", "刑事>危害公共安全罪"])
        config = build_search_config(args)
        cat = next(n for n in config["fieldNodes"] if n["field"] == "CategoryNew")
        assert cat["values"] == ["001002"]

    def test_settings_defaults(self):
        parser = create_parser()
        args = parser.parse_args(["estimate"])
        config = build_search_config(args)
        assert config["settings"]["delay"] == 0.5
        assert config["settings"]["max_pages"] == 10
        assert config["settings"]["output_dir"] == "output"

    def test_settings_custom(self):
        parser = create_parser()
        args = parser.parse_args(
            [
                "crawl",
                "--delay",
                "1.0",
                "--max-pages",
                "5",
                "--format",
                "json",
            ]
        )
        config = build_search_config(args)
        assert config["settings"]["delay"] == 1.0
        assert config["settings"]["max_pages"] == 5
        assert config["settings"]["format"] == ["json"]

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

    def test_date_range(self):
        parser = create_parser()
        args = parser.parse_args(["estimate", "--date-range", "2020-2025"])
        config = build_search_config(args)
        dr = next(n for n in config["fieldNodes"] if n["field"] == "LastInstanceDate")
        assert dr["range"] == ["2020", "2025"]

    def test_no_fields_produced_when_no_args(self):
        parser = create_parser()
        args = parser.parse_args(["estimate"])
        config = build_search_config(args)
        assert config["fieldNodes"] == []


class TestBuildSearchConfigFromJson:
    def test_json_file_loading(self, tmp_path):
        query_file = tmp_path / "query.json"
        query_file.write_text(
            json.dumps(
                {
                    "fieldNodes": [
                        {"field": "FullText", "value": "抗诉"},
                        {"field": "TrialStep", "values": ["二审", "再审"]},
                    ],
                },
                ensure_ascii=False,
            )
        )

        parser = create_parser()
        args = parser.parse_args(["estimate", "--query", str(query_file)])
        config = build_search_config(args)

        assert any(
            n["field"] == "FullText" and n["value"] == "抗诉"
            for n in config["fieldNodes"]
        )
        ts = next(n for n in config["fieldNodes"] if n["field"] == "TrialStep")
        assert ts["values"] == ["002", "003"]

    def test_json_with_category_hierarchy(self, tmp_path):
        query_file = tmp_path / "query.json"
        query_file.write_text(
            json.dumps(
                {
                    "fieldNodes": [
                        {
                            "field": "CategoryNew",
                            "values": ["刑事"],
                            "children": {"刑事": ["侵犯财产罪"]},
                        },
                    ],
                },
                ensure_ascii=False,
            )
        )

        parser = create_parser()
        args = parser.parse_args(["estimate", "--query", str(query_file)])
        config = build_search_config(args)
        cat = next(n for n in config["fieldNodes"] if n["field"] == "CategoryNew")
        assert "001" in cat["values"]
        children = cat.get("children", {})
        assert "001005" in children.get("001", [])

    def test_cli_overrides_json(self, tmp_path):
        query_file = tmp_path / "query.json"
        query_file.write_text(
            json.dumps(
                {
                    "fieldNodes": [
                        {"field": "FullText", "value": "original"},
                    ],
                },
                ensure_ascii=False,
            )
        )

        parser = create_parser()
        args = parser.parse_args(
            [
                "estimate",
                "--query",
                str(query_file),
                "--full-text",
                "override",
            ]
        )
        config = build_search_config(args)
        ft = next(n for n in config["fieldNodes"] if n["field"] == "FullText")
        assert ft["value"] == "override"

    def test_json_settings(self, tmp_path):
        query_file = tmp_path / "query.json"
        query_file.write_text(
            json.dumps(
                {
                    "fieldNodes": [],
                    "settings": {"delay": 1.0, "max_pages": 5},
                },
                ensure_ascii=False,
            )
        )

        parser = create_parser()
        args = parser.parse_args(["estimate", "--query", str(query_file)])
        config = build_search_config(args)
        assert config["settings"]["delay"] == 1.0
        assert config["settings"]["max_pages"] == 5
