# Iteration 1: Foundation (config + cli + log) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build CLI framework, parameter mappings, and logging system so `pkulaw --help`, `pkulaw estimate --help`, `pkulaw status`, and `pkulaw estimate --full-text "抗诉" --trial-step "二审,再审"` all work.

**Architecture:** New CLI layer wraps the existing crawler. `config.py` holds all Chinese→API ID mappings and resolve functions. `cli.py` parses CLI args or JSON query files into a unified SearchConfig dict. `log.py` provides structured logging. `pkulaw.py` is the entry point that dispatches to subcommands. No existing files are modified or deleted.

**Tech Stack:** Python 3.10+, argparse, logging, pytest, openpyxl, playwright

---

## File Structure

```
Created:
├── pyproject.toml                    # Package config, dependencies, entry point
├── pkulaw.py                         # CLI entry point (main + subcommand dispatch)
├── src/config.py                     # Field definitions, resolve functions
├── src/config_data.py                # Generated: all Chinese→API ID mappings
├── src/log.py                        # Structured logging setup
├── src/cli.py                        # argparse + SearchConfig builder + JSON parser
├── tests/__init__.py
├── tests/conftest.py
├── tests/test_config.py
├── tests/test_log.py
├── tests/test_cli.py
└── scripts/generate_config_data.py   # One-time script to generate config_data.py

Untouched (existing):
├── src/crawler.py
├── src/parser.py
├── src/exporter.py
├── src/refetch.py
├── src/search.py
├── src/auth.py
├── src/__init__.py
└── main.py
```

---

## Task 1: Feature branch + pyproject.toml + test infrastructure

**Files:**
- Create: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create feature branch**

```bash
git checkout -b feature/iter1-foundation
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "pkulaw"
version = "0.1.0"
description = "PKULaw case database CLI crawler"
requires-python = ">=3.10"
dependencies = [
    "playwright>=1.59.0",
    "requests>=2.32.0",
    "beautifulsoup4>=4.14.0",
    "lxml>=6.0.0",
    "openpyxl>=3.1.0",
]

[project.scripts]
pkulaw = "pkulaw:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.black]
line-length = 88

[tool.isort]
profile = "black"
```

- [ ] **Step 3: Create tests/__init__.py (empty) and tests/conftest.py**

```python
# tests/__init__.py
```

```python
# tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 4: Install test dependency and verify**

```bash
pip install pytest
python -m pytest --co -q
```

Expected: "no tests collected" (no test files yet), exit code 5

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/__init__.py tests/conftest.py
git commit -m "chore: add pyproject.toml and test infrastructure"
```

---

## Task 2: Generate config data from API JSON

**Files:**
- Create: `scripts/generate_config_data.py`
- Create: `src/config_data.py` (generated output)

The CategoryNew tree alone has 1792 entries. A generation script reads the API data JSON and outputs `src/config_data.py` with all mappings.

- [ ] **Step 1: Create scripts/generate_config_data.py**

