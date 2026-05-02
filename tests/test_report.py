"""Testes do módulo report / report module tests"""
import pytest

from report import clean_title, generate_html, get_site_name, group_relevant_items


class TestCleanTitle:
    def test_strips_known_suffix(self):
        assert clean_title("Notícia X - PCI Concursos") == "Notícia X"

    def test_strips_pipe_suffix(self):
        assert clean_title("Notícia X | PCI Concursos") == "Notícia X"

    def test_unknown_suffix_unchanged(self):
        assert clean_title("Notícia X - Site Desconhecido") == "Notícia X - Site Desconhecido"

    def test_trims_whitespace(self):
        assert clean_title("  Notícia X  ") == "Notícia X"


class TestGetSiteName:
    def test_strips_www(self):
        assert get_site_name("https://www.pciconcursos.com.br/noticia") == "PCICONCURSOS.COM.BR"

    def test_uppercases(self):
        assert get_site_name("https://example.com/x") == "EXAMPLE.COM"


class TestGroupRelevantItems:
    def test_groups_by_group_id(self):
        items = [
            {"url": "u1", "group": "pgm-foo-procurador"},
            {"url": "u2", "group": "pgm-foo-procurador"},
            {"url": "u3", "group": "pgm-bar-advogado"},
        ]
        groups = group_relevant_items(items)
        assert len(groups) == 2
        assert groups[0]["size"] == 2
        assert groups[1]["size"] == 1

    def test_isolates_items_without_group(self):
        items = [
            {"url": "u1", "group": ""},
            {"url": "u2", "group": ""},
        ]
        groups = group_relevant_items(items)
        assert len(groups) == 2

    def test_largest_group_first(self):
        items = [
            {"url": "u1", "group": "small"},
            {"url": "u2", "group": "big"},
            {"url": "u3", "group": "big"},
            {"url": "u4", "group": "big"},
        ]
        groups = group_relevant_items(items)
        assert groups[0]["group_id"] == "big"
        assert groups[0]["size"] == 3


class TestGenerateHtmlSecurity:
    """Cobertura do bug 1.2: escape de href e rel='noopener noreferrer'"""

    def _make_groups(self, items):
        return group_relevant_items(items)

    def test_xss_in_url_is_escaped(self):
        items = [{
            "url": 'https://x.com/p"><script>alert(1)</script>',
            "title": "Edital",
            "real_title": "",
            "reason": "x",
            "status": "",
            "group": "g",
        }]
        html = generate_html(self._make_groups(items), "01/01/2026", 1, 1)
        # A string crua de ataque NÃO deve aparecer; entidades HTML escapadas SIM
        assert '"><script>alert(1)</script>' not in html
        assert "&lt;script&gt;" in html or "&quot;&gt;" in html

    def test_external_links_have_rel_noopener(self):
        items = [{
            "url": "https://example.com/page",
            "title": "Edital",
            "real_title": "",
            "reason": "x",
            "status": "",
            "group": "g",
        }]
        html = generate_html(self._make_groups(items), "01/01/2026", 1, 1)
        assert 'rel="noopener noreferrer"' in html

    def test_xss_in_title_is_escaped(self):
        items = [{
            "url": "https://x.com/p",
            "title": "<script>alert(1)</script>",
            "real_title": "",
            "reason": "x",
            "status": "",
            "group": "g",
        }]
        html = generate_html(self._make_groups(items), "01/01/2026", 1, 1)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_empty_groups_renders_empty_state(self):
        html = generate_html([], "01/01/2026", 0, 0)
        assert "Nenhuma oportunidade relevante" in html
