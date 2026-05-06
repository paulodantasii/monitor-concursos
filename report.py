"""Geração do relatório HTML / HTML report generation"""
import os
import re
from datetime import datetime
from html import escape
from urllib.parse import urlparse

from config import HISTORY_DIR, OUTPUT_HTML, OUTPUT_RELEVANT, STATUS_LABELS, TITLE_SUFFIXES


def get_site_name(url: str) -> str:
    """Extrai o nome principal do site para exibir na tag visual / Extracts the main site name to display in the visual tag"""
    host = urlparse(url).netloc.replace("www.", "")
    return host.upper()


def clean_title(title: str) -> str:
    """Remove os nomes dos sites de notícias do final dos títulos / Removes news site names from the end of article titles"""
    for suffix in TITLE_SUFFIXES:
        if title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title.strip()


def group_relevant_items(relevant_items: list) -> list:
    """Agrupa artigos por exame com base na etiqueta 'group' gerada pela IA / Groups articles by exam based on the AI-generated 'group' tag"""
    groups: dict = {}
    for item in relevant_items:
        group_id = (item.get("group") or "").strip().lower()
        if not group_id:
            group_id = f"_isolated_{id(item)}"
        groups.setdefault(group_id, []).append(item)

    group_list = [
        {"group_id": gid, "items": items, "size": len(items)}
        for gid, items in groups.items()
    ]
    group_list.sort(key=lambda g: g["size"], reverse=True)
    return group_list


def _card_search_blob(items: list) -> str:
    """Concatena texto dos slides para alimentar o filtro JS / Concatenates slide text to feed the JS filter"""
    parts: list = []
    for item in items:
        parts.append(item.get("real_title") or item.get("title") or "")
        parts.append(item.get("reason", ""))
        parts.append(item.get("group", ""))
        parts.append(item.get("status", ""))
        parts.append(get_site_name(item.get("url", "")))
    return " ".join(p for p in parts if p).lower()


def render_group_card(group: dict) -> str:
    """Gera o HTML de um cartão de exame / Renders the HTML of an exam card"""
    items = group["items"]
    size = group["size"]

    highlight_class = " highlight" if size >= 3 else ""
    sources_badge = f'<div class="sources-badge">{size} {"fonte" if size == 1 else "fontes"}</div>'
    search_blob = escape(_card_search_blob(items))

    slides_html = ""
    for item in items:
        raw_title = item.get("real_title") or item.get("title") or "Ver link"
        title = escape(clean_title(raw_title))
        url = item.get("url", "")
        safe_url = escape(url)
        reason = escape(item.get("reason", ""))
        site = escape(get_site_name(url))
        status = item.get("status", "")
        status_label, status_color = STATUS_LABELS.get(status, ("", "#6c757d"))
        status_html = (
            f'<span class="status-tag" style="background:{status_color};">{status_label}</span>'
            if status_label else ""
        )
        slides_html += f"""
            <div class="slide">
                {status_html}<span class="site-tag">{site}</span>
                <h2><a href="{safe_url}" target="_blank" rel="noopener noreferrer">{title}</a></h2>
                <p class="reason">{reason}</p>
                <a href="{safe_url}" target="_blank" rel="noopener noreferrer" class="btn">Acessar matéria →</a>
            </div>
        """

    controls_html = ""
    if size > 1:
        indicators = "".join(
            f'<span class="indicator{" active" if i == 0 else ""}"></span>'
            for i in range(size)
        )
        controls_html = f"""
            <div class="controls">
                <button class="arrow arrow-left" aria-label="Anterior">‹</button>
                <div class="indicators">{indicators}</div>
                <button class="arrow arrow-right" aria-label="Próxima">›</button>
            </div>
        """

    return f"""
        <div class="group-card{highlight_class}" data-search="{search_blob}">
            {sources_badge}
            <div class="carousel">
                <div class="slides">
                    {slides_html}
                </div>
            </div>
            {controls_html}
        </div>
    """