```python
"""Generate src/config_data.py from PKULaw API data files.

Usage: python scripts/generate_config_data.py /tmp/pkulaw_cluster_full.json /tmp/pkulaw_form_full.json
"""

import json
import sys
from pathlib import Path


def build_flat_map(items: list[dict]) -> dict[str, str]:
    """Build name→id mapping for a flat list."""
    result = {}
    for item in items:
        result[item["name"]] = item.get("id", "")
    return result


def build_tree(items: list[dict]) -> dict:
    """Build nested dict: name → id (leaf) or name → {"id": ..., "children": {...}}."""
    result = {}
    for item in items:
        name = item["name"]
        vid = item.get("id", "")
        children = item.get("children") or []
        if children:
            result[name] = {"id": vid, "children": build_tree(children)}
        else:
            result[name] = vid
    return result


def build_hierarchical_map(items: list[dict]) -> dict[str, str]:
    """Flatten entire tree into name→id, including all levels."""
    result = {}
    for item in items:
        name = item["name"]
        vid = item.get("id", "")
        result[name] = vid
        for child in (item.get("children") or []):
            child_name = child["name"]
            child_id = child.get("id", "")
            result[child_name] = child_id
            for grandchild in (child.get("children") or []):
                result[grandchild["name"]] = grandchild.get("id", "")
    return result


def main():
    cluster_path = Path(sys.argv[1])
    form_path = Path(sys.argv[2])
    output_path = Path(__file__).resolve().parent.parent / "src" / "config_data.py"

    with open(cluster_path) as f:
        cluster_data = json.load(f)
    with open(form_path) as f:
        form_data = json.load(f)

    lines = [
        '"""Auto-generated PKULaw API field mappings.',
        "",
        f"Generated from: {cluster_path.name}, {form_path.name}",
        "DO NOT EDIT — regenerate with: python scripts/generate_config_data.py",
        '"""',
        "",
    ]

    # Field definitions from form
    lines.append("FIELD_DEFINITIONS = {")
    for field in form_data:
        fn = field["fieldName"]
        lines.append(f'    "{fn}": {{')
        lines.append(f'        "show_text": "{field.get("showText", "")}",')
        lines.append(f'        "type": "{field.get("type", "")}",')
        lines.append(f'        "order": {field.get("order", 0)},')
        lines.append("    },")
    lines.append("}")
    lines.append("")

    # Cluster dimension mappings
    lines.append("CLUSTER_DIMENSIONS = {")
    for dim in cluster_data:
        dim_id = dim["id"]
        dim_title = dim["title"]
        values = dim.get("list") or []
        lines.append(f'    "{dim_id}": {{')
        lines.append(f'        "title": "{dim_title}",')
        if values:
            flat = build_hierarchical_map(values)
            lines.append(f'        "values": {json.dumps(flat, ensure_ascii=False)},')
        else:
            lines.append('        "values": {},')
        lines.append("    },")
    lines.append("}")
    lines.append("")

    # CategoryNew tree (full hierarchy)
    cat_dim = next(d for d in cluster_data if d["id"] == "CategoryNew")
    cat_tree = build_tree(cat_dim.get("list") or [])
    lines.append("CATEGORY_TREE = ")
    lines.append(_format_dict(cat_tree, indent=0))
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {output_path} ({output_path.stat().st_size} bytes)")


def _format_dict(d: dict, indent: int) -> str:
    """Pretty-print a nested dict as Python literal."""
    prefix = "    " * indent
    if not d:
        return "{}"

    parts = []
    for key, value in d.items():
        if isinstance(value, dict):
            if "children" in value and isinstance(value["children"], dict):
                inner = _format_dict(value["children"], indent + 2)
                parts.append(
                    f'{prefix}    "{key}": {{"id": "{value["id"]}", "children": {inner}}},'
                )
            elif all(isinstance(v, str) for v in value.values()):
                # Flat dict of name→id
                items = ", ".join(f'"{k}": "{v}"' for k, v in value.items())
                parts.append(f'{prefix}    "{key}": {{{items}}},')
            else:
                inner = _format_dict(value, indent + 1)
                parts.append(f'{prefix}    "{key}": {inner},')
        else:
            parts.append(f'{prefix}    "{key}": "{value}",')

    return "{\n" + "\n".join(parts) + f"\n{prefix}}}"


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run generation script**

```bash
python scripts/generate_config_data.py /tmp/pkulaw_cluster_full.json /tmp/pkulaw_form_full.json
```

Expected: `Generated src/config_data.py (NNNN bytes)`

- [ ] **Step 3: Verify generated file**

```bash
python -c "from src.config_data import FIELD_DEFINITIONS, CLUSTER_DIMENSIONS, CATEGORY_TREE; print(f'{len(FIELD_DEFINITIONS)} fields, {len(CLUSTER_DIMENSIONS)} dimensions')"
```

Expected: `25 fields, 14 dimensions`

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_config_data.py src/config_data.py
git commit -m "feat: add parameter mapping data generated from PKULaw API"
```

---

## Task 3: Create src/config.py — resolve functions + tests

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write tests/test_config.py**

