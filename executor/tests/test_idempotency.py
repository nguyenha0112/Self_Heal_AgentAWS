"""Unit tests cho fallback idempotency lock."""
from __future__ import annotations

from idempotency import IdempotencyLock


class _Cfg:
    aws_region = "ap-southeast-1"
    audit_bucket = ""
    idempotency_table = ""
    idempotency_ttl_seconds = 86400


def test_in_memory_duplicate_denied():
    lock = IdempotencyLock(_Cfg())
    assert lock.acquire("dup-key") is True
    assert lock.acquire("dup-key") is False

