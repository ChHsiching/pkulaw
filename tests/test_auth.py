"""Tests for src/auth.py — browser auth and API call."""

import inspect

import pytest

from src.auth import API_URL, search_api


class TestConstants:
    def test_api_url(self):
        assert API_URL == "/searchingapi/adv/list/pfnl"


class TestSearchApiSignature:
    def test_search_api_has_correct_params(self):
        sig = inspect.signature(search_api)
        params = list(sig.parameters.keys())
        assert "page" in params
        assert "token" in params
        assert "body" in params
