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
