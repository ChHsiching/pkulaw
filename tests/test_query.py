"""Tests for src/query.py — SearchConfig to API body conversion."""

import pytest

from src.query import (
    _build_select_node,
    _build_text_node,
    build_api_body,
    reverse_lookup,
)


class TestReverseLookup:
    def test_trial_step(self):
        assert reverse_lookup("TrialStep", "002") == "二审"

    def test_court_grade(self):
        assert reverse_lookup("CourtGrade", "03") == "中级人民法院"

    def test_case_grade(self):
        assert reverse_lookup("CaseGrade", "01") == "指导性案例"

    def test_category_new(self):
        assert reverse_lookup("CategoryNew", "001") == "刑事"

    def test_category_second_level(self):
        assert reverse_lookup("CategoryNew", "001001") == "危害国家安全罪"

    def test_missing_id_returns_none(self):
        assert reverse_lookup("TrialStep", "999") is None


class TestBuildTextNode:
    def test_full_text(self):
        node = _build_text_node("FullText", "抗诉")
        assert node["type"] == "text"
        assert node["fieldName"] == "FullText"
        assert node["showText"] == "全文"
        items = node["fieldItems"]
        assert len(items) == 1
        assert items[0]["values"] == "抗诉"

    def test_title(self):
        node = _build_text_node("Title", "盗窃")
        assert node["fieldName"] == "Title"
        assert node["fieldItems"][0]["values"] == "盗窃"


class TestBuildSelectNode:
    def test_trial_step(self):
        node = _build_select_node("TrialStep", ["002", "003"])
        assert node["type"] == "select"
        assert node["fieldName"] == "TrialStep"
        assert node["showText"] == "审理程序"
        items = node["fieldItems"][0]["items"]
        assert len(items) == 2
        assert items[0]["value"] == "002"
        assert items[0]["text"] == "二审"

    def test_court_grade_checkbox(self):
        node = _build_select_node("CourtGrade", ["01", "03"])
        assert node["type"] == "checkbox"
        items = node["fieldItems"][0]["items"]
        assert items[0]["text"] == "最高人民法院"
        assert items[1]["text"] == "中级人民法院"


class TestBuildApiBody:
    def test_minimal_query(self):
        config = {"fieldNodes": [], "settings": {}}
        body = build_api_body(config)
        assert body["pageSize"] == 100
        assert body["pageIndex"] == 0
        assert body["orderbyExpression"] == "LastInstanceDate Desc"
        assert body["groupBy"] == {}
        assert "fieldNodes" in body
        assert isinstance(body["clusterFilters"], dict)

    def test_text_field_in_field_nodes(self):
        config = {
            "fieldNodes": [{"field": "FullText", "value": "抗诉"}],
            "settings": {},
        }
        body = build_api_body(config)
        fn = body["fieldNodes"]
        assert any(n["fieldName"] == "FullText" for n in fn)

    def test_select_field_in_field_nodes(self):
        config = {
            "fieldNodes": [{"field": "TrialStep", "values": ["002", "003"]}],
            "settings": {},
        }
        body = build_api_body(config)
        fn = body["fieldNodes"]
        ts = next(n for n in fn if n["fieldName"] == "TrialStep")
        items = ts["fieldItems"][0]["items"]
        assert len(items) == 2
        assert items[0]["value"] == "002"

    def test_category_new_in_cluster_filters(self):
        config = {
            "fieldNodes": [{"field": "CategoryNew", "values": ["001"]}],
            "settings": {},
        }
        body = build_api_body(config)
        assert body["clusterFilters"].get("CategoryNew") == "001"
        assert not any(n["fieldName"] == "CategoryNew" for n in body["fieldNodes"])

    def test_group_by_override(self):
        config = {"fieldNodes": [], "settings": {}}
        body = build_api_body(config, group_by={"LastInstanceDate": "2025"})
        assert body["groupBy"] == {"LastInstanceDate": "2025"}

    def test_page_params(self):
        config = {"fieldNodes": [], "settings": {}}
        body = build_api_body(
            config, page_index=3, page_size=50, order_by="SortNum Desc"
        )
        assert body["pageIndex"] == 3
        assert body["pageSize"] == 50
        assert body["orderbyExpression"] == "SortNum Desc"

    def test_multiple_fields_combined(self):
        config = {
            "fieldNodes": [
                {"field": "FullText", "value": "抗诉"},
                {"field": "TrialStep", "values": ["002", "003"]},
                {"field": "CategoryNew", "values": ["001"]},
            ],
            "settings": {},
        }
        body = build_api_body(config)
        assert len(body["fieldNodes"]) == 2  # FullText + TrialStep (not CategoryNew)
        assert body["clusterFilters"]["CategoryNew"] == "001"

    def test_cluster_filters_additive(self):
        config = {
            "fieldNodes": [
                {"field": "CategoryNew", "values": ["001"]},
            ],
            "settings": {},
        }
        body = build_api_body(config, cluster_overrides={"CaseGrade": "01"})
        assert body["clusterFilters"]["CategoryNew"] == "001"
        assert body["clusterFilters"]["CaseGrade"] == "01"

    def test_date_range_field_ignored_in_field_nodes(self):
        config = {
            "fieldNodes": [{"field": "LastInstanceDate", "range": ["2020", "2025"]}],
            "settings": {},
        }
        body = build_api_body(config)
        assert not any(n["fieldName"] == "LastInstanceDate" for n in body["fieldNodes"])
