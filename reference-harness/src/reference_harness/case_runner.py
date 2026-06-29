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

import functools
import re
from decimal import Decimal
from typing import Any

from . import serde
from .case import Case, Entity, Model
from .data_loader import load_model
from .ddl_builder import column_order, ddl_for, quote_identifier
from .providers import DatabaseProvider
from .sql_normalize import normalize


class CaseFailure(AssertionError):
    """A compatibility-case assertion failed."""


def _coerce_identity_key(value: Any) -> Any:
    """Coerce a DB / expected scalar to an exact hashable identity-key form.

    Used only by deep-fetch key gathering, bucket lookup, and node identity.
    Projected graph values must keep their original types so graph equality can
    compare numerics exactly via :func:`_scalars_equal`.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else value
    if isinstance(value, float):
        return Decimal(str(value))
    return value


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


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
    elif case.is_scenario:
        if not case.scenario:
            raise CaseFailure(f"{case.path.name}: scenario case has no steps")
    elif case.is_conflict:
        if case.expected_affected_rows is None and not case.attempts:
            raise CaseFailure(
                f"{case.path.name}: conflict case missing expectedAffectedRows / attempts"
            )
    elif case.is_coherence:
        if len(case.coherence) < 2:
            raise CaseFailure(
                f"{case.path.name}: coherence case needs at least a write and a "
                f"re-fetch step"
            )
        if not any(step.get("observeRows") is not None for step in case.coherence):
            raise CaseFailure(
                f"{case.path.name}: coherence case asserts nothing — at least the "
                f"final re-fetch MUST declare observeRows"
            )
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
    # Layer 4a: operation serde. A read case has one top-level operation; a
    # scenario case has one operation per step (under `find`); a write-sequence
    # case and a conflict case (M10) have none. Layer 4b: metamodel (descriptor)
    # serde — always.
    if case.is_scenario:
        for step in case.scenario:
            # Read steps carry an operation under `find`; write steps carry none.
            if "find" in step:
                serde.assert_roundtrip(step["find"])
    elif case.is_coherence:
        # A coherence case's read steps carry an operation under `find`; write
        # steps carry none. Round-trip each present operation through the serde.
        for step in case.coherence:
            if "find" in step:
                serde.assert_roundtrip(step["find"])
    elif not case.is_write_sequence and not case.is_conflict:
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
    if case.is_write_sequence or case.is_scenario or case.is_conflict or case.is_coherence:
        # A write-sequence and a conflict case have no operation; a scenario and a
        # coherence case carry their operations per step. Equivalent-encodings is a
        # single-operation check.
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
        order_by: list[dict[str, Any]] | None = None,
    ) -> None:
        self.rel_ref = rel_ref
        self.rel_name = rel_ref.split(".", 1)[1]
        self.parent_entity = parent_entity
        self.child_entity = child_entity
        self.parent_attr = parent_attr
        self.child_attr = child_attr
        self.cardinality = cardinality
        self.order_by = order_by or []

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
                    order_by=relationship.get("orderBy"),
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
    empty schema and is fully self-contained — UNLESS it sets ``loadFixtures``
    (the M9 detached-update merge-back case), in which case the model's fixtures
    are loaded first so the merge-back can mutate a pre-existing persisted row.
    """
    db.reset()
    db.apply_ddl(ddl_for(case.model, db.dialect))
    if case.load_fixtures:
        load_model(case.model, db)


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


def _sorted_by_order_keys(
    rows: list[dict[str, Any]],
    sort_spec: list[tuple[str, bool]],
) -> list[dict[str, Any]]:
    """Return *rows* sorted by *sort_spec* — a list of ``(column, descending)``
    pairs evaluated left to right. Stable: rows tied on every key keep input order.
    NULL values sort LAST on every key, regardless of ``asc``/``desc`` (M4 policy).
    """

    def compare(row_a: dict[str, Any], row_b: dict[str, Any]) -> int:
        for column, descending in sort_spec:
            left, right = row_a[column], row_b[column]
            if left == right:
                continue
            # NULLs sort last on every key, regardless of asc/desc (M4 policy).
            if left is None:
                return 1
            if right is None:
                return -1
            ordered = -1 if left < right else 1
            return -ordered if descending else ordered
        return 0

    return sorted(rows, key=functools.cmp_to_key(compare))


