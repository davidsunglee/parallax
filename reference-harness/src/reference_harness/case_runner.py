"""The layered assertion engine (m-case-format runner sub-part).

Per case, against a freshly-provisioned database selected via the provider seam:

1. **Schema conformance** — descriptor / query / case validate (done
   statically by :mod:`schema_validate`; re-asserted here for the loaded case).
2. **Triple equivalence** — ``exec(then.statements[dialect]) == exec(referenceSql) ==
   then.rows`` (the ``referenceSql`` term only when present).
3. **Normalization determinism** — ``normalize(then.statements[dialect]) ==
   then.statements[dialect]`` (per statement, for multi-statement cases).
4. **Serde round-trip** — ``serialize(deserialize(x)) == x`` for BOTH the
   Object Query encoding AND the model descriptor, in BOTH JSON and YAML.
5. **Round-trip-count consistency** — for relationship / deep-fetch
   cases the number of golden SQL statements equals the declared ``roundTrips``,
   each level executes (child levels keyed by the parents gathered from the
   previous level), and the assembled object graph equals ``then.graph``.

It deliberately **never compiles a query to SQL** — that is the job of a
real implementation, graded against the golden SQL.
"""

from __future__ import annotations

import contextlib
import datetime
import functools
import json
import re
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, NamedTuple

import sqlglot
from sqlglot import exp
from sqlglot.expressions.core import Expr

from . import errors, portable_literal, serde
from .case import Case, Entity, Model, conflict_write_rows
from .data_loader import load_model
from .ddl_builder import (
    contributor_types,
    ddl_for,
    placeholder_cast_type,
    quote_identifier,
)
from .document_codec import decode_leaf, decode_stored, encode_document, encode_leaf, is_document
from .inheritance import (
    MODEL_REJECTED_RULES,
    PREDICATE_REJECTED_RULES,
    STRATEGY_TPCS,
    STRATEGY_TPH,
    WRITE_REJECTED_RULES,
    Family,
    inheritance_of,
    is_abstract,
    narrowed_view_key,
    resolve_hop_effective_set,
    resolve_root_source_set,
    tag_of,
    tag_value_to_subtype,
    validate_family,
    validate_query_inheritance,
)
from .keyed_write_validate import (
    KEYED_WRITE_REJECTED_RULES,
    states_framework_marker,
    undeclared_row_members,
    validate_keyed_write,
)
from .metamodel import (
    MODEL_REJECTED_RULES as METAMODEL_MODEL_REJECTED_RULES,
)
from .metamodel import (
    validate_index_identities,
)
from .object_query_validate import validate_object_query
from .predicate_write_validate import (
    requires_predicate_write_materialization,
    validate_predicate_write,
)
from .providers import DatabaseProvider
from .sql_normalize import _detach_read_lock, is_union_all, normalize, sqlglot_dialect
from .storage_layout import (
    MODEL_REJECTED_RULES as STORAGE_LAYOUT_MODEL_REJECTED_RULES,
)
from .storage_layout import (
    ColumnContributor,
    ColumnSlot,
    ColumnTier,
    DocumentPath,
    PositionBranch,
    PositionColumn,
    PositionLayoutView,
    RelationalDocument,
    TableLayout,
    position_projection,
    position_view,
    validate_storage_layout,
)
from .temporal_selection_validate import normalize_authored_temporal_selections
from .temporality import TEMPORAL_DIMENSION_RANK, derive_temporal_structure, temporal_axes
from .value_object_resolve import REJECTED_RULES, RejectionError
from .write_validate import undeclared_members, validate_subtype_write, validate_write


class _MaterializedRow(dict[str, Any]):
    __slots__ = ("consumed_value_object_columns", "value_object_columns")

    def __init__(
        self,
        values: dict[str, Any],
        *,
        value_object_columns: dict[str, Any] | None = None,
        consumed_value_object_columns: set[str] | None = None,
    ) -> None:
        super().__init__(values)
        self.value_object_columns = value_object_columns or {}
        self.consumed_value_object_columns = consumed_value_object_columns or set()


def _materialized_row(row: dict[str, Any]) -> _MaterializedRow:
    if isinstance(row, _MaterializedRow):
        return _MaterializedRow(
            dict(row),
            value_object_columns=dict(row.value_object_columns),
            consumed_value_object_columns=set(row.consumed_value_object_columns),
        )
    return _MaterializedRow(dict(row))


def _reference_identity_row(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, _MaterializedRow):
        return dict(row)
    return {
        key: value
        for key, value in row.items()
        if key not in row.value_object_columns or key in row.consumed_value_object_columns
    }


def _write_column_order(case: Case, entity: Entity) -> tuple[str, ...]:
    """The Table-Layout Columns a row-owning *entity* writes, in canonical order.

    Every golden write-shape check reads its column sequence here, so the
    independently compiled layout — not a second effective-definition walk — is
    what the authored DML is graded against.
    """
    view = case.model.storage_layout.entity(entity.canonical_name)
    if view is None:
        raise CaseFailure(
            f"{case.path.name}: {entity.name} owns no rows, so it has no Table Layout to "
            f"write through."
        )
    return tuple(slot.column for slot in view.columns)


# The full pre-SQL rejection vocabulary spans value objects, queries,
# inheritance, storage layout, writes, and keyed-instruction shape. The
# compatibility-case schema's `rejectedRule` enum is the source of truth; these
# sets MUST stay in lockstep with it.
ALL_REJECTED_RULES = (
    REJECTED_RULES
    | METAMODEL_MODEL_REJECTED_RULES
    | MODEL_REJECTED_RULES
    | STORAGE_LAYOUT_MODEL_REJECTED_RULES
    | PREDICATE_REJECTED_RULES
    | WRITE_REJECTED_RULES
    | KEYED_WRITE_REJECTED_RULES
    | {"predicate-write-readless-document-many-unsupported"}
)


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


# The host carrier each string-carried Neutral Type decodes to, and the decoder
# that reads its portable literal.
_LITERAL_CARRIERS: tuple[tuple[type, Callable[[str], Any]], ...] = (
    (datetime.datetime, portable_literal.decode_timestamp),
    (datetime.date, portable_literal.decode_date),
    (datetime.time, portable_literal.decode_time),
    (uuid.UUID, portable_literal.decode_uuid),
    (bytes, portable_literal.decode_octets),
)


def _decoded_against(value: Any, other: Any) -> Any:
    """*value* decoded as a portable literal of *other*'s space, else unchanged.

    ``datetime`` is asked before ``date`` because it is a ``date`` subclass, so an
    instant would otherwise be compared against a calendar-date literal.
    """
    if not isinstance(value, str):
        return value
    for carrier, decode in _LITERAL_CARRIERS:
        if isinstance(other, carrier):
            return decode(value) if decode(value) is not None else value
    return value


def _scalars_equal(left: Any, right: Any, tolerance: Decimal | None) -> bool:
    """Compare two scalars exactly in Decimal space, or within ``tolerance``.

    Numerics compare as exact Decimals (no ``float`` anywhere) so a ``decimal``
    money column matches to the cent and a value's type never depends on whether
    it is whole. When the case declares a ``tolerance`` — for inherently inexact
    results (stddev / variance / repeating-decimal avg) that cannot be authored
    exactly and differ in scale across dialects — numeric comparison becomes
    ``abs(left - right) <= tolerance``. Non-numerics (str / bool / None) use ``==``.

    A case authors a `date` / `time` / `timestamp` / `uuid` / `bytes` value as its
    PORTABLE LITERAL — the corpus YAML schema resolves four implicit types and no
    more (:mod:`corpus_yaml`), so such a value reaches here as the text its author
    wrote, while the row read back carries the decoded host value. The literal is
    decoded before comparison, so the two name the same value or they do not.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        # bool is not numeric: a boolean equals only a boolean of the same value
        # (so True != 1 and False != 0), never a number that happens to be 0/1.
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    left, right = _decoded_against(left, right), _decoded_against(right, left)
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


def _entry_bind_values(entry: Mapping[str, Any], dialect: str) -> list[Any]:
    """One golden entry's binds for *dialect* (default ``[]``).

    A flat array is dialect-agnostic and answers for every dialect; a map is keyed
    by dialect, covering exactly the dialects its own ``sql`` map declares
    (asserted by :func:`_assert_binds_dialect_keys` and its scenario twin). Both
    forms are authorable wherever a golden statement is, because a document
    mutation's path bind differs between the two dialects while the value bind
    beside it does not (m-dialect).
    """
    binds = entry.get("binds", [])
    return list(binds[dialect]) if isinstance(binds, dict) else list(binds)


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
            pairs.append((sql[dialect], _entry_bind_values(entry, dialect)))
    return pairs


def _entry_binds(entries: Any, index: int, dialect: str) -> list[Any]:
    """The authored binds of statement *index* in a `statements` entry list for
    *dialect* (default ``[]``).

    Resolved through :func:`_entry_bind_values`, so a dialect-keyed ``binds`` map
    answers with the executing dialect's own array rather than with its keys.
    """
    if not isinstance(entries, list) or index >= len(entries):
        return []
    entry = entries[index]
    return _entry_bind_values(entry, dialect) if isinstance(entry, dict) else []


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
        # Whether a write step may settle against a find at all is a property of
        # the document, not of a dialect, so it is decided HERE — the one layer
        # every scenario reaches. The cross-check that consumes the reference
        # (:func:`_assert_scenario_settled_write`) is skipped for a dialect the
        # case carries no golden for, so a rule left there would hold on some
        # runs and not others.
        _assert_scenario_source_finds(case)
    elif case.is_conflict:
        if case.expected_affected_rows is None and not case.attempts:
            raise CaseFailure(f"{case.path.name}: conflict case missing affectedRows / attempts")
        # Whether the case may name an observed milestone at all is a property of
        # the document, not of a dialect or of an execution path, so it is decided
        # HERE — the one layer every conflict shape reaches. The cross-check that
        # consumes the coordinate (:func:`_assert_conflict_input`) is skipped
        # entirely for an api-conformance lane case and for a dialect the case
        # carries no golden for, so an entitlement left there would hold on some
        # runs and not others.
        _assert_observed_edge_entitlement(case, _conflict_temporal_entity(case))
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
        if case.rejected_rule not in ALL_REJECTED_RULES:
            raise CaseFailure(
                f"{case.path.name}: rejected case then.rejectedRule "
                f"{case.rejected_rule!r} is not a known rule"
            )
        # A rejected case pins a SINGLE invalid input, so its `when` MUST carry
        # EXACTLY ONE of `objectQuery` / `write` / `model` (the normative "exactly
        # one invalid input" rule, m-case-format Rejected cases). This guard is a
        # defense-in-depth mirror of the schema's `oneOf`
        # (compatibility-case.schema.json rejected branch): it keeps the constraint
        # enforced even if some future caller reaches the runner without schema
        # validation, and `_assert_rejected` below dispatches on the single member
        # present.
        present = [member for member in ("objectQuery", "write", "model") if member in case.when]
        if len(present) != 1:
            raise CaseFailure(
                f"{case.path.name}: a rejected case MUST carry EXACTLY ONE of "
                f"when.objectQuery / when.write / when.model (one invalid input); found "
                f"{present or 'none'}."
            )
    elif "objectQuery" not in case.when:
        raise CaseFailure(f"{case.path.name}: missing objectQuery")
    if not case.model.class_name:
        raise CaseFailure(f"{case.path.name}: model has no class name")
    _assert_binds_dialect_keys(case)
    _assert_reference_sql_dialect_keys(case)
    _assert_scenario_sql_bookkeeping(case)


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


def _assert_scenario_sql_bookkeeping(case: Case) -> None:
    """Validate scenario-local binds and independent read-oracle maps.

    Scenario SQL is stored below each step rather than at ``then``.  The same
    per-dialect coverage rules therefore apply independently at that location,
    and a read oracle must correspond to exactly one golden read statement.
    """
    if not case.is_scenario:
        return
    for index, step in enumerate(case.scenario):
        entries = step.get("statements", [])
        if not isinstance(entries, list):
            continue
        for statement_index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("binds"), dict):
                continue
            sql = entry.get("sql")
            sql_keys = set(sql) if isinstance(sql, dict) else set()
            if set(entry["binds"]) != sql_keys:
                raise CaseFailure(
                    f"{case.path.name}: when.scenario[{index}].statements[{statement_index}] "
                    f"binds map keys {sorted(entry['binds'])} != sql map keys "
                    f"{sorted(sql_keys)}"
                )
        reference_sql = step.get("referenceSql")
        if reference_sql is None:
            continue
        if len(entries) != 1:
            raise CaseFailure(
                f"{case.path.name}: when.scenario[{index}] referenceSql needs exactly one "
                "golden read statement"
            )
        if not isinstance(reference_sql, dict):
            continue
        sql = entries[0].get("sql") if isinstance(entries[0], dict) else None
        sql_keys = set(sql) if isinstance(sql, dict) else set()
        if set(reference_sql) != sql_keys:
            raise CaseFailure(
                f"{case.path.name}: when.scenario[{index}].referenceSql map keys "
                f"{sorted(reference_sql)} != golden sql map keys {sorted(sql_keys)}"
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
    # Layer 4a: Object Query serde. A read case has one top-level query; a
    # scenario or coherence case has one per read step; a write-sequence case and a
    # conflict case (m-opt-lock) have none. Layer 4b: metamodel (descriptor)
    # serde — always.
    if case.is_scenario:
        for step in case.scenario:
            # Read steps carry an `objectQuery`; write steps carry none.
            if "objectQuery" in step:
                serde.assert_roundtrip(step["objectQuery"])
    elif case.is_coherence:
        for step in case.coherence:
            if "objectQuery" in step:
                serde.assert_roundtrip(step["objectQuery"])
    elif case.is_rejected:
        # A rejected case carries the invalid input under `when.objectQuery` (a
        # schema-valid m-object-query document — serde it), `when.write` (a neutral
        # write row, which has no query to serde), OR `when.model` (an inline invalid
        # inheritance descriptor — round-tripped through descriptor serde before
        # semantic validation asserts the rejection, m-inheritance resolved Q3). The
        # referenced (valid) descriptor still round-trips below.
        if "objectQuery" in case.when:
            serde.assert_roundtrip(case.when["objectQuery"])
        elif "model" in case.when:
            serde.assert_roundtrip(case.when["model"])
    elif (
        not case.is_write_sequence
        and not case.is_conflict
        and not case.is_error
        and not case.is_concurrency_success
    ):
        serde.assert_roundtrip(case.object_query)
    serde.assert_roundtrip(case.model.descriptor)


def _assert_equivalent_encodings(case: Case) -> None:
    """Layer 4c: every declared alternate encoding collapses to its canonical read.

    Dialect-agnostic and database-free. A top-level read compares entries under
    ``when.equivalentEncodings`` to ``when.objectQuery``; a scenario read step does
    the same with its own sibling field and its own query. Authoring normalization
    first makes an omitted Transaction-Time selection explicit, then ordinary
    serde canonicalization proves both surface spellings denote one canonical
    query.
    """
    family = Family(case.model.entity_defs)
    if case.is_scenario:
        for step_index, step in enumerate(case.scenario):
            encodings = step.get("equivalentEncodings", [])
            if not encodings:
                continue
            canonical_query = serde.canonical(step["objectQuery"])
            for encoding_index, encoding in enumerate(encodings):
                normalized = normalize_authored_temporal_selections(encoding, family)
                if serde.canonical(normalized) != canonical_query:
                    raise CaseFailure(
                        f"{case.path.name}: scenario[{step_index}].equivalentEncodings"
                        f"[{encoding_index}] does not canonicalize to the step query.\n"
                        f"  encoding (canonical): {serde.canonical(normalized)!r}\n"
                        f"  query (canonical):    {canonical_query!r}"
                    )
        return
    if (
        case.is_write_sequence
        or case.is_conflict
        or case.is_coherence
        or case.is_error
        or case.is_concurrency_success
    ):
        return
    canonical_query = serde.canonical(case.object_query)
    for index, encoding in enumerate(case.equivalent_encodings):
        normalized = normalize_authored_temporal_selections(encoding, family)
        if serde.canonical(normalized) != canonical_query:
            raise CaseFailure(
                f"{case.path.name}: equivalentEncodings[{index}] does not "
                f"canonicalize to the case query.\n"
                f"  encoding (canonical): {serde.canonical(normalized)!r}\n"
                f"  query (canonical):    {canonical_query!r}"
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


def _join_endpoints(relationship: dict[str, Any]) -> tuple[str, str]:
    """Return ``(source_attr, target_attr)`` from a compiled structured join."""
    join = relationship["join"]
    return join["source"]["attribute"], join["target"]["attribute"]


def _column_of(entity: Entity, attr_name: str) -> str:
    return entity.attribute_by_name(attr_name)["column"]


def _resolve_rel_ref(model: Model, rel_ref: str) -> tuple[Entity, dict[str, Any]]:
    """Resolve ``Class.relationship`` to its owning entity + relationship def."""
    class_name, _, rel_name = rel_ref.rpartition(".")
    entity = model.entity(class_name)
    return entity, entity.relationship_metadata_by_name(rel_name)


def _deepfetch_paths(query: dict[str, Any]) -> list[list[str]]:
    """One Object Query's include paths as ordered lists of ``Class.relationship`` refs.

    A path is a closed object ``{appliesTo?, segments}`` whose entries are closed
    ``{rel, narrowTo?}`` segments (m-object-query); this projection keeps only the
    ``rel`` and is used where narrowing is irrelevant (root-entity resolution).
    Narrow-aware hop identity is built from :func:`_deepfetch_paths_raw`.

    Every helper here takes the QUERY rather than the case, because a read case's
    top-level ``when.objectQuery`` and a scenario read step's own ``objectQuery``
    are the same document in two positions and both carry includes.
    """
    return [[segment["rel"] for segment in path["segments"]] for path in query["includes"]]


def _deepfetch_paths_raw(query: dict[str, Any]) -> list[dict[str, Any]]:
    """The Include Paths as authored: closed ``{appliesTo?, segments}`` objects.

    Preserves both selection positions — the SOURCE guard and each hop's own
    ``narrowTo`` — so the fetch machinery can derive the narrowed view key, the
    root participation filter, and the dedup identity built from both.
    """
    return list(query["includes"])


def _deepfetch_root_position(query: dict[str, Any]) -> str | None:
    """The polymorphic position a deep fetch's paths are rooted at.

    The query's own ``target`` when it names an entity of the model, which is what
    a source guard clamps against.
    """
    target = query.get("target")
    return target if isinstance(target, str) else None


def _query_has_includes(query: dict[str, Any]) -> bool:
    """Whether an Object Query eager-fetches anything at all."""
    return bool(query.get("includes"))


def _is_deep_fetch(case: Case) -> bool:
    return _query_has_includes(case.object_query)


def _deepfetch_root_entity(model: Model, query: dict[str, Any]) -> Entity:
    """The entity the deep-fetch root query targets.

    It is the owning class of the first relationship in the first declared path
    (every path starts at the queried entity), so a deep fetch may be rooted at
    any entity in a multi-entity model, not just the descriptor's first one.
    """
    first_rel = _deepfetch_paths(query)[0][0]
    root_class = first_rel.rpartition(".")[0]
    return model.entity(root_class)


# Canonical as-of dimension order: Valid Time precedes Transaction Time in both the
# golden SQL clause order and the bind order (m-bitemp-write bitemporal table;
# case m-temporal-read-015).
_CANONICAL_AXIS_ORDER: tuple[str, ...] = ("valid-time", "transaction-time")


@dataclass(frozen=True, slots=True)
class _AsOfSelection:
    coordinate: str


@dataclass(frozen=True, slots=True)
class _AsOfRangeSelection:
    start: str
    end: str


@dataclass(frozen=True, slots=True)
class _HistorySelection:
    pass


_TemporalSelection = _AsOfSelection | _AsOfRangeSelection | _HistorySelection


def _query_temporal_selections(query: Any) -> dict[str, _TemporalSelection]:
    """One Object Query's Temporal Selection clause, keyed by dimension."""
    temporal = query.get("temporal") if isinstance(query, dict) else None
    if not isinstance(temporal, dict):
        return {}
    selections: dict[str, _TemporalSelection] = {}
    for dimension, selection in temporal.items():
        if not isinstance(selection, dict) or len(selection) != 1:
            continue
        tag = next(iter(selection))
        body = selection[tag]
        if tag == "asOf" and isinstance(body, str):
            selections[dimension] = _AsOfSelection(body)
        elif tag == "asOfRange" and isinstance(body, dict):
            start = body.get("start")
            end = body.get("end")
            if isinstance(start, str) and isinstance(end, str):
                selections[dimension] = _AsOfRangeSelection(start, end)
        elif tag == "history":
            selections[dimension] = _HistorySelection()
    return selections


def _root_asof_pins(query: dict[str, Any]) -> dict[str, str]:
    """Map ``{dimension: coordinate}`` from the read's own ``asOf`` selections. A
    dimension absent here defaults to the child's own ``latest`` value at
    propagation time. Empty when the root is unpinned.
    """
    return {
        dimension: selection.coordinate
        for dimension, selection in _query_temporal_selections(query).items()
        if isinstance(selection, _AsOfSelection)
    }


