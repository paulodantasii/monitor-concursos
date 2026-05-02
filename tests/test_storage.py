"""Testes do módulo storage / storage module tests"""
from datetime import datetime, timedelta, timezone

from config import (
    BLOCK_403_DAYS,
    MAX_URL_FAILURES,
    URL_COOLDOWN_DAYS,
)
from storage import (
    clear_expired_blocks,
    is_domain_blocked,
    is_url_in_failure_cooldown,
    record_processed,
    register_403_block,
    register_url_failure,
)


class TestUrlFailureCooldown:
    def test_unknown_url_not_in_cooldown(self):
        assert is_url_in_failure_cooldown({}, "https://x.com/p") is False

    def test_url_with_few_failures_not_in_cooldown(self):
        db = {"https://x.com/p": {"consecutive_failures": MAX_URL_FAILURES - 1}}
        assert is_url_in_failure_cooldown(db, "https://x.com/p") is False

    def test_recent_failures_trigger_cooldown(self):
        now = datetime.now(timezone.utc).isoformat()
        db = {
            "https://x.com/p": {
                "consecutive_failures": MAX_URL_FAILURES,
                "last_failure": now,
            }
        }
        assert is_url_in_failure_cooldown(db, "https://x.com/p") is True

    def test_old_failures_release_cooldown(self):
        old = (datetime.now(timezone.utc) - timedelta(days=URL_COOLDOWN_DAYS + 1)).isoformat()
        db = {
            "https://x.com/p": {
                "consecutive_failures": MAX_URL_FAILURES,
                "last_failure": old,
            }
        }
        assert is_url_in_failure_cooldown(db, "https://x.com/p") is False

    def test_register_failure_creates_entry(self):
        db = {}
        now = datetime.now(timezone.utc).isoformat()
        register_url_failure(db, "https://x.com/p", "timeout", "scraping", now)
        assert db["https://x.com/p"]["consecutive_failures"] == 1
        assert db["https://x.com/p"]["failure_reason"] == "timeout"
        assert db["https://x.com/p"]["last_failure"] == now

    def test_register_failure_increments(self):
        now = datetime.now(timezone.utc).isoformat()
        db = {}
        for _ in range(3):
            register_url_failure(db, "https://x.com/p", "timeout", "scraping", now)
        assert db["https://x.com/p"]["consecutive_failures"] == 3

    def test_register_failure_preserves_existing_entry(self):
        now = datetime.now(timezone.utc).isoformat()
        db = {"https://x.com/p": {"first_seen": "2025-01-01", "source": "alert"}}
        register_url_failure(db, "https://x.com/p", "empty", "alert", now)
        assert db["https://x.com/p"]["first_seen"] == "2025-01-01"
        assert db["https://x.com/p"]["consecutive_failures"] == 1


class TestRecordProcessed:
    def test_clears_failure_counters(self):
        now = datetime.now(timezone.utc).isoformat()
        db = {"https://x.com/p": {
            "first_seen": "2025-01-01",
            "consecutive_failures": 3,
            "last_failure": now,
            "failure_reason": "timeout",
        }}
        record_processed(db, "https://x.com/p", "scraping", now)
        entry = db["https://x.com/p"]
        assert "consecutive_failures" not in entry
        assert "last_failure" not in entry
        assert "failure_reason" not in entry
        assert entry["last_seen"] == now
        assert entry["consecutive_absences"] == 0

    def test_creates_entry_for_new_url(self):
        db = {}
        now = datetime.now(timezone.utc).isoformat()
        record_processed(db, "https://x.com/p", "alert", now)
        assert db["https://x.com/p"]["first_seen"] == now
        assert db["https://x.com/p"]["source"] == "alert"

    def test_preserves_first_seen(self):
        now = datetime.now(timezone.utc).isoformat()
        db = {"https://x.com/p": {"first_seen": "2025-01-01", "consecutive_absences": 2}}
        record_processed(db, "https://x.com/p", "scraping", now)
        assert db["https://x.com/p"]["first_seen"] == "2025-01-01"


class TestDomainBlock403:
    def test_no_block_returns_false(self):
        assert is_domain_blocked({}, "https://x.com/p") is False

    def test_recent_block_active(self):
        db = {}
        register_403_block(db, "https://example.com/page")
        assert is_domain_blocked(db, "https://example.com/other") is True

    def test_block_strips_www(self):
        db = {"_blocks_403": {"example.com": datetime.now(timezone.utc).isoformat()}}
        assert is_domain_blocked(db, "https://www.example.com/page") is True

    def test_old_block_inactive(self):
        old = (datetime.now(timezone.utc) - timedelta(days=BLOCK_403_DAYS + 1)).isoformat()
        db = {"_blocks_403": {"example.com": old}}
        assert is_domain_blocked(db, "https://example.com/page") is False

    def test_clear_expired_blocks(self):
        old = (datetime.now(timezone.utc) - timedelta(days=BLOCK_403_DAYS + 1)).isoformat()
        new = datetime.now(timezone.utc).isoformat()
        db = {"_blocks_403": {"old.com": old, "new.com": new}}
        clear_expired_blocks(db)
        assert "old.com" not in db["_blocks_403"]
        assert "new.com" in db["_blocks_403"]
