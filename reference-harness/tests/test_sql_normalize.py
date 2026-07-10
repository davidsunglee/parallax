"""Unit tests for the m-sql SQL normalizer (``sql_normalize``).

These are Docker-free: ``normalize`` is a pure function, so the canonical-form
rules can be checked without booting a database. They guard the canonical form
of the m-read-lock read-lock suffix, whose lock-clause keywords sqlglot tokenizes as
``VAR`` (not keyword tokens) — the case that previously escaped lowercasing.
"""

from __future__ import annotations

from reference_harness.sql_normalize import is_canonical, normalize


def test_read_lock_share_suffix_normalizes_to_lowercase() -> None:
    # sqlglot's generator emits the lock-clause keywords uppercase and tokenizes
    # `SHARE`/`OF` as VAR, so they used to survive the keyword-lowercasing pass.
    # m-sql rule 2 lowercases keywords, so the canonical form is fully lowercase.
    canonical = "select t0.id from account t0 where t0.id = ? for share of t0"
    assert normalize("select t0.id from account t0 where t0.id = ? for SHARE OF t0") == canonical
    assert is_canonical(canonical)


def test_read_lock_update_suffix_normalizes_to_lowercase() -> None:
    canonical = "select t0.id from account t0 where t0.id = ? for update of t0"
    assert normalize("select t0.id from account t0 where t0.id = ? for UPDATE OF t0") == canonical
    assert is_canonical(canonical)


# --- quoted identifiers (reserved words) are preserved, not stripped ---------
# A reserved-word column must be quoted; the normalizer keeps the quotes (with
# the dialect's quote character) rather than stripping them (Postgres) or
# mangling the backticks (MariaDB), which is what broke before the fix.


def test_quoted_reserved_identifier_is_canonical_postgres() -> None:
    canonical = 'select t0.id, t0."order", t0.label from grade t0 where t0."order" > ?'
    assert is_canonical(canonical, "postgres")
    assert normalize(canonical, "postgres") == canonical


def test_quoted_reserved_identifier_is_canonical_mariadb() -> None:
    canonical = "select t0.id, t0.`order`, t0.label from grade t0 where t0.`order` > ?"
    assert is_canonical(canonical, "mariadb")
    assert normalize(canonical, "mariadb") == canonical


def test_quoted_identifier_in_insert_is_canonical() -> None:
    assert is_canonical('insert into grade(id, "order", label) values (?, ?, ?)', "postgres")
    assert is_canonical("insert into grade(id, `order`, label) values (?, ?, ?)", "mariadb")


# --- canonical-rule enforcement (m-sql rule 1: t0,t1 aliases + qualified columns;
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


# --- union all (table-per-concrete-subtype abstract-read lowering) -----------
# `union all` over the effective concrete tables is a NEW canonical SQL surface
# (m-sql). It must be a normalization fixed point: each branch's alias scheme and
# column qualification (rule 1) apply PER BRANCH, branch order is preserved, and the
# NULL-placeholder casts + `familyVariant` string literals it introduces survive.

_TPCS_ROOT_UNION = (
    "select t0.id, t0.title, t0.currency, t0.amount_due, "
    "cast(null as decimal(18, 2)) paid_amount, cast(null as varchar(64)) body, "
    "'Invoice' family_variant from invoice t0 "
    "union all "
    "select t0.id, t0.title, t0.currency, cast(null as decimal(18, 2)) amount_due, "
    "t0.paid_amount, cast(null as varchar(64)) body, 'Receipt' family_variant "
    "from receipt t0 "
    "union all "
    "select t0.id, t0.title, cast(null as varchar(3)) currency, "
    "cast(null as decimal(18, 2)) amount_due, cast(null as decimal(18, 2)) paid_amount, "
    "t0.body, 'Memo' family_variant from memo t0"
)


def test_union_all_read_is_a_normalization_fixed_point() -> None:
    # The full three-branch abstract-root golden is already canonical, and
    # normalizing it is idempotent (the fixed-point property sql_lint enforces).
    assert is_canonical(_TPCS_ROOT_UNION, "postgres")
    assert normalize(_TPCS_ROOT_UNION, "postgres") == _TPCS_ROOT_UNION


def test_union_all_alias_scheme_restarts_per_branch() -> None:
    # Each branch independently uses t0; the alias scheme is NOT globalized across
    # branches (which would demand t0, t1, t2 for three branches).
    two_branch = "select t0.id from invoice t0 union all select t0.id from receipt t0"
    assert is_canonical(two_branch, "postgres")


def test_union_all_preserves_all_and_branch_order() -> None:
    # `union all` (not `union`) is preserved — de-duplication would drop rows — and
    # the left-to-right branch order is stable (a normalizer must not reorder arms).
    assert normalize(_TPCS_ROOT_UNION, "postgres").count(" union all ") == 2
    order = [
        _TPCS_ROOT_UNION.index("from invoice"),
        _TPCS_ROOT_UNION.index("from receipt"),
        _TPCS_ROOT_UNION.index("from memo"),
    ]
    assert order == sorted(order)


# --- only `union all` is a canonical set operation (Phase 5 review, Finding 1) ------
# `union all` is the ONLY canonical m-sql set operation (the TPCS abstract-read
# lowering). A plain `union` silently DE-DUPLICATES rows — changing the read's
# semantics — and `intersect` / `except` are never emitted; all three are non-canonical
# and MUST be rejected, or a golden that used the wrong set op would slip past the lint.
# Reproduce-then-green: before the fix `_canonical_select_scopes` walked any
# `SetOperation`, so these were wrongly accepted as canonical.


