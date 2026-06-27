"""Unit tests for the M3 SQL normalizer (``sql_normalize``).

These are Docker-free: ``normalize`` is a pure function, so the canonical-form
rules can be checked without booting a database. They guard the canonical form
of the M8 read-lock suffix, whose lock-clause keywords sqlglot tokenizes as
``VAR`` (not keyword tokens) — the case that previously escaped lowercasing.
"""

from __future__ import annotations

from reference_harness.sql_normalize import is_canonical, normalize


def test_read_lock_share_suffix_normalizes_to_lowercase() -> None:
    # sqlglot's generator emits the lock-clause keywords uppercase and tokenizes
    # `SHARE`/`OF` as VAR, so they used to survive the keyword-lowercasing pass.
    # M3 rule 2 lowercases keywords, so the canonical form is fully lowercase.
    canonical = "select t0.id from account t0 where t0.id = ? for share of t0"
    assert normalize("select t0.id from account t0 where t0.id = ? for SHARE OF t0") == canonical
    assert is_canonical(canonical)


def test_read_lock_update_suffix_normalizes_to_lowercase() -> None:
    canonical = "select t0.id from account t0 where t0.id = ? for update of t0"
    assert normalize("select t0.id from account t0 where t0.id = ? for UPDATE OF t0") == canonical
    assert is_canonical(canonical)
