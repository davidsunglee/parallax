"""The layered assertion engine (m-case-format runner sub-part).

Per case, against a freshly-provisioned database selected via the provider seam:

1. **Schema conformance** — descriptor / operation / case validate (done
   statically by :mod:`schema_validate`; re-asserted here for the loaded case).
2. **Triple equivalence** — ``exec(then.statements[dialect]) == exec(referenceSql) ==
   then.rows`` (the ``referenceSql`` term only when present).
3. **Normalization determinism** — ``normalize(then.statements[dialect]) ==
   then.statements[dialect]`` (per statement, for multi-statement cases).
4. **Serde round-trip** — ``serialize(deserialize(x)) == x`` for BOTH the
   operation encoding AND the model descriptor, in BOTH JSON and YAML.
5. **Round-trip-count consistency** (Phase 3) — for relationship / deep-fetch
   cases the number of golden SQL statements equals the declared ``roundTrips``,
   each level executes (child levels keyed by the parents gathered from the
   previous level), and the assembled object graph equals ``then.graph``.

It deliberately **never compiles the operation to SQL** — that is the job of a
real implementation, graded against the golden SQL.
"""

from __future__ import annotations

import contextlib
import functools
import json
import re
import threading
from decimal import Decimal
from typing import Any

from . import errors, serde
from .case import Case, Entity, Model
from .data_loader import load_model
from .ddl_builder import column_order, ddl_for, quote_identifier
from .op_validate import validate_operation
from .providers import DatabaseProvider
from .sql_normalize import normalize
from .value_object_resolve import REJECTED_RULES, RejectionError
from .write_validate import validate_write


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


def _row_matches(left: dict[str, Any], right: dict[str, Any], tolerance: Decimal | None) -> bool:
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


# --- statement-entry readers ------------------------------------------------
#
# Every per-step SQL location (scenario / coherence / attempts / concurrency
# rounds) carries its golden SQL as an ordered list of `{sql, binds}` statement
# entries, mirroring the top-level `then.statements`. Binds are attached to their
# statement structurally — there is no positional pairing convention to interpret.


def _entry_statements(entries: Any, dialect: str) -> list[str]:
    """The per-dialect golden SQL texts of a `statements` entry list (empty if none)."""
    if not isinstance(entries, list):
        return []
    return [
        entry["sql"][dialect]
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("sql"), dict)
        and dialect in entry["sql"]
    ]


def _entry_pairs(entries: Any, dialect: str) -> list[tuple[str, list[Any]]]:
    """The ``(sql, binds)`` pairs a `statements` entry list declares for *dialect*.

    Each statement's binds ride inline on its own entry (default ``[]``), so the
    execution sites read the two together rather than pairing them positionally.
    """
    if not isinstance(entries, list):
        return []
    pairs: list[tuple[str, list[Any]]] = []
    for entry in entries:
        sql = entry.get("sql") if isinstance(entry, dict) else None
        if isinstance(sql, dict) and dialect in sql:
            pairs.append((sql[dialect], list(entry.get("binds", []))))
    return pairs


def _entry_binds(entries: Any, index: int) -> list[Any]:
    """The authored binds of statement *index* in a `statements` entry list (default [])."""
    if not isinstance(entries, list) or index >= len(entries):
        return []
    entry = entries[index]
    return list(entry.get("binds", [])) if isinstance(entry, dict) else []


def _assert_schema(case: Case) -> None:
    # Layer 1 is enforced statically across the whole tree by schema_validate.
    # Here we assert the minimal structural invariants the runner relies on so a
    # malformed case fails loudly rather than deep in execution.
    if case.is_write_sequence:
        if not case.expected_table_state:
            raise CaseFailure(f"{case.path.name}: write sequence missing then.tableState")
    elif case.is_scenario:
        if not case.scenario:
            raise CaseFailure(f"{case.path.name}: scenario case has no steps")
    elif case.is_conflict:
        if case.expected_affected_rows is None and not case.attempts:
            raise CaseFailure(f"{case.path.name}: conflict case missing affectedRows / attempts")
    elif case.is_coherence:
        if len(case.coherence) < 2:
            raise CaseFailure(
                f"{case.path.name}: coherence case needs at least a write and a re-fetch step"
            )
        for index, step in enumerate(case.coherence):
            if step.get("kind") == "write" and "sameObjectAs" in step:
                raise CaseFailure(
                    f"{case.path.name}: coherence[{index}] is a write step but "
                    f"declares sameObjectAs; identity is asserted on read steps "
                    f"(a write observes no object)."
                )
        if not any(step.get("observeRows") is not None for step in case.coherence):
            raise CaseFailure(
                f"{case.path.name}: coherence case asserts nothing — at least the "
                f"final re-fetch MUST declare observeRows"
            )
    elif case.is_error:
        if not case.error_class:
            raise CaseFailure(f"{case.path.name}: error case missing errorClass")
        if not case.expected_native_code:
            raise CaseFailure(f"{case.path.name}: error case missing then.nativeCode")
        if not (_error_has_golden(case, "postgres") or _error_has_golden(case, "mariadb")):
            raise CaseFailure(
                f"{case.path.name}: error case declares no trigger — needs then.statements "
                f"(single-connection) or a non-empty concurrency choreography"
            )
    elif case.is_concurrency_success:
        if not (
            _concurrency_has_golden(case, "postgres") or _concurrency_has_golden(case, "mariadb")
        ):
            raise CaseFailure(
                f"{case.path.name}: concurrency-success case has an empty concurrency "
                f"choreography (no round declares a golden statement)"
            )
        # Fail fast (DB-free, timing-independent) if a success step omits its `kind` or a
        # `read` forgot expectRows: the runner branches read-vs-write on the EXPLICIT kind
        # (no SQL-verb sniffing), so a mis-declared step would mis-dispatch. Redundant with
        # the schema (which requires kind + the read/write expectRows rule), as defense.
        _assert_concurrency_success_step_kinds(case)
    elif case.is_boundary:
        if not case.boundary:
            raise CaseFailure(f"{case.path.name}: boundary case has no actions")
        if not case.outcome:
            raise CaseFailure(f"{case.path.name}: boundary case missing outcome")
    elif case.is_rejected:
        if case.rejected_rule not in REJECTED_RULES:
            raise CaseFailure(
                f"{case.path.name}: rejected case then.rejectedRule "
                f"{case.rejected_rule!r} is not a known rule"
            )
        # A rejected case pins a SINGLE invalid input, so its `when` MUST carry
        # EXACTLY ONE of `operation` / `write` (the normative "exactly one invalid
        # input" rule, m-case-format Rejected cases). This XOR guard is a
        # defense-in-depth mirror of the schema's `oneOf`
        # (compatibility-case.schema.json rejected branch): it keeps the constraint
        # enforced even if some future caller reaches the runner without schema
        # validation, and `_assert_rejected` below validates `operation` first and
        # would otherwise SILENTLY ignore a `write` present alongside it.
        has_operation = "operation" in case.when
        has_write = "write" in case.when
        if has_operation == has_write:
            raise CaseFailure(
                f"{case.path.name}: a rejected case MUST carry EXACTLY ONE of "
                f"when.operation / when.write (one invalid input); found "
                f"{'both' if has_operation else 'neither'}."
            )
    elif "operation" not in case.when:
        raise CaseFailure(f"{case.path.name}: missing operation")
    if not case.model.class_name:
        raise CaseFailure(f"{case.path.name}: model has no class name")
    _assert_binds_dialect_keys(case)
    _assert_reference_sql_dialect_keys(case)


def _assert_binds_dialect_keys(case: Case) -> None:
    """A golden entry's dialect-keyed ``binds`` map MUST cover the same dialects as
    its ``sql`` map (m-case-format resolved question 12). A flat-array ``binds`` is
    dialect-agnostic and imposes no constraint. This is the cross-field invariant
    JSON Schema alone cannot express — resolve-per-dialect would otherwise silently
    miss a dialect whose binds were never authored.
    """
    for index, entry in enumerate(case.golden_entries()):
        binds = entry.get("binds")
        if not isinstance(binds, dict):
            continue
        sql = entry.get("sql")
        sql_keys = set(sql) if isinstance(sql, dict) else set()
        if set(binds) != sql_keys:
            raise CaseFailure(
                f"{case.path.name}: then.statements[{index}] binds map keys "
                f"{sorted(binds)} != sql map keys {sorted(sql_keys)}; a dialect-keyed "
                f"binds map MUST cover exactly the dialects its sql map declares."
            )


def _assert_reference_sql_dialect_keys(case: Case) -> None:
    """A dialect-keyed ``then.referenceSql`` map MUST cover exactly the dialects the
    case's golden ``sql`` maps declare (m-case-format resolved question 12) — the
    ``referenceSql`` analogue of :func:`_assert_binds_dialect_keys`. A plain-string
    ``referenceSql`` is dialect-agnostic and imposes no constraint; an absent one
    (a trivial case with no oracle) is likewise unconstrained.

    Enforcing this closes a silent gap: without it, a ``referenceSql`` map that omits
    a dialect the golden ``sql`` declares would drop the INDEPENDENT oracle for that
    dialect unnoticed — the run would still pass on the golden-vs-``then.rows`` check
    alone, exactly the self-consistent-but-wrong failure the oracle exists to catch.
    ``golden_dialects`` is the set the run loop keys execution on, so matching against
    it guarantees every executed dialect has its oracle.
    """
    reference_sql = case.then.get("referenceSql")
    if not isinstance(reference_sql, dict):
        return
    sql_keys = case.golden_dialects
    if set(reference_sql) != sql_keys:
        raise CaseFailure(
            f"{case.path.name}: then.referenceSql map keys {sorted(reference_sql)} "
            f"!= golden sql map keys {sorted(sql_keys)}; a dialect-keyed referenceSql "
            f"map MUST cover exactly the dialects its golden sql declares, so no "
            f"executed dialect runs without its independent oracle."
        )


def _assert_normalization(case: Case, dialect: str) -> None:
    for index, statement in enumerate(case.golden_statements(dialect)):
        canonical = normalize(statement, dialect)
        if canonical != statement:
            where = f"then.statements[{index}].sql.{dialect}"
            raise CaseFailure(
                f"{case.path.name}: {where} is not canonical.\n"
                f"  stored:     {statement!r}\n"
                f"  normalized: {canonical!r}"
            )


def _assert_serde(case: Case) -> None:
    # Layer 4a: operation serde. A read case has one top-level operation; a
    # scenario case has one operation per step (under `find`); a write-sequence
    # case and a conflict case (m-opt-lock) have none. Layer 4b: metamodel (descriptor)
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
    elif case.is_rejected:
        # A rejected case carries the invalid input under `when.operation` (a
        # schema-valid m-op-algebra node — serde it) OR `when.write` (a neutral write
        # row, which has no operation to serde). The descriptor still round-trips.
        if "operation" in case.when:
            serde.assert_roundtrip(case.when["operation"])
    elif (
        not case.is_write_sequence
        and not case.is_conflict
        and not case.is_error
        and not case.is_concurrency_success
    ):
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
    if (
        case.is_write_sequence
        or case.is_scenario
        or case.is_conflict
        or case.is_coherence
        or case.is_error
        or case.is_concurrency_success
    ):
        # A write-sequence and a conflict case have no operation; a scenario and a
        # coherence case carry their operations per step. An error case and a
        # concurrency-success case have no operation either. Equivalent-encodings is a
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
            f"{case.path.name}: then.statements ({dialect}) has {len(statements)} "
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
    """The deep-fetch paths as ordered lists of ``Class.relationship`` refs.

    A path segment is a closed object ``{rel, narrow?}`` in the canonical operation
    (m-op-algebra); the deep-fetch machinery here keys hops by the relationship ref,
    so each segment is projected to its ``rel``. ``narrow`` (deferred) is ignored.
    """
    return [[segment["rel"] for segment in path] for path in case.operation["deepFetch"]["paths"]]


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


# Canonical as-of axis order: business terms precede processing terms in both the
# golden SQL clause order and the bind order (m-bitemp-write bitemporal table;
# case m-temporal-read-015).
_CANONICAL_AXIS_ORDER: tuple[str, ...] = ("business", "processing")


def _peel_directive_wrappers(node: Any) -> Any:
    """Descend past the result-directive wrappers (``distinct`` / ``orderBy`` /
    ``limit``) that the root compile peels *before* the temporal wrappers, returning
    the innermost node. Without this, a directive-wrapped temporal root (e.g.
    ``limit(orderBy(asOf(...)))``, case m-navigate-024) would seed no child propagation pins
    and the child would wrongly default to now (mismatching the authored instant).
    """
    while isinstance(node, dict):
        for directive in ("distinct", "orderBy", "limit"):
            if directive in node:
                node = node[directive]["operand"]
                break
        else:
            break
    return node


def _root_asof_pins(case: Case) -> dict[str, str]:
    """Map ``{axis: pinned date}`` from the nested ``asOf`` nodes wrapping the
    deep-fetch root operand. An axis absent here defaults to the child's own
    default ("now" = latest) at propagation time. Empty when the root is unpinned.

    Result directives (``distinct`` / ``orderBy`` / ``limit``) are peeled first,
    mirroring the root compile, so a directive-wrapped temporal root still pins.
    """
    pins: dict[str, str] = {}
    node: Any = _peel_directive_wrappers(_deepfetch_root_operand(case))
    while isinstance(node, dict) and "asOf" in node:
        asof = node["asOf"]
        entity_name, attr_name = asof["asOfAttr"].split(".", 1)
        entity = case.model.entity(entity_name)
        axis = next(a["axis"] for a in entity.as_of_attributes if a["name"] == attr_name)
        pins[axis] = asof["date"]
        node = asof["operand"]
    return pins


def _expected_asof_suffix(child_entity: Entity, pins: dict[str, str]) -> list[Any]:
    """The as-of binds a temporal child level MUST carry, after its IN-list.

    Per-axis, in canonical order (business, then processing): the propagated value
    is the root pin for that axis, or the child's own ``default`` ("now") when the
    root did not pin it. ``now``/latest lowers to the single equality bind
    (the axis's ``infinity``); a finite instant lowers to the half-open range's
    two binds ``[D, D]``. A non-temporal child yields ``[]``.
    """
    by_axis = {a["axis"]: a for a in child_entity.as_of_attributes}
    suffix: list[Any] = []
    for axis in _CANONICAL_AXIS_ORDER:
        attr = by_axis.get(axis)
        if attr is None:
            continue
        date = pins.get(axis, attr.get("default", "now"))
        if date == "now":
            suffix.append(attr["infinity"])
        else:
            suffix.extend([date, date])
    return suffix


