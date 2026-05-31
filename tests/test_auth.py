"""Tests for src/auth.py — browser auth and API call."""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from src.auth import (
    API_URL,
    TokenContext,
    _is_token_error,
    _is_unexpected_response,
    search_api,
)


class TestConstants:
    def test_api_url(self):
        assert API_URL == "/searchingapi/adv/list/pfnl"


class TestTokenContext:
    def test_mutable_token_update(self):
        ctx = TokenContext(token="old")
        assert ctx.token == "old"
        ctx.token = "new"
        assert ctx.token == "new"

    def test_shared_mutation_visible_to_all(self):
        ctx = TokenContext(token="original")
        ref = ctx
        ref.token = "updated"
        assert ctx.token == "updated"


class TestIsTokenError:
    def test_detects_token_error(self):
        assert _is_token_error({"code": "1", "message": "token error"}) is True

    def test_detects_token_error_case_insensitive(self):
        assert _is_token_error({"code": "1", "message": "Token Error"}) is True

    def test_ignores_non_token_error(self):
        assert _is_token_error({"code": "1", "message": "rate limit"}) is False

    def test_ignores_success_response(self):
        assert _is_token_error({"total": 100, "data": []}) is False

    def test_ignores_empty_message(self):
        assert _is_token_error({"code": "1", "message": ""}) is False


class TestIsUnexpectedResponse:
    def test_detects_error_response(self):
        assert _is_unexpected_response({"code": "2", "message": "server error"}) is True

    def test_passes_with_total(self):
        assert _is_unexpected_response({"total": 100}) is False

    def test_passes_with_data(self):
        assert _is_unexpected_response({"data": []}) is False

    def test_passes_with_both(self):
        assert _is_unexpected_response({"total": 100, "data": []}) is False


class TestSearchApiSignature:
    def test_search_api_has_correct_params(self):
        sig = inspect.signature(search_api)
        params = list(sig.parameters.keys())
        assert "page" in params
        assert "ctx" in params
        assert "body" in params


class TestSearchApiTokenContext:
    def test_updates_ctx_on_js_error(self):
        mock_page = MagicMock()
        call_count = 0

        def fake_evaluate(js, args, timeout=30000):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"_error": "not_json"}
            return {"total": 100, "data": []}

        mock_page.evaluate.side_effect = fake_evaluate

        ctx = TokenContext(token="old_token")
        with patch("src.auth.reauthenticate", return_value="new_token"):
            result = search_api(mock_page, ctx, {"test": True})

        assert ctx.token == "new_token"
        assert result["total"] == 100

    def test_updates_ctx_on_api_token_error(self):
        mock_page = MagicMock()
        call_count = 0

        def fake_evaluate(js, args, timeout=30000):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"code": "1", "message": "token error"}
            return {"total": 200, "data": []}

        mock_page.evaluate.side_effect = fake_evaluate

        ctx = TokenContext(token="expired")
        with patch("src.auth.reauthenticate", return_value="fresh"):
            result = search_api(mock_page, ctx, {"test": True})

        assert ctx.token == "fresh"
        assert result["total"] == 200

    def test_raises_on_unexpected_response(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = {"code": "2", "message": "server error"}

        ctx = TokenContext(token="good")
        with pytest.raises(RuntimeError, match="Unexpected API response"):
            search_api(mock_page, ctx, {"test": True})

    def test_returns_data_on_success(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = {"total": 500, "data": [{"gid": "g1"}]}

        ctx = TokenContext(token="valid")
        result = search_api(mock_page, ctx, {"test": True})

        assert result["total"] == 500
        assert ctx.token == "valid"

    def test_uses_ctx_token_in_request(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = {"total": 1, "data": []}

        ctx = TokenContext(token="my_token")
        search_api(mock_page, ctx, {"test": True})

        call_args = mock_page.evaluate.call_args[0][1]
        assert call_args[1] == "my_token"
