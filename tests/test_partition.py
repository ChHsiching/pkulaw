"""Tests for src/partition.py — recursive partitioning algorithm."""

from unittest.mock import MagicMock

import pytest

from src.auth import TokenContext
from src.partition import (
    _get_available_dimensions,
    _get_partition_values,
    partition_query,
)


class TestGetAvailableDimensions:
    def test_all_available_when_empty_query(self):
        config = {"fieldNodes": [], "settings": {}}
        dims = _get_available_dimensions(config)
        assert "LastInstanceDate" in dims
        assert "CaseGrade" in dims
        assert "CourtGrade" in dims

    def test_category_excluded_when_already_set(self):
        config = {
            "fieldNodes": [{"field": "CategoryNew", "values": ["001"]}],
            "settings": {},
        }
        dims = _get_available_dimensions(config)
        assert "CategoryNew" not in dims

    def test_trial_step_excluded_when_set(self):
        config = {
            "fieldNodes": [{"field": "TrialStep", "values": ["002"]}],
            "settings": {},
        }
        dims = _get_available_dimensions(config)
        assert "TrialStep" not in dims


class TestGetPartitionValues:
    def test_last_instance_date(self):
        values = _get_partition_values("LastInstanceDate")
        assert len(values) > 20
        assert "2025" in values

    def test_case_grade(self):
        values = _get_partition_values("CaseGrade")
        assert len(values) >= 10
        assert "01" in values

    def test_court_grade(self):
        values = _get_partition_values("CourtGrade")
        assert len(values) == 5


class TestPartitionQuery:
    def test_small_total_returns_leaf(self):
        """If total <= threshold, return a single leaf node."""
        mock_api = MagicMock(return_value={"total": 500, "data": []})
        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        result = partition_query(
            page=None,
            ctx=TokenContext(token="test"),
            search_config=config,
            search_fn=mock_api,
        )
        assert result["total"] == 500
        assert result["crawlable"] == 500
        assert result["children"] is None

    def test_large_total_splits_by_year(self):
        """If total > threshold, split by LastInstanceDate."""

        def fake_search(page, ctx, body):
            gb = body.get("groupBy", {})
            if gb and gb.get("LastInstanceDate") == "2025":
                return {"total": 200, "data": []}
            if gb:
                return {"total": 50, "data": []}
            return {"total": 1500, "data": []}

        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        result = partition_query(
            page=None,
            ctx=TokenContext(token="test"),
            search_config=config,
            search_fn=fake_search,
        )
        assert result["total"] == 1500
        assert result["dimension"] == "LastInstanceDate"
        assert result["children"] is not None
        assert result["crawlable"] > 0

    def test_very_large_year_splits_further(self):
        """If a year partition is still > threshold, split by next dimension."""

        def fake_search(page, ctx, body):
            gb = body.get("groupBy", {})
            cf = body.get("clusterFilters", {})
            if gb and gb.get("LastInstanceDate") == "2025":
                if cf.get("CaseGrade"):
                    return {"total": 100, "data": []}
                return {"total": 2000, "data": []}
            if gb:
                return {"total": 50, "data": []}
            return {"total": 5000, "data": []}

        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        result = partition_query(
            page=None,
            ctx=TokenContext(token="test"),
            search_config=config,
            search_fn=fake_search,
        )
        assert result["total"] == 5000
        year_2025 = None
        for child in result["children"] or []:
            if child.get("label") == "2025":
                year_2025 = child
                break
        assert year_2025 is not None
        assert year_2025.get("dimension") == "CaseGrade"


class TestPartitionQueryTokenContext:
    def test_accepts_token_context(self):
        mock_api = MagicMock(return_value={"total": 500, "data": []})
        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        ctx = TokenContext(token="test")
        result = partition_query(
            page=None,
            ctx=ctx,
            search_config=config,
            search_fn=mock_api,
        )
        assert result["total"] == 500
        call_args = mock_api.call_args[0]
        assert call_args[1] is ctx

    def test_propagates_context_through_recursion(self):
        tokens_seen = []

        def tracking_search(page, ctx, body):
            tokens_seen.append(ctx.token)
            gb = body.get("groupBy", {})
            if gb.get("LastInstanceDate"):
                return {"total": 100, "data": []}
            return {"total": 3000, "data": []}

        ctx = TokenContext(token="initial")
        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        partition_query(
            page=None, ctx=ctx, search_config=config, search_fn=tracking_search
        )

        assert all(t == "initial" for t in tokens_seen)

        ctx.token = "refreshed"
        tokens_seen.clear()
        partition_query(
            page=None, ctx=ctx, search_config=config, search_fn=tracking_search
        )

        assert all(t == "refreshed" for t in tokens_seen)
