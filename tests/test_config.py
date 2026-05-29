"""Tests for src/config.py — field definitions, resolve functions."""

import pytest

from src.config import (
    CATEGORY_VALUES,
    CLI_TO_FIELD_MAP,
    FIELD_DEFINITIONS,
    resolve_value,
    resolve_values,
    validate_field_values,
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
        assert "001005002" in result
        assert "001005003" in result
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
            assert (
                field_name in FIELD_DEFINITIONS
            ), f"{flag} maps to unknown field {field_name}"