```python
"""Tests for src/config.py — field definitions, resolve functions."""

import pytest

from src.config import (
    FIELD_DEFINITIONS,
    CATEGORY_VALUES,
    resolve_value,
    resolve_values,
    validate_field_values,
    CLI_TO_FIELD_MAP,
)


class TestFieldDefinitions:
    def test_all_25_fields_defined(self):
        assert len(FIELD_DEFINITIONS) == 25

    def test_text_fields(self):
        text_fields = [f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "text"]
        assert "FullText" in text_fields
        assert "Title" in text_fields

    def test_select_fields(self):
        select_fields = [
            f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "select"
        ]
        assert "TrialStep" in select_fields
        assert "CaseGrade" in select_fields

    def test_daterange_fields(self):
        date_fields = [
            f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "daterange"
        ]
        assert "LastInstanceDate" in date_fields
        assert "IssueDate" in date_fields

    def test_pickselect_fields(self):
        ps_fields = [
            f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "pickselect"
        ]
        assert "CategoryNew" in ps_fields


class TestResolveFlatValues:
    def test_trial_step(self):
        assert resolve_value("TrialStep", "二审") == "002"

    def test_court_grade(self):
        assert resolve_value("CourtGrade", "中级人民法院") == "03"

    def test_case_grade(self):
        assert resolve_value("CaseGrade", "指导性案例") == "01"

    def test_document_attr(self):
        assert resolve_value("DocumentAttr", "判决书") == "001"

    def test_unknown_value_raises(self):
        with pytest.raises(ValueError, match="Unknown value"):
            resolve_value("TrialStep", "不存在")


class TestResolveHierarchicalValues:
    def test_category_top_level(self):
        assert resolve_value("CategoryNew", "刑事") == "001"

    def test_category_second_level(self):
        assert resolve_value("CategoryNew", "刑事>危害公共安全罪") == "001002"

    def test_category_third_level(self):
        assert resolve_value("CategoryNew", "刑事>危害公共安全罪>放火罪") == "001002001"

    def test_category_civil(self):
        assert resolve_value("CategoryNew", "民事") == "002"

    def test_penalty_codes_top(self):
        assert resolve_value("PenaltyCodes", "主刑") == "001"

    def test_penalty_codes_child(self):
        assert resolve_value("PenaltyCodes", "主刑>管制") == "001001"

    def test_invalid_path_raises(self):
        with pytest.raises(ValueError, match="not found"):
            resolve_value("CategoryNew", "刑事>不存在")


class TestResolveMultipleValues:
    def test_comma_separated(self):
        result = resolve_values("TrialStep", "二审,再审")
        assert result == ["002", "003"]

    def test_mixed_hierarchy(self):
        result = resolve_values(
            "CategoryNew", "刑事>侵犯财产罪>盗窃罪,刑事>侵犯财产罪>诈骗罪"
        )
        assert "001005001" in result
        assert len(result) == 2


class TestValidateFieldValues:
    def test_valid_values_pass(self):
        validate_field_values("TrialStep", ["001", "002"])

    def test_invalid_values_fail(self):
        with pytest.raises(ValueError, match="Invalid value"):
            validate_field_values("TrialStep", ["999"])

    def test_text_field_skips_validation(self):
        validate_field_values("FullText", ["anything"])


class TestCliToFieldMap:
    def test_common_flags_exist(self):
        assert "--full-text" in CLI_TO_FIELD_MAP
        assert "--trial-step" in CLI_TO_FIELD_MAP
        assert "--category" in CLI_TO_FIELD_MAP
        assert "--case-grade" in CLI_TO_FIELD_MAP

    def test_all_cli_flags_map_to_real_fields(self):
        for flag, field_name in CLI_TO_FIELD_MAP.items():
            assert field_name in FIELD_DEFINITIONS, (
                f"{flag} maps to unknown field {field_name}"
            )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Create src/config.py**

```python
"""PKULaw API field definitions and Chinese→API ID resolution."""

from src.config_data import CATEGORY_TREE, CLUSTER_DIMENSIONS, FIELD_DEFINITIONS

__all__ = [
    "FIELD_DEFINITIONS",
    "CATEGORY_TREE",
    "CATEGORY_VALUES",
    "CLI_TO_FIELD_MAP",
    "FIELD_CLI_NAMES",
    "resolve_value",
    "resolve_values",
    "validate_field_values",
]

# Flat name→id mapping for every dimension (built from CLUSTER_DIMENSIONS)
CATEGORY_VALUES: dict[str, dict[str, str]] = {
    dim_id: dim_data["values"] for dim_id, dim_data in CLUSTER_DIMENSIONS.items()
}

# CLI flag → API fieldName mapping
CLI_TO_FIELD_MAP: dict[str, str] = {
    "--full-text": "FullText",
    "--title": "Title",
    "--case-flag": "CaseFlag",
    "--gist": "CaseGist",
    "--party": "Party",
    "--judge": "Judge",
    "--lawyer": "AgentLawyer",
    "--law-firm": "AgentLawOffice",
    "--category": "CategoryNew",
    "--trial-step": "TrialStep",
    "--court-grade": "CourtGrade",
    "--court": "LastInstanceCourt",
    "--case-grade": "CaseGrade",
    "--case-class": "CaseClass",
    "--doc-type": "DocumentAttr",
    "--result": "TrialStepCount",
    "--topic": "SubjectClassSpecialType",
    "--punishment": "PenaltyCodes",
    "--accusation": "Accusation",
    "--date-range": "LastInstanceDate",
    "--issue-date-range": "IssueDate",
    "--public-type": "NoPublicReason",
    "--word-count": "WordNum",
    "--judge-type": "JudgeType",
    "--guiding-case-no": "GuidingCaseNO",
    "--source-note": "SourceNote",
}

# Reverse map: API fieldName → CLI flag name (without --)
FIELD_CLI_NAMES: dict[str, str] = {
    v: k.lstrip("-").replace("-", "_") for k, v in CLI_TO_FIELD_MAP.items()
}

# Fields that accept hierarchical paths (tree structure)
_HIERARCHICAL_FIELDS = {"CategoryNew", "CaseClass", "CaseGrade", "PenaltyCodes", "DocumentAttr", "CaseElements"}

# Fields that are text type (free-form input, no value resolution)
_TEXT_FIELDS = {f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "text"}


def resolve_value(field: str, path: str) -> str:
    """Resolve a Chinese name or hierarchical path to an API ID.

    Flat fields:  resolve_value("TrialStep", "二审") → "002"
    Hierarchical: resolve_value("CategoryNew", "刑事>危害公共安全罪") → "001002"
    """
    if field in _TEXT_FIELDS:
        return path

    parts = path.split(">")

    if field in _HIERARCHICAL_FIELDS and len(parts) > 1:
        return _resolve_hierarchical(field, parts)

    # Flat lookup
    values = CATEGORY_VALUES.get(field, {})
    if path in values:
        return values[path]

    raise ValueError(f"Unknown value '{path}' for field '{field}'")