def _assert_child_ordering(
    case_name: str,
    steps: list[_FetchStep],
    children_by_step: dict[str, dict[Any, list[dict[str, Any]]]],
) -> None:
    """Assert each ordered to-many level returned its children in the declared order.

    A to-many relationship that declares ``orderBy`` requires the per-level child
    query to emit ``ORDER BY`` over the declared keys (M4), so the rows the DB
    returned — preserved in SQL order inside each parent's bucket — must already
    equal those rows sorted by the declared keys/directions. The harness derives
    the expected order from the model (an independent oracle) rather than trusting
    the authored ``expectedGraph`` order. A relationship with no ``orderBy`` is
    skipped (its order is unspecified). NULL values sort LAST on every key,
    regardless of ``asc``/``desc`` (the canonical M4 policy); two NULLs are equal
    and fall through to the next key. Residual ties beyond the declared keys keep
    their DB order (the sort is stable), which the contract permits. Every
    declared ``orderBy`` key MUST be present in the child query's projection; a
    key absent from the returned rows raises a clean ``CaseFailure`` (the order
    cannot be verified without the key).
    """
    for step in steps:
        if not step.to_many or not step.order_by:
            continue
        sort_spec = [
            (
                _column_of(step.child_entity, key["attr"]),
                key.get("direction", "asc") == "desc",
            )
            for key in step.order_by
        ]
        bucket = children_by_step.get(step.rel_ref, {})
        for parent_key, rows in bucket.items():
            if not rows:
                continue
            missing = [column for column, _ in sort_spec if column not in rows[0]]
            if missing:
                raise CaseFailure(
                    f"{case_name}: {step.rel_ref} orderBy column(s) {missing!r} are "
                    f"not in the child query's projection, so the order cannot be "
                    f"verified; project them in the child SELECT."
                )
            expected = _sorted_by_order_keys(rows, sort_spec)
            if rows != expected:
                cols = [column for column, _ in sort_spec]
                got = [[row[c] for c in cols] for row in rows]
                want = [[row[c] for c in cols] for row in expected]
                raise CaseFailure(
                    f"{case_name}: {step.rel_ref} children for parent "
                    f"{parent_key!r} are not in declared orderBy order "
                    f"(keys {cols!r}). got {got!r}, expected {want!r}."
                )


