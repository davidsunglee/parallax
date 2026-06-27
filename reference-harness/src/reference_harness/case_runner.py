"""The layered assertion engine (M12 runner sub-part).

Per case, against a freshly-provisioned database selected via the provider seam:

1. **Schema conformance** — descriptor / operation / case validate (done
   statically by :mod:`schema_validate`; re-asserted here for the loaded case).
2. **Triple equivalence** — ``exec(goldenSql[dialect]) == exec(referenceSql) ==
   expectedRows`` (the ``referenceSql`` term only when present).
3. **Normalization determinism** — ``normalize(goldenSql[dialect]) ==
   goldenSql[dialect]`` (per statement, for multi-statement cases).
4. **Serde round-trip** — ``serialize(deserialize(x)) == x`` for BOTH the
   operation encoding AND the model descriptor, in BOTH JSON and YAML.
5. **Round-trip-count consistency** (Phase 3) — for relationship / deep-fetch
   cases the number of golden SQL statements equals the declared ``roundTrips``,
   each level executes (child levels keyed by the parents gathered from the
   previous level), and the assembled object graph equals ``expectedGraph``.

It deliberately **never compiles the operation to SQL** — that is the job of a
real implementation, graded against the golden SQL.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from . import serde
from .case import Case, Entity, Model
from .data_loader import load_model
from .ddl_builder import column_order, ddl_for
from .providers import DatabaseProvider
from .sql_normalize import normalize


class CaseFailure(AssertionError):
    """A compatibility-case assertion failed."""


def _coerce_scalar(value: Any) -> Any:
    """Coerce a DB / expected scalar to a JSON-serializable identity form.

    Used by the deep-fetch KEY-gathering and graph-identity paths, where values
    must stay hashable and JSON-serializable (those columns are integer-domain
    join keys and primary keys). Row *value* comparison does NOT use this — it
    normalizes to an exact :class:`Decimal` via :func:`_to_decimal` so money and
    aggregate values compare exactly, never through ``float``. See
    :func:`_scalars_equal`.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    return value


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _coerce_scalar(value) for key, value in row.items()}


def _to_decimal(value: Any) -> Any:
    """Normalize a numeric to an EXACT ``Decimal``; pass non-numerics through.

    Integers and ``Decimal``\\ s convert losslessly. A ``float`` is converted via
    its shortest round-tripping repr (``Decimal(str(x))``) so a YAML-authored
    ``0.1`` becomes ``Decimal('0.1')`` — matching the DB's exact ``numeric`` —
    rather than ``Decimal(0.1)``, which would inject the binary-float expansion.
    ``bool`` is deliberately NOT treated as numeric, so ``True`` never equals 1.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    return value


def _scalars_equal(left: Any, right: Any, tolerance: Decimal | None) -> bool:
    """Compare two scalars exactly in Decimal space, or within ``tolerance``.

    Numerics compare as exact Decimals (no ``float`` anywhere) so a ``decimal``
    money column matches to the cent and a value's type never depends on whether
    it is whole. When the case declares a ``tolerance`` — for inherently inexact
    results (stddev / variance / repeating-decimal avg) that cannot be authored
    exactly and differ in scale across dialects — numeric comparison becomes
    ``abs(left - right) <= tolerance``. Non-numerics (str / bool / None) use ``==``.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        # bool is not numeric: a boolean equals only a boolean of the same value
        # (so True != 1 and False != 0), never a number that happens to be 0/1.
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    da, db = _to_decimal(left), _to_decimal(right)
    if isinstance(da, Decimal) and isinstance(db, Decimal):
        if tolerance is not None:
            return abs(da - db) <= tolerance
        return da == db
    return left == right


def _row_matches(
    left: dict[str, Any], right: dict[str, Any], tolerance: Decimal | None
) -> bool:
    if left.keys() != right.keys():
        return False
    return all(_scalars_equal(left[key], right[key], tolerance) for key in left)