def _expected_sequence_ids(initial: int, increment: int, batch: int, count: int) -> list[int]:
    """The ids a simulated sequence hands out for *count* inserts, in order.

    Within a reserved block of *batch* ids the values step by *increment*; the
    next block's base is *batch* x *increment* higher. Inserting fewer than a
    full block consumes the block's leading ids (the rest are reserved-and-lost).
    """
    ids: list[int] = []
    for i in range(count):
        block, offset = divmod(i, batch)
        ids.append(initial + block * batch * increment + offset * increment)
    return ids


def _expected_sequence_counter(initial: int, increment: int, batch: int, count: int) -> int:
    """The registry counter after *count* inserts: a full block is reserved per
    allocation, so it advances by ``batch * increment`` for each block touched.
    """
    blocks = -(-count // batch)  # ceil division (count >= 0, batch >= 1)
    return initial + blocks * batch * increment


def _pk_sequence_target(case: Case) -> tuple[Entity, dict[str, Any], dict[str, Any]] | None:
    """The ``sequence``-strategy entity this writeSequence case inserts into.

    Returns ``(entity, pkGenerator, pk_attribute)`` or ``None`` when the case does
    not insert into a sequence entity (e.g. ``max`` cases, non-pk-gen cases).
    """
    inserted = {step["entity"] for step in case.write_sequence if step.get("mutation") == "insert"}
    for entity in case.model.entities:
        if entity.name not in inserted:
            continue
        pk_attr = next((a for a in entity.attributes if a.get("primaryKey")), None)
        if pk_attr is None:
            continue
        gen = pk_attr.get("pkGenerator")
        if isinstance(gen, dict) and gen.get("strategy") == "sequence":
            return entity, gen, pk_attr
    return None


def _pk_sequence_registry(model: Model, exclude: Entity) -> Entity:
    """The simulated-sequence registry entity: the string-PK counter table."""
    for entity in model.entities:
        if entity.name == exclude.name:
            continue
        pk_attr = next((a for a in entity.attributes if a.get("primaryKey")), None)
        if pk_attr is not None and pk_attr.get("type") == "string":
            return entity
    raise CaseFailure(
        f"model {model.class_name!r} declares a sequence pkGenerator but has no "
        f"string-PK registry entity"
    )


def _pk_sequence_counter_column(registry: Entity) -> str:
    """The simulated-sequence registry's counter column: its int64 non-PK
    attribute. Require exactly one so the selection is unambiguous even if the
    registry entity ever grows another column.
    """
    counters = [
        a for a in registry.attributes if not a.get("primaryKey") and a.get("type") == "int64"
    ]
    if len(counters) != 1:
        raise CaseFailure(
            f"simulated-sequence registry {registry.name!r} must have exactly one "
            f"int64 non-PK counter column, found {len(counters)}"
        )
    return counters[0]["column"]


def _assert_pk_allocation(case: Case, db: DatabaseProvider) -> None:
    """PK-generation oracle (sequence strategy).

    Independently re-derives, from the DECLARED pkGenerator config, the ids a
    simulated sequence should have allocated and the value its registry counter
    should hold, and asserts both against the real post-write DB state. ``max`` and
    non-pk-gen writeSequence cases are a no-op (``max`` is pinned by its
    self-describing ``coalesce(max(...),0)+1`` golden + ``then.tableState``).
    """
    target = _pk_sequence_target(case)
    if target is None:
        return
    entity, gen, pk_attr = target
    initial = gen.get("initialValue", 1)
    increment = gen.get("incrementSize", 1)
    batch = gen.get("batchSize", 1)
    seq_name = gen["sequenceName"]
    pk_column = pk_attr["column"]

    actual_rows = _read_table(db, entity)
    # Assumes target starts empty; row count equals ids allocated from initialValue
    # (a pre-seeded table would mismatch loudly, not silently).
    count = len(actual_rows)
    expected_ids = sorted(_expected_sequence_ids(initial, increment, batch, count))
    actual_ids = sorted(row[pk_column] for row in actual_rows)
    if actual_ids != expected_ids:
        raise CaseFailure(
            f"{case.path.name}: {entity.name} allocated PKs {actual_ids} != "
            f"config-derived {expected_ids} "
            f"(init={initial}, inc={increment}, batch={batch}, count={count})"
        )

    registry = _pk_sequence_registry(case.model, entity)
    name_column = next(a for a in registry.attributes if a.get("primaryKey"))["column"]
    counter_column = _pk_sequence_counter_column(registry)
    reg_rows = _read_table(db, registry)
    reg_row = next((r for r in reg_rows if r.get(name_column) == seq_name), None)
    if reg_row is None:
        raise CaseFailure(f"{case.path.name}: {registry.name} has no row for sequence {seq_name!r}")
    expected_counter = _expected_sequence_counter(initial, increment, batch, count)
    if reg_row.get(counter_column) != expected_counter:
        raise CaseFailure(
            f"{case.path.name}: sequence {seq_name!r} counter "
            f"{reg_row.get(counter_column)} != config-derived {expected_counter}"
        )


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
    empty schema and is fully self-contained — UNLESS it sets ``given.fixtures``
    (the m-detach detached-update merge-back case), in which case the model's fixtures
    are loaded first so the merge-back can mutate a pre-existing persisted row.
    """
    db.reset()
    db.apply_ddl(ddl_for(case.model, db.dialect))
    if case.load_fixtures:
        load_model(case.model, db)


def _assert_flat_equivalence(case: Case, db: DatabaseProvider) -> None:
    dialect = db.dialect
    (golden,) = case.golden_statements(dialect)

    golden_rows = _query_rows(db, golden, case.statement_binds(0, dialect))
    expected = case.expected_rows
    tolerance = case.tolerance

    if not _rows_equal(golden_rows, expected, tolerance):
        raise CaseFailure(
            f"{case.path.name}: then.statements ({dialect}) rows != then.rows.\n"
            f"  golden:   {golden_rows!r}\n"
            f"  expected: {expected!r}"
        )

    reference_sql = case.reference_sql_for(dialect)
    if reference_sql is not None:
        reference_rows = db.query(reference_sql)
        if not _rows_equal(reference_rows, expected, tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql rows != then.rows.\n"
                f"  reference: {reference_rows!r}\n"
                f"  expected:  {expected!r}"
            )


def _sorted_by_order_keys(
    rows: list[dict[str, Any]],
    sort_spec: list[tuple[str, bool]],
) -> list[dict[str, Any]]:
    """Return *rows* sorted by *sort_spec* — a list of ``(column, descending)``
    pairs evaluated left to right. Stable: rows tied on every key keep input order.
    NULL values sort LAST on every key, regardless of ``asc``/``desc`` (m-navigate policy).
    """

    def compare(row_a: dict[str, Any], row_b: dict[str, Any]) -> int:
        for column, descending in sort_spec:
            left, right = row_a[column], row_b[column]
            if left == right:
                continue
            # NULLs sort last on every key, regardless of asc/desc (m-navigate policy).
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
    query to emit ``ORDER BY`` over the declared keys (m-navigate), so the rows the DB
    returned — preserved in SQL order inside each parent's bucket — must already
    equal those rows sorted by the declared keys/directions. The harness derives
    the expected order from the model (an independent oracle) rather than trusting
    the authored ``then.graph`` order. A relationship with no ``orderBy`` is
    skipped (its order is unspecified). NULL values sort LAST on every key,
    regardless of ``asc``/``desc`` (the canonical m-navigate policy); two NULLs are equal
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
    """Execute each level, assemble the object graph, compare to then.graph.

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
    root_pins = _root_asof_pins(case)

    # Level 0: the root query.
    root_binds = case.statement_binds(0, dialect)
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
            {_coerce_identity_key(p[parent_col]) for p in parents if p.get(parent_col) is not None}
        )

        if not parent_keys:
            rows_by_entity[step.child_entity.name] = []
            children_by_step[step.rel_ref] = {}
            continue

        if statement_index >= len(statements):
            raise CaseFailure(
                f"{case.path.name}: then.statements ({dialect}) has no child statement "
                f"for {step.rel_ref}, but the previous level gathered parent "
                f"keys {parent_keys!r}."
            )

        raw_authored = case.statement_binds(statement_index, dialect)
        in_slice = raw_authored[: len(parent_keys)]
        asof_suffix = list(raw_authored[len(parent_keys) :])
        if sorted(_coerce_identity_key(b) for b in in_slice) != parent_keys:
            raise CaseFailure(
                f"{case.path.name}: then.statements ({dialect}) level {statement_index} "
                f"({step.rel_ref}) IN-list binds {in_slice!r} != gathered parent "
                f"keys {parent_keys!r}. The child level MUST be keyed by exactly "
                f"the parents from the previous level (the N+1-eliminating IN list)."
            )

        # As-of propagation oracle: the root pin propagates per-hop, matched by
        # axis, to each temporal child level. The harness derives the child's
        # as-of binds independently and asserts the authored suffix matches, so a
        # dropped/wrong propagated as-of fails the case. A non-temporal child has
        # an empty suffix (no as-of term).
        expected_suffix = (
            _expected_asof_suffix(step.child_entity, root_pins)
            if step.child_entity.is_temporal
            else []
        )
        if asof_suffix != expected_suffix:
            raise CaseFailure(
                f"{case.path.name}: then.statements ({dialect}) level {statement_index} "
                f"({step.rel_ref}) as-of suffix {asof_suffix!r} != the propagated "
                f"as-of binds {expected_suffix!r}. The root pin MUST propagate to "
                f"this temporal child (matched by axis), appended after the IN list."
            )

        child_rows = _query_rows(
            db, statements[statement_index], list(parent_keys) + expected_suffix
        )
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
            f"{case.path.name}: then.statements ({dialect}) lists "
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
            f"{case.path.name}: assembled graph != then.graph.\n"
            f"  assembled: {assembled!r}\n"
            f"  expected:  {expected!r}"
        )

    # referenceSql (a single naive statement) is the independent oracle for the
    # ROOT row set of the deep fetch.
    reference_sql = case.reference_sql_for(db.dialect)
    if reference_sql is not None:
        reference_rows = db.query(reference_sql)
        root_projection = [_project_like(r, root_rows) for r in reference_rows]
        if not _rows_equal(root_projection, root_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql root rows != then.statements root rows.\n"
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


# --- value-object materialization (m-value-object graph read) ---------------


def _decode_document(raw: Any) -> Any:
    """Decode a structured-document column value to a Python object.

    The single value-object column materializes with the owning entity in one
    round trip (m-value-object). Postgres returns a ``jsonb`` column already
    parsed (a ``dict`` / ``list``); MariaDB returns its ``json`` column as the raw
    JSON text (``str`` / ``bytes``). Both collapse to the same Python structure
    here, so the projection below is dialect-agnostic. A SQL-NULL column is
    ``None``.
    """
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray, memoryview)):
        raw = bytes(raw).decode()
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def _project_value_object(vo: dict[str, Any], decoded: Any) -> Any:
    """Project a decoded document slot to its DECLARED value-object shape.

    The projection mirrors the typed getter surface (m-value-object): only
    declared members appear (undeclared JSON keys are dropped), every declared
    member is always present (null where the document does not supply it), and the
    absence states collapse exactly as the read predicates do (m-op-algebra,
    resolved Q5):

    * a ``one`` member is a nested object when the slot is a JSON object, else
      ``None`` (a SQL-NULL column, a missing key, a JSON ``null``, or a non-object
      intermediate all read as "not present");
    * a ``many`` member is the collection of its element projections when the
      slot is a JSON array, else ``[]`` (a null / missing / non-array ``many``
      value collapses to zero elements).

    Element order within a ``many`` member is UNSPECIFIED (m-value-object): this
    projection walks the JSON array in document order for readability, but that
    order is not part of the contract. ``then.graph`` comparison of value-object
    arrays reuses :func:`_graphs_equal`'s order-insensitive list comparison (a
    multiset compare — element multiplicity still matters, only order does not),
    so a reordered array still matches. That reuse is INTENTIONAL here, not an
    oversight.
    """
    if vo.get("cardinality", "one") == "many":
        if isinstance(decoded, list):
            return [_project_members(vo, element) for element in decoded]
        return []
    if isinstance(decoded, dict):
        return _project_members(vo, decoded)
    return None


def _project_members(vo: dict[str, Any], obj: Any) -> dict[str, Any]:
    """Build the declared-member projection of one value-object document object.

    Each declared ``attribute`` contributes its leaf value (``None`` for a missing
    key or a JSON ``null``); each declared nested ``valueObject`` recurses. A
    non-object element (e.g. a scalar inside a ``many`` array) yields all-null
    declared members. Undeclared keys are omitted, so the projected node's key set
    is exactly the declared members — the shape the typed getters expose.
    """
    source = obj if isinstance(obj, dict) else {}
    node: dict[str, Any] = {}
    for attribute in vo.get("attributes", []):
        node[attribute["name"]] = source.get(attribute["name"])
    for nested in vo.get("valueObjects", []):
        node[nested["name"]] = _project_value_object(nested, source.get(nested["name"]))
    return node


def _materialize_owner_node(entity: Entity, row: dict[str, Any]) -> dict[str, Any]:
    """A read row with its top-level value-object columns decoded + projected.

    Scalar columns pass through under their result-column name; each declared
    top-level value object's document column is decoded and replaced by its
    declared projection, keyed by the value-object name. A value-object column
    the golden SELECT did not project is left untouched (no synthetic null).
    """
    node = _normalize_row(row)
    for vo in entity.value_objects:
        column = vo["column"]
        if column not in node:
            continue
        node[vo["name"]] = _project_value_object(vo, _decode_document(node.pop(column)))
    return node