def _expected_pin_suffix(child_entity: Entity, pins: dict[str, str]) -> list[Any]:
    """The as-of binds a temporal child level MUST carry, after its IN-list.

    Per dimension, in canonical order (Valid Time, then Transaction Time): the propagated value
    is the root pin for that dimension, or the child's own ``default`` (``latest``) when the
    root did not pin it. ``latest`` lowers to the single equality bind
    (the axis's ``infinity``); a finite instant lowers to the half-open range's
    two binds ``[D, D]``. A non-temporal child yields ``[]``.
    """
    by_axis = {a["dimension"]: a for a in child_entity.temporal_runtime_axes}
    suffix: list[Any] = []
    for axis in _CANONICAL_AXIS_ORDER:
        attr = by_axis.get(axis)
        if attr is None:
            continue
        date = pins.get(axis, attr.get("default", "latest"))
        if date == "latest":
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

    Returns ``(entity, pkGeneration, pk_attribute)`` or ``None`` when the case does
    not insert into a sequence entity (e.g. ``max`` cases, non-pk-gen cases).
    """
    inserted = {step["entity"] for step in case.write_sequence if step.get("mutation") == "insert"}
    for entity in case.model.entities:
        if not inserted & {entity.name, entity.canonical_name}:
            continue
        pk_attr = next((a for a in entity.attributes if a.get("primaryKey")), None)
        if pk_attr is None:
            continue
        gen = pk_attr.get("pkGeneration")
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
        f"model {model.class_name!r} declares a sequence pkGeneration but has no "
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

    Independently re-derives, from the DECLARED pkGeneration config, the ids a
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
    seq_name = gen["name"]
    pk_column = pk_attr["column"]

    types = contributor_types(case.model)
    actual_rows = _read_table(db, _table_layout(case, entity.table), types)
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
    reg_rows = _read_table(db, _table_layout(case, registry.table), types)
    reg_row = next((r for r in reg_rows if r.get(name_column) == seq_name), None)
    if reg_row is None:
        raise CaseFailure(f"{case.path.name}: {registry.name} has no row for sequence {seq_name!r}")
    expected_counter = _expected_sequence_counter(initial, increment, batch, count)
    if reg_row.get(counter_column) != expected_counter:
        raise CaseFailure(
            f"{case.path.name}: sequence {seq_name!r} counter "
            f"{reg_row.get(counter_column)} != config-derived {expected_counter}"
        )


class _HopKey(NamedTuple):
    """The dedup identity of one deep-fetch hop (m-deep-fetch).

    ``parent`` is the key of the hop this one descends from, absent at a path's
    first segment: it is what keeps two branches that reach the same relationship
    from different parents apart, so every hop names exactly one set of parent rows.
    ``root_source`` is the path's resolved ROOT SOURCE SET, carried at that first
    segment alone — deeper hops inherit the guard through ``parent``.
    ``narrowed_set`` is the hop's own effective concrete set, carried only when a
    narrow was AUTHORED.

    The two narrow positions key on deliberately different things. ``narrowed_set``
    keys on whether a narrow was authored, because a narrowed hop populates its own
    view key even when it resolves to the target's entire set. ``root_source`` keys
    on the resolved set alone, because a root guard creates no view: a guard
    admitting every root object is observationally the broad path and collapses onto
    it, while every proper guard resolves to a strict subset and differs
    automatically.
    """

    parent: _HopKey | None
    root_source: tuple[str, ...] | None
    rel_ref: str
    narrowed_set: tuple[str, ...] | None


class _ResolvedHop(NamedTuple):
    """One authored path segment resolved against the family.

    The single derivation both passes over a deep fetch share — the execution pass
    that issues each level's statement and the assembly pass that walks the authored
    paths again — so a hop cannot be identified one way while executing and another
    way while attaching. ``effective_set`` is the hop's canonically-ordered effective
    concrete set, or ``None`` for a non-polymorphic target; ``target`` is the
    relationship's declared target class, carried alongside it because the
    table-per-hierarchy tag predicate is derived from the family it belongs to.
    """

    key: _HopKey
    target: str | None
    effective_set: list[str] | None
    is_narrowed: bool


def _resolve_hop(
    family: Family,
    segment: dict[str, Any],
    *,
    parent: _HopKey | None,
    root_source: tuple[str, ...] | None,
) -> _ResolvedHop:
    """Resolve one authored segment into its effective set and its dedup identity.

    *root_source* is the path's resolved root source set at a path's FIRST segment
    and ``None`` at every deeper one, because a deeper hop descends from parents the
    guard already selected and is separated by *parent* instead.
    """
    rel_ref = segment["rel"]
    narrow_to = segment.get("narrowTo") if isinstance(segment.get("narrowTo"), list) else None
    target = family.relationship_target(rel_ref)
    if target is not None and inheritance_of(family.defs.get(target, {})) is not None:
        effective_set, is_narrowed = resolve_hop_effective_set(family, rel_ref, narrow_to)
    else:
        effective_set, is_narrowed = None, False
    key = _HopKey(
        parent=parent,
        root_source=root_source,
        rel_ref=rel_ref,
        narrowed_set=tuple(effective_set) if (is_narrowed and effective_set is not None) else None,
    )
    return _ResolvedHop(
        key=key, target=target, effective_set=effective_set, is_narrowed=is_narrowed
    )


class _FetchStep:
    """One relationship hop = one golden statement (after the root).

    A hop is identified by :attr:`hop_key`, so a BROAD hop and a NARROWED hop over
    the same relationship, two narrowed hops with different effective sets, two
    paths guarded to different root sources, and two branches reaching one
    relationship from different parents are all DISTINCT levels (each counts toward
    ``L`` in ``1 + L``), while equivalent authored narrowings that resolve to the
    same set DEDUPLICATE (m-deep-fetch). :attr:`parent_hop` names the hop whose
    fetched rows this one gathers its parent keys from, absent when those are the
    root query's own rows. Its graph attach key is :attr:`view_key` — the ordinary
    relationship name for a broad hop, the derived ``<rel>[<Concrete>,<Concrete>]``
    for a narrowed one; a root guard contributes NO view key at all.
    :attr:`root_guard` is the source set a PROPER root guard restricts this hop's
    parent objects to, carried only on the hop a guarded path starts with (a deeper
    hop's parents are already the guarded ones) and only when the guard admits fewer
    than every root object.
    """

    def __init__(
        self,
        rel_ref: str,
        parent_entity: Entity,
        child_entity: Entity,
        parent_attr: str,
        child_attr: str,
        cardinality: str,
        order_by: list[dict[str, Any]] | None = None,
        *,
        hop_key: _HopKey,
        view_key: str,
        effective_set: list[str] | None,
        is_narrowed: bool,
        root_guard: tuple[str, ...] | None,
        tag_column: str | None,
        tag_binds: list[Any],
        polymorphic: bool,
        variant_map: dict[Any, str],
    ) -> None:
        self.rel_ref = rel_ref
        self.rel_name = rel_ref.rpartition(".")[2]
        self.parent_entity = parent_entity
        self.child_entity = child_entity
        self.parent_attr = parent_attr
        self.child_attr = child_attr
        self.cardinality = cardinality
        self.order_by = order_by or []
        self.hop_key = hop_key
        self.view_key = view_key
        self.effective_set = effective_set
        self.is_narrowed = is_narrowed
        self.root_guard = root_guard
        self.tag_column = tag_column
        self.tag_binds = tag_binds
        self.polymorphic = polymorphic
        self.variant_map = variant_map

    @property
    def parent_hop(self) -> _HopKey | None:
        return self.hop_key.parent

    @property
    def to_many(self) -> bool:
        return self.cardinality == "one-to-many"


def _fetch_steps(model: Model, query: dict[str, Any]) -> list[_FetchStep]:
    """Ordered, de-duplicated relationship hops for a deep fetch.

    Each distinct hop across all paths is exactly one statement (one query per level
    — the N+1-eliminating contract). Dedup identity is :class:`_HopKey`: paths
    sharing a segment prefix (``{segments: [{rel: Order.items}]}`` /
    ``{segments: [{rel: Order.items}, {rel: OrderItem.statuses}]}``) fetch
    ``Order.items`` once; a broad and a narrowed hop over the same relationship, or
    two differently-narrowed hops, are DISTINCT; equivalent authored narrowings
    (``[Pet]`` vs ``[Cat, Dog]``) converge — at the segment position and at the root
    position alike.
    """
    family = Family(model.entity_defs)
    variant_map = tag_value_to_subtype(model.entity_defs)
    root_position = _deepfetch_root_position(query)
    root_full_set = resolve_root_source_set(family, root_position, {})
    steps: list[_FetchStep] = []
    seen: set[_HopKey] = set()
    for path in _deepfetch_paths_raw(query):
        root_source = resolve_root_source_set(family, root_position, path)
        # A guard admitting every root object restricts nothing, so only a PROPER
        # guard is carried as a participation filter.
        guard = root_source if root_source != root_full_set else None
        parent_hop: _HopKey | None = None
        for index, segment in enumerate(path["segments"]):
            hop = _resolve_hop(
                family, segment, parent=parent_hop, root_source=root_source if index == 0 else None
            )
            if hop.key not in seen:
                seen.add(hop.key)
                steps.append(
                    _step_of(
                        model,
                        family,
                        hop,
                        variant_map,
                        root_guard=guard if index == 0 else None,
                    )
                )
            parent_hop = hop.key
    return steps


def _step_of(
    model: Model,
    family: Family,
    hop: _ResolvedHop,
    variant_map: dict[Any, str],
    *,
    root_guard: tuple[str, ...] | None,
) -> _FetchStep:
    """The executable step one resolved hop denotes: its endpoints, its graph attach
    key, and the table-per-hierarchy tag binds its shared-table read carries."""
    rel_ref = hop.key.rel_ref
    parent_entity, relationship = _resolve_rel_ref(model, rel_ref)
    child_entity = model.entity(relationship["join"]["target"]["entity"])
    this_attr, other_attr = _join_endpoints(relationship)
    rel_name = rel_ref.rpartition(".")[2]

    if hop.effective_set is not None and hop.target is not None:
        # The shared table holds the WHOLE family's concretes (the root's
        # descendants), not just the relationship target's — so a hop targeting an
        # abstract SUBTYPE still needs a tag predicate to exclude sibling branches in
        # the same table. No tag predicate when the hop spans the whole shared table;
        # otherwise a tag `=`/`in` over the effective set's tagValues.
        root = family.root_of(hop.target)
        whole = family.effective_concrete_set(root) if root is not None else hop.effective_set
        tag_column = family.tag_column_of(hop.target)
        tag_binds: list[Any] = (
            []
            if set(hop.effective_set) == set(whole)
            else _hop_tag_binds(family, hop.effective_set)
        )
        view_key = (
            narrowed_view_key(family, rel_ref, hop.effective_set) if hop.is_narrowed else rel_name
        )
        polymorphic = len(hop.effective_set) > 1 and family.strategy_of(hop.target) == STRATEGY_TPH
    else:
        tag_column, tag_binds, polymorphic = None, [], False
        view_key = rel_name

    return _FetchStep(
        rel_ref=rel_ref,
        parent_entity=parent_entity,
        child_entity=child_entity,
        parent_attr=this_attr,
        child_attr=other_attr,
        cardinality=relationship["cardinality"],
        order_by=relationship.get("orderBy"),
        hop_key=hop.key,
        view_key=view_key,
        effective_set=hop.effective_set,
        is_narrowed=hop.is_narrowed,
        root_guard=root_guard,
        tag_column=tag_column,
        tag_binds=tag_binds,
        polymorphic=bool(polymorphic),
        variant_map=variant_map,
    )


def _hop_tag_binds(family: Family, effective_set: list[str]) -> list[Any]:
    """The ``tagValue`` list for a table-per-hierarchy hop's effective set.

    A single concrete lowers to ``kind = ?`` (one bind); several to ``kind in (?, …)``
    (one bind per concrete). *effective_set* is already in the family's canonical
    sibling-set order (ALPHABETICAL by entity name, m-inheritance), so the binds follow
    that order. Mirrors the top-level TPH tag-selection rule (m-sql), applied to a
    deep-fetch child level.
    """
    binds: list[Any] = []
    for name in effective_set:
        block = inheritance_of(family.defs.get(name, {}))
        if block is not None and block.get("tagValue") is not None:
            binds.append(block["tagValue"])
    return binds


# --- assertions -------------------------------------------------------------


def _query_rows(
    case: Case, db: DatabaseProvider, sql: str, binds: list[Any]
) -> list[dict[str, Any]]:
    executable, presence_keys = _alias_document_presence_projections(sql, db.dialect, case.model)
    rows = db.query(executable, binds) if binds else db.query(executable)
    if not presence_keys:
        return rows
    return [{key: value for key, value in row.items() if key not in presence_keys} for row in rows]


def _document_presence_projection(projection: Any) -> bool:
    """Whether an expression has the physical document-presence syntax."""
    return (
        isinstance(projection, exp.Not)
        and isinstance(projection.this, exp.Is)
        and isinstance(projection.this.this, exp.Column)
        and isinstance(projection.this.expression, exp.Null)
    )


def _same_projected_document(
    presence: Any,
    document: Any,
    select: Any,
    document_columns: Mapping[str, frozenset[str]],
    dialect: str,
) -> bool:
    if not _document_presence_projection(presence):
        return False
    candidate = _projection_expr(document)
    if not isinstance(candidate, exp.Column):
        return False
    source = presence.this.this
    if source.name != candidate.name or source.table != candidate.table:
        return False
    physical = _physical_column_source(select, source, dialect)
    return physical is not None and physical[1] in document_columns.get(physical[0], frozenset())


def _containing_select(expression: Any) -> Any | None:
    parent = expression.parent
    while parent is not None and not isinstance(parent, exp.Select):
        parent = parent.parent
    return parent


def _source_relations(select: Any) -> dict[str, Any]:
    """Immediate FROM/JOIN relations in ``select``, keyed by their visible alias."""
    from_clause = select.args.get("from_")
    relations = ([] if from_clause is None else [from_clause.this, *from_clause.expressions]) + [
        join.this for join in select.args.get("joins") or ()
    ]
    return {
        relation.alias_or_name: relation
        for relation in relations
        if isinstance(relation, (exp.Table, exp.Subquery)) and relation.alias_or_name
    }


def _column_identity(column: Any, dialect: str) -> str:
    identifier = column.this
    return _identifier_identity(
        column.name,
        dialect,
        quoted=isinstance(identifier, exp.Identifier) and bool(identifier.args.get("quoted")),
    )


def _passthrough_projection(select: Any, column: Any, dialect: str) -> tuple[int, Any] | None:
    identity = _column_identity(column, dialect)
    matches = [
        (ordinal, projection)
        for ordinal, projection in enumerate(select.expressions)
        if _projection_identity(projection, dialect) == identity
    ]
    if len(matches) == 1:
        ordinal, projection = matches[0]
        candidate = _projection_expr(projection)
        if isinstance(candidate, exp.Column) and not candidate.is_star:
            return ordinal, candidate
    return None


def _passthrough_column(select: Any, column: Any, dialect: str) -> Any | None:
    if (matched := _passthrough_projection(select, column, dialect)) is not None:
        return matched[1]
    stars = [
        projection
        for projection in select.expressions
        if isinstance(projection, exp.Star)
        or isinstance(projection, exp.Column)
        and projection.is_star
    ]
    if len(stars) != 1:
        return None
    relations = _source_relations(select)
    star = stars[0]
    qualifier = star.table if isinstance(star, exp.Column) else ""
    identifier = column.this
    quoted = isinstance(identifier, exp.Identifier) and bool(identifier.args.get("quoted"))
    if qualifier:
        return exp.column(column.name, table=qualifier, quoted=quoted)
    if len(relations) == 1:
        return exp.column(column.name, table=next(iter(relations)), quoted=quoted)
    return None


def _ordinal_passthrough_column(select: Any, ordinal: int) -> Any | None:
    if ordinal >= len(select.expressions):
        return None
    projection = select.expressions[ordinal]
    candidate = _projection_expr(projection)
    return candidate if isinstance(candidate, exp.Column) and not candidate.is_star else None


def _physical_column_source(select: Any, column: Any, dialect: str) -> tuple[str, str] | None:
    """Trace one selected Column through aliases to its physical Table and Column."""
    relations = _source_relations(select)
    relation = relations.get(column.table)
    if relation is None and not column.table and len(relations) == 1:
        relation = next(iter(relations.values()))
    if isinstance(relation, exp.Table):
        return relation.name, column.name
    if not isinstance(relation, exp.Subquery):
        return None
    branches = _select_branches(relation.this)
    if isinstance(relation.this, exp.SetOperation):
        if not branches:
            return None
        matched = _passthrough_projection(branches[0], column, dialect)
        if matched is None:
            return None
        ordinal = matched[0]
        passthroughs = [_ordinal_passthrough_column(branch, ordinal) for branch in branches]
    else:
        passthroughs = [_passthrough_column(branch, column, dialect) for branch in branches]
    sources = [
        source
        for branch, passthrough in zip(branches, passthroughs, strict=True)
        if passthrough is not None
        if (source := _physical_column_source(branch, passthrough, dialect)) is not None
    ]
    unique = set(sources)
    return next(iter(unique)) if len(sources) == len(branches) and len(unique) == 1 else None


def _identifier_identity(name: str, dialect: str, *, quoted: bool) -> str:
    """Database identity used when allocating unquoted execution aliases."""
    if quoted:
        return name
    if dialect in {"postgres", "mariadb"}:
        return name.casefold()
    return name


def _projection_identity(projection: Any, dialect: str) -> str | None:
    output = projection.args.get("alias") if isinstance(projection, exp.Alias) else None
    if not isinstance(output, exp.Identifier) and isinstance(projection, exp.Column):
        output = projection.this
    if isinstance(output, exp.Identifier):
        return _identifier_identity(output.name, dialect, quoted=bool(output.args.get("quoted")))
    return (
        _identifier_identity(projection.output_name, dialect, quoted=False)
        if projection.output_name
        else None
    )


def _false_presence_padding(projection: Any) -> bool:
    return isinstance(projection, exp.Boolean) and projection.this is False


def _document_presence_ordinals(selects: list[Any], model: Model, dialect: str) -> tuple[int, ...]:
    """Presence ordinals proved by layout metadata and adjacency across branches."""
    if not selects:
        return ()
    width = len(selects[0].expressions)
    if any(len(select.expressions) != width for select in selects):
        return ()
    document_columns = {
        table.table: frozenset(
            slot.column for slot in table.columns if slot.tier is ColumnTier.DOCUMENT
        )
        for table in model.storage_layout.tables
    }
    ordinals: list[int] = []
    for ordinal in range(width - 1):
        arms = [select.expressions[ordinal] for select in selects]
        next_arms = [select.expressions[ordinal + 1] for select in selects]
        structural = [
            _same_projected_document(arm, next_arm, select, document_columns, dialect)
            for arm, next_arm, select in zip(arms, next_arms, selects, strict=True)
        ]
        if any(structural) and all(
            proved or _false_presence_padding(arm)
            for proved, arm in zip(structural, arms, strict=True)
        ):
            ordinals.append(ordinal)
    return tuple(ordinals)


def _select_branches(tree: Any) -> list[Any]:
    branches = _union_branch_selects(tree)
    if branches:
        return branches
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    return [] if select is None else [select]


def _alias_document_presence_projections(
    sql: str, dialect: str, model: Model
) -> tuple[str, frozenset[str]]:
    """Give only proven physical presence cells collision-safe execution aliases."""
    tree = sqlglot.parse_one(sql, read=sqlglot_dialect(dialect))
    selects = _select_branches(tree)
    ordinals = _document_presence_ordinals(selects, model, dialect)
    reserved = {
        identity
        for select in selects
        for projection in select.expressions
        if (identity := _projection_identity(projection, dialect)) is not None
    }
    aliases: dict[int, str] = {}
    for ordinal in ordinals:
        base = f"__parallax_document_presence_{ordinal}"
        alias = base
        suffix = 1
        while _identifier_identity(alias, dialect, quoted=False) in reserved:
            alias = f"{base}_{suffix}"
            suffix += 1
        aliases[ordinal] = alias
        reserved.add(_identifier_identity(alias, dialect, quoted=False))
    keys = frozenset(aliases.values())
    for select in selects:
        projections = list(select.expressions)
        for ordinal in ordinals:
            projections[ordinal] = exp.alias_(projections[ordinal], aliases[ordinal])
        select.set("expressions", projections)
    if not ordinals:
        return sql, keys
    lock_suffix = _detach_read_lock(tree, dialect)
    return tree.sql(dialect=sqlglot_dialect(dialect)) + lock_suffix, keys


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


def _apply_given(case: Case, db: DatabaseProvider) -> None:
    """Apply a case's out-of-band ``given.apply`` entries verbatim.

    Every lane that admits the key calls this at the same point — after its own
    provisioning and before the lane's first golden statement or step — so the
    timing and the interpretation are one thing rather than one per lane. Each
    entry's ``sql`` is naive, dialect-agnostic text run as authored; ``binds``
    defaults to empty. A case carrying none applies nothing.
    """
    for entry in case.apply:
        db.execute(entry["sql"], list(entry.get("binds", [])))


def _assert_flat_equivalence(case: Case, db: DatabaseProvider) -> None:
    dialect = db.dialect
    (golden,) = case.golden_statements(dialect)

    _assert_tph_document_partition_shape(case, dialect)

    # Temporal composition (m-sql / m-temporal-read): the dedicated temporal-only
    # table-per-concrete-subtype witness carries each branch's selected temporal
    # contribution, while history contributes no predicate or bind.
    _assert_temporal_only_union_binds(case, dialect)

    golden_rows = _query_rows(case, db, golden, case.statement_binds(0, dialect))
    # Relational Document Layout (m-storage-layout / m-sql): the golden projects the
    # shared Structured Column once and the row-form result is the scalars it
    # carries, under the names a Column of each would have had.
    golden_rows = _materialize_target_tph_document_layout(
        case, golden_rows, include_value_objects=False
    )
    expected = case.expected_rows
    tolerance = case.tolerance

    # Abstract-target inheritance read oracle (m-inheritance / m-sql, resolved Q6):
    # the golden SQL projects the RAW tag column; `familyVariant` is materialized
    # from the tag metadata map, never projected as SQL.
    golden_rows = _materialize_family_variant(case, golden_rows)

    if not _rows_equal(golden_rows, expected, tolerance):
        raise CaseFailure(
            f"{case.path.name}: then.statements ({dialect}) rows != then.rows.\n"
            f"  golden:   {golden_rows!r}\n"
            f"  expected: {expected!r}"
        )

    reference_sql = case.reference_sql_for(dialect)
    if reference_sql is not None:
        reference_rows = _materialize_target_tph_document_layout(
            case, db.query(reference_sql), include_value_objects=False
        )
        reference_rows = _materialize_family_variant(case, reference_rows)
        if not _rows_equal(reference_rows, expected, tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql rows != then.rows.\n"
                f"  reference: {reference_rows!r}\n"
                f"  expected:  {expected!r}"
            )


class _AbstractFamilyPosition(NamedTuple):
    """The abstract family node a query reads, with the family it belongs to.

    *target* keeps the QUERY's own spelling of that position — every :class:`Family`
    lookup resolves an unambiguous local alias itself, so carrying the authored
    spelling keeps a consumer's diagnostics in the case's own words.
    """

    family: Family
    target: str
    strategy: str | None


def _abstract_family_position(case: Case, query: Any) -> _AbstractFamilyPosition | None:
    """Classify *query*'s target position: the abstract family node it reads, or
    ``None`` for every other read.

    One classifier for every consumer whose behavior turns on the distinction,
    because they all ask the same question of the same field. An ABSTRACT position
    resolves over more than one concrete subtype, so its SQL partitions per branch
    and its result carries a variant tag (`m-sql`); a CONCRETE-target read — and any
    read of a non-inheritance entity — carries neither, having already named the one
    variant it returns. What differs between consumers is only the storage
    *strategy* they then project that behavior from.

    Abstractness is read off the definition's inheritance role, which only a family
    participant carries, so a non-inheritance target answers ``None`` by the same
    test.
    """
    target = query.get("target") if isinstance(query, dict) else None
    if not isinstance(target, str):
        return None
    family = Family(case.model.entity_defs)
    if target not in family.defs:
        return None
    if not is_abstract(family.defs[target]):
        return None
    return _AbstractFamilyPosition(family, target, family.strategy_of(target))


def _read_effective_set(case: Case, family: Family, target_name: str) -> list[str]:
    """The effective concrete-subtype set an abstract-target read resolves over.

    The queried position is *target_name*, further constrained by the query's own
    ``narrowTo`` clause — then the narrowed selection drives the projection
    superset. A ``narrow`` inside the predicate (grouped branch predicates) leaves
    the target's full family in scope, as does an Include Path's own source guard,
    which qualifies a path's source objects rather than the read's result.
    """
    narrow_to = case.object_query.get("narrowTo")
    if isinstance(narrow_to, list):
        return family.resolve_to_set(narrow_to)
    return family.effective_concrete_set(target_name)


def _read_temporal_selections(case: Case) -> dict[str, _TemporalSelection]:
    """Return every canonical Temporal Selection on a read, keyed by dimension."""
    return _query_temporal_selections(case.object_query)


def _is_temporal_only_read(query: Any) -> bool:
    """Whether a query selects and shapes on nothing but its Temporal Selections.

    Every clause that contributes a bind of its own disqualifies it, because the
    per-branch bind vector this predicate gates is derived from the Temporal
    Selections alone: a user predicate, result narrowing, an ordering, and the cap
    each add binds the derivation does not model.
    """
    if not isinstance(query, dict):
        return False
    return (
        query.get("predicate") == {"all": {}}
        and not query.get("narrowTo")
        and not query.get("orderBy")
        and query.get("limit") is None
    )


def _expected_temporal_suffix(
    entity: Entity, selections: Mapping[str, _TemporalSelection]
) -> list[Any]:
    by_axis = {axis["dimension"]: axis for axis in entity.temporal_runtime_axes}
    suffix: list[Any] = []
    for dimension in _CANONICAL_AXIS_ORDER:
        axis = by_axis.get(dimension)
        if axis is None:
            continue
        selection = selections.get(dimension)
        if selection is None:
            raise CaseFailure(
                f"temporal selection oracle is missing {dimension!r} for {entity.canonical_name}"
            )
        if isinstance(selection, _AsOfSelection):
            if selection.coordinate == "latest":
                suffix.append(axis["infinity"])
            else:
                suffix.extend([selection.coordinate, selection.coordinate])
        elif isinstance(selection, _AsOfRangeSelection):
            suffix.extend([selection.end, selection.start])
    return suffix


def _assert_temporal_only_union_binds(case: Case, dialect: str) -> None:
    """Assert the temporal contributions of the abstract-TPCS temporal witness.

    This deliberately narrow m-sql / m-temporal-read oracle applies only to
    ``m-inheritance-093`` while its query filters on nothing but Temporal Selections.
    It derives each branch's temporal predicates in Valid-Time-first order; ``history``
    contributes none. Canonical SQL/bind goldens, compile sweeps, execution checks, and
    focused compatibility cases own complete predicate, projection, and result-clause
    bind vectors. A no-op for every case outside that temporal-only boundary.
    """
    if not case.path.stem.startswith("m-inheritance-093-") or not _is_temporal_only_read(
        case.object_query
    ):
        return
    position = _abstract_family_position(case, case.object_query)
    if position is None or position.strategy != STRATEGY_TPCS:
        return
    family = position.family
    ordered = family.canonical_concrete_order(_read_effective_set(case, family, position.target))
    branch_entities = [case.model.entity(name) for name in ordered]
    if not any(entity.is_temporal for entity in branch_entities):
        return
    selections = _read_temporal_selections(case)
    expected: list[Any] = []
    for entity in branch_entities:
        expected.extend(_expected_temporal_suffix(entity, selections))
    actual = case.statement_binds(0, dialect)
    if len(actual) != len(expected) or not all(
        _write_value_equal(want, got) for want, got in zip(expected, actual, strict=False)
    ):
        raise CaseFailure(
            f"{case.path.name}: temporal-only table-per-concrete-subtype abstract read binds "
            f"{actual!r} != temporal contributions {expected!r} — selected temporal "
            f"predicates apply per branch in Valid-Time-first order, history contributes "
            f"none, and branches repeat in alphabetical order {ordered} "
            "(m-sql / m-temporal-read)."
        )


def _assert_tph_document_partition_shape(case: Case, dialect: str) -> None:
    """Grade a TPH document `union all` as one tag-filtered branch per variant."""
    position = _abstract_family_position(case, case.object_query)
    if position is None or position.strategy != STRATEGY_TPH:
        return
    family, target_name = position.family, position.target
    target = case.model.entity(target_name)
    if not _document_layout_members(case, target)[0]:
        return
    statements = case.golden_statements(dialect)
    if not statements or " union all " not in statements[0]:
        return

    tree = sqlglot.parse_one(statements[0], read=sqlglot_dialect(dialect))
    _assert_union_all_only(case, tree)
    partition = next(tree.find_all(exp.SetOperation), tree)
    branches = _union_branch_selects(partition)
    effective = family.canonical_concrete_order(_read_effective_set(case, family, target_name))
    if len(branches) != len(effective):
        raise CaseFailure(
            f"{case.path.name}: variant-partitioned table-per-hierarchy document read "
            f"has {len(branches)} branches, expected one for each selected concrete "
            f"variant {effective} (m-sql)."
        )
    tag_column = family.tag_column_of(target_name)
    table = target.table
    if case.path.stem.startswith("m-read-lock-"):
        outer_tables = [source.name for source in tree.find_all(exp.Table)]
        base_occurrences = [name for name in outer_tables if name == table]
        if (
            not outer_tables
            or outer_tables[0] != table
            or len(base_occurrences) != len(branches) + 1
        ):
            raise CaseFailure(
                f"{case.path.name}: locking TPH partition must join one outer base Table "
                f"{table!r} to its {len(branches)} derived variant branches, got "
                f"{outer_tables!r} (m-sql / m-read-lock)."
            )
    for position, (branch, concrete) in enumerate(zip(branches, effective, strict=True)):
        tables = [source.name for source in branch.find_all(exp.Table)]
        if not tables or tables[0] != table:
            raise CaseFailure(
                f"{case.path.name}: TPH document branch {position} ({concrete}) reads "
                f"{tables[0] if tables else None!r}, expected shared Table {table!r}."
            )
        guarded = any(
            any(
                isinstance(predicate, exp.EQ)
                and any(
                    isinstance(column, exp.Column) and column.name == tag_column
                    for column in predicate.find_all(exp.Column)
                )
                for predicate in where.find_all(exp.EQ)
            )
            for where in branch.find_all(exp.Where)
        )
        if not guarded:
            raise CaseFailure(
                f"{case.path.name}: TPH document branch {position} ({concrete}) has no "
                f"equality guard on discriminator {tag_column!r}; its casts could evaluate "
                "against a sibling variant (m-sql)."
            )


def _golden_projection_columns(case: Case) -> set[str]:
    """The OUTPUT column names the case's (single) golden SELECT projects.

    Parses the golden ``select`` with sqlglot and returns each projection's output
    name — a plain ``t0.col`` projects ``col`` (the table alias is dropped), matching
    the DB result-key semantics. This reads the projection SHAPE from the SQL text,
    not a sample row, so the abstract-read projection check that consumes it is
    row-count-INDEPENDENT (a zero-row read still witnesses a dropped column).

    Postgres is parsed when present (the abstract-read goldens author it), else the
    first declared golden dialect. A ``*`` or a function-wrapped / literal projection
    contributes no static column name, so it is skipped: canonical m-sql golden SQL
    always projects explicit, qualified columns, so this only trims degenerate shapes.
    """
    dialects = case.golden_dialects
    dialect = "postgres" if "postgres" in dialects else next(iter(dialects), None)
    if dialect is None:
        return set()
    statements = case.golden_statements(dialect)
    if not statements:
        return set()
    tree = sqlglot.parse_one(statements[0], read=sqlglot_dialect(dialect))
    branches = _select_branches(tree)
    if not branches:
        return set()
    select = branches[0]
    presence_ordinals = set(_document_presence_ordinals(branches, case.model, dialect))
    return {
        name
        for ordinal, projection in enumerate(select.expressions)
        if ordinal not in presence_ordinals
        if (name := projection.output_name) and name != "*"
    }


class _DocumentMember(NamedTuple):
    """One member a Relational Document Layout keeps inside the shared Structured
    Column: what a result row calls it, where it sits in the document, and — for a
    leaf — the declared type its stored spelling decodes through."""

    column: str
    path: tuple[str, ...]
    type_spelling: str | None


class _DocumentAssignment(NamedTuple):
    """One independently derived assigned Document Path and the complete encoded
    value that lands there.

    The two positions a Parallax assignment reaches — a leaf and a whole
    occurrence — differ only in how that value is spelled, a leaf encoding against
    a whole occurrence document, so nothing downstream branches on which one it
    was: an assigned occurrence binds its subtree whole, exactly as a leaf binds
    its own value.
    """

    path: tuple[str, ...]
    value: Any


def _document_layout_members(case: Case, entity: Entity) -> tuple[str, tuple[_DocumentMember, ...]]:
    """*entity*'s Structured Column and the top-level members it carries.

    Answers ``("", ())`` for a conventional ``Columns`` entity, which is what makes
    the fan-out below inert rather than conditional at its call sites. Residency
    comes from the independently compiled Member Placements, never from the
    declaration: a one-segment Document Path over the Structured Column is a
    document-resident top-level member, and a longer one addresses a leaf inside an
    occurrence, which the occurrence's own document already carries.
    """
    layout = case.model.storage_layout.table(entity.table)
    if layout is None:
        return "", ()
    slot = next(
        (slot for slot in layout.columns if isinstance(slot.contributor, RelationalDocument)), None
    )
    if slot is None:
        return "", ()
    resident = {
        address.path[0]: placement.path
        for address, placement in layout.placements.items()
        if len(address.path) == 1 and isinstance(placement, DocumentPath) and placement.slot == slot
    }
    members = [
        _DocumentMember(attribute["column"], resident[attribute["name"]], attribute["type"])
        for attribute in entity.attributes
        if attribute["name"] in resident
    ]
    members.extend(
        _DocumentMember(occurrence["column"], resident[occurrence["name"]], None)
        for occurrence in entity.value_objects
        if occurrence["name"] in resident
    )
    return slot.column, tuple(members)


def _materialize_target_document_layout(
    case: Case, rows: list[dict[str, Any]], *, include_value_objects: bool
) -> list[dict[str, Any]]:
    """:func:`_materialize_document_layout` over the case's own read target.

    A top-level read's rows belong to its query's own ``target``; a deep fetch's
    child level does not, which is why the entity is an argument there and resolved
    here.
    """
    target_name = case.object_query.get("target")
    if not isinstance(target_name, str):
        return rows
    return _materialize_document_layout(
        case,
        case.model.entity(target_name),
        rows,
        include_value_objects=include_value_objects,
    )


def _materialize_target_tph_document_layout(
    case: Case, rows: list[dict[str, Any]], *, include_value_objects: bool
) -> list[dict[str, Any]]:
    """Decode an abstract TPH document only after its raw tag resolves the variant."""
    position = _abstract_family_position(case, case.object_query)
    if position is None or position.strategy != STRATEGY_TPH:
        return _materialize_target_document_layout(
            case, rows, include_value_objects=include_value_objects
        )
    family, target_name = position.family, position.target
    target = case.model.entity(target_name)
    column, _members = _document_layout_members(case, target)
    if not column:
        return _materialize_target_document_layout(
            case, rows, include_value_objects=include_value_objects
        )

    tagged = _materialize_family_variant(case, rows)
    effective = _read_effective_set(case, family, target_name)
    scalar_superset = {
        member.column
        for concrete in effective
        for member in _document_layout_members(case, case.model.entity(concrete))[1]
        if member.type_spelling is not None
    }
    materialized: list[dict[str, Any]] = []
    for row in tagged:
        variant = row.get("familyVariant")
        if not isinstance(variant, str):
            materialized.append(row)
            continue
        (decoded,) = _materialize_document_layout(
            case,
            case.model.entity(variant),
            [row],
            include_value_objects=include_value_objects,
        )
        if not include_value_objects:
            for column_name in scalar_superset:
                decoded.setdefault(column_name, None)
        materialized.append(decoded)
    return materialized


def _materialize_document_layout(
    case: Case,
    entity: Entity,
    rows: list[dict[str, Any]],
    *,
    include_value_objects: bool,
) -> list[dict[str, Any]]:
    """Fan a Relational Document Layout read's Structured Column out into the members
    it was asked for, under the result names a ``Columns`` layout would have used.

    The same shape as :func:`_materialize_family_variant`: the golden SQL projects a
    raw column and the logical result is derived from it here, because the Structured
    Column is never itself a result field (`m-sql`). Which members a read asked for
    is the result form's answer — a row-form read takes the scalars alone while an
    instance form additionally carries every applicable occurrence — so the caller
    states it rather than this deriving a second projection rule of its own.

    ``entity`` owns ``rows``, which is the level of a deep fetch they came from
    rather than always the case's read target: every level projects its own
    Structured Column and decodes its own members out of it.

    Each leaf decodes by its DECLARED type (:func:`decode_leaf`), not by the JSON
    value's own shape, and an absent key and an explicit JSON null both read as one
    absence — the single not-present state a NULL Column has.

    An owner with a Structured Column and no member inside it fans out nothing and
    still drops the column: an observation-bearing read projects it for the stored
    document itself (`m-sql` *Read projection*, rule 5), which is provenance rather
    than a result field.
    """
    column, members = _document_layout_members(case, entity)
    if not column:
        return rows
    selected = [
        member for member in members if include_value_objects or member.type_spelling is not None
    ]
    materialized: list[dict[str, Any]] = []
    for row in rows:
        if column not in row:
            return rows
        document = decode_stored(row[column])
        node = {key: value for key, value in row.items() if key != column}
        for member in selected:
            stored = _document_value(document, member.path)
            node[member.column] = (
                stored
                if member.type_spelling is None
                else decode_leaf(member.type_spelling, stored)
            )
        materialized.append(node)
    return materialized


def _document_value(document: Any, path: tuple[str, ...]) -> Any:
    """The raw stored value at *path*, or ``None`` where the walk stops."""
    current = document
    for name in path:
        if not isinstance(current, dict) or name not in current:
            return None
        current = current[name]
    return current


def _materialize_family_variant(case: Case, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Materialize ``familyVariant`` for an abstract-target table-per-hierarchy read.

    A non-inheritance / concrete-target read (or a non-TPH strategy) returns *rows*
    unchanged. For an abstract target the golden SQL projects the raw tag column and
    the full concrete superset; this asserts that projection shape, then replaces the
    tag column with the derived ``familyVariant`` (``tagValue`` -> concrete subtype
    name) so the materialized rows can be compared to ``then.rows``.
    """
    position = _abstract_family_position(case, case.object_query)
    if position is None:
        return rows  # concrete-target (or non-inheritance) read carries no familyVariant
    family, target_name = position.family, position.target
    if position.strategy == STRATEGY_TPCS:
        return _materialize_tpcs_family_variant(case, rows, family, target_name)
    if position.strategy != STRATEGY_TPH:
        return rows

    tag_column = family.tag_column_of(target_name)
    if tag_column is None:
        return rows
    if rows and all("familyVariant" in row and tag_column not in row for row in rows):
        return rows
    effective = _read_effective_set(case, family, target_name)
    expected_columns = set(position_projection(case.model.storage_layout, family, effective))
    variant_map = tag_value_to_subtype(case.model.entity_defs)

    # Projection-shape assertion, derived from the GOLDEN SQL projection rather than a
    # sample row, so it is row-count-INDEPENDENT: a zero-row abstract read still
    # witnesses a golden that drops the raw tag column or a concrete-superset column
    # (an empty result set carries no keys to inspect, but the golden text always does).
    # The tag column is checked first so a tag-only omission reports the specific tag
    # diagnostic (the superset set below also contains the tag).
    projected = _golden_projection_columns(case)
    if tag_column not in projected:
        raise CaseFailure(
            f"{case.path.name}: abstract-target read does not project the tag "
            f"column {tag_column!r}; an abstract read MUST project the raw tag column "
            f"so familyVariant can be materialized (m-sql / m-inheritance, resolved Q6)."
        )
    missing = expected_columns - projected
    if missing:
        raise CaseFailure(
            f"{case.path.name}: abstract-target read projection is missing "
            f"concrete-superset column(s) {sorted(missing)}; an abstract read MUST "
            f"project the full concrete superset PLUS the raw tag column "
            f"(m-sql / m-inheritance, resolved Q6)."
        )

    materialized: list[dict[str, Any]] = []
    for row in rows:
        new_row = _materialized_row(row)
        if tag_column not in new_row:
            raise CaseFailure(
                f"{case.path.name}: abstract-target read does not project the tag "
                f"column {tag_column!r}; familyVariant cannot be materialized."
            )
        tag_value = new_row.pop(tag_column)
        variant = variant_map.get(tag_value)
        if variant is None:
            raise CaseFailure(
                f"{case.path.name}: tag value {tag_value!r} maps to no concrete subtype "
                f"in the family (tag metadata {sorted(variant_map)})."
            )
        if "familyVariant" in new_row:
            new_row.consumed_value_object_columns.add("familyVariant")
        new_row["familyVariant"] = variant
        materialized.append(new_row)
    return materialized


def _narrow_to_variant_columns(case: Case, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Narrow each row of an INSTANCE-FORM abstract-target read to its own concrete
    variant's declared columns (m-case-format "Read targeting", the instance-form
    per-variant node shape).

    A materialized instance carries only its own branch's members — its inherited
    chain plus its own declared attributes — never a sibling branch's null-padded
    column: a `Dog` node has no `indoor` key to be null. Row-form (`then.rows`)
    keeps the full concrete-superset row unchanged (:func:`_materialize_family_variant`
    alone); this ADDITIONAL narrowing applies only where a row already carries a
    materialized ``familyVariant`` (a no-op for a concrete-target read, or a
    non-inheritance entity, whose rows carry none).
    """
    family = Family(case.model.entity_defs)
    narrowed: list[dict[str, Any]] = []
    for row in rows:
        variant = row.get("familyVariant")
        if not isinstance(variant, str):
            narrowed.append(row)
            continue
        own_columns = set(position_projection(case.model.storage_layout, family, [variant]))
        own_columns.update(
            member.column
            for member in _document_layout_members(case, case.model.entity(variant))[1]
        )
        narrowed.append(
            _MaterializedRow(
                {
                    key: value
                    for key, value in row.items()
                    if key == "familyVariant" or key in own_columns
                },
                value_object_columns=(
                    dict(row.value_object_columns) if isinstance(row, _MaterializedRow) else None
                ),
                consumed_value_object_columns=(
                    set(row.consumed_value_object_columns)
                    if isinstance(row, _MaterializedRow)
                    else None
                ),
            )
        )
    return narrowed


# The projected output column that carries the table-per-concrete-subtype
# `familyVariant` literal per `union all` branch (the settled TPCS asymmetry,
# m-sql): unlike table-per-hierarchy — which projects the RAW tag column and
# derives `familyVariant` at materialization — TPCS has no tag column, so each
# branch projects a subtype-name literal aliased to this column, which the oracle
# renames to `familyVariant` after asserting the branch shape.
_TPCS_VARIANT_COLUMN = "family_variant"


def _tpcs_result_aliases(columns: list[str]) -> list[str]:
    counts = {column: columns.count(column) for column in set(columns)}
    allocated = set(columns) | {_TPCS_VARIANT_COLUMN}
    aliases: list[str] = []
    next_internal = 0
    for column in columns:
        if counts[column] == 1 and column != _TPCS_VARIANT_COLUMN:
            aliases.append(column)
            continue
        while f"parallax_attr_{next_internal}" in allocated:
            next_internal += 1
        alias = f"parallax_attr_{next_internal}"
        allocated.add(alias)
        aliases.append(alias)
        next_internal += 1
    return aliases


def _placeholder_types(
    model: Model, columns: tuple[PositionColumn, ...]
) -> list[tuple[str, int | None] | None]:
    """Each position column's declared neutral type and length bound, in column order.

    The only declaration residue an abstract-read `union all` shape needs: the layout
    settles composition and never a SQL type, yet a branch owning no slot for a
    contributor must still render `cast(null as <declared type>)` in the same neutral
    type the branch that owns it was provisioned with.
    """
    types = contributor_types(model)
    return [types.get(column.contributor) for column in columns]


def _canonical_concrete_order(family: Family, target_name: str, effective: list[str]) -> list[str]:
    """*effective* re-sorted into the family's CANONICAL sibling-set order.

    The `union all` branch order is the effective concrete set in ALPHABETICAL order
    (by entity name, ordinal ascending — m-inheritance / m-sql), independent of an
    authored `narrow.to` spelling and of the descriptor's file layout, so
    `[Memo, Invoice]` and `[Invoice, Memo]` yield the same branch order. *target_name*
    is accepted for call-site symmetry but does not affect the order.
    """
    return family.canonical_concrete_order(effective)


def _assert_union_all_only(case: Case, tree: Any) -> None:
    """Reject any set operation in *tree* that is not a canonical `union all` (m-sql).

    The TPCS abstract-read lowering is `union all` — a plain `union` silently
    de-duplicates rows (changing the read's semantics) and `intersect` / `except` are
    never emitted. sqlglot parses all of these into `exp.SetOperation`, so the branch
    walk below would happily accept them; this guard makes the oracle reject a golden
    that used the wrong set operation, mirroring the normalizer's canonicality gate.
    """
    for setop in tree.find_all(exp.SetOperation):
        if not is_union_all(setop):
            raise CaseFailure(
                f"{case.path.name}: table-per-concrete-subtype abstract read uses set "
                f"operation {setop.key!r}, not `union all`; only `union all` is a "
                f"canonical TPCS lowering (a plain `union` de-duplicates rows; m-sql)."
            )


def _union_branch_selects(tree: Any) -> list[Any]:
    """The leaf SELECT branches of a (possibly nested) `union all`, in order.

    A plain SELECT is a single branch; a `SetOperation` yields its arms left to
    right (``A union all B union all C`` nests left, so the walk restores authored
    branch order). Callers assert `union all`-only separately (:func:`_assert_union_all_only`).
    """
    if isinstance(tree, exp.Select):
        return [tree]
    if isinstance(tree, exp.SetOperation):
        return _union_branch_selects(tree.this) + _union_branch_selects(tree.expression)
    return []


def _projection_expr(projection: Any) -> Any:
    """The underlying expression of a (possibly aliased) projection."""
    return projection.this if isinstance(projection, exp.Alias) else projection


def _string_literal_value(projection: Any) -> str | None:
    """The string value of a (possibly aliased) string-literal projection, else None."""
    node = _projection_expr(projection)
    if isinstance(node, exp.Literal) and node.is_string:
        return node.this
    return None


def _assert_branch_projection_shape(
    case: Case,
    branch: Any,
    position: int,
    name: str,
    superset: list[str],
    slots: tuple[ColumnSlot | None, ...],
    placeholder_types: list[tuple[str, int | None] | None],
    dialect: str,
) -> None:
    """Assert one `union all` branch's per-column projection SHAPE (m-sql).

    For every superset column (all but the trailing `familyVariant` literal): a column
    the branch OWNS A SLOT for MUST be a real column reference (``t0.<col>``); a column
    it owns no slot for MUST be exactly ``cast(null as <type>)`` in the column's
    declared type mapped to *dialect* (`placeholder_cast_type`, m-dialect). This closes
    the gap where a bare `null <col>` (no cast) or a wrong-typed cast shares the owned
    column's output name and would otherwise pass the name-only check.
    """
    engine = sqlglot_dialect(dialect)
    for column_index, (column, slot, placeholder_type) in enumerate(
        zip(superset, slots, placeholder_types, strict=True)
    ):
        node = _projection_expr(branch.expressions[column_index])
        if slot is not None:
            if not isinstance(node, exp.Column):
                raise CaseFailure(
                    f"{case.path.name}: `union all` branch {position} ({name!r}) "
                    f"projects column {column!r} as {node.sql(dialect=engine)!r}, but "
                    f"{column!r} is APPLICABLE to {name!r} (its branch owns the slot) "
                    f"and MUST be a real column reference (m-sql)."
                )
            continue
        # Slotless in this branch: exactly `cast(null as <declared type>)` for this dialect.
        if placeholder_type is None:
            raise CaseFailure(
                f"{case.path.name}: framework-owned column {column!r} is absent from "
                f"the concrete branch {name!r}"
            )
        expected = exp.DataType.build(
            placeholder_cast_type(*placeholder_type, dialect),
            dialect=engine,
        )
        if not (isinstance(node, exp.Cast) and isinstance(node.this, exp.Null)):
            raise CaseFailure(
                f"{case.path.name}: `union all` branch {position} ({name!r}) projects "
                f"NON-applicable column {column!r} as {node.sql(dialect=engine)!r}, but "
                f"it MUST be a `cast(null as {expected.sql(dialect=engine)})` placeholder "
                f"(a bare `null` gives the union an untyped column; m-sql / m-dialect)."
            )
        if node.to != expected:
            raise CaseFailure(
                f"{case.path.name}: `union all` branch {position} ({name!r}) casts the "
                f"NON-applicable column {column!r} placeholder to "
                f"{node.to.sql(dialect=engine)!r}, expected the declared type "
                f"{expected.sql(dialect=engine)!r} for dialect {dialect!r} "
                f"(m-sql / m-dialect)."
            )


def _tpcs_position_branches(
    case: Case, family: Family, ordered: list[str], view: PositionLayoutView
) -> list[tuple[PositionBranch, str]]:
    """The position's branches paired with the subtype name each one's literal spells.

    A table-per-concrete-subtype position owns exactly one branch per concrete Table,
    so the layout's branch sequence IS the `union all` branch order; each branch is
    paired with the family's rendered spelling of its single row owner, which is what
    the golden's `familyVariant` literal carries.
    """
    rendered = {family.defs.canonical_key(name): name for name in ordered}
    pairs = [
        (branch, rendered[branch.concrete_entities[0]])
        for branch in view.branches
        if len(branch.concrete_entities) == 1 and branch.concrete_entities[0] in rendered
    ]
    if len(pairs) != len(ordered):
        raise CaseFailure(
            f"{case.path.name}: the storage layout maps the effective concrete set "
            f"{ordered} onto {len(view.branches)} branch table(s); a table-per-concrete-"
            f"subtype abstract read requires exactly one branch per concrete Table."
        )
    return pairs


def _assert_tpcs_union_shape(
    case: Case,
    view: PositionLayoutView,
    position_branches: list[tuple[PositionBranch, str]],
) -> None:
    """Assert the table-per-concrete-subtype abstract-read `union all` shape (m-sql).

    The read-side inheritance oracle for TPCS (the counterpart of the TPH
    projection-shape check). The layout position settles the physical facts — the
    branch count and order, the Table each branch reads, the one logical contributor
    sequence every branch aligns to, and each branch's slot-or-absence entry per
    contributor. This asserts the SQL renderings layered over them, which are never
    layout concerns: the collision-safe result aliases, each branch's per-column shape
    (an owned slot is a real reference; a slotless position is a
    `cast(null as <declared type>)` placeholder in that dialect's type), and each
    branch's `familyVariant` literal (the concrete subtype NAME). EVERY declared golden
    dialect is checked (so a MariaDB `char` cast is asserted with the MariaDB type
    mapping, not the Postgres one). Parsed from the golden text, so it is
    row-count-independent — a zero-row abstract read still witnesses a mis-ordered
    branch, a dropped superset column, a bare/mis-typed placeholder, or a wrong literal.
    """
    superset = list(view.column_spellings)
    placeholder_types = _placeholder_types(case.model, view.columns)
    expected_columns = [*_tpcs_result_aliases(superset), _TPCS_VARIANT_COLUMN]
    for dialect in sorted(case.golden_dialects):
        statements = case.golden_statements(dialect)
        if not statements:
            continue
        tree = sqlglot.parse_one(statements[0], read=sqlglot_dialect(dialect))
        _assert_union_all_only(case, tree)
        branches = _union_branch_selects(tree)
        if len(branches) != len(position_branches):
            raise CaseFailure(
                f"{case.path.name}: table-per-concrete-subtype abstract read lowers to "
                f"{len(position_branches)} `union all` branch(es) (the effective concrete "
                f"set {[name for _, name in position_branches]}), but the {dialect} golden "
                f"has {len(branches)}."
            )
        for position, (branch, (position_branch, name)) in enumerate(
            zip(branches, position_branches, strict=True)
        ):
            table = position_branch.layout.table
            branch_tables = [source.name for source in branch.find_all(exp.Table)]
            if not branch_tables or branch_tables[0] != table:
                raise CaseFailure(
                    f"{case.path.name}: `union all` branch {position} must read from "
                    f"{table!r} (the alphabetical-order concrete subtype {name!r}), got "
                    f"{branch_tables[0] if branch_tables else None!r}."
                )
            presence_ordinals = set(_document_presence_ordinals(branches, case.model, dialect))
            logical_projections = [
                projection
                for ordinal, projection in enumerate(branch.expressions)
                if ordinal not in presence_ordinals
            ]
            out_columns = [projection.output_name for projection in logical_projections]
            if out_columns != expected_columns:
                raise CaseFailure(
                    f"{case.path.name}: `union all` branch {position} ({name!r}) projects "
                    f"{out_columns}, not the stable superset + familyVariant literal "
                    f"{expected_columns} (the position's one contributor sequence, then "
                    f"familyVariant; m-sql)."
                )
            logical_branch = branch.copy()
            logical_branch.set("expressions", logical_projections)
            _assert_branch_projection_shape(
                case,
                logical_branch,
                position,
                name,
                superset,
                position_branch.slots,
                placeholder_types,
                dialect,
            )
            literal = _string_literal_value(logical_projections[-1])
            if literal != name:
                raise CaseFailure(
                    f"{case.path.name}: `union all` branch {position} projects familyVariant "
                    f"literal {literal!r}, expected the concrete subtype name {name!r} "
                    f"(TPCS projects familyVariant as a per-branch literal; m-sql)."
                )


def _materialize_tpcs_family_variant(
    case: Case, rows: list[dict[str, Any]], family: Family, target_name: str
) -> list[dict[str, Any]]:
    """Rename the projected `familyVariant` literal column for a TPCS abstract read.

    Asserts the `union all` branch/projection shape, then renames each row's
    ``family_variant`` (the per-branch subtype-name literal) to ``familyVariant`` so
    the materialized rows compare against ``then.rows`` — the TPCS counterpart of the
    TPH tag-to-variant materialization (m-inheritance / m-sql). A row observed through
    a collision-safe internal alias is restored to the physical spelling its OWN
    branch's slot carries, and an alias standing for a slot that branch does not own is
    dropped.
    """
    effective = _read_effective_set(case, family, target_name)
    ordered = _canonical_concrete_order(family, target_name, effective)
    view = position_view(case.model.storage_layout, family, effective)
    if view is None:
        raise CaseFailure(
            f"{case.path.name}: the storage layout resolves no position for the effective "
            f"concrete set {ordered}; a table-per-concrete-subtype abstract read must map "
            f"onto one family's canonical concrete selection."
        )
    position_branches = _tpcs_position_branches(case, family, ordered, view)
    _assert_tpcs_union_shape(case, view, position_branches)
    superset = list(view.column_spellings)
    result_aliases = _tpcs_result_aliases(superset)
    column_counts = {column: superset.count(column) for column in set(superset)}
    slots_by_variant = {name: branch.slots for branch, name in position_branches}
    layouts_by_variant = {name: branch.layout for branch, name in position_branches}

    materialized: list[dict[str, Any]] = []
    for row in rows:
        new_row = _materialized_row(row)
        if _TPCS_VARIANT_COLUMN not in new_row:
            raise CaseFailure(
                f"{case.path.name}: table-per-concrete-subtype abstract read does not "
                f"project the {_TPCS_VARIANT_COLUMN!r} literal; familyVariant cannot be "
                f"materialized (m-sql)."
            )
        if "familyVariant" in new_row:
            new_row.consumed_value_object_columns.add("familyVariant")
        variant = new_row.pop(_TPCS_VARIANT_COLUMN)
        slots = slots_by_variant.get(variant)
        if slots is None:
            raise CaseFailure(
                f"{case.path.name}: {_TPCS_VARIANT_COLUMN!r} literal {variant!r} names no "
                f"branch of the effective concrete set {sorted(slots_by_variant)}."
            )
        for slot, column, result_alias in zip(slots, superset, result_aliases, strict=True):
            if (
                result_alias in new_row
                and result_alias != column
                and (column_counts[column] == 1 or slot is not None)
            ):
                new_row[column] = new_row.pop(result_alias)
            elif column_counts[column] > 1 and slot is None:
                new_row.pop(result_alias, None)
        new_row["familyVariant"] = variant
        new_row = _materialize_tpcs_document_row(case, layouts_by_variant[variant], new_row)
        materialized.append(new_row)
    return materialized


def _materialize_tpcs_document_row(
    case: Case, layout: TableLayout, row: dict[str, Any]
) -> dict[str, Any]:
    """Decode one concrete TPCS branch through that branch's placements."""
    slot = next(
        (slot for slot in layout.columns if isinstance(slot.contributor, RelationalDocument)), None
    )
    if slot is None or slot.column not in row:
        return row
    document = decode_stored(row[slot.column])
    materialized = {key: value for key, value in row.items() if key != slot.column}
    entities = {entity.canonical_name: entity for entity in case.model.entities}
    for candidate in case.model.storage_layout.tables:
        if candidate.contribution(slot.contributor) is None:
            continue
        for address, placement in candidate.placements.items():
            if len(address.path) != 1 or not isinstance(placement, DocumentPath):
                continue
            declaration = entities[address.owner]
            name = address.path[0]
            attribute = next(
                (item for item in declaration.attributes if item["name"] == name), None
            )
            if attribute is not None:
                materialized.setdefault(attribute["column"], None)
    for address, placement in layout.placements.items():
        if len(address.path) != 1 or not isinstance(placement, DocumentPath):
            continue
        entity = entities[address.owner]
        name = address.path[0]
        attribute = next((item for item in entity.attributes if item["name"] == name), None)
        occurrence = next((item for item in entity.value_objects if item["name"] == name), None)
        stored = _document_value(document, placement.path)
        if attribute is not None:
            materialized[attribute["column"]] = decode_leaf(attribute["type"], stored)
        elif occurrence is not None:
            materialized[occurrence["column"]] = stored
    return materialized


def _sorted_by_order_keys(
    rows: list[dict[str, Any]],
    sort_spec: list[tuple[str, bool, bool]],
) -> list[dict[str, Any]]:
    """Return *rows* sorted by *sort_spec* — a list of
    ``(column, descending, nulls_first)`` triples evaluated left to right. Stable:
    rows tied on every key keep input order. A key's Null Placement is
    independent of its direction (m-deep-fetch), so ``nulls_first`` is not derived
    from ``descending``; an authored placement is what the caller passes and an
    omitted one arrives already defaulted to nulls-last.
    """

    def compare(row_a: dict[str, Any], row_b: dict[str, Any]) -> int:
        for column, descending, nulls_first in sort_spec:
            left, right = row_a[column], row_b[column]
            if left == right:
                continue
            if left is None:
                return -1 if nulls_first else 1
            if right is None:
                return 1 if nulls_first else -1
            ordered = -1 if left < right else 1
            return -ordered if descending else ordered
        return 0

    return sorted(rows, key=functools.cmp_to_key(compare))


def _assert_child_ordering(
    case_name: str,
    steps: list[_FetchStep],
    children_by_step: dict[_HopKey, dict[Any, list[dict[str, Any]]]],
) -> None:
    """Assert each ordered to-many level returned its children in the declared order.

    A to-many relationship that declares ``orderBy`` requires the per-level child
    query to emit ``ORDER BY`` over the declared keys (m-navigate), so the rows the DB
    returned — preserved in SQL order inside each parent's bucket — must already
    equal those rows sorted by the declared keys/directions. The harness derives
    the expected order from the model (an independent oracle) rather than trusting
    the authored ``then.graph`` order. A relationship with no ``orderBy`` is
    skipped (its order is unspecified). NULL values sort where the key's authored
    ``nulls`` asks, and where it is omitted they sort LAST — the canonical
    placement in either direction (m-deep-fetch); two NULLs are equal and fall
    through to the next key. Residual ties beyond the declared keys keep
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
                _column_of(step.child_entity, key["attribute"]),
                key.get("direction", "asc") == "desc",
                key.get("nulls", "last") == "first",
            )
            for key in step.order_by
        ]
        bucket = children_by_step.get(step.hop_key, {})
        for parent_key, rows in bucket.items():
            if not rows:
                continue
            missing = [column for column, _, _ in sort_spec if column not in rows[0]]
            if missing:
                raise CaseFailure(
                    f"{case_name}: {step.rel_ref} orderBy column(s) {missing!r} are "
                    f"not in the child query's projection, so the order cannot be "
                    f"verified; project them in the child SELECT."
                )
            expected = _sorted_by_order_keys(rows, sort_spec)
            if rows != expected:
                cols = [column for column, _, _ in sort_spec]
                got = [[row[c] for c in cols] for row in rows]
                want = [[row[c] for c in cols] for row in expected]
                raise CaseFailure(
                    f"{case_name}: {step.rel_ref} children for parent "
                    f"{parent_key!r} are not in declared orderBy order "
                    f"(keys {cols!r}). got {got!r}, expected {want!r}."
                )


def _guarded_parents(
    case_name: str, step: _FetchStep, parents: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The parent rows a path-root guard admits into *step* (m-deep-fetch).

    A root guard changes no statement of its own and populates no view of its own:
    it selects which already-fetched ROOT objects the hop starts from, so the hop's
    child statement is keyed by exactly those objects' gathered keys. Selection is
    by the root row's own concrete subtype, which an abstract-target read carries as
    ``familyVariant`` — a guard can only ever be a proper subset of a POLYMORPHIC
    position, so a root read that projects no variant cannot be guarded at all.
    """
    if step.root_guard is None:
        return parents
    admitted = set(step.root_guard)
    for row in parents:
        if "familyVariant" not in row:
            raise CaseFailure(
                f"{case_name}: the path-root guard {list(step.root_guard)!r} on "
                f"{step.rel_ref} cannot select root objects — the root read carries no "
                f"`familyVariant`, so its own position is not polymorphic "
                f"(m-inheritance / m-deep-fetch)."
            )
    return [row for row in parents if row["familyVariant"] in admitted]


def _assert_deep_fetch(case: Case, db: DatabaseProvider) -> None:
    """Execute each level, assemble the object graph, compare to then.graph.

    The contract proven here is N+1 elimination: the root plus at most one
    statement per relationship level (never one-per-parent). A child level is
    executed only when the previous level produces parent keys; an empty parent
    key set elides that child SQL entirely. Executed child levels are keyed by
    the DISTINCT parent keys gathered from THIS hop's own parent hop — narrowed to
    the root objects a path-root guard admits, which is the only place a guard is
    observable — and the children are fanned back out in memory. Rows are held per
    HOP rather than per entity, because two branches may reach one entity through
    different guards or different parents and a deeper hop descends from exactly
    one of them.
    """
    dialect = db.dialect
    query = case.object_query
    statements = case.golden_statements(dialect)
    steps = _fetch_steps(case.model, query)

    # Level 0: the root query. An abstract-target root resolves each row's own
    # concrete subtype into `familyVariant` exactly as a flat abstract read does —
    # both because the graph's root nodes carry it and because a path-root guard
    # selects the participating roots by it.
    root_binds = case.statement_binds(0, dialect)
    # Every level of a deep fetch is instance-form and fans its own Structured Column
    # out into its own members (a no-op under `Columns` layout). The join columns the
    # levels are keyed on are direct under either layout, so the fan-out changes what
    # a node CARRIES and never how the levels are matched up.
    root_rows = _materialize_target_tph_document_layout(
        case,
        _query_rows(case, db, statements[0], root_binds),
        include_value_objects=True,
    )
    root_rows = _materialize_family_variant(case, root_rows)

    levels = [
        (statements[index], case.statement_binds(index, dialect))
        for index in range(1, len(statements))
    ]
    children_by_step = _execute_fetch_levels(
        case, db, "then.statements", query, steps, root_rows, levels
    )

    # Assemble the graph: attach each child set under its relationship name on
    # the parent rows, following the declared paths.
    assembled = _assemble_graph(case, query, steps, root_rows, children_by_step)

    expected = case.expected_graph or {}
    if not _graphs_equal(assembled, expected, case.model):
        raise CaseFailure(
            f"{case.path.name}: assembled graph != then.graph.\n"
            f"  assembled: {assembled!r}\n"
            f"  expected:  {expected!r}"
        )

    # referenceSql (a single naive statement) is the independent oracle for the
    # ROOT row set of the deep fetch.
    reference_sql = case.reference_sql_for(db.dialect)
    if reference_sql is not None:
        reference_rows = _materialize_family_variant(case, db.query(reference_sql))
        root_projection = [_project_like(r, root_rows) for r in reference_rows]
        if not _rows_equal(root_projection, root_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql root rows != then.statements root rows.\n"
                f"  reference: {reference_rows!r}\n"
                f"  golden:    {root_rows!r}"
            )


def _execute_fetch_levels(
    case: Case,
    db: DatabaseProvider,
    source: str,
    query: dict[str, Any],
    steps: list[_FetchStep],
    root_rows: list[dict[str, Any]],
    levels: list[tuple[str, list[Any]]],
) -> dict[_HopKey, dict[Any, list[dict[str, Any]]]]:
    """Execute one Object Query's child levels and bucket each hop's rows by parent key.

    The N+1-elimination contract, executed once for both positions an Include
    Path is authored at — a read case's own ``then.statements`` and a scenario
    read step's own ``statements``, named by *source* in every diagnostic. A
    child level runs only when the previous level produced parent keys; an empty
    parent key set elides that child SQL entirely, and a level the golden lists
    but no parent reaches is unused SQL the case is refused for. Each executed
    level's authored binds are cross-checked against the keys, tag values, and
    propagated as-of coordinates the harness derives independently, so a dropped
    IN list, a missing table-per-hierarchy tag filter, or a lost as-of
    propagation fails the case rather than passing on the DB's own answer. Rows
    are held per HOP rather than per entity, because two branches may reach one
    entity through different guards or different parents and a deeper hop
    descends from exactly one of them.
    """
    dialect = db.dialect
    root_pins = _root_asof_pins(query)

    # rows_by_hop[hop key] -> the result-rows that hop fetched.
    rows_by_hop: dict[_HopKey, list[dict[str, Any]]] = {}

    # Execute each hop once, keyed by gathered parent keys, bucketed by hop identity.
    children_by_step: dict[_HopKey, dict[Any, list[dict[str, Any]]]] = {}
    statement_index = 0
    for step in steps:
        source_rows = root_rows if step.parent_hop is None else rows_by_hop[step.parent_hop]
        parents = _guarded_parents(case.path.name, step, source_rows)
        parent_col = _column_of(step.parent_entity, step.parent_attr)
        parent_keys = sorted(
            {_coerce_identity_key(p[parent_col]) for p in parents if p.get(parent_col) is not None}
        )

        if not parent_keys:
            rows_by_hop[step.hop_key] = []
            children_by_step[step.hop_key] = {}
            continue

        if statement_index >= len(levels):
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) has no child statement "
                f"for {step.view_key}, but the previous level gathered parent "
                f"keys {parent_keys!r}."
            )

        # Bind layout per child level: the IN-list of gathered parent keys, then the
        # polymorphic hop's tag binds (table-per-hierarchy `kind = ?` / `in (?, …)`
        # over the effective set, alphabetical order), then the propagated as-of binds.
        level_sql, raw_authored = levels[statement_index]
        in_slice = raw_authored[: len(parent_keys)]
        rest = list(raw_authored[len(parent_keys) :])
        tag_slice = rest[: len(step.tag_binds)]
        asof_suffix = rest[len(step.tag_binds) :]
        if sorted(_coerce_identity_key(b) for b in in_slice) != parent_keys:
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) level {statement_index + 1} "
                f"({step.view_key}) IN-list binds {in_slice!r} != gathered parent "
                f"keys {parent_keys!r}. The child level MUST be keyed by exactly "
                f"the parents from the previous level (the N+1-eliminating IN list)."
            )
        if list(tag_slice) != list(step.tag_binds):
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) level {statement_index + 1} "
                f"({step.view_key}) tag binds {tag_slice!r} != the effective-set tag "
                f"values {step.tag_binds!r}. A polymorphic table-per-hierarchy hop over a "
                f"proper subset MUST filter its shared-table read by the effective set's "
                f"tag values (m-navigate / m-inheritance)."
            )

        # As-of propagation oracle: the root pin propagates per-hop, matched by
        # axis, to each temporal child level. The harness derives the child's
        # as-of binds independently and asserts the authored suffix matches, so a
        # dropped/wrong propagated as-of fails the case. A non-temporal child has
        # an empty suffix (no as-of term).
        expected_suffix = (
            _expected_pin_suffix(step.child_entity, root_pins)
            if step.child_entity.is_temporal
            else []
        )
        if list(asof_suffix) != expected_suffix:
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) level {statement_index + 1} "
                f"({step.view_key}) as-of suffix {asof_suffix!r} != the propagated "
                f"as-of binds {expected_suffix!r}. The root pin MUST propagate to "
                f"this temporal child (matched by axis), appended after the IN list."
            )

        child_rows = _query_rows(
            case,
            db,
            level_sql,
            list(parent_keys) + list(step.tag_binds) + expected_suffix,
        )
        # A polymorphic (multi-concrete, table-per-hierarchy) hop projects the raw tag
        # column; materialize each row's `familyVariant` from the tag map (never a
        # projected SQL column), exactly as an abstract-target flat read does (Q6).
        if step.polymorphic and step.tag_column is not None:
            child_rows = [_materialize_hop_variant(case, step, row) for row in child_rows]
            child_rows = [
                _materialize_document_layout(
                    case,
                    case.model.entity(row["familyVariant"]),
                    [row],
                    include_value_objects=True,
                )[0]
                for row in child_rows
            ]
        else:
            child_rows = _materialize_document_layout(
                case,
                step.child_entity,
                child_rows,
                include_value_objects=True,
            )
        rows_by_hop[step.hop_key] = child_rows

        child_col = _column_of(step.child_entity, step.child_attr)
        bucket: dict[Any, list[dict[str, Any]]] = {}
        for row in child_rows:
            bucket.setdefault(_coerce_identity_key(row[child_col]), []).append(row)
        children_by_step[step.hop_key] = bucket
        statement_index += 1

    _assert_child_ordering(case.path.name, steps, children_by_step)

    if statement_index != len(levels):
        raise CaseFailure(
            f"{case.path.name}: {source} ({dialect}) lists "
            f"{len(levels) - statement_index} unused deep-fetch child "
            f"statement(s). Child SQL MUST be omitted after a level gathers no "
            f"parent keys."
        )
    return children_by_step