def _rows_equal(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    tolerance: Decimal | None = None,
) -> bool:
    """Order-insensitive multiset comparison of result rows.

    Tolerance-aware scalar comparison is not hashable, so this is a greedy match:
    each left row must claim a distinct right row. Result sets are tiny, so the
    O(n^2) match is free.
    """
    if len(left) != len(right):
        return False
    remaining = list(right)
    for row in left:
        for index, candidate in enumerate(remaining):
            if _row_matches(row, candidate, tolerance):
                del remaining[index]
                break
        else:
            return False
    return not remaining


def _assert_schema(case: Case) -> None:
    # Layer 1 is enforced statically across the whole tree by schema_validate.
    # Here we assert the minimal structural invariants the runner relies on so a
    # malformed case fails loudly rather than deep in execution.
    if case.is_write_sequence:
        if not case.expected_table_state:
            raise CaseFailure(f"{case.path.name}: write sequence missing expectedTableState")
    elif "operation" not in case.raw:
        raise CaseFailure(f"{case.path.name}: missing operation")
    if not case.model.class_name:
        raise CaseFailure(f"{case.path.name}: model has no class name")


def _assert_normalization(case: Case, dialect: str) -> None:
    for index, statement in enumerate(case.golden_statements(dialect)):
        canonical = normalize(statement, dialect)
        if canonical != statement:
            where = f"goldenSql.{dialect}"
            if len(case.golden_statements(dialect)) > 1:
                where += f"[{index}]"
            raise CaseFailure(
                f"{case.path.name}: {where} is not canonical.\n"
                f"  stored:     {statement!r}\n"
                f"  normalized: {canonical!r}"
            )


def _assert_serde(case: Case) -> None:
    # Layer 4a: operation serde (read cases only; a write-sequence case has no
    # operation). Layer 4b: metamodel (descriptor) serde — always.
    if not case.is_write_sequence:
        serde.assert_roundtrip(case.operation)
    serde.assert_roundtrip(case.model.descriptor)


def _assert_equivalent_encodings(case: Case) -> None:
    """Layer 4c: every declared alternate encoding collapses to ``operation``.

    Dialect-agnostic and database-free: each ``equivalentEncodings`` entry MUST
    canonicalize (via the serde seam) to the same node as the case's canonical
    ``operation``. This pins the precedence/serialization-fidelity contract — a
    prefix and a fluent surface of the same grouped intent denote one node — in
    the fixture itself rather than in bespoke test code.
    """
    if case.is_write_sequence:
        return
    canonical_operation = serde.canonical(case.operation)
    for index, encoding in enumerate(case.equivalent_encodings):
        if serde.canonical(encoding) != canonical_operation:
            raise CaseFailure(
                f"{case.path.name}: equivalentEncodings[{index}] does not "
                f"canonicalize to the case operation.\n"
                f"  encoding (canonical):  {serde.canonical(encoding)!r}\n"
                f"  operation (canonical): {canonical_operation!r}"
            )


def _assert_round_trip_count(case: Case, dialect: str) -> None:
    statements = case.golden_statements(dialect)
    if len(statements) != case.round_trips:
        raise CaseFailure(
            f"{case.path.name}: goldenSql.{dialect} has {len(statements)} "
            f"statement(s) but roundTrips is {case.round_trips}. The statement "
            f"count MUST equal the declared round-trip count."
        )


# --- relationship / deep-fetch resolution -----------------------------------

_JOIN_RE = re.compile(
    r"^\s*this\.(?P<this>[A-Za-z][A-Za-z0-9]*)\s*=\s*"
    r"(?P<entity>[A-Za-z][A-Za-z0-9]*)\.(?P<other>[A-Za-z][A-Za-z0-9]*)\s*$"
)


def _join_endpoints(relationship: dict[str, Any]) -> tuple[str, str]:
    """Return ``(this_attr, related_attr)`` from a ``this.X = Entity.Y`` join."""
    match = _JOIN_RE.match(relationship["join"])
    if not match:
        raise CaseFailure(f"unparseable relationship join: {relationship['join']!r}")
    return match.group("this"), match.group("other")