def _assert_value_object_graph(case: Case, db: DatabaseProvider) -> None:
    """Assert a value object materializes WITH its owner in one round trip.

    A value-object graph read carries a single golden statement (``roundTrips: 1``
    — enforced by :func:`_assert_round_trip_count`) that projects the owning
    entity including its structured-document column(s); there is **no** child
    statement. The harness executes that one statement, decodes each row's
    value-object column into its declared nested to-one / to-many projection, and
    asserts the assembled ``{Class: [node, …]}`` graph equals ``then.graph`` — the
    proof that nested values arrive with the owner, never via a deep fetch
    (m-value-object, "Materialization and navigation contract").

    The comparison reuses :func:`_graphs_equal`, whose list comparison is
    order-insensitive (a multiset compare). For value-object ``many`` members that
    reuse is INTENTIONAL, not an oversight: element order within a ``many`` member
    is unspecified (m-value-object), so a reordered ``phones`` array still matches
    while element multiplicity is still enforced.

    When a ``referenceSql`` oracle is present it independently pins the matched
    row SET (identity columns only, the value-object columns stripped), so the
    filter that selected the owners is checked by a different formulation without
    routing the JSON document through row comparison.
    """
    dialect = db.dialect
    (golden,) = case.golden_statements(dialect)
    entity = case.model.root_entity

    rows = _query_rows(db, golden, case.statement_binds(0, dialect))
    assembled = {entity.name: [_materialize_owner_node(entity, row) for row in rows]}

    expected = case.expected_graph or {}
    if not _graphs_equal(assembled, expected):
        raise CaseFailure(
            f"{case.path.name}: materialized value-object graph != then.graph.\n"
            f"  assembled: {assembled!r}\n"
            f"  expected:  {expected!r}"
        )

    reference_sql = case.reference_sql_for(dialect)
    if reference_sql is not None:
        vo_columns = {vo["column"] for vo in entity.value_objects}
        identity_rows = [
            {key: value for key, value in row.items() if key not in vo_columns} for row in rows
        ]
        reference_rows = db.query(reference_sql)
        if not _rows_equal(reference_rows, identity_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql rows != golden owner rows (identity).\n"
                f"  reference: {reference_rows!r}\n"
                f"  expected:  {identity_rows!r}"
            )


# --- negative validation (Phase 8, the `rejected` shape) -------------------------------


def _assert_rejected(case: Case) -> None:
    """Assert the input is refused PRE-SQL by model-aware validation (m-case-format Q7).

    A ``rejected`` case carries a schema-valid ``when.operation`` OR a ``when.write``
    that a model-aware validator MUST refuse BEFORE any SQL is emitted, naming the
    violated normative rule in ``then.rejectedRule``. This runs the reference
    validators (``op_validate`` / ``write_validate``) against the queried entity's
    DECLARED value-object structure and asserts they raise EXACTLY that rule — the
    portable analogue of Reladomo refusing a structurally-invalid embedded-value use.
    No dialect, no provisioning, no execution: rejection is dialect-agnostic and
    happens with no database.
    """
    entity = case.model.root_entity
    expected = case.rejected_rule
    try:
        if "operation" in case.when:
            validate_operation(entity, case.when["operation"])
        elif "write" in case.when:
            validate_write(entity, case.write or {})
        else:  # pragma: no cover - guarded by _assert_schema
            raise CaseFailure(f"{case.path.name}: rejected case needs when.operation or when.write")
    except RejectionError as exc:
        if exc.rule != expected:
            raise CaseFailure(
                f"{case.path.name}: input was rejected with rule {exc.rule!r} "
                f"({exc.detail}) but the case expects then.rejectedRule {expected!r}."
            ) from exc
        return
    raise CaseFailure(
        f"{case.path.name}: expected a pre-SQL rejection ({expected!r}) but model-aware "
        f"validation ACCEPTED the input."
    )


# --- write sequences (Phase 5, m-audit-write) ------------------------------------------


def _assert_write_step_count(case: Case, dialect: str) -> None:
    """The DML statement count MUST equal the sum of the steps' declared counts.

    Each ``writeSequence`` step declares how many golden DML statements it emits
    (default 1); the total over the sequence is the round-trip count, which MUST
    equal the number of then.statements for the dialect (and ``roundTrips``).
    """
    statements = case.golden_statements(dialect)
    step_total = sum(step.get("statements", 1) for step in case.write_sequence)
    if len(statements) != step_total:
        raise CaseFailure(
            f"{case.path.name}: then.statements ({dialect}) has {len(statements)} DML "
            f"statement(s) but the writeSequence declares {step_total} "
            f"(sum of per-step statement counts). They MUST be equal."
        )
    if len(statements) != case.round_trips:
        raise CaseFailure(
            f"{case.path.name}: then.statements ({dialect}) has {len(statements)} DML "
            f"statement(s) but roundTrips is {case.round_trips}."
        )


_INSERT_COLUMNS_RE = re.compile(r"insert\s+into\s+\S+\s*\(([^)]*)\)", re.IGNORECASE)
_SET_CLAUSE_RE = re.compile(r"\bset\s+(.+?)\s+where\b", re.IGNORECASE)

# The full-bitemporal `*Until` rectangle-split mutations (DQ11): a business-bounded
# write whose ① carries the valid-time window (`at`/`until`/`businessFrom`).
_UNTIL_MUTATIONS = ("insertUntil", "updateUntil", "terminateUntil")

# The plain (UNBOUNDED) bitemporal rectangle-split mutations: an everyday business
# correction/termination from an instant onward with no upper business bound
# (`m-bitemp-write-006` / `m-bitemp-write-007`). Like the `*Until` trio they close
# the original on the processing axis and chain head / (new-)tail milestones, but
# the residual window runs to the open bound (thru_z), so ① carries no `until`.
_PLAIN_SPLIT_MUTATIONS = ("update", "terminate")


def _is_bitemporal(entity: Entity) -> bool:
    """Whether an entity carries BOTH as-of axes (business + processing) — the
    full-bitemporal rectangle profile, where a plain `update` / `terminate` is a
    milestone rectangle split (close + chain), not the audit-only close-and-open."""
    axes = {dim.get("axis") for dim in entity.as_of_attributes}
    return {"business", "processing"} <= axes


def _is_computed_marker(value: Any) -> bool:
    """Whether an ① value is a DB-COMPUTED pk-gen `max` marker.

    ``{ computed: "maxPlusOne" }`` names a column the database derives as
    ``coalesce(max(col), ?) + ?`` (its binds are the strategy's coalesce base +
    increment), so the attribute carries no literal ① bind of its own — the
    cross-check skips the bind at that position (DQ-D / R5).

    Matches the EXACT ``writeComputedMarker`` schema shape: a dict with exactly
    one key ``computed`` whose value is exactly ``"maxPlusOne"``. A multi-key
    dict or a different ``computed`` value is not a marker the schema accepts, so
    it is not treated as one here either (it binds as an ordinary literal ①).
    """
    return isinstance(value, dict) and len(value) == 1 and value.get("computed") == "maxPlusOne"


def _increment_marker(value: Any) -> Any:
    """The amount of a self-referential ``{ increment: <n> }`` marker, or None.

    The column is emitted as ``col = col + ?`` (e.g. a sequence registry's
    ``next_val``); the marker's integer is the value bound at that ``?``.

    Matches the EXACT ``writeComputedMarker`` schema shape: a dict with exactly
    one key ``increment`` whose value is a JSON ``integer``. A multi-key dict, a
    non-integer ``increment`` (a string, a float), or a JSON ``boolean`` (schema
    type ``boolean``, not ``integer`` — and Python's ``bool`` is an ``int``
    subclass, so it is excluded explicitly) is not a marker the schema accepts,
    so it returns ``None`` and the value binds as an ordinary literal ①.
    """
    if isinstance(value, dict) and len(value) == 1 and "increment" in value:
        amount = value["increment"]
        if isinstance(amount, int) and not isinstance(amount, bool):
            return amount
    return None


def _increment_or_value(value: Any) -> Any:
    """The bind an ① set value implies: an ``increment`` marker binds its amount."""
    increment = _increment_marker(value)
    return increment if increment is not None else value


def _document_columns(entity: Entity) -> set[str]:
    """The physical columns of *entity*'s value objects (m-value-object).

    A value-object column holds the WHOLE embedded composite as one document; its
    write value is ALWAYS literal document content (a JSON object / array / SQL
    NULL), NEVER a DB-computed marker. DB-computed marker interpretation
    (``computed`` / ``increment``) is gated on this set so the marker branch is only
    ever taken for a SCALAR ATTRIBUTE column — the role is resolved from the
    metamodel (``columnOrder(entity)`` position), not from the value's shape, so a
    marker-SHAPED document (``{computed: …}`` / ``{increment: n}``) still binds as
    one literal document.
    """
    return {value_object["column"] for value_object in entity.value_objects}


def _set_bind_value(column: str, value: Any, document_columns: set[str]) -> Any:
    """The bind a set-column's ① value implies, gated on the column's model role.

    A value-object (document) column ALWAYS binds its whole literal document
    (m-value-object), never a marker; a scalar attribute's self-referential
    ``{increment: n}`` marker binds its amount.
    """
    if column in document_columns:
        return value
    return _increment_or_value(value)


def _is_self_increment(statement: str, column: str) -> bool:
    """Whether *statement* assigns *column* as a self-referential ``col = col + ?``."""
    pattern = rf"\b{re.escape(column)}\s*=\s*{re.escape(column)}\s*\+\s*\?"
    return re.search(pattern, statement, re.IGNORECASE) is not None


def _classify_write_row(
    case: Case, entity: Entity, row: dict[str, Any]
) -> tuple[dict[str, Any], Any, dict[str, Any], Any]:
    """Classify a flat attribute-named ① row against *entity*'s metamodel.

    Mirrors the fixture loader's attribute→column resolution. Every key is either
    the reserved control key ``observedVersion``, an ENTITY ATTRIBUTE name, or a
    top-level VALUE-OBJECT name (a bad key raises :class:`CaseFailure`, so the
    neutral input can't silently name a non-member); the primary-key attribute's
    value is split into the pk, every other attribute AND every value object into
    the domain ``set`` — all keyed by physical column. A value object resolves to
    its single structured-document column and its value is the WHOLE document
    (m-value-object): it binds atomically as one document value in columnOrder
    position, never decomposed into path-level binds. Because that role is resolved
    HERE (from ``columnOrder(entity)``), a value-object column's value is ALWAYS
    literal document content downstream — never a DB-computed marker
    (``computed`` / ``increment``), even when the document is marker-SHAPED; marker
    interpretation applies only to a scalar-attribute column (see
    :func:`_document_columns`).
    """
    pk_columns = {a["column"] for a in entity.attributes if a.get("primaryKey")}
    columns: dict[str, Any] = {}
    set_columns: dict[str, Any] = {}
    pk_value: Any = None
    observed_version: Any = None
    for key, value in row.items():
        if key == "observedVersion":
            observed_version = value
            continue
        try:
            column = entity.attribute_by_name(key)["column"]
        except KeyError:
            # Not an attribute — a value object binds as ONE document in its
            # columnOrder position (m-value-object); the neutral input names it
            # like a scalar attribute and its value is the whole document.
            try:
                column = entity.value_object_by_name(key)["column"]
            except KeyError as exc:
                raise CaseFailure(
                    f"{case.path.name}: writeSequence row key {key!r} is not an attribute "
                    f"or value object of {entity.name} — the neutral write input speaks "
                    f"ATTRIBUTE / value-object names, not columns."
                ) from exc
        columns[column] = value
        if column in pk_columns:
            pk_value = value
        else:
            set_columns[column] = value
    return columns, pk_value, set_columns, observed_version


def _version_column(entity: Entity) -> str | None:
    """The physical column of an entity's explicit optimistic-lock version, or None.

    A VERSIONED entity carries an attribute-level ``optimisticLocking: true`` version
    (m-opt-lock); the value advance (``initial 1`` / ``observed + 1``) and gate are DERIVED,
    so the column never appears in the neutral write input (①). A temporal entity
    locks via its processing ``in_z`` timestamp and declares no such attribute.
    """
    for attribute in entity.attributes:
        if attribute.get("optimisticLocking"):
            return attribute["column"]
    return None


def _discriminator(entity: Entity) -> tuple[str, Any] | None:
    """The (column, value) a table-per-hierarchy INSERT writes, or None (m-inheritance).

    A TABLE-PER-HIERARCHY entity maps to a shared table discriminated by a
    ``discriminator`` column; the value THIS entity's rows carry is its
    ``discriminatorValue``. On a write that column is FRAMEWORK-DERIVED — set from the
    declared ``discriminatorValue``, never carried in the neutral write input (①),
    exactly as the version column's advance is derived. A TABLE-PER-LEAF entity has no
    shared table and no discriminator (``discriminatorValue`` is FORBIDDEN, m-inheritance),
    so this returns ``None`` and the leaf INSERT is an ordinary single-table write.
    """
    inheritance = entity.definition.get("inheritance")
    if not inheritance:
        return None
    discriminator = inheritance.get("discriminator")
    value = inheritance.get("discriminatorValue")
    if discriminator is None or value is None:
        return None
    return discriminator["column"], value


def _bytes_to_hex(value: Any) -> Any:
    """Render a ``bytes`` / ``memoryview`` value as lowercase hex text, else unchanged.

    The neutral write input (①) authors a ``bytes`` column as its wire form — a
    lowercase hex STRING (a ``bytes`` object is not a JSON type the write-row schema
    admits), while the golden bind carries the raw bytes (a ``!!binary`` tag). Both
    collapse to the same lowercase hex text here so ① ↔ golden cross-checking and
    table-state read-back compare a ``bytes`` column dialect-agnostically (the same
    hex form the TypeScript adapter's ``toWire`` produces).
    """
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


def _write_value_equal(left: Any, right: Any) -> bool:
    """Scalar equality for an ① value vs a golden bind, tolerant of date/bytes encoding.

    A date/timestamp authored QUOTED in ① (a string) must match the golden bind
    that PyYAML parsed from an UNQUOTED token into a ``date`` / ``datetime`` object;
    compare their ISO string forms once the exact-Decimal comparison declines. A
    ``bytes`` column is authored as a hex STRING in ① but as raw ``!!binary`` bytes
    in the golden bind, so both are normalized to lowercase hex first.
    """
    left = _bytes_to_hex(left)
    right = _bytes_to_hex(right)
    if _scalars_equal(left, right, None):
        return True
    return str(left) == str(right)


def _assert_write_values(
    case: Case, expected: list[Any], actual: list[Any], statement: str
) -> None:
    if len(expected) != len(actual):
        raise CaseFailure(
            f"{case.path.name}: the neutral write input supplies {len(expected)} write "
            f"value(s) but the golden binds carry {len(actual)} for {statement!r}."
        )
    for want, got in zip(expected, actual, strict=True):
        if not _write_value_equal(want, got):
            raise CaseFailure(
                f"{case.path.name}: neutral write input value {want!r} != golden bind "
                f"{got!r} for {statement!r}."
            )


def _parse_insert_columns(case: Case, statement: str) -> list[str]:
    match = _INSERT_COLUMNS_RE.search(statement)
    if not match:
        raise CaseFailure(
            f"{case.path.name}: could not parse the INSERT column list from golden {statement!r}."
        )
    return [column.strip() for column in match.group(1).split(",")]


