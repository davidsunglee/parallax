"""Docker-free dialect contract suite (m-dialect).

Table-driven over the concrete dialects (one row today: postgres), covering the
`m-dialect` decision catalog: identifier quoting, NULL ordering per direction,
row-limit rendering, shared-read-lock application, neutral-scalar column-type
mapping (parametric decimals, bounded strings), the bytes projection shape and
its projection-introduced bind, the structured-document extraction / typed-cast
forms, canonical `?` -> `%s` placeholder translation, the infinity sentinel, and
the native error-code classification predicates. Pure strategy, no driver I/O.

Dual-marked ``unit`` so the pure strategy is covered by the branch-coverage gate
and also runs under ``pytest -m dialect``.
"""

from __future__ import annotations

import pytest

from parallax.core.dialect import INFINITY, POSTGRES, Dialect, dialect_for

pytestmark = [pytest.mark.unit, pytest.mark.dialect]

DIALECTS: list[Dialect] = [POSTGRES]
IDS = [d.name for d in DIALECTS]


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_identifier_quoting(dialect: Dialect) -> None:
    assert dialect.quote("owner") == "owner"  # simple lowercase: unquoted
    assert dialect.quote("order") == '"order"'  # reserved: quoted
    assert dialect.quote("MixedCase") == '"MixedCase"'  # non-simple: quoted
    assert dialect.qualified("t0", "id") == "t0.id"
    assert dialect.qualified("t0", "order") == 't0."order"'


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_null_ordering_per_direction(dialect: Dialect) -> None:
    assert dialect.null_order("t0.c", "asc") == "t0.c asc"
    assert dialect.null_order("t0.c", "desc") == "t0.c desc nulls last"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_row_limit_and_read_lock(dialect: Dialect) -> None:
    assert dialect.limit_clause() == "limit ?"
    assert dialect.read_lock_suffix("t0") == "for share of t0"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_column_type_mapping(dialect: Dialect) -> None:
    assert dialect.column_type("int64", None) == "bigint"
    assert dialect.column_type("int32", None) == "integer"
    assert dialect.column_type("boolean", None) == "boolean"
    assert dialect.column_type("timestamp", None) == "timestamptz"
    assert dialect.column_type("json", None) == "jsonb"
    assert dialect.column_type("uuid", None) == "uuid"
    assert dialect.column_type("bytes", None) == "bytea"
    assert dialect.column_type("string", 64) == "varchar(64)"
    assert dialect.column_type("string", None) == "text"
    assert dialect.column_type("decimal(18,2)", None) == "numeric(18, 2)"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_column_type_rejects_unknown(dialect: Dialect) -> None:
    with pytest.raises(ValueError, match="no postgres column type"):
        dialect.column_type("mystery", None)


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_bytes_projection_shape(dialect: Dialect) -> None:
    expr, binds = dialect.project("t0", "payload", "bytes")
    assert expr == "encode(t0.payload, ?) payload_hex"
    assert binds == ["hex"]
    plain_expr, plain_binds = dialect.project("t0", "name", "string")
    assert plain_expr == "t0.name"
    assert plain_binds == []


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_nested_extraction_and_cast(dialect: Dialect) -> None:
    extract, binds = dialect.nested_extract("t0", "address", ("geo", "country"))
    assert extract == "jsonb_extract_path_text(t0.address, ?, ?)"
    assert binds == ["geo", "country"]
    assert dialect.nested_cast("EXT", "string") == "EXT"  # text compares directly
    assert dialect.nested_cast("EXT", "int64") == "cast(EXT as bigint)"
    assert dialect.nested_cast("EXT", "float64") == "cast(EXT as double precision)"
    assert dialect.nested_cast("EXT", "decimal(18,2)") == "cast(EXT as decimal(18, 2))"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_array_guard_fragment_binds_the_path_twice(dialect: Dialect) -> None:
    # m-sql "To-many — exists / notExists and any-element predicates", the `<arr>`
    # guard: the path segment(s) reaching the array are bound TWICE (the
    # `jsonb_typeof` probe, then the `then` branch's re-extraction), followed by
    # the `array` type-name literal and the `[]` empty-array fallback.
    fragment, binds = dialect.array_guard("t0", "address", ("phones",))
    assert fragment == (
        "case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? "
        "then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end"
    )
    assert binds == ["phones", "array", "phones", "[]"]


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_array_guard_fragment_multi_segment_path_doubles_every_segment(dialect: Dialect) -> None:
    # A `many` member reached through an intermediate nested value object binds
    # EVERY segment of the path twice, in the same order (m-sql rule 4).
    fragment, binds = dialect.array_guard("t0", "profile", ("shipping", "rates"))
    assert fragment == (
        "case when jsonb_typeof(jsonb_extract_path(t0.profile, ?, ?)) = ? "
        "then jsonb_extract_path(t0.profile, ?, ?) else cast(? as jsonb) end"
    )
    assert binds == ["shipping", "rates", "array", "shipping", "rates", "[]"]


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_array_guard_fragment_top_level_many_needs_no_path_descent(dialect: Dialect) -> None:
    # A `many` value object declared AT THE TOP LEVEL is itself the array — no
    # `jsonb_extract_path` call is needed to reach it, so the guard probes the
    # plain column reference directly and binds only the type-name/fallback pair.
    fragment, binds = dialect.array_guard("t0", "tags", ())
    assert fragment == "case when jsonb_typeof(t0.tags) = ? then t0.tags else cast(? as jsonb) end"
    assert binds == ["array", "[]"]


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_placeholder_translation(dialect: Dialect) -> None:
    assert dialect.to_driver_sql("select t0.id from t where t0.id = ?") == (
        "select t0.id from t where t0.id = %s"
    )


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_from_driver_sql_reverses_placeholder_translation(dialect: Dialect) -> None:
    # `from_driver_sql` is `to_driver_sql`'s reverse (COR-3 Phase 8 increment 5):
    # the conformance engine's materializing-predicate-write capture reports
    # ACTUAL driver SQL it did not itself lower, so it round-trips that text back
    # to canonical `?`-placeholder form before joining it with every other
    # (canonically-lowered) emission.
    canonical = "select t0.id from t where t0.id = ?"
    assert dialect.from_driver_sql(dialect.to_driver_sql(canonical)) == canonical
    assert dialect.from_driver_sql("select t0.id from t where t0.id = %s") == canonical


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_error_classification(dialect: Dialect) -> None:
    assert dialect.classify("23505") == "uniqueViolation"
    assert dialect.classify("40P01") == "deadlock"
    assert dialect.classify("40001") == "deadlock"
    assert dialect.classify("55P03") == "lockWaitTimeout"
    assert dialect.classify("00000") is None


def test_infinity_sentinel_and_lookup() -> None:
    assert INFINITY == "infinity"
    assert dialect_for("postgres") is POSTGRES
    with pytest.raises(ValueError, match="unsupported dialect"):
        dialect_for("mariadb")