def _graphs_root_entity(case: Case) -> Entity:
    """The entity a `history` / `asOfRange` graph read is rooted at.

    A milestone-set graph read (`then.graphs`) is a flat temporal read (no deep-fetch
    includes — history-with-includes is out of scope for both v1 slices), so the root
    is the read's own query ``target``.
    """
    return case.model.entity(case.object_query["target"])


def _assert_graphs(case: Case, db: DatabaseProvider) -> None:
    """Execute a `history` / `asOfRange` snapshot read and assert its per-milestone
    edge-pinned graphs (m-snapshot-read, Q5a).

    The single root `history` / `asOfRange` statement returns the FULL milestone set
    in one query. Each ``then.graphs`` entry declares a milestone ``pin`` — its OWN
    edge coordinate (the milestone's from-instant per as-of axis), never a shared root
    pin — and the graph materialized at it. The harness partitions the root rows by
    edge pin (matching each pin's per-axis from-instant to the row's from-column) and
    asserts each partition equals its declared graph, so ``history`` yields one
    independently edge-pinned graph per milestone and ``asOfRange`` one per overlapping
    milestone. The declared graphs PARTITION the milestone set: every root row MUST
    belong to exactly one declared graph and every declared pin MUST match at least one
    row (a stray row, an unmatched pin, OR a row claimed by two graphs — overlapping /
    duplicate pins — is a loud failure), and ``referenceSql`` independently cross-checks
    the whole milestone set.

    (History with deep-fetch includes is out of scope for both v1 slices, so a graph
    carries no child levels — there is no per-level child SQL to reuse the deep-fetch
    per-level assertions on. A graph node authored with a nested relationship key would
    fail the value comparison, since the root-only assembly carries only the root
    projection.)
    """
    dialect = db.dialect
    statements = case.golden_statements(dialect)
    graph_specs = case.expected_graphs or []
    root_entity = _graphs_root_entity(case)

    # Level 0: the single history / asOfRange query — every milestone in one round trip.
    root_rows = _query_rows(case, db, statements[0], case.statement_binds(0, dialect))

    # referenceSql (an independent naive statement) cross-checks the whole milestone set.
    reference_sql = case.reference_sql_for(dialect)
    if reference_sql is not None:
        reference_rows = [_project_like(r, root_rows) for r in db.query(reference_sql)]
        if not _rows_equal(reference_rows, root_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql rows != then.statements milestone rows.\n"
                f"  reference: {reference_rows!r}\n"
                f"  golden:    {root_rows!r}"
            )

    # An as-of attribute's from-column is the edge coordinate a pin keys on (per axis,
    # keyed by the ATTRIBUTE name the pin uses — `transaction-time` / `valid-time`).
    from_column_by_attr = {
        axis["dimension"]: axis["start_column"] for axis in root_entity.temporal_runtime_axes
    }

    # The declared graphs PARTITION the milestone set: every root row belongs to
    # EXACTLY ONE graph, so the pins must be pairwise disjoint. `owner` records which
    # graph index claimed each root-row index; a second claim on any row is a loud
    # overlap failure (this is the fundamental partition guarantee — it catches both a
    # literally-duplicate pin dict and two distinct pins that happen to match the same
    # rows). `seen_pins` additionally rejects an identical pin dict up front for a
    # sharper diagnostic than the row-overlap message.
    owner: dict[int, int] = {}
    seen_pins: dict[tuple[tuple[str, str], ...], int] = {}
    for gi, spec in enumerate(graph_specs):
        pin = spec["pin"]
        expected = spec["graph"]
        for attr_name in pin:
            if attr_name not in from_column_by_attr:
                raise CaseFailure(
                    f"{case.path.name}: then.graphs[{gi}].pin names as-of attribute "
                    f"{attr_name!r}, which {root_entity.name} does not declare "
                    f"(declared: {sorted(from_column_by_attr)})."
                )
        pin_key = tuple(sorted(pin.items()))
        if pin_key in seen_pins:
            raise CaseFailure(
                f"{case.path.name}: then.graphs[{gi}] repeats the pin declared by "
                f"then.graphs[{seen_pins[pin_key]}] ({pin!r}); each milestone MUST be "
                f"edge-pinned by exactly one graph — the pins MUST be pairwise disjoint."
            )
        seen_pins[pin_key] = gi
        group = [
            index
            for index, row in enumerate(root_rows)
            if all(str(row.get(from_column_by_attr[name])) == date for name, date in pin.items())
        ]
        if not group:
            raise CaseFailure(
                f"{case.path.name}: then.graphs[{gi}] pin {pin!r} matched no milestone "
                f"row; each declared graph MUST be edge-pinned to a real milestone's "
                f"from-instant."
            )
        overlap = [i for i in group if i in owner]
        if overlap:
            shared = [_normalize_row(root_rows[i]) for i in overlap]
            raise CaseFailure(
                f"{case.path.name}: then.graphs[{gi}] (pin {pin!r}) claims milestone "
                f"row(s) already claimed by then.graphs[{owner[overlap[0]]}] — the "
                f"declared graphs MUST partition the milestone set, so every row belongs "
                f"to EXACTLY ONE graph (no overlapping pins).\n"
                f"  shared: {shared!r}"
            )
        for index in group:
            owner[index] = gi
        assembled = {
            root_entity.name: [_graph_node(case.model, root_entity, root_rows[i]) for i in group]
        }
        if not _graphs_equal(assembled, expected, case.model):
            raise CaseFailure(
                f"{case.path.name}: then.graphs[{gi}] (pin {pin!r}) assembled graph "
                f"!= expected.\n"
                f"  assembled: {assembled!r}\n"
                f"  expected:  {expected!r}"
            )

    if len(owner) != len(root_rows):
        stray = [row for index, row in enumerate(root_rows) if index not in owner]
        raise CaseFailure(
            f"{case.path.name}: {len(stray)} milestone row(s) matched no then.graphs "
            f"pin — every milestone MUST be edge-pinned into exactly one graph.\n"
            f"  unmatched: {stray!r}"
        )


