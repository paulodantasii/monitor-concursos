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
AI_MODEL = "gpt-5-nano"
AI_URL = "https://api.openai.com/v1/chat/completions"

# Instruções de comportamento da IA / AI behavior instructions
PROMPT_RELEVANCE = """Sua tarefa é avaliar se o conteúdo abaixo é uma atualização, previsão, ou divulgação, de edital, concurso, processo seletivo, certame, ou similares, que sejam relevantes

RELEVANTE — sempre que o conteúdo tiver
Qualquer cargo, carreira, vaga, estágio de pós-graduação ou residência que exija formação superior (bacharelado/diploma) em Direito
Vagas com atividades jurídicas, judiciais, contratuais, legais, legislativas, procuradorias, advocacias, analistas, assistentes, técnicos, ou assessores, de matéria jurídica, judicial, contratual, legal, ou legislativa
Cargos em órgãos públicos, empresas públicas ou privadas, ou autarquias que, pelo contexto, demandem diploma em Direito ou conhecimento jurídico especializado

NÃO RELEVANTE — se o conteúdo for apenas sobre
Cargos que NÃO exijam formação (curso superior/bacharelato/diploma) em Direito, como, por exemplo: professores de ensino básico, médicos, engenheiros, enfermeiros, saúde, limpeza, motoristas ou técnicos de outras áreas
Cargos de nível médio ou técnico sem relevância jurídica
Páginas que sejam apenas listagens ou conjuntos de vários concursos, ou de provas para download, ou de índices de banca, ou agregadores de diversos concursos sem foco em um certame específico
Páginas que sejam sobre cursos, eventos ou aulas

Se for relevante, identifique também STATUS do certame, escolhendo UMA das opções
"announced"; se autorização publicada, comissão formada, banca contratada, edital previsto mas ainda não publicado
"registration_open"; se edital publicado e inscrições em andamento
"registration_closed"; se inscrições já fecharam, aguardando prova
"exam_taken"; se prova aplicada, aguardando gabarito ou resultado preliminar
"result"; se gabarito divulgado, resultado preliminar, recursos, resultado final
"closed"; se certame finalizado, convocações, posses, prorrogação de validade

Se for relevante, identifique também GROUP no formato "orgao-localidade-cargo" usando apenas letras minúsculas, números e hífens, SEM acentos
Exemplos
"cgm-porto-velho-ro-auditor"
"prefeitura-martinopolis-sp-advogado"
"sefaz-ce-auditor-fiscal"
"pgm-caxias-do-sul-rs-procurador"
"al-ms-analista-juridico"
"tjto-residencia-juridica"

Responda APENAS no seguinte formato JSON, sem nenhum texto adicional:
{"relevant": true, "reason": "Em um resumo de ~500 caracteres, descreva o cargo e o contexto específico do certame sem usar frases como "relevante para bacharéis em Direito", "exige formação em Direito" ou similares, essas conclusões são óbvias; agregue informação relevante, não reafirme o óbvio", "status": "...escolha uma das opções...", "group": "orgao-localidade-cargo"}
ou
{"relevant": false, "reason": "Irrelevante"}

Conteúdo para avaliar:
"""

PROMPT_CONSOLIDATION = """Abaixo está uma lista JSON de notícias sobre concursos, cada uma com um 'id', 'title', 'reason' e um 'group' (identificador provisório).
Sua tarefa é identificar quais notícias falam do mesmo certame/concurso e unificar o campo 'group'.
Se duas ou mais notícias falam de um mesmo orgão, provavelmente são do mesmo certame, analise com cuidado, o 'group' delas deve ser idêntico (repita um dos identificadores já existentes ou crie um novo padronizado).
Responda APENAS com um objeto JSON válido, onde as chaves são as strings dos IDs originais e os valores são as strings do novo 'group' unificado.
Exemplo: Se o ID "1" e "3" falam do TJSP para Juiz, e o ID "2" fala do MPSP, responda:
{"1": "tjsp-juiz", "3": "tjsp-juiz", "2": "mpsp-promotor"}

Lista de itens:
"""

def normalize_group(g: str) -> str:
    """Normaliza o nome do grupo gerado por IA (remove acentos e espaços) / Normalizes the AI-generated group name (removes accents and spaces)"""
    if not g:
        return ""
    g = unicodedata.normalize("NFKD", g).encode("ascii", "ignore").decode("ascii")
    g = g.lower().strip()
    g = re.sub(r"[^a-z0-9-]", "-", g)
    g = re.sub(r"-+", "-", g).strip("-")
    return g

def call_ai_api(system_prompt: str, user_content: str) -> str:
    """Faz a chamada HTTP para a API da OpenAI com lógica de repetição / Makes the HTTP call to the OpenAI API with retry logic"""
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "developer", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "max_completion_tokens": 50000,
        "verbosity": "low",
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
            choice = data["choices"][0]
            content = choice["message"].get("content")
            finish_reason = choice.get("finish_reason", "unknown")
            if not content:
                logger.warning("OpenAI retornou conteúdo vazio (finish_reason=%s) na tentativa %d/3", finish_reason, attempt + 1)
                if attempt < 2:
                    time.sleep(10 * (attempt + 1))
                continue
            return content.strip()
        except requests.exceptions.HTTPError as e:
            body = ""
            try:
                body = e.response.text[:500]
            except Exception:
                pass
            logger.error("OpenAI tentativa %d/3 falhou [HTTP %s]: %s | body: %s", attempt + 1, e.response.status_code if e.response is not None else "?", e, body)
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
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

    content = f"URL: {url}\nTítulo: {title}\n\nTexto:\n{text}"
    response = call_ai_api(PROMPT_RELEVANCE, content)

    if not response:
        return {"relevant": False, "reason": "empty response from AI"}

    try:
        raw = json.loads(response)
    except json.JSONDecodeError:
        return {"relevant": False, "reason": "error parsing response", "raw_response": response}

    result = _validate_evaluation(raw)
    result["raw_response"] = response
    return result


def consolidate_groups(relevant_items: list) -> None:
    """Faz um passe de consolidação para unificar os identificadores de grupo de itens que tratam do mesmo certame / Consolidation pass to unify group IDs of items about the same exam"""
    if not AI_API_KEY or len(relevant_items) <= 1:
        return

    items_to_send = [
        {
            "id": str(i),
            "title": item.get("real_title") or item.get("title") or "",
            "reason": item.get("reason", ""),
            "group": item.get("group", "")
        }
        for i, item in enumerate(relevant_items)
    ]

    content = json.dumps(items_to_send, ensure_ascii=False, indent=2)
    response = call_ai_api(PROMPT_CONSOLIDATION, content)

    if not response:
        logger.warning("Falha na consolidação de grupos: sem resposta da IA.")
        return

    try:
        mapping = json.loads(response)
        if isinstance(mapping, dict):
            for i, item in enumerate(relevant_items):
                str_i = str(i)
                if str_i in mapping:
                    item["group"] = normalize_group(mapping[str_i])
    except json.JSONDecodeError:
        logger.warning("Falha na consolidação de grupos: resposta não é JSON.")
    except Exception as e:
        logger.warning("Falha na consolidação de grupos: %s", e)