def _parse_set_columns(case: Case, statement: str) -> list[str]:
    match = _SET_CLAUSE_RE.search(statement)
    if not match:
        raise CaseFailure(
            f"{case.path.name}: could not parse the SET clause from golden {statement!r}."
        )
    return [piece.strip().split("=")[0].strip() for piece in match.group(1).split(",")]


def _assert_write_input_columns(case: Case, dialect: str) -> None:
    """Cross-check each non-temporal write step's neutral input (①) against golden (②).

    The corpus is self-validating regardless of any adapter: a GENERATING adapter
    derives the emitted column list from ① (``rows``) classified against the model,
    so the harness asserts that same classification agrees with the authored golden.
    Per non-temporal write step the columns ① resolves to — in ``columnOrder``
    order, filtered to the present attributes — MUST equal the golden's INSERT / SET
    column list, and ①'s values MUST equal the write-value prefix of the golden
    binds. Comparing against the golden HERE is legitimate: the harness compares two
    AUTHORED representations, never grading its own generation.

    A TEMPORAL step is Family B: it ALWAYS writes the entity's full physical row, so
    the column list stays metamodel-sourced (``column_order``) and ① carries only the
    domain values (``rows``) plus the milestone instant — the transaction instant
    ``at`` (→ ``in_z``) for an audit-only entity, or ``businessAt`` (→ ``from_z``) for
    a business-only one — with the ``fromColumn = instant`` / ``toColumn = infinity``
    bookkeeping DERIVED, never authored (:func:`_assert_temporal_input`). A
    full-bitemporal ``*Until`` step is the rectangle-split analogue: its ① carries the
    valid-time window (``at`` / ``until`` / ``businessFrom``), cross-checked by
    :func:`_assert_until_input`. pk-gen ``rows`` carry DB-computed markers
    (``computed`` / ``increment``) whose bind is derived by the strategy, not authored.

    ① is REQUIRED on every writeSequence step (the permanent Family A + Family B
    contract, enforced in the schema), so there is no presence-tolerance here: a step
    without ``rows`` never reaches the gate. Family C — scenario write steps and
    boundary cases — carries no writeSequence, so it is exempt by construction.
    """
    statements = case.golden_statements(dialect)
    stmt_index = 0
    for step in case.write_sequence:
        count = step.get("statements", 1)
        rows = step.get("rows")
        entity = case.model.entity(step["entity"])
        if rows is None:
            raise CaseFailure(
                f"{case.path.name}: writeSequence step on {step['entity']} carries no "
                f"neutral write input (① `rows`) — required on every writeSequence step."
            )
        classified = [_classify_write_row(case, entity, row) for row in rows]
        step_statements = statements[stmt_index : stmt_index + count]
        step_binds = [case.statement_binds(stmt_index + offset) for offset in range(count)]
        mutation = step["mutation"]
        # A full-bitemporal step is a RECTANGLE SPLIT: the windowed `*Until` trio, or
        # a plain (unbounded) `update` / `terminate` on a two-axis entity (the everyday
        # business correction / termination, `m-bitemp-write-006` / `-007`). Both close
        # the original on the processing axis and chain head / (new-)tail milestones, so
        # both route through the rectangle-split cross-check — never the audit-only
        # close-and-open, which would mis-count the chained inserts.
        if mutation in _UNTIL_MUTATIONS or (
            _is_bitemporal(entity) and mutation in _PLAIN_SPLIT_MUTATIONS
        ):
            _assert_until_input(case, entity, classified, step, step_statements, step_binds)
        elif entity.is_temporal:
            _assert_temporal_input(case, entity, classified, step, step_statements, step_binds)
        elif mutation == "insert":
            _assert_insert_input(case, entity, classified, step_statements, step_binds)
        elif mutation in ("delete", "cascadeDelete"):
            _assert_delete_input(case, classified, step_binds)
        elif _version_column(entity) is not None:
            _assert_versioned_update_input(
                case, entity, case.concurrency_mode, classified, step_statements, step_binds
            )
        else:
            _assert_update_input(case, entity, classified, step_statements, step_binds)
        stmt_index += count


def _assert_insert_input(
    case: Case,
    entity: Entity,
    classified: list[tuple[dict[str, Any], Any, dict[str, Any], Any]],
    step_statements: list[str],
    step_binds: list[list[Any]],
) -> None:
    if not step_statements:
        return
    version_col = _version_column(entity)
    # A pk-gen `sequence` insert step emits one single-row INSERT per allocated id
    # (statements == rows); a set-based batched insert (m-batch-write-001) is one multi-row INSERT.
    per_row = len(step_statements) == len(classified) and len(step_statements) > 1
    if per_row:
        for cls, statement, binds in zip(classified, step_statements, step_binds, strict=True):
            _assert_insert_statement(case, entity, [cls], version_col, statement, binds)
        return
    _assert_insert_statement(
        case,
        entity,
        classified,
        version_col,
        step_statements[0],
        step_binds[0] if step_binds else [],
    )


def _assert_insert_statement(
    case: Case,
    entity: Entity,
    classified: list[tuple[dict[str, Any], Any, dict[str, Any], Any]],
    version_col: str | None,
    statement: str,
    binds: list[Any],
) -> None:
    golden_columns = _parse_insert_columns(case, statement)
    domain = [c for c in column_order(entity) if any(c in cols for cols, *_ in classified)]
    # A TABLE-PER-HIERARCHY insert writes the discriminator column from the entity's
    # discriminatorValue (m-inheritance) — a FRAMEWORK-DERIVED column, never carried in
    # ① — slotted at its columnOrder position, exactly as the version column is derived.
    discriminator = _discriminator(entity)
    if discriminator is not None and discriminator[0] in domain:
        raise CaseFailure(
            f"{case.path.name}: the neutral write input (①) carries the discriminator "
            f"column {discriminator[0]!r}, which a table-per-hierarchy write derives from "
            f"the entity's discriminatorValue (m-inheritance), never authored."
        )
    emitted = [
        c
        for c in column_order(entity)
        if c in domain or (discriminator is not None and c == discriminator[0])
    ]
    # A VERSIONED insert appends the framework-owned version column with the DERIVED
    # initial value `1` (never authored in ①, so it is not in the row's columns).
    present = [*emitted, version_col] if version_col is not None else emitted
    if golden_columns != present:
        raise CaseFailure(
            f"{case.path.name}: the golden INSERT column list {golden_columns} != the "
            f"columns the neutral write input resolves to {present} (columnOrder order, "
            f"present attributes"
            f"{' + derived discriminator' if discriminator is not None else ''}"
            f"{' + derived version' if version_col is not None else ''})."
        )
    # A DB-computed marker is a SCALAR-ATTRIBUTE-only interpretation (m-value-object):
    # a value-object (document) column ALWAYS binds its whole literal document in
    # columnOrder position, so it is excluded here even when the authored document is
    # marker-SHAPED (`{computed: …}`) — the role is resolved from the metamodel, never
    # from the value's shape.
    document_columns = _document_columns(entity)
    computed = [
        c
        for c in domain
        if c not in document_columns
        and any(_is_computed_marker(cols.get(c)) for cols, *_ in classified)
    ]
    if computed:
        # pk-gen `max`: a DB-COMPUTED column (`coalesce(max(id), ?) + ?`) contributes
        # the strategy's binds (coalesce base + increment), NOT an ① literal — its bind
        # is SKIPPED. The column still appears in the golden INSERT list (checked
        # above); the remaining LITERAL columns' values are the trailing binds.
        literal_columns = [c for c in domain if c not in computed]
        expected = [cols[column] for cols, *_ in classified for column in literal_columns]
        _assert_write_values(case, expected, binds[len(binds) - len(expected) :], statement)
        return
    expected: list[Any] = []
    for cols, *_ in classified:
        for column in emitted:
            if discriminator is not None and column == discriminator[0]:
                # The discriminator's bind is the entity's discriminatorValue, DERIVED
                # from the model (m-inheritance), never an ① literal.
                expected.append(discriminator[1])
            else:
                expected.append(cols[column])
        if version_col is not None:
            expected.append(1)  # derived initial version (m-opt-lock baseline), never authored
    _assert_write_values(case, expected, binds, statement)


def _assert_versioned_update_input(
    case: Case,
    entity: Entity,
    mode: str,
    classified: list[tuple[dict[str, Any], Any, dict[str, Any], Any]],
    step_statements: list[str],
    step_binds: list[list[Any]],
) -> None:
    """Cross-check a VERSIONED writeSequence update step's ① against its golden (②).

    The golden SET clause is the domain set columns + the framework-owned ``version``
    column (advanced ``observedVersion + 1``, DERIVED — never authored in ①). The
    binds are ``[…set values…, newVersion, pk]`` in the default LOCKING mode
    (``m-opt-lock-002`` / ``m-detach-002`` — the m-read-lock shared read lock makes
    the write correct, so no
    ``and version = ?`` gate) or ``[…, newVersion, pk, observedVersion]`` in
    optimistic mode. One golden statement per ① row.
    """
    version_col = _version_column(entity)
    for (_, pk, set_cols, observed), statement, binds in zip(
        classified, step_statements, step_binds, strict=True
    ):
        golden_set = _parse_set_columns(case, statement)
        set_present = [c for c in column_order(entity) if c in set_cols]
        expected_cols = [*set_present, version_col]
        if golden_set != expected_cols:
            raise CaseFailure(
                f"{case.path.name}: the golden versioned-UPDATE SET column list "
                f"{golden_set} != the domain set columns + version {expected_cols} the "
                f"neutral write input resolves to."
            )
        if observed is None:
            raise CaseFailure(
                f"{case.path.name}: a versioned update's neutral write input (①) MUST "
                f"carry observedVersion — the version advance is derived from it."
            )
        set_values = [set_cols[column] for column in set_present]
        expected = [*set_values, observed + 1, pk]
        if mode == "optimistic":
            expected.append(observed)  # the optimistic gate bind
        _assert_write_values(case, expected, binds, statement)


def _assert_update_input(
    case: Case,
    entity: Entity,
    classified: list[tuple[dict[str, Any], Any, dict[str, Any], Any]],
    step_statements: list[str],
    step_binds: list[list[Any]],
) -> None:
    set_present = [
        c for c in column_order(entity) if any(c in set_cols for _, _, set_cols, _ in classified)
    ]
    # Columns whose ① value is a self-referential `{ increment: <n> }` marker (a
    # sequence registry's `next_val`): the golden assigns `col = col + ?` and the bind
    # at that `?` is the increment amount, not a plain literal (DQ-D / R5). This is a
    # SCALAR-ATTRIBUTE-only interpretation (m-value-object): a value-object (document)
    # column ALWAYS binds its whole literal document, so a marker-SHAPED document
    # (`{increment: n}`) is never read as a self-advance — the role is resolved from
    # the metamodel, never from the value's shape.
    document_columns = _document_columns(entity)
    increment_columns = {
        column
        for _, _, set_cols, _ in classified
        for column in set_cols
        if column not in document_columns and _increment_marker(set_cols[column]) is not None
    }
    for statement in step_statements:
        golden_set = _parse_set_columns(case, statement)
        if golden_set != set_present:
            raise CaseFailure(
                f"{case.path.name}: the golden SET column list {golden_set} != the domain "
                f"columns the neutral write input resolves to {set_present}."
            )
        for column in increment_columns:
            if not _is_self_increment(statement, column):
                raise CaseFailure(
                    f"{case.path.name}: an `increment` ① on {column!r} requires the golden's "
                    f"self-referential `set {column} = {column} + ?` shape, not found in "
                    f"{statement!r}."
                )
    per_key = len(step_statements) == len(classified) and len(step_statements) > 1
    width = len(set_present)
    if per_key:
        for (_, _, set_cols, _), binds, statement in zip(
            classified, step_binds, step_statements, strict=True
        ):
            expected = [
                _set_bind_value(column, set_cols[column], document_columns)
                for column in set_present
            ]
            _assert_write_values(case, expected, binds[:width], statement)
        return
    first_set = classified[0][2] if classified else {}
    expected = [
        _set_bind_value(column, first_set[column], document_columns) for column in set_present
    ]
    binds = step_binds[0] if step_binds else []
    statement = step_statements[0] if step_statements else ""
    _assert_write_values(case, expected, binds[:width], statement)


def _assert_delete_input(
    case: Case,
    classified: list[tuple[dict[str, Any], Any, dict[str, Any], Any]],
    step_binds: list[list[Any]],
) -> None:
    # A delete / cascadeDelete row carries only the pk (the `where` key — no written
    # columns), so ① supplies no INSERT/SET column list to cross-check; assert the
    # pk value(s) appear in the DELETE binds.
    pk_values = [pk for _, pk, _, _ in classified]
    # A COLLAPSED set-based DELETE (m-batch-write-003) is ONE statement whose
    # `id in (…)` binds carry EVERY buffered pk. Cross-check that all of them appear
    # — a meaningful check for the collapse (a dropped/typo'd key is caught). The
    # per-statement path below (one statement per row: the FK-ordered m-unit-work-007
    # deletes, the versioned per-key m-batch-write-004 deletes, the dependent-cascade
    # m-cascade-delete-001 statements keyed on a same-valued FK) keeps the weaker
    # "this statement's binds carry SOME pk" check, since those bind a single key.
    collapsed = len(step_binds) == 1 and len(pk_values) > 1
    if collapsed:
        binds = step_binds[0]
        # A collapsed `id in (?, …)` binds EXACTLY the buffered pks, in ① order — the
        # same exact-bind discipline the insert/update input cross-checks apply. Require
        # positional bind equality against the pk list, rejecting a reordered, duplicated,
        # or extra bind (not the weaker "every pk appears somewhere", which tolerated all
        # three): the golden's binds MUST equal the pk list one-for-one and in order.
        if len(binds) != len(pk_values) or any(
            not _write_value_equal(pk, bind) for pk, bind in zip(pk_values, binds, strict=False)
        ):
            raise CaseFailure(
                f"{case.path.name}: the collapsed DELETE binds {binds} MUST equal the "
                f"neutral write input pk value(s) {pk_values} exactly and in order "
                f"(no reorder, duplicate, or extra bind)."
            )
        return
    for binds in step_binds:
        if not any(_write_value_equal(pk, bind) for pk in pk_values for bind in binds):
            raise CaseFailure(
                f"{case.path.name}: the neutral write input pk value(s) {pk_values} appear "
                f"in none of the DELETE binds {binds}."
            )