def _assert_deep_fetch(case: Case, db: DatabaseProvider) -> None:
    """Execute each level, assemble the object graph, compare to expectedGraph.

    The contract proven here is N+1 elimination: the root plus at most one
    statement per relationship level (never one-per-parent). A child level is
    executed only when the previous level produces parent keys; an empty parent
    key set elides that child SQL entirely. Executed child levels are keyed by
    the DISTINCT parent keys gathered from the previous level, and the children
    are fanned back out in memory.
    """
    dialect = db.dialect
    statements = case.golden_statements(dialect)
    steps = _fetch_steps(case)

    root_entity = _deepfetch_root_entity(case)

    # Level 0: the root query.
    root_binds = _binds_for_statement(case, 0)
    root_rows = _query_rows(db, statements[0], root_binds)

    # rows_by_entity[entity_name] -> list of result-rows fetched for that entity.
    rows_by_entity: dict[str, list[dict[str, Any]]] = {root_entity.name: root_rows}

    # Execute each relationship level once, keyed by gathered parent keys.
    children_by_step: dict[str, dict[Any, list[dict[str, Any]]]] = {}
    statement_index = 1
    for step in steps:
        parents = rows_by_entity.get(step.parent_entity.name, [])
        parent_col = _column_of(step.parent_entity, step.parent_attr)
        parent_keys = sorted(
            {
                _coerce_identity_key(p[parent_col])
                for p in parents
                if p.get(parent_col) is not None
            }
        )

        if not parent_keys:
            rows_by_entity[step.child_entity.name] = []
            children_by_step[step.rel_ref] = {}
            continue

        if statement_index >= len(statements):
            raise CaseFailure(
                f"{case.path.name}: goldenSql.{dialect} has no child statement "
                f"for {step.rel_ref}, but the previous level gathered parent "
                f"keys {parent_keys!r}."
            )

        authored = [
            _coerce_identity_key(b)
            for b in _binds_for_statement(case, statement_index)
        ]
        if sorted(authored) != parent_keys:
            raise CaseFailure(
                f"{case.path.name}: goldenSql.{dialect} level {statement_index} "
                f"({step.rel_ref}) authored binds {authored!r} != gathered parent "
                f"keys {parent_keys!r}. The child level MUST be keyed by exactly "
                f"the parents from the previous level (the N+1-eliminating IN list)."
            )

        child_rows = _query_rows(db, statements[statement_index], parent_keys)
        rows_by_entity[step.child_entity.name] = child_rows

        child_col = _column_of(step.child_entity, step.child_attr)
        bucket: dict[Any, list[dict[str, Any]]] = {}
        for row in child_rows:
            bucket.setdefault(_coerce_identity_key(row[child_col]), []).append(row)
        children_by_step[step.rel_ref] = bucket
        statement_index += 1

    _assert_child_ordering(case.path.name, steps, children_by_step)

    if statement_index != len(statements):
        raise CaseFailure(
            f"{case.path.name}: goldenSql.{dialect} lists "
            f"{len(statements) - statement_index} unused deep-fetch child "
            f"statement(s). Child SQL MUST be omitted after a level gathers no "
            f"parent keys."
        )

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
        key = (entity.name, _coerce_identity_key(raw_row[pk_col]))
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
                parent_key = _coerce_identity_key(parent_node.get(parent_col))
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
    """Order-insensitive structural equality for assembled deep-fetch graphs."""

    def equal_value(a: Any, b: Any) -> bool:
        if isinstance(a, dict) or isinstance(b, dict):
            if not isinstance(a, dict) or not isinstance(b, dict):
                return False
            if a.keys() != b.keys():
                return False
            return all(equal_value(a[key], b[key]) for key in a)

        if isinstance(a, list) or isinstance(b, list):
            if not isinstance(a, list) or not isinstance(b, list):
                return False
            if len(a) != len(b):
                return False
            remaining = list(b)
            for item in a:
                for index, candidate in enumerate(remaining):
                    if equal_value(item, candidate):
                        del remaining[index]
                        break
                else:
                    return False
            return not remaining

        return _scalars_equal(a, b, None)

    return equal_value(left, right)


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
    projection = ", ".join(f"t0.{quote_identifier(column, db.dialect)}" for column in columns)
    return db.query(f"select {projection} from {quote_identifier(entity.table, db.dialect)} t0")


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


# --- scenarios (Phase 6, M8) ------------------------------------------------


def _step_statements(step: dict[str, Any], dialect: str) -> list[str]:
    """The ordered golden SQL statements a scenario step lists for *dialect*."""
    golden = step.get("goldenSql") or {}
    value = golden.get(dialect)
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def _scenario_has_golden(case: Case, dialect: str) -> bool:
    """True if any scenario step lists golden SQL for *dialect*."""
    return any(_step_statements(step, dialect) for step in case.scenario)


def _assert_scenario_normalization(case: Case, dialect: str) -> None:
    for index, step in enumerate(case.scenario):
        for sql in _step_statements(step, dialect):
            canonical = normalize(sql, dialect)
            if canonical != sql:
                raise CaseFailure(
                    f"{case.path.name}: scenario[{index}].goldenSql.{dialect} is "
                    f"not canonical.\n"
                    f"  stored:     {sql!r}\n"
                    f"  normalized: {canonical!r}"
                )


def _assert_scenario_count_consistency(case: Case, dialect: str) -> None:
    """Each step's declared roundTrips MUST equal its golden SQL statement count.

    A cache HIT lists no golden SQL and declares ``roundTrips: 0``; a cache MISS
    that executes one statement declares ``roundTrips: 1``. The steps' total MUST
    equal the case-level ``roundTrips``. This is the round-trip contract proven
    from the fixture's own declared counts — the harness never compiles an
    operation to SQL.
    """
    total = 0
    for index, step in enumerate(case.scenario):
        declared = step["roundTrips"]
        statements = _step_statements(step, dialect)
        if len(statements) != declared:
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] declares roundTrips "
                f"{declared} but lists {len(statements)} golden SQL statement(s) "
                f"for {dialect}. A step's declared round trips MUST equal the "
                f"number of golden SQL statements it emits (a cache hit = 0)."
            )
        total += declared
    if total != case.round_trips:
        raise CaseFailure(
            f"{case.path.name}: scenario steps total {total} round trip(s) but "
            f"roundTrips is {case.round_trips}. The case-level roundTrips MUST "
            f"equal the sum of the per-step round trips."
        )