def _project_like(row: dict[str, Any], template_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep only the columns the golden root projection carries (oracle compare)."""
    if not template_rows:
        return row
    keep = set(template_rows[0])
    return {k: v for k, v in row.items() if k in keep}


def _materialize_hop_variant(case: Case, step: _FetchStep, row: dict[str, Any]) -> dict[str, Any]:
    """Replace a polymorphic deep-fetch child row's raw tag column with ``familyVariant``.

    The table-per-hierarchy analogue of :func:`_materialize_family_variant` for a
    deep-fetch hop: a polymorphic view projects the raw tag column so the harness can
    derive the concrete subtype name; this pops it and inserts ``familyVariant``. A
    tag value that maps to no concrete subtype is a loud failure.
    """
    new_row = dict(row)
    if step.tag_column not in new_row:
        raise CaseFailure(
            f"{case.path.name}: polymorphic hop {step.view_key} does not project the tag "
            f"column {step.tag_column!r}; familyVariant cannot be materialized (m-inheritance)."
        )
    tag_value = new_row.pop(step.tag_column)
    variant = step.variant_map.get(tag_value)
    if variant is None:
        raise CaseFailure(
            f"{case.path.name}: hop {step.view_key} tag value {tag_value!r} maps to no "
            f"concrete subtype (tag metadata {sorted(step.variant_map)})."
        )
    new_row["familyVariant"] = variant
    return new_row


def _assemble_graph(
    case: Case,
    query: dict[str, Any],
    steps: list[_FetchStep],
    root_rows: list[dict[str, Any]],
    children_by_step: dict[_HopKey, dict[Any, list[dict[str, Any]]]],
) -> dict[str, list[dict[str, Any]]]:
    """Build the root-keyed object graph following the deep-fetch paths.

    Each path is walked hop by hop; at each hop the child rows for a given parent are
    attached under the hop's VIEW KEY — the ordinary relationship name for a broad
    hop, the derived ``<rel>[<Concrete>,<Concrete>]`` for a narrowed one (m-deep-fetch).
    A path-root guard contributes no key of its own: it withholds the path's whole
    attachment from the root objects it excludes, so an unguarded object's view stays
    UNSET rather than empty — the observable difference between "no such related row"
    and "this object never participated".
    """
    root_entity = _deepfetch_root_entity(case.model, query)
    family = Family(case.model.entity_defs)
    root_position = _deepfetch_root_position(query)
    step_by_hopkey = {step.hop_key: step for step in steps}

    # Build per-view row registries keyed by primary key so a shared hop (e.g.
    # Order.items consumed by two paths) reuses the same child objects, while two
    # DISTINCT views over one relationship (a broad and a narrowed hop, or two
    # narrowed hops) keep independent node sets. Nodes key by (view, entity, pk).
    def pk_attr(entity: Entity) -> str:
        for attribute in entity.attributes:
            if attribute.get("primaryKey"):
                return attribute["name"]
        return entity.attributes[0]["name"]

    registry: dict[tuple[str, str, Any], dict[str, Any]] = {}

    def node_for(view: str, entity: Entity, raw_row: dict[str, Any]) -> dict[str, Any]:
        pk_col = _column_of(entity, pk_attr(entity))
        key = (view, entity.name, _coerce_identity_key(raw_row[pk_col]))
        if key not in registry:
            # Instance-form graph node: decode + project each top-level value-object
            # document column into its declared composite, at EVERY level (root AND
            # child), so a VO-bearing deep-fetch child materializes its document with
            # the owner exactly as a root value-object read does (m-value-object /
            # m-sql "Read projection", slot 4). A VO-free entity (every orders-model
            # entity) has no value objects, so this is byte-identical to the prior
            # `_normalize_row` — no existing deep-fetch graph changes.
            registry[key] = _graph_node(case.model, entity, raw_row)
        return registry[key]

    root_nodes = [node_for("", root_entity, r) for r in root_rows]

    for path in _deepfetch_paths_raw(query):
        root_source = resolve_root_source_set(family, root_position, path)
        parent_nodes = root_nodes
        parent_hop: _HopKey | None = None
        for index, segment in enumerate(path["segments"]):
            hop = _resolve_hop(
                family, segment, parent=parent_hop, root_source=root_source if index == 0 else None
            )
            step = step_by_hopkey[hop.key]
            admitted = _guarded_parents(case.path.name, step, parent_nodes)
            bucket = children_by_step[step.hop_key]

            next_nodes: list[dict[str, Any]] = []
            for parent_node in admitted:
                # A materialized node is keyed by declared member name, so the
                # correlation member is addressed by name rather than by column.
                parent_key = _coerce_identity_key(parent_node.get(step.parent_attr))
                matched = bucket.get(parent_key, [])
                child_nodes = [node_for(step.view_key, step.child_entity, c) for c in matched]
                if step.to_many:
                    parent_node[step.view_key] = child_nodes
                else:
                    parent_node[step.view_key] = child_nodes[0] if child_nodes else None
                next_nodes.extend(child_nodes)
            parent_nodes = next_nodes
            parent_hop = hop.key

    return {root_entity.name: root_nodes}


def _graphs_equal(
    left: Mapping[str, list[Any]],
    right: Mapping[str, list[Any]],
    model: Model | None = None,
) -> bool:
    """Compare assembled graphs while preserving semantic collection order.

    Entity result sets and relationship collections are multisets.  A Value
    Object occurrence with ``multiplicity: many`` is different: its authored
    document order is semantic, so its elements compare positionally.  Passing
    the model enables that distinction; the model-free form remains useful for
    generic graph-comparison tests that contain relationships only.
    """

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

    if model is None:
        return equal_value(left, right)

    def equal_value_object_member(a: Any, b: Any, declaration: dict[str, Any]) -> bool:
        if not isinstance(a, dict) or not isinstance(b, dict) or a.keys() != b.keys():
            return False
        nested_by_name = {nested["name"]: nested for nested in declaration.get("valueObjects", [])}
        return all(
            equal_value_object(a[key], b[key], nested_by_name[key])
            if key in nested_by_name
            else _scalars_equal(a[key], b[key], None)
            for key in a
        )

    def equal_value_object(a: Any, b: Any, declaration: dict[str, Any]) -> bool:
        if declaration.get("multiplicity", "one") == "many":
            if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
                return False
            return all(
                equal_value_object_member(left_item, right_item, declaration)
                for left_item, right_item in zip(a, b, strict=True)
            )
        if a is None or b is None:
            return a is None and b is None
        return equal_value_object_member(a, b, declaration)

    def equal_entity_node(a: Any, b: Any, entity: Entity) -> bool:
        if not isinstance(a, dict) or not isinstance(b, dict) or a.keys() != b.keys():
            return False
        value_objects = {
            value_object["name"]: value_object for value_object in entity.value_objects
        }
        relationships = {
            relationship["name"]: relationship for relationship in entity.relationship_metadata
        }
        for key in a:
            if key in value_objects:
                if not equal_value_object(a[key], b[key], value_objects[key]):
                    return False
                continue

            relationship_name = key.split("[", 1)[0]
            relationship = relationships.get(relationship_name)
            if relationship is None:
                if not _scalars_equal(a[key], b[key], None):
                    return False
                continue

            target = model.entity(relationship["join"]["target"]["entity"])
            if relationship["cardinality"] == "one-to-many":
                if not isinstance(a[key], list) or not isinstance(b[key], list):
                    return False
                if len(a[key]) != len(b[key]):
                    return False
                remaining = list(b[key])
                for child in a[key]:
                    for index, candidate in enumerate(remaining):
                        if equal_entity_node(child, candidate, target):
                            del remaining[index]
                            break
                    else:
                        return False
                if remaining:
                    return False
                continue

            if a[key] is None or b[key] is None:
                if a[key] is not None or b[key] is not None:
                    return False
            elif not equal_entity_node(a[key], b[key], target):
                return False
        return True

    if left.keys() != right.keys():
        return False
    for entity_name in left:
        left_nodes = left[entity_name]
        right_nodes = right[entity_name]
        if len(left_nodes) != len(right_nodes):
            return False
        entity = model.entity(entity_name)
        remaining = list(right_nodes)
        for node in left_nodes:
            for index, candidate in enumerate(remaining):
                if equal_entity_node(node, candidate, entity):
                    del remaining[index]
                    break
            else:
                return False
        if remaining:
            return False
    return True


# --- value-object + inheritance single-statement graph read (m-value-object, m-inheritance) ---


def _project_value_object(vo: dict[str, Any], decoded: Any) -> Any:
    """Project a decoded document slot to its DECLARED value-object shape.

    The projection answers one occurrence's own value once its parent has decided
    the position exists at all (:func:`_project_members`):

    * a ``one`` member is a nested object when the slot is a JSON object, else
      ``None`` — a SQL-NULL column, a JSON ``null``, and a non-object intermediate
      all collapse the composite (m-document-codec);
    * a ``many`` member is the collection of its element projections when the
      slot is a JSON array of objects, else ``[]``, because a ``many`` has no
      absent state: an omitted key, a JSON ``null``, and ``[]`` are three stored
      spellings of one zero value. A non-array, and an array holding any
      non-object element, are one wrong-kind ``many`` AT THE OCCURRENCE
      POSITION — the whole collection collapses and no element is projected, so
      a conforming sibling element never survives a malformed one
      (m-document-codec).

    Element order within a ``many`` member is semantic (m-value-object), so this
    projection preserves JSON document order and metadata-aware graph comparison
    checks those elements positionally.
    """
    if vo.get("multiplicity", "one") == "many":
        if isinstance(decoded, list) and all(isinstance(element, dict) for element in decoded):
            return [_project_members(vo, element) for element in decoded]
        return []
    if isinstance(decoded, dict):
        return _project_members(vo, decoded)
    return None


def _project_members(vo: dict[str, Any], obj: Any) -> dict[str, Any]:
    """Build the declared-member projection of one value-object document object.

    Undeclared keys are omitted and each declared member the document HOLDS is
    decoded by its declared type (:func:`decode_leaf`) rather than copied out,
    because the document stores the codec's portable spelling. Which declared
    members become keys is not decided here: this projection realizes the read
    contract (m-snapshot-read "What a materialized value carries") and is graded
    against a language implementation of the same contract, so each position where a
    key survives a document that did not hold it is read from there rather than
    restated (:func:`_publishes_when_omitted`). The one position that runs the other
    way has no case here, because :func:`decode_leaf` raises on an undecodable leaf
    instead of classifying it. What the projection adds of its own is the decoding
    alone, which is why a stored state a hydration rule collapses projects that
    collapse whole rather than element by element.
    """
    source = obj if isinstance(obj, dict) else {}
    node: dict[str, Any] = {}
    for attribute in vo.get("attributes", []):
        if attribute["name"] in source:
            node[attribute["name"]] = decode_leaf(attribute["type"], source[attribute["name"]])
    for nested in vo.get("valueObjects", []):
        if _publishes_when_omitted(nested) or nested["name"] in source:
            node[nested["name"]] = _project_value_object(nested, source.get(nested["name"]))
    return node


def _publishes_when_omitted(nested: dict[str, Any]) -> bool:
    return nested.get("multiplicity", "one") == "many" or not nested.get("nullable", False)


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
        raw = (
            row.value_object_columns[column]
            if isinstance(row, _MaterializedRow) and column in row.value_object_columns
            else node.pop(column)
        )
        if column in node and (
            not isinstance(row, _MaterializedRow) or column not in row.consumed_value_object_columns
        ):
            node.pop(column)
        node[vo["name"]] = _project_value_object(vo, decode_stored(raw))
    return node


def _graph_node(model: Model, entity: Entity, row: dict[str, Any]) -> dict[str, Any]:
    """One materialized node keyed the way `then.graph` keys one.

    A graph leaf is keyed by the DECLARED member name (`m-case-format` *Graph
    keys*), while a read row arrives keyed by its physical column, so the
    attribute half is renamed here. Value Object occurrences and relationship
    views are already name-keyed by :func:`_materialize_owner_node` and the
    assembly, and `familyVariant` names no declared member, so both pass through.

    The rename map comes from the node's OWN concrete Entity where the row states
    one: an abstract-root read narrows each node to its variant's declared
    columns, and two concrete siblings may spell one column name for two
    different members. A polymorphic level that projects no variant is read at an
    abstract position that declares none of its descendants' own members, so the
    model's remaining declarations fill what that position cannot name — never
    overriding what it can.
    """
    node = _materialize_owner_node(entity, row)
    concrete = entity
    variant = node.get("familyVariant")
    if isinstance(variant, str):
        try:
            concrete = model.entity(variant)
        except KeyError:
            concrete = entity
    names = {attribute["column"]: attribute["name"] for attribute in concrete.attributes}
    for other in model.entities:
        for attribute in other.attributes:
            names.setdefault(attribute["column"], attribute["name"])
    return {names.get(key, key): value for key, value in node.items()}


def _assert_single_statement_graph(case: Case, db: DatabaseProvider) -> None:
    """Assert a top-level ``then.graph`` read (no Includes, no milestone set)
    materializes from its ONE golden statement, with no child statement.

    This is the non-deep-fetch, single-instant ``then.graph`` grader — the dispatch
    counterpart of :func:`_assert_deep_fetch` and :func:`_assert_graphs`
    (`m-case-format` *Read result form*). Two, independently-conditional kinds of
    case route here, and either, both, or neither may apply to a given case:

    * **A value-object graph read** (m-value-object): the single golden statement
      (``roundTrips: 1`` — enforced by :func:`_assert_round_trip_count`) projects
      the owning entity including its structured-document column(s); the harness
      decodes each row's value-object column into its declared nested to-one /
      to-many projection (:func:`_materialize_owner_node`) — the proof that nested
      values arrive with the owner, never via a deep fetch ("Materialization and
      navigation contract"). A no-op for an entity that declares no value objects.
    * **An abstract-target inheritance read** (m-inheritance / m-case-format "Read
      targeting"): additionally materializes ``familyVariant``
      (:func:`_materialize_family_variant`, the SAME oracle the row-form path uses)
      and then narrows each node to its own concrete variant's declared columns
      (:func:`_narrow_to_variant_columns`) — the instance-form per-variant node
      shape, distinct from row-form's unnarrowed superset. A no-op for a
      non-inheritance / concrete-target read.

    Either way the assembled ``{Class: [node, …]}`` graph is compared against
    ``then.graph`` via :func:`_graphs_equal`. Root result sets remain
    order-insensitive, while metadata identifies Value Object ``many`` members
    whose document order is semantic.

    When a ``referenceSql`` oracle is present it independently pins the matched
    row SET (identity columns only, the value-object columns stripped), so the
    filter that selected the rows is checked by a different formulation without
    routing the JSON document through row comparison.
    """
    dialect = db.dialect
    (golden,) = case.golden_statements(dialect)
    entity = case.model.entity(case.object_query["target"])

    value_object_columns = {vo["column"] for vo in entity.value_objects}
    # An instance form additionally carries every applicable occurrence, so a
    # Relational Document Layout read fans those out of its one Structured Column
    # too — after which each occurrence sits under the very column name a `Columns`
    # layout would have given it and the node assembly below is layout-blind.
    projected = _materialize_target_tph_document_layout(
        case,
        _query_rows(case, db, golden, case.statement_binds(0, dialect)),
        include_value_objects=True,
    )
    rows: list[dict[str, Any]] = [
        _MaterializedRow(
            row,
            value_object_columns={key: row[key] for key in value_object_columns if key in row},
        )
        for row in projected
    ]
    # `familyVariant` materialization happens on the RAW rows (also what a
    # referenceSql identity check below compares against — the matched ROW SET,
    # unrelated to per-variant field narrowing); the per-variant COLUMN narrowing
    # is a separate, graph-assembly-only step.
    rows = _materialize_family_variant(case, rows)
    narrowed_rows = _narrow_to_variant_columns(case, rows)
    assembled = {entity.name: [_graph_node(case.model, entity, row) for row in narrowed_rows]}

    expected = case.expected_graph or {}
    if not _graphs_equal(assembled, expected, case.model):
        raise CaseFailure(
            f"{case.path.name}: materialized graph != then.graph.\n"
            f"  assembled: {assembled!r}\n"
            f"  expected:  {expected!r}"
        )

    reference_sql = case.reference_sql_for(dialect)
    if reference_sql is not None:
        identity_rows = [_reference_identity_row(row) for row in rows]
        # An abstract-target inheritance read's naive reference SQL projects the
        # RAW tag column too (it is an independently-formulated but otherwise
        # equivalent selection); materialize familyVariant on it the same way,
        # so this identity check compares apples to apples (m-inheritance).
        reference_rows = _materialize_family_variant(case, db.query(reference_sql))
        if not _rows_equal(reference_rows, identity_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql rows != golden rows (identity).\n"
                f"  reference: {reference_rows!r}\n"
                f"  expected:  {identity_rows!r}"
            )


# --- negative validation (the `rejected` shape) ----------------------------------------


def _assert_rejected(case: Case) -> None:
    """Assert one of the three rejected inputs is refused before SQL.

    A rejected case carries exactly one schema-valid ``when.objectQuery``,
    ``when.write``, or inline ``when.model`` and names the violated rule in
    ``then.rejectedRule``. A query runs ``validate_object_query`` and Inheritance's
    ``validate_query_inheritance``, resolved against the position the query itself
    names.

    A write is dispatched on the members it carries, never on the rule the case
    names (`m-case-format` Rejected cases): a ``target`` is a predicate-selected
    instruction, a ``rows`` array is a whole KEYED instruction judged by
    ``validate_keyed_write`` against the entity IT names, and anything else is
    the bare neutral write row, run through ``validate_write`` and Inheritance's
    ``validate_subtype_write`` against the model's default write root. Both
    discriminators are RESERVED from a bare row at this position
    (`compatibility-case.schema.json` ``$defs/bareWriteRow``), so a domain member
    can never be mistaken for one and this dispatch cannot re-read a row as an
    instruction. Membership can decide the form only for an OBJECT, so
    :func:`_rejected_write_input` refuses anything else before dispatch. Inline
    models run the foundational
    ``validate_index_identities`` before the semantic rule sets — Inheritance's
    ``validate_family`` and Storage Layout’s ``validate_storage_layout``, including
    standalone Table ownership and Column claims. The referenced top-level model
    remains valid and loadable.

    The raised rule must match exactly. No rejected variant reaches dialect
    selection, provisioning, SQL emission, or database execution.
    """
    expected = case.rejected_rule
    try:
        if "objectQuery" in case.when:
            query = case.when["objectQuery"]
            validate_object_query(case.model.entity(query["target"]), query)
            # Inheritance selection / subtype-scope validation (m-object-query x
            # m-inheritance): a no-op on a non-inheritance model, so it runs after
            # the value-object validation without disturbing the existing cases.
            validate_query_inheritance(case.model.entity_defs, query)
        elif "write" in case.when:
            write = _rejected_write_input(case)
            if "target" in write:
                _validate_rejected_predicate_write(case, write)
                raise CaseFailure(
                    f"{case.path.name}: predicate write did not match its pre-SQL refusal"
                )
            if "rows" in write:
                _validate_rejected_keyed_write(case, write)
                raise CaseFailure(
                    f"{case.path.name}: keyed instruction did not match its pre-SQL refusal"
                )
            # The concrete-subtype payload-shape and target-validity rules run
            # FIRST, unconditionally (`m-inheritance` "A validator checks these
            # payload-shape rules... before the target-validity rule"): a malformed
            # inheritance payload has no well-defined target for the declared-member
            # walk to run against. A no-op on a non-inheritance model.
            #
            # The default write root is resolved HERE rather than up front: the two
            # instruction forms above name their own handle, so a model with no
            # default is only a defect for the bare row, which names none.
            entity = _rejected_default_root(case)
            validate_subtype_write(entity, case.model.entity_defs, write)
            _assert_bare_row_members_declared(case, entity, write)
            validate_write(entity, write)
        elif "model" in case.when:
            inline_model = derive_temporal_structure(case.when["model"])
            inline_entities = inline_model.get("entities")
            if not isinstance(inline_entities, list):
                inline_entity = inline_model.get("entity")
                inline_entities = [inline_entity] if isinstance(inline_entity, dict) else []
            validate_index_identities(inline_entities)
            validate_family(inline_model)
            validate_storage_layout(inline_entities)
        else:  # pragma: no cover - guarded by _assert_schema
            raise CaseFailure(
                f"{case.path.name}: rejected case needs when.objectQuery / when.write / when.model"
            )
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


def _rejected_default_root(case: Case) -> Entity:
    """The entity a rejected case's ``when`` is resolved against but never names.

    A bare ``when.write`` row carries no entity handle of its own, so it resolves
    against the model's DEFAULT write root (`m-case-format` Rejected cases): the
    inheritance-family root when the model declares exactly one family, else — when
    the model declares no family at all — its own first entity. A rejected
    ``when.objectQuery`` names its own queried position and reaches none of this.

    A model declaring SEVERAL families names no single root, so it has no default
    and the case must carry its own handle; resolving such a model to whichever
    entity happens to be declared first would grade a rule against an entity the
    case never asked about.
    """
    entities = case.model.entities
    participants = [entity for entity in entities if entity.inheritance is not None]
    if not participants:
        return entities[0]
    roots = [entity for entity in participants if entity.role == "root"]
    if len(roots) != 1:
        raise CaseFailure(
            f"{case.path.name}: the case's model declares {len(roots)} inheritance family "
            f"roots, so a `when` naming no explicit target has no default write root to "
            f"resolve against"
        )
    return roots[0]


def _assert_bare_row_members_declared(case: Case, entity: Entity, row: dict[str, Any]) -> None:
    """Fail the case when the bare row names members *entity* does not declare.

    Member honesty is a case-authoring judgement, not a violated normative MUST: an
    undeclared name resolves to no declared position, so no rule of the closed
    ``then.rejectedRule`` vocabulary is about it, and grading the row anyway would
    report whichever rule some OTHER member happens to violate — a case that passes
    while testing something it never claimed. The keyed instruction lane refuses the
    same way (:func:`_validate_rejected_keyed_write`), so one neutral write row is
    judged one way whichever form carries it.

    Asked AFTER the concrete-subtype protocol, which `m-inheritance` orders first and
    which owns the family-specific names a row may not carry: the tag column and the
    ``tag`` / ``tagValue`` / ``familyVariant`` handles are
    ``subtype-write-metadata-field``, and a sibling branch's attribute is
    ``subtype-write-sibling-attribute``. Those are classified rules, so they must not
    be reported as authoring defects.
    """
    unknown = undeclared_members(entity, row)
    if unknown:
        raise CaseFailure(
            f"{case.path.name}: the bare write row names {unknown}, which are not "
            f"attributes or value objects of {entity.name}"
        )


def _rejected_write_input(case: Case) -> dict[str, Any]:
    """The ONE ``when.write`` document a rejected case puts under test.

    Each of the three rejected write forms is an object whose members name it, so
    a document that is not one reaches :func:`_assert_rejected`'s dispatch with
    nothing to dispatch ON. The multi-key ARRAY the shared ``when.write``
    vocabulary also admits is the conflict lane's form alone
    (`compatibility-case.schema.json`): it states a collapsed statement's
    aggregate affected-row count, which a pre-SQL rejection asserts nothing about.
    Refused here rather than normalized: reading a one-element array as its row and
    a longer one as nothing would, in both directions, grade a document no rejected
    lane defines.
    """
    write = case.when.get("write")
    if not isinstance(write, dict):
        raise CaseFailure(
            f"{case.path.name}: a rejected `when.write` is a predicate-selected instruction, a "
            f"keyed instruction, or a bare neutral write row — all objects, and the members "
            f"decide which. {type(write).__name__} is the conflict lane's multi-key form, which "
            f"asserts an aggregate affected-row count no rejected case emits SQL to produce."
        )
    return write


def _validate_rejected_keyed_write(case: Case, write: dict[str, Any]) -> None:
    """Run the keyed-instruction rules against the entity the instruction names.

    A keyed instruction brings its own ``entity`` handle, so — unlike the bare
    neutral write row beside it — nothing here falls back to the model's default
    write root; an undeclared handle is a case-authoring failure rather than a
    silent resolution against some other entity.

    The PAYLOAD is judged before the instruction's shape
    (:func:`~reference_harness.keyed_write_validate.undeclared_row_members`),
    which is what `m-case-format` means by checking the payload against the entity
    the instruction authored: a row naming no declared member fails the case
    outright rather than being classified with an instruction rule it never
    reached.

    Ahead of BOTH runs the concrete-subtype payload-shape protocol, once per row,
    exactly as the bare-row lane runs it ahead of its own member-honesty refusal
    (:func:`_assert_bare_row_members_declared`). Those rules own the family-specific
    names a row may not carry, so a keyed update of `CardPayment` carrying a
    sibling branch's own attribute is `subtype-write-sibling-attribute` and not an
    authoring defect — one neutral write row is judged one way whichever form
    carries it.
    """
    entity_name = write.get("entity")
    try:
        entity = case.model.entity(str(entity_name))
    except KeyError as exc:
        raise CaseFailure(
            f"{case.path.name}: keyed instruction names entity {entity_name!r}, which the "
            f"case's model does not declare"
        ) from exc
    rows = write.get("rows")
    for row in rows if isinstance(rows, list) else ():
        if isinstance(row, dict):
            validate_subtype_write(entity, case.model.entity_defs, row)
    unknown = undeclared_row_members(entity, write)
    if unknown:
        raise CaseFailure(
            f"{case.path.name}: keyed instruction's row(s) name {unknown}, which are not "
            f"attributes or value objects of {entity.name}"
        )
    validate_keyed_write(entity, write)


def _validate_rejected_predicate_write(case: Case, write: dict[str, Any]) -> None:
    target = write.get("target", {})
    target_name = target.get("entity") if isinstance(target, dict) else None
    entity = case.model.entity(str(target_name))
    if entity is None:
        return
    validate_predicate_write(entity, write)
    document_layout = entity.runtime_facts.get("layout", {}).get("document")
    if not document_layout:
        return
    if requires_predicate_write_materialization(entity):
        return
    for assignment in write.get("assignments", []):
        name = str(assignment.get("attr", "")).rsplit(".", 1)[-1]
        occurrence = next((item for item in entity.value_objects if item.get("name") == name), None)
        if occurrence is None:
            continue
        nested_many = _authored_many_path(occurrence, assignment.get("value"))
        if occurrence.get("multiplicity", "one") == "many" or nested_many is not None:
            path = name if nested_many is None else ".".join((name, *nested_many))
            raise RejectionError(
                "predicate-write-readless-document-many-unsupported",
                f"{target_name}.{path}: readless document-resident many assignment",
            )


def _authored_many_path(occurrence: dict[str, Any], authored: object) -> tuple[str, ...] | None:
    if not isinstance(authored, dict):
        return None
    for nested in occurrence.get("valueObjects", []):
        name = nested["name"]
        if name not in authored:
            continue
        if nested.get("multiplicity", "one") == "many":
            return (name,)
        path = _authored_many_path(nested, authored[name])
        if path is not None:
            return (name, *path)
    return None


# --- write sequences (m-txtime-write) ---------------------------------------------------


# The mutations that OPEN a row with no prior state to close: the unbounded
# `insert` and its Valid-Time-bounded `insertUntil` sibling. Such an entry
# resolves no source — there is no row for a read to return — and on a temporal
# target it opens a rectangle rather than splitting one.
_OPENING_MUTATIONS = ("insert", "insertUntil")

# The keyed write mutations a public verb states. `cascadeDelete` is deliberately
# absent: it is not a Keyed Mutation, no verb states it, and an entry writing one
# therefore resolves no source.
_KEYED_MUTATIONS = (
    *_OPENING_MUTATIONS,
    "update",
    "delete",
    "terminate",
    "updateUntil",
    "terminateUntil",
)


def _entry_entity(case: Case, entry: dict[str, Any]) -> Entity:
    """The Entity one write entry targets, resolved from the spelling it authored
    — canonical or an unambiguous bare local name, which name one Entity."""
    return case.model.entity(entry.get("entity", ""))


def _entry_object_keys(case: Case, entry: dict[str, Any]) -> list[tuple[str, tuple[Any, ...]]]:
    """Which object each of ``entry``'s rows names, by its declared primary key.

    The entity's flattened definition carries the family's key, so a concrete
    subtype resolves the same key its root declares, and each object is named by
    the CANONICAL Entity spelling, so two entries spelling one target differently
    name one object rather than two.
    """
    entity = _entry_entity(case, entry)
    names = [a["name"] for a in entity.attributes if a.get("primaryKey")]
    return [
        (entity.canonical_name, tuple(repr(row.get(name)) for name in names))
        for row in entry.get("rows", [])
    ]


def _unit_resolving_reads(case: Case, entries: list[dict[str, Any]]) -> int:
    """The resolving reads ONE choreography unit owes: one per target Entity whose
    existing-row keyed writes address a row this unit did not itself open.

    A keyed write verb is addressed and licensed by a value a read published, so
    a unit writing against existing state reads it first — once per Entity,
    resolving every row of that Entity the unit addresses, because a read
    interleaved between two writes would force-flush the first and destroy the
    batch collapse the goldens pin. Three kinds of entry owe nothing: an insert
    OPENS its row, a row an earlier entry of the same unit opened is
    read-your-own-writes, and an entry carrying a DB-computed write marker states
    the framework's own bookkeeping, which no public verb accepts.

    Targets are counted by their canonical spelling, so two entries naming one
    Entity two ways owe one read between them.
    """
    opened: set[tuple[str, tuple[Any, ...]]] = set()
    needed: set[str] = set()
    for entry in entries:
        mutation = entry.get("mutation")
        if mutation in _OPENING_MUTATIONS:
            opened.update(_entry_object_keys(case, entry))
            continue
        if mutation not in _KEYED_MUTATIONS:
            continue
        entity = _entry_entity(case, entry)
        if states_framework_marker(entity, entry):
            continue
        if any(key not in opened for key in _entry_object_keys(case, entry)):
            needed.add(entity.canonical_name)
    return len(needed)


def _assert_write_step_count(case: Case, dialect: str) -> None:
    """The DML statement count MUST equal the sum of the steps' declared counts,
    and the round trips MUST be that plus every resolving read the sequence owes.

    Each ``writeSequence`` step declares how many golden DML statements it emits
    (default 1); the total over the sequence is the DML statement count, which
    MUST equal the number of then.statements for the dialect. ``roundTrips``
    counts every call that reached the database, so it is that total plus one
    resolving read per entry writing against existing state
    (:func:`_unit_resolving_reads`) — the read a keyed write verb's source
    requires, which is work the framework genuinely does.
    """
    statements = case.golden_statements(dialect)
    step_total = sum(step.get("statements", 1) for step in case.write_sequence)
    if len(statements) != step_total:
        raise CaseFailure(
            f"{case.path.name}: then.statements ({dialect}) has {len(statements)} DML "
            f"statement(s) but the writeSequence declares {step_total} "
            f"(sum of per-step statement counts). They MUST be equal."
        )
    reads = sum(_unit_resolving_reads(case, [entry]) for entry in case.write_sequence)
    if len(statements) + reads != case.round_trips:
        raise CaseFailure(
            f"{case.path.name}: then.statements ({dialect}) has {len(statements)} DML "
            f"statement(s) and the sequence owes {reads} resolving read(s), but roundTrips "
            f"is {case.round_trips}."
        )


# The full-bitemporal `*Until` rectangle-split mutations: a Valid-Time-bounded
# write whose ① carries the valid-time window (`at`/`until`/`validFrom`).
_UNTIL_MUTATIONS = ("insertUntil", "updateUntil", "terminateUntil")

# The plain (UNBOUNDED) bitemporal rectangle-split mutations: an everyday retroactive
# correction/termination from an instant onward with no upper Valid-Time bound
# (`m-bitemp-write-006` / `m-bitemp-write-007`). Like the `*Until` trio they close
# the original on the Transaction-Time dimension and chain head / (new-)tail milestones, but
# the residual window runs to the open bound (thru_z), so ① carries no `until`.
_PLAIN_SPLIT_MUTATIONS = ("update", "terminate")

# The rectangle-split mutations that END coverage rather than carrying a changed
# value forward: they re-open the head (and, when windowed, the tail) but no slice
# for the window itself.
_TERMINATE_MUTATIONS = ("terminate", "terminateUntil")

# The ONE reserved observation control key a case write row may spell
# (`compatibility-case.schema.json` `$defs/writeRow`). Which (target, mutation)
# pair is entitled to spell it is :func:`_observation_refusal`'s answer — one
# shared `writeRow` definition spans every authoring location, so the schema
# cannot express it.
_VERSION_OBSERVATION_KEY = "observedVersion"

# The two halves of an observed milestone's own EDGE coordinate. Neither is a
# write-row key in any authoring location: a temporal write observes a whole
# predecessor milestone, which no flat row cell can name, so both ride beside the
# write, at `when.observedTxStart` / `when.observedValidStart` — and, on a retry
# attempt, `observedTxStart` alone, since the edge form is single-attempt only
# (`m-case-format`). Named here so a row that spells one is refused by the rule
# rather than by the generic "not a member" diagnosis.
_MILESTONE_COORDINATE_KEYS = ("observedTxStart", "observedValidStart")

# The milestone close a temporal conflict case writes. Not a `writeSequence`
# verb: a conflict close is shaped by `when.mutation`-less close authoring, and
# this names it for the entitlement diagnosis alone.
_CLOSE_MUTATION = "close"


def _is_bitemporal(entity: Entity) -> bool:
    """Whether an entity carries BOTH as-of axes (Valid Time + Transaction Time) — the
    full-bitemporal rectangle profile, where a plain `update` / `terminate` is a
    milestone rectangle split (close + chain), not the audit-only close-and-open."""
    axes = {dim.get("dimension") for dim in entity.temporal_runtime_axes}
    return {"valid-time", "transaction-time"} <= axes


def _as_of_axes(entity: Entity) -> list[dict[str, Any]]:
    """*entity*'s As-Of Axes in canonical dimension rank (Valid Time first)."""
    return sorted(
        entity.temporal_runtime_axes,
        key=lambda axis: TEMPORAL_DIMENSION_RANK[axis["dimension"]],
    )


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
    metamodel (the member's own declared role), not from the value's shape, so a
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


def _observation_refusal(entity: Entity, mutation: str) -> str | None:
    """Why a write row against *entity* under *mutation* may not spell the reserved
    ``observedVersion`` control key — ``None`` when that pair is the ONE the case
    vocabulary entitles to spell it.

    This is the whole licensing rule `m-unit-work`'s "Absence is structural"
    states, restated by the case schema's own ``observedVersion`` prose ("absent
    on a versioned insert and on a non-versioned write"), and it is TOTAL over
    every (target, mutation) pair a case can author. A VERSIONED, NON-TEMPORAL
    update or delete may spell the key; nothing else may:

    - a TEMPORAL target's write observes a whole predecessor MILESTONE, which no
      flat row cell can name, and a close's Transaction-Time gate is authored
      beside the write (``when.observedTxStart`` or the attempt's own field,
      `m-case-format`) rather than inside the row;
    - an INSERT opens a row rather than writing against one, so an observed
      version names a milestone that does not yet exist;
    - an UNVERSIONED non-temporal target has no version to observe, so an
      observed version on it is evidence about nothing.

    Deciding it HERE, at the one seam every ① row is classified through, is what
    keeps the neutral grader's table the same table the conformance engine
    enforces: a consumer that merely ignores the value it was handed accepts a
    case the engine refuses, and the two implementations then disagree about
    which cases the corpus even admits.
    """
    if entity.is_temporal:
        return (
            f"a temporal row spells no {_VERSION_OBSERVATION_KEY!r} (m-unit-work: a temporal "
            f"write observes a whole predecessor milestone, which no flat row cell can name, "
            f"and a close's observed `in_z` gate rides beside the write)"
        )
    if mutation in _OPENING_MUTATIONS:
        return (
            f"an insert row spells no {_VERSION_OBSERVATION_KEY!r} (m-unit-work: inserts have "
            f"no observation — an observed version names the milestone a write against an "
            f"EXISTING row observed)"
        )
    if _version_column(entity) is None:
        return (
            f"an unversioned row spells no {_VERSION_OBSERVATION_KEY!r} (m-unit-work: "
            f"unversioned Non-Temporal writes have no observation — there is no observed "
            f"version for it to name)"
        )
    return None


def _classify_write_row(
    case: Case, entity: Entity, row: dict[str, Any], *, mutation: str, opening: bool
) -> tuple[dict[str, Any], Any, dict[str, Any], Any]:
    """Classify a flat attribute-named ① row against *entity*'s metamodel.

    Mirrors the fixture loader's attribute→column resolution. Every key is either
    the reserved control key ``observedVersion`` — admitted only where
    :func:`_observation_refusal` entitles this (*entity*, *mutation*) pair to
    spell it, so an unobservable row is refused HERE rather than accepted and
    discarded by whichever consumer has no use for it — an ENTITY ATTRIBUTE name,
    or a
    top-level VALUE-OBJECT name (a bad key raises :class:`CaseFailure`, so the
    neutral input can't silently name a non-member); the primary-key attribute's
    value is split into the pk, every other attribute AND every value object into
    the domain ``set`` — all keyed by physical column. A value object resolves to
    its single structured-document column and its value is the WHOLE document
    (m-value-object): it binds atomically as one document value at its Document-tier
    slot, never decomposed into path-level binds. Because that role is resolved
    HERE (from the entity's declared members), a value-object column's value is ALWAYS
    literal document content downstream — never a DB-computed marker
    (``computed`` / ``increment``), even when the document is marker-SHAPED; marker
    interpretation applies only to a scalar-attribute column (see
    :func:`_document_columns`).

    A value object's ① value is the occurrence's neutral write input, so it is
    ENCODED here (``document_codec``) rather than taken as the document. That is what
    makes the golden bind graded rather than trusted: the harness derives the document
    a conforming writer must produce from the case's own member values, and
    :func:`_assert_write_values` compares it to the authored bind — so a leaf spelled
    any other way fails the case instead of surviving it. An OPENING statement
    additionally binds every `many` occurrence's column whether ① names it or not:
    absence and the empty array are one logical zero state (m-value-object).

    Under Relational Document Layout the members the layout moved inside the shared
    Structured Column resolve to THAT one column rather than to columns of their own,
    and their derived value depends on what the statement does with them: an opening
    statement writes the whole document, so they are composed into it here, while a
    revising one patches only the assigned paths and takes them from
    :func:`_document_assignments` instead. ``opening`` is therefore the caller's
    answer, from the step's own mutation, and never inferred from the row.
    """
    pk_columns = {a["column"] for a in entity.attributes if a.get("primaryKey")}
    document_column, resident = _document_layout_members(case, entity)
    resident_columns = {member.column for member in resident}
    columns: dict[str, Any] = {}
    set_columns: dict[str, Any] = {}
    pk_value: Any = None
    observed_version: Any = None
    for key, value in row.items():
        if key in _MILESTONE_COORDINATE_KEYS:
            raise CaseFailure(
                f"{case.path.name}: {entity.name} {mutation!r}: a write row spells no {key!r} "
                f"(m-case-format: an observed milestone's own edge coordinate rides beside the "
                f"write, at `when.observedTxStart` / `when.observedValidStart`, or an "
                f"attempt's own `observedTxStart`; a writeRow reserves "
                f"{_VERSION_OBSERVATION_KEY!r} alone and every other key names an entity member)"
            )
        if key == _VERSION_OBSERVATION_KEY:
            refusal = _observation_refusal(entity, mutation)
            if refusal is not None:
                raise CaseFailure(f"{case.path.name}: {entity.name} {mutation!r}: {refusal}")
            observed_version = value
            continue
        try:
            column = entity.attribute_by_name(key)["column"]
        except KeyError:
            # Not an attribute — a value object binds as ONE document at its
            # Document-tier slot (m-value-object); the neutral input names it
            # like a scalar attribute and its value is the whole document.
            try:
                value_object = entity.value_object_by_name(key)
            except KeyError as exc:
                raise CaseFailure(
                    f"{case.path.name}: writeSequence row key {key!r} is not an attribute "
                    f"or value object of {entity.name} — the neutral write input speaks "
                    f"ATTRIBUTE / value-object names, not columns."
                ) from exc
            column = value_object["column"]
            if column not in resident_columns:
                value = encode_document(value_object, value)
        if column in resident_columns:
            continue  # the Structured Column carries it; composed below
        columns[column] = value
        if column in pk_columns:
            pk_value = value
        else:
            set_columns[column] = value
    if opening:
        # A `many` occurrence with a Column of its own binds on every opening
        # statement whether or not the row names it: absence and the empty array are
        # one logical zero state, so an unnamed `many` stores `[]` (m-value-object) —
        # the same answer the codec composes for one inside a document.
        for value_object in entity.value_objects:
            column = value_object["column"]
            if value_object.get("multiplicity", "one") != "many" or column in resident_columns:
                continue
            if value_object["name"] not in row:
                columns[column] = encode_document(value_object, [])
                set_columns[column] = columns[column]
    if document_column and opening:
        # The Structured Column binds on EVERY opening statement, including one for
        # an Entity whose members are all direct: it is `NOT NULL` and every governed
        # row carries a document, the empty object included (m-storage-layout).
        document = _entity_document(case, entity, resident, row)
        columns[document_column] = document
        set_columns[document_column] = document
    return columns, pk_value, set_columns, observed_version


def _entity_document(
    case: Case, entity: Entity, resident: tuple[_DocumentMember, ...], row: dict[str, Any]
) -> dict[str, Any]:
    """The complete Structured Column document one opening ① row implies.

    Composed over EVERY document-resident member rather than only the named ones,
    because presence is the codec's classification: an omitted key stays absent, an
    authored null becomes JSON null, and a ``many`` occurrence always contributes its
    array. Members are emitted in canonical placement order — every attribute, then
    every occurrence — so one set of member values yields exactly one document.
    """
    document: dict[str, Any] = {}
    for member in resident:
        name = member.path[0]
        if member.type_spelling is None:
            occurrence = entity.value_object_by_name(name)
            if name in row:
                document[name] = encode_document(occurrence, row[name])
            elif occurrence.get("multiplicity", "one") == "many":
                document[name] = []
            continue
        if name in row:
            document[name] = encode_leaf(member.type_spelling, row[name])
    return document


def _document_path_bind(path: tuple[str, ...], dialect: str) -> str:
    """The bind addressing *path* inside a document mutation, per dialect.

    Postgres `jsonb_set` takes ONE text-array path; MariaDB `json_set` takes the
    same ``$.a.b`` JSON-path string its `json_value` extraction does (m-dialect).
    Spelled here rather than taken from any implementation: the ①↔② cross-check is
    an independent derivation, so it must know the two spellings itself.
    """
    if dialect == "mariadb":
        return "$." + ".".join(path)
    return "{" + ",".join(path) + "}"


def _document_value_bind(value: Any) -> Any:
    """One assigned document value as the mutation expression's hole takes it.

    A composite crosses the seam as the portable document it is and each provider
    adapts it; a JSON scalar, which no structural authoring form distinguishes from
    an ordinary scalar bind, crosses as the JSON text both dialects' value
    expressions parse (m-case-format).
    """
    return value if is_document(value) else json.dumps(value)


def _document_assignments(
    case: Case, entity: Entity, row: dict[str, Any]
) -> tuple[_DocumentAssignment, ...]:
    """The ordered Document Paths one revising ① row assigns, canonical order.

    A revising statement writes only the paths it names (`m-storage-layout`), so
    this is the resident member sequence narrowed to the row's own keys — never the
    whole document. An assigned occurrence contributes ONE path carrying its whole
    encoded document, because assigning one replaces its subtree rather than
    reaching inside it. Order is the layout's, not the row's, because both
    dialects' mutation expressions apply left to right (`m-dialect`).
    """
    _column, resident = _document_layout_members(case, entity)
    assignments: list[_DocumentAssignment] = []
    for member in resident:
        name = member.path[0]
        if name not in row:
            continue
        value = row[name]
        if member.type_spelling is None:
            occurrence = entity.value_object_by_name(name)
            assignments.append(_DocumentAssignment(member.path, encode_document(occurrence, value)))
        else:
            assignments.append(
                _DocumentAssignment(member.path, encode_leaf(member.type_spelling, value))
            )
    return tuple(assignments)


def _document_assignment_binds(
    assignments: tuple[_DocumentAssignment, ...], dialect: str
) -> list[Any]:
    binds: list[Any] = []
    for assignment in assignments:
        binds.extend(
            [
                _document_path_bind(assignment.path, dialect),
                _document_value_bind(assignment.value),
            ]
        )
    return binds


def _version_column(entity: Entity) -> str | None:
    """The physical column of an entity's explicit optimistic-lock version, or None.

    A VERSIONED entity carries an attribute-level ``optimisticLocking: true`` version
    (m-opt-lock); the value advance (``initial 1`` / ``observed + 1``) and gate are DERIVED,
    so the column never appears in the neutral write input (①). A temporal entity
    locks via its Transaction-Time ``in_z`` timestamp and declares no such attribute.
    """
    for attribute in entity.attributes:
        if attribute.get("optimisticLocking"):
            return attribute["column"]
    return None


def _tag(entity: Entity) -> tuple[str, Any] | None:
    """The (column, value) a table-per-hierarchy INSERT writes, or None (m-inheritance).

    A TABLE-PER-HIERARCHY concrete subtype maps to a shared table discriminated by
    the root's ``tag`` column; the value THIS subtype's rows carry is its
    ``tagValue``. On a write that column is FRAMEWORK-DERIVED — set from the declared
    ``tagValue``, never carried in the neutral write input (①), exactly as the version
    column's advance is derived. A TABLE-PER-CONCRETE-SUBTYPE subtype has its own
    table and no tag (``tagValue`` is absent, m-inheritance), so this returns
    ``None`` and the write is an ordinary single-table write. The concrete subtype's
    flattened definition (:func:`inheritance.resolve_effective_definition`) carries
    both the resolved root ``tag`` column and the subtype's own ``tagValue``.
    """
    return tag_of(entity.runtime_facts)


def _close_address_binds(case: Case, entity: Entity, pk: Any, valid_end: Any) -> list[Any]:
    """The binds a milestone close's ADDRESS carries, in rendered predicate order.

    A close addresses the ONE stored milestone it means to close, and that address is
    identical in both concurrency modes: the primary key, the table-per-hierarchy tag
    GUARD that rides the identity predicates right after it (m-inheritance), then one
    exclusive upper bound PER As-Of Axis in canonical dimension rank. The
    Transaction-Time end is invariantly the open bound, because only a
    Transaction-Time-current milestone is closable; the Valid-Time end is the observed
    rectangle's OWN end, which may be finite — a key plus the open Transaction-Time
    bound alone would select every disjoint current rectangle of that key
    (`m-bitemp-write`). An optimistic gate is appended AFTER the address, never woven
    into it.
    """
    tag = _tag(entity)
    binds: list[Any] = [pk] if tag is None else [pk, tag[1]]
    for axis in _as_of_axes(entity):
        if axis["dimension"] != "valid-time":
            binds.append(axis.get("infinity", "infinity"))
            continue
        if valid_end is None:
            raise CaseFailure(
                f"{case.path.name}: a Bitemporal close of {entity.name} carries no observed "
                f"Valid-Time end — the address needs one exclusive upper bound per As-Of "
                f"Axis, and only the Transaction-Time one is invariant."
            )
        binds.append(valid_end)
    return binds


def _primary_key_columns(entity: Entity) -> list[str]:
    """The physical primary-key column(s) of *entity* (its flattened definition)."""
    return [a["column"] for a in entity.attributes if a.get("primaryKey")]


def _is_existing_row_statement(statement: str) -> bool:
    """True for an existing-row write (UPDATE / DELETE), False for an INSERT.

    A table-per-hierarchy existing-row statement carries the tag guard; an INSERT
    derives the tag COLUMN instead. This classifies by the leading verb so it covers
    the milestone TEMPORAL closes / inactivations (an ``update <table> set out_z = ?
    …``, m-txtime-write / m-bitemp-write) alongside the plain non-temporal
    ``update`` / ``delete`` — both are existing-row writes that MUST carry the guard,
    while the chained milestone INSERTs are not.
    """
    head = statement.lstrip().lower()
    return head.startswith("update ") or head.startswith("delete ")


def _assert_inheritance_write_routing(
    case: Case,
    entity: Entity,
    step_statements: list[str],
    step_binds: list[list[Any]],
    dialect: str,
) -> None:
    """Assert an inheritance write's golden DML routes and guards correctly.

    A no-op on a non-inheritance entity. For a TABLE-PER-HIERARCHY concrete subtype
    every EXISTING-ROW statement in the step — a plain ``update`` / ``delete`` OR a
    milestone TEMPORAL close / inactivation (m-txtime-write / m-bitemp-write) — MUST
    carry the tag GUARD among the identity predicates, canonically right after the
    primary key (m-inheritance, m-sql); a chained milestone INSERT derives the tag
    COLUMN instead (cross-checked by :func:`_assert_insert_statement` /
    :func:`_assert_temporal_input`). For a TABLE-PER-CONCRETE-SUBTYPE concrete subtype
    every write (insert / close / delete) MUST target the subtype's OWN table (no
    shared table, no tag).

    Both facts are read off the golden's PARSE for the executing *dialect*, never off
    its text: the physical table and the guarded columns are rendered quoted where
    they are reserved or otherwise non-simple, and the quote character itself diverges
    per dialect (`m-dialect`).
    """
    tag = _tag(entity)
    if tag is not None:  # table-per-hierarchy concrete subtype
        for statement, binds in zip(step_statements, step_binds, strict=True):
            if _is_existing_row_statement(statement):
                _assert_existing_row_tag_guard(case, entity, statement, binds, dialect)
        return
    if entity.role == "concrete-subtype":  # table-per-concrete-subtype (tag is None)
        for statement in step_statements:
            _assert_concrete_table_routing(case, entity, statement, dialect)


def _assert_existing_row_tag_guard(
    case: Case, entity: Entity, statement: str, binds: list[Any], dialect: str
) -> None:
    """A table-per-hierarchy existing-row write carries the tag guard after the PK.

    The tag guard is the ``<tag.column> = ?`` equality joining the identity predicates
    immediately after the primary-key equality (m-inheritance / m-sql; resolved Q9),
    and its ``?`` binds the concrete subtype's ``tagValue`` — framework-derived, so it
    is pinned to the model, never authored. The optimistic version gate, when present,
    still binds LAST (after the tag).

    Both halves are read off the statement's own parse — the guard's shape from the
    predicate's first two conjuncts (:func:`_existing_row_write`), its bind position
    from the scanned placeholder count (:func:`_predicate_bind_offset`) — because a
    literal ``<pk> = ? and <tag> = ?`` fragment finds neither a quoted physical column
    nor a legally reformatted predicate, and a textual ``?`` count includes the ones
    inside string literals and quoted identifiers, which bind nothing.
    """
    tag_column, tag_value = _tag(entity)  # type: ignore[misc]
    pk_columns = _primary_key_columns(entity)
    if len(pk_columns) != 1:  # the inheritance families key on a single-column pk (`id`)
        return
    write = _existing_row_write(statement, dialect)
    offset = _predicate_bind_offset(statement)
    guarded = (
        write is not None
        and len(write.conjuncts) > 1
        and _gates_on(write.conjuncts[0], pk_columns[0])
        and _gates_on(write.conjuncts[1], tag_column)
    )
    if not guarded or offset is None:
        raise CaseFailure(
            f"{case.path.name}: a table-per-hierarchy existing-row write of "
            f"{entity.name} MUST carry the tag guard immediately after the primary-key "
            f"equality (`{pk_columns[0]} = ? and {tag_column} = ?`), not found in golden "
            f"{statement!r}."
        )
    # The pk equality opens the predicate and binds one placeholder, so the tag's own
    # bind lands one past it — after the SET placeholders, before any opt-lock gate,
    # in either concurrency mode.
    tag_bind_index = offset + 1
    if tag_bind_index >= len(binds) or not _write_value_equal(tag_value, binds[tag_bind_index]):
        actual = binds[tag_bind_index] if tag_bind_index < len(binds) else "<missing>"
        raise CaseFailure(
            f"{case.path.name}: the tag guard binds {actual!r} at position "
            f"{tag_bind_index}, but concrete subtype {entity.name}'s tagValue is "
            f"{tag_value!r} (the tag is framework-derived, never authored)."
        )


def _assert_concrete_table_routing(
    case: Case, entity: Entity, statement: str, dialect: str
) -> None:
    """A table-per-concrete-subtype write targets the subtype's OWN table.

    There is no shared table and no tag column (m-inheritance), so the concrete
    subtype is selected by WHICH table the DML targets: an insert / delete of that
    subtype MUST name its own table. The golden's target is compared to the model by
    the identifier it SPELLS (:func:`_dml_target`, :func:`_names`), so a reserved
    physical table routes correctly under the quoting each dialect renders it with.
    """
    target = _dml_target(statement, dialect)
    if target is None:
        raise CaseFailure(
            f"{case.path.name}: could not read the DML target table from golden {statement!r}."
        )
    if not _names(target, entity.table):
        raise CaseFailure(
            f"{case.path.name}: a table-per-concrete-subtype write of {entity.name} MUST "
            f"target its own table {entity.table!r} (no shared table), but the golden "
            f"targets {target.sql(dialect=sqlglot_dialect(dialect))}: {statement!r}."
        )


def _bytes_to_hex(value: Any) -> Any:
    """Render a ``bytes`` / ``memoryview`` value as lowercase hex text, else unchanged.

    The neutral write input (①) authors a ``bytes`` column as its wire form — a
    lowercase hex STRING (a ``bytes`` object is not a JSON type the write-row schema
    admits), while the golden bind carries the raw bytes (a ``!!binary`` tag). Both
    collapse to the same lowercase hex text here so ① ↔ golden cross-checking and
    table-state read-back compare a ``bytes`` column dialect-agnostically.
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


def _assert_carried_document(
    case: Case, derived: Any, golden: Any, statement: str, path: str = ""
) -> None:
    """Grade one chained milestone's Structured Column against the members ① names.

    A temporal successor's document is its predecessor's, patched. ① states one
    logical row and can therefore fix only what the model declares; every other key
    the golden carries came from the row the successor supersedes, which is the
    whole claim of retaining that document rather than rebuilding it. So every
    position ① resolves — each top-level member and, inside an occurrence, each of
    ITS declared members — MUST appear with the value the codec spells for it, while
    a key ① names nowhere is admitted rather than refused.
    """
    if not isinstance(golden, dict) or not isinstance(derived, dict):
        raise CaseFailure(
            f"{case.path.name}: the golden chained-milestone Structured Column bind {golden!r} "
            f"is not a document at {path or 'the document root'!r} for {statement!r}."
        )
    for key, want in derived.items():
        location = f"{path}.{key}" if path else key
        if key not in golden:
            raise CaseFailure(
                f"{case.path.name}: the neutral write input names {location!r} inside the "
                f"Structured Column, and the golden chained-milestone document omits it for "
                f"{statement!r}."
            )
        _assert_carried_value(case, want, golden[key], statement, location)


def _assert_carried_value(case: Case, derived: Any, golden: Any, statement: str, path: str) -> None:
    """Grade one position of a carried document: a subtree, an array, or a leaf.

    An array is the stored form of a `many` occurrence, which is ordered and
    compares element by element at equal length (`m-document-codec`), so position
    pairs the two sides and each element is graded on the same terms the enclosing
    document is — an element that is itself a document admits a key ① names
    nowhere, exactly as the document around it does.
    """
    if isinstance(derived, dict) and isinstance(golden, dict):
        _assert_carried_document(case, derived, golden, statement, path)
        return
    if isinstance(derived, list) and isinstance(golden, list):
        if len(derived) != len(golden):
            raise CaseFailure(
                f"{case.path.name}: the neutral write input's {path!r} array carries "
                f"{len(derived)} element(s) and the golden chained-milestone document carries "
                f"{len(golden)} for {statement!r}."
            )
        for index, (element, golden_element) in enumerate(zip(derived, golden, strict=True)):
            _assert_carried_value(case, element, golden_element, statement, f"{path}[{index}]")
        return
    if not _write_value_equal(derived, golden):
        raise CaseFailure(
            f"{case.path.name}: neutral write input value {derived!r} != golden document key "
            f"{path!r} value {golden!r} for {statement!r}."
        )


def _parse_insert_columns(case: Case, statement: str) -> list[str]:
    """The columns an INSERT names: the parenthesised list following its target table.

    Read through :func:`_sql_scan` for the same reason its `set`-clause sibling is: a
    quoted identifier may itself carry a bracket or a comma, and neither is syntax
    there.
    """
    columns = _insert_column_list(statement)
    if columns is None:
        raise CaseFailure(
            f"{case.path.name}: could not parse the INSERT column list from golden {statement!r}."
        )
    return [column.strip() for column in _top_level_commas(columns)]


def _insert_column_list(statement: str) -> str | None:
    """The text between the parentheses that follow an INSERT's target table, or
    ``None`` when the statement is not an INSERT or opens no such list."""
    if not _keyword_at(statement.lstrip().lower(), 0, "insert"):
        return None
    opened: int | None = None
    for index, char, depth in _sql_scan(statement):
        if char == "(" and depth == 1 and opened is None:
            opened = index + 1
        elif char == ")" and depth == 0 and opened is not None:
            return statement[opened:index]
    return None


def _parse_set_columns(case: Case, statement: str) -> list[str]:
    clause = _set_clause(statement)
    if clause is None:
        raise CaseFailure(
            f"{case.path.name}: could not parse the SET clause from golden {statement!r}."
        )
    return [_assigned_column(piece) for piece in _top_level_commas(clause)]


def _sql_scan(sql: str) -> Iterator[tuple[int, str, int]]:
    """Each character of *sql* OUTSIDE a quoted identifier or string literal, with
    its index and its bracket depth.

    Every reader that takes a golden statement apart by COLUMN goes through here —
    an INSERT's column list, an UPDATE's `set` clause, its assignments, and each
    assignment's own `=` — because a column name is any nonempty string and a
    dialect quotes one that is reserved or otherwise non-simple (`m-dialect`): a
    comma, a bracket, an `=`, and the word `where` can each sit inside an
    identifier, and none of them is syntax there.
    """
    quote = ""
    depth = 0
    for index, char in enumerate(sql):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"`'":
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        yield index, char, depth


def _keyword_at(lowered: str, index: int, keyword: str) -> bool:
    """Whether *keyword* occupies a whole word at *index* of a lowercased statement."""
    if not lowered.startswith(keyword, index):
        return False
    before = lowered[index - 1] if index else " "
    after = lowered[index + len(keyword) :][:1] or " "
    return not _word_char(before) and not _word_char(after)


def _word_char(char: str) -> bool:
    return char.isalnum() or char == "_"


def _set_clause(statement: str) -> str | None:
    """An UPDATE's `set` clause: what sits between its own `set` and `where` keywords.

    Both delimiters are read at bracket depth zero and outside quotes, so neither a
    subquery's own keyword nor a column named `set` or `where` — legal, and quoted
    for exactly that reason — delimits the clause.
    """
    lowered = statement.lower()
    start: int | None = None
    for index, _char, depth in _sql_scan(statement):
        if depth:
            continue
        if start is None:
            if _keyword_at(lowered, index, "set"):
                start = index + len("set")
        elif _keyword_at(lowered, index, "where"):
            return statement[start:index].strip()
    return None


def _assigned_column(assignment: str) -> str:
    """The column one `set` term names: what sits left of its own top-level `=`."""
    for index, char, depth in _sql_scan(assignment):
        if char == "=" and depth == 0:
            return assignment[:index].strip()
    return assignment.strip()


def _top_level_commas(clause: str) -> list[str]:
    """*clause* split on the commas that separate its assignments.

    A `set` term's right-hand side may itself be a call taking commas — the
    document mutation expression is nested `jsonb_set` calls on Postgres and one
    N-pair `json_set` on MariaDB (m-dialect) — so only a comma at bracket depth
    zero ends an assignment. A comma inside a quoted identifier or a string literal
    ends nothing at all: `set "payload,archive" = ?` is one assignment, not two.
    """
    parts: list[str] = []
    start = 0
    for index, char, depth in _sql_scan(clause):
        if char == "," and depth == 0:
            parts.append(clause[start:index])
            start = index + 1
    parts.append(clause[start:])
    return parts


def _assert_write_input_columns(case: Case, dialect: str) -> None:
    """Cross-check each non-temporal write step's neutral input (①) against golden (②).

    The corpus is self-validating regardless of any adapter: a GENERATING adapter
    derives the emitted column list from ① (``rows``) classified against the model,
    so the harness asserts that same classification agrees with the authored golden.
    Per non-temporal write step the columns ① resolves to — in Table Layout
    order, filtered to the present attributes — MUST equal the golden's INSERT / SET
    column list, and ①'s values MUST equal the write-value prefix of the golden
    binds. Comparing against the golden HERE is legitimate: the harness compares two
    AUTHORED representations, never grading its own generation.

    A TEMPORAL step is Family B: it ALWAYS writes the entity's full physical row, so
    the column list stays layout-sourced (``_write_column_order``) and ① carries only the
    domain values (``rows``) plus the handle-supplied transaction instant ``at``
    (→ ``in_z``), with the ``start_column = instant`` / ``end_column = infinity``
    bookkeeping DERIVED, never authored (:func:`_assert_temporal_input`). A
    full-bitemporal ``*Until`` step is the rectangle-split analogue: its ① carries the
    valid-time window (``at`` / ``until`` / ``validFrom``), cross-checked by
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
        mutation = step["mutation"]
        # Whether ① describes a row being OPENED whole or a sparse revision. The
        # mutation decides it for a non-temporal step; a TEMPORAL step's every
        # chained milestone writes the entity's full physical row whatever verb
        # opened it (`m-txtime-write` / `m-bitemp-write`), so its ① is an opening
        # row even under `update` / `terminate`.
        classified = [
            _classify_write_row(
                case,
                entity,
                row,
                mutation=mutation,
                opening=mutation in _OPENING_MUTATIONS or entity.is_temporal,
            )
            for row in rows
        ]
        # `m-unit-work`'s temporal singleton, asked of this lane through the SAME
        # validator the rejected lane and the buffered scenario write reach: a
        # writeSequence step carries the keyed instruction's own members
        # (`mutation` / `entity` / `rows`), so it is judged as one rather than by a
        # count restated here. The shared `rows` array states the general
        # one-or-more bound because the singleton is model-dependent, and the
        # temporal cross-checks below read the first row alone — so a plural
        # authoring would leave a later row graded against nothing.
        try:
            validate_keyed_write(entity, step)
        except RejectionError as exc:
            raise CaseFailure(
                f"{case.path.name}: writeSequence step on {step['entity']}: {exc.detail}"
            ) from exc
        step_statements = statements[stmt_index : stmt_index + count]
        step_binds = [case.statement_binds(stmt_index + offset, dialect) for offset in range(count)]
        # A full-bitemporal step is a RECTANGLE SPLIT: the windowed `*Until` trio, or
        # a plain (unbounded) `update` / `terminate` on a two-axis entity (the everyday
        # retroactive correction / termination, `m-bitemp-write-006` / `-007`). Both close
        # the original on the Transaction-Time dimension and chain head / (new-)tail milestones, so
        # both route through the rectangle-split cross-check — never the audit-only
        # close-and-open, which would mis-count the chained inserts.
        if mutation in _UNTIL_MUTATIONS or (
            _is_bitemporal(entity) and mutation in _PLAIN_SPLIT_MUTATIONS
        ):
            _assert_until_input(
                case, entity, classified, step, step_statements, step_binds, dialect
            )
        elif entity.is_temporal:
            _assert_temporal_input(
                case, entity, classified, step, step_statements, step_binds, dialect
            )
        elif mutation == "insert":
            _assert_insert_input(case, entity, classified, step_statements, step_binds)
        elif mutation in ("delete", "cascadeDelete"):
            _assert_delete_input(case, classified, step_binds)
        elif _version_column(entity) is not None:
            _assert_versioned_update_input(
                case,
                entity,
                case.concurrency_mode,
                classified,
                step_statements,
                step_binds,
                dialect=dialect,
                rows=rows,
            )
        else:
            _assert_update_input(
                case,
                entity,
                classified,
                step_statements,
                step_binds,
                dialect=dialect,
                rows=rows,
            )
        # Inheritance write routing: a TABLE-PER-HIERARCHY
        # existing-row statement (a plain update/delete OR a temporal close/inactivation)
        # carries the tag guard after the pk; a TABLE-PER-CONCRETE-SUBTYPE write targets
        # the subtype's own table. A no-op on a non-inheritance entity and on a chained
        # INSERT (whose tag COLUMN is cross-checked by _assert_insert_statement /
        # _assert_temporal_input).
        _assert_inheritance_write_routing(case, entity, step_statements, step_binds, dialect)
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
    order = _write_column_order(case, entity)
    domain = [c for c in order if any(c in cols for cols, *_ in classified)]
    # A TABLE-PER-HIERARCHY insert writes the tag column from the concrete subtype's
    # tagValue (m-inheritance) — a FRAMEWORK-DERIVED column, never carried in ① —
    # slotted at its Discriminator-tier position, exactly as the version column is derived.
    tag = _tag(entity)
    if tag is not None and tag[0] in domain:
        raise CaseFailure(
            f"{case.path.name}: the neutral write input (①) carries the tag "
            f"column {tag[0]!r}, which a table-per-hierarchy write derives from "
            f"the concrete subtype's tagValue (m-inheritance), never authored."
        )
    emitted = [c for c in order if c in domain or (tag is not None and c == tag[0])]
    # A VERSIONED insert appends the framework-owned version column with the DERIVED
    # initial value `1` (never authored in ①, so it is not in the row's columns).
    present = [*emitted, version_col] if version_col is not None else emitted
    if golden_columns != present:
        raise CaseFailure(
            f"{case.path.name}: the golden INSERT column list {golden_columns} != the "
            f"columns the neutral write input resolves to {present} (Table Layout order, "
            f"present attributes"
            f"{' + derived tag' if tag is not None else ''}"
            f"{' + derived version' if version_col is not None else ''})."
        )
    # A DB-computed marker is a SCALAR-ATTRIBUTE-only interpretation (m-value-object):
    # a value-object (document) column ALWAYS binds its whole literal document in
    # Document-tier slot, so it is excluded here even when the authored document is
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
            if tag is not None and column == tag[0]:
                # The tag's bind is the concrete subtype's tagValue, DERIVED
                # from the model (m-inheritance), never an ① literal.
                expected.append(tag[1])
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
    *,
    dialect: str,
    rows: list[dict[str, Any]],
) -> None:
    """Cross-check a VERSIONED writeSequence update step's ① against its golden (②).

    The golden SET clause is the domain set columns + the framework-owned ``version``
    column (advanced ``observedVersion + 1``, DERIVED — never authored in ①). The
    binds are ``[…set values…, newVersion, pk]`` under the Locking strategy a
    declared ``locking`` preference imposes (``m-opt-lock-002`` / ``m-detach-002``
    — the m-read-lock shared read lock makes the write correct, so no
    ``and version = ?`` gate) or ``[…, newVersion, pk, observedVersion]`` under
    the Optimistic strategy a versioned target takes by default. One golden
    statement per ① row.

    Under Relational Document Layout the Structured Column is one further `set`
    term, carrying the dialect's mutation expression and contributing one
    ``(path, value)`` PAIR per assigned Document Path in the layout's own order —
    the same contribution :func:`_assert_update_input` derives for an unversioned
    row. The version Column stays a plain assignment after it, because an explicit
    optimistic-lock Attribute keeps a Column of its own under either layout.
    """
    version_col = _version_column(entity)
    document_column, _resident = _document_layout_members(case, entity)
    assignments = (
        [_document_assignments(case, entity, row) for row in rows] if document_column else []
    )
    patches_document = any(assignments)
    for (_, pk, set_cols, observed), patches, statement, binds in zip(
        classified,
        assignments or [()] * len(classified),
        step_statements,
        step_binds,
        strict=True,
    ):
        golden_set = _parse_set_columns(case, statement)
        set_present = [
            c
            for c in _write_column_order(case, entity)
            if c in set_cols or (patches_document and c == document_column)
        ]
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
        set_values: list[Any] = []
        for column in set_present:
            if column == document_column and patches_document:
                set_values.extend(_document_assignment_binds(patches, dialect))
                continue
            set_values.append(set_cols[column])
        expected = [*set_values, observed + 1, pk]
        # A TABLE-PER-HIERARCHY concrete subtype's existing-row UPDATE carries the tag
        # GUARD among the identity predicates — canonically right after the primary key
        # (m-inheritance, m-sql; resolved Q9). The optimistic gate still binds LAST, so
        # the tag value slots between the pk and the observed-version gate.
        tag = _tag(entity)
        if tag is not None:
            expected.append(tag[1])
        if mode == "optimistic":
            expected.append(observed)  # the optimistic gate bind — always LAST
        _assert_write_values(case, expected, binds, statement)


def _assert_update_input(
    case: Case,
    entity: Entity,
    classified: list[tuple[dict[str, Any], Any, dict[str, Any], Any]],
    step_statements: list[str],
    step_binds: list[list[Any]],
    *,
    dialect: str,
    rows: list[dict[str, Any]],
) -> None:
    """Cross-check a plain (unversioned, non-temporal) update step's ① against ②.

    Under Relational Document Layout the Structured Column is one `set` term
    carrying the dialect's mutation expression rather than one bind, so its
    contribution to the golden binds is one ``(path, value)`` PAIR per assigned
    Document Path, in the layout's own order. Everything else — which columns the
    `set` clause names, and in what order — is unchanged, because a document
    assignment is still one column assignment.
    """
    document_column, resident = _document_layout_members(case, entity)
    assignments = (
        [_document_assignments(case, entity, row) for row in rows] if document_column else []
    )
    patches_document = any(assignments)
    set_present = [
        c
        for c in _write_column_order(case, entity)
        if any(c in set_cols for _, _, set_cols, _ in classified)
        or (patches_document and c == document_column)
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

    def expected_values(
        set_cols: dict[str, Any], patches: tuple[_DocumentAssignment, ...]
    ) -> list[Any]:
        values: list[Any] = []
        for column in set_present:
            if column == document_column and patches_document:
                values.extend(_document_assignment_binds(patches, dialect))
                continue
            values.append(_set_bind_value(column, set_cols[column], document_columns))
        return values

    if per_key:
        for (_, _, set_cols, _), patches, binds, statement in zip(
            classified,
            assignments or [()] * len(classified),
            step_binds,
            step_statements,
            strict=True,
        ):
            expected = expected_values(set_cols, patches)
            _assert_write_values(case, expected, binds[: len(expected)], statement)
        return
    _assert_uniform_assignments(case, entity, classified, assignments)
    first_set = classified[0][2] if classified else {}
    expected = expected_values(first_set, assignments[0] if assignments else ())
    binds = step_binds[0] if step_binds else []
    statement = step_statements[0] if step_statements else ""
    _assert_write_values(case, expected, binds[: len(expected)], statement)


def _assert_uniform_assignments(
    case: Case,
    entity: Entity,
    classified: list[tuple[dict[str, Any], Any, dict[str, Any], Any]],
    assignments: list[tuple[_DocumentAssignment, ...]],
) -> None:
    """Every row of a COLLAPSED update assigns the identical non-key values.

    One statement addressing several keys carries ONE assignment shape, so
    `m-batch-write` collapses a run only when the values are uniform across the
    keys and keeps incompatible writes in separate steps. That is what licenses
    the first row to stand for the step: without it, a later row's changed value
    would ride a golden derived from the first and the case would pass on a
    statement that never writes it.
    """
    for position, (_columns, pk, set_cols, _observed) in enumerate(classified[1:], start=1):
        patches = assignments[position] if assignments else ()
        if set_cols == classified[0][2] and patches == (assignments[0] if assignments else ()):
            continue
        raise CaseFailure(
            f"{case.path.name}: a collapsed {entity.name} UPDATE is ONE statement over several "
            f"keys, so every ① row assigns the identical non-key values (m-batch-write) — row "
            f"{position} (pk {pk!r}) assigns {sorted(set_cols.items())!r} against row 0's "
            f"{sorted(classified[0][2].items())!r}; incompatible values stay separate steps."
        )


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
    dialect: str,
) -> None:
    """Cross-check a Transaction-Time-Only write step's ① against its golden DML.

    A milestone-chaining write ALWAYS writes the entity's full physical row (DQ-B
    Family B), so the emitted column list is layout-sourced (``_write_column_order``) —
    ① carries only the domain values (``rows``) plus the handle-supplied
    Transaction-Time instant ``at`` (→ ``in_z``). The bookkeeping
    ``start_column = instant`` and the open bound
    ``end_column = infinity`` are DERIVED, never authored in ① (the m-temporal-read milestone
    discipline stays under test). The gate cross-checks, per statement: an ``insert``
    (open a milestone) writes the full physical row with ``start_column = instant`` and
    ``end_column = infinity``; a close (``update`` step 1 / ``terminate``) binds
    ``[instant, pk, infinity]`` — sets ``end_column = instant`` addressed on the one
    Transaction-Time-current milestone, which on a single axis is the pk plus
    ``end_column = infinity`` alone (:func:`_close_address_binds`); an ``update``
    chains a second full-row insert carrying the row's columns.

    A BITEMPORAL step never reaches this cross-check's close: a two-axis
    ``update`` / ``terminate`` is a rectangle split routed to
    :func:`_assert_until_input`, and only its opening ``insert`` lands here.
    """
    transaction_time = next(
        (a for a in entity.temporal_runtime_axes if a["dimension"] == "transaction-time"), None
    )
    if transaction_time is None:
        raise CaseFailure(
            f"{case.path.name}: active temporal writes require a Transaction-Time dimension."
        )
    valid_time = next(
        (a for a in entity.temporal_runtime_axes if a["dimension"] == "valid-time"), None
    )
    axis, at, instant_key = transaction_time, step.get("at"), "at"
    in_z, infinity = axis["start_column"], axis.get("infinity", "infinity")
    full_columns = list(_write_column_order(case, entity))
    if at is None:
        raise CaseFailure(
            f"{case.path.name}: a temporal write step's neutral write input (①) MUST carry "
            f"`{instant_key}` (the milestone instant → {in_z}), which is DERIVED into the "
            f"milestone bookkeeping, never read from the golden."
        )
    valid_from = step.get("validFrom")
    if valid_time is not None and valid_from is None:
        raise CaseFailure(
            f"{case.path.name}: a Valid-Time write step's neutral write input (①) MUST "
            "carry `validFrom`, which is DERIVED into the start column."
        )
    derived_starts = {
        transaction_time["start_column"]: step.get("at"),
        **({valid_time["start_column"]: valid_from} if valid_time is not None else {}),
    }
    derived_ends = {temporal_axis["end_column"] for temporal_axis in entity.temporal_runtime_axes}
    # The step's only row: a temporal step carrying any other count is refused
    # before this cross-check runs.
    (columns, pk, _set_cols, _observed) = classified[0]
    # A TABLE-PER-HIERARCHY concrete subtype's milestone rows carry the framework-owned
    # tag column, DERIVED from its `tagValue` (m-inheritance) — the chained INSERT sets
    # it at its Discriminator-tier slot and the close GUARDS on it right after the pk, exactly
    # as the non-temporal concrete-subtype write does. `None` for a table-per-concrete-
    # subtype / non-inheritance entity (an ordinary single-table milestone write).
    tag = _tag(entity)
    document_column, _resident = _document_layout_members(case, entity)

    def assert_open(statement: str, binds: list[Any]) -> None:
        golden_columns = _parse_insert_columns(case, statement)
        if golden_columns != full_columns:
            raise CaseFailure(
                f"{case.path.name}: the golden temporal INSERT column list {golden_columns} != "
                f"the entity's full physical row {full_columns} — a milestone always writes the "
                f"whole row (metamodel-sourced, not derived from ①)."
            )
        expected = [
            derived_starts[column]
            if column in derived_starts
            else infinity
            if column in derived_ends
            else tag[1]
            if (tag is not None and column == tag[0])
            else columns.get(column)
            for column in full_columns
        ]
        if not document_column or len(binds) != len(expected):
            _assert_write_values(case, expected, binds, statement)
            return
        # Under Relational Document Layout a chained milestone's Structured Column
        # is the predecessor's own document with the mutation's changes patched
        # into it, so ① fixes the members it names and NOT the whole document: a
        # key no member declares rides forward from the row the successor
        # supersedes, and `then.tableState` is what grades that it did.
        position = full_columns.index(document_column)
        _assert_carried_document(case, expected[position], binds[position], statement)
        _assert_write_values(
            case,
            [*expected[:position], *expected[position + 1 :]],
            [*binds[:position], *binds[position + 1 :]],
            statement,
        )

    def assert_close(statement: str, binds: list[Any]) -> None:
        # A close sets `out_z = at` on the milestone its address selects — no domain
        # values, just the derived bounds. A Transaction-Time-Only entity has one axis,
        # so the address supplies no observed Valid-Time end. Whether the close also
        # GATES is decided by the SQL shape, exactly as the bitemporal split's own
        # close is: a gated one appends the observed milestone's `in_z` LAST, and the
        # gate's bind is reconstructed from the case's own history rather than
        # authored on the step (:func:`_observed_milestone_start`).
        expected = [at, *_close_address_binds(case, entity, pk, None)]
        if _has_temporal_gate(statement, transaction_time["start_column"], dialect):
            expected.append(_observed_milestone_start(case, entity, step, pk))
        _assert_write_values(case, expected, binds, statement)

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
    dialect: str,
) -> None:
    """Cross-check a full-bitemporal RECTANGLE-SPLIT step's ① against its golden (②).

    A rectangle-split write inactivates the observed rectangle on the TRANSACTION-TIME
    axis at the transaction instant and chains head / (middle) / (new-)tail rows at
    fresh Transaction Time ``[at, infinity)``, partitioned on the VALID-TIME axis around
    the mutation instant. Three forms share this cross-check:

      * a WINDOWED ``*Until`` write bounds the change to ``[validFrom, until)``
        (`m-bitemp-write-001` / `-002` / `-008`); ① carries both ``at`` and ``until``;
      * a PLAIN (unbounded) ``update`` / ``terminate`` corrects/ends the value from
        ``validFrom`` ONWARD (`m-bitemp-write-006` / `-007`); ① carries ``at`` but
        no ``until`` — the residual window runs to the open bound (``thru_z``);
      * an OPENING ``insertUntil`` (`m-bitemp-write-003`) has no prior rectangle to
        close, so it is the single bounded INSERT the other two chain around.

    Like the audit-only close it is Family B (full physical row, metamodel-sourced
    column list), so the cross-check is BINDS-only on the DERIVED coordinates ①
    supplies:

      * the inactivating close (the ``update … set out_z = ? where …`` statement) binds
        ``[at, …address…]`` (:func:`_close_address_binds`) — the observed rectangle's
        own Valid-Time end then the invariant Transaction-Time infinity, IDENTICAL in
        both concurrency modes. A GATED close (`m-bitemp-write-008`, optimistic)
        appends the observed rectangle's ``in_z`` LAST. Neither coordinate is present
        in the closing step's own ① row, so both are reconstructed from the case's own
        earlier steps (:func:`_observed_rectangle`); the gate rides the golden directly
        (no ``observedTxStart`` token on the writeSequence step);
      * every chained INSERT opens a fresh Transaction-Time milestone, so its ``in_z``
        bind equals ``at`` and its ``out_z`` bind equals ``infinity``;
      * the chained inserts' Valid-Time windows (``from_z`` / ``thru_z``) are EXACTLY
        the successors the split re-opens (:func:`_split_successors`) from ①'s
        ``validFrom`` / ``until`` and the reconstructed rectangle's own bounds, in
        head / middle / tail order.

    The domain values are carried, not derived, so they are graded observably by
    ``then.tableState`` in the run rather than restated in ①.
    """
    valid_time = next(a for a in entity.temporal_runtime_axes if a["dimension"] == "valid-time")
    transaction_time = next(
        a for a in entity.temporal_runtime_axes if a["dimension"] == "transaction-time"
    )
    from_z, thru_z = valid_time["start_column"], valid_time["end_column"]
    in_z, out_z = transaction_time["start_column"], transaction_time["end_column"]
    infinity = transaction_time.get("infinity", "infinity")
    full_columns = list(_write_column_order(case, entity))
    in_z_pos, out_z_pos = full_columns.index(in_z), full_columns.index(out_z)
    from_z_pos, thru_z_pos = full_columns.index(from_z), full_columns.index(thru_z)

    mutation = step["mutation"]
    windowed = mutation in _UNTIL_MUTATIONS
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
            f"`until` (the Valid-Time window end → thru_z), which is DERIVED, never read "
            f"from the golden."
        )
    # The step's only row, as above: a plural temporal step never reaches here.
    (_columns, pk, _set_cols, _version) = classified[0]
    valid_from = step.get("validFrom")
    if valid_from is None:
        raise CaseFailure(
            f"{case.path.name}: a bitemporal rectangle-split step's ① row MUST carry the "
            f"Valid-Time window start (`validFrom` → {from_z}), which discriminates the "
            f"chained rows."
        )
    if mutation in _OPENING_MUTATIONS:
        observed = None
        expected_windows = [(valid_from, until)]
    else:
        observed = _observed_rectangle(case, entity, step, pk)
        expected_windows = [
            (rectangle.valid_start, rectangle.valid_end)
            for rectangle in _split_successors(mutation, observed, valid_from, until, at)
        ]

    chained_windows: list[tuple[Any, Any]] = []
    for statement, binds in zip(step_statements, step_binds, strict=True):
        if "insert into" in statement.lower():
            # A chained milestone opens at fresh Transaction Time [at, infinity).
            _assert_write_values(case, [at], [binds[in_z_pos]], statement)
            _assert_write_values(case, [infinity], [binds[out_z_pos]], statement)
            chained_windows.append((binds[from_z_pos], binds[thru_z_pos]))
            continue
        if observed is None:
            raise CaseFailure(
                f"{case.path.name}: an opening `{mutation}` step has no prior rectangle to "
                f"close, but its golden carries the close {statement!r}."
            )
        # The inactivation: out_z = at on the ADDRESSED rectangle. Whether the close is
        # GATED (optimistic) is decided by the SQL SHAPE — never by a longer bind row —
        # so a close with spurious trailing binds fails as a mismatch rather than being
        # tolerated as gated, and a gated one pairs its single trailing predicate with
        # EXACTLY one trailing bind.
        expected = [at, *_close_address_binds(case, entity, pk, observed.valid_end)]
        gated = _has_temporal_gate(statement, in_z, dialect)
        if gated:
            expected.append(observed.tx_start)
        placeholders = statement.count("?")
        if placeholders != len(expected) or len(binds) != len(expected):
            raise CaseFailure(
                f"{case.path.name}: the {'gated' if gated else 'ungated'} bitemporal close "
                f"{statement!r} carries {placeholders} placeholder(s) and {len(binds)} "
                f"bind(s), but its derived shape is {len(expected)} — every close renders "
                f"the address `pk [and tag = ?] and {thru_z} = ? and {out_z} = ?`, and a "
                f"gated close appends the single `and {in_z} = ?` gate."
            )
        _assert_write_values(case, expected, binds, statement)

    _assert_split_successor_windows(case, expected_windows, chained_windows)


def _assert_split_successor_windows(
    case: Case,
    expected_windows: list[tuple[Any, Any]],
    chained_windows: list[tuple[Any, Any]],
) -> None:
    """The chained INSERTs' Valid-Time windows are exactly the derived successors."""
    matched = len(expected_windows) == len(chained_windows) and all(
        _write_value_equal(want_start, got_start) and _write_value_equal(want_end, got_end)
        for (want_start, want_end), (got_start, got_end) in zip(
            expected_windows, chained_windows, strict=False
        )
    )
    if not matched:
        raise CaseFailure(
            f"{case.path.name}: the chained inserts' Valid-Time windows {chained_windows!r} "
            f"!= the successors the rectangle split re-opens {expected_windows!r} — the "
            f"head / middle / tail windows are DERIVED from ①'s validFrom / until and the "
            f"closed rectangle's own bounds, never read from the golden."
        )


class _Rectangle(NamedTuple):
    """One milestone rectangle: its Valid-Time window and its Transaction-Time start.

    The Transaction-Time END is not carried because only a rectangle still current on
    that axis is addressable — a closed one is history no later step touches.
    """

    valid_start: Any
    valid_end: Any
    tx_start: Any


def _split_successors(
    mutation: str, closed: _Rectangle, valid_from: Any, until: Any, at: Any
) -> tuple[_Rectangle, ...]:
    """The rectangles a rectangle split re-opens at fresh Transaction Time ``at``.

    Every split re-opens the HEAD ``[closed.valid_start, validFrom)``. An ``update`` /
    ``updateUntil`` carries the changed slice on from ``validFrom`` — to ``until`` when
    the write is windowed, otherwise to the closed rectangle's own end — while a
    ``terminate`` / ``terminateUntil`` ends coverage there instead. A windowed split
    restores the TAIL ``[until, closed.valid_end)``, so a plain ``terminate`` is the
    one form that leaves everything from ``validFrom`` onward covered by no current
    rectangle.
    """
    windowed = mutation in _UNTIL_MUTATIONS
    head = _Rectangle(closed.valid_start, valid_from, at)
    changed = (
        ()
        if mutation in _TERMINATE_MUTATIONS
        else (_Rectangle(valid_from, until if windowed else closed.valid_end, at),)
    )
    tail = (_Rectangle(until, closed.valid_end, at),) if windowed else ()
    return (head, *changed, *tail)


def _edge_named_rectangle(
    case: Case, entity: Entity, pk: Any, valid_start: Any, tx_start: Any, pointer: str
) -> _Rectangle:
    """The ONE fixture milestone of *pk* whose own EDGE is (*valid_start*,
    *tx_start*) — the milestone a close named the edge of observed.

    A conflict case starts from its model's fixtures, so the milestones its
    address may select are exactly the fixture rows still current on Transaction
    Time. A milestone's edge is its guaranteed-selecting start instant per axis
    (`m-temporal-read`), which is what makes it a NAME for the milestone rather
    than a restatement of the close's address: several disjoint rectangles of one
    key may be current at once, and each carries a distinct edge while sharing
    the key, the open Transaction-Time bound, and possibly the gate.

    Both the address's Valid-Time end and the gate's Transaction-Time start are
    then read off this one row, so a close's address and its gate cannot come
    from two different milestones.
    """
    axes = {axis.dimension: axis for axis in temporal_axes(entity.runtime_facts)}
    valid_axis, tx_axis = axes["valid-time"], axes["transaction-time"]
    key_member = next(
        attribute["name"] for attribute in entity.attributes if attribute.get("primaryKey")
    )
    open_bound = "infinity"
    matched = [
        row
        for row in entity.rows
        if _write_value_equal(row.get(key_member), pk)
        and _write_value_equal(row.get(tx_axis.end.name), open_bound)
        and _write_value_equal(row.get(valid_axis.start.name), valid_start)
        and _write_value_equal(row.get(tx_axis.start.name), tx_start)
    ]
    if len(matched) != 1:
        raise CaseFailure(
            f"{case.path.name}: a close naming the observed edge "
            f"({valid_axis.start.name} {valid_start!r}, {tx_axis.start.name} {tx_start!r}) of "
            f"{entity.name} pk {pk!r} ({pointer}) selects {len(matched)} current fixture "
            f"milestone(s) — an edge names exactly one, and a close derives its address and "
            f"its gate from the one it named."
        )
    row = matched[0]
    return _Rectangle(valid_start, row.get(valid_axis.end.name), tx_start)


def _prior_steps_for_key(
    case: Case, entity: Entity, current_step: dict[str, Any], pk: Any
) -> Iterator[dict[str, Any]]:
    """Every writeSequence step BEFORE *current_step* that mutates *pk* of the
    same Entity, in authored order.

    Both temporal reconstructions replay this same history — the
    Transaction-Time-Only milestone and the bitemporal rectangle — so the filter
    lives here once. A row's key is not authored as such: it is what classifying
    the row against its own mutation yields, which is why the traversal cannot be
    a plain attribute comparison.
    """
    for prior in case.write_sequence:
        if prior is current_step:
            return
        if prior["entity"] != current_step["entity"]:
            continue
        prior_keys = [
            _classify_write_row(case, entity, row, mutation=prior["mutation"], opening=True)[1]
            for row in prior.get("rows", [])
        ]
        if any(_write_value_equal(prior_pk, pk) for prior_pk in prior_keys):
            yield prior


def _observed_milestone_start(case: Case, entity: Entity, step: dict[str, Any], pk: Any) -> Any:
    """The Transaction-Time start of the ONE milestone *step*'s close addresses.

    A Transaction-Time-Only close's gate binds the observed ``in_z``, which the
    closing step's own ① row never carries — that row carries the NEW value. It
    comes from the milestone the case's own history left current: an earlier
    writeSequence step that opened or chained one for the same key, or, when the
    case loads its model's fixtures, the single fixture row of that key still
    open on Transaction Time.
    """
    tx_axis = next(
        axis for axis in temporal_axes(entity.runtime_facts) if axis.dimension == "transaction-time"
    )
    key_member = next(
        attribute["name"] for attribute in entity.attributes if attribute.get("primaryKey")
    )
    current: Any = None
    if case.load_fixtures:
        # Fixture rows are keyed by MEMBER name, so the axis's declared
        # attributes name them; the open upper bound is the `infinity` literal.
        open_rows = [
            row
            for row in entity.rows
            if _write_value_equal(row.get(key_member), pk)
            and _write_value_equal(row.get(tx_axis.end.name), "infinity")
        ]
        if len(open_rows) == 1:
            current = open_rows[0].get(tx_axis.start.name)
    for prior in _prior_steps_for_key(case, entity, step, pk):
        # An `insert` opens a milestone and an `update` chains a successor; both
        # leave one current at the step's own instant, and a `terminate` leaves
        # none for a later close to address.
        current = None if prior["mutation"] in _TERMINATE_MUTATIONS else prior.get("at")
    if current is None:
        raise CaseFailure(
            f"{case.path.name}: a gated close of {entity.name} pk {pk!r} binds the observed "
            f"{tx_axis.start.name}, but neither the case's own earlier steps nor its fixtures "
            f"leave exactly one milestone of that key current on Transaction Time."
        )
    return current


def _observed_rectangle(case: Case, entity: Entity, step: dict[str, Any], pk: Any) -> _Rectangle:
    """The one current rectangle *step*'s close addresses, reconstructed from ①.

    Neither the address's Valid-Time end nor the optimistic gate's ``in_z`` appears in
    the closing step's own ① row — that row carries the NEW value and the window start
    — so both come from the rectangle the case's earlier steps left current.
    """
    rectangles = _current_rectangles(case, entity, step, pk)
    if len(rectangles) != 1:
        raise CaseFailure(
            f"{case.path.name}: a bitemporal close of pk {pk!r} inactivates the ONE "
            f"rectangle current on Transaction Time, but replaying the earlier "
            f"writeSequence steps leaves {len(rectangles)} — neither its address (the "
            f"observed Valid-Time end) nor its optimistic gate (the observed in_z) can "
            f"be derived from the case's own history."
        )
    return rectangles[0]


def _current_rectangles(
    case: Case, entity: Entity, current_step: dict[str, Any], pk: Any
) -> tuple[_Rectangle, ...]:
    """The rectangles *pk* has current on Transaction Time when *current_step* runs.

    A bitemporal write-sequence case builds its whole history from its own ordered DML
    — the model's fixture rows belong to the as-of READ cases and are not loaded — so
    the state a close addresses is REPLAYED from the earlier steps for the same key: an
    ``insert`` / ``insertUntil`` opens one rectangle over ``[validFrom, until)`` (an
    absent ``until`` meaning the open Valid-Time bound), and a split closes the current
    rectangle and re-opens its surviving slices at the step's own instant.

    Replaying a split needs the single rectangle it closed, so the replay yields nothing
    once a key holds several — the same refusal a step-shaped input forces on any
    tracker, because such a step names no rectangle of its own.
    """
    valid_time = next(a for a in entity.temporal_runtime_axes if a["dimension"] == "valid-time")
    infinity = valid_time.get("infinity", "infinity")
    rectangles: tuple[_Rectangle, ...] = ()
    for prior in _prior_steps_for_key(case, entity, current_step, pk):
        valid_from, until, at = prior.get("validFrom"), prior.get("until"), prior.get("at")
        if prior["mutation"] in _OPENING_MUTATIONS:
            opened = _Rectangle(valid_from, infinity if until is None else until, at)
            rectangles = (*rectangles, opened)
            continue
        if len(rectangles) != 1:
            return ()
        rectangles = _split_successors(prior["mutation"], rectangles[0], valid_from, until, at)
    return rectangles


def _has_temporal_gate(statement: str, in_z: str, dialect: str) -> bool:
    """True when a milestone close's SQL carries the OPTIMISTIC gate predicate.

    Address and gate are separate facts (`m-bitemp-write` "Address and gate are
    separate"): every close renders the same address in either mode, and an optimistic
    one APPENDS the observed Transaction-Time start (``and <in_z> = ?``) last. The gate
    signature is therefore that predicate as the predicate's LAST conjunct, so the
    address's own ``<out_z> = ?`` is never mistaken for it and a close that weaves the
    observed start into the address instead of appending it is reported UNGATED and
    fails on arity rather than passing as a well-formed gated close. A close is then
    never mis-read as gated on the strength of a longer bind row alone, nor on a gate
    predicate that binds anywhere but last.

    The temporal peer of :func:`_has_version_gate`, and projected out of the same
    parsed statement (:func:`_existing_row_write`) for the same reasons: a reserved
    physical interval column is rendered QUOTED in the executing dialect's own quote
    character (`m-dialect`), and a nested ``SELECT``'s trailing predicate is a conjunct
    of that query rather than of this one.
    """
    write = _existing_row_write(statement, dialect)
    return write is not None and _gates_on(write.conjuncts[-1], in_z)


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
    """The Transaction-Time TEMPORAL entity a conflict-close case targets, or None.

    A temporal / bitemporal conflict close (``m-temporal-read-009`` through
    ``m-temporal-read-012`` / ``m-bitemp-write-004`` / ``m-bitemp-write-005``) carries no
    version column; it locks via the observed Transaction-Time start (``in_z``),
    so the target is the first CONCRETE (row-owning) entity with a Transaction-Time
    as-of axis. An inheritance family's abstract root (m-inheritance) resolves
    the SAME family-wide axis (`resolve_effective_definition` flattens it onto
    every descendant), but is tableless and rowless — a conflict case's golden
    UPDATE always targets the concrete subtype that owns the row
    (``m-inheritance-105``, the composed temporal x inheritance x optimistic
    conflict witness), so an abstract node is skipped even when it is the
    first entity in the descriptor to carry the axis.
    """
    for entity in case.model.entities:
        if entity.is_abstract:
            continue
        if any(a["dimension"] == "transaction-time" for a in entity.temporal_runtime_axes):
            return entity
    return None


def _sole_conflict_write(
    case: Case, attempt: dict[str, Any], pointer: str
) -> dict[str, Any] | None:
    """The ONE ① row a versioned or temporal conflict's cross-check derives from.

    Both derivations read a single row's key, set columns, and observation
    against ONE golden statement. The multi-key ``write`` array is neither: a
    versioned or temporal target materializes per-row writes rather than
    collapsing, so a multi-key array authored against one is refused rather than
    cross-checked against a golden that cannot describe it.
    """
    rows = conflict_write_rows(attempt)
    if len(rows) > 1:
        raise CaseFailure(
            f"{case.path.name}: a versioned or temporal conflict ({pointer}) authors "
            f"{len(rows)} write rows — the multi-key `write` array is keyed and "
            f"non-temporal, since a versioned or temporal target materializes per-row "
            f"writes rather than collapsing into one statement."
        )
    return rows[0] if rows else None


def _assert_conflict_input(case: Case, dialect: str) -> None:
    """Cross-check a conflict case's neutral input (① ``write``) against its golden.

    A VERSIONED keyed conflict — an ``update`` or a ``delete``, named by
    ``when.mutation`` — is cross-checked by
    :func:`_assert_versioned_conflict_input`. The single form reads a root
    ``write``; the retry form reads a ``write`` per attempt. A temporal-close
    conflict (no version column) carries a close-shaped ① instead, cross-checked by
    :func:`_assert_temporal_conflict_input`. An UNVERSIONED, non-temporal
    conflict has neither derivation to make — its golden carries no gate and no
    version advance — so it is left to the execution assertion alone. Comparing
    against the golden is legitimate — two AUTHORED representations, never
    grading generated output.

    Whether the case may name an observed milestone at all is decided earlier and
    unconditionally, in :func:`_assert_schema`
    (:func:`_assert_observed_edge_entitlement`): a versioned target reaches
    neither derivation below, and this function itself is not on every run's path.
    """
    entity = _conflict_versioned_entity(case)
    if entity is None:
        _assert_temporal_conflict_input(case, dialect)
        return
    version_col = _version_column(entity)
    mutation = case.conflict_mutation
    if case.attempts:
        for index, attempt in enumerate(case.attempts):
            pointer = f"attempts[{index}].write"
            _assert_versioned_conflict_input(
                case,
                entity,
                version_col,
                mutation,
                _sole_conflict_write(case, attempt, pointer),
                _attempt_statements(attempt, dialect),
                _entry_binds(attempt.get("statements"), 0, dialect),
                pointer,
                dialect,
            )
        return
    _assert_versioned_conflict_input(
        case,
        entity,
        version_col,
        mutation,
        _sole_conflict_write(case, case.when, "write"),
        case.golden_statements(dialect),
        case.statement_binds(0),
        "write",
        dialect,
    )


def _assert_versioned_conflict_input(
    case: Case,
    entity: Entity,
    version_col: str | None,
    mutation: str,
    write: dict[str, Any] | None,
    statements: list[str],
    binds: list[Any],
    pointer: str,
    dialect: str,
) -> None:
    """Cross-check one versioned keyed conflict attempt's ① against its golden.

    One derivation serves both keyed verbs, because they differ only in what the
    golden's SET clause contributes (:func:`_conflict_set_binds`). Everything after
    that is shared: ① MUST carry ``observedVersion`` — a keyed write against a
    versioned row requires a prior observation in EITHER mode — and the CONCURRENCY
    MODE ALONE decides whether the golden appends the ``and <version> = ?`` gate and
    the trailing observed bind behind it (`m-opt-lock`: the gate is uniform across
    the update, the delete, and the close, and the verb decides nothing). The derived
    binds are therefore ``[…set values…, pk]``, extended by ``observedVersion``
    when gated.
    """
    if write is None:
        raise CaseFailure(
            f"{case.path.name}: a versioned conflict ({pointer}) carries no neutral write "
            f"input (① `write`) — required on every conflict sub-form."
        )
    if len(statements) != 1:
        raise CaseFailure(
            f"{case.path.name}: a versioned conflict ({pointer}) has exactly one golden "
            f"statement, but {len(statements)} were listed."
        )
    statement = statements[0]
    _, pk, set_cols, observed = _classify_write_row(
        case, entity, write, mutation=mutation, opening=False
    )
    if observed is None:
        raise CaseFailure(
            f"{case.path.name}: a versioned conflict's neutral write input ({pointer}) MUST "
            f"carry observedVersion — a keyed {mutation.upper()} of a versioned row requires "
            f"a prior observation in either mode, and the advance and gate derive from it."
        )
    expected = [
        *_conflict_set_binds(
            case, entity, version_col, mutation, statement, set_cols, observed, pointer
        ),
        pk,
    ]
    gated = case.concurrency_mode == "optimistic"
    gate_rendered = version_col is not None and _has_version_gate(statement, version_col, dialect)
    if gate_rendered != gated:
        raise CaseFailure(
            f"{case.path.name}: the golden {mutation.upper()} ({pointer}) "
            f"{'renders' if gate_rendered else 'omits'} the version gate under "
            f"{case.concurrency_mode!r} mode — optimistic mode gates, locking mode does not."
        )
    if gated:
        expected.append(observed)
    _assert_write_values(case, expected, binds, statement)


def _conflict_set_binds(
    case: Case,
    entity: Entity,
    version_col: str | None,
    mutation: str,
    statement: str,
    set_cols: dict[str, Any],
    observed: Any,
    pointer: str,
) -> list[Any]:
    """The binds a versioned keyed conflict's SET clause contributes, in golden order.

    A DELETE writes no column at all, so ① carries only the pk and the reserved
    ``observedVersion`` and the cross-check downstream is binds-only. An UPDATE
    writes the domain set columns ① resolves to — in Table Layout order, filtered to
    the present attributes — followed by the FRAMEWORK-DERIVED version advance
    (``observedVersion + 1``), which advances in BOTH concurrency modes and so is
    never conditional on the gate.
    """
    if mutation == "delete":
        if set_cols:
            raise CaseFailure(
                f"{case.path.name}: a versioned DELETE conflict's neutral write input "
                f"({pointer}) assigns {sorted(set_cols)} — a DELETE writes no columns, so ① "
                f"carries only the pk and observedVersion."
            )
        return []
    golden_set = _parse_set_columns(case, statement)
    set_present = [c for c in _write_column_order(case, entity) if c in set_cols]
    expected_cols = [*set_present, version_col]
    if golden_set != expected_cols:
        raise CaseFailure(
            f"{case.path.name}: the golden conflict SET column list {golden_set} != the "
            f"domain set columns + version {expected_cols} the neutral write input "
            f"({pointer}) resolves to."
        )
    return [*(set_cols[column] for column in set_present), observed + 1]


def _assert_observed_edge_entitlement(case: Case, entity: Entity | None) -> None:
    """Refuse an observation coordinate the conflict target, mode, or attempt form
    cannot consume.

    Five entitlements, all properties of the CASE rather than of any attempt's
    arithmetic (`m-case-format`, *Naming the observed milestone*): a NON-temporal
    target has no milestone at all, so it may author NEITHER coordinate, wherever
    it is spelled; a target declaring no Valid-Time axis has no
    ``observedValidStart`` to supply, so the edge form is Bitemporal-only; a
    RETRY attempt re-reads what the concurrent writer left behind, while an edge
    selects among the milestones the case's own fixtures hold, so the observation
    form is single-attempt only; a retry sequence reads each attempt's own
    coordinates and never the root ``when``'s, so a root coordinate beside
    ``attempts`` is consumed by nothing; and ``observedTxStart`` standing ALONE is
    the address form's gate candidate, which a ``locking`` close never renders, so
    it needs an explicit ``optimistic`` mode — beside ``observedValidStart`` it is
    the edge's Transaction-Time half instead and selects the milestone in either
    mode.

    Refusing here rather than at the point of use is what turns each into a named
    authoring diagnosis: the edge-named rectangle scan would otherwise look up an
    axis a Transaction-Time-Only target never declares, and a non-temporal
    conflict's own execution path reads neither coordinate at all, so an
    unentitled one would sit in the document grading nothing.
    """
    attempts = case.attempts
    sources = [
        ("write", case.when),
        *((f"attempts[{i}]", a) for i, a in enumerate(attempts)),
    ]
    observing = [
        pointer
        for pointer, source in sources
        if any(key in source for key in _MILESTONE_COORDINATE_KEYS)
    ]
    if not observing:
        return
    if entity is None:
        raise CaseFailure(
            f"{case.path.name}: a NON-temporal conflict target has no milestone to observe, "
            f"so it may author neither of {sorted(_MILESTONE_COORDINATE_KEYS)} "
            f"({', '.join(observing)})."
        )
    if attempts:
        stranded = sorted(key for key in _MILESTONE_COORDINATE_KEYS if key in case.when)
        if stranded:
            raise CaseFailure(
                f"{case.path.name}: the root `when` authors {stranded} beside `attempts` — a "
                f"retry sequence reads each attempt's own coordinates, so a root one is "
                f"consumed by no attempt."
            )
    if case.concurrency_mode != "optimistic":
        ungated = [
            pointer
            for pointer, source in sources
            if "observedTxStart" in source and "observedValidStart" not in source
        ]
        if ungated:
            raise CaseFailure(
                f"{case.path.name}: `locking` mode renders no gate, so a lone "
                f"`observedTxStart` is consumed by nothing ({', '.join(ungated)}) — it is "
                f"entitled under `optimistic`, or beside `observedValidStart` as the observed "
                f"milestone's edge."
            )
    named = [pointer for pointer, source in sources if "observedValidStart" in source]
    if not named:
        return
    if not any(a["dimension"] == "valid-time" for a in entity.temporal_runtime_axes):
        raise CaseFailure(
            f"{case.path.name}: {entity.name} declares no Valid-Time axis, so its milestones "
            f"have no Valid-Time start for `observedValidStart` to name ({', '.join(named)}) "
            f"— the observed-milestone edge form is Bitemporal-only."
        )
    retries = [pointer for pointer in named if pointer != "write"]
    if retries:
        raise CaseFailure(
            f"{case.path.name}: {', '.join(retries)} names its observed milestone's edge, "
            f"which selects among the case's own fixtures — a retry re-reads what the "
            f"concurrent writer left, so a retry attempt names its address (`validEnd`) "
            f"directly."
        )


def _assert_temporal_conflict_input(case: Case, dialect: str) -> None:
    """Cross-check a TEMPORAL / bitemporal conflict CLOSE's ① against its golden (②).

    A Transaction-Time temporal entity carries no version column, so the close gates
    on the observed Transaction-Time start (``in_z``) — the version analogue (DQ-C). The
    close is Family B: it always writes the single metamodel-fixed SET column
    (``out_z``), so the cross-check is BINDS-only (OQ3 → Option A). ① carries the
    milestone pk (→ the address's key), the close instant ``at`` (→ the new
    ``out_z``), and — in optimistic mode — ``observedTxStart`` (the ``and in_z = ?``
    gate); a BITEMPORAL close additionally NAMES the rectangle it addresses through the
    Valid-Time end attribute (``validEnd`` → the ``thru_z = ?`` bound whose VALUE the
    metamodel cannot know), which a conflict case authors explicitly rather than
    reconstructing from a history it does not have. The single form reads root
    ``write`` / ``at`` / ``observedTxStart``; the retry form reads them per attempt.

    A Bitemporal close may name the observed MILESTONE instead of the address:
    ``observedValidStart`` with ``observedTxStart`` is that milestone's own edge,
    and both the address's Valid-Time end and the gate are then derived from the
    one fixture milestone the edge selects (:func:`_edge_named_rectangle`).
    """
    entity = _conflict_temporal_entity(case)
    if entity is None:
        return
    gated = case.concurrency_mode == "optimistic"
    if case.attempts:
        for index, attempt in enumerate(case.attempts):
            pointer = f"attempts[{index}]"
            _assert_temporal_conflict_close(
                case,
                entity,
                _sole_conflict_write(case, attempt, pointer),
                attempt.get("at"),
                attempt.get("observedTxStart"),
                # The edge form is single-attempt only, so a retry attempt names
                # its address directly and observes no milestone here.
                None,
                gated,
                _attempt_statements(attempt, dialect),
                _entry_binds(attempt.get("statements"), 0, dialect),
                pointer,
                dialect,
            )
        return
    _assert_temporal_conflict_close(
        case,
        entity,
        _sole_conflict_write(case, case.when, "write"),
        case.at,
        case.observed_tx_start,
        case.observed_valid_start,
        gated,
        case.golden_statements(dialect),
        case.statement_binds(0),
        "write",
        dialect,
    )


def _assert_temporal_conflict_close(
    case: Case,
    entity: Entity,
    write: dict[str, Any] | None,
    at: Any,
    observed_tx_start: Any,
    observed_valid_start: Any,
    gated: bool,
    statements: list[str],
    binds: list[Any],
    pointer: str,
    dialect: str,
) -> None:
    """Cross-check one temporal-close attempt's ① binds against its golden close.

    A close sets ``out_z = at`` on the milestone its ADDRESS selects
    (:func:`_close_address_binds`); an optimistic close appends the ``and in_z = ?``
    gate bound to ``observedTxStart``, so the derived binds are ``[at, …address…,
    (observedTxStart if gated)]``. A TABLE-PER-HIERARCHY concrete subtype's close ALSO
    carries the tag GUARD among the identity predicates, immediately after the primary
    key — the SAME composition a keyed update follows (m-inheritance x m-opt-lock
    "Optimistic locking composes with inheritance", resolved Q9), extended to a
    temporal close (``m-inheritance-105``).

    Because address and gate are separate, ① names EXACTLY the address's per-axis
    upper bounds it can supply: nothing for a Transaction-Time-Only target, whose only
    bound is the invariant infinity, and the Valid-Time end alone for a Bitemporal one.
    A close writes no domain value, so any other ① coordinate is a defect.

    An EDGE-NAMED close (``observedValidStart``) supplies neither: it names the
    milestone it observed, and both the Valid-Time end and the gate are derived
    from that milestone's own fixture row. ① then carries the pk alone, and an
    authored ``validEnd`` beside the edge is refused rather than cross-checked —
    the two spell the same fact, so a case that agrees with itself proves nothing
    the derivation does not, and one that disagrees would have to pick a winner.
    """
    if write is None:
        raise CaseFailure(
            f"{case.path.name}: a temporal conflict close ({pointer}) carries no neutral "
            f"write input (① `write`) — required on every conflict sub-form."
        )
    if len(statements) != 1:
        raise CaseFailure(
            f"{case.path.name}: a temporal conflict close ({pointer}) has exactly one "
            f"golden statement, but {len(statements)} were listed."
        )
    if at is None:
        raise CaseFailure(
            f"{case.path.name}: a temporal conflict close's neutral write input "
            f"({pointer}) MUST carry `at` (the close instant → out_z), which is DERIVED "
            f"into the close binds, never read from the golden."
        )
    valid_time = next(
        (a for a in entity.temporal_runtime_axes if a["dimension"] == "valid-time"), None
    )
    _, pk, set_cols, _ = _classify_write_row(
        case, entity, write, mutation=_CLOSE_MUTATION, opening=False
    )
    edge_named = observed_valid_start is not None
    addressed: set[str] = set() if valid_time is None or edge_named else {valid_time["end_column"]}
    if set(set_cols) != addressed:
        raise CaseFailure(
            f"{case.path.name}: a temporal conflict close's neutral write input "
            f"({pointer}) resolves to the coordinate(s) {sorted(set_cols)}, but a close "
            f"writes no domain value and names exactly the address bound(s) it can "
            f"supply: {sorted(addressed)}."
        )
    if edge_named:
        observed = _edge_named_rectangle(
            case, entity, pk, observed_valid_start, observed_tx_start, pointer
        )
        valid_end, observed_tx_start = observed.valid_end, observed.tx_start
    elif valid_time is None:
        valid_end = None
    else:
        valid_end = set_cols[valid_time["end_column"]]
    expected = [at, *_close_address_binds(case, entity, pk, valid_end)]
    gate_rendered = _has_temporal_gate(
        statements[0],
        next(a for a in entity.temporal_runtime_axes if a["dimension"] == "transaction-time")[
            "start_column"
        ],
        dialect,
    )
    if gate_rendered != gated:
        raise CaseFailure(
            f"{case.path.name}: the golden temporal close ({pointer}) "
            f"{'renders' if gate_rendered else 'omits'} the observed-in_z gate under "
            f"{case.concurrency_mode!r} mode — optimistic mode gates, locking mode does "
            f"not, and the address is the same either way."
        )
    if gated:
        if observed_tx_start is None:
            raise CaseFailure(
                f"{case.path.name}: an optimistic temporal conflict close's neutral write "
                f"input ({pointer}) MUST carry observedTxStart — the `and in_z = ?` gate is "
                f"derived from it."
            )
        expected.append(observed_tx_start)  # the optimistic in_z gate bind
    _assert_write_values(case, expected, binds, statements[0])
    _assert_inheritance_write_routing(case, entity, statements, [binds], dialect)


def _table_layout(case: Case, table: str) -> TableLayout:
    """The compiled layout of one physical *table* an observation reads back."""
    layout = case.model.storage_layout.table(table)
    if layout is None:
        raise CaseFailure(
            f"{case.path.name}: an observation names table {table!r} "
            f"which the model does not declare."
        )
    return layout


def _read_table(
    db: DatabaseProvider,
    layout: TableLayout,
    types: Mapping[ColumnContributor, tuple[str, int | None]],
) -> list[dict[str, Any]]:
    """Read the full state of *layout*'s table, projecting every slot in order.

    The layout is the whole physical row, so a table-per-hierarchy shared table
    reports a sibling-only column as ``null`` rather than omitting it. Each
    slot's own provenance decides its normalization: a document slot is decoded
    to a Python structure (m-value-object), because Postgres returns its
    ``jsonb`` already parsed while MariaDB returns raw JSON text, and both
    dialects must collapse to the same ``dict`` / ``list`` / ``None`` a
    ``then.tableState`` document row is authored as. A ``bytes`` contributor
    reads back as raw driver bytes (Postgres ``memoryview`` / MariaDB
    ``bytes``); it renders to lowercase hex text so a write round-trip compares
    dialect-agnostically to the authored hex string.
    """
    projection = ", ".join(
        f"t0.{quote_identifier(slot.column, db.dialect)}" for slot in layout.columns
    )
    rows = db.query(f"select {projection} from {quote_identifier(layout.table, db.dialect)} t0")
    document_columns = {slot.column for slot in layout.columns if slot.tier is ColumnTier.DOCUMENT}
    bytes_columns = {
        slot.column
        for slot in layout.columns
        if types.get(slot.contributor, ("", None))[0] == "bytes"
    }
    for row in rows:
        for column in document_columns:
            if column in row:
                row[column] = decode_stored(row[column])
        for column in bytes_columns:
            if isinstance(row.get(column), (bytes, bytearray, memoryview)):
                row[column] = bytes(row[column]).hex()
    return rows


def _assert_write_sequence(case: Case, db: DatabaseProvider) -> None:
    """Apply the ordered DML golden SQL, then assert the resulting table state.

    This is the observable form of the milestone-chaining write contract (m-txtime-write):
    rather than introspecting the implementation, we APPLY the documented golden
    DML in order and assert the rows it leaves behind — including the current-row
    state where the open bound ``to`` equals native ``infinity``.
    """
    dialect = db.dialect
    statements = case.golden_statements(dialect)

    for index, statement in enumerate(statements):
        binds = case.statement_binds(index, dialect)
        db.execute(statement, binds)

    expected = case.expected_table_state
    types = contributor_types(case.model)
    for table, expected_rows in expected.items():
        actual = _read_table(db, _table_layout(case, table), types)
        if not _rows_equal(actual, expected_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: table {table!r} state after the write "
                f"sequence != then.tableState.\n"
                f"  actual:   {actual!r}\n"
                f"  expected: {expected_rows!r}"
            )


# --- scenarios (m-unit-work) ----------------------------------------------------------


def _step_statements(step: dict[str, Any], dialect: str) -> list[str]:
    """The ordered golden SQL statements a scenario step lists for *dialect*."""
    return _entry_statements(step.get("statements"), dialect)


def _scenario_has_golden(case: Case, dialect: str) -> bool:
    """True if any scenario step lists golden SQL for *dialect*."""
    return any(_step_statements(step, dialect) for step in case.scenario)


def _scenario_reference_sql_for(step: dict[str, Any], dialect: str) -> str | None:
    """Resolve one scenario read's naive SQL oracle for *dialect*."""
    raw = step.get("referenceSql")
    if raw is None:
        return None
    if isinstance(raw, dict):
        if dialect not in raw:
            raise KeyError(
                f"scenario referenceSql map has no key {dialect!r} (keys: {sorted(raw)})"
            )
        return raw[dialect]
    return raw


def _assert_scenario_reference_sql(
    case: Case,
    reader: DatabaseProvider,
    index: int,
    step: dict[str, Any],
    golden_rows: list[dict[str, Any]],
) -> None:
    """Run a scenario find's independent, bind-free naive SQL oracle.

    *reader* MUST be the SAME connection the golden read used — the provider's
    autocommit connection for an ungrouped find, or the `uow` group's own held
    session for a grouped one — so a grouped find's mid-transaction (possibly
    uncommitted) state is what the oracle observes too, never a different
    connection's committed-only view.
    """
    reference_sql = _scenario_reference_sql_for(step, reader.dialect)
    if reference_sql is None:
        return
    reference_rows = _query_rows(case, reader, reference_sql, [])
    if not _rows_equal(reference_rows, golden_rows, case.tolerance):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] referenceSql rows != golden rows.\n"
            f"  reference: {reference_rows!r}\n"
            f"  golden:    {golden_rows!r}"
        )


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


