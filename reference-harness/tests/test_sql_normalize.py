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


# --- canonical-rule enforcement (M3 rule 1: t0,t1 aliases + qualified columns;
#     rule 4: parameters as ? binds) ----------------------------------------
# Lowercasing + re-spacing alone is not enough: a lowercase-but-non-canonical
# read must be REJECTED so sql_lint cannot accept it as a fixture.


def test_rejects_non_canonical_table_alias() -> None:
    # alias `o` is not the canonical t0 (rule 1)
    assert not is_canonical("select o.id from orders o")


def test_rejects_out_of_sequence_alias() -> None:
    # a single table must be t0, not t1
    assert not is_canonical("select t1.id from orders t1")


def test_rejects_unqualified_column_in_read() -> None:
    # bare `id` is not alias-qualified (rule 1)
    assert not is_canonical("select id from orders t0")


def test_rejects_inline_predicate_literal() -> None:
    # `42` is a parameter and must be a ? bind (rule 4)
    assert not is_canonical("select t0.id from orders t0 where t0.id = 42")


def test_rejects_inline_in_list_literal() -> None:
    assert not is_canonical("select t0.id from orders t0 where t0.id in (1, 2)")


def test_rejects_inline_between_literal() -> None:
    assert not is_canonical("select t0.id from orders t0 where t0.amt between 1 and 9")


def test_rejects_inline_limit_literal() -> None:
    assert not is_canonical("select t0.id from orders t0 limit 10")


def test_rejects_insert_values_literal() -> None:
    assert not is_canonical("insert into account(id) values (1)")


def test_rejects_insert_values_literal_in_multi_row_insert() -> None:
    assert not is_canonical("insert into account(id) values (?), (2)")


def test_accepts_insert_values_placeholders_in_multi_row_insert() -> None:
    assert is_canonical("insert into account(id, owner) values (?, ?), (?, ?)")


# Structural literals are NOT parameters — they are part of the canonical form
# and must stay accepted.


def test_accepts_none_identity_structural_literal() -> None:
    assert is_canonical("select t0.id, t0.name from orders t0 where 1 = 0")


def test_accepts_exists_probe_and_correlated_alias() -> None:
    assert is_canonical(
        "select t0.id from orders t0 where exists "
        "(select 1 from order_item t1 where t1.order_id = t0.id)"
    )


# DML has its own canonical shape: the target table is unaliased and columns
# are bare. The read-only rules (1) MUST NOT be applied to it.


def test_accepts_dml_with_bare_columns() -> None:
    assert is_canonical("update balance set out_z = ? where bal_id = ? and out_z = ?")
    assert is_canonical("insert into balance(bal_id, val) values (?, ?)")