def _pk_column(entity: Entity) -> str:
    for attribute in entity.attributes:
        if attribute.get("primaryKey"):
            return attribute["column"]
    return entity.attributes[0]["column"]


def _scenario_root_entity(case: Case) -> Entity:
    """The entity the scenario's finds target (the model's root entity).

    M8 scenarios query a single entity (cache / identity over one type), so the
    identity column defaults to that entity's primary-key column.
    """
    return case.model.root_entity


def _assert_scenario(case: Case, db: DatabaseProvider) -> None:
    """Execute the scenario against the provisioned DB and assert its contract.

    For each step: execute its listed golden SQL (a cache-hit step executes
    nothing and reuses the prior step's rows), assert ``expectRows`` when
    declared, and check any ``sameObjectAs`` identity assertion (both steps'
    results carry the same primary-key identity — the one-object-per-PK rule).
    """
    dialect = db.dialect
    default_identity = _pk_column(_scenario_root_entity(case))
    tolerance = case.tolerance

    results: list[list[dict[str, Any]]] = []
    for index, step in enumerate(case.scenario):
        statements = _step_statements(step, dialect)
        binds = step.get("binds", [])
        if "write" in step:
            # A committed write between finds (M8 read-your-own-writes / cache
            # invalidation): apply and COMMIT each DML statement on the unit of
            # work's connection. It captures no rows; a later find observes the
            # committed state. Its index still occupies a slot so `sameObjectAs`
            # references stay aligned.
            for statement_index, statement in enumerate(statements):
                stmt_binds = _binds_for_list(binds, statement_index, len(statements))
                db.execute(statement, stmt_binds)
            results.append([])
            continue
        if statements:
            # A DB-touching step: M8 finds are single-statement, so the round-trip
            # count is one; execute it and capture the rows.
            rows = _query_rows(db, statements[0], binds)
        else:
            # A cache hit: no statement executes. The contract is that it returns
            # the SAME interned objects as the find it hits — modeled here as
            # reusing the rows from the step named by `sameObjectAs` (or, absent
            # that, the immediately preceding step).
            source = step.get("sameObjectAs", index - 1)
            if source < 0 or source >= len(results):
                raise CaseFailure(
                    f"{case.path.name}: scenario[{index}] is a cache hit "
                    f"(roundTrips 0) but names no resolvable prior step to reuse."
                )
            rows = results[source]
        results.append(rows)

        expect = step.get("expectRows")
        if expect is not None and not _rows_equal(rows, expect, tolerance):
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] rows != expectRows.\n"
                f"  rows:     {rows!r}\n"
                f"  expected: {expect!r}"
            )

        if "sameObjectAs" in step:
            source = step["sameObjectAs"]
            if source < 0 or source >= index:
                raise CaseFailure(
                    f"{case.path.name}: scenario[{index}].sameObjectAs={source} "
                    f"must reference an EARLIER step."
                )
            identity_col = step.get("identityAttr", default_identity)
            this_ids = _identity_keys(case, index, rows, identity_col)
            that_ids = _identity_keys(case, source, results[source], identity_col)
            if this_ids != that_ids:
                raise CaseFailure(
                    f"{case.path.name}: scenario[{index}] is declared to denote "
                    f"the same object(s) as step {source}, but their primary-key "
                    f"identities differ (one-object-per-PK violated).\n"
                    f"  step {index}: {this_ids!r}\n"
                    f"  step {source}: {that_ids!r}"
                )


def _identity_keys(
    case: Case, index: int, rows: list[dict[str, Any]], identity_col: str
) -> list[Any]:
    """The ordered set of primary-key identities carried by *rows*."""
    if any(identity_col not in row for row in rows):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] result rows do not carry the "
            f"identity column {identity_col!r}; a scenario's finds MUST project "
            f"the primary key so identity can be checked."
        )
    return sorted(_coerce_identity_key(row[identity_col]) for row in rows)