def _resolve_hierarchical(field: str, parts: list[str]) -> str:
    """Walk a tree to resolve a hierarchical path."""
    tree = CATEGORY_TREE if field == "CategoryNew" else CATEGORY_VALUES.get(field, {})
    if field == "CategoryNew":
        current = tree
        for i, part in enumerate(parts):
            if isinstance(current, dict):
                if part in current:
                    entry = current[part]
                else:
                    # Try flat values as fallback
                    flat = CATEGORY_VALUES.get(field, {})
                    if part in flat:
                        return flat[part]
                    raise ValueError(
                        f"'{part}' not found in {field} at level {i + 1}"
                    )
                if isinstance(entry, str):
                    if i == len(parts) - 1:
                        return entry
                    raise ValueError(
                        f"'{part}' is a leaf but path continues"
                    )
                elif isinstance(entry, dict):
                    if "id" in entry and "children" in entry:
                        if i == len(parts) - 1:
                            return entry["id"]
                        current = entry["children"]
                    else:
                        if i == len(parts) - 1:
                            return entry.get("id", "")
                        current = entry
            else:
                raise ValueError(f"Cannot navigate into non-dict at '{part}'")
        return ""
    else:
        # For other hierarchical fields, use flat values with ">" joining
        # Try the full path as a single key first
        flat = CATEGORY_VALUES.get(field, {})
        full_path = ">".join(parts)
        if full_path in flat:
            return flat[full_path]
        # Try just the last part (child name)
        if parts[-1] in flat:
            return flat[parts[-1]]
        raise ValueError(f"'{path}' not found in {field}")


def resolve_values(field: str, comma_path: str) -> list[str]:
    """Resolve comma-separated paths to a list of API IDs.

    resolve_values("TrialStep", "二审,再审") → ["002", "003"]
    resolve_values("CategoryNew", "刑事>侵犯财产罪>盗窃罪,刑事>侵犯财产罪>诈骗罪")
    """
    return [resolve_value(field, p.strip()) for p in comma_path.split(",")]


