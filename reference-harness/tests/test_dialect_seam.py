"""Unit tests for the Phase 10 MariaDB dialect seam (m-dialect), DB-free.

These pin the localization claim: adding MariaDB as the second dialect touches
ONLY the dialect seam — the normalizer's dialect mapping + read-lock rendering,
the DDL type table, and the provider's infinity / instant adapters — never the
spec prose or the fixtures. The end-to-end execution against a real MariaDB
container is exercised by the compatibility suite (``-k dialect``); these tests
cover the seam logic that needs no database.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from pymysql.constants import FIELD_TYPE

from reference_harness.case import load_model
from reference_harness.ddl_builder import _column_type, ddl_for, quote_identifier
from reference_harness.providers.mariadb import (
    _INFINITY_SENTINEL,
    _from_db_value,
    _is_boolean_field,
    _to_db_bind,
    _to_pymysql,
)
from reference_harness.sql_normalize import is_canonical, normalize, sqlglot_dialect

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


# --- the normalizer knows the mariadb dialect --------------------------------


def test_mariadb_maps_to_mysql_engine() -> None:
    assert sqlglot_dialect("mariadb") == "mysql"
    # An unknown / native dialect passes through unchanged.
    assert sqlglot_dialect("postgres") == "postgres"


def test_plain_read_is_identical_canonical_form_on_both_dialects() -> None:
    sql = "select t0.id, t0.name from orders t0 where t0.id = ?"
    assert is_canonical(sql, "postgres")
    assert is_canonical(sql, "mariadb")


def test_temporal_read_and_insert_are_canonical_on_mariadb() -> None:
    for sql in (
        "select t0.bal_id, t0.acct_num, t0.val, t0.in_z, t0.out_z "
        "from balance t0 where t0.out_z = ?",
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
    ):
        assert is_canonical(sql, "mariadb"), sql


# --- the read-lock divergence is rendered through the seam -------------------


def test_read_lock_diverges_per_dialect() -> None:
    """Postgres `for share of t0` and MariaDB `lock in share mode` are EACH the
    canonical fixed point for their own dialect — the marquee Phase 10 seam."""
    pg = "select t0.id, t0.owner, t0.balance from account t0 where t0.id = ? for share of t0"
    md = "select t0.id, t0.owner, t0.balance from account t0 where t0.id = ? lock in share mode"
    assert is_canonical(pg, "postgres")
    assert is_canonical(md, "mariadb")


def test_mariadb_lock_normalizes_idempotently() -> None:
    md = "select t0.id from account t0 where t0.id = ? lock in share mode"
    once = normalize(md, "mariadb")
    assert once.endswith("lock in share mode")
    assert normalize(once, "mariadb") == once


def test_sqlglot_for_share_is_rewritten_to_mariadb_lock() -> None:
    """sqlglot would render the shared lock as `for share`; the seam rewrites it
    to MariaDB's `lock in share mode` so the golden SQL is MariaDB-idiomatic."""
    md = "select t0.id from account t0 where t0.id = ? lock in share mode"
    assert "for share" not in normalize(md, "mariadb")


# --- the DDL type table maps neutral types to MariaDB ------------------------


def test_mariadb_type_mappings() -> None:
    assert _column_type("timestamp", None, "mariadb") == "datetime(6)"
    assert _column_type("boolean", None, "mariadb") == "tinyint(1)"
    assert _column_type("int64", None, "mariadb") == "bigint"
    assert _column_type("decimal(18,2)", None, "mariadb") == "decimal(18,2)"
    assert _column_type("string", 32, "mariadb") == "varchar(32)"
    assert _column_type("string", None, "mariadb") == "text"


def test_mariadb_ddl_derives_from_descriptor() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/balance.yaml")
    (create,) = ddl_for(model, "mariadb")
    # The temporal interval columns use DATETIME(6) (no native infinity); the
    # money column uses DECIMAL — both behind the seam, derived from the model.
    assert "in_z datetime(6)" in create
    assert "out_z datetime(6)" in create
    assert "val decimal(18,2)" in create


# --- identifier quoting (the divergent quote character) ----------------------


