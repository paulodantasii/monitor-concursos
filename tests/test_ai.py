"""Testes do módulo ai / ai module tests"""
import json
from unittest.mock import patch

import pytest

from ai import (
    evaluate_relevance,
    has_legal_keywords,
    normalize_group,
)


class TestHasLegalKeywords:
    def test_explicit_legal_keyword(self):
        assert has_legal_keywords("Concurso AGU", "vagas para advogado público") is True

    def test_case_insensitive(self):
        assert has_legal_keywords("PROCURADOR", "") is True

    def test_handles_accents(self):
        assert has_legal_keywords("Direito Constitucional", "") is True

    def test_word_in_text_only(self):
        assert has_legal_keywords("Edital 2026", "vagas para advocacia pública") is True

    def test_unrelated_content_rejected(self):
        assert has_legal_keywords("Concurso de Matemática", "professor de ensino médio") is False

    def test_empty_input(self):
        assert has_legal_keywords("", "") is False

    def test_none_input_safe(self):
        assert has_legal_keywords(None, None) is False


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

    def test_no_legal_keywords_skips_ai(self, monkeypatch):
        """Pré-filtro 3.1: economiza chamada à IA quando não há indício jurídico"""
        monkeypatch.setattr("ai.AI_API_KEY", "fake-key")
        text = "Concurso para professor de matemática do ensino fundamental " * 5
        with patch("ai.call_ai_api") as mock_api:
            result = evaluate_relevance("https://x.com", "Edital", text)
        mock_api.assert_not_called()
        assert result["relevant"] is False
        assert result["reason"] == "no legal keywords"

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
        assert result["reason"] == "error after 3 attempts"