def _assert_temporal_input(
    case: Case,
    entity: Entity,
    classified: list[tuple[dict[str, Any], Any, dict[str, Any], Any]],
    step: dict[str, Any],
    step_statements: list[str],
    step_binds: list[list[Any]],
) -> None:
    """Cross-check a TEMPORAL (audit-only / business-only) write step's ① vs golden.

    A milestone-chaining write ALWAYS writes the entity's full physical row (DQ-B
    Family B), so the emitted column list is metamodel-sourced (``column_order``) —
    ① carries only the domain values (``rows``) plus the milestone instant. For an
    AUDIT-ONLY (processing) entity that instant is ``at`` (→ ``in_z``); for a
    BUSINESS-ONLY (unitemporal-business) entity it is ``businessAt`` (→ ``from_z``) —
    the same close-and-chain shape driven by business date rather than transaction
    instant. The bookkeeping ``fromColumn = instant`` and the open bound
    ``toColumn = infinity`` are DERIVED, never authored in ① (the m-temporal-read milestone
    discipline stays under test). The gate cross-checks, per statement: an ``insert``
    (open a milestone) writes the full physical row with ``fromColumn = instant`` and
    ``toColumn = infinity``; a close (``update`` step 1 / ``terminate``) binds
    ``[instant, pk, infinity]`` — sets ``toColumn = instant`` keyed on the still-open
    current row (``pk and toColumn = infinity``); an ``update`` chains a second
    full-row insert carrying the row's columns.
    """
    processing = next((a for a in entity.as_of_attributes if a["axis"] == "processing"), None)
    if processing is not None:
        axis, at, instant_key = processing, step.get("at"), "at"
    else:
        # A business-only (unitemporal-business) entity closes/chains on the BUSINESS
        # axis, driven by `businessAt` (→ from_z/thru_z) — the analogue of `at`.
        axis = next(a for a in entity.as_of_attributes if a["axis"] == "business")
        at, instant_key = step.get("businessAt"), "businessAt"
    in_z, out_z, infinity = axis["fromColumn"], axis["toColumn"], axis.get("infinity", "infinity")
    full_columns = list(column_order(entity))
    if at is None:
        raise CaseFailure(
            f"{case.path.name}: a temporal write step's neutral write input (①) MUST carry "
            f"`{instant_key}` (the milestone instant → {in_z}), which is DERIVED into the "
            f"milestone bookkeeping, never read from the golden."
        )
    columns, pk, _set_cols, _observed = classified[0] if classified else ({}, None, {}, None)

    def assert_open(statement: str, binds: list[Any]) -> None:
        golden_columns = _parse_insert_columns(case, statement)
        if golden_columns != full_columns:
            raise CaseFailure(
                f"{case.path.name}: the golden temporal INSERT column list {golden_columns} != "
                f"the entity's full physical row {full_columns} — a milestone always writes the "
                f"whole row (metamodel-sourced, not derived from ①)."
            )
        expected = [
            at if column == in_z else infinity if column == out_z else columns.get(column)
            for column in full_columns
        ]
        _assert_write_values(case, expected, binds, statement)

    def assert_close(statement: str, binds: list[Any]) -> None:
        # A close sets `out_z = at` keyed on the still-open current row
        # (`pk and out_z = infinity`) — no domain values, just the derived bounds.
        _assert_write_values(case, [at, pk, infinity], binds, statement)

    mutation = step["mutation"]
    if mutation == "insert":
        assert_open(step_statements[0], step_binds[0])
    elif mutation == "update":
        assert_close(step_statements[0], step_binds[0])
        assert_open(step_statements[1], step_binds[1])
    elif mutation == "terminate":
        assert_close(step_statements[0], step_binds[0])
    else:
        raise CaseFailure(
            f"{case.path.name}: unexpected temporal mutation {mutation!r} for a ① cross-check."
        )


def _assert_until_input(
    case: Case,
    entity: Entity,
    classified: list[tuple[dict[str, Any], Any, dict[str, Any], Any]],
    step: dict[str, Any],
    step_statements: list[str],
    step_binds: list[list[Any]],
) -> None:
    """Cross-check a full-bitemporal RECTANGLE-SPLIT step's ① against its golden (②).

    A rectangle-split write inactivates the original on the PROCESSING axis at the
    transaction instant and chains head / (middle) / (new-)tail rows at fresh
    processing time ``[at, infinity)``, partitioned on the BUSINESS axis around the
    mutation instant. Two forms share this cross-check:

      * a WINDOWED ``*Until`` write bounds the change to ``[businessFrom, until)``
        (`m-bitemp-write-001` / `-002` / `-003` / `-008`); ① carries both ``at`` and
        ``until``;
      * a PLAIN (unbounded) ``update`` / ``terminate`` corrects/ends the value from
        ``businessFrom`` ONWARD (`m-bitemp-write-006` / `-007`); ① carries ``at`` but
        no ``until`` — the residual window runs to the open bound (``thru_z``).

    Like the audit-only close it is Family B (full physical row, metamodel-sourced
    column list), so the cross-check is BINDS-only on the DERIVED coordinates ①
    supplies:

      * the inactivating close (the ``update … set out_z = ? where …`` statement)
        binds ``[at, pk, infinity]`` — closes the original at the transaction instant.
        A GATED close (`m-bitemp-write-008`, optimistic) additionally carries the
        observed rectangle's ``(from_z, in_z)`` as the trailing ``and from_z = ? and
        in_z = ?`` binds — drawn from the currently-open row (reconstructed by
        replaying prior insert steps, :func:`_open_rectangle_binds`), NOT the closing
        step's own ①, and DISTINCT from the window boundary; the gate rides the golden
        directly (no ``observedInZ`` token on the writeSequence step);
      * every chained INSERT opens a fresh processing milestone, so its ``in_z`` bind
        equals ``at`` and its ``out_z`` bind equals ``infinity``;
      * the business window bounds — ``businessFrom`` (the window start, an ① row
        attribute) and, for a windowed write, ``until`` (the window end, step-level) —
        appear among the chained inserts' business-axis (``from_z`` / ``thru_z``) binds.

    The domain values (carried, not derived) and the head/tail residual windows are
    graded observably by ``then.tableState`` in the run, not restated in ①.
    """
    business = next(a for a in entity.as_of_attributes if a["axis"] == "business")
    processing = next(a for a in entity.as_of_attributes if a["axis"] == "processing")
    from_z, thru_z = business["fromColumn"], business["toColumn"]
    in_z, out_z = processing["fromColumn"], processing["toColumn"]
    infinity = processing.get("infinity", "infinity")
    full_columns = list(column_order(entity))
    in_z_pos, out_z_pos = full_columns.index(in_z), full_columns.index(out_z)
    from_z_pos, thru_z_pos = full_columns.index(from_z), full_columns.index(thru_z)

    windowed = step["mutation"] in _UNTIL_MUTATIONS
    at = step.get("at")
    until = step.get("until")
    if at is None:
        raise CaseFailure(
            f"{case.path.name}: a bitemporal rectangle-split step's neutral write input "
            f"(①) MUST carry `at` (the transaction instant → in_z), which is DERIVED, "
            f"never read from the golden."
        )
    if windowed and until is None:
        raise CaseFailure(
            f"{case.path.name}: a `*Until` step's neutral write input (①) MUST carry "
            f"`until` (the business window end → thru_z), which is DERIVED, never read "
            f"from the golden."
        )
    columns, pk, _set_cols, _observed = classified[0] if classified else ({}, None, {}, None)
    business_from = columns.get(from_z)
    if business_from is None:
        raise CaseFailure(
            f"{case.path.name}: a bitemporal rectangle-split step's ① row MUST carry the "
            f"business window start (`businessFrom` → {from_z}), which discriminates the "
            f"chained rows."
        )

    business_binds: list[Any] = []
    for statement, binds in zip(step_statements, step_binds, strict=True):
        if "insert into" in statement.lower():
            # A chained milestone opens at fresh processing time [at, infinity).
            _assert_write_values(case, [at], [binds[in_z_pos]], statement)
            _assert_write_values(case, [infinity], [binds[out_z_pos]], statement)
            business_binds.extend([binds[from_z_pos], binds[thru_z_pos]])
        else:
            # The inactivating close: out_z = at, keyed on the current-on-processing row.
            # Whether the close is GATED (optimistic) is decided by the SQL SHAPE — it MUST
            # carry the observed rectangle's business + processing gate predicates
            # (`and from_z = ? and in_z = ?`) — NEVER merely by a longer bind row, so a
            # plain close with spurious trailing binds fails as a mismatch rather than being
            # tolerated as gated. A gated close then pairs those two predicates with EXACTLY
            # two trailing binds — the currently-open row's (from_z, in_z), reconstructed
            # from prior insert steps and DISTINCT from the window boundary.
            expected = [at, pk, infinity]
            gated = _has_temporal_gate(statement, from_z, in_z)
            if gated:
                open_rect = _open_rectangle_binds(case, entity, step, pk, from_z)
                if open_rect is None:
                    raise CaseFailure(
                        f"{case.path.name}: a gated bitemporal close carries the "
                        f"`and {from_z} = ? and {in_z} = ?` gate, but no prior insert step "
                        f"opens a rectangle for pk {pk!r} to draw the observed "
                        f"(from_z, in_z) from."
                    )
                expected = [*expected, *open_rect]
            placeholders = statement.count("?")
            if placeholders != len(expected) or len(binds) != len(expected):
                raise CaseFailure(
                    f"{case.path.name}: the {'gated' if gated else 'plain'} bitemporal close "
                    f"{statement!r} carries {placeholders} placeholder(s) and {len(binds)} "
                    f"bind(s), but its derived shape is {len(expected)} — a gated close MUST "
                    f"pair the `and {from_z} = ? and {in_z} = ?` gate with exactly two "
                    f"trailing (from_z, in_z) binds; a plain close carries only "
                    f"`[at, pk, infinity]`."
                )
            _assert_write_values(case, expected, binds, statement)

    bounds = [(business_from, "businessFrom")]
    if until is not None:
        bounds.append((until, "until"))
    for bound, label in bounds:
        if not any(_write_value_equal(bound, value) for value in business_binds):
            raise CaseFailure(
                f"{case.path.name}: the rectangle-split business window bound "
                f"{label}={bound!r} appears in none of the chained inserts' business-axis "
                f"binds {business_binds!r}."
            )


def _open_rectangle_binds(
    case: Case, entity: Entity, current_step: dict[str, Any], pk: Any, from_z: str
) -> tuple[Any, Any] | None:
    """Reconstruct the currently-open rectangle's ``(from_z, in_z)`` for a gated close.

    A gated bitemporal close (`m-bitemp-write-008`) gates on the observed rectangle's
    business-from and processing-from — neither present in the closing step's own ①
    row (the row carries the NEW value + window start, distinct from the observed
    ``from_z``). Replay the prior insert / insertUntil steps in the same write sequence
    and return the last-opened rectangle's ``(businessFrom → from_z, at → in_z)`` for
    ``pk``, so the trailing gate binds cross-check against the row they inactivate
    rather than being tolerated blind. Returns ``None`` when no prior step opens ``pk``.
    """
    reconstructed: tuple[Any, Any] | None = None
    for prior in case.write_sequence:
        if prior is current_step:
            break
        if prior.get("mutation") not in ("insert", "insertUntil"):
            continue
        for row in prior.get("rows", []):
            _, prior_pk, prior_set, _ = _classify_write_row(case, entity, row)
            if _write_value_equal(prior_pk, pk):
                reconstructed = (prior_set.get(from_z), prior.get("at"))
    return reconstructed


def _has_temporal_gate(statement: str, from_z: str, in_z: str) -> bool:
    """True when a bitemporal close's SQL carries the OPTIMISTIC gate predicates.

    A gated (optimistic) bitemporal close (`m-bitemp-write-008`) targets EXACTLY the
    observed rectangle, so its inactivating ``UPDATE``'s ``WHERE`` adds the business +
    processing discriminators — ``and <from_z> = ? and <in_z> = ?`` — beyond the plain
    ``and <out_z> = ?`` current-row key. BOTH predicates are required, matched
    word-bounded so ``out_z = ?`` is never mistaken for ``in_z = ?``; a plain close is
    then never mis-read as gated on the strength of a longer bind row alone.
    """
    return bool(
        re.search(rf"\b{re.escape(from_z)}\s*=\s*\?", statement)
        and re.search(rf"\b{re.escape(in_z)}\s*=\s*\?", statement)
    )


def _conflict_versioned_entity(case: Case) -> Entity | None:
    """The versioned entity a conflict case targets, or None (a temporal close).

    A versioned conflict (``m-opt-lock-005`` through ``m-opt-lock-009``) gates on a
    version column; a temporal / bitemporal close (``m-temporal-read-009`` through
    ``m-temporal-read-012`` / ``m-bitemp-write-004`` / ``m-bitemp-write-005``) has none
    and carries a different ① (see :func:`_assert_temporal_conflict_input`).
    """
    for entity in case.model.entities:
        if _version_column(entity) is not None:
            return entity
    return None


def _conflict_temporal_entity(case: Case) -> Entity | None:
    """The processing-axis TEMPORAL entity a conflict-close case targets, or None.

    A temporal / bitemporal conflict close (``m-temporal-read-009`` through
    ``m-temporal-read-012`` / ``m-bitemp-write-004`` / ``m-bitemp-write-005``) carries no
    version column; it locks via the observed processing-from (``in_z``),
    so the target is the first entity with a processing as-of axis.
    """
    for entity in case.model.entities:
        if any(a["axis"] == "processing" for a in entity.as_of_attributes):
            return entity
    return None


def _assert_conflict_input(case: Case, dialect: str) -> None:
    """Cross-check a conflict case's neutral input (① ``write``) against its golden.

    A VERSIONED conflict is intrinsically optimistic (R4) — always gated: the golden
    SET clause is the domain set columns + ``version`` (advanced ``observedVersion +
    1``), and the binds are ``[…set values…, newVersion, pk, observedVersion]`` (the
    trailing bind is the ``and version = ?`` gate). The single form reads a root
    ``write``; the retry form reads a ``write`` per attempt. A temporal-close
    conflict (no version column) carries a close-shaped ① instead, cross-checked by
    :func:`_assert_temporal_conflict_input`. Comparing against the golden is
    legitimate — two AUTHORED representations, never grading generated output.
    """
    entity = _conflict_versioned_entity(case)
    if entity is None:
        _assert_temporal_conflict_input(case, dialect)
        return
    version_col = _version_column(entity)
    if case.attempts:
        for index, attempt in enumerate(case.attempts):
            _assert_versioned_conflict_write(
                case,
                entity,
                version_col,
                attempt.get("write"),
                _attempt_statements(attempt, dialect),
                _entry_binds(attempt.get("statements"), 0),
                f"attempts[{index}].write",
            )
        return
    _assert_versioned_conflict_write(
        case,
        entity,
        version_col,
        case.write,
        case.golden_statements(dialect),
        case.statement_binds(0),
        "write",
    )