def test_quote_identifier_leaves_simple_names_unquoted() -> None:
    # Simple lowercase, non-reserved names are returned unchanged on both
    # dialects, so the generated DDL/DML for every existing model is untouched.
    for name in ("id", "in_z", "card_network", "order_id"):
        assert quote_identifier(name, "postgres") == name
        assert quote_identifier(name, "mariadb") == name


def test_quote_identifier_quotes_reserved_words_per_dialect() -> None:
    # A reserved word MUST be quoted, with the dialect's divergent quote char.
    assert quote_identifier("order", "postgres") == '"order"'
    assert quote_identifier("order", "mariadb") == "`order`"
    assert quote_identifier("select", "postgres") == '"select"'
    assert quote_identifier("select", "mariadb") == "`select`"


def test_quote_identifier_quotes_non_simple_names() -> None:
    # Uppercase / special-character names are not simple, so they are quoted too.
    assert quote_identifier("fullName", "postgres") == '"fullName"'
    assert quote_identifier("fullName", "mariadb") == "`fullName`"


def test_reserved_word_column_ddl_is_quoted() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/grade.yaml")
    assert '"order" integer not null' in ddl_for(model, "postgres")[0]
    assert "`order` int not null" in ddl_for(model, "mariadb")[0]
    # the simple columns stay unquoted
    assert "id bigint not null" in ddl_for(model, "postgres")[0]


# --- the infinity / instant adapters (the max-sentinel fallback) -------------


def test_infinity_literal_maps_to_max_sentinel_and_back() -> None:
    # The suite's `infinity` literal becomes the largest DATETIME(6) on the way
    # in, and reads back as `infinity` on the way out — so a fixture authored once
    # against native-infinity Postgres compares identically on MariaDB.
    assert _to_db_bind("infinity") == _INFINITY_SENTINEL
    assert _from_db_value(_INFINITY_SENTINEL) == "infinity"


def test_iso_instant_binds_become_naive_utc_datetimes() -> None:
    bound = _to_db_bind("2024-06-01T00:00:00+00:00")
    assert bound == dt.datetime(2024, 6, 1, 0, 0, 0)
    assert bound.tzinfo is None


def test_finite_datetime_reads_back_as_iso_utc() -> None:
    read = _from_db_value(dt.datetime(2024, 6, 1, 0, 0, 0))
    assert read == "2024-06-01T00:00:00+00:00"


def test_non_temporal_scalars_pass_through() -> None:
    assert _to_db_bind(42) == 42
    assert _to_db_bind("A-100") == "A-100"
    assert _from_db_value(250) == 250


def test_tinyint_one_field_is_boolean() -> None:
    # `boolean` is the only neutral type mapped to `tinyint(1)`; pymysql reports it
    # as FIELD_TYPE.TINY with display length 1. A wider integer (int32 -> `int` /
    # FIELD_TYPE.LONG) or a non-(1) tinyint is not a boolean column.
    assert _is_boolean_field(FIELD_TYPE.TINY, 1) is True
    assert _is_boolean_field(FIELD_TYPE.LONG, 11) is False
    assert _is_boolean_field(FIELD_TYPE.TINY, 4) is False


def test_tinyint_one_reads_back_as_bool() -> None:
    # MariaDB has no native boolean; a `tinyint(1)` column reads back as int 0/1.
    # The type-aware coercion returns a real bool so it compares to the fixture's
    # boolean — the row comparator keeps bool out of numeric space (`true` != `1`).
    assert _from_db_value(1, is_boolean=True) is True
    assert _from_db_value(0, is_boolean=True) is False
    # A NULL boolean column stays None; a non-boolean int is untouched even when the
    # flag is off (the default), so ordinary integer columns pass through unchanged.
    assert _from_db_value(None, is_boolean=True) is None
    assert _from_db_value(250, is_boolean=False) == 250


def test_placeholder_translation_escapes_percent() -> None:
    # `?` -> `%s`. A literal `%` is escaped only when pymysql will receive an args
    # tuple; bindless SQL must preserve the literal because no formatting runs.
    assert _to_pymysql("select t0.id from t0 where t0.id = ?") == (
        "select t0.id from t0 where t0.id = %s"
    )
    assert _to_pymysql("select id from t where sku like '%50%'") == (
        "select id from t where sku like '%50%'"
    )
    assert _to_pymysql("select id from t where sku like '%50%'", escape_percent=True) == (
        "select id from t where sku like '%%50%%'"
    )
