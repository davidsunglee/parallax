"""Docker-free dialect contract suite (m-dialect).

Table-driven over the concrete dialects (one row today: postgres), covering the
`m-dialect` decision catalog: identifier quoting, NULL ordering per direction,
row-limit rendering, optimizer fencing, shared-read-lock application, neutral-scalar column-type
mapping (parametric decimals, bounded strings), the bytes projection shape and
its projection-introduced bind, the structured-document extraction / typed-cast
forms, canonical `?` -> `%s` placeholder translation, the infinity sentinel, the
native error-code classification predicates, and the DDL primitives a schema
generator composes statements out of. Pure strategy, no driver I/O.

Dual-marked ``unit`` so the pure strategy is covered by the branch-coverage gate
and runs in the ``dbfree`` class.
"""

from __future__ import annotations

import pytest

from parallax.core.base import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT32,
    FLOAT64,
    INT32,
    INT64,
    JSON,
    SQL_NULL,
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    Decimal,
    PresentDocument,
)
from parallax.core.dialect import (
    DIALECT_CATALOG,
    INFINITY,
    POSTGRES,
    ColumnDdl,
    Dialect,
    DocumentLeafAssignment,
    DocumentValueAssignment,
    IndexColumnDdl,
    PhysicalIndexName,
    Unsupported,
    dialect_for,
)

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
def test_null_ordering_per_direction_and_placement(dialect: Dialect) -> None:
    assert dialect.null_order("t0.c", "asc", "last") == "t0.c asc"
    assert dialect.null_order("t0.c", "desc", "last") == "t0.c desc nulls last"
    assert dialect.null_order("t0.c", "asc", "first") == "t0.c asc nulls first"
    assert dialect.null_order("t0.c", "desc", "first") == "t0.c desc"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_row_limit_and_read_lock(dialect: Dialect) -> None:
    assert dialect.limit_clause() == "limit ?"
    assert dialect.optimizer_fence() == ("offset 0", [])
    assert dialect.read_lock_suffix("t0") == "for share of t0"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_column_type_mapping(dialect: Dialect) -> None:
    assert dialect.column_type(INT64, None) == "bigint"
    assert dialect.column_type(INT32, None) == "integer"
    assert dialect.column_type(BOOLEAN, None) == "boolean"
    assert dialect.column_type(TIMESTAMP, None) == "timestamptz"
    assert dialect.column_type(JSON, None) == "jsonb"
    assert dialect.column_type(UUID, None) == "uuid"
    assert dialect.column_type(BYTES, None) == "bytea"
    assert dialect.column_type(FLOAT32, None) == "real"
    assert dialect.column_type(FLOAT64, None) == "double precision"
    assert dialect.column_type(DATE, None) == "date"
    assert dialect.column_type(TIME, None) == "time"
    assert dialect.column_type(STRING, 64) == "varchar(64)"
    assert dialect.column_type(STRING, None) == "text"
    assert dialect.column_type(Decimal(18, 2), None) == "numeric(18, 2)"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_null_cast_spells_a_decimal_placeholder_apart_from_its_ddl_type(
    dialect: Dialect,
) -> None:
    # The union-all placeholder cast is a decision of its own: a decimal casts to
    # `decimal(p, s)` even though its DDL column type is `numeric(p, s)`, while
    # every other type reuses the DDL mapping (a bounded string still narrows to
    # `varchar(n)`).
    assert dialect.null_cast(Decimal(18, 2), None) == "decimal(18, 2)"
    assert dialect.null_cast(STRING, 64) == "varchar(64)"
    assert dialect.null_cast(INT32, None) == "integer"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_bytes_projection_shape(dialect: Dialect) -> None:
    expr, binds = dialect.project("t0", "payload", BYTES)
    assert expr == "encode(t0.payload, ?) payload_hex"
    assert binds == ["hex"]
    plain_expr, plain_binds = dialect.project("t0", "name", STRING)
    assert plain_expr == "t0.name"
    assert plain_binds == []


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_document_read_parsing_uses_the_boolean_discriminator_first(dialect: Dialect) -> None:
    assert dialect.parse_document_read(False, object()) is SQL_NULL
    assert dialect.parse_document_read(True, None) == PresentDocument(None)
    with pytest.raises(ValueError, match="must be a SQL boolean"):
        dialect.parse_document_read(1, None)
    with pytest.raises(ValueError, match="portable JSON value"):
        dialect.parse_document_read(True, object())


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_nested_extraction_and_cast(dialect: Dialect) -> None:
    extract, binds = dialect.nested_extract("t0.address", ("geo", "country"))
    assert extract == "jsonb_extract_path_text(t0.address, ?, ?)"
    assert binds == ["geo", "country"]
    # The document reference is rendered by the CALLER, so the same helper serves a
    # write's unaliased bare-column form (m-sql rule 1) with no second code path.
    bare, bare_binds = dialect.nested_extract("address", ("geo", "country"))
    assert bare == "jsonb_extract_path_text(address, ?, ?)"
    assert bare_binds == ["geo", "country"]
    assert dialect.nested_cast("EXT", STRING) == "EXT"  # text compares directly
    assert dialect.nested_cast("EXT", INT64) == "cast(EXT as bigint)"
    assert dialect.nested_cast("EXT", FLOAT64) == "cast(EXT as double precision)"
    assert dialect.nested_cast("EXT", Decimal(18, 2)) == "cast(EXT as decimal(18, 2))"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_array_guard_fragment_binds_the_path_twice(dialect: Dialect) -> None:
    # m-sql "To-many — exists / notExists and any-element predicates", the `<arr>`
    # guard: the path segment(s) reaching the array are bound TWICE (the
    # `jsonb_typeof` probe, then the `then` branch's re-extraction), followed by
    # the `array` type-name literal and the `[]` empty-array fallback.
    fragment, binds = dialect.array_guard("t0.address", ("phones",))
    assert fragment == (
        "case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? "
        "then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end"
    )
    assert binds == ["phones", "array", "phones", "[]"]


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_array_guard_fragment_multi_segment_path_doubles_every_segment(dialect: Dialect) -> None:
    # A `many` member reached through an intermediate nested value object binds
    # EVERY segment of the path twice, in the same order (m-sql rule 4).
    fragment, binds = dialect.array_guard("t0.profile", ("shipping", "rates"))
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
    fragment, binds = dialect.array_guard("t0.tags", ())
    assert fragment == "case when jsonb_typeof(t0.tags) = ? then t0.tags else cast(? as jsonb) end"
    assert binds == ["array", "[]"]


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_document_mutation_composes_one_assignment_through_the_value_expression(
    dialect: Dialect,
) -> None:
    # m-dialect *Document mutation-expression form*: the value hole is a
    # per-dialect EXPRESSION, not a bare `?`. A bare parameter there resolves to
    # `jsonb_set`'s declared `jsonb` and rejects every scalar bind, so the cast
    # is what makes one authored bind form work at all.
    sql, binds = dialect.document_mutation(
        "payload", [DocumentLeafAssignment(("displayName",), "Solveig")]
    )
    assert sql == "jsonb_set(payload, ?, cast(? as jsonb))"
    assert binds == ["{displayName}", '"Solveig"']


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_document_mutation_nests_n_assignments_innermost_first(dialect: Dialect) -> None:
    # Each call's target is the previous call's result, so the INNERMOST call is
    # the first assignment and the binds read path, value, path, value in
    # assignment order — which is what keeps canonical logical placement order
    # observable (m-storage-layout / m-sql).
    sql, binds = dialect.document_mutation(
        "t0.payload",
        [
            DocumentLeafAssignment(("displayName",), "Solveig"),
            DocumentLeafAssignment(("score",), 7),
        ],
    )
    assert sql == "jsonb_set(jsonb_set(t0.payload, ?, cast(? as jsonb)), ?, cast(? as jsonb))"
    assert binds == ["{displayName}", '"Solveig"', "{score}", "7"]


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_document_mutation_carries_a_composite_as_the_document_and_a_scalar_as_json_text(
    dialect: Dialect,
) -> None:
    # m-case-format draws the boundary: a composite rides as the portable
    # document the provider adapts, so no key order or separator convention
    # reaches a golden; a JSON scalar — which no structural authoring form
    # distinguishes from an ordinary scalar bind — rides as the JSON text both
    # dialects' value expressions parse, and has neither to protect.
    _, binds = dialect.document_mutation(
        "payload",
        [
            DocumentValueAssignment(("address",), {"city": "Oslo"}),
            DocumentValueAssignment(("tags",), [{"label": "x"}]),
            DocumentLeafAssignment(("score",), None),
            DocumentLeafAssignment(("active",), True),
        ],
    )
    assert binds[1] == {"city": "Oslo"}
    assert binds[3] == [{"label": "x"}]
    assert binds[5] == "null"
    assert binds[7] == "true"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_an_occurrence_assignment_is_one_call_over_its_own_path(dialect: Dialect) -> None:
    # The seam renders both nodes of the algebra identically, because an assigned
    # occurrence hands it one already-encoded document for one absolute path. There
    # is no type test and no write-back: only the FINAL path segment has to be
    # created, and a top-level occurrence's parent is the document root itself.
    sql, binds = dialect.document_mutation(
        "payload",
        [
            DocumentValueAssignment(("manifest",), {"origin": {"city": "Oslo"}}),
            DocumentValueAssignment(("berths",), None),
        ],
    )
    assert "jsonb_typeof" not in sql
    assert sql == ("jsonb_set(jsonb_set(payload, ?, cast(? as jsonb)), ?, cast(? as jsonb))")
    assert binds == ["{manifest}", {"origin": {"city": "Oslo"}}, "{berths}", "null"]


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_document_path_is_the_dialects_own_mutation_path_spelling(dialect: Dialect) -> None:
    # Divergent from the extraction path binds above on purpose: `jsonb_set`
    # takes ONE text-array path where `jsonb_extract_path_text` takes one bind
    # per segment.
    assert dialect.document_path(("displayName",)) == "{displayName}"
    assert dialect.document_path(("address", "city")) == "{address,city}"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_structural_document_equality(dialect: Dialect) -> None:
    # Postgres `jsonb` normalizes on storage, so `=` is already structural;
    # MariaDB's `json` is a text alias and needs `json_equals`. Obtaining the
    # comparison through the seam is what stops one assertion meaning two things.
    assert dialect.document_equals("t0.payload", "?") == "t0.payload = ?"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_placeholder_translation(dialect: Dialect) -> None:
    assert dialect.to_driver_sql("select t0.id from t where t0.id = ?") == (
        "select t0.id from t where t0.id = %s"
    )


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_a_literal_percent_is_escaped_for_the_driver_parameter_style(dialect: Dialect) -> None:
    # A physical name is any non-empty string, so `rate%` is an admissible column
    # and renders as a quoted identifier. The `%s` parameter style is applied to
    # the statement as flat text, so a bare `%` there is a malformed placeholder
    # the driver refuses outright and a name ending `%s` is a bind that silently
    # eats one — which is why the escape reaches inside quoted runs the
    # placeholder translation deliberately leaves alone.
    assert dialect.to_driver_sql('select t0."rate%" from t t0 where t0.id = ?') == (
        'select t0."rate%%" from t t0 where t0.id = %s'
    )
    assert dialect.to_driver_sql('select t0."rate%s" from t t0') == (
        'select t0."rate%%s" from t t0'
    )


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_from_driver_sql_reverses_percent_escaping(dialect: Dialect) -> None:
    # Undoubling is the inverse of the escape above. It shares one left-to-right
    # pass with the placeholder recovery because the two spellings overlap from
    # both sides: the `%%` a `%s` was just recovered out of must not be read as
    # an escape, and an escaped `%` standing before an `s` must not be read
    # tail-first as a bind.
    canonical = 'update "t%s" t0 set "rate%" = ? where t0.id = ?'
    assert dialect.from_driver_sql(dialect.to_driver_sql(canonical)) == canonical
    modulo = "select t0.rate%s from t t0 where t0.id = ?"
    assert dialect.from_driver_sql(dialect.to_driver_sql(modulo)) == modulo


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_from_driver_sql_reverses_placeholder_translation(dialect: Dialect) -> None:
    # `from_driver_sql` is `to_driver_sql`'s reverse:
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


