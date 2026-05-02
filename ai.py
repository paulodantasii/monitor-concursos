import json
import logging
import re
import time
import unicodedata
import os
import requests

from config import STATUS_LABELS

logger = logging.getLogger(__name__)

# Configurações da API da IA / AI API settings
AI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
AI_MODEL = "gpt-4o-mini"
AI_URL = "https://api.openai.com/v1/chat/completions"

# Instruções de comportamento da IA / AI behavior instructions
PROMPT_RELEVANCE = """Sua tarefa é avaliar se o conteúdo abaixo é um artigo de atualização, previsão, ou divulgação, de edital, concurso, processo seletivo, certame, e similares, que sejam relevantes para um bacharel em Direito que estuda para concursos públicos nas seguintes áreas:

RELEVANTE — sempre que o conteúdo tiver:
- Procurador ou Advogado em qualquer órgão do executivo ou legislativo: AGU, PGFN, PGF, PGE, PGM, câmaras municipais, assembleias legislativas, TCU, TCE, TCM, agências reguladoras federais como ANATEL, ANEEL, ANVISA, ANAC, ANS, ANA, ANTAQ, ANTT, ANP, CADE, Banco Central (BACEN), conselhos profissionais como OAB, CRM, CREA, CFM, CFBM, CRBM, CONFEA, etc
- Procurador ou Advogado da Caixa Econômica Federal, Banco do Brasil, Petrobras, BNDES, Correios, EBSERH, Embrapa, Serpro, DATAPREV, autarquias e fundações federais, estaduais e municipais, etc
- Analista ou Assessor de matéria jurídica ou correlatas em órgãos do executivo federal, estadual ou municipal, secretarias, ministérios, autarquias, agências reguladoras, empresas públicas, etc
- Analista ou Assessor de matéria jurídica ou correlatas de Tribunal de Contas como TCU, TCE, TCM, etc
- Cargos que exijam bacharelado em Direito e cujo conteúdo programático envolva direito público, como: administrativo, constitucional, tributário, civil, financeiro, licitações, contratos públicos, execução fiscal, etc
- Residência Jurídica em qualquer órgão público
- Estágio de pós-graduação em Direito em qualquer órgão público
- Programas de formação jurídica remunerada em órgãos públicos
- Todos os cargos que, por algum dos motivos acima, pareçam necessitar de curso superior (diploma) em Direito mas não estejam incluídos nessa lista

NÃO RELEVANTE — se o conteúdo for integralmente apenas sobre:
- Cargos que NÃO exijam formação (curso superior/bacharelato/diploma) em Direito, como, por exemplo: professores de ensino básico, médicos, engenheiros, enfermeiros, saúde, limpeza, motoristas, técnicos de outras áreas, etc
- Cargos de nível médio ou técnico sem relevância jurídica
- Páginas que sejam apenas listagens de provas para download, índices de banca, ou agregadores de outros concursos sem foco em um certame específico

Se for relevante, identifique também:

1. STATUS do certame, escolhendo UMA das opções:
   - "announced" → autorização publicada, comissão formada, banca contratada, edital previsto mas ainda não publicado
   - "registration_open" → edital publicado e inscrições em andamento
   - "registration_closed" → inscrições já fecharam, aguardando prova
   - "exam_taken" → prova aplicada, aguardando gabarito ou resultado preliminar
   - "result" → gabarito divulgado, resultado preliminar, recursos, resultado final
   - "closed" → certame finalizado, convocações, posses, prorrogação de validade

2. GROUP no formato "orgao-localidade-cargo" usando apenas letras minúsculas, números e hífens, SEM acentos. Exemplos:
   - "cgm-porto-velho-ro-auditor"
   - "prefeitura-martinopolis-sp-advogado"
   - "sefaz-ce-auditor-fiscal"
   - "pgm-caxias-do-sul-rs-procurador"
   - "al-ms-analista-juridico"
   - "tjto-residencia-juridica"
   Use o mesmo identificador para notícias que tratem do mesmo concurso, mesmo que escritas de formas diferentes. Se houver dúvida sobre o cargo específico, omita a parte do cargo.

REGRAS PARA O CAMPO "reason":
- Descreva o cargo e o contexto específico do certame
- Nunca use frases como "relevante para bacharéis em Direito", "exige formação em Direito" ou similares
- Essas conclusões são óbvias; o motivo deve agregar informação nova, não reafirmar o óbvio

Responda APENAS no seguinte formato JSON, sem nenhum texto adicional:
{"relevant": true, "reason": "Cargo e contexto específico do certame", "status": "registration_open", "group": "orgao-localidade-cargo"}
ou
{"relevant": false, "reason": "explicação em uma linha"}

Conteúdo para avaliar:
"""

