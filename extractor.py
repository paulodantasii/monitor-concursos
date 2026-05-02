"""Funções de URL e extração de conteúdo / URL handling and page content extraction

Reúne tudo que opera sobre URLs (normalizar, classificar, desempacotar Google
Alerts) e a extração de texto de páginas — com cascata semântica antes de cair
no `get_text()` puro.

Groups everything that operates on URLs (normalize, classify, unwrap Google
Alerts) and page text extraction — with a semantic cascade before falling back
to plain `get_text()`.
"""
import logging
import re
from urllib.parse import (
    parse_qs,
    parse_qsl,
    unquote,
    urlencode,
    urlparse,
    urlunparse,
)

import requests
import trafilatura
from bs4 import BeautifulSoup

from config import (
    HEADERS,
    IGNORE_PATTERNS,
    MAX_PAGE_CHARS,
    RELEVANT_PATTERNS,
    TARGET_DOMAINS,
    TRACKING_PARAMS,
)

logger = logging.getLogger(__name__)

# Containers semânticos que tipicamente envolvem o miolo do artigo / Semantic
# containers that typically wrap the article body
_CONTENT_CLASS_RE = re.compile(
    r"(article-?body|post-?content|entry-?content|news-?content|content-?body|main-?content|story-?body)",
    re.I,
)
_CONTENT_ID_RE = re.compile(r"(article|post|content|main|story)", re.I)
_MIN_FALLBACK_LENGTH = 100  # Texto menor que isso provavelmente não é o miolo


# Funções de URL / URL helpers
def host_matches_target(host: str) -> bool:
    """Match exato por domínio ou subdomínio (não substring) / Exact host or subdomain match"""
    host = host.replace("www.", "")
    return any(host == d or host.endswith("." + d) for d in TARGET_DOMAINS)


def is_relevant_url(url: str) -> bool:
    """Verifica se o link pertence aos domínios e padrões permitidos / Checks if URL matches allowed domains and patterns"""
    host = urlparse(url).netloc
    if not host_matches_target(host):
        return False
    for p in IGNORE_PATTERNS:
        if re.search(p, url, re.IGNORECASE):
            return False
    for p in RELEVANT_PATTERNS:
        if re.search(p, url, re.IGNORECASE):
            return True
    return False


def clean_tracking_params(url: str) -> str:
    """Remove parâmetros de rastreamento (utm_*, fbclid, gclid, etc.) / Strips tracking params"""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    params = parse_qsl(parsed.query, keep_blank_values=True)
    cleaned = [(k, v) for k, v in params if k.lower() not in TRACKING_PARAMS]
    if not cleaned:
        return urlunparse(parsed._replace(query=""))
    return urlunparse(parsed._replace(query=urlencode(cleaned)))


def normalize_url(url: str) -> str:
    """Remove fragmentos (#) e parâmetros de rastreamento / Strips anchor fragments and tracking params"""
    url = url.split("#")[0].strip()
    parsed = urlparse(url)
    url = urlunparse(parsed._replace(fragment=""))
    return clean_tracking_params(url)


def extract_real_url(href: str) -> str:
    """Desempacota URLs mascaradas pelo Google Alerts / Unwraps URLs masked by Google Alerts"""
    parsed = urlparse(href)
    if "google.com" in parsed.netloc and parsed.path == "/url":
        qs = parse_qs(parsed.query)
        if "url" in qs:
            return unquote(qs["url"][0])
    return href


# Extração de texto / Text extraction
def _extract_from_semantic_containers(soup: BeautifulSoup) -> str:
    """Tenta extrair texto de <article>, <main>, .content, #content / Tries to extract text from semantic containers"""
    candidates = [
        soup.find("article"),
        soup.find("main"),
        soup.find(attrs={"role": "main"}),
        soup.find(class_=_CONTENT_CLASS_RE),
        soup.find(id=_CONTENT_ID_RE),
    ]
    for node in candidates:
        if node is None:
            continue
        text = node.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= _MIN_FALLBACK_LENGTH:
            return text
    return ""


def _extract_with_fallback(html_content: str, soup: BeautifulSoup) -> str:
    """Cascata: trafilatura → containers semânticos → get_text limpo / Cascade: trafilatura → semantic containers → cleaned get_text"""
    text = trafilatura.extract(html_content, include_comments=False)
    if text:
        return text

    text = _extract_from_semantic_containers(soup)
    if text:
        return text

    # Último recurso: remover ruído conhecido e pegar tudo que sobrou
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _extract_title(soup: BeautifulSoup) -> str:
    """Extrai o título da página: <title> > <h1> / Extracts page title"""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        if title:
            return title
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


def extract_page(url: str, timeout: int = 20) -> tuple:
    """Extrai apenas o texto relevante de uma página / Extracts only the useful body text from a page

    Retorna (titulo, texto, error). error é "" em sucesso, "timeout" ou "403" em falhas conhecidas.
    """
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS)
        resp.raise_for_status()
        html_content = resp.text

        soup = BeautifulSoup(html_content, "html.parser")
        title = _extract_title(soup)
        text = _extract_with_fallback(html_content, soup)

        return title, text[:MAX_PAGE_CHARS], ""

    except requests.exceptions.Timeout:
        logger.warning("TIMEOUT em %s", url)
        return "", "", "timeout"
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 403:
            logger.warning("403 Forbidden em %s", url)
            return "", "", "403"
        logger.error("HTTP em %s: %s", url, e)
        return "", "", ""
    except Exception as e:
        logger.error("Erro em %s: %s", url, e)
        return "", "", ""
