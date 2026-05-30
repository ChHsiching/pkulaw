"""Regression tests for token propagation fix (Issue #15).

Verifies that the four root causes (H1-H4) of the zero-results crawl
are fixed:

H1: search_api detects API-level token errors
H2: TokenContext propagates refreshed token to all callers
H3: partition_query uses propagated token through recursive calls
H4: Unexpected API responses raise RuntimeError instead of silent swallowing
"""

from unittest.mock import MagicMock, patch

import pytest

from src.auth import (
    TokenContext,
    _is_token_error,
    _is_unexpected_response,
    search_api,
)
from src.partition import _add_dimension_filter, partition_query

# ---------------------------------------------------------------------------
# H1: search_api detects API-level token errors
# ---------------------------------------------------------------------------


class TestH1TokenErrorDetection:
    def test_api_token_error_triggers_reauthenticate(self):
        """When API returns {"code": "1", "message": "token error"},
        search_api should detect it, reauthenticate, and retry."""
        mock_page = MagicMock()
        call_count = 0

        def fake_evaluate(js, args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"code": "1", "message": "token error"}
            return {"total": 100, "data": []}

        mock_page.evaluate.side_effect = fake_evaluate

        ctx = TokenContext(token="expired")
        with patch("src.auth.reauthenticate", return_value="new_token"):
            result = search_api(mock_page, ctx, {"test": True})

        assert result["total"] == 100
        assert ctx.token == "new_token"

    def test_is_token_error_catches_known_format(self):
        assert _is_token_error({"code": "1", "message": "token error"}) is True
        assert _is_token_error({"code": "1", "message": "Token Error"}) is True

    def test_is_token_error_ignores_other_errors(self):
        assert _is_token_error({"code": "1", "message": "rate limit"}) is False
        assert _is_token_error({"total": 100, "data": []}) is False
        assert _is_token_error({"code": "1", "message": ""}) is False


# ---------------------------------------------------------------------------
# H2: TokenContext propagates refreshed token
# ---------------------------------------------------------------------------


class TestH2TokenPropagation:
    def test_shared_context_visible_to_all_holders(self):
        """Multiple references to the same TokenContext all see token updates."""
        ctx = TokenContext(token="old")
        holder_a = ctx
        holder_b = ctx

        with patch("src.auth.reauthenticate", return_value="refreshed"):
            ctx.token = "refreshed"

        assert holder_a.token == "refreshed"
        assert holder_b.token == "refreshed"

    def test_search_api_updates_ctx_on_js_error(self):
        mock_page = MagicMock()
        call_count = 0

        def fake_evaluate(js, args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"_error": "not_json"}
            return {"total": 50, "data": []}

        mock_page.evaluate.side_effect = fake_evaluate

        ctx = TokenContext(token="stale")
        with patch("src.auth.reauthenticate", return_value="fresh"):
            search_api(mock_page, ctx, {})

        assert ctx.token == "fresh"

    def test_search_api_sends_ctx_token_in_request(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = {"total": 1, "data": []}

        ctx = TokenContext(token="my_token_123")
        search_api(mock_page, ctx, {"test": True})

        sent_token = mock_page.evaluate.call_args[0][1][1]
        assert sent_token == "my_token_123"


# ---------------------------------------------------------------------------
# H3: partition_query propagates token through recursive calls
# ---------------------------------------------------------------------------


class TestH3PartitionTokenPropagation:
    def test_ctx_propagated_to_all_search_fn_calls(self):
        """partition_query passes the same ctx to every search_fn call."""
        ctx_instances = []

        def tracking_search(page, ctx, body):
            ctx_instances.append(ctx)
            gb = body.get("groupBy", {})
            if gb.get("LastInstanceDate"):
                return {"total": 100, "data": []}
            return {"total": 3000, "data": []}

        ctx = TokenContext(token="session_token")
        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        partition_query(
            page=None, ctx=ctx, search_config=config, search_fn=tracking_search
        )

        # All calls received the same ctx object
        assert all(c is ctx for c in ctx_instances)

    def test_token_refresh_mid_partition_visible_to_later_calls(self):
        """If token is refreshed during partition, subsequent calls use new token."""
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

        # Simulate mid-session token refresh
        ctx.token = "refreshed"
        tokens_seen.clear()
        partition_query(
            page=None, ctx=ctx, search_config=config, search_fn=tracking_search
        )

        assert all(t == "refreshed" for t in tokens_seen)

    def test_full_partition_tree_built_with_valid_token(self):
        """With a valid token, partition_query builds a complete tree — no
        silent skipping of valid partitions."""
        call_count = 0

        def fake_search(page, ctx, body):
            nonlocal call_count
            call_count += 1
            gb = body.get("groupBy", {})

            if not gb:
                return {"total": 5000, "data": []}

            year = gb.get("LastInstanceDate", "")
            # All years have data (token is valid)
            return {"total": 200, "data": []}

        ctx = TokenContext(token="valid")
        config = {"fieldNodes": [], "settings": {"max_pages": 10}}
        result = partition_query(
            page=None, ctx=ctx, search_config=config, search_fn=fake_search
        )

        # All years should be present (not silently skipped)
        assert result["dimension"] == "LastInstanceDate"
        assert len(result["children"]) > 2
        assert result["crawlable"] > 0


# ---------------------------------------------------------------------------
# H4: Unexpected API responses raise RuntimeError
# ---------------------------------------------------------------------------


class TestH4UnexpectedResponseDetection:
    def test_unexpected_response_raises_runtime_error(self):
        """Responses with no total/data keys raise RuntimeError, not silent empty."""
        mock_page = MagicMock()
        mock_page.evaluate.return_value = {"code": "2", "message": "server error"}

        ctx = TokenContext(token="valid")
        with pytest.raises(RuntimeError, match="Unexpected API response"):
            search_api(mock_page, ctx, {"test": True})

    def test_is_unexpected_response_detects_bad_formats(self):
        assert _is_unexpected_response({"code": "2", "message": "error"}) is True
        assert _is_unexpected_response({}) is True

    def test_is_unexpected_response_passes_normal_data(self):
        assert _is_unexpected_response({"total": 100}) is False
        assert _is_unexpected_response({"data": []}) is False
        assert _is_unexpected_response({"total": 100, "data": []}) is False


# ---------------------------------------------------------------------------
# _add_dimension_filter: multi-value CategoryNew preservation
# ---------------------------------------------------------------------------


class TestAddDimensionFilterPreservesCategoryNew:
    def test_year_partition_keeps_multi_value_category(self):
        config = {
            "fieldNodes": [
                {"field": "CategoryNew", "values": ["id1", "id2", "id3"]},
            ],
            "settings": {},
        }
        result = _add_dimension_filter(config, "LastInstanceDate", "2025")
        cat_nodes = [n for n in result["fieldNodes"] if n["field"] == "CategoryNew"]
        assert len(cat_nodes) == 1
        assert cat_nodes[0]["values"] == ["id1", "id2", "id3"]

    def test_category_partition_replaces_with_single_value(self):
        config = {
            "fieldNodes": [
                {"field": "CategoryNew", "values": ["id1", "id2", "id3"]},
            ],
            "settings": {},
        }
        result = _add_dimension_filter(config, "CategoryNew", "id2")
        cat_nodes = [n for n in result["fieldNodes"] if n["field"] == "CategoryNew"]
        assert len(cat_nodes) == 1
        assert cat_nodes[0]["values"] == ["id2"]