def _column_of(entity: Entity, attr_name: str) -> str:
    return entity.attribute_by_name(attr_name)["column"]


def _resolve_rel_ref(model: Model, rel_ref: str) -> tuple[Entity, dict[str, Any]]:
    """Resolve ``Class.relationship`` to its owning entity + relationship def."""
    class_name, rel_name = rel_ref.split(".", 1)
    entity = model.entity(class_name)
    return entity, entity.relationship_by_name(rel_name)


def _deepfetch_paths(case: Case) -> list[list[str]]:
    return case.operation["deepFetch"]["paths"]


def _deepfetch_root_operand(case: Case) -> dict[str, Any]:
    return case.operation["deepFetch"]["operand"]


def _is_deep_fetch(case: Case) -> bool:
    return "deepFetch" in case.operation


def _deepfetch_root_entity(case: Case) -> Entity:
    """The entity the deep-fetch root query targets.

    It is the owning class of the first relationship in the first declared path
    (every path starts at the queried entity), so a deep fetch may be rooted at
    any entity in a multi-entity model, not just the descriptor's first one.
    """
    first_rel = _deepfetch_paths(case)[0][0]
    root_class = first_rel.split(".", 1)[0]
    return case.model.entity(root_class)


class _FetchStep:
    """One relationship hop = one golden statement (after the root)."""

    def __init__(
        self,
        rel_ref: str,
        parent_entity: Entity,
        child_entity: Entity,
        parent_attr: str,
        child_attr: str,
        cardinality: str,
    ) -> None:
        self.rel_ref = rel_ref
        self.rel_name = rel_ref.split(".", 1)[1]
        self.parent_entity = parent_entity
        self.child_entity = child_entity
        self.parent_attr = parent_attr
        self.child_attr = child_attr
        self.cardinality = cardinality

    @property
    def to_many(self) -> bool:
        return self.cardinality in ("one-to-many", "many-to-many")


def _fetch_steps(case: Case) -> list[_FetchStep]:
    """Ordered, de-duplicated relationship hops for a deep fetch.

    Each distinct relationship across all paths is exactly one statement (one
    query per relationship level — the N+1-eliminating contract). Paths that
    share a prefix (e.g. ``[Order.items]`` and ``[Order.items, OrderItem.statuses]``)
    therefore fetch ``Order.items`` once, not twice.
    """
    model = case.model
    steps: list[_FetchStep] = []
    seen: set[str] = set()
    for path in _deepfetch_paths(case):
        for rel_ref in path:
            if rel_ref in seen:
                continue
            seen.add(rel_ref)
            parent_entity, relationship = _resolve_rel_ref(model, rel_ref)
            child_entity = model.entity(relationship["relatedEntity"])
            this_attr, other_attr = _join_endpoints(relationship)
            steps.append(
                _FetchStep(
                    rel_ref=rel_ref,
                    parent_entity=parent_entity,
                    child_entity=child_entity,
                    parent_attr=this_attr,
                    child_attr=other_attr,
                    cardinality=relationship["cardinality"],
                )
            )
    return steps


# --- assertions -------------------------------------------------------------


def _query_rows(db: DatabaseProvider, sql: str, binds: list[Any]) -> list[dict[str, Any]]:
    return db.query(sql, binds) if binds else db.query(sql)


def _provision(case: Case, db: DatabaseProvider) -> None:
    db.reset()
    db.apply_ddl(ddl_for(case.model, db.dialect))
    load_model(case.model, db)


def _provision_empty(case: Case, db: DatabaseProvider) -> None:
    """Provision DDL only (no fixture load) for a write-sequence case.

    A write-sequence case constructs its entire milestone history from its own
    ordered DML (the `insert` step is part of the sequence), so it starts from an
    empty schema and is fully self-contained.
    """
    db.reset()
    db.apply_ddl(ddl_for(case.model, db.dialect))