def _scenario_step_resolving_reads(case: Case, step: dict[str, Any]) -> int:
    """The resolving reads ONE scenario step owes beside the SQL it lists.

    An UNGROUPED write step is its own choreography unit, so it owes what any
    unit owes (:func:`_unit_resolving_reads`). A GROUPED one owes none of its
    own: its group's find steps are what publish the values it settles against,
    and those finds already declare their own round trips (`m-case-format`
    *Resolving reads a write owes*). A find step owes none either — a read IS
    the SQL it lists.
    """
    if "write" not in step or isinstance(step.get("uow"), str):
        return 0
    return _unit_resolving_reads(case, _scenario_write_entries(step))


def _assert_scenario_count_consistency(case: Case, dialect: str) -> None:
    """Each step's declared roundTrips MUST equal its golden SQL statement count
    plus the resolving reads it owes.

    A cache HIT lists no golden SQL and declares ``roundTrips: 0``; a cache MISS
    that executes one statement declares ``roundTrips: 1``. An ungrouped write
    step declares its DML beside the read its keyed verbs' sources require, which
    it lists no SQL for — the framework composes that read from the model rather
    than from the case. The steps' total MUST equal the case-level
    ``roundTrips``. This is the round-trip contract proven from the fixture's own
    declared counts — the harness never compiles a query to SQL.
    """
    total = 0
    for index, step in enumerate(case.scenario):
        declared = step["roundTrips"]
        statements = _step_statements(step, dialect)
        reads = _scenario_step_resolving_reads(case, step)
        if len(statements) + reads != declared:
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] declares roundTrips "
                f"{declared} but lists {len(statements)} golden SQL statement(s) "
                f"for {dialect} and owes {reads} resolving read(s). A step's declared "
                f"round trips MUST equal the number of calls it makes (a cache hit = 0)."
            )
        total += declared
    if total != case.round_trips:
        raise CaseFailure(
            f"{case.path.name}: scenario steps total {total} round trip(s) but "
            f"roundTrips is {case.round_trips}. The case-level roundTrips MUST "
            f"equal the sum of the per-step round trips."
        )