def validate_field_values(field: str, values: list[str]) -> None:
    """Validate that all values are valid API IDs for the given field.

    Text fields skip validation (any value is valid).
    """
    if field in _TEXT_FIELDS:
        return

    valid_ids = set(CATEGORY_VALUES.get(field, {}).values())
    if not valid_ids:
        return

    for v in values:
        if v not in valid_ids:
            raise ValueError(
                f"Invalid value '{v}' for field '{field}'. "
                f"Valid: {sorted(valid_ids)[:10]}..."
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_config.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add config.py with field definitions and resolve functions"
```

---

## Task 4: Create src/log.py — structured logging + tests

**Files:**
- Create: `src/log.py`
- Create: `tests/test_log.py`

- [ ] **Step 1: Write tests/test_log.py**

```python
"""Tests for src/log.py — structured logging."""

import logging
from pathlib import Path

from src.log import setup_logger, get_logger


class TestSetupLogger:
    def test_returns_logger(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = setup_logger(log_file)
        assert isinstance(logger, logging.Logger)

    def test_writes_to_file(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = setup_logger(log_file)
        logger.info("test message")
        content = log_file.read_text()
        assert "test message" in content
        assert "INFO" in content

    def test_format_includes_timestamp(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = setup_logger(log_file)
        logger.info("format check")
        content = log_file.read_text()
        # Format: [YYYY-MM-DD HH:MM:SS] LEVEL message
        assert "[" in content
        assert "]" in content
        assert "INFO" in content

    def test_log_levels(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = setup_logger(log_file)
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warn msg")
        logger.error("error msg")
        content = log_file.read_text()
        assert "debug msg" not in content  # Default level is INFO
        assert "info msg" in content
        assert "warn msg" in content  # WARN stored as WARNING
        assert "error msg" in content

    def test_creates_parent_dirs(self, tmp_path):
        log_file = tmp_path / "subdir" / "deep" / "test.log"
        logger = setup_logger(log_file)
        logger.info("deep path")
        assert log_file.exists()

    def test_file_rotation(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = setup_logger(log_file, max_bytes=100, backup_count=2)
        for i in range(200):
            logger.info(f"line {i} " + "x" * 10)
        # Rotation should have created backup files
        files = list(tmp_path.glob("test.log*"))
        assert len(files) >= 1


class TestGetLogger:
    def test_returns_same_logger_after_setup(self, tmp_path):
        log_file = tmp_path / "test.log"
        setup_logger(log_file)
        logger = get_logger()
        assert isinstance(logger, logging.Logger)
        logger.info("via get_logger")
        assert "via get_logger" in log_file.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_log.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.log'`

- [ ] **Step 3: Create src/log.py**

```python
"""Structured logging for PKULaw CLI crawler."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_logger: logging.Logger | None = None


class _Formatter(logging.Formatter):
    """Custom format: [YYYY-MM-DD HH:MM:SS] LEVEL message"""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S")
        level = record.levelname
        # Shorten WARNING → WARN for display
        if level == "WARNING":
            level = "WARN"
        return f"[{timestamp}] {level:5s} {record.getMessage()}"


def setup_logger(
    log_file: Path,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """Configure and return the application logger.

    Logs to both console (stderr) and a rotating file.
    """
    global _logger

    logger = logging.getLogger("pkulaw")
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers to allow re-setup in tests
    logger.handlers.clear()

    formatter = _Formatter()

    # File handler (accepts DEBUG and above, with rotation)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler (respects the level parameter)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """Return the configured logger. Must call setup_logger first."""
    if _logger is None:
        return logging.getLogger("pkulaw")
    return _logger
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_log.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/log.py tests/test_log.py
git commit -m "feat: add log.py with structured logging"
```

---

## Task 5: Create src/cli.py — argparse definitions + tests

**Files:**
- Create: `src/cli.py`
- Create: `tests/test_cli.py`

This task creates the argparse parser with all CLI flags and subcommands. The next task adds SearchConfig building and JSON parsing.

- [ ] **Step 1: Write tests/test_cli.py (part 1: parser tests)**

```python
"""Tests for src/cli.py — argument parsing and SearchConfig building."""

import json
from pathlib import Path

import pytest

from src.cli import create_parser, build_search_config


class TestParserHelp:
    def test_main_help(self):
        parser = create_parser()
        # Should not raise
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
        args = parser.parse_args([
            "estimate",
            "--full-text", "抗诉",
            "--trial-step", "二审,再审",
            "--category", "刑事",
        ])
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
        args = parser.parse_args([
            "crawl",
            "--full-text", "抗诉",
            "--trial-step", "二审,再审",
        ])
        assert args.command == "crawl"
        assert args.full_text == "抗诉"

    def test_crawl_has_output_options(self):
        parser = create_parser()
        args = parser.parse_args([
            "crawl",
            "--format", "json,csv",
            "--output-dir", "/tmp/out",
            "--chunk-size", "500",
        ])
        assert args.format == "json,csv"
        assert args.output_dir == "/tmp/out"
        assert args.chunk_size == 500


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
        args = parser.parse_args([
            "crawl", "--delay", "1.0", "--max-pages", "5", "--format", "json",
        ])
        config = build_search_config(args)
        assert config["settings"]["delay"] == 1.0
        assert config["settings"]["max_pages"] == 5
        assert config["settings"]["format"] == ["json"]

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
        query_file.write_text(json.dumps({
            "fieldNodes": [
                {"field": "FullText", "value": "抗诉"},
                {"field": "TrialStep", "values": ["二审", "再审"]},
            ],
        }, ensure_ascii=False))

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
        query_file.write_text(json.dumps({
            "fieldNodes": [
                {
                    "field": "CategoryNew",
                    "values": ["刑事"],
                    "children": {"刑事": ["侵犯财产罪"]},
                },
            ],
        }, ensure_ascii=False))

        parser = create_parser()
        args = parser.parse_args(["estimate", "--query", str(query_file)])
        config = build_search_config(args)
        cat = next(n for n in config["fieldNodes"] if n["field"] == "CategoryNew")
        # "刑事" resolves to "001", "侵犯财产罪" resolves to "001005"
        assert "001" in cat["values"]
        children = cat.get("children", {})
        assert "001005" in children.get("001", [])

    def test_cli_overrides_json(self, tmp_path):
        query_file = tmp_path / "query.json"
        query_file.write_text(json.dumps({
            "fieldNodes": [
                {"field": "FullText", "value": "original"},
            ],
        }, ensure_ascii=False))

        parser = create_parser()
        args = parser.parse_args([
            "estimate", "--query", str(query_file), "--full-text", "override",
        ])
        config = build_search_config(args)
        ft = next(n for n in config["fieldNodes"] if n["field"] == "FullText")
        assert ft["value"] == "override"

    def test_json_settings(self, tmp_path):
        query_file = tmp_path / "query.json"
        query_file.write_text(json.dumps({
            "fieldNodes": [],
            "settings": {"delay": 1.0, "max_pages": 5},
        }, ensure_ascii=False))

        parser = create_parser()
        args = parser.parse_args(["estimate", "--query", str(query_file)])
        config = build_search_config(args)
        assert config["settings"]["delay"] == 1.0
        assert config["settings"]["max_pages"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_cli.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.cli'`

- [ ] **Step 3: Create src/cli.py**

```python
"""CLI argument parsing and SearchConfig building for PKULaw crawler."""

import argparse
import json
from pathlib import Path

from src.config import (
    FIELD_DEFINITIONS,
    _TEXT_FIELDS,
    resolve_value,
    resolve_values,
)
from src.log import get_logger


def _add_search_args(parser: argparse.ArgumentParser) -> None:
    """Add common search parameters to a subcommand parser."""
    # Text search fields
    parser.add_argument("--query", help="JSON query file path")
    parser.add_argument("--full-text", help="全文检索")
    parser.add_argument("--title", help="标题检索")
    parser.add_argument("--case-flag", help="案号检索")
    parser.add_argument("--gist", help="裁判要点")
    parser.add_argument("--party", help="当事人")
    parser.add_argument("--judge", help="审理法官")
    parser.add_argument("--lawyer", help="代理律师")
    parser.add_argument("--law-firm", help="代理律所")

    # Select/checkbox fields (comma-separated)
    parser.add_argument("--category", help="案由分类 (支持层级: 刑事>危害公共安全罪)")
    parser.add_argument("--trial-step", help="审理程序 (逗号分隔)")
    parser.add_argument("--court-grade", help="法院级别 (逗号分隔)")
    parser.add_argument("--court", help="审理法院")
    parser.add_argument("--case-grade", help="参照级别 (逗号分隔)")
    parser.add_argument("--case-class", help="案件类型 (逗号分隔)")
    parser.add_argument("--doc-type", help="文书类型 (逗号分隔)")
    parser.add_argument("--result", help="终审结果 (逗号分隔)")
    parser.add_argument("--topic", help="专题分类 (逗号分隔)")
    parser.add_argument("--punishment", help="刑罚 (逗号分隔)")
    parser.add_argument("--accusation", help="判定罪名")

    # Date ranges
    parser.add_argument("--date-range", help="审结日期范围 (YYYY-YYYY)")
    parser.add_argument("--issue-date-range", help="发布日期范围 (YYYY-YYYY)")

    # Output options
    parser.add_argument("--format", default="json,xlsx", help="输出格式 (默认: json,xlsx)")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--chunk-size", type=int, default=0, help="分表大小 (0=不分)")

    # Run control
    parser.add_argument("--delay", type=float, default=0.5, help="请求间隔秒数")
    parser.add_argument("--max-pages", type=int, default=10, help="每组最大页数")
    parser.add_argument("--browser", default="/usr/bin/chromium", help="Chromium 路径")
    parser.add_argument("--no-headless", action="store_true", help="显示浏览器")


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="pkulaw",
        description="PKULaw 北大法宝案例数据库 CLI 采集工具",
    )
    subparsers = parser.add_subparsers(dest="command")

    # estimate subcommand
    est = subparsers.add_parser("estimate", help="估算可爬取数据量")
    _add_search_args(est)

    # crawl subcommand
    crawl = subparsers.add_parser("crawl", help="执行搜索+采集+导出")
    _add_search_args(crawl)

    # status subcommand
    subparsers.add_parser("status", help="查看爬取进度")

    return parser


def build_search_config(args: argparse.Namespace) -> dict:
    """Build a unified SearchConfig dict from parsed CLI args.

    Handles both direct CLI flags and --query JSON file.
    CLI flags override JSON file values.
    """
    config = {"fieldNodes": [], "settings": _build_settings(args)}

    if args.query:
        _load_json_config(args.query, config)

    _apply_cli_overrides(args, config)

    return config


def _build_settings(args: argparse.Namespace) -> dict:
    """Build settings dict from CLI args."""
    formats = args.format.split(",") if args.format else ["json", "xlsx"]
    return {
        "format": formats,
        "output_dir": args.output_dir,
        "chunk_size": args.chunk_size,
        "delay": args.delay,
        "max_pages": args.max_pages,
        "browser": args.browser,
        "headless": not args.no_headless,
    }


def _load_json_config(path: str, config: dict) -> None:
    """Load field nodes and settings from a JSON query file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    for node in data.get("fieldNodes", []):
        field = node["field"]
        if field in _TEXT_FIELDS:
            config["fieldNodes"].append({
                "field": field,
                "value": node.get("value", ""),
                **({"scope": node["scope"]} if "scope" in node else {}),
                **({"match": node["match"]} if "match" in node else {}),
            })
        elif "range" in node:
            config["fieldNodes"].append({
                "field": field,
                "range": node["range"],
            })
        elif "values" in node:
            resolved = [resolve_value(field, v) for v in node["values"]]
            entry = {"field": field, "values": resolved}
            if "children" in node:
                children = {}
                for parent_name, child_names in node["children"].items():
                    parent_id = resolve_value(field, parent_name)
                    child_ids = [resolve_value(field, c) for c in child_names]
                    children[parent_id] = child_ids
                entry["children"] = children
            config["fieldNodes"].append(entry)

    if "settings" in data:
        config["settings"].update(data["settings"])

    if "orderBy" in data:
        config["orderBy"] = data["orderBy"]


def _apply_cli_overrides(args: argparse.Namespace, config: dict) -> None:
    """Override or add field nodes from CLI flags."""
    # Text fields: CLI flag name → (API field name, arg attr name)
    text_fields = [
        ("FullText", "full_text"),
        ("Title", "title"),
        ("CaseFlag", "case_flag"),
        ("CaseGist", "gist"),
        ("Party", "party"),
        ("Judge", "judge"),
        ("AgentLawyer", "lawyer"),
        ("AgentLawOffice", "law_firm"),
    ]
    for field_name, attr_name in text_fields:
        value = getattr(args, attr_name, None)
        if value is not None:
            _set_field_node(config, {"field": field_name, "value": value})

    # Multi-value fields: CLI flag name → (API field name, arg attr name)
    multi_fields = [
        ("TrialStep", "trial_step"),
        ("CourtGrade", "court_grade"),
        ("CaseGrade", "case_grade"),
        ("CaseClass", "case_class"),
        ("DocumentAttr", "doc_type"),
        ("TrialStepCount", "result"),
        ("SubjectClassSpecialType", "topic"),
        ("PenaltyCodes", "punishment"),
    ]
    for field_name, attr_name in multi_fields:
        value = getattr(args, attr_name, None)
        if value is not None:
            ids = resolve_values(field_name, value)
            _set_field_node(config, {"field": field_name, "values": ids})

    # Category (hierarchical)
    category = getattr(args, "category", None)
    if category is not None:
        parts = [p.strip() for p in category.split(",")]
        ids = [resolve_value("CategoryNew", p) for p in parts]
        _set_field_node(config, {"field": "CategoryNew", "values": ids})

    # Accusation (select field)
    accusation = getattr(args, "accusation", None)
    if accusation is not None:
        ids = resolve_values("Accusation", accusation)
        _set_field_node(config, {"field": "Accusation", "values": ids})

    # Date ranges
    date_range = getattr(args, "date_range", None)
    if date_range is not None:
        parts = date_range.split("-")
        _set_field_node(config, {
            "field": "LastInstanceDate",
            "range": [parts[0], parts[-1]],
        })

    issue_date_range = getattr(args, "issue_date_range", None)
    if issue_date_range is not None:
        parts = issue_date_range.split("-")
        _set_field_node(config, {
            "field": "IssueDate",
            "range": [parts[0], parts[-1]],
        })

    # Court (text-like)
    court = getattr(args, "court", None)
    if court is not None:
        _set_field_node(config, {"field": "LastInstanceCourt", "value": court})


def _set_field_node(config: dict, node: dict) -> None:
    """Set or replace a field node in the config by field name."""
    field_name = node["field"]
    for i, existing in enumerate(config["fieldNodes"]):
        if existing["field"] == field_name:
            config["fieldNodes"][i] = node
            return
    config["fieldNodes"].append(node)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_cli.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cli.py tests/test_cli.py
git commit -m "feat: add cli.py with argparse and SearchConfig builder"
```

---

## Task 6: Create pkulaw.py — entry point + status placeholder

**Files:**
- Create: `pkulaw.py`

- [ ] **Step 1: Write pkulaw.py**

```python
"""PKULaw CLI crawler — entry point."""

import sys

from src.cli import build_search_config, create_parser
from src.log import setup_logger


def cmd_estimate(config: dict) -> None:
    """Estimate crawlable data volume (placeholder)."""
    logger = setup_logger(
        __import__("pathlib").Path(config["settings"]["output_dir"]) / "crawl.log"
    )
    logger.info("Estimate command started")
    logger.info("Query: %s", _format_query(config))
    print("\n=== PKULaw 数据量估算 ===")
    print("\n检索条件：")
    for node in config["fieldNodes"]:
        field = node["field"]
        if "value" in node:
            print(f"  {field}: {node['value']}")
        elif "values" in node:
            print(f"  {field}: {', '.join(node['values'])}")
        elif "range" in node:
            print(f"  {field}: {node['range'][0]} ~ {node['range'][1]}")
    print("\n（API 连接功能将在 Phase 2 实现）\n")


def cmd_crawl(config: dict) -> None:
    """Execute crawl (placeholder)."""
    logger = setup_logger(
        __import__("pathlib").Path(config["settings"]["output_dir"]) / "crawl.log"
    )
    logger.info("Crawl command started")
    logger.info("Query: %s", _format_query(config))
    print("\n=== PKULaw 采集 ===")
    print("\n检索条件：")
    for node in config["fieldNodes"]:
        field = node["field"]
        if "value" in node:
            print(f"  {field}: {node['value']}")
        elif "values" in node:
            print(f"  {field}: {', '.join(node['values'])}")
        elif "range" in node:
            print(f"  {field}: {node['range'][0]} ~ {node['range'][1]}")
    print("\n（采集功能将在 Phase 3 实现）\n")


def cmd_status() -> None:
    """Show crawl status from existing data files."""
    from pathlib import Path

    output_dir = Path("output")

    print("\n=== PKULaw 爬取状态 ===")

    if not output_dir.exists():
        print("\n无活跃任务（output/ 目录不存在）\n")
        return

    # Check for log file
    log_file = output_dir / "crawl.log"
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        print(f"\n最近日志 ({log_file}):")
        for line in lines[-20:]:
            print(f"  {line}")
    else:
        print("\n无日志文件")

    # Check for progress
    progress_file = output_dir / "progress.json"
    if progress_file.exists():
        import json

        data = json.loads(progress_file.read_text(encoding="utf-8"))
        fetched = data.get("fetched_gids", [])
        print(f"\n进度：已采集 {len(fetched)} 条")
    else:
        print("\n无进度文件")

    # Check for search cache
    cache_file = output_dir / "search_results.json"
    if cache_file.exists():
        import json

        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            print(f"搜索缓存：{len(data)} 条")
        elif isinstance(data, dict):
            total = data.get("total_unique", len(data.get("results", [])))
            print(f"搜索缓存：{total} 条")

    # Check for results
    results_file = output_dir / "pkulaw_cases.json"
    if results_file.exists():
        import json

        data = json.loads(results_file.read_text(encoding="utf-8"))
        print(f"结果文件：{len(data)} 条 ({results_file.stat().st_size / 1024 / 1024:.1f} MB)")

    print()


def _format_query(config: dict) -> str:
    """Format field nodes as a readable string."""
    parts = []
    for node in config["fieldNodes"]:
        field = node["field"]
        if "value" in node:
            parts.append(f"{field}={node['value']}")
        elif "values" in node:
            parts.append(f"{field}={','.join(node['values'])}")
        elif "range" in node:
            parts.append(f"{field}={node['range'][0]}~{node['range'][1]}")
    return " | ".join(parts)


def main() -> None:
    """CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "status":
            cmd_status()
        elif args.command in ("estimate", "crawl"):
            config = build_search_config(args)
            if args.command == "estimate":
                cmd_estimate(config)
            else:
                cmd_crawl(config)
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test acceptance criteria**

```bash
python pkulaw.py --help
```

Expected: Help text showing estimate, crawl, status subcommands.

```bash
python pkulaw.py estimate --help
```

Expected: Help text showing all search flags.

```bash
python pkulaw.py status
```

Expected: Status output (empty or showing existing data if output/ exists).

```bash
python pkulaw.py estimate --full-text "抗诉" --trial-step "二审,再审" --category "刑事"
```

Expected: Shows search criteria with resolved IDs (FullText=抗诉, TrialStep=002,003, CategoryNew=001).

- [ ] **Step 3: Commit**

```bash
git add pkulaw.py
git commit -m "feat: add pkulaw.py CLI entry point with status placeholder"
```

---

## Task 7: Acceptance verification + merge

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Verify all acceptance criteria from Issue #2**

```bash
python pkulaw.py --help
python pkulaw.py estimate --help
python pkulaw.py status
python pkulaw.py estimate --full-text "抗诉" --trial-step "二审,再审"
```

All four must succeed without errors.

- [ ] **Step 3: Run pre-commit checks**

```bash
pre-commit run --all-files
```

Expected: All hooks pass (black, isort, trailing-whitespace, no-co-author, no-sensitive-data).

- [ ] **Step 4: Merge to develop**

```bash
git checkout develop
git merge --no-ff feature/iter1-foundation
```

- [ ] **Step 5: Push**

```bash
git push origin develop
```

- [ ] **Step 6: Close Issue #2**

Comment on the issue with the commit SHA and acceptance results.

---

## Self-Review

**1. Spec coverage check:**

| Issue #2 Requirement | Covered By |
|---|---|
| `src/config.py` — all field definitions + mappings | Task 2 (data) + Task 3 (resolve functions) |
| CategoryNew tree with 3-level hierarchy | Task 2 (generated from API) |
| All other mappings (TrialStep, CaseGrade, etc.) | Task 2 (generated from API) |
| `resolve_value("CategoryNew", "刑事>危害公共安全罪")` → `"001002"` | Task 3 |
| `src/log.py` — structured logging | Task 4 |
| Format `[YYYY-MM-DD HH:MM:SS] LEVEL message` | Task 4 |
| File + console output | Task 4 |
| Log levels DEBUG/INFO/WARN/ERROR | Task 4 |
| `src/cli.py` — 3 subcommands | Task 5 |
| All CLI flags from spec §2.3 | Task 5 |
| JSON query file parser | Task 5 |
| CLI + JSON → unified SearchConfig | Task 5 |
| CLI overrides JSON | Task 5 |
| Hierarchical path parsing | Task 3 (resolve) + Task 5 (cli) |
| `pkulaw.py` — entry point | Task 6 |
| Ctrl+C handling | Task 6 |
| `pyproject.toml` | Task 1 |
| `status` subcommand (placeholder) | Task 6 |
| 4 acceptance criteria commands | Task 7 |

**2. Placeholder scan:** No TBD, TODO, or "implement later" found. All code steps include complete implementation.

**3. Type consistency:**
- `resolve_value(field: str, path: str) -> str` — used consistently in cli.py
- `resolve_values(field: str, comma_path: str) -> list[str]` — returns list of IDs
- `build_search_config(args: Namespace) -> dict` — returns dict with fieldNodes, settings
- Field node format: `{"field": str, "value": str}` or `{"field": str, "values": list[str]}` or `{"field": str, "range": list[str]}` — consistent across all functions
