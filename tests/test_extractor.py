"""Testes do módulo extractor / extractor module tests"""
from bs4 import BeautifulSoup

from extractor import (
    _extract_from_semantic_containers,
    _extract_with_fallback,
    clean_tracking_params,
    extract_real_url,
    host_matches_target,
    is_relevant_url,
    normalize_url,
)


class TestHostMatchesTarget:
    def test_exact_domain_matches(self):
        assert host_matches_target("pciconcursos.com.br") is True

    def test_www_prefix_matches(self):
        assert host_matches_target("www.pciconcursos.com.br") is True

    def test_subdomain_matches(self):
        assert host_matches_target("noticias.pciconcursos.com.br") is True

    def test_other_target_domain_matches(self):
        assert host_matches_target("acheconcursos.com.br") is True

    def test_unknown_domain_rejected(self):
        assert host_matches_target("outrosite.com") is False

    def test_substring_attack_rejected(self):
        # Bug fix 10.3: antes "pciconcursos.com.br" in "pciconcursos.com.br.evil.com" era True
        assert host_matches_target("pciconcursos.com.br.evil.com") is False

    def test_prefix_attack_rejected(self):
        assert host_matches_target("notpciconcursos.com.br") is False

    def test_empty_host_rejected(self):
        assert host_matches_target("") is False


class TestIsRelevantUrl:
    def test_news_url_accepted(self):
        assert is_relevant_url("https://www.pciconcursos.com.br/noticias/algo") is True

    def test_login_url_rejected(self):
        assert is_relevant_url("https://www.pciconcursos.com.br/login/") is False

    def test_image_url_rejected(self):
        assert is_relevant_url("https://www.pciconcursos.com.br/foto.jpg") is False

    def test_outside_domain_rejected(self):
        assert is_relevant_url("https://outrosite.com/concurso") is False

    def test_substring_attack_rejected(self):
        assert is_relevant_url("https://pciconcursos.com.br.evil.com/concurso") is False


class TestCleanTrackingParams:
    def test_no_query_unchanged(self):
        url = "https://example.com/page"
        assert clean_tracking_params(url) == url

    def test_strips_utm_source(self):
        result = clean_tracking_params("https://example.com/page?utm_source=alert")
        assert result == "https://example.com/page"

    def test_keeps_legitimate_params(self):
        result = clean_tracking_params("https://example.com/page?id=42&utm_source=alert")
        assert result == "https://example.com/page?id=42"

    def test_strips_multiple_trackers(self):
        result = clean_tracking_params("https://x.com/p?utm_source=a&fbclid=b&gclid=c")
        assert result == "https://x.com/p"

    def test_case_insensitive_param_names(self):
        result = clean_tracking_params("https://x.com/p?UTM_SOURCE=alert&id=1")
        assert result == "https://x.com/p?id=1"

    def test_preserves_path_and_fragment(self):
        result = clean_tracking_params("https://x.com/path/sub?utm_source=a#section")
        assert result == "https://x.com/path/sub#section"


class TestNormalizeUrl:
    def test_strips_fragment(self):
        assert normalize_url("https://x.com/page#anchor") == "https://x.com/page"

    def test_strips_fragment_and_tracking(self):
        result = normalize_url("https://x.com/page?utm_source=a#anchor")
        assert result == "https://x.com/page"

    def test_keeps_legitimate_query(self):
        result = normalize_url("https://x.com/page?id=1#anchor")
        assert result == "https://x.com/page?id=1"


class TestExtractRealUrl:
    def test_unwraps_google_alerts_url(self):
        wrapped = "https://www.google.com/url?rct=j&sa=t&url=https://real.com/page&ct=ga"
        assert extract_real_url(wrapped) == "https://real.com/page"

    def test_returns_non_google_url_unchanged(self):
        url = "https://example.com/page"
        assert extract_real_url(url) == url


class TestExtractFromSemanticContainers:
    """Cobertura do item 2.8: cascata de fallbacks estruturados"""

    def test_extracts_from_article_tag(self):
        html = "<html><body><article>" + ("Conteúdo do artigo. " * 20) + "</article><nav>menu</nav></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        text = _extract_from_semantic_containers(soup)
        assert "Conteúdo do artigo" in text
        assert "menu" not in text

    def test_extracts_from_main_tag(self):
        html = "<html><body><main>" + ("Texto principal. " * 20) + "</main></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        text = _extract_from_semantic_containers(soup)
        assert "Texto principal" in text

    def test_extracts_from_content_class(self):
        html = '<html><body><div class="article-body">' + ("Corpo. " * 30) + "</div></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        text = _extract_from_semantic_containers(soup)
        assert "Corpo" in text

    def test_returns_empty_when_no_container(self):
        html = "<html><body><div>texto avulso</div></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_from_semantic_containers(soup) == ""

    def test_skips_too_short_container(self):
        html = "<html><body><article>oi</article></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_from_semantic_containers(soup) == ""


class TestExtractWithFallback:
    def test_falls_back_to_get_text_when_no_structure(self):
        html = "<html><body><script>alert(1)</script><div>" + ("Conteúdo. " * 50) + "</div></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        text = _extract_with_fallback(html, soup)
        assert "Conteúdo" in text
        assert "alert(1)" not in text  # script removido