# --- conflict cases (Phase 7, M10 optimistic locking) -----------------------


def _assert_conflict(case: Case, db: DatabaseProvider) -> None:
    """Run the precondition + golden UPDATE, assert the affected-row count.

    This is the observable form of optimistic-lock conflict detection (M10).
    The model's fixtures are loaded (the row exists with its current version),
    then an OPTIONAL out-of-band ``precondition`` simulates a concurrent
    transaction mutating the row (e.g. bumping the version). The golden
    ``UPDATE … where pk = ? and version = ?`` is then applied with the version
    the caller read EARLIER; if a concurrent write changed the version, the
    stale-version predicate matches **zero** rows — the conflict signal
    (``updatedRows != 1``). A fresh version matches exactly **one** row.

    The harness asserts the affected-row count equals ``expectedAffectedRows``,
    and (when authored) the resulting table state — so the contract is proven
    against real data, not merely asserted in prose.
    """
    dialect = db.dialect
    statements = case.golden_statements(dialect)
    if len(statements) != 1:
        raise CaseFailure(
            f"{case.path.name}: a conflict case has exactly one golden UPDATE "
            f"statement, but goldenSql.{dialect} lists {len(statements)}."
        )

    # Apply any out-of-band precondition (a concurrent mutation) before the UPDATE.
    for index, statement in enumerate(case.precondition):
        binds = _binds_for_list(case.precondition_binds, index, len(case.precondition))
        db.execute(statement, binds)

    affected = db.execute(statements[0], case.binds)
    expected = case.expected_affected_rows
    if affected != expected:
        raise CaseFailure(
            f"{case.path.name}: golden UPDATE affected {affected} row(s) but "
            f"expectedAffectedRows is {expected}. A stale optimistic-lock version "
            f"MUST affect 0 rows (conflict); a fresh version MUST affect 1."
        )

    if case.expected_table_state:
        entity_by_table = {entity.table: entity for entity in case.model.entities}
        for table, expected_rows in case.expected_table_state.items():
            if table not in entity_by_table:
                raise CaseFailure(
                    f"{case.path.name}: expectedTableState names table {table!r} "
                    f"which the model does not declare."
                )
            actual = _read_table(db, entity_by_table[table])
            if not _rows_equal(actual, expected_rows, case.tolerance):
                raise CaseFailure(
                    f"{case.path.name}: table {table!r} state after the conflict "
                    f"case != expectedTableState.\n"
                    f"  actual:   {actual!r}\n"
                    f"  expected: {expected_rows!r}"
                )


def _binds_for_list(binds: list[Any], index: int, count: int) -> list[Any]:
    """The binds for statement *index* of a (possibly multi-statement) list.

    A list-of-lists carries one bind list per statement; a flat list is the binds
    for a single statement. Mirrors :func:`_binds_for_statement` for the
    precondition list, which is independent of the case's golden-SQL ``binds``.
    """
    if binds and isinstance(binds[0], list):
        return binds[index] if index < len(binds) else []
    return binds if index == 0 else []


# --- conflict RETRY cases (M10 retry contract) ------------------------------


def _attempt_statements(attempt: dict[str, Any], dialect: str) -> list[str]:
    """The golden UPDATE statement(s) a retry attempt lists for *dialect*."""
    golden = attempt.get("goldenSql") or {}
    value = golden.get(dialect)
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def _conflict_retry_has_golden(case: Case, dialect: str) -> bool:
    """True if any retry attempt lists golden SQL for *dialect*."""
    return any(_attempt_statements(attempt, dialect) for attempt in case.attempts)


def _assert_conflict_retry_normalization(case: Case, dialect: str) -> None:
    for index, attempt in enumerate(case.attempts):
        for sql in _attempt_statements(attempt, dialect):
            canonical = normalize(sql, dialect)
            if canonical != sql:
                raise CaseFailure(
                    f"{case.path.name}: attempts[{index}].goldenSql.{dialect} is "
                    f"not canonical.\n"
                    f"  stored:     {sql!r}\n"
                    f"  normalized: {canonical!r}"
                )