def _assert_versioned_conflict_write(
    case: Case,
    entity: Entity,
    version_col: str | None,
    write: dict[str, Any] | None,
    statements: list[str],
    binds: list[Any],
    pointer: str,
) -> None:
    if write is None:
        raise CaseFailure(
            f"{case.path.name}: a versioned conflict ({pointer}) carries no neutral write "
            f"input (① `write`) — required on every conflict sub-form."
        )
    if len(statements) != 1:
        raise CaseFailure(
            f"{case.path.name}: a versioned conflict ({pointer}) has exactly one golden "
            f"UPDATE, but {len(statements)} were listed."
        )
    statement = statements[0]
    _, pk, set_cols, observed = _classify_write_row(case, entity, write)
    golden_set = _parse_set_columns(case, statement)
    set_present = [c for c in column_order(entity) if c in set_cols]
    expected_cols = [*set_present, version_col]
    if golden_set != expected_cols:
        raise CaseFailure(
            f"{case.path.name}: the golden conflict SET column list {golden_set} != the "
            f"domain set columns + version {expected_cols} the neutral write input "
            f"({pointer}) resolves to."
        )
    if observed is None:
        raise CaseFailure(
            f"{case.path.name}: a versioned conflict's neutral write input ({pointer}) MUST "
            f"carry observedVersion — the advance + gate are derived from it."
        )
    set_values = [set_cols[column] for column in set_present]
    # A conflict is intrinsically gated (R4): [...set, newVersion, pk, observedVersion].
    expected = [*set_values, observed + 1, pk, observed]
    _assert_write_values(case, expected, binds, statement)


def _assert_temporal_conflict_input(case: Case, dialect: str) -> None:
    """Cross-check a TEMPORAL / bitemporal conflict CLOSE's ① against its golden (②).

    A processing-axis temporal entity carries no version column, so the close gates
    on the observed processing-from (``in_z``) — the version analogue (DQ-C). The
    close is Family B: it always writes the single metamodel-fixed SET column
    (``out_z``), so the cross-check is BINDS-only (OQ3 → Option A). ① carries the
    milestone pk (→ the ``where`` key), the close instant ``at`` (→ the new
    ``out_z``), and — in optimistic mode — ``observedInZ`` (the ``and in_z = ?``
    gate); a BITEMPORAL close additionally carries the business discriminator (e.g.
    ``businessFrom`` → the ``from_z = ?`` gate whose VALUE the metamodel cannot know).
    The single form reads root ``write`` / ``at`` / ``observedInZ``; the retry form
    reads them per attempt.
    """
    entity = _conflict_temporal_entity(case)
    if entity is None:
        return
    gated = case.concurrency_mode == "optimistic"
    if case.attempts:
        for index, attempt in enumerate(case.attempts):
            _assert_temporal_conflict_close(
                case,
                entity,
                attempt.get("write"),
                attempt.get("at"),
                attempt.get("observedInZ"),
                gated,
                _attempt_statements(attempt, dialect),
                _entry_binds(attempt.get("statements"), 0),
                f"attempts[{index}]",
            )
        return
    _assert_temporal_conflict_close(
        case,
        entity,
        case.write,
        case.at,
        case.observed_in_z,
        gated,
        case.golden_statements(dialect),
        case.statement_binds(0),
        "write",
    )


def _assert_temporal_conflict_close(
    case: Case,
    entity: Entity,
    write: dict[str, Any] | None,
    at: Any,
    observed_in_z: Any,
    gated: bool,
    statements: list[str],
    binds: list[Any],
    pointer: str,
) -> None:
    """Cross-check one temporal-close attempt's ① binds against the golden UPDATE.

    A close sets ``out_z = at`` keyed on the still-open current row
    (``pk and out_z = infinity``); an optimistic close adds the ``and in_z = ?`` gate
    bound to ``observedInZ``. A bitemporal close inserts the business discriminator's
    VALUE (the classified ``set`` coordinate, e.g. ``from_z``) between ``out_z`` and
    ``in_z`` in model column order, so the derived binds are
    ``[at, pk, infinity, …businessCoords, (observedInZ if gated)]``.
    """
    if write is None:
        raise CaseFailure(
            f"{case.path.name}: a temporal conflict close ({pointer}) carries no neutral "
            f"write input (① `write`) — required on every conflict sub-form."
        )
    if len(statements) != 1:
        raise CaseFailure(
            f"{case.path.name}: a temporal conflict close ({pointer}) has exactly one "
            f"golden UPDATE, but {len(statements)} were listed."
        )
    if at is None:
        raise CaseFailure(
            f"{case.path.name}: a temporal conflict close's neutral write input "
            f"({pointer}) MUST carry `at` (the close instant → out_z), which is DERIVED "
            f"into the close binds, never read from the golden."
        )
    axis = next(a for a in entity.as_of_attributes if a["axis"] == "processing")
    infinity = axis.get("infinity", "infinity")
    _, pk, set_cols, _ = _classify_write_row(case, entity, write)
    # A bitemporal close's business discriminator (e.g. from_z) slots between out_z
    # and in_z in model column order; a processing-only close has none.
    business_coords = [set_cols[column] for column in column_order(entity) if column in set_cols]
    expected = [at, pk, infinity, *business_coords]
    if gated:
        if observed_in_z is None:
            raise CaseFailure(
                f"{case.path.name}: an optimistic temporal conflict close's neutral write "
                f"input ({pointer}) MUST carry observedInZ — the `and in_z = ?` gate is "
                f"derived from it."
            )
        expected.append(observed_in_z)  # the optimistic in_z gate bind
    _assert_write_values(case, expected, binds, statements[0])


def _read_table(db: DatabaseProvider, entity: Entity) -> list[dict[str, Any]]:
    """Read the full state of *entity*'s table, projecting every column by name.

    A value-object column is decoded to a Python structure (m-value-object): Postgres
    returns its ``jsonb`` already parsed while MariaDB returns raw JSON text, so both
    dialects collapse to the same ``dict`` / ``list`` / ``None`` here — the shape a
    ``then.tableState`` document row is authored as, so the write-sequence comparison
    is dialect-agnostic.
    """
    columns = list(column_order(entity))
    projection = ", ".join(f"t0.{quote_identifier(column, db.dialect)}" for column in columns)
    rows = db.query(f"select {projection} from {quote_identifier(entity.table, db.dialect)} t0")
    document_columns = {value_object["column"] for value_object in entity.value_objects}
    # A `bytes` column reads back as raw driver bytes (Postgres ``memoryview`` /
    # MariaDB ``bytes``); render it to lowercase hex text so a write round-trip's
    # ``then.tableState`` compares dialect-agnostically to the authored hex string
    # (the same wire form the TypeScript adapter's ``toWire`` produces on read).
    bytes_columns = {
        attribute["column"] for attribute in entity.attributes if attribute.get("type") == "bytes"
    }
    for row in rows:
        for column in document_columns:
            if column in row:
                row[column] = _decode_document(row[column])
        for column in bytes_columns:
            if isinstance(row.get(column), (bytes, bytearray, memoryview)):
                row[column] = bytes(row[column]).hex()
    return rows


def _assert_write_sequence(case: Case, db: DatabaseProvider) -> None:
    """Apply the ordered DML golden SQL, then assert the resulting table state.

    This is the observable form of the milestone-chaining write contract (m-audit-write):
    rather than introspecting the implementation, we APPLY the documented golden
    DML in order and assert the rows it leaves behind — including the current-row
    state where the open bound ``to`` equals native ``infinity``.
    """
    dialect = db.dialect
    statements = case.golden_statements(dialect)

    for index, statement in enumerate(statements):
        binds = case.statement_binds(index)
        db.execute(statement, binds)

    expected = case.expected_table_state
    entity_by_table = {entity.table: entity for entity in case.model.entities}
    for table, expected_rows in expected.items():
        if table not in entity_by_table:
            raise CaseFailure(
                f"{case.path.name}: then.tableState names table {table!r} "
                f"which the model does not declare."
            )
        actual = _read_table(db, entity_by_table[table])
        if not _rows_equal(actual, expected_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: table {table!r} state after the write "
                f"sequence != then.tableState.\n"
                f"  actual:   {actual!r}\n"
                f"  expected: {expected_rows!r}"
            )


# --- scenarios (Phase 6, m-unit-work) ------------------------------------------------


def _step_statements(step: dict[str, Any], dialect: str) -> list[str]:
    """The ordered golden SQL statements a scenario step lists for *dialect*."""
    return _entry_statements(step.get("statements"), dialect)


def _scenario_has_golden(case: Case, dialect: str) -> bool:
    """True if any scenario step lists golden SQL for *dialect*."""
    return any(_step_statements(step, dialect) for step in case.scenario)


def _assert_scenario_normalization(case: Case, dialect: str) -> None:
    for index, step in enumerate(case.scenario):
        for sql in _step_statements(step, dialect):
            canonical = normalize(sql, dialect)
            if canonical != sql:
                raise CaseFailure(
                    f"{case.path.name}: when.scenario[{index}].statements ({dialect}) is "
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

    Scenario cases query a single entity (cache / identity over one type), so the
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
        pairs = _entry_pairs(step.get("statements"), dialect)
        if "write" in step:
            if step.get("rollback"):
                # An ABORTED write (m-unit-work abort contract): apply each DML statement
                # inside a manual-commit session, then ROLL BACK. The write lands
                # in the atomic scope the abort discards, so a later find MUST
                # re-resolve and observe the ORIGINAL rows, never the aborted write.
                with db.open_session() as session:
                    executed: list[tuple[str, int]] = []
                    for statement, stmt_binds in pairs:
                        executed.append((statement, session.execute(statement, stmt_binds)))
                    # A scenario that declares `then.affectedRows` is a conflict-abort
                    # case (m-opt-lock + m-unit-work): the UoW aborts BECAUSE a
                    # version-gated write conflicted. Assert the conflict was actually
                    # DETECTED (the gated write affected `then.affectedRows` rows —
                    # `updatedRows != 1`) BEFORE rolling back, so a rollback that merely
                    # discarded a NON-conflicting write fails the case rather than
                    # passing on a vacuous abort.
                    if case.expected_affected_rows is not None:
                        _assert_scenario_conflict_abort(case, index, executed)
                    session.rollback()
            else:
                # A committed write between finds (read-your-own-writes / cache
                # invalidation): apply and COMMIT each DML statement on the unit of
                # work's connection. It captures no rows; a later find observes the
                # committed state.
                for statement, stmt_binds in pairs:
                    db.execute(statement, stmt_binds)
            # The step's index still occupies a slot so `sameObjectAs` references
            # stay aligned.
            results.append([])
            continue
        if pairs:
            # A DB-touching step: m-unit-work finds are single-statement, so the round-trip
            # count is one; execute it and capture the rows.
            statement, stmt_binds = pairs[0]
            rows = _query_rows(db, statement, stmt_binds)
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


def _has_version_gate(statement: str, version_col: str) -> bool:
    """True when a versioned write's WHERE clause gates on the optimistic version.

    The optimistic golden write appends ``and <version> = ?`` to its keyed predicate
    (m-opt-lock). The version column also appears in an ``UPDATE``'s SET clause, so the
    gate is matched only in the WHERE clause (after the final ` where `), word-bounded
    so a longer column ending in the version name is never mistaken for the gate.
    """
    lowered = statement.lower()
    where_at = lowered.rfind(" where ")
    if where_at == -1:
        return False
    where_clause = lowered[where_at + len(" where ") :]
    return bool(re.search(rf"\b{re.escape(version_col.lower())}\s*=\s*\?", where_clause))


def _assert_scenario_conflict_abort(
    case: Case,
    index: int,
    executed: list[tuple[str, int]],
) -> None:
    """Assert an aborted scenario step aborted BECAUSE a versioned write conflicted.

    A scenario that declares ``then.affectedRows`` (the m-opt-lock conflict signal) is
    a conflict-abort case (m-opt-lock + m-unit-work): the rollback must be the
    CONSEQUENCE of a genuinely detected optimistic-lock conflict, not a vacuous abort.
    The step's version-gated write (identified by its ``and <version> = ?`` gate) MUST
    have affected ``then.affectedRows`` rows — ``0`` for a stale-version gate that
    matched no row (``updatedRows != 1``). A gated write that unexpectedly affects 1
    row is NO conflict, so the case fails rather than passing on the rollback alone.
    """
    expected = case.expected_affected_rows
    if case.concurrency_mode != "optimistic":
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] declares then.affectedRows (an "
            f"optimistic-lock conflict) but the unit of work is not "
            f"`concurrency: optimistic` — a conflict abort requires the version gate."
        )
    if expected == 1:
        raise CaseFailure(
            f"{case.path.name}: then.affectedRows is 1, which is NOT a conflict — "
            f"`updatedRows != 1` is the conflict signal. A conflict-abort scenario MUST "
            f"declare a != 1 count (0 for a stale-version gate)."
        )
    version_col = _version_column(_scenario_root_entity(case))
    if version_col is None:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] declares a conflict abort but the "
            f"entity carries no optimistic-lock version column to gate on."
        )
    gated = [(sql, affected) for sql, affected in executed if _has_version_gate(sql, version_col)]
    if len(gated) != 1:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] conflict-abort step MUST list exactly "
            f"one version-gated write (the conflicting statement), found {len(gated)}."
        )
    _sql, affected = gated[0]
    if affected != expected:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] gated versioned write affected "
            f"{affected} row(s) but then.affectedRows is {expected}. The UoW abort MUST "
            f"be a CONSEQUENCE of a detected optimistic-lock conflict "
            f"(`updatedRows != 1`); a gated write affecting 1 row is NO conflict."
        )


def _identity_keys(
    case: Case,
    index: int,
    rows: list[dict[str, Any]],
    identity_col: str,
    label: str = "scenario",
) -> list[Any]:
    """The ordered set of primary-key identities carried by *rows*."""
    if any(identity_col not in row for row in rows):
        raise CaseFailure(
            f"{case.path.name}: {label}[{index}] result rows do not carry the "
            f"identity column {identity_col!r}; a {label} step's find MUST project "
            f"the primary key so identity can be checked."
        )
    return sorted(_coerce_identity_key(row[identity_col]) for row in rows)


# --- conflict cases (Phase 7, m-opt-lock optimistic locking) -----------------------