# --- DDL primitives -----------------------------------------------------------


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_identifier_byte_limit_is_declared(dialect: Dialect) -> None:
    # Only a DERIVED identifier has to fit a budget, so the limit is a fact about
    # the database rather than a rule applied to authored names here.
    assert dialect.max_identifier_bytes == 63


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_create_table_renders_columns_then_the_inline_key(dialect: Dialect) -> None:
    statement = dialect.create_table(
        "widget",
        [ColumnDdl("id", "bigint", False), ColumnDdl("label", "varchar(8)", True)],
        ["id"],
    )
    assert (
        statement == "create table widget (id bigint not null, label varchar(8), primary key (id))"
    )


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_create_table_of_a_keyless_model_emits_no_key_clause(dialect: Dialect) -> None:
    statement = dialect.create_table("widget", [ColumnDdl("label", "varchar(8)", True)], [])
    assert statement == "create table widget (label varchar(8))"


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_add_column_carries_the_same_column_clause(dialect: Dialect) -> None:
    assert (
        dialect.add_column("widget", ColumnDdl("label", "varchar(8)", False))
        == "alter table widget add column label varchar(8) not null"
    )


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_expand_column_spells_each_widening_as_its_own_action(dialect: Dialect) -> None:
    # Postgres factors a type change and a relaxed `not null` into two actions of
    # one statement, which is why the primitive receives the whole change rather
    # than one clause at a time.
    narrower = ColumnDdl("label", "varchar(8)", False)
    assert dialect.expand_column("widget", narrower, ColumnDdl("label", "text", False)) == (
        "alter table widget alter column label type text"
    )
    assert dialect.expand_column("widget", narrower, ColumnDdl("label", "varchar(8)", True)) == (
        "alter table widget alter column label drop not null"
    )
    assert dialect.expand_column("widget", narrower, ColumnDdl("label", "text", True)) == (
        "alter table widget alter column label type text, alter column label drop not null"
    )


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_create_index_spells_uniqueness_and_component_order(dialect: Dialect) -> None:
    name = PhysicalIndexName("pxi_widget_label_0")
    components = [
        IndexColumnDdl("label", STRING, 8),
        IndexColumnDdl("id", INT64, None),
    ]
    assert dialect.create_index("widget", name, components, unique=False) == (
        "create index pxi_widget_label_0 on widget (label, id)"
    )
    assert dialect.create_index("widget", name, components, unique=True) == (
        "create unique index pxi_widget_label_0 on widget (label, id)"
    )


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_postgres_indexes_an_unbounded_string(dialect: Dialect) -> None:
    # The refusal arm exists for a dialect that needs a key length; Postgres has
    # no such requirement, so it answers with a statement for every component.
    statement = dialect.create_index(
        "widget",
        PhysicalIndexName("pxi_widget_note_0"),
        [IndexColumnDdl("note", STRING, None)],
        unique=False,
    )
    assert not isinstance(statement, Unsupported)


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_drop_index_names_the_index_alone(dialect: Dialect) -> None:
    assert dialect.drop_index("widget", PhysicalIndexName("pxi_widget_label_0")) == (
        "drop index pxi_widget_label_0"
    )