# Palavras-chave do pré-filtro: se nenhuma aparecer, não chamamos a IA / Pre-filter keywords: if none appear we skip the AI call
LEGAL_KEYWORDS = (
    "direito", "juridic", "advogad", "procurad",
    "advocacia", "procuradoria", "bacharel",
    "judiciario", "judicial",
)

def _strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

def has_legal_keywords(title: str, text: str) -> bool:
    """Verifica se há indício de matéria jurídica no conteúdo / Checks for any sign of legal subject matter in the content"""
    combined = _strip_accents(f"{title or ''} {text or ''}").lower()
    return any(kw in combined for kw in LEGAL_KEYWORDS)

def normalize_group(g: str) -> str:
    """Normaliza o nome do grupo gerado por IA (remove acentos e espaços) / Normalizes the AI-generated group name (removes accents and spaces)"""
    if not g:
        return ""
    g = unicodedata.normalize("NFKD", g).encode("ascii", "ignore").decode("ascii")
    g = g.lower().strip()
    g = re.sub(r"[^a-z0-9-]", "-", g)
    g = re.sub(r"-+", "-", g).strip("-")
    return g

def call_ai_api(prompt: str) -> str:
    """Faz a chamada HTTP para a API da OpenAI com lógica de repetição / Makes the HTTP call to the OpenAI API with retry logic"""
    payload = {
        "model": AI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 400,
        "response_format": {"type": "json_object"},
    }
    for attempt in range(3):
        try:
            resp = requests.post(
                AI_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {AI_API_KEY}",
                },
                json=payload,
                timeout=45,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error("OpenAI tentativa %d/3 falhou: %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
    return ""

def _validate_evaluation(data) -> dict:
    """Valida e normaliza a resposta da IA contra um schema esperado / Validates and normalizes the AI response against an expected schema"""
    if not isinstance(data, dict):
        return {"relevant": False, "reason": "response not a json object"}

    relevant = data.get("relevant")
    if not isinstance(relevant, bool):
        return {"relevant": False, "reason": "missing or invalid 'relevant' field"}

    reason_raw = data.get("reason", "")
    reason = reason_raw if isinstance(reason_raw, str) else str(reason_raw or "")

    result = {"relevant": relevant, "reason": reason}

    if relevant:
        status_raw = data.get("status", "")
        status = status_raw.strip().lower() if isinstance(status_raw, str) else ""
        result["status"] = status if status in STATUS_LABELS else ""

        group_raw = data.get("group", "")
        result["group"] = normalize_group(group_raw if isinstance(group_raw, str) else "")

    return result


def evaluate_relevance(url: str, title: str, text: str) -> dict:
    """Envia o conteúdo da página para a IA e retorna uma avaliação validada / Sends page content to the AI and returns a validated evaluation"""
    if not AI_API_KEY:
        return {"relevant": False, "reason": "AI_API_KEY not configured"}
    if not text or len(text) < 50:
        return {"relevant": False, "reason": "insufficient text"}

    if not has_legal_keywords(title, text):
        return {"relevant": False, "reason": "no legal keywords"}

    content = f"URL: {url}\nTítulo: {title}\n\nTexto:\n{text}"
    response = call_ai_api(PROMPT_RELEVANCE + content)

    if not response:
        return {"relevant": False, "reason": "error after 3 attempts"}

    try:
        raw = json.loads(response)
    except json.JSONDecodeError:
        return {"relevant": False, "reason": "error parsing response"}

    return _validate_evaluation(raw)