def _scenario_write_entries(step: dict[str, Any]) -> list[dict[str, Any]]:
    """One scenario write step's own buffered KEYED entries, or none.

    A write step's ``write`` is a legacy string label, a single predicate-selected
    instruction (a mapping), or the buffered keyed sequence (a list) — only the
    last is a list of ``{mutation, entity, rows}`` entries.
    """
    write = step.get("write")
    if not isinstance(write, list):
        return []
    return [entry for entry in write if isinstance(entry, dict)]


def _assert_scenario_source_finds(case: Case) -> None:
    """Validate every write step's ``on`` — the find it settles against
    (`m-case-format` *Settling against a grouped find*).

    The reference is legal only where every part of it is meaningful: on a `uow`-
    grouped step whose ``write`` is the BUFFERED KEYED form, naming ONE earlier
    step of the SAME group that is a find. Every target profile is nameable,
    because on every one of them a unit of work may hold more than one piece of
    evidence about a key: a milestone chain holds several rows per key, and a
    versioned Non-Temporal key holds one observed generation per read of it.

    Structural and dialect-free, so it holds on every run rather than only where
    the case carries a golden for the dialect under test — the same reason the
    conflict lane decides observed-edge entitlement in :func:`_assert_schema`.
    """
    for index, step in enumerate(case.scenario):
        if "write" not in step or "on" not in step:
            continue
        source, label = step["on"], step.get("uow")
        if not isinstance(label, str):
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] settles against a find but declares no "
                f"`uow` group — the evidence a write consumes is transaction-scoped, and an "
                f"ungrouped write shares a unit of work with no find."
            )
        if not isinstance(source, int) or isinstance(source, bool):
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}].on is {source!r}; a write step settles "
                f"against exactly ONE find, named by its index — a keyed write settles "
                f"against the one observed state the value it was handed came from."
            )
        if not 0 <= source < index:
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}].on references step {source!r}, which is "
                f"not a real EARLIER step (0 <= source < {index})."
            )
        origin = case.scenario[source]
        if "objectQuery" not in origin or origin.get("uow") != label:
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] settles against step {source}, which is "
                f"not a find step of its own `uow` group {label!r}."
            )
        if not isinstance(step.get("write"), list):
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] settles against a find but its `write` is "
                f"not the buffered keyed form — a legacy string label carries no instruction and "
                f"a predicate-selected write consumes no single observation, so neither has "
                f"anything the named observation could reach."
            )