def _format_run_seconds(run_seconds) -> str:
    """Formata o tempo de execução em algo amigável / Formats run time in a friendly way"""
    if run_seconds is None:
        return ""
    if run_seconds < 60:
        return f"{run_seconds:.0f}s"
    minutes = int(run_seconds // 60)
    seconds = int(run_seconds % 60)
    return f"{minutes}min {seconds}s"


def _pretty_date(iso_date: str) -> str:
    """2026-05-02 → 02/05/2026 / Convert ISO date to BR format"""
    try:
        y, m, d = iso_date.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso_date


def _render_archive_banner(date_str: str, archive_link: str) -> str:
    """Banner exibido em edições arquivadas / Banner shown on archived editions"""
    if not archive_link:
        return ""
    return f"""
        <div class="archive-banner">
            Você está vendo a edição de<strong>{escape(date_str)}</strong>·
            <a href="{escape(archive_link)}">Ver versão mais recente</a>
        </div>
    """


def _render_history_section(history: list) -> str:
    """Lista colapsada de edições anteriores / Collapsed list of past editions"""
    if not history:
        return ""
    items_html = ""
    for entry in history:
        date = entry.get("date", "")
        filename = entry.get("filename", "")
        pretty = escape(_pretty_date(date))
        if entry.get("is_current"):
            items_html += f'<li class="current">{pretty} (esta edição)</li>'
        else:
            items_html += f'<li><a href="{escape(filename)}">{pretty}</a></li>'
    return f"""
        <details class="history-section">
            <summary>Edições anteriores ({len(history)})</summary>
            <ul class="history-list">{items_html}</ul>
        </details>
    """


_CSS = """
    :root {
        --bg: #f0f2f5; --card-bg: #ffffff; --text: #1a1a2e; --text-muted: #666;
        --header-bg-from: #1a1a2e; --header-bg-to: #16213e; --header-text: #ffffff;
        --accent: #e94560; --shadow: rgba(0,0,0,0.07);
        --border: #f0f2f5; --input-bg: #ffffff; --input-border: #d8dde3;
        --site-tag-bg: #f0f2f5; --site-tag-text: #555; --controls-bg: #fafbfc;
        --arrow-bg: #ffffff; --arrow-border: #ddd; --indicator: #ccc;
    }
    [data-theme="dark"] {
        --bg: #0f1419; --card-bg: #1a1f2e; --text: #e1e6f0; --text-muted: #8a93a6;
        --header-bg-from: #0a0e1a; --header-bg-to: #14192a; --header-text: #e1e6f0;
        --accent: #f25575; --shadow: rgba(0,0,0,0.4);
        --border: #2a3142; --input-bg: #14192a; --input-border: #2a3142;
        --site-tag-bg: #2a3142; --site-tag-text: #b3bccf; --controls-bg: #14192a;
        --arrow-bg: #2a3142; --arrow-border: #2a3142; --indicator: #3a4356;
    }
    @media (prefers-color-scheme: dark) {
        :root:not([data-theme="light"]) {
            --bg: #0f1419; --card-bg: #1a1f2e; --text: #e1e6f0; --text-muted: #8a93a6;
            --header-bg-from: #0a0e1a; --header-bg-to: #14192a; --header-text: #e1e6f0;
            --accent: #f25575; --shadow: rgba(0,0,0,0.4);
            --border: #2a3142; --input-bg: #14192a; --input-border: #2a3142;
            --site-tag-bg: #2a3142; --site-tag-text: #b3bccf; --controls-bg: #14192a;
            --arrow-bg: #2a3142; --arrow-border: #2a3142; --indicator: #3a4356;
        }
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: var(--bg); color: var(--text); min-height: 100vh; transition: background 0.2s, color 0.2s; }
    header { background: linear-gradient(135deg, var(--header-bg-from) 0%, var(--header-bg-to) 100%);
             color: var(--header-text); padding: 2rem 1.5rem 1.5rem; text-align: center; position: relative; }
    header h1 { font-size: 1.5rem; font-weight: 700; margin-bottom: 0.4rem; }
    header p { font-size: 0.85rem; opacity: 0.75; }
    header .meta { font-size: 0.72rem; opacity: 0.55; margin-top: 0.4rem; }
    .badge { display: inline-block; background: var(--accent); color: white; font-size: 0.8rem; font-weight: 600;
             padding: 0.3rem 0.8rem; border-radius: 20px; margin-top: 0.8rem; }
    .theme-toggle { position: absolute; top: 1rem; right: 1rem; background: rgba(255,255,255,0.12);
                    border: 1px solid rgba(255,255,255,0.2); color: var(--header-text); width: 36px; height: 36px;
                    border-radius: 50%; cursor: pointer; font-size: 1rem; display: flex; align-items: center;
                    justify-content: center; transition: background 0.2s; }
    .theme-toggle:hover { background: rgba(255,255,255,0.2); }
    .container { max-width: 680px; margin: 0 auto; padding: 1.5rem 1rem; }
    .search-bar { margin-bottom: 1rem; position: relative; }
    .search-bar input { width: 100%; padding: 0.6rem 0.9rem 0.6rem 2.2rem; border-radius: 10px;
                        border: 1px solid var(--input-border); background: var(--input-bg); color: var(--text);
                        font-size: 0.9rem; outline: none; transition: border-color 0.2s; }
    .search-bar input:focus { border-color: var(--accent); }
    .search-bar::before { content: '🔎'; position: absolute; left: 0.7rem; top: 50%;
                          transform: translateY(-50%); font-size: 0.9rem; opacity: 0.6; pointer-events: none; }
    .filter-info { font-size: 0.78rem; color: var(--text-muted); margin: 0.5rem 0 1rem; min-height: 1em; }
    .group-card { background: var(--card-bg); border-radius: 12px; margin-bottom: 1rem;
                  box-shadow: 0 2px 8px var(--shadow); border-left: 4px solid var(--accent);
                  overflow: hidden; position: relative; transition: background 0.2s; }
    .group-card.highlight { border-left-width: 6px; }
    .sources-badge { position: absolute; top: 0.8rem; right: 0.8rem; background: var(--header-bg-from);
                     color: white; font-size: 0.7rem; font-weight: 600; padding: 0.25rem 0.55rem;
                     border-radius: 12px; z-index: 2; }
    .carousel { position: relative; overflow: hidden; }
    .slides { display: flex; transition: transform 0.35s ease; }
    .slide { min-width: 100%; padding: 1.2rem 1.3rem 0.5rem; }
    .status-tag { display: inline-block; color: white; font-size: 0.7rem; font-weight: 600;
                  padding: 0.2rem 0.55rem; border-radius: 6px; margin-bottom: 0.5rem; }
    .site-tag { display: inline-block; background: var(--site-tag-bg); color: var(--site-tag-text);
                font-size: 0.7rem; font-weight: 600; padding: 0.2rem 0.55rem; border-radius: 6px;
                margin-bottom: 0.5rem; margin-left: 0.4rem; }
    .slide h2 { font-size: 1rem; font-weight: 600; line-height: 1.4; margin-bottom: 0.5rem; color: var(--text); }
    .slide h2 a { color: inherit; text-decoration: none; }
    .slide h2 a:hover { color: var(--accent); }
    .reason { font-size: 0.85rem; color: var(--text-muted); line-height: 1.5; margin-bottom: 0.9rem; }
    .btn { display: inline-block; background: var(--header-bg-from); color: white; font-size: 0.82rem;
           font-weight: 600; padding: 0.45rem 1rem; border-radius: 8px; text-decoration: none;
           transition: background 0.2s; }
    .btn:hover { background: var(--accent); }
    .controls { display: flex; justify-content: space-between; align-items: center;
                padding: 0.6rem 1rem 1rem; border-top: 1px solid var(--border); background: var(--controls-bg); }
    .arrow { background: var(--arrow-bg); border: 1px solid var(--arrow-border); color: var(--text);
             width: 32px; height: 32px; border-radius: 50%; font-size: 1rem; cursor: pointer;
             display: flex; align-items: center; justify-content: center; line-height: 1; }
    .arrow:disabled { opacity: 0.3; cursor: default; }
    .arrow:not(:disabled):hover { background: var(--header-bg-from); color: white; }
    .indicators { display: flex; gap: 0.4rem; }
    .indicator { width: 8px; height: 8px; border-radius: 50%; background: var(--indicator); }
    .indicator.active { background: var(--accent); }
    .empty { text-align: center; color: var(--text-muted); padding: 3rem 1rem; font-size: 0.95rem; }
    .archive-banner { background: var(--accent); color: white; padding: 0.8rem 1rem; border-radius: 8px;
                      margin-bottom: 1rem; font-size: 0.9rem; display: flex; align-items: center;
                      flex-wrap: wrap; gap: 0.5rem; }
    .archive-banner a { color: white; text-decoration: underline; font-weight: 600; }
    .history-section { background: var(--card-bg); border-radius: 12px; padding: 1rem 1.2rem;
                       margin-top: 2rem; box-shadow: 0 2px 8px var(--shadow); }
    .history-section summary { cursor: pointer; font-weight: 600; color: var(--text);
                               font-size: 0.9rem; padding: 0.2rem 0; }
    .history-section summary:hover { color: var(--accent); }
    .history-list { list-style: none; padding: 0; margin: 1rem 0 0; max-height: 400px; overflow-y: auto; }
    .history-list li { padding: 0.5rem 0; border-bottom: 1px solid var(--border); font-size: 0.88rem; }
    .history-list li:last-child { border-bottom: none; }
    .history-list li.current { color: var(--accent); font-weight: 600; }
    .history-list a { color: var(--text-muted); text-decoration: none; display: block; }
    .history-list a:hover { color: var(--accent); }
    footer { text-align: center; padding: 1.5rem; font-size: 0.78rem; color: var(--text-muted); }
"""

_JS = """
    // Tema (dark mode) / Theme (dark mode)
    (function () {
        var saved = localStorage.getItem('curadoria-theme');
        if (saved === 'dark' || saved === 'light') {
            document.documentElement.setAttribute('data-theme', saved);
        }
    })();

    function toggleTheme() {
        var html = document.documentElement;
        var current = html.getAttribute('data-theme');
        if (!current) {
            current = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        var next = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        localStorage.setItem('curadoria-theme', next);
        var btn = document.getElementById('theme-toggle');
        if (btn) btn.textContent = next === 'dark' ? '☀️' : '🌙';
    }

    document.addEventListener('DOMContentLoaded', function () {
        var btn = document.getElementById('theme-toggle');
        if (btn) {
            var current = document.documentElement.getAttribute('data-theme') ||
                          (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            btn.textContent = current === 'dark' ? '☀️' : '🌙';
            btn.addEventListener('click', toggleTheme);
        }

        // Carrossel / Carousel
        document.querySelectorAll('.group-card').forEach(function (card) {
            var slidesEl = card.querySelector('.slides');
            if (!slidesEl) return;
            var total = slidesEl.children.length;
            var current = 0;
            var leftArrow = card.querySelector('.arrow-left');
            var rightArrow = card.querySelector('.arrow-right');
            var indicators = card.querySelectorAll('.indicator');

            function update() {
                slidesEl.style.transform = 'translateX(-' + (current * 100) + '%)';
                indicators.forEach(function (ind, i) { ind.classList.toggle('active', i === current); });
                if (leftArrow) leftArrow.disabled = current === 0;
                if (rightArrow) rightArrow.disabled = current === total - 1;
            }
            if (leftArrow) leftArrow.addEventListener('click', function () {
                if (current > 0) { current--; update(); }
            });
            if (rightArrow) rightArrow.addEventListener('click', function () {
                if (current < total - 1) { current++; update(); }
            });
            update();
        });

        // Busca / Search
        var searchInput = document.getElementById('search');
        var filterInfo = document.getElementById('filter-info');
        var allCards = document.querySelectorAll('.group-card');

        function applyFilter() {
            var q = (searchInput.value || '').trim().toLowerCase();
            var visible = 0;
            allCards.forEach(function (card) {
                var blob = card.getAttribute('data-search') || '';
                var match = !q || blob.indexOf(q) !== -1;
                card.style.display = match ? '' : 'none';
                if (match) visible++;
            });
            if (filterInfo) {
                if (!q) filterInfo.textContent = '';
                else filterInfo.textContent = visible + ' de ' + allCards.length + ' certames correspondem a "' + q + '"';
            }
        }

        if (searchInput) {
            searchInput.addEventListener('input', applyFilter);
            searchInput.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') { searchInput.value = ''; applyFilter(); }
            });
        }
    });
"""


def generate_html(
    groups: list,
    date_str: str,
    total_analyzed: int,
    total_relevant: int,
    run_seconds: float = None,
    history: list = None,
    archive_link: str = None,
) -> str:
    """Gera a página HTML completa para hospedagem no GitHub Pages / Generates the full HTML page for GitHub Pages

    history: lista [{date, filename, is_current}] de edições anteriores (somente na versão atual)
    archive_link: URL para a versão mais recente (somente em arquivos do histórico)
    """
    cards = "".join(render_group_card(g) for g in groups)
    if not groups:
        cards = '<div class="empty">Nenhuma oportunidade relevante encontrada nesta verificação.</div>'

    elapsed = _format_run_seconds(run_seconds)
    meta_html = (
        f'<p class="meta">Última verificação: {escape(date_str)} · Tempo de execução: {escape(elapsed)}</p>'
        if elapsed else
        f'<p class="meta">Última verificação: {escape(date_str)}</p>'
    )

    search_bar_html = """
        <div class="search-bar">
            <input id="search" type="search" placeholder="Buscar por órgão, cargo, status..." aria-label="Buscar">
        </div>
        <div class="filter-info" id="filter-info"></div>
    """ if groups else ""

    archive_banner_html = _render_archive_banner(date_str, archive_link)
    history_html = _render_history_section(history)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CuradorIA de Carreiras Jurídicas</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚖️</text></svg>">
    <style>{_CSS}</style>
</head>
<body>
    <header>
        <button id="theme-toggle" class="theme-toggle" aria-label="Alternar tema">🌙</button>
        <h1>CuradorIA de Carreiras Jurídicas</h1>
        <p>Foram analisados {total_analyzed} artigos na última verificação.</p>
        <div class="badge">Encontrados {total_relevant} artigos relevantes sobre {len(groups)} certames.</div>
        {meta_html}
    </header>
    <div class="container">
        {archive_banner_html}
        {search_bar_html}
        {cards}
        {history_html}
    </div>
    <footer>Gerado automaticamente · CuradorIA de Carreiras Jurídicas · Todos os créditos reservados aos respectivos autores dos artigos encontrados.</footer>
    <script>{_JS}</script>
</body>
</html>"""

if __name__ == "__main__":
    def _parse_new_relevant(file_path: str) -> tuple:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        date_match = re.search(r"Verificação:\s*(.+)", content)
        analyzed_match = re.search(r"Links analisados:\s*(\d+)", content)
        relevant_match = re.search(r"Links relevantes:\s*(\d+)", content)
        
        date_str = date_match.group(1) if date_match else datetime.now().isoformat()
        try:
            dt = datetime.fromisoformat(date_str)
            date_str = dt.strftime("%d/%m/%Y às %Hh%M")
        except:
            pass

        total_analyzed = int(analyzed_match.group(1)) if analyzed_match else 0
        
        items = []
        blocks = content.split("=" * 60)
        if len(blocks) > 1:
            item_blocks = blocks[1].strip().split("\n\n")
            for block in item_blocks:
                item = {}
                for line in block.split("\n"):
                    if line.startswith("Title:   "):
                        item["real_title"] = line[len("Title:   "):].strip()
                    elif line.startswith("URL:     "):
                        item["url"] = line[len("URL:     "):].strip()
                    elif line.startswith("Status:  "):
                        item["status"] = line[len("Status:  "):].strip()
                    elif line.startswith("Group:   "):
                        item["group"] = line[len("Group:   "):].strip()
                    elif line.startswith("Reason:  "):
                        item["reason"] = line[len("Reason:  "):].strip()
                if "url" in item:
                    items.append(item)
        return items, date_str, total_analyzed

    if not os.path.exists(OUTPUT_RELEVANT):
        print(f"Arquivo {OUTPUT_RELEVANT} não encontrado.")
    else:
        relevant_items, run_date_str, tot_analyzed = _parse_new_relevant(OUTPUT_RELEVANT)
        grouped = group_relevant_items(relevant_items)
        
        os.makedirs(HISTORY_DIR, exist_ok=True)
        hist_files = sorted(
            (f for f in os.listdir(HISTORY_DIR) if f.startswith("report-") and f.endswith(".html")),
            reverse=True,
        )
        hist_entries = [
            {
                "date": f[len("report-"):-len(".html")],
                "filename": f"{HISTORY_DIR}/{f}",
                "is_current": False,
            }
            for f in hist_files
        ]
        if hist_entries:
            hist_entries[0]["is_current"] = True
            
        generated_html = generate_html(
            grouped,
            run_date_str,
            tot_analyzed,
            len(relevant_items),
            run_seconds=None,
            history=hist_entries,
        )
        
        with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
            f.write(generated_html)
            
        print(f"HTML regenerado com sucesso em {OUTPUT_HTML} com {len(relevant_items)} itens relevantes!")