def _assert_flat_equivalence(case: Case, db: DatabaseProvider) -> None:
    dialect = db.dialect
    (golden,) = case.golden_statements(dialect)

    golden_rows = _query_rows(db, golden, case.binds)
    expected = case.expected_rows
    tolerance = case.tolerance

    if not _rows_equal(golden_rows, expected, tolerance):
        raise CaseFailure(
            f"{case.path.name}: goldenSql.{dialect} rows != expectedRows.\n"
            f"  golden:   {golden_rows!r}\n"
            f"  expected: {expected!r}"
        )

    if case.reference_sql is not None:
        reference_rows = db.query(case.reference_sql)
        if not _rows_equal(reference_rows, expected, tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql rows != expectedRows.\n"
                f"  reference: {reference_rows!r}\n"
                f"  expected:  {expected!r}"
            )


def _binds_for_statement(case: Case, index: int) -> list[Any]:
    """The authored binds for statement *index* of a multi-statement case.

    ``binds`` for a multi-statement case is a list-of-lists (one per statement).
    For a single flat list (single-statement case) this is never called.
    """
    raw = case.binds
    if raw and isinstance(raw[0], list):
        return raw[index] if index < len(raw) else []
    return raw if index == 0 else []


def _assert_deep_fetch(case: Case, db: DatabaseProvider) -> None:
    """Execute each level, assemble the object graph, compare to expectedGraph.

    The contract proven here is N+1 elimination: the root plus one statement per
    relationship level (never one-per-parent). Each child level is executed once,
    keyed by the DISTINCT parent keys gathered from the previous level, and the
    children are fanned back out in memory.
    """
    dialect = db.dialect
    statements = case.golden_statements(dialect)
    steps = _fetch_steps(case)

    if len(statements) != 1 + len(steps):
        raise CaseFailure(
            f"{case.path.name}: goldenSql.{dialect} has {len(statements)} "
            f"statement(s) but the deep fetch needs {1 + len(steps)} "
            f"(1 root + {len(steps)} relationship level(s))."
        )

    root_entity = _deepfetch_root_entity(case)

    # Level 0: the root query.
    root_binds = _binds_for_statement(case, 0)
    root_rows = _query_rows(db, statements[0], root_binds)

    # rows_by_entity[entity_name] -> list of result-rows fetched for that entity.
    rows_by_entity: dict[str, list[dict[str, Any]]] = {root_entity.name: root_rows}

    # Execute each relationship level once, keyed by gathered parent keys.
    children_by_step: dict[str, dict[Any, list[dict[str, Any]]]] = {}
    for index, step in enumerate(steps, start=1):
        parents = rows_by_entity.get(step.parent_entity.name, [])
        parent_col = _column_of(step.parent_entity, step.parent_attr)
        parent_keys = sorted(
            {_coerce_scalar(p[parent_col]) for p in parents if p.get(parent_col) is not None}
        )

        authored = [_coerce_scalar(b) for b in _binds_for_statement(case, index)]
        if sorted(authored) != parent_keys:
            raise CaseFailure(
                f"{case.path.name}: goldenSql.{dialect} level {index} "
                f"({step.rel_ref}) authored binds {authored!r} != gathered parent "
                f"keys {parent_keys!r}. The child level MUST be keyed by exactly "
                f"the parents from the previous level (the N+1-eliminating IN list)."
            )

        child_rows = _query_rows(db, statements[index], parent_keys) if parent_keys else []
        rows_by_entity[step.child_entity.name] = child_rows

        child_col = _column_of(step.child_entity, step.child_attr)
        bucket: dict[Any, list[dict[str, Any]]] = {}
        for row in child_rows:
            bucket.setdefault(_coerce_scalar(row[child_col]), []).append(row)
        children_by_step[step.rel_ref] = bucket

    # Assemble the graph: attach each child set under its relationship name on
    # the parent rows, following the declared paths.
    assembled = _assemble_graph(case, steps, rows_by_entity, children_by_step)

    expected = case.expected_graph or {}
    if not _graphs_equal(assembled, expected):
        raise CaseFailure(
            f"{case.path.name}: assembled graph != expectedGraph.\n"
            f"  assembled: {assembled!r}\n"
            f"  expected:  {expected!r}"
        )

    # referenceSql (a single naive statement) is the independent oracle for the
    # ROOT row set of the deep fetch.
    if case.reference_sql is not None:
        reference_rows = db.query(case.reference_sql)
        root_projection = [_project_like(r, root_rows) for r in reference_rows]
        if not _rows_equal(root_projection, root_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql root rows != goldenSql root rows.\n"
                f"  reference: {reference_rows!r}\n"
                f"  golden:    {root_rows!r}"
            )