def _assert_scenario_settled_write(case: Case, dialect: str) -> None:
    """Cross-check each settled write step's golden against the observed state the
    find it names recorded (`m-case-format` *Settling against a grouped find*).

    The observed state is resolved INDEPENDENTLY of the golden, from the named
    find step's own ``expectRows`` — the rows that read returned, which is exactly
    the evidence the store it filled holds — and by each entry's OWN object
    (:func:`_settled_observed_row`), so a find that observed no row of that object
    names evidence that does not exist.
    What the resolution then reaches is the target's PROFILE's answer: a temporal
    write's close address (on a Bitemporal target, its Valid-Time exclusive upper
    bound) and its optimistic gate, and a versioned Non-Temporal write's own gate
    and framework-computed version advance. Either way the corpus states which
    state the write settled against in two independent places — here and in
    execution.

    Which bind a misresolution moves differs the same way: a Bitemporal key's
    current rectangles are disjoint on Valid Time, so a close binding the OTHER
    current rectangle fails on the address, while a Transaction-Time-Only close
    addresses the key plus the invariant open bound and a versioned write its key
    alone, so on both of those the whole difference lands on what the observation
    derives.

    An entry is aligned with its golden by the OBJECT each statement itself
    addresses (:func:`_statement_object`), never by the order the buffer names
    objects in: a flush dependency-orders its surviving writes so a parent is
    inserted before and deleted after the children referencing it (`m-unit-work`
    *the planning pipeline*, `m-case-format` *foreign-key-ordered at flush*), so
    the statement order a legal buffer produces is the graph's, not the author's.
    Entries settling against one state of one object coalesce into ONE statement
    (`m-unit-work` *Observed-State Coalescing*) — what distinguishes them is the
    assignments they contribute to it, while what this cross-check reads, the
    state they settled against, is the one thing they share — and the same buffer
    equally expresses a mixed multi-object flush, whose objects emit one statement
    each. The settling statement is the EXISTING-ROW one; a temporal successor's
    chained INSERT settles nothing and is passed over.

    An address names the object but not which concrete subtype of it a golden
    claims, because a table-per-hierarchy family shares one table, so the aligned
    statement is also required to ROUTE to the entry's own subtype — the tag guard
    binding that subtype's ``tagValue``, or, under table-per-concrete-subtype, its
    own table (`m-inheritance`). The writeSequence lane asks the same of its
    goldens; a scenario write carries no writeSequence, so this is where a settled
    one is asked.
    """
    for index, step in enumerate(case.scenario):
        if "write" not in step or "on" not in step:
            continue
        settling = [
            (_statement_object(case, index, statement, binds, dialect), statement, binds)
            for statement, binds in _entry_pairs(step.get("statements"), dialect)
            if _is_existing_row_statement(statement)
        ]
        origin = case.scenario[step["on"]]
        aligned: set[int] = set()
        for entry in _scenario_write_entries(step):
            entity = case.model.entity(entry["entity"])
            row = _sole_settled_row(case, index, entity, entry)
            temporal = bool(temporal_axes(entity.runtime_facts))
            _, pk, _set_cols, _observed = _classify_write_row(
                case, entity, row, mutation=entry["mutation"], opening=temporal
            )
            statement, binds = _settled_statement(case, index, entity, pk, settling, aligned)
            _assert_inheritance_write_routing(case, entity, [statement], [binds], dialect)
            if not temporal:
                _assert_settled_version_binds(
                    case, entity, index, origin, pk, binds, statement, dialect
                )
                continue
            observed = _settled_milestone(case, entity, index, origin, pk)
            expected = [
                entry.get("at"),
                *_close_address_binds(case, entity, pk, observed.valid_end),
            ]
            if case.concurrency_mode == "optimistic":
                expected.append(observed.tx_start)
            _assert_write_values(case, expected, binds, statement)
        if len(aligned) != len(settling):
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] carries {len(settling) - len(aligned)} "
                f"existing-row statement(s) for {dialect} addressing an object no entry of its "
                f"buffer writes — every statement a settled flush emits belongs to one of the "
                f"objects written, and entries settling against one state coalesce into one."
            )


def _settled_statement(
    case: Case,
    index: int,
    entity: Entity,
    pk: Any,
    settling: Sequence[tuple[_ObjectAddress, str, list[Any]]],
    aligned: set[int],
) -> tuple[str, list[Any]]:
    """The golden statement one settled entry's OBJECT survives as, with the binds
    authored on it.

    Alignment is by OBJECT IDENTITY — the entry's own table and Object Key against
    the ones each statement addresses — so it holds however the flush ordered
    those statements, and every entry of one object reaches the one statement they
    coalesce into. Two statements addressing one object are refused as firmly as
    none: coalescing leaves an object at most one surviving existing-row write per
    observed state, and the second would be graded against evidence the first
    already consumed.

    ``aligned`` collects the statements entries reached, which is what lets the
    caller name a golden addressing an object the buffer never writes.
    """
    matches = [
        position
        for position, (address, _statement, _binds) in enumerate(settling)
        if _names(address.table, entity.table)
        and _names(address.key_column, _pk_column(entity))
        and _write_value_equal(address.key, pk)
    ]
    if not matches:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles a write of {entity.name} pk {pk!r} "
            f"against a find but its golden carries no existing-row statement addressing that "
            f"object — a settled write emits one."
        )
    if len(matches) > 1:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] carries {len(matches)} existing-row "
            f"statements addressing {entity.name} pk {pk!r} — writes settling against one "
            f"observed state of one object coalesce into ONE statement."
        )
    (position,) = matches
    aligned.add(position)
    _address, statement, binds = settling[position]
    return statement, binds


class _ObjectAddress(NamedTuple):
    """Which object an existing-row statement writes: the identifiers its DML names
    the target table and the key column with, and the primary-key value its identity
    predicate binds.

    Table and key together ARE an Object Key — Entity Identity plus primary-key
    values (`m-unit-work`). Every structural Table has exactly one mapping owner
    (`m-storage-layout`) and object identity normalizes to the inheritance family
    (`m-identity-map`), so a table names ONE Entity Identity: a table-per-hierarchy
    family's shared table names that family, a table-per-concrete-subtype table its
    own subtype, and no two objects share a table and a primary key. Which concrete
    subtype of a shared table a golden claims is the one thing the address cannot
    say, so the settled lane grades it separately
    (:func:`_assert_inheritance_write_routing`).
    """

    table: exp.Identifier
    key_column: exp.Identifier
    key: Any


def _statement_object(
    case: Case, index: int, statement: str, binds: list[Any], dialect: str
) -> _ObjectAddress:
    """The object *statement* addresses, read off the statement's own address.

    Every existing-row write renders one address shape: the DML names the target
    table and the predicate LEADS with the primary-key equality, which the
    table-per-hierarchy tag guard, the temporal bounds, and the optimistic gate
    then follow in that order (`m-sql`, `m-inheritance`, `m-opt-lock`). The key's
    bind is therefore the predicate's first placeholder, and every placeholder
    before it belongs to the `set` clause.
    """
    write = _existing_row_write(statement, dialect)
    key_column = _bound_equality_identifier(write.conjuncts[0]) if write is not None else None
    offset = _predicate_bind_offset(statement)
    if write is None or key_column is None or offset is None or offset >= len(binds):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] carries an existing-row golden whose "
            f"predicate does not open with a bound key equality for {dialect}: "
            f"{statement!r} — a settled write addresses the ONE object it survives as, "
            f"and its key leads that address."
        )
    return _ObjectAddress(write.table, key_column, binds[offset])


def _predicate_bind_offset(statement: str) -> int | None:
    """How many binds precede the outer predicate's own first placeholder, or None
    when the statement carries no outer predicate.

    Scanned through :func:`_sql_scan` for the reason every reader that takes a
    golden apart by position is: a `?` inside a string literal binds nothing, and a
    `where` inside a quoted identifier or a subquery opens no predicate of this
    statement's own.
    """
    lowered = statement.lower()
    preceding = 0
    for position, char, depth in _sql_scan(statement):
        if depth == 0 and _keyword_at(lowered, position, "where"):
            return preceding
        if char == "?":
            preceding += 1
    return None


def _assert_settled_version_binds(
    case: Case,
    entity: Entity,
    index: int,
    origin: dict[str, Any],
    pk: Any,
    binds: list[Any],
    statement: str,
    dialect: str,
) -> None:
    """Cross-check a settled VERSIONED Non-Temporal write's golden against the
    generation the find it names observed OF ITS OWN KEY.

    A versioned write is addressed by its key alone, so the whole difference
    between one observed generation and another lands on what the observation
    derives, and both halves are graded: the optimistic gate, which is the
    golden's LAST bind and is the observed version itself, and the
    framework-computed advance, which is one more than it and is assigned in
    BOTH concurrency modes. A locking UPDATE therefore still states its observed
    generation; a DELETE assigns nothing, so a locking one states none and there
    is nothing here to cross-check.

    Which of the two the statement carries is read off the STATEMENT rather than
    off the entry's own verb, because coalescing decides what survives: a
    destructive intent supersedes the assignments buffered before it, so an
    entry spelling `update` may reach a golden DELETE that advances nothing.

    The generation is read off the named find step's own ``expectRows`` by the
    write's own key, exactly as the temporal arm reads its milestone
    (:func:`_settled_milestone`), so the corpus states which generation the write
    settled against in two independent places.

    The version column is located in the SET clause by the spelling the golden
    renders it with (:func:`quote_identifier`) rather than by its model name: a
    physical column may be reserved or otherwise non-simple, and the golden then
    quotes it exactly as the generated DML does (`m-dialect`).
    """
    version_column = _version_column(entity)
    if version_column is None:
        return
    observed = _settled_generation(case, entity, index, origin, pk, version_column)
    if case.concurrency_mode == "optimistic" and (
        not binds or not _write_value_equal(binds[-1], observed)
    ):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles {entity.name} against a find that "
            f"observed version {observed!r}, but its golden gate binds "
            f"{binds[-1] if binds else None!r}."
        )
    if _set_clause(statement) is None:
        return
    assigned = _parse_set_columns(case, statement)
    spelling = quote_identifier(version_column, dialect)
    if spelling not in assigned:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles a versioned {entity.name} update "
            f"whose golden SET clause {assigned} assigns no {spelling!r} — a versioned "
            f"update advances the framework-owned version under either concurrency strategy."
        )
    position = assigned.index(spelling)
    advanced = binds[position] if position < len(binds) else None
    if not _write_value_equal(advanced, observed + 1):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles {entity.name} against a find that "
            f"observed version {observed!r}, but its golden advances the version to "
            f"{advanced!r} rather than {observed + 1!r}."
        )


def _settled_observed_row(
    case: Case, entity: Entity, index: int, origin: dict[str, Any], pk: Any, state: str
) -> dict[str, Any]:
    """The ONE row of *pk* a settled write's named find declares it observed.

    Read off that find step's own ``expectRows`` — the rows the case declares that
    read returned, which is exactly the evidence the store it filled holds — so
    this derivation consults the case's READ result rather than the tracked
    current state every other write shape resolves from. That is the whole point
    of the reference: a unit of work may hold more than one piece of evidence
    about a key, so tracked state answers for at most one of them and only the
    read the write named says which it was handed.

    One resolver for both profiles, because the rule they share is the whole of
    it — the write's own object, exactly one match — and what differs is only the
    state each then projects out of the row (:func:`_settled_generation`,
    :func:`_settled_milestone`). *state* is that profile's own noun, so the
    refusal names what the write would have settled against.

    A POLYMORPHIC find needs the write's own concrete subtype beside the key
    (:func:`_row_is_variant_of`): a primary key names one object per TABLE, and only a
    table-per-hierarchy family shares one, so a discriminated-union read over
    table-per-concrete-subtype legitimately returns sibling rows of one key from
    different tables. Two rows the write's own subtype claims are two observed states,
    which is what the write would have to choose between. Which of a row's fields
    STATES a variant is the ORIGIN read's own question, so it is asked of that read
    once (:func:`_origin_variant_columns`) rather than guessed per row.
    """
    key_column = _pk_column(entity)
    observed_rows: list[dict[str, Any]] = origin.get("expectRows") or []
    variant_columns = _origin_variant_columns(case, origin)
    matched = [
        row
        for row in observed_rows
        if _write_value_equal(row.get(key_column), pk)
        and _row_is_variant_of(case, entity, row, variant_columns)
    ]
    if len(matched) != 1:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles against a find that observed "
            f"{len(matched)} row(s) of {entity.name} pk {pk!r} — a keyed write settles "
            f"against the ONE {state} the value it was handed came from."
        )
    return matched[0]


def _origin_variant_columns(case: Case, origin: dict[str, Any]) -> tuple[str, ...]:
    """The fields of *origin*'s observed rows that state a row's variant SPELLING, in
    precedence order — empty when that read states no variant at all.

    Only a read whose queried position is ABSTRACT is discriminated: it resolves over
    more than one concrete subtype, so `m-sql` gives its result a variant tag —
    materialized as ``familyVariant`` in the compatibility rows (`m-case-format`),
    and, under table-per-concrete-subtype before that materialization, carried by the
    projected per-branch ``family_variant`` literal. The materialized spelling leads,
    because a materialized row carries BOTH: alias remapping restores an authored
    physical column its own spelling, so `family_variant` beside `familyVariant` is
    the model's own column beside the read's answer.

    A **concrete-target** read carries no variant tag whatsoever (`m-sql`: the caller
    already queried a known variant), so neither spelling means anything there. Both
    are legal physical spellings a model may author — the compatibility corpus maps
    `catalog.Record.variantMarker` to the column ``family_variant`` and
    `compatibility.overlap.VariantRecord`'s value-object document to the column
    ``familyVariant`` — and reading one of those as a discriminator would refuse a
    settled write whose find observed exactly the row it names.

    Which position is abstract is asked of the same classifier materialization asks
    (:func:`_abstract_family_position`), so one rule in this harness decides whether
    a read's rows carry a variant — of *origin*'s own query, because that is the read
    whose rows are being interrogated.
    """
    position = _abstract_family_position(case, origin.get("objectQuery"))
    if position is None:
        return ()
    if position.strategy == STRATEGY_TPCS:
        return ("familyVariant", _TPCS_VARIANT_COLUMN)
    return ("familyVariant",)


def _row_is_variant_of(
    case: Case, entity: Entity, row: dict[str, Any], variant_columns: tuple[str, ...]
) -> bool:
    """Whether an observed row is a row of *entity*'s own concrete subtype.

    A discriminated-union read tags every returned row with the concrete variant it
    resolved to (`m-inheritance` *Abstract-position reads*), and that tag is what
    separates two sibling rows a key alone cannot: the raw tag column under
    table-per-hierarchy, and otherwise whichever field the ORIGIN read states its
    variant in (*variant_columns*, from :func:`_origin_variant_columns`). The tag
    column is read first and needs no such licence: it is a real column of the shared
    table carrying that row's own ``tagValue``, so it says the same thing wherever it
    appears.

    A row stating no variant answers for its key alone — a concrete-target read
    projects no discriminator, because every row it returns is already the queried
    subtype's.
    """
    tag = _tag(entity)
    if tag is not None and tag[0] in row:
        return _write_value_equal(row[tag[0]], tag[1])
    for column in variant_columns:
        if column in row:
            return row[column] == Family(case.model.entity_defs).variant_spelling(
                entity.canonical_name
            )
    return True


def _settled_generation(
    case: Case, entity: Entity, index: int, origin: dict[str, Any], pk: Any, version_column: str
) -> Any:
    """The version a settled versioned write's named find observed, of *pk*.

    The versioned peer of :func:`_settled_milestone`: a versioned key holds one
    ROW but one observed GENERATION per read of it, so the resolved row must carry
    the version that read saw, and a row carrying none states no generation for
    the write to have settled against.
    """
    row = _settled_observed_row(case, entity, index, origin, pk, "generation")
    if version_column not in row:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles against a find whose observed "
            f"{entity.name} pk {pk!r} carries no {version_column!r} — a keyed write settles "
            f"against the ONE generation the value it was handed came from."
        )
    return row[version_column]


def _sole_settled_row(
    case: Case, index: int, entity: Entity, entry: dict[str, Any]
) -> dict[str, Any]:
    """The ONE row a settled write entry authors.

    The plural half is `m-unit-work`'s own singleton — a temporal entry chains
    one milestone, and an observed write of any profile is evidence about one row
    — and it is asked of the SAME
    :func:`~reference_harness.keyed_write_validate.validate_keyed_write` every
    other lane asks it of, so this lane cannot refuse a different set of entries;
    what is local here is only the consequence — a settled entry must hand over
    exactly one row, because the named find handed over exactly one value.
    """
    try:
        validate_keyed_write(entity, entry)
    except RejectionError as exc:
        raise CaseFailure(f"{case.path.name}: scenario[{index}]: {exc.detail}") from exc
    rows = entry.get("rows")
    if not isinstance(rows, list) or len(rows) != 1:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles a write entry carrying "
            f"{len(rows) if isinstance(rows, list) else 0} rows against a find — a settled "
            f"entry carries ONE row, which is the one value that find handed over."
        )
    return rows[0]


def _settled_milestone(
    case: Case, entity: Entity, index: int, origin: dict[str, Any], pk: Any
) -> _Rectangle:
    """The milestone a settled write's named find observed, of *pk*.

    A milestone chain holds several rows per key, so the resolved row's own
    rectangle is the whole of what the close derives from.

    A Transaction-Time-Only target has no Valid-Time half to read, and its close
    addresses the key plus the invariant open Transaction-Time bound, so there the
    milestone the find observed reaches the golden through the optimistic gate
    alone.
    """
    axes = {axis.dimension: axis for axis in temporal_axes(entity.runtime_facts)}
    valid_axis, tx_axis = axes.get("valid-time"), axes["transaction-time"]
    row = _settled_observed_row(case, entity, index, origin, pk, "milestone")
    return _Rectangle(
        row.get(valid_axis.start.column) if valid_axis is not None else None,
        row.get(valid_axis.end.column) if valid_axis is not None else None,
        row.get(tx_axis.start.column),
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


# Action-step verbs in the m-case-format lifecycle vocabulary. The DML verbs
# COMMIT their buffered golden SQL (a `flush` materializes pending writes, a
# `mergeBack` / `commit` reconciles at the boundary); the READ verbs execute a
# relationship / list query and return rows (a `load` triggers a deferred fetch,
# an `access` reads an already-loaded set). Every other verb (`mutate` with no
# DML, `detachCopy`, `abort`) is an in-memory / rollback step whose lifecycle and
# reference-identity observables are adapter-delegated — validated by the schema
# here, then graded by each language's API Conformance Suite.
_ACTION_DML_VERBS = frozenset({"flush", "mergeBack", "commit"})
_ACTION_READ_VERBS = frozenset({"load", "access"})


def _relationship_path_target(case: Case, start: Entity, path: str) -> Entity:
    """The terminal entity of a dotted relationship *path* walked from *start*.

    A ``load`` / ``access`` navigates one hop (``items``) or a dotted multi-hop path
    (``items.statuses``) from the source object, so its rows are of the entity the
    LAST hop targets — the entity whose value-object schema decodes them. Each hop
    resolves through its owning entity's compiled structured relationship join.
    """
    entity = start
    for rel_name in path.split("."):
        relationship = entity.relationship_metadata_by_name(rel_name)
        entity = case.model.entity(relationship["join"]["target"]["entity"])
    return entity


def _scenario_step_read_entity(
    case: Case, step: dict[str, Any], step_entities: list[Entity | None]
) -> Entity | None:
    """The entity a scenario step's observed rows belong to (for value-object decode).

    Resolving the PER-STEP read entity — rather than assuming the scenario root —
    is what lets a step reading a DIFFERENT, value-object-bearing entity decode its
    document column with the RIGHT composite schema (m-sql *Read projection*, slot 4;
    m-case-format *Read result form*). A read step names its queried position
    inside its own ``objectQuery.target``. A ``load`` / ``access`` action
    navigates from an earlier object (``on``, required for the read verbs): with a
    ``path`` its rows are the path's TERMINAL entity; a path-less query-backed-list
    ``access`` resolves the constructed list's own (source) entity. Every other step
    (a write, a boundary / in-memory action) observes no rows, so it decodes nothing
    (``None``).
    """
    if "objectQuery" in step:
        return case.model.entity(step["objectQuery"]["target"])
    if step.get("action") in _ACTION_READ_VERBS:
        on = step["on"]
        source = on[0] if isinstance(on, list) else on
        start = step_entities[source]
        path = step.get("path")
        if path is None or start is None:
            # A path-less query-backed-list `access` resolves the list's own (source)
            # entity; a source that observed no rows (should not occur for a read
            # verb, whose `on` names a row-producing step) decodes nothing.
            return start
        return _relationship_path_target(case, start, path)
    return None


@dataclass(frozen=True)
class _StepIncludes:
    """What one scenario read step's Include Paths materialized, kept for a later step.

    A snapshot graph issues no SQL after materialization (`m-snapshot-read`), so an
    `access` step over an already-loaded relationship executes nothing at all: the
    contents it observes are the ones THIS step's own levels fetched. They are held
    per HOP, exactly as a deep-fetch read case holds them, so the assembly a later
    step runs is the same assembly over the same buckets
    (:func:`_assemble_graph`) — the retention is the only new thing, not the graph.
    """

    query: dict[str, Any]
    steps: list[_FetchStep]
    root_rows: list[dict[str, Any]]
    children_by_hop: dict[_HopKey, dict[Any, list[dict[str, Any]]]]


def _run_step_includes(
    case: Case,
    reader: DatabaseProvider,
    index: int,
    step: dict[str, Any],
    root_rows: list[dict[str, Any]],
    pairs: list[tuple[str, list[Any]]],
) -> _StepIncludes | None:
    """Execute a scenario read step's child levels, or refuse a step that lists SQL
    for levels its own query declares none of.

    A read step's own ``objectQuery`` carries Include Paths exactly as a read case's
    does, so the step costs ``1 + L`` round trips and lists one golden statement per
    non-empty level. Without includes there is nothing after the root, so a second
    listed statement is SQL nobody executes and the step's declared round trips would
    count a call it never made.
    """
    query = step["objectQuery"]
    if not _query_has_includes(query):
        if len(pairs) > 1:
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] lists {len(pairs)} golden "
                f"statements but its objectQuery declares no `includes`, so only the "
                f"root read has a level to run. A step that costs more than one round "
                f"trip MUST declare the include levels the extra statements fetch."
            )
        return None
    steps = _fetch_steps(case.model, query)
    children_by_hop = _execute_fetch_levels(
        case,
        reader,
        f"when.scenario[{index}].statements",
        query,
        steps,
        root_rows,
        pairs[1:],
    )
    return _StepIncludes(query, steps, root_rows, children_by_hop)