@pytest.mark.parametrize("dialect", DIALECTS, ids=IDS)
def test_ddl_identifiers_are_quoted_by_the_same_rule_as_every_other(dialect: Dialect) -> None:
    # A DDL primitive receives already-quoted table and column strings, so the one
    # identifier it quotes itself is the Index name it is handed as a value.
    assert (
        dialect.create_index(
            "widget", PhysicalIndexName("order"), [IndexColumnDdl("label", STRING, 8)], unique=False
        )
        == 'create index "order" on widget (label)'
    )


def test_a_physical_index_name_is_a_nonempty_identifier() -> None:
    # The value validates nothing else: a name read back off a driver diagnostic
    # is as legitimate as a generated one, and the byte limit is the generating
    # rule's concern rather than this value's.
    assert PhysicalIndexName("widget_pkey").value == "widget_pkey"
    with pytest.raises(ValueError, match="nonempty identifier"):
        PhysicalIndexName("")


def test_the_supported_dialect_catalog_is_the_specification_s() -> None:
    # The catalog names every Dialect the specification supports, whether or not
    # this implementation ships a strategy for it, so a consumer enumerating it
    # reports the gap rather than narrowing the matrix to what it happens to have.
    assert DIALECT_CATALOG == ("postgres", "mariadb")
    with pytest.raises(ValueError, match="unsupported dialect"):
        dialect_for("mariadb")