def _assert_conflict(case: Case, db: DatabaseProvider) -> None:
    """Run the given.apply + golden UPDATE, assert the affected-row count.

    This is the observable form of optimistic-lock conflict detection (m-opt-lock).
    The model's fixtures are loaded (the row exists with its current version),
    then an OPTIONAL out-of-band ``given.apply`` simulates a concurrent
    transaction mutating the row (e.g. bumping the version). The golden
    ``UPDATE … where pk = ? and version = ?`` is then applied with the version
    the caller read EARLIER; if a concurrent write changed the version, the
    stale-version predicate matches **zero** rows — the conflict signal
    (``updatedRows != 1``). A fresh version matches exactly **one** row.

    The harness asserts the affected-row count equals ``affectedRows``,
    and (when authored) the resulting table state — so the contract is proven
    against real data, not merely asserted in prose.
    """
    dialect = db.dialect
    statements = case.golden_statements(dialect)
    if len(statements) != 1:
        raise CaseFailure(
            f"{case.path.name}: a conflict case has exactly one golden UPDATE "
            f"statement, but then.statements ({dialect}) lists {len(statements)}."
        )

    # Apply any out-of-band given.apply setup (a concurrent mutation) before the UPDATE.
    for entry in case.apply:
        db.execute(entry["sql"], list(entry.get("binds", [])))

    affected = db.execute(statements[0], case.statement_binds(0))
    expected = case.expected_affected_rows
    if affected != expected:
        raise CaseFailure(
            f"{case.path.name}: golden UPDATE affected {affected} row(s) but "
            f"affectedRows is {expected}. A stale optimistic-lock version "
            f"MUST affect 0 rows (conflict); a fresh version MUST affect 1."
        )

    if case.expected_table_state:
        entity_by_table = {entity.table: entity for entity in case.model.entities}
        for table, expected_rows in case.expected_table_state.items():
            if table not in entity_by_table:
                raise CaseFailure(
                    f"{case.path.name}: then.tableState names table {table!r} "
                    f"which the model does not declare."
                )
            actual = _read_table(db, entity_by_table[table])
            if not _rows_equal(actual, expected_rows, case.tolerance):
                raise CaseFailure(
                    f"{case.path.name}: table {table!r} state after the conflict "
                    f"case != then.tableState.\n"
                    f"  actual:   {actual!r}\n"
                    f"  expected: {expected_rows!r}"
                )


# --- conflict RETRY cases (m-opt-lock retry contract) ------------------------------


def _attempt_statements(attempt: dict[str, Any], dialect: str) -> list[str]:
    """The golden UPDATE statement(s) a retry attempt lists for *dialect*."""
    return _entry_statements(attempt.get("statements"), dialect)


def _conflict_retry_has_golden(case: Case, dialect: str) -> bool:
    """True if any retry attempt lists golden SQL for *dialect*."""
    return any(_attempt_statements(attempt, dialect) for attempt in case.attempts)


def _assert_conflict_retry_normalization(case: Case, dialect: str) -> None:
    for index, attempt in enumerate(case.attempts):
        for sql in _attempt_statements(attempt, dialect):
            canonical = normalize(sql, dialect)
            if canonical != sql:
                raise CaseFailure(
                    f"{case.path.name}: when.attempts[{index}].statements ({dialect}) is "
                    f"not canonical.\n"
                    f"  stored:     {sql!r}\n"
                    f"  normalized: {canonical!r}"
                )


def _assert_conflict_retry(case: Case, db: DatabaseProvider) -> None:
    """Run the given.apply + ordered retry attempts, asserting each affected count.

    This is the observable form of the m-opt-lock RETRY contract (Phase 7). The model's
    fixtures are loaded (the versioned row exists), an OPTIONAL out-of-band
    ``given.apply`` simulates a concurrent writer that advanced the version, then
    each attempt's golden ``UPDATE`` is applied in order. The first attempt gates
    on the STALE version the caller read before detaching/reading, so it affects
    ZERO rows (the ``updatedRows != 1`` conflict signal); the retry re-reads the
    now-fresh version and re-applies, affecting exactly ONE row. The harness
    asserts every attempt's affected-row count and (when authored) the final table
    state, proving the conflict was detected AND the retry closed the loop against
    real data.
    """
    dialect = db.dialect

    for entry in case.apply:
        db.execute(entry["sql"], list(entry.get("binds", [])))

    for index, attempt in enumerate(case.attempts):
        statements = _attempt_statements(attempt, dialect)
        if len(statements) != 1:
            raise CaseFailure(
                f"{case.path.name}: attempts[{index}] must list exactly one golden "
                f"UPDATE for {dialect}, found {len(statements)}."
            )
        affected = db.execute(statements[0], _entry_binds(attempt.get("statements"), 0))
        expected = attempt["affectedRows"]
        if affected != expected:
            raise CaseFailure(
                f"{case.path.name}: attempts[{index}] UPDATE affected {affected} "
                f"row(s) but affectedRows is {expected}. A stale version "
                f"MUST affect 0 rows (conflict); the fresh-version retry MUST "
                f"affect 1."
            )

    _assert_table_state(case, db)


def _assert_table_state(case: Case, db: DatabaseProvider) -> None:
    """Assert each table named in ``then.tableState`` matches (order-insensitive)."""
    if not case.expected_table_state:
        return
    entity_by_table = {entity.table: entity for entity in case.model.entities}
    for table, expected_rows in case.expected_table_state.items():
        if table not in entity_by_table:
            raise CaseFailure(
                f"{case.path.name}: then.tableState names table {table!r} "
                f"which the model does not declare."
            )
        actual = _read_table(db, entity_by_table[table])
        if not _rows_equal(actual, expected_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: table {table!r} state != then.tableState.\n"
                f"  actual:   {actual!r}\n"
                f"  expected: {expected_rows!r}"
            )


# --- error-code classification cases (m-db-error dialect seam) ----------------------


def _error_statements(case: Case, dialect: str) -> list[str]:
    """Every golden statement an error case lists for *dialect* (for lint/layer 3).

    Single-connection: the ordered top-level ``then.statements``. Two-connection:
    each node's per-round step ``statements``, in round/node order.
    """
    if case.concurrency is None:
        return case.golden_statements(dialect) if dialect in case.golden_dialects else []
    statements: list[str] = []
    for rnd in case.concurrency["rounds"]:
        for node in ("A", "B"):
            step = rnd.get(node)
            if isinstance(step, dict):
                statements.extend(_entry_statements(step.get("statements"), dialect))
    return statements


def _error_has_golden(case: Case, dialect: str) -> bool:
    return bool(_error_statements(case, dialect))


def _assert_error_normalization(case: Case, dialect: str) -> None:
    for statement in _error_statements(case, dialect):
        canonical = normalize(statement, dialect)
        if canonical != statement:
            raise CaseFailure(
                f"{case.path.name}: error-case statements ({dialect}) is not canonical.\n"
                f"  stored:     {statement!r}\n"
                f"  normalized: {canonical!r}"
            )


def _assert_error_classification(case: Case, db: DatabaseProvider) -> None:
    if case.concurrency is not None:
        _assert_error_concurrency(case, db)  # Task 8
    else:
        _assert_error_single_connection(case, db)


def _assert_error_single_connection(case: Case, db: DatabaseProvider) -> None:
    """Run ordered golden DML; every statement but the last MUST succeed, the
    last MUST raise, and the raised error MUST classify to errorClass."""
    _provision(case, db) if case.load_fixtures else _provision_empty(case, db)
    statements = case.golden_statements(db.dialect)
    last = len(statements) - 1
    raised: Exception | None = None
    for index, statement in enumerate(statements):
        binds = case.statement_binds(index)
        try:
            db.execute(statement, binds)
        except Exception as exc:  # noqa: BLE001 -- any driver error is the signal
            if index != last:
                raise CaseFailure(
                    f"{case.path.name}: setup statement[{index}] raised before the trigger: {exc!r}"
                ) from exc
            raised = exc
    if raised is None:
        raise CaseFailure(
            f"{case.path.name}: expected the final statement to raise "
            f"{case.error_class!r}, but no error was raised"
        )
    _assert_classified(case, db, raised)


def _assert_classified(case: Case, db: DatabaseProvider, exc: Exception) -> None:
    """Assert the raised error's neutral category, native code, and the call-site
    predicate partition (so the harness exercises the interface, not a shortcut)."""
    dialect = db.dialect
    category = db.classify_error(exc)
    if category != case.error_class:
        raise CaseFailure(
            f"{case.path.name}: error classified as {category!r} on {dialect}, "
            f"expected {case.error_class!r} (native code "
            f"{db.native_error_code(exc)!r}; exc {exc!r})"
        )
    expected_code = case.expected_native_code.get(dialect)
    actual_code = db.native_error_code(exc)
    if str(actual_code) != str(expected_code):
        raise CaseFailure(
            f"{case.path.name}: native code on {dialect} was {actual_code!r}, "
            f"expected {expected_code!r}"
        )
    # The call-site predicate interface: exactly the one predicate for this
    # category is true; the others false. Proves the partition language impls rely
    # on, not just the category string.
    truthy = {
        "is_retriable": errors.is_retriable(category),
        "violates_unique_index": errors.violates_unique_index(category),
        "is_timed_out": errors.is_timed_out(category),
    }
    expected_true = errors.predicate_for(category)
    for name, value in truthy.items():
        if value != (name == expected_true):
            raise CaseFailure(
                f"{case.path.name}: predicate {name} was {value} for category "
                f"{category!r}; expected only {expected_true!r} true"
            )