def _assert_conflict_retry(case: Case, db: DatabaseProvider) -> None:
    """Run the precondition + ordered retry attempts, asserting each affected count.

    This is the observable form of the M10 RETRY contract (Phase 7). The model's
    fixtures are loaded (the versioned row exists), an OPTIONAL out-of-band
    ``precondition`` simulates a concurrent writer that advanced the version, then
    each attempt's golden ``UPDATE`` is applied in order. The first attempt gates
    on the STALE version the caller read before detaching/reading, so it affects
    ZERO rows (the ``updatedRows != 1`` conflict signal); the retry re-reads the
    now-fresh version and re-applies, affecting exactly ONE row. The harness
    asserts every attempt's affected-row count and (when authored) the final table
    state, proving the conflict was detected AND the retry closed the loop against
    real data.
    """
    dialect = db.dialect

    for index, statement in enumerate(case.precondition):
        binds = _binds_for_list(case.precondition_binds, index, len(case.precondition))
        db.execute(statement, binds)

    for index, attempt in enumerate(case.attempts):
        statements = _attempt_statements(attempt, dialect)
        if len(statements) != 1:
            raise CaseFailure(
                f"{case.path.name}: attempts[{index}] must list exactly one golden "
                f"UPDATE for {dialect}, found {len(statements)}."
            )
        affected = db.execute(statements[0], attempt.get("binds", []))
        expected = attempt["expectedAffectedRows"]
        if affected != expected:
            raise CaseFailure(
                f"{case.path.name}: attempts[{index}] UPDATE affected {affected} "
                f"row(s) but expectedAffectedRows is {expected}. A stale version "
                f"MUST affect 0 rows (conflict); the fresh-version retry MUST "
                f"affect 1."
            )

    _assert_table_state(case, db)


def _assert_table_state(case: Case, db: DatabaseProvider) -> None:
    """Assert each table named in ``expectedTableState`` matches (order-insensitive)."""
    if not case.expected_table_state:
        return
    entity_by_table = {entity.table: entity for entity in case.model.entities}
    for table, expected_rows in case.expected_table_state.items():
        if table not in entity_by_table:
            raise CaseFailure(
                f"{case.path.name}: expectedTableState names table {table!r} "
                f"which the model does not declare."
            )
        actual = _read_table(db, entity_by_table[table])
        if not _rows_equal(actual, expected_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: table {table!r} state != expectedTableState.\n"
                f"  actual:   {actual!r}\n"
                f"  expected: {expected_rows!r}"
            )


# --- coherence cases (Phase 11, cross-process cache coherence) ---------------


def _coherence_step_statements(step: dict[str, Any], dialect: str) -> list[str]:
    """The ordered golden SQL statements a coherence step lists for *dialect*."""
    golden = step.get("goldenSql") or {}
    value = golden.get(dialect)
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def _coherence_has_golden(case: Case, dialect: str) -> bool:
    """True if any coherence step lists golden SQL for *dialect*."""
    return any(_coherence_step_statements(step, dialect) for step in case.coherence)


def _assert_coherence_normalization(case: Case, dialect: str) -> None:
    for index, step in enumerate(case.coherence):
        for sql in _coherence_step_statements(step, dialect):
            canonical = normalize(sql, dialect)
            if canonical != sql:
                raise CaseFailure(
                    f"{case.path.name}: coherence[{index}].goldenSql.{dialect} is "
                    f"not canonical.\n"
                    f"  stored:     {sql!r}\n"
                    f"  normalized: {canonical!r}"
                )