def _step_graph_nodes(
    case: Case, index: int, path: str, includes: _StepIncludes
) -> list[dict[str, Any] | None]:
    """The nodes a step's ``path`` reaches in the view its source read materialized.

    The whole graph is assembled from the source read's own retained buckets, then
    each hop of the dotted path is followed through the already-attached view keys —
    a to-many hop contributing its list and a to-one hop its single node (or the
    ``None`` a loaded-null view carries). Reaching a key the assembly never attached
    means the source read did not include that relationship, which is an access with
    no materialized contents to state rather than an empty answer.
    """
    assembled = _assemble_graph(
        case, includes.query, includes.steps, includes.root_rows, includes.children_by_hop
    )
    nodes: list[Any] = [node for group in assembled.values() for node in group]
    for hop, rel_name in enumerate(path.split(".")):
        reached: list[Any] = []
        for node in nodes:
            if not isinstance(node, dict) or rel_name not in node:
                raise CaseFailure(
                    f"{case.path.name}: scenario[{index}] accesses {path!r}, but the "
                    f"source read did not include {rel_name!r} (hop {hop}). An access "
                    f"asserting relationship contents MUST name a read whose "
                    f"`objectQuery.includes` materialized them."
                )
            value = node[rel_name]
            reached.extend(value) if isinstance(value, list) else reached.append(value)
        nodes = reached
    return nodes


def _action_source_includes(
    step: dict[str, Any], step_includes: list[_StepIncludes | None]
) -> _StepIncludes | None:
    """What the read an action step names materialized, if that read included anything.

    An action's ``on`` is the read whose objects it acts on, so the view it accesses
    is that read's — the same resolution :func:`_scenario_step_read_entity` makes for
    the entity, made here for the contents.
    """
    on = step.get("on")
    source = (on[0] if on else None) if isinstance(on, list) else on
    if not isinstance(source, int) or not 0 <= source < len(step_includes):
        return None
    return step_includes[source]


def _assert_step_graph(
    case: Case,
    index: int,
    step: dict[str, Any],
    includes: _StepIncludes | None,
    read_entity: Entity | None,
) -> None:
    """Assert an ``access`` step's ``expectGraph`` — the relationship contents the
    already-materialized view answers with (`m-case-format`).

    The oracle is the SAME graph comparison a read case's ``then.graph`` runs
    (:func:`_graphs_equal`, model-aware so an entity collection compares as a
    multiset and a `multiplicity: many` Value Object positionally), applied to the
    nodes the step's ``path`` reaches, keyed by that path's TERMINAL entity — the
    entity :func:`_scenario_step_read_entity` already resolved for this step.
    """
    expected = step.get("expectGraph")
    if expected is None:
        return
    path = step.get("path")
    if includes is None or read_entity is None or not isinstance(path, str):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] declares expectGraph, but it names no "
            f"navigated `path` on a source read carrying `objectQuery.includes`. The "
            f"contents an access states are the ones that read materialized."
        )
    observed = {read_entity.name: _step_graph_nodes(case, index, path, includes)}
    if not _graphs_equal(observed, expected, case.model):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] relationship contents != expectGraph.\n"
            f"  observed: {observed!r}\n"
            f"  expected: {expected!r}"
        )


def _reuse_prior_rows(
    case: Case, step: dict[str, Any], index: int, results: list[list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Rows a zero-round-trip step reuses from an earlier step.

    Two mutually-exclusive shapes, kept distinct so a mis-authored step fails
    LOUDLY rather than passing vacuously on a silently-empty reuse:

    - **A named reuse** — a cache hit / re-access that returns the SAME interned
      objects as an earlier step, named by ``sameObjectAs`` (else, on an action
      step, its ``on`` source). The named source MUST resolve to an EARLIER step
      (``0 <= source < index``); a forward / self / out-of-range index is an
      authoring error, NOT an empty set (which would let a ``sameObjectAs`` /
      ``expectRows`` assertion pass against nothing).
    - **A query-backed list construction that has not resolved yet**
      (``m-op-list-001`` step 0: a ``find`` built with ``roundTrips: 0``, no
      golden SQL, and no named source). It carries no rows until first access, so
      it legitimately reuses the empty set — the ONE intentionally-empty case. It
      MUST assert nothing non-empty (a construction resolves no rows yet), so a
      non-empty ``expectRows`` here is a loud failure.
    """
    named = step.get("sameObjectAs", step.get("on"))
    if named is not None:
        source = (named[0] if named else -1) if isinstance(named, list) else named
        if not 0 <= source < index:
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] reuses prior rows from an "
                f"UNRESOLVED source {source!r} — a zero-round-trip cache hit / "
                f"re-access MUST name an EARLIER resolved step (0 <= source < {index}). "
                f"An empty reuse here would let its identity / expectRows assertion "
                f"pass vacuously."
            )
        return results[source]
    if step.get("expectRows"):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] declares roundTrips 0 with no golden "
            f"SQL and names no reuse source, but asserts non-empty expectRows. Only an "
            f"query-backed list CONSTRUCTION that has not resolved yet may reuse the "
            f"empty set, and it resolves no rows until first access."
        )
    return []


def _assert_action_on(
    case: Case, index: int, step: dict[str, Any], pairs: list[tuple[str, list[Any]]]
) -> None:
    """Validate an action step's ``on`` source indices.

    Every index in ``on`` — a single int, or an array of coordinate-group sources —
    MUST name a REAL earlier step: ``>= 0``, strictly EARLIER than this step, and,
    for the array form, UNIQUE (each source referenced at most once). A
    coordinate-grouped ``load`` (an array ``on``) emits one child statement per
    lowered-coordinate group, so it MUST NOT execute MORE statement groups than it
    references sources — every executed group is accounted for by a referenced
    source (m-deep-fetch batching contract). ``on`` is OPTIONAL on the boundary
    verbs (``flush`` / ``commit`` / ``abort``), which target the unit of work
    rather than a prior object; when a boundary step DOES carry ``on`` (a ``flush``
    documenting its buffered write), the same earlier-and-unique checks apply.
    """
    if "on" not in step:
        return
    on = step["on"]
    indices = list(on) if isinstance(on, list) else [on]
    if isinstance(on, list) and len(set(indices)) != len(indices):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}].on {on!r} names a DUPLICATE source; "
            f"a coordinate-grouped action references each source at most once."
        )
    for src in indices:
        if not 0 <= src < index:
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}].on references step {src!r}, which "
                f"is not a real EARLIER step (0 <= source < {index}); an action targets "
                f"the result of a prior step."
            )
    is_grouped_load = isinstance(on, list) and step.get("action") in _ACTION_READ_VERBS
    if is_grouped_load and len(pairs) > len(indices):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] executes {len(pairs)} statement "
            f"group(s) but references only {len(indices)} coordinate source(s); a "
            f"coordinate-grouped load emits at most one statement per referenced source, "
            f"so every executed group MUST be accounted for by a referenced source."
        )


def _run_scenario_action(
    case: Case,
    db: DatabaseProvider,
    index: int,
    step: dict[str, Any],
    pairs: list[tuple[str, list[Any]]],
    results: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Execute one action step's golden SQL and return the rows it observes.

    A DML verb (`flush` / `mergeBack` / `commit`) commits every buffered statement
    on the unit of work's connection — so a later read observes the flushed state —
    and captures no rows. A read verb (`load` / `access`) executes EVERY listed
    statement (a coordinate-grouped or multi-level load lists one per group / level)
    and aggregates the returned rows; a zero-round-trip re-access reuses the source
    rows. Any other verb (`mutate` / `detachCopy` / `abort`) commits any authored
    golden DML (a Valid-Time-past correction's split write) and captures no rows.
    """
    _assert_action_on(case, index, step, pairs)
    verb = step["action"]
    if verb in _ACTION_READ_VERBS:
        if not pairs:
            return _reuse_prior_rows(case, step, index, results)
        rows: list[dict[str, Any]] = []
        for statement, stmt_binds in pairs:
            rows.extend(_query_rows(case, db, statement, stmt_binds))
        return rows
    for statement, stmt_binds in pairs:
        db.execute(statement, stmt_binds)
    return []


def _assert_step_row_observables(
    case: Case,
    index: int,
    step: dict[str, Any],
    rows: list[dict[str, Any]],
    results: list[list[dict[str, Any]]],
    tolerance: Decimal | None,
    default_identity: str,
) -> None:
    """Assert a step's row-level observables: ``expectRows`` and ``sameObjectAs``.

    ``expectRows`` compares the step's observed rows to the fixture-derived
    expectation; ``sameObjectAs`` checks the one-object-per-PK rule against an
    earlier step. The reference-identity observables (``differentObjectFrom``,
    ``expectState``, ``expectError``) are adapter-delegated — validated by the
    schema and graded by each language's API Conformance Suite — so the wire
    harness skips them here.
    """
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


def _scenario_uow_groups(case: Case) -> dict[str, list[int]]:
    """Every declared `uow` GROUP label -> its step indices, in AUTHORED order
    (`m-case-format` scenario `uow` grouping). A group's own indices need NOT
    be contiguous — two groups may interleave (the optimistic-lock race shape,
    `m-opt-lock-012`: one unit of work's observing find, a CONCURRENT unit of
    work's own observe-and-commit, then back to the first unit of work's own
    doomed write)."""
    groups: dict[str, list[int]] = {}
    for index, step in enumerate(case.scenario):
        label = step.get("uow")
        if isinstance(label, str):
            groups.setdefault(label, []).append(index)
    return groups


def _uow_group_is_doomed(case: Case, indices: list[int]) -> bool:
    """Whether a `uow` group ROLLS BACK after its last step: at least one of
    its OWN write steps declares `rollback: true` — the WHOLE group is then
    the doomed unit of work (`m-case-format` scenario `uow` grouping), not
    just that one step; a later step in the SAME group (e.g. a find re-issued
    to force-flush a pending write) still runs inside the still-open
    transaction before the eventual rollback."""
    return any(
        "write" in case.scenario[i] and case.scenario[i].get("rollback") is True for i in indices
    )


@dataclass
class _UowGroupState:
    """One `uow` group's coordinated lifecycle (`m-case-format` scenario
    grouping) — the data clump :func:`_finish_uow_group` used to juggle as
    four separately-keyed dicts, now one invariant-owning instance per group
    label: the HELD session every step of the group shares (``None`` until
    the group's FIRST step lazily opens it), whether the group is DOOMED —
    rolls back instead of commits at its last step
    (:func:`_uow_group_is_doomed`) — the write statements it has executed so
    far (the conflict-abort proof, :func:`_assert_scenario_conflict_abort`),
    and the step index its LAST step occupies (the boundary
    :func:`_finish_uow_group` closes the group at)."""

    doomed: bool
    last_step: int
    session: Any = None
    executed: list[tuple[str, int]] = field(default_factory=list)


def _finish_uow_group(
    case: Case,
    index: int,
    label: str | None,
    group_states: dict[str, _UowGroupState],
    dialect: str,
) -> None:
    """Close a `uow` group's held session when *index* is its declared LAST
    step: COMMIT (the default), or — when the group is doomed
    (:func:`_uow_group_is_doomed`) — assert the conflict-abort proof on the
    group's own accumulated executed write statements (exactly as the
    ungrouped single-step rollback branch does for one step) and ROLL BACK.
    A no-op for a step whose group has not yet reached its last step, or for
    an ungrouped step (*label* is ``None``)."""
    if label is None:
        return
    state = group_states[label]
    if index != state.last_step:
        return
    if state.doomed:
        # A group that declares `then.affectedRows` is a conflict-abort group
        # (m-opt-lock + m-unit-work): the UoW aborts BECAUSE a version-gated
        # write conflicted. Assert the conflict was actually DETECTED (the
        # gated write affected `then.affectedRows` rows — `updatedRows != 1`)
        # BEFORE rolling back, so a rollback that merely discarded a
        # NON-conflicting write fails the case rather than passing on a
        # vacuous abort.
        if case.expected_affected_rows is not None and state.executed:
            _assert_scenario_conflict_abort(case, index, state.executed, dialect)
        state.session.rollback()
    else:
        state.session.commit()
    # The group's own steps are exhausted (this WAS its last step, by
    # `_scenario_uow_groups`'s own authored-order accounting), so no later
    # step ever looks the session up again — cleared anyway, so a
    # (structurally impossible) later step of the SAME label would open a
    # FRESH session rather than reuse a closed one.
    state.session = None


def _assert_scenario(case: Case, db: DatabaseProvider) -> None:
    """Execute the scenario against the provisioned DB and assert its contract.

    For each step: execute its listed golden SQL (a cache-hit step executes
    nothing and reuses the prior step's rows), assert ``expectRows`` when
    declared, and check any ``sameObjectAs`` identity assertion (both steps'
    results carry the same primary-key identity — the one-object-per-PK rule).

    A step carrying the OPTIONAL `uow` grouping key (`m-case-format`) executes
    on a HELD session shared with every other step of the SAME label instead
    of its own default boundary: a grouped write applies through the session
    (never committed per-step) and a grouped find reads THROUGH the session
    (read-your-own-writes, mid-transaction). The group's session commits
    after its own declared LAST step, or rolls back there instead when the
    group is doomed (:func:`_uow_group_is_doomed`) — the whole group is then
    ONE unit of work sharing the abort contract, not each step its own. Two
    groups MAY interleave (non-contiguous in authored order): each group's
    own session, once opened, stays open across the OTHER group's steps in
    between, closing only at ITS OWN last step. An UNGROUPED step (no `uow`
    key) keeps exactly today's behavior, byte-for-byte: a committed write
    applies on the provider's autocommit connection, a rolled-back write opens
    its OWN single-step session, and a find reads on the autocommit
    connection.
    """
    dialect = db.dialect
    root_entity = _scenario_root_entity(case)
    default_identity = _pk_column(root_entity)
    tolerance = case.tolerance

    groups = _scenario_uow_groups(case)
    group_states: dict[str, _UowGroupState] = {
        label: _UowGroupState(doomed=_uow_group_is_doomed(case, indices), last_step=indices[-1])
        for label, indices in groups.items()
    }

    results: list[list[dict[str, Any]]] = []
    step_entities: list[Entity | None] = []
    # Parallel to `results`, holding what each step's Include Paths materialized so
    # a later zero-round-trip `access` can state its contents (`_StepIncludes`). A
    # step that included nothing parks `None`, exactly as a write parks `[]`.
    step_includes: list[_StepIncludes | None] = []
    with contextlib.ExitStack() as stack:
        for index, step in enumerate(case.scenario):
            pairs = _entry_pairs(step.get("statements"), dialect)
            raw_label = step.get("uow")
            label = raw_label if isinstance(raw_label, str) else None
            state = group_states.get(label) if label is not None else None
            session: Any = None
            if state is not None:
                if state.session is None:
                    state.session = stack.enter_context(db.open_session())
                session = state.session
            if "write" in step:
                if session is not None:
                    # A GROUPED write: apply on the group's own held session — the
                    # GROUP commits or rolls back as ONE unit at its last step
                    # (:func:`_finish_uow_group`), never this step alone.
                    assert state is not None  # `session` is only ever set alongside `state`
                    for statement, stmt_binds in pairs:
                        state.executed.append((statement, session.execute(statement, stmt_binds)))
                elif step.get("rollback"):
                    # An UNGROUPED aborted write (m-unit-work abort contract): apply
                    # each DML statement inside a manual-commit session, then ROLL
                    # BACK. The write lands in the atomic scope the abort discards,
                    # so a later find MUST re-resolve and observe the ORIGINAL rows,
                    # never the aborted write.
                    with db.open_session() as rb_session:
                        executed: list[tuple[str, int]] = []
                        for statement, stmt_binds in pairs:
                            executed.append((statement, rb_session.execute(statement, stmt_binds)))
                        # See the SAME conflict-abort reasoning in
                        # :func:`_finish_uow_group` — the ungrouped, single-step form.
                        if case.expected_affected_rows is not None:
                            _assert_scenario_conflict_abort(case, index, executed, dialect)
                        rb_session.rollback()
                else:
                    # A committed write between finds (read-your-own-writes / cache
                    # invalidation): apply and COMMIT each DML statement on the unit of
                    # work's connection. It captures no rows; a later find observes the
                    # committed state.
                    for statement, stmt_binds in pairs:
                        db.execute(statement, stmt_binds)
                # The step's index still occupies a slot so `sameObjectAs` references
                # stay aligned. A write observes no rows, so it reads no entity.
                results.append([])
                step_entities.append(None)
                step_includes.append(None)
                _finish_uow_group(case, index, label, group_states, dialect)
                continue
            if "action" in step:
                # A lifecycle ACTION step: execute its golden SQL
                # (a load / access relationship query, a flush / mergeBack / commit DML)
                # and grade its row-level observables; identity / state / error observables
                # are adapter-delegated (validated, then skipped on the wire lane). The
                # schema forbids `uow` on an action step (it routes through the
                # lifecycle-object engine path, which never observes grouping), so it
                # always executes on the provider's autocommit connection.
                rows = _run_scenario_action(case, db, index, step, pairs, results)
                read_entity = _scenario_step_read_entity(case, step, step_entities)
                if pairs and read_entity is not None:
                    # A FRESHLY-resolved load / first access materializes the value-object
                    # document of the entity it navigated TO (m-sql "Read projection", slot 4;
                    # m-case-format "Read result form") — resolved per-step, so a value-object-
                    # bearing child decodes with its OWN composite schema, never the root's. A
                    # zero-round-trip re-access reuses rows already materialized upstream.
                    rows = [_materialize_owner_node(read_entity, row) for row in rows]
                results.append(rows)
                step_entities.append(read_entity)
                step_includes.append(None)
                _assert_step_row_observables(
                    case, index, step, rows, results, tolerance, default_identity
                )
                # `expectGraph` states the contents of the relationship this step
                # navigated TO, which the SOURCE read materialized — nothing this
                # zero-round-trip access fetched, which is the whole claim.
                _assert_step_graph(
                    case, index, step, _action_source_includes(step, step_includes), read_entity
                )
                continue
            # Every remaining step is a read (per the schema's exactly-one-of
            # objectQuery/write/action): its read entity resolves through the SAME
            # per-step helper the action branch uses (`_scenario_step_read_entity`,
            # the single source of truth) — for a read that is its query's own
            # `target`, so its value-object document is decoded with THAT entity's
            # composite schema, not the scenario root's.
            read_entity = _scenario_step_read_entity(case, step, step_entities)
            if read_entity is None:
                raise CaseFailure(
                    f"{case.path.name}: scenario[{index}] find step resolved no read entity"
                )
            if pairs:
                # A DB-touching step: m-unit-work finds are single-statement, so the round-trip
                # count is one; execute it and capture the rows. GROUPED, it reads THROUGH the
                # group's own held session (read-your-own-writes, mid-transaction); ungrouped,
                # it reads on the provider's autocommit connection, exactly as before.
                statement, stmt_binds = pairs[0]
                reader: Any = session if session is not None else db
                rows = _query_rows(case, reader, statement, stmt_binds)
                # GROUPED, the oracle runs on the SAME held session as the golden read
                # above (`reader`) rather than the top-level `db`: after an uncommitted
                # grouped write the two connections would otherwise observe DIFFERENT
                # states, silently breaking the "independent-but-equivalent" contract.
                _assert_scenario_reference_sql(case, reader, index, step, rows)
                # An INSTANCE-FORM find materializes its owner's value-object document with
                # the row (m-value-object / m-sql "Read projection", slot 4), so decode +
                # project each top-level value-object column into its declared composite
                # before grading expectRows — exactly as the graph-read path does
                # (`_materialize_owner_node`). A ROW-FORM read (the materialized-predicate-
                # write resolving find) projects the document only where the write it serves
                # needs it, and a value-object-free entity (every scenario read but the
                # supplier and subscriber witnesses) declares no value object, so a row
                # carrying no document column passes through byte-identical. The referenceSql
                # oracle above already ran on the raw rows, so the value-object columns never
                # route through that identity compare.
                #
                # Under Relational Document Layout the fan-out comes FIRST, because it is
                # what puts each occurrence back under the very column name the projection
                # below reads it from — after which that projection is layout-blind.
                rows = _materialize_document_layout(
                    case, read_entity, rows, include_value_objects=True
                )
                rows = [_materialize_owner_node(read_entity, row) for row in rows]
                # A read step's own Include Paths are the levels after the root, run
                # and retained here so a later `access` states contents THIS read
                # materialized rather than ones it re-fetched.
                includes = _run_step_includes(case, reader, index, step, rows, pairs)
            else:
                # A cache hit (or an m-op-list construction that has not resolved yet): no
                # statement executes. Reuse the SAME interned objects as the step it hits.
                rows = _reuse_prior_rows(case, step, index, results)
                includes = None
            results.append(rows)
            step_entities.append(read_entity)
            step_includes.append(includes)
            _assert_step_row_observables(
                case, index, step, rows, results, tolerance, default_identity
            )
            _finish_uow_group(case, index, label, group_states, dialect)


def _has_version_gate(statement: str, version_col: str, dialect: str) -> bool:
    """True when a versioned write's OUTER predicate gates on the optimistic version.

    The optimistic golden write appends ``and <version> = ?`` to its keyed predicate
    (m-opt-lock). Two other places name the same column and are NOT that gate: an
    ``UPDATE``'s own ``SET`` clause, which carries the framework-derived advance in
    BOTH modes, and any nested ``SELECT``'s own ``WHERE`` — which is why the gate is
    projected out of the parsed statement (:func:`_existing_row_write`) rather than
    scanned for. A statement that is no existing-row write carries no gate.
    """
    write = _existing_row_write(statement, dialect)
    return write is not None and any(_gates_on(operand, version_col) for operand in write.conjuncts)


def _dml_target(statement: str, dialect: str) -> exp.Identifier | None:
    """The identifier *statement* names its target table with, or None when it is no
    table-targeting DML for *dialect*.

    The one reader of WHICH TABLE a write lands in, covering the ``INSERT`` that
    :func:`_existing_row_write` does not: table-per-concrete-subtype routing asks it of
    every statement a write emits, because there the table IS the concrete subtype
    (`m-inheritance`). Taken from the parse so the identifier keeps its own quoting,
    which is what decides whether the spelling is the model's table (:func:`_names`) —
    a reserved or otherwise non-simple physical name is rendered QUOTED (`m-dialect`).
    """
    with contextlib.suppress(sqlglot.ParseError):
        return _dml_target_of(sqlglot.parse_one(statement, read=sqlglot_dialect(dialect)))
    return None


def _dml_target_of(tree: Expr) -> exp.Identifier | None:
    """The target-table identifier of an already-parsed ``INSERT`` / ``UPDATE`` /
    ``DELETE``, or None for any other statement.

    An ``INSERT`` carries its table inside the column-list schema; the existing-row
    verbs name it directly.
    """
    if not isinstance(tree, (exp.Insert, exp.Update, exp.Delete)):
        return None
    target = tree.this
    if isinstance(target, exp.Schema):
        target = target.this
    if not isinstance(target, exp.Table) or not isinstance(target.this, exp.Identifier):
        return None
    return target.this


class _ExistingRowWrite(NamedTuple):
    """The outer keyed DML a golden statement is: the identifier its ``UPDATE`` /
    ``DELETE`` names the target table with, and its own top-level predicate
    conjuncts."""

    table: exp.Identifier
    conjuncts: tuple[Expr, ...]


def _existing_row_write(statement: str, dialect: str) -> _ExistingRowWrite | None:
    """*statement* read as the existing-row write it is, or None when it is not one.

    The ONE reader of that grammar, which each consumer projects its own fact out of
    — which object the statement addresses (:func:`_statement_object`), whether it
    gates on the optimistic version (:func:`_has_version_gate`) — so what counts as
    an existing-row write, and what an unparseable or non-DML statement answers,
    is decided in one place for all of them.

    Read through the grammar rather than by pattern, because a reserved physical
    table or column is rendered QUOTED (`m-dialect`), the last ` where ` in the text
    may belong to a subquery, and a subquery's own predicate is a conjunct of the
    inner ``SELECT`` rather than of this one (:func:`_conjuncts`). A statement that
    does not parse for *dialect*, that is not an ``UPDATE`` / ``DELETE`` of a table,
    or that carries no outer predicate is no existing-row write: it addresses no
    object and gates on nothing.
    """
    with contextlib.suppress(sqlglot.ParseError):
        tree = sqlglot.parse_one(statement, read=sqlglot_dialect(dialect))
        if not isinstance(tree, (exp.Update, exp.Delete)):
            return None
        table, where = _dml_target_of(tree), tree.args.get("where")
        if table is not None and isinstance(where, exp.Where):
            return _ExistingRowWrite(table, tuple(_conjuncts(where.this)))
    return None


def _conjuncts(predicate: Expr) -> Iterator[Expr]:
    """*predicate*'s own top-level ``AND`` operands, parentheses flattened.

    A subquery yields as ONE opaque operand: its own predicate is a conjunct of the
    inner ``SELECT``, never of this one, which is exactly the distinction a text scan
    cannot make.
    """
    if isinstance(predicate, exp.And):
        yield from _conjuncts(predicate.left)
        yield from _conjuncts(predicate.right)
    elif isinstance(predicate, exp.Paren):
        yield from _conjuncts(predicate.this)
    else:
        yield predicate


def _gates_on(operand: Expr, column: str) -> bool:
    """Whether *operand* is the ``<column> = ?`` equality a gate renders."""
    bound = _bound_equality_identifier(operand)
    return bound is not None and _names(bound, column)


def _bound_equality_identifier(operand: Expr) -> exp.Identifier | None:
    """The identifier a ``<column> = ?`` conjunct names its column with, or None for
    any other operand.

    The one predicate shape both a gate and an address are written in, either way
    round, taken from the parse so the identifier keeps its own quoting — which is
    what decides whether the spelling is the model's column (:func:`_names`).
    """
    if not isinstance(operand, exp.EQ):
        return None
    left, right = operand.left, operand.right
    if isinstance(right, exp.Column) and isinstance(left, exp.Placeholder):
        left, right = right, left
    if isinstance(left, exp.Column) and isinstance(right, exp.Placeholder):
        return left.this if isinstance(left.this, exp.Identifier) else None
    return None


def _names(identifier: exp.Identifier, declared: str) -> bool:
    """Whether *identifier*, as a golden spells it, is the physical *declared* name.

    A QUOTED identifier keeps exactly the name it spells — quoting is what a
    reserved or otherwise non-simple physical name is rendered with, and the
    normalizer preserves it (`m-dialect`) — while an UNQUOTED one is folded by the
    database, so it names *declared* whenever the two differ only in case.
    Lowercasing both sides instead would read a quoted ``"Order"`` and a bare
    ``order``, two names one model may declare separately, as one identifier.
    """
    return identifier.name == declared or (
        not identifier.quoted and identifier.name.lower() == declared.lower()
    )


def _assert_scenario_conflict_abort(
    case: Case,
    index: int,
    executed: list[tuple[str, int]],
    dialect: str,
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
    gated = [
        (sql, affected)
        for sql, affected in executed
        if _has_version_gate(sql, version_col, dialect)
    ]
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


# --- conflict cases (m-opt-lock optimistic locking) ----------------------------------


def _assert_conflict(case: Case, db: DatabaseProvider) -> None:
    """Run the given.apply + the golden write, assert the affected-row count.

    This is the observable form of a write's affected-row outcome. The model's
    fixtures are loaded (the addressed rows exist), then an OPTIONAL out-of-band
    ``given.apply`` simulates a concurrent transaction mutating, removing, or
    duplicating them. The golden write is then applied. Under ``optimistic`` mode
    a versioned golden renders ``… where pk = ? and version = ?`` and binds the
    version the caller read EARLIER, so a concurrent version bump makes the
    stale-version predicate match zero rows; under ``locking`` mode it renders no
    gate at all, and the shared read lock is what licensed the write. Either way
    the count the golden reaches — short of, equal to, or beyond what its target
    addresses — is the observable, and the case's own ``affectedRows`` names it.

    This harness runs the golden statement directly rather than through a unit of
    work, so it never refuses a write and never rolls one back. A case whose write
    a unit of work WOULD refuse therefore authors no ``then.tableState``: the two
    lanes legitimately disagree on the resulting rows, and only the count and the
    statement are common ground.
    """
    dialect = db.dialect
    statements = case.golden_statements(dialect)
    if len(statements) != 1:
        raise CaseFailure(
            f"{case.path.name}: a conflict case has exactly one golden write "
            f"statement, but then.statements ({dialect}) lists {len(statements)}."
        )

    # Here the out-of-band setup is a concurrent transaction's own mutation.
    _apply_given(case, db)

    affected = db.execute(statements[0], case.statement_binds(0))
    expected = case.expected_affected_rows
    if affected != expected:
        raise CaseFailure(
            f"{case.path.name}: the golden write affected {affected} row(s) but "
            f"affectedRows is {expected}. The count a golden reaches after the "
            f"concurrent mutation is the whole claim: a row moved out from under it "
            f"is not matched, a row left alone is, and a target the concurrent "
            f"mutation duplicated is matched more than once."
        )

    if case.expected_table_state:
        types = contributor_types(case.model)
        for table, expected_rows in case.expected_table_state.items():
            actual = _read_table(db, _table_layout(case, table), types)
            if not _rows_equal(actual, expected_rows, case.tolerance):
                raise CaseFailure(
                    f"{case.path.name}: table {table!r} state after the conflict "
                    f"case != then.tableState.\n"
                    f"  actual:   {actual!r}\n"
                    f"  expected: {expected_rows!r}"
                )


# --- conflict RETRY cases (m-opt-lock retry contract) ------------------------------


def _attempt_statements(attempt: dict[str, Any], dialect: str) -> list[str]:
    """The golden write statement(s) a retry attempt lists for *dialect*."""
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

    This is the observable form of the m-opt-lock RETRY contract. The model's
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

    _apply_given(case, db)

    for index, attempt in enumerate(case.attempts):
        statements = _attempt_statements(attempt, dialect)
        if len(statements) != 1:
            raise CaseFailure(
                f"{case.path.name}: attempts[{index}] must list exactly one golden "
                f"UPDATE for {dialect}, found {len(statements)}."
            )
        affected = db.execute(statements[0], _entry_binds(attempt.get("statements"), 0, dialect))
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
    types = contributor_types(case.model)
    for table, expected_rows in case.expected_table_state.items():
        actual = _read_table(db, _table_layout(case, table), types)
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
    barrier + two ``open_session`` plumbing: ``m-read-lock-007`` (both readers take
    the shared lock and BOTH succeed -- shared, not exclusive). Each node runs its
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
                        # A write step (kind: write) succeeds iff no lock blocks it;
                        # it holds until the finally rolls it back.
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


# --- coherence cases (cross-process cache coherence) -------------------------


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
                rows = _query_rows(case, node, statement, binds)
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
            # `m-read-lock-002`, `m-read-lock-004`, and `m-read-lock-005`) still
            # round-trips its query + descriptor through the serde seam.
            _assert_serde(case)
            _assert_equivalent_encodings(case)
        return

    if case.is_rejected:
        # Negative validation (m-value-object / m-predicate, resolved Q7): the input
        # is refused PRE-SQL by model-aware validation — no dialect, no provisioning,
        # no execution. It runs identically on every dialect (idempotent, DB-free), so
        # branch here before the dialect is even read.
        _assert_schema(case)  # layer 1 (structural invariants for the shape)
        _assert_serde(case)  # layer 4 (query, if any, + descriptor)
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
        _assert_scenario_settled_write(case, dialect)  # layer 5c (observed state ↔ ②)
        _provision(case, db)
        # Here the out-of-band setup puts state into a row no authored member could
        # produce — a Structured Column key the model declares nowhere included.
        _apply_given(case, db)
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
        _assert_serde(case)  # descriptor serde only (error cases carry no query)
        _assert_equivalent_encodings(case)
        if not _error_has_golden(case, dialect):
            return  # no golden for this dialect: dialect-agnostic checks only
        _assert_error_normalization(case, dialect)  # layer 3
        _assert_error_classification(case, db)
        return

    if case.is_concurrency_success:
        # A concurrency-success case (m-read-lock behavioral read-lock:
        # m-read-lock-007) also carries its golden per round inside
        # `concurrency.rounds` (no top-level then.statements), so
        # branch before the then.statements access below, as a sibling of `is_error`.
        _assert_schema(case)
        _assert_serde(case)  # descriptor serde only (no query)
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
        # Here the out-of-band setup is what the m-detach merge-back-reinserts case
        # needs: DELETE the original persisted row, so the merge-back finds no
        # original and INSERTs the copy as a new row.
        _apply_given(case, db)
        _assert_write_sequence(case, db)  # apply DML, assert table state
        _assert_pk_allocation(case, db)  # layer 5b: PK-generation oracle (sequence)
        return

    if case.is_conflict:
        _assert_conflict_input(case, dialect)  # layer 5c (① ↔ ② single form)
        _provision(case, db)  # fixtures loaded: the row to lock exists
        _assert_conflict(case, db)  # given.apply + golden write, affected rows
        return

    # Every remaining shape is a read, and every read's narrow / attribute positions are
    # validated once here rather than per result form (the read-side counterpart of the
    # write-derivation oracle). It runs before provisioning because the rule it enforces
    # is a pre-SQL refusal: a read whose reference escapes its active position must fail
    # the case, not reach a database.
    validate_query_inheritance(case.model.entity_defs, case.object_query)
    _assert_round_trip_count(case, dialect)  # layer 5 (count)
    _provision(case, db)
    if _is_deep_fetch(case):
        _assert_deep_fetch(case, db)  # layer 2 + 5 (graph)
    elif case.expected_graphs is not None:
        # A milestone-set snapshot read (m-snapshot-read, Q5a): a `history` /
        # `asOfRange` read materializes one independently edge-pinned graph per
        # milestone, asserted from `then.graphs`.
        _assert_graphs(case, db)  # layer 2 + 5 (per-milestone graphs)
    elif case.expected_graph is not None:
        # A top-level, single-instant `then.graph` read (no Includes): the single
        # golden statement materializes into the graph with no child statement.
        # Value-object decoding (m-value-object) and inheritance per-variant
        # narrowing are each a conditional step inside —
        # a no-op for a case that carries neither.
        _assert_single_statement_graph(case, db)  # layer 2 + 5 (graph)
    else:
        _assert_flat_equivalence(case, db)  # layer 2
