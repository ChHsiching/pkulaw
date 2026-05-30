"""Tests for src/auth.py — browser auth and API call."""

import inspect

import pytest

from src.auth import API_URL, TokenContext, search_api


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


class TestSearchApiSignature:
    def test_search_api_has_correct_params(self):
        sig = inspect.signature(search_api)
        params = list(sig.parameters.keys())
        assert "page" in params
        assert "ctx" in params
        assert "body" in params