def _project_like(row: dict[str, Any], template_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep only the columns the golden root projection carries (oracle compare)."""
    if not template_rows:
        return row
    keep = set(template_rows[0])
    return {k: v for k, v in row.items() if k in keep}


def _assemble_graph(
    case: Case,
    steps: list[_FetchStep],
    rows_by_entity: dict[str, list[dict[str, Any]]],
    children_by_step: dict[str, dict[Any, list[dict[str, Any]]]],
) -> dict[str, list[dict[str, Any]]]:
    """Build the root-keyed object graph following the deep-fetch paths.

    Each path is walked hop by hop; at each hop the child rows for a given parent
    are attached under the relationship name (a list for to-many, a single object
    or ``None`` for to-one).
    """
    root_entity = _deepfetch_root_entity(case)
    step_by_ref = {step.rel_ref: step for step in steps}

    # Build per-entity row registries keyed by primary key so a shared hop
    # (e.g. Order.items consumed by two paths) reuses the same child objects;
    # nodes are keyed by (entity, pk) identity.
    def pk_attr(entity: Entity) -> str:
        for attribute in entity.attributes:
            if attribute.get("primaryKey"):
                return attribute["name"]
        return entity.attributes[0]["name"]

    # node registry: (entity_name, pk_value) -> assembled node (dict)
    registry: dict[tuple[str, Any], dict[str, Any]] = {}

    def node_for(entity: Entity, raw_row: dict[str, Any]) -> dict[str, Any]:
        pk_col = _column_of(entity, pk_attr(entity))
        key = (entity.name, _coerce_scalar(raw_row[pk_col]))
        if key not in registry:
            registry[key] = _normalize_row(raw_row)
        return registry[key]

    root_nodes = [node_for(root_entity, r) for r in rows_by_entity[root_entity.name]]

    for path in _deepfetch_paths(case):
        parent_entities = [root_entity]
        parent_nodes_levels: list[list[dict[str, Any]]] = [root_nodes]
        for rel_ref in path:
            step = step_by_ref[rel_ref]
            parent_entity = parent_entities[-1]
            parent_nodes = parent_nodes_levels[-1]
            parent_col = _column_of(parent_entity, step.parent_attr)
            bucket = children_by_step[rel_ref]

            next_nodes: list[dict[str, Any]] = []
            for parent_node in parent_nodes:
                # parent_node holds normalized columns; the join key is parent_col.
                parent_key = parent_node.get(parent_col)
                matched = bucket.get(parent_key, [])
                child_nodes = [node_for(step.child_entity, c) for c in matched]
                if step.to_many:
                    parent_node[step.rel_name] = child_nodes
                else:
                    parent_node[step.rel_name] = child_nodes[0] if child_nodes else None
                next_nodes.extend(child_nodes)
            parent_entities.append(step.child_entity)
            parent_nodes_levels.append(next_nodes)

    return {root_entity.name: root_nodes}


def _graphs_equal(
    left: dict[str, list[dict[str, Any]]],
    right: dict[str, list[dict[str, Any]]],
) -> bool:
    return serde.canonical(_sort_graph(left)) == serde.canonical(_sort_graph(right))


def _sort_graph(graph: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Recursively normalize a graph for order-insensitive comparison.

    Lists of objects are sorted by a stable serialization of their contents, so
    a to-many relationship's child order does not affect equality.
    """

    def norm(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: norm(value[k]) for k in value}
        if isinstance(value, list):
            normed = [norm(v) for v in value]
            return sorted(normed, key=lambda v: serde.serialize(serde.canonical(v)))
        return _coerce_scalar(value)

    return {key: norm(value) for key, value in graph.items()}


# --- write sequences (Phase 5, M7) ------------------------------------------


def _assert_write_step_count(case: Case, dialect: str) -> None:
    """The DML statement count MUST equal the sum of the steps' declared counts.

    Each ``writeSequence`` step declares how many golden DML statements it emits
    (default 1); the total over the sequence is the round-trip count, which MUST
    equal the number of goldenSql statements for the dialect (and ``roundTrips``).
    """
    statements = case.golden_statements(dialect)
    step_total = sum(step.get("statements", 1) for step in case.write_sequence)
    if len(statements) != step_total:
        raise CaseFailure(
            f"{case.path.name}: goldenSql.{dialect} has {len(statements)} DML "
            f"statement(s) but the writeSequence declares {step_total} "
            f"(sum of per-step statement counts). They MUST be equal."
        )
    if len(statements) != case.round_trips:
        raise CaseFailure(
            f"{case.path.name}: goldenSql.{dialect} has {len(statements)} DML "
            f"statement(s) but roundTrips is {case.round_trips}."
        )


def _read_table(db: DatabaseProvider, entity: Entity) -> list[dict[str, Any]]:
    """Read the full state of *entity*'s table, projecting every column by name."""
    columns = list(column_order(entity))
    projection = ", ".join(f"t0.{column}" for column in columns)
    return db.query(f"select {projection} from {entity.table} t0")


def _assert_write_sequence(case: Case, db: DatabaseProvider) -> None:
    """Apply the ordered DML golden SQL, then assert the resulting table state.

    This is the observable form of the milestone-chaining write contract (M7):
    rather than introspecting the implementation, we APPLY the documented golden
    DML in order and assert the rows it leaves behind — including the current-row
    state where the open bound ``to`` equals native ``infinity``.
    """
    dialect = db.dialect
    statements = case.golden_statements(dialect)

    for index, statement in enumerate(statements):
        binds = _binds_for_statement(case, index)
        db.execute(statement, binds)

    expected = case.expected_table_state
    entity_by_table = {entity.table: entity for entity in case.model.entities}
    for table, expected_rows in expected.items():
        if table not in entity_by_table:
            raise CaseFailure(
                f"{case.path.name}: expectedTableState names table {table!r} "
                f"which the model does not declare."
            )
        actual = _read_table(db, entity_by_table[table])
        if not _rows_equal(actual, expected_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: table {table!r} state after the write "
                f"sequence != expectedTableState.\n"
                f"  actual:   {actual!r}\n"
                f"  expected: {expected_rows!r}"
            )


# --- entry point ------------------------------------------------------------


def run_case(case: Case, db: DatabaseProvider) -> None:
    """Run all available assertion layers for *case* against *db*."""
    dialect = db.dialect
    if dialect not in case.golden_sql:
        # No golden SQL for this dialect: nothing to execute against it. The
        # serde + (dialect-agnostic) checks still run so coverage is not skipped.
        _assert_schema(case)
        _assert_serde(case)
        _assert_equivalent_encodings(case)  # layer 4c (dialect-agnostic)
        return

    _assert_schema(case)
    _assert_normalization(case, dialect)  # layer 3
    _assert_serde(case)  # layer 4
    _assert_equivalent_encodings(case)  # layer 4c

    if case.is_write_sequence:
        _assert_write_step_count(case, dialect)  # layer 5 (count)
        _provision_empty(case, db)
        _assert_write_sequence(case, db)  # apply DML, assert table state
        return

    _assert_round_trip_count(case, dialect)  # layer 5 (count)
    _provision(case, db)
    if _is_deep_fetch(case):
        _assert_deep_fetch(case, db)  # layer 2 + 5 (graph)
    else:
        _assert_flat_equivalence(case, db)  # layer 2