def _assert_coherence(case: Case, db: DatabaseProvider) -> None:
    """Run the two-node coherence sequence and assert node B observes A's write.

    The harness provisions ONE database (node A = the provider's own connection,
    with the model's fixtures loaded so the seed read has a row) and opens a
    second, independent connection (node B) via the provider's ``open_peer`` seam.
    Each step runs on its declared node, executing that step's golden SQL: a
    ``write`` step COMMITs DML on its node; a ``read`` step queries. A step that
    declares ``observeRows`` asserts the rows its node observes — most importantly
    the FINAL node-B re-fetch, which MUST return node A's committed post-write
    state, never the stale pre-write rows.

    The harness contains no cache and no notification bus; it proves the suite's
    post-write golden SQL is correct against real, committed, cross-connection
    data — the observable contract any conforming invalidation mechanism satisfies.
    """
    dialect = db.dialect
    tolerance = case.tolerance

    _provision(case, db)  # fixtures loaded so the seed read sees a row
    with db.open_peer() as peer:
        nodes: dict[str, Any] = {"A": db, "B": peer}
        for index, step in enumerate(case.coherence):
            node = nodes[step["node"]]
            statements = _coherence_step_statements(step, dialect)
            if step["kind"] == "write":
                for statement_index, statement in enumerate(statements):
                    binds = _binds_for_list(
                        step.get("binds", []), statement_index, len(statements)
                    )
                    node.execute(statement, binds)
                continue

            # A read step: execute its SELECT on its node and (when declared)
            # assert the rows it observes.
            if not statements:
                raise CaseFailure(
                    f"{case.path.name}: coherence[{index}] is a read step but "
                    f"lists no golden SQL for {dialect}."
                )
            rows: list[dict[str, Any]] = []
            for statement_index, statement in enumerate(statements):
                binds = _binds_for_list(
                    step.get("binds", []), statement_index, len(statements)
                )
                rows = _query_rows(node, statement, binds)
            observe = step.get("observeRows")
            if observe is not None and not _rows_equal(rows, observe, tolerance):
                raise CaseFailure(
                    f"{case.path.name}: coherence[{index}] on node "
                    f"{step['node']} observed rows != observeRows.\n"
                    f"  observed: {rows!r}\n"
                    f"  expected: {observe!r}\n"
                    f"  (node B's re-fetch after node A's committed write MUST "
                    f"return the new state, never the stale cached rows.)"
                )


# --- entry point ------------------------------------------------------------


def run_case(case: Case, db: DatabaseProvider) -> None:
    """Run all available assertion layers for *case* against *db*."""
    dialect = db.dialect

    if case.is_scenario:
        if not _scenario_has_golden(case, dialect):
            # No golden SQL for this dialect anywhere in the scenario: still run
            # the dialect-agnostic checks so coverage is not skipped.
            _assert_schema(case)
            _assert_serde(case)
            _assert_equivalent_encodings(case)
            return
        _assert_schema(case)
        _assert_scenario_normalization(case, dialect)  # layer 3
        _assert_serde(case)  # layer 4
        _assert_equivalent_encodings(case)  # layer 4c
        _assert_scenario_count_consistency(case, dialect)  # layer 5 (count)
        _provision(case, db)
        _assert_scenario(case, db)  # layer 2 + identity
        return

    if case.is_coherence:
        if not _coherence_has_golden(case, dialect) or not hasattr(db, "open_peer"):
            # No golden SQL for this dialect, or this provider has no two-node
            # seam: run the dialect-agnostic checks so coverage is not skipped.
            _assert_schema(case)
            _assert_serde(case)
            _assert_equivalent_encodings(case)
            return
        _assert_schema(case)
        _assert_coherence_normalization(case, dialect)  # layer 3
        _assert_serde(case)  # layer 4
        _assert_equivalent_encodings(case)  # layer 4c
        _assert_coherence(case, db)  # layer 2 (two-node observation)
        return

    if case.is_conflict and case.attempts:
        # Retry conflict (M10): golden SQL lives PER ATTEMPT, so there is no
        # top-level goldenSql to key on. Handle it here, before the goldenSql
        # access below, mirroring the scenario / coherence per-step shapes.
        if not _conflict_retry_has_golden(case, dialect):
            _assert_schema(case)
            _assert_serde(case)
            _assert_equivalent_encodings(case)
            return
        _assert_schema(case)
        _assert_conflict_retry_normalization(case, dialect)  # layer 3
        _assert_serde(case)  # layer 4
        _assert_equivalent_encodings(case)  # layer 4c
        _provision(case, db)  # fixtures loaded: the versioned row exists
        _assert_conflict_retry(case, db)  # precondition + ordered attempts
        return

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

    if case.is_conflict:
        _provision(case, db)  # fixtures loaded: the row to lock exists
        _assert_conflict(case, db)  # precondition + golden UPDATE, affected rows
        return

    _assert_round_trip_count(case, dialect)  # layer 5 (count)
    _provision(case, db)
    if _is_deep_fetch(case):
        _assert_deep_fetch(case, db)  # layer 2 + 5 (graph)
    else:
        _assert_flat_equivalence(case, db)  # layer 2
