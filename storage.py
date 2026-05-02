"""Persistência e estado do CuradorIA / CuradorIA persistence and state

Encapsula o `database.json` e as decisões de "essa URL/domínio está em
penalidade?". O scraper trata isso como uma caixa-preta — só chama as
funções públicas daqui e não conhece a estrutura interna do dicionário.

Wraps `database.json` and the "is this URL/domain currently penalized?"
decisions. The scraper treats this as a black box: it only calls the
public functions here and doesn't know the dict's internal shape.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from config import (
    BLOCK_403_DAYS,
    DATABASE_FILE,
    MAX_URL_FAILURES,
    URL_COOLDOWN_DAYS,
)

logger = logging.getLogger(__name__)


# Persistência / Persistence
def load_database() -> dict:
    """Lê o database.json do disco / Loads database.json from disk"""
    if not os.path.exists(DATABASE_FILE):
        return {}
    with open(DATABASE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_database(db: dict) -> None:
    """Persiste o database.json no disco / Persists database.json to disk"""
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# Bloqueio de domínio inteiro por 403 / Whole-domain block on 403
def is_domain_blocked(db: dict, url: str) -> bool:
    """Verifica se o domínio está bloqueado por 403 prévio / Checks if domain is blocked due to a prior 403"""
    blocks = db.get("_blocks_403", {})
    d = urlparse(url).netloc.replace("www.", "")
    if d not in blocks:
        return False
    deadline = datetime.fromisoformat(blocks[d]) + timedelta(days=BLOCK_403_DAYS)
    return datetime.now(timezone.utc) < deadline


def register_403_block(db: dict, url: str) -> None:
    """Registra bloqueio do domínio após erro 403 / Records domain block after a 403 error"""
    if "_blocks_403" not in db:
        db["_blocks_403"] = {}
    d = urlparse(url).netloc.replace("www.", "")
    db["_blocks_403"][d] = datetime.now(timezone.utc).isoformat()
    logger.warning("Domínio '%s' bloqueado por %d dias após 403.", d, BLOCK_403_DAYS)


def clear_expired_blocks(db: dict) -> None:
    """Remove bloqueios cujo período expirou / Removes blocks whose period expired"""
    blocks = db.get("_blocks_403", {})
    now = datetime.now(timezone.utc)
    expired = [d for d, date_str in blocks.items() if now >= datetime.fromisoformat(date_str) + timedelta(days=BLOCK_403_DAYS)]
    for d in expired:
        del blocks[d]
        logger.info("Bloqueio 403 vencido para '%s', domínio liberado.", d)


# Cooldown por URL após falhas repetidas / Per-URL cooldown after repeated failures
def is_url_in_failure_cooldown(db: dict, url: str) -> bool:
    """True se URL acumulou MAX_URL_FAILURES e cooldown ainda está válido / True if URL hit failure threshold and cooldown still active"""
    entry = db.get(url) or {}
    failures = entry.get("consecutive_failures", 0)
    if failures < MAX_URL_FAILURES:
        return False
    last = entry.get("last_failure")
    if not last:
        return False
    deadline = datetime.fromisoformat(last) + timedelta(days=URL_COOLDOWN_DAYS)
    return datetime.now(timezone.utc) < deadline


def register_url_failure(db: dict, url: str, reason: str, source: str, now_utc: str) -> None:
    """Registra falha (timeout/empty) e incrementa contador / Records failure and bumps counter"""
    entry = db.get(url) or {
        "first_seen": now_utc,
        "last_seen": now_utc,
        "consecutive_absences": 0,
        "source": source,
    }
    entry["consecutive_failures"] = entry.get("consecutive_failures", 0) + 1
    entry["last_failure"] = now_utc
    entry["failure_reason"] = reason
    db[url] = entry


def _clear_url_failures(entry: dict) -> dict:
    entry.pop("consecutive_failures", None)
    entry.pop("last_failure", None)
    entry.pop("failure_reason", None)
    return entry


def record_processed(db: dict, url: str, source: str, now_utc: str) -> None:
    """Marca URL como processada com sucesso, zerando contadores de falha / Marks URL as successfully processed and clears failure counters"""
    entry = db.get(url) or {"first_seen": now_utc, "consecutive_absences": 0}
    if "first_seen" not in entry:
        entry["first_seen"] = now_utc
    entry["last_seen"] = now_utc
    entry["consecutive_absences"] = 0
    entry["source"] = source
    db[url] = _clear_url_failures(entry)
