"""Testes do módulo ai / ai module tests"""
import json
from unittest.mock import patch

import pytest

from ai import (
    evaluate_relevance,
    normalize_group,
    consolidate_groups,
)


class TestNormalizeGroup:
    def test_lowercases_and_replaces_spaces(self):
        assert normalize_group("PGM Caxias do Sul - Procurador") == "pgm-caxias-do-sul-procurador"

    def test_strips_accents(self):
        assert normalize_group("Procuração") == "procuracao"

    def test_collapses_repeated_separators(self):
        assert normalize_group("foo // bar -- baz") == "foo-bar-baz"

    def test_strips_leading_trailing_separators(self):
        assert normalize_group("--foo--") == "foo"

    def test_empty_returns_empty(self):
        assert normalize_group("") == ""

    def test_none_returns_empty(self):
        assert normalize_group(None) == ""


class TestEvaluateRelevance:
    LEGAL_TEXT = "Edital de concurso para procurador municipal " * 5

    def test_no_api_key(self, monkeypatch):
        monkeypatch.setattr("ai.AI_API_KEY", "")
        result = evaluate_relevance("https://x.com", "title", self.LEGAL_TEXT)
        assert result["relevant"] is False
        assert result["reason"] == "AI_API_KEY not configured"

    def test_insufficient_text(self, monkeypatch):
        monkeypatch.setattr("ai.AI_API_KEY", "fake-key")
        result = evaluate_relevance("https://x.com", "title", "curto")
        assert result["relevant"] is False
        assert result["reason"] == "insufficient text"

    def test_relevant_response_passthrough(self, monkeypatch):
        monkeypatch.setattr("ai.AI_API_KEY", "fake-key")
        ai_response = json.dumps({
            "relevant": True,
            "reason": "Cargo de procurador municipal",
            "status": "registration_open",
            "group": "PGM Foo - Procurador",
        })
        with patch("ai.call_ai_api", return_value=ai_response):
            result = evaluate_relevance("https://x.com", "Edital", self.LEGAL_TEXT)
        assert result["relevant"] is True
        assert result["status"] == "registration_open"
        assert result["group"] == "pgm-foo-procurador"

    def test_invalid_status_normalized_to_empty(self, monkeypatch):
        monkeypatch.setattr("ai.AI_API_KEY", "fake-key")
        ai_response = json.dumps({
            "relevant": True,
            "reason": "x",
            "status": "INVALID_STATUS",
            "group": "g",
        })
        with patch("ai.call_ai_api", return_value=ai_response):
            result = evaluate_relevance("https://x.com", "Edital", self.LEGAL_TEXT)
        assert result["status"] == ""

    def test_malformed_json_handled(self, monkeypatch):
        monkeypatch.setattr("ai.AI_API_KEY", "fake-key")
        with patch("ai.call_ai_api", return_value="not valid json"):
            result = evaluate_relevance("https://x.com", "Edital", self.LEGAL_TEXT)
        assert result["relevant"] is False
        assert result["reason"] == "error parsing response"

    def test_empty_response_handled(self, monkeypatch):
        monkeypatch.setattr("ai.AI_API_KEY", "fake-key")
        with patch("ai.call_ai_api", return_value=""):
            result = evaluate_relevance("https://x.com", "Edital", self.LEGAL_TEXT)
        assert result["relevant"] is False
        assert result["reason"] == "empty response from AI"

class TestConsolidateGroups:
    def test_consolidate_groups_success(self, monkeypatch):
        monkeypatch.setattr("ai.AI_API_KEY", "fake-key")
        items = [
            {"title": "Edital TJSP", "group": "tjsp-juiz"},
            {"title": "Magistratura SP", "group": "tj-sp-magistratura"},
            {"title": "MPSP Promotor", "group": "mpsp-promotor"}
        ]
        
        ai_response = json.dumps({
            "0": "tjsp-juiz",
            "1": "tjsp-juiz",
            "2": "mpsp-promotor"
        })
        
        with patch("ai.call_ai_api", return_value=ai_response):
            consolidate_groups(items)
            
        assert items[0]["group"] == "tjsp-juiz"
        assert items[1]["group"] == "tjsp-juiz"
        assert items[2]["group"] == "mpsp-promotor"

    def test_consolidate_groups_invalid_json(self, monkeypatch, caplog):
        monkeypatch.setattr("ai.AI_API_KEY", "fake-key")
        items = [
            {"title": "Edital TJSP", "group": "tjsp-juiz"},
            {"title": "Magistratura SP", "group": "tj-sp-magistratura"},
        ]
        
        with patch("ai.call_ai_api", return_value="not a json"):
            consolidate_groups(items)
            
        assert items[0]["group"] == "tjsp-juiz"
        assert "Falha na consolidação de grupos" in caplog.text

    def test_consolidate_groups_empty_items(self, monkeypatch):
        monkeypatch.setattr("ai.AI_API_KEY", "fake-key")
        items = []
        with patch("ai.call_ai_api") as mock_api:
            consolidate_groups(items)
        mock_api.assert_not_called()