def _assert_error_concurrency(case: Case, db: DatabaseProvider) -> None:
    """Two-node, barrier-synchronized contention (deadlock / lock timeout / serialization).

    Each node (A, B) runs on its own thread over its own non-autocommit session.
    A threading.Barrier separates rounds so round k completes for both nodes
    before round k+1 begins -- guaranteeing both first locks/reads are established
    before the contention round. In that round both statements block; the DB
    resolves the contention (deadlock victim, or lock-wait timeout) and one
    statement raises. A thread that catches an error ROLLS BACK immediately
    (releasing its locks so the peer can proceed) then meets the barrier.

    A **serialization-failure** case (Postgres SQLSTATE ``40001``) is a different
    mechanism: there is NO lock contention -- under SERIALIZABLE both transactions
    read one row and write ANOTHER (a read/write dependency cycle), so nothing
    blocks and nothing raises mid-round. The dangerous structure surfaces only at
    COMMIT, so this runner switches into a serialization mode (keyed off the
    expected ``40001`` native code): each node runs its transaction at SERIALIZABLE
    (an isolation SET the harness issues, NOT authored golden SQL) and, after the
    rounds, the runner COMMITS each still-open transaction and captures the SSI
    abort raised on the victim. This is orthogonal to the deadlock / lock-timeout
    cases, which never enter serialization mode and behave exactly as before.

    The single raised error is classified. Sessions are rolled back + closed in a
    finally.
    """
    dialect = db.dialect
    concurrency = case.concurrency
    if concurrency is None:
        raise CaseFailure(f"{case.path.name}: error case missing concurrency choreography")
    rounds = concurrency["rounds"]
    nodes = ("A", "B")
    barrier = threading.Barrier(len(nodes))
    raised: dict[str, Exception] = {}
    # A serialization-failure case declares Postgres SQLSTATE 40001; it needs
    # SERIALIZABLE isolation + a commit phase (the SSI abort is a commit-time event).
    # Every other error/concurrency case (deadlock 40P01, lock-wait 55P03) leaves this
    # False and keeps the original mid-round-raise-only behavior untouched.
    serialization = str(case.expected_native_code.get(dialect)) == "40001"

    _provision(case, db)  # given.fixtures seeds the lockable Gauge rows

    def run_node(node: str, session: Any) -> None:
        errored = False
        if serialization:
            # A read/write dependency cycle is only a *conflict* under SERIALIZABLE;
            # set it as the first statement of the transaction (before any read).
            session.execute("set transaction isolation level serializable")
        for rnd in rounds:
            step = rnd.get(node)
            pairs = _entry_pairs(step.get("statements"), dialect) if isinstance(step, dict) else []
            if pairs:
                try:
                    for sql, binds in pairs:
                        session.execute(sql, binds)
                except Exception as exc:  # noqa: BLE001 -- the contention signal
                    raised[node] = exc
                    errored = True
                    with contextlib.suppress(Exception):
                        session.rollback()  # release locks so the peer unblocks
            try:
                barrier.wait(timeout=30)
            except threading.BrokenBarrierError:
                return
        # Serialization mode: the dangerous read/write cycle surfaces at COMMIT, not
        # mid-round. Commit each still-open transaction; the SSI monitor aborts one
        # with 40001, which this captures as the contention signal (the peer commits
        # cleanly). The barrier above guarantees BOTH transactions finished their
        # reads + writes before either commits, so the cycle is complete.
        if serialization and not errored:
            try:
                session.commit()
            except Exception as exc:  # noqa: BLE001 -- the serialization-failure signal
                raised[node] = exc
                with contextlib.suppress(Exception):
                    session.rollback()

    with contextlib.ExitStack() as stack:
        sessions = {node: stack.enter_context(db.open_session()) for node in nodes}
        threads = [
            threading.Thread(target=run_node, args=(node, sessions[node]), daemon=True)
            for node in nodes
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        # Roll back any session that did not error (releases held locks) before
        # the ExitStack closes them.
        for session in sessions.values():
            with contextlib.suppress(Exception):
                session.rollback()

    if not raised:
        raise CaseFailure(
            f"{case.path.name}: expected a {case.error_class!r} error from the "
            f"contention round, but none was raised on {dialect}"
        )
    if len(raised) > 1:
        raise CaseFailure(
            f"{case.path.name}: expected exactly one contention error, got "
            f"{len(raised)} ({list(raised)}): {raised}"
        )
    _assert_classified(case, db, next(iter(raised.values())))


# --- concurrency-success cases (m-read-lock behavioral read-lock) ---------------------


def _concurrency_statements(case: Case, dialect: str) -> list[str]:
    """Every golden statement a concurrency case lists for *dialect*, in round/A/B
    order (shared by the error/concurrency and concurrency-success shapes)."""
    statements: list[str] = []
    concurrency = case.concurrency or {}
    for rnd in concurrency.get("rounds", []):
        for node in ("A", "B"):
            step = rnd.get(node)
            if isinstance(step, dict):
                statements.extend(_entry_statements(step.get("statements"), dialect))
    return statements


def _concurrency_has_golden(case: Case, dialect: str) -> bool:
    return bool(_concurrency_statements(case, dialect))


def _assert_concurrency_success_step_kinds(case: Case) -> None:
    """Guard: every present step of a concurrency-success case MUST declare a valid
    ``kind`` (``"read"`` or ``"write"``), and a ``read`` step MUST carry ``expectRows``.

    ``kind`` is the EXPLICIT read-vs-write discriminator :func:`_assert_concurrency_success`
    branches on -- replacing the brittle SQL-verb sniffing that could misclassify a write
    CTE or a novel read form. Database-free and timing-independent, run pre-flight before
    any round executes: a step missing/with an unknown kind would mis-dispatch (a read
    graded as an execute-only write, its rows never proven), so the runner fails fast,
    naming the offending ``/concurrency/rounds/{i}/{node}`` pointer. The schema enforces
    both rules structurally (the success branch requires ``kind``; the ``kind`` if/then
    requires ``expectRows`` on a read); this re-check is defense-in-depth.
    """
    concurrency = case.concurrency or {}
    for index, rnd in enumerate(concurrency.get("rounds", [])):
        for node in ("A", "B"):
            step = rnd.get(node)
            if step is None:
                continue
            kind = step.get("kind")
            if kind not in ("read", "write"):
                raise CaseFailure(
                    f"{case.path.name}: /concurrency/rounds/{index}/{node}: a concurrency-"
                    f"success step must declare kind: 'read' | 'write' (the explicit read-"
                    f"vs-write discriminator); got {kind!r}"
                )
            if kind == "read" and step.get("expectRows") is None:
                raise CaseFailure(
                    f"{case.path.name}: /concurrency/rounds/{index}/{node}: a kind: read "
                    f"step must declare expectRows (its rows are graded on the held session)"
                )


def _assert_concurrency_normalization(case: Case, dialect: str) -> None:
    for statement in _concurrency_statements(case, dialect):
        canonical = normalize(statement, dialect)
        if canonical != statement:
            raise CaseFailure(
                f"{case.path.name}: concurrency statements ({dialect}) is not canonical.\n"
                f"  stored:     {statement!r}\n"
                f"  normalized: {canonical!r}"
            )


def _assert_concurrency_success(case: Case, db: DatabaseProvider) -> None:
    """Two-node, barrier-synchronized rounds that assert NO error and each read's rows.

    The non-error counterpart of :func:`_assert_error_concurrency`, reusing the same
    barrier + two ``open_session`` plumbing: ``m-read-lock-007`` (both readers take the shared
    lock and BOTH succeed -- shared, not exclusive) and ``m-read-lock-008`` (A holds an UNLOCKED
    projection, B's UPDATE is admitted -- no lock to block it). Each node runs its
    round steps on its own held non-autocommit session; a ``kind: read`` step is
    fetched on that HELD session (``session.query`` -- inside the open transaction, so
    a locking SELECT both takes the lock and returns its rows) and its ``expectRows``
    compared via the order-insensitive :func:`_rows_equal`, while a ``kind: write``
    step asserts only that it did not block/raise. Success is exactly "NO node raised
    and every ``expectRows`` matched". Sessions are rolled back + closed in a finally
    (releasing any lock a held read took).
    """
    dialect = db.dialect
    tolerance = case.tolerance
    concurrency = case.concurrency
    if concurrency is None:
        raise CaseFailure(f"{case.path.name}: concurrency-success case missing concurrency")
    rounds = concurrency["rounds"]
    nodes = ("A", "B")
    barrier = threading.Barrier(len(nodes))
    raised: dict[str, Exception] = {}
    row_failures: list[str] = []

    _provision(case, db)  # given.fixtures seeds the Account rows the reads observe

    def run_node(node: str, session: Any) -> None:
        for rnd in rounds:
            step = rnd.get(node)
            pairs = _entry_pairs(step.get("statements"), dialect) if isinstance(step, dict) else []
            if pairs:
                try:
                    if step.get("kind") == "read":
                        # A read step: fetch on the HELD session (a shared-lock SELECT
                        # takes its lock here) and compare the observed rows.
                        rows: list[dict[str, Any]] = []
                        for sql, binds in pairs:
                            rows = session.query(sql, binds)
                        expect = step.get("expectRows") or []
                        if not _rows_equal(rows, expect, tolerance):
                            row_failures.append(
                                f"node {node} observed rows != expectRows.\n"
                                f"  observed: {rows!r}\n"
                                f"  expected: {expect!r}"
                            )
                    else:
                        # A write step (kind: write): succeeds iff no lock blocks it
                        # (m-read-lock-008's admitted UPDATE); it holds until the finally
                        # rolls it back.
                        for sql, binds in pairs:
                            session.execute(sql, binds)
                except Exception as exc:  # noqa: BLE001 -- any raise fails the "no error" claim
                    raised[node] = exc
                    with contextlib.suppress(Exception):
                        session.rollback()  # release any lock so the peer can proceed
            try:
                barrier.wait(timeout=30)
            except threading.BrokenBarrierError:
                return

    with contextlib.ExitStack() as stack:
        sessions = {node: stack.enter_context(db.open_session()) for node in nodes}
        threads = [
            threading.Thread(target=run_node, args=(node, sessions[node]), daemon=True)
            for node in nodes
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        # Roll back both held sessions (releasing any shared read lock / uncommitted
        # write) before the ExitStack closes them.
        for session in sessions.values():
            with contextlib.suppress(Exception):
                session.rollback()

    if raised:
        raise CaseFailure(
            f"{case.path.name}: expected NO error on {dialect} (the lock is shared / "
            f"absent), but node(s) {sorted(raised)} raised: {raised}"
        )
    if row_failures:
        raise CaseFailure(f"{case.path.name}: " + "\n".join(row_failures))


# --- coherence cases (Phase 11, cross-process cache coherence) ---------------


def _coherence_step_statements(step: dict[str, Any], dialect: str) -> list[str]:
    """The ordered golden SQL statements a coherence step lists for *dialect*."""
    return _entry_statements(step.get("statements"), dialect)


def _coherence_has_golden(case: Case, dialect: str) -> bool:
    """True if any coherence step lists golden SQL for *dialect*."""
    return any(_coherence_step_statements(step, dialect) for step in case.coherence)


def _assert_coherence_normalization(case: Case, dialect: str) -> None:
    for index, step in enumerate(case.coherence):
        for sql in _coherence_step_statements(step, dialect):
            canonical = normalize(sql, dialect)
            if canonical != sql:
                raise CaseFailure(
                    f"{case.path.name}: when.coherence[{index}].statements ({dialect}) is "
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
    state, never the stale pre-write rows. A read step MAY additionally declare
    ``sameObjectAs`` — that its observed object is the SAME logical object (same
    primary-key identity) as an earlier step, the cross-process lift of the m-process-cache
    identity contract: the refresh updates the interned object in place rather than
    forking a second object for the same primary key.

    The harness contains no cache and no notification bus; it proves the suite's
    post-write golden SQL is correct against real, committed, cross-connection
    data — the observable contract any conforming invalidation mechanism satisfies.
    """
    dialect = db.dialect
    tolerance = case.tolerance
    default_identity = _pk_column(case.model.root_entity)

    _provision(case, db)  # fixtures loaded so the seed read sees a row
    with db.open_peer() as peer:
        nodes: dict[str, Any] = {"A": db, "B": peer}
        results: list[list[dict[str, Any]]] = []
        for index, step in enumerate(case.coherence):
            node = nodes[step["node"]]
            pairs = _entry_pairs(step.get("statements"), dialect)
            if step["kind"] == "write":
                for statement, binds in pairs:
                    node.execute(statement, binds)
                results.append([])  # keep indices aligned for sameObjectAs
                continue

            # A read step: execute its SELECT on its node and (when declared)
            # assert the rows it observes.
            if not pairs:
                raise CaseFailure(
                    f"{case.path.name}: coherence[{index}] is a read step but "
                    f"lists no golden SQL for {dialect}."
                )
            rows: list[dict[str, Any]] = []
            for statement, binds in pairs:
                rows = _query_rows(node, statement, binds)
            results.append(rows)

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

            if "sameObjectAs" in step:
                _assert_coherence_identity(case, index, step, results, default_identity)


def _assert_coherence_identity(
    case: Case,
    index: int,
    step: dict[str, Any],
    results: list[list[dict[str, Any]]],
    default_identity: str,
) -> None:
    """Assert this read step denotes the SAME logical object as an earlier step.

    Identity preservation across the cross-process refresh: node B's re-fetch
    resolves the same primary-key identity it interned on the seed read (the
    interned object is updated in place, not forked). The witness must be
    discriminating, so the reference MUST be an EARLIER read step on the SAME node
    (identity is a per-process notion) and BOTH steps MUST observe at least one row
    (an empty re-fetch — e.g. after a delete — cannot witness preservation).
    """
    source = step["sameObjectAs"]
    # source < 0 defends programmatic (non-YAML) callers; the schema enforces minimum 0.
    if source < 0 or source >= index:
        raise CaseFailure(
            f"{case.path.name}: coherence[{index}].sameObjectAs={source} "
            f"must reference an EARLIER step."
        )
    referenced = case.coherence[source]
    if referenced["kind"] != "read":
        raise CaseFailure(
            f"{case.path.name}: coherence[{index}].sameObjectAs={source} must "
            f"reference a read step; a write step observes no object."
        )
    if referenced["node"] != step["node"]:
        raise CaseFailure(
            f"{case.path.name}: coherence[{index}].sameObjectAs={source} crosses "
            f"nodes ({referenced['node']} -> {step['node']}); identity preservation "
            f"is per-process, so both steps MUST run on the same node."
        )
    identity_col = step.get("identityAttr", default_identity)
    this_ids = _identity_keys(case, index, results[index], identity_col, label="coherence")
    that_ids = _identity_keys(case, source, results[source], identity_col, label="coherence")
    if not this_ids or not that_ids:
        raise CaseFailure(
            f"{case.path.name}: coherence[{index}].sameObjectAs={source} has an "
            f"empty identity witness; both steps MUST observe at least one row for "
            f"identity preservation to mean anything."
        )
    if this_ids != that_ids:
        raise CaseFailure(
            f"{case.path.name}: coherence[{index}] is declared to denote the same "
            f"object(s) as step {source}, but their primary-key identities differ "
            f"(cross-process refresh forked a new object).\n"
            f"  step {index}: {this_ids!r}\n"
            f"  step {source}: {that_ids!r}"
        )


# --- entry point ------------------------------------------------------------


def run_case(case: Case, db: DatabaseProvider) -> None:
    """Run all available assertion layers for *case* against *db*."""
    if case.lane == "api-conformance":
        # The api-conformance lane is schema-validated by the m-case-format harness but NOT
        # executed here — its observable (an injected transient, a retry-loop
        # branch, the emitted read-lock proof) needs machinery the single-connection
        # harness lacks. Each language's API Conformance Suite satisfies it. Run the
        # dialect-agnostic structural checks so coverage is not silently skipped,
        # then return BEFORE touching the database (no dialect / provisioning /
        # execution — so this lane runs even with no provider bound).
        _assert_schema(case)
        if not case.is_boundary:
            # A read-shape api-conformance case (the read-lock matrix
            # `m-read-lock-002`-`m-read-lock-005`) still round-trips its operation +
            # descriptor through the serde seam.
            _assert_serde(case)
            _assert_equivalent_encodings(case)
        return

    if case.is_rejected:
        # Negative validation (m-value-object / m-op-algebra, resolved Q7): the input
        # is refused PRE-SQL by model-aware validation — no dialect, no provisioning,
        # no execution. It runs identically on every dialect (idempotent, DB-free), so
        # branch here before the dialect is even read.
        _assert_schema(case)  # layer 1 (structural invariants for the shape)
        _assert_serde(case)  # layer 4 (operation, if any, + descriptor)
        _assert_rejected(case)  # the pre-SQL refusal, asserting the named rule
        return

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
        # Retry conflict (m-opt-lock): golden SQL lives PER ATTEMPT, so there is no
        # top-level then.statements to key on. Handle it here, before the then.statements
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
        _assert_conflict_input(case, dialect)  # layer 5c (① ↔ ② per attempt)
        _provision(case, db)  # fixtures loaded: the versioned row exists
        _assert_conflict_retry(case, db)  # given.apply + ordered attempts
        return

    if case.is_error:
        # A two-connection (concurrency) error case has no top-level then.statements, so
        # branch before the then.statements access below, like the per-step shapes.
        _assert_schema(case)
        _assert_serde(case)  # descriptor serde only (error cases have no operation)
        _assert_equivalent_encodings(case)
        if not _error_has_golden(case, dialect):
            return  # no golden for this dialect: dialect-agnostic checks only
        _assert_error_normalization(case, dialect)  # layer 3
        _assert_error_classification(case, db)
        return

    if case.is_concurrency_success:
        # A concurrency-success case (m-read-lock behavioral read-lock:
        # m-read-lock-007/m-read-lock-008) also carries its golden per round inside
        # `concurrency.rounds` (no top-level then.statements), so
        # branch before the then.statements access below, as a sibling of `is_error`.
        _assert_schema(case)
        _assert_serde(case)  # descriptor serde only (no operation)
        _assert_equivalent_encodings(case)
        if not _concurrency_has_golden(case, dialect):
            return  # no golden for this dialect: dialect-agnostic checks only
        _assert_concurrency_normalization(case, dialect)  # layer 3
        _assert_concurrency_success(case, db)  # layer 2 (two held sessions, no error)
        return

    if dialect not in case.golden_dialects:
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
        _assert_write_input_columns(case, dialect)  # layer 5c (① ↔ ② column/value)
        _provision_empty(case, db)
        _assert_write_sequence(case, db)  # apply DML, assert table state
        _assert_pk_allocation(case, db)  # layer 5b: PK-generation oracle (sequence)
        return

    if case.is_conflict:
        _assert_conflict_input(case, dialect)  # layer 5c (① ↔ ② single form)
        _provision(case, db)  # fixtures loaded: the row to lock exists
        _assert_conflict(case, db)  # given.apply + golden UPDATE, affected rows
        return

    _assert_round_trip_count(case, dialect)  # layer 5 (count)
    _provision(case, db)
    if _is_deep_fetch(case):
        _assert_deep_fetch(case, db)  # layer 2 + 5 (graph)
    elif case.expected_graph is not None:
        # A value-object materialization read (m-value-object): the single owner
        # statement carries the document column; nested values are decoded from it
        # (no deep-fetch child statement).
        _assert_value_object_graph(case, db)  # layer 2 + 5 (graph)
    else:
        _assert_flat_equivalence(case, db)  # layer 2