def test_plain_union_is_not_canonical() -> None:
    # Same branches as the canonical golden but a de-duplicating `union` (not `union all`).
    plain = "select t0.id from invoice t0 union select t0.id from receipt t0"
    assert not is_canonical(plain, "postgres")


def test_intersect_and_except_are_not_canonical() -> None:
    assert not is_canonical("select t0.id from invoice t0 intersect select t0.id from receipt t0")
    assert not is_canonical("select t0.id from invoice t0 except select t0.id from receipt t0")


def test_union_all_remains_canonical() -> None:
    # The positive twin: `union all` stays a canonical fixed point.
    assert is_canonical("select t0.id from invoice t0 union all select t0.id from receipt t0")


def test_nested_plain_union_inside_union_all_is_not_canonical() -> None:
    # A single non-`union all` arm anywhere in the tree taints the whole statement.
    mixed = (
        "select t0.id from invoice t0 union all "
        "select t0.id from receipt t0 union "
        "select t0.id from memo t0"
    )
    assert not is_canonical(mixed, "postgres")


# --- MariaDB `union all` + `char` NULL-placeholder casts (Phase 5 review, Finding 3) --
# The TPCS abstract-read goldens run on BOTH dialects. MariaDB's CAST target grammar
# does not accept `varchar`, so a bounded-string placeholder casts to `char(n)`
# (m-dialect); `decimal(p, s)` is identical on both. The MariaDB golden must be a
# normalization fixed point under the `mariadb` dialect.
_TPCS_ROOT_UNION_MARIADB = (
    "select t0.id, t0.title, t0.currency, t0.amount_due, "
    "cast(null as decimal(18, 2)) paid_amount, cast(null as char(64)) body, "
    "'Invoice' family_variant from invoice t0 "
    "union all "
    "select t0.id, t0.title, t0.currency, cast(null as decimal(18, 2)) amount_due, "
    "t0.paid_amount, cast(null as char(64)) body, 'Receipt' family_variant "
    "from receipt t0 "
    "union all "
    "select t0.id, t0.title, cast(null as char(3)) currency, "
    "cast(null as decimal(18, 2)) amount_due, cast(null as decimal(18, 2)) paid_amount, "
    "t0.body, 'Memo' family_variant from memo t0"
)


def test_mariadb_union_all_char_cast_is_a_fixed_point() -> None:
    assert is_canonical(_TPCS_ROOT_UNION_MARIADB, "mariadb")
    assert normalize(_TPCS_ROOT_UNION_MARIADB, "mariadb") == _TPCS_ROOT_UNION_MARIADB


def test_mariadb_varchar_cast_normalizes_to_char() -> None:
    # A MariaDB golden authored with `varchar` is NOT a fixed point: sqlglot's mysql
    # dialect renders the CAST target as `char`, so lint would reject the `varchar`
    # spelling — the mechanism that keeps the MariaDB goldens honest.
    authored = "select cast(null as varchar(3)) currency, t0.id from memo t0"
    expected = "select cast(null as char(3)) currency, t0.id from memo t0"
    assert normalize(authored, "mariadb") == expected
    assert not is_canonical(authored, "mariadb")


def test_union_all_rejects_non_canonical_branch_alias() -> None:
    # A bad alias in ONE branch fails the whole statement (rule 1, per branch).
    bad = "select o.id from invoice o union all select t0.id from receipt t0"
    assert not is_canonical(bad, "postgres")


def test_union_all_rejects_unqualified_column_in_a_branch() -> None:
    bad = "select id from invoice t0 union all select t0.id from receipt t0"
    assert not is_canonical(bad, "postgres")


def test_union_all_rejects_inline_literal_in_a_branch() -> None:
    # A parameter literal in any branch must be a ? bind (rule 4).
    bad = "select t0.id from invoice t0 where t0.id = 5 union all select t0.id from receipt t0"
    assert not is_canonical(bad, "postgres")


# --- string literals + NULL-placeholder casts (the union-all projection) -----
# String literals (the `familyVariant` branch literal) and cast(null as <type>)
# NULL placeholders appear in canonical m-sql only via the TPCS lowering. The
# literal keeps its single quotes and case; a parametrized type binds its length
# list tight (`decimal(18, 2)`, not `decimal (18, 2)`).


def test_string_literal_is_requoted_and_case_preserved() -> None:
    canonical = "select 'Invoice' family_variant from invoice t0"
    assert is_canonical(canonical, "postgres")
    # sqlglot strips the surrounding quotes on re-tokenize; the normalizer re-wraps
    # them, and the literal's case is not lowered.
    assert normalize("select 'Invoice' AS family_variant from invoice t0", "postgres") == canonical


def test_null_placeholder_cast_binds_type_params_tight() -> None:
    canonical = "select cast(null as decimal(18, 2)) amount_due, t0.id from invoice t0"
    assert is_canonical(canonical, "postgres")
    # `numeric` canonicalizes to `decimal`, and the length list renders tight to the
    # type name rather than with an interposed space.
    assert (
        normalize(
            "select cast(null as numeric(18,2)) amount_due, t0.id from invoice t0", "postgres"
        )
        == canonical
    )
