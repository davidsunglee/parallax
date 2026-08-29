"""The layered assertion engine (m-case-format runner sub-part).

:func:`run_case` decides which of the corpus's case shapes a case is and runs
that shape's own ordered sequence of assertion layers against a freshly
provisioned database selected via the provider seam:

1. **Schema conformance** — descriptor / query / case validate (done
   statically by :mod:`schema_validate`; re-asserted here for the loaded case).
2. **Triple equivalence** — ``exec(then.statements[dialect]) == exec(referenceSql) ==
   then.rows`` (the ``referenceSql`` term only when present).
3. **Normalization determinism** — ``normalize(then.statements[dialect]) ==
   then.statements[dialect]`` (per statement, for multi-statement cases).
4. **Serde round-trip** — ``serialize(deserialize(x)) == x`` for BOTH the
   Object Query encoding AND the model descriptor, in BOTH JSON and YAML.
5. **Round-trip-count consistency** — the number of golden SQL statements a case
   declares equals its ``roundTrips``.

What this module owns beyond those shared layers is everything that is not an
accepted Object Query observation: case-shape routing, rejected-case
adjudication, provisioning, DDL, fixtures, write sequences, conflicts, error
classification, concurrency, coherence, and Unit Work Scenario orchestration —
step order, reader selection, transaction lifecycle, writes, boundary actions,
unresolved query-backed-list construction, and Scenario-wide accounting.

Every accepted read is :mod:`object_query_oracle`'s: ``assert_case_read`` for a
read-shaped case and ``ScenarioReads.assert_step`` for a Scenario's read steps.
This module states a case and an executor, or a step index and a reader, and
nothing about delivery strategy, retained observations, or read intent.

What a golden WRITE statement must be for the neutral input it renders is
:mod:`write_plan`'s, for every lane that authors one. This module composes a
lane's own ordered steps and states each write it grades; how a row resolves to
columns, what a close addresses, which column gates or routes, and how a rendered
statement is taken apart are decided there.

It deliberately **never compiles a query to SQL** — that is the job of a
real implementation, graded against the golden SQL.
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from . import errors, serde
from .case import (
    Case,
    Entity,
    Model,
    conflict_write_rows,
    entry_bind_values,
    entry_pairs,
    entry_statements,
)
from .case_assertions import (
    CaseFailure,
    assert_step_on_sources,
    coerce_identity_key,
    rows_equal,
    write_value_equal,
)
from .data_loader import load_model
from .ddl_builder import (
    contributor_types,
    ddl_for,
    quote_identifier,
)
from .document_codec import decode_stored, encode_document, encode_leaf, is_document
from .inheritance import (
    MODEL_REJECTED_RULES,
    PREDICATE_REJECTED_RULES,
    STRATEGY_TPCS,
    WRITE_REJECTED_RULES,
    Family,
    query_position,
    validate_family,
    validate_query_inheritance,
)
from .keyed_write_validate import (
    KEYED_WRITE_REJECTED_RULES,
    undeclared_row_members,
    validate_keyed_write,
)
from .metamodel import (
    MODEL_REJECTED_RULES as METAMODEL_MODEL_REJECTED_RULES,
)
from .metamodel import (
    validate_index_identities,
)
from .object_query_oracle import ScenarioReads, assert_case_read
from .object_query_validate import validate_object_query
from .predicate_write_validate import (
    requires_predicate_write_materialization,
    validate_predicate_write,
)
from .providers import DatabaseProvider
from .sql_normalize import normalize
from .storage_layout import (
    MODEL_REJECTED_RULES as STORAGE_LAYOUT_MODEL_REJECTED_RULES,
)
from .storage_layout import (
    ColumnContributor,
    ColumnTier,
    TableLayout,
    validate_storage_layout,
)
from .temporal_selection_validate import normalize_authored_temporal_selections
from .temporality import derive_temporal_structure, temporal_axes
from .value_object_resolve import REJECTED_RULES, RejectionError
from .write_plan import (
    MILESTONE_COORDINATE_KEYS,
    OPENING_MUTATIONS,
    ObjectAddress,
    assert_inheritance_write_routing,
    assert_write_values,
    classify_write_row,
    close_address_binds,
    has_temporal_gate,
    has_version_gate,
    is_existing_row_statement,
    parse_insert_columns,
    parse_set_columns,
    statement_object,
    tag,
    unit_resolving_reads,
    version_column,
)
from .write_validate import undeclared_members, validate_subtype_write, validate_write


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


# --- statement-entry readers ------------------------------------------------
#
# Every per-step SQL location (scenario / coherence / attempts / concurrency
# rounds) carries its golden SQL as an ordered list of `{sql, binds}` statement
# entries, mirroring the top-level `then.statements`. Binds are attached to their
# statement structurally — there is no positional pairing convention to interpret.


def _entry_binds(entries: Any, index: int, dialect: str) -> list[Any]:
    """The authored binds of statement *index* in a `statements` entry list for
    *dialect* (default ``[]``).

    Resolved through :func:`~reference_harness.case.entry_bind_values`, so a
    dialect-keyed ``binds`` map answers with the executing dialect's own array
    rather than with its keys.
    """
    if not isinstance(entries, list) or index >= len(entries):
        return []
    entry = entries[index]
    return entry_bind_values(entry, dialect) if isinstance(entry, dict) else []


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
    and a read oracle must correspond to the golden read it is the naive
    spelling of: one statement for an ordinary find, and a STREAMED step's whole
    page list for one delivery (`m-case-format` *Streamed read steps*), whose
    naive oracle answers the roots every page of it published.
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
        if not entries or (len(entries) != 1 and "stream" not in step):
            raise CaseFailure(
                f"{case.path.name}: when.scenario[{index}] referenceSql needs the golden read "
                "it is the naive spelling of — exactly one statement for an ordinary find, "
                "and a streamed step's own pages for one delivery"
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


# --- primary-key generation (m-pk-generation sequence oracle) ---------------


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


# --- provisioning and the model facts every lane reads -----------------------


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


# The projected output column that carries the table-per-concrete-subtype
# `familyVariant` literal per `union all` branch (the settled TPCS asymmetry,
# m-sql): unlike table-per-hierarchy — which projects the RAW tag column and
# derives `familyVariant` at materialization — TPCS has no tag column, so each
# branch projects a subtype-name literal aliased to this column. A settled write's
# find observed its rows under that spelling, so matching one back to its variant
# reads it here.
_TPCS_VARIANT_COLUMN = "family_variant"


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


def _assert_write_step_count(case: Case, dialect: str) -> None:
    """The DML statement count MUST equal the sum of the steps' declared counts,
    and the round trips MUST be that plus every resolving read the sequence owes.

    Each ``writeSequence`` step declares how many golden DML statements it emits
    (default 1); the total over the sequence is the DML statement count, which
    MUST equal the number of then.statements for the dialect. ``roundTrips``
    counts every call that reached the database, so it is that total plus one
    resolving read per entry writing against existing state
    (:func:`write_plan.unit_resolving_reads`) — the read a keyed write verb's source
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
    reads = sum(unit_resolving_reads(case, [entry]) for entry in case.write_sequence)
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
    resident = case.model.storage_layout.document(entity.canonical_name).members
    assignments: list[_DocumentAssignment] = []
    for member in resident:
        name = member.name
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
    if not write_value_equal(derived, golden):
        raise CaseFailure(
            f"{case.path.name}: neutral write input value {derived!r} != golden document key "
            f"{path!r} value {golden!r} for {statement!r}."
        )


def _golden_set_columns(case: Case, statement: str) -> list[str]:
    """The columns a golden UPDATE assigns, refusing a statement that assigns none.

    The write lanes reach this having already decided the step emits an UPDATE, so
    a statement with no `set` clause is an unparseable golden rather than the
    ordinary "assigns nothing" answer :func:`write_plan.parse_set_columns` gives a
    caller that has not.
    """
    columns = parse_set_columns(statement)
    if columns is None:
        raise CaseFailure(
            f"{case.path.name}: could not parse the SET clause from golden {statement!r}."
        )
    return columns


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
            classify_write_row(
                case,
                entity,
                row,
                mutation=mutation,
                opening=mutation in OPENING_MUTATIONS or entity.is_temporal,
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
        elif version_column(entity) is not None:
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
        assert_inheritance_write_routing(case, entity, step_statements, step_binds, dialect)
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
    version_col = version_column(entity)
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
    golden_columns = parse_insert_columns(case, statement)
    order = _write_column_order(case, entity)
    domain = [c for c in order if any(c in cols for cols, *_ in classified)]
    # A TABLE-PER-HIERARCHY insert writes the tag column from the concrete subtype's
    # tagValue (m-inheritance) — a FRAMEWORK-DERIVED column, never carried in ① —
    # slotted at its Discriminator-tier position, exactly as the version column is derived.
    discriminator = tag(entity)
    if discriminator is not None and discriminator[0] in domain:
        raise CaseFailure(
            f"{case.path.name}: the neutral write input (①) carries the tag "
            f"column {discriminator[0]!r}, which a table-per-hierarchy write derives from "
            f"the concrete subtype's tagValue (m-inheritance), never authored."
        )
    emitted = [
        c for c in order if c in domain or (discriminator is not None and c == discriminator[0])
    ]
    # A VERSIONED insert appends the framework-owned version column with the DERIVED
    # initial value `1` (never authored in ①, so it is not in the row's columns).
    present = [*emitted, version_col] if version_col is not None else emitted
    if golden_columns != present:
        raise CaseFailure(
            f"{case.path.name}: the golden INSERT column list {golden_columns} != the "
            f"columns the neutral write input resolves to {present} (Table Layout order, "
            f"present attributes"
            f"{' + derived tag' if discriminator is not None else ''}"
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
        assert_write_values(case, expected, binds[len(binds) - len(expected) :], statement)
        return
    expected: list[Any] = []
    for cols, *_ in classified:
        for column in emitted:
            if discriminator is not None and column == discriminator[0]:
                # The tag's bind is the concrete subtype's tagValue, DERIVED
                # from the model (m-inheritance), never an ① literal.
                expected.append(discriminator[1])
            else:
                expected.append(cols[column])
        if version_col is not None:
            expected.append(1)  # derived initial version (m-opt-lock baseline), never authored
    assert_write_values(case, expected, binds, statement)


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
    version_col = version_column(entity)
    document_column = case.model.storage_layout.document(entity.canonical_name).column
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
        golden_set = _golden_set_columns(case, statement)
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
        discriminator = tag(entity)
        if discriminator is not None:
            expected.append(discriminator[1])
        if mode == "optimistic":
            expected.append(observed)  # the optimistic gate bind — always LAST
        assert_write_values(case, expected, binds, statement)


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
    document_column = case.model.storage_layout.document(entity.canonical_name).column
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
        golden_set = _golden_set_columns(case, statement)
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
            assert_write_values(case, expected, binds[: len(expected)], statement)
        return
    _assert_uniform_assignments(case, entity, classified, assignments)
    first_set = classified[0][2] if classified else {}
    expected = expected_values(first_set, assignments[0] if assignments else ())
    binds = step_binds[0] if step_binds else []
    statement = step_statements[0] if step_statements else ""
    assert_write_values(case, expected, binds[: len(expected)], statement)


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
            not write_value_equal(pk, bind) for pk, bind in zip(pk_values, binds, strict=False)
        ):
            raise CaseFailure(
                f"{case.path.name}: the collapsed DELETE binds {binds} MUST equal the "
                f"neutral write input pk value(s) {pk_values} exactly and in order "
                f"(no reorder, duplicate, or extra bind)."
            )
        return
    for binds in step_binds:
        if not any(write_value_equal(pk, bind) for pk in pk_values for bind in binds):
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
    ``end_column = infinity`` alone (:func:`write_plan.close_address_binds`); an ``update``
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
    discriminator = tag(entity)
    document_column = case.model.storage_layout.document(entity.canonical_name).column

    def assert_open(statement: str, binds: list[Any]) -> None:
        golden_columns = parse_insert_columns(case, statement)
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
            else discriminator[1]
            if (discriminator is not None and column == discriminator[0])
            else columns.get(column)
            for column in full_columns
        ]
        if not document_column or len(binds) != len(expected):
            assert_write_values(case, expected, binds, statement)
            return
        # Under Relational Document Layout a chained milestone's Structured Column
        # is the predecessor's own document with the mutation's changes patched
        # into it, so ① fixes the members it names and NOT the whole document: a
        # key no member declares rides forward from the row the successor
        # supersedes, and `then.tableState` is what grades that it did.
        position = full_columns.index(document_column)
        _assert_carried_document(case, expected[position], binds[position], statement)
        assert_write_values(
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
        expected = [at, *close_address_binds(case, entity, pk, None)]
        if has_temporal_gate(statement, transaction_time["start_column"], dialect):
            expected.append(_observed_milestone_start(case, entity, step, pk))
        assert_write_values(case, expected, binds, statement)

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
        ``[at, …address…]`` (:func:`write_plan.close_address_binds`) — the observed rectangle's
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
    if mutation in OPENING_MUTATIONS:
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
            assert_write_values(case, [at], [binds[in_z_pos]], statement)
            assert_write_values(case, [infinity], [binds[out_z_pos]], statement)
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
        expected = [at, *close_address_binds(case, entity, pk, observed.valid_end)]
        gated = has_temporal_gate(statement, in_z, dialect)
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
        assert_write_values(case, expected, binds, statement)

    _assert_split_successor_windows(case, expected_windows, chained_windows)


def _assert_split_successor_windows(
    case: Case,
    expected_windows: list[tuple[Any, Any]],
    chained_windows: list[tuple[Any, Any]],
) -> None:
    """The chained INSERTs' Valid-Time windows are exactly the derived successors."""
    matched = len(expected_windows) == len(chained_windows) and all(
        write_value_equal(want_start, got_start) and write_value_equal(want_end, got_end)
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
        if write_value_equal(row.get(key_member), pk)
        and write_value_equal(row.get(tx_axis.end.name), open_bound)
        and write_value_equal(row.get(valid_axis.start.name), valid_start)
        and write_value_equal(row.get(tx_axis.start.name), tx_start)
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
            classify_write_row(case, entity, row, mutation=prior["mutation"], opening=True)[1]
            for row in prior.get("rows", [])
        ]
        if any(write_value_equal(prior_pk, pk) for prior_pk in prior_keys):
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
            if write_value_equal(row.get(key_member), pk)
            and write_value_equal(row.get(tx_axis.end.name), "infinity")
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
        if prior["mutation"] in OPENING_MUTATIONS:
            opened = _Rectangle(valid_from, infinity if until is None else until, at)
            rectangles = (*rectangles, opened)
            continue
        if len(rectangles) != 1:
            return ()
        rectangles = _split_successors(prior["mutation"], rectangles[0], valid_from, until, at)
    return rectangles


def _conflict_versioned_entity(case: Case) -> Entity | None:
    """The versioned entity a conflict case targets, or None (a temporal close).

    A versioned conflict (``m-opt-lock-005`` through ``m-opt-lock-009``) gates on a
    version column; a temporal / bitemporal close (``m-temporal-read-009`` through
    ``m-temporal-read-012`` / ``m-bitemp-write-004`` / ``m-bitemp-write-005``) has none
    and carries a different ① (see :func:`_assert_temporal_conflict_input`).
    """
    for entity in case.model.entities:
        if version_column(entity) is not None:
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
    version_col = version_column(entity)
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
    _, pk, set_cols, observed = classify_write_row(
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
    gate_rendered = version_col is not None and has_version_gate(statement, version_col, dialect)
    if gate_rendered != gated:
        raise CaseFailure(
            f"{case.path.name}: the golden {mutation.upper()} ({pointer}) "
            f"{'renders' if gate_rendered else 'omits'} the version gate under "
            f"{case.concurrency_mode!r} mode — optimistic mode gates, locking mode does not."
        )
    if gated:
        expected.append(observed)
    assert_write_values(case, expected, binds, statement)


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
    golden_set = _golden_set_columns(case, statement)
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
        if any(key in source for key in MILESTONE_COORDINATE_KEYS)
    ]
    if not observing:
        return
    if entity is None:
        raise CaseFailure(
            f"{case.path.name}: a NON-temporal conflict target has no milestone to observe, "
            f"so it may author neither of {sorted(MILESTONE_COORDINATE_KEYS)} "
            f"({', '.join(observing)})."
        )
    if attempts:
        stranded = sorted(key for key in MILESTONE_COORDINATE_KEYS if key in case.when)
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
    (:func:`write_plan.close_address_binds`); an optimistic close appends the ``and in_z = ?``
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
    _, pk, set_cols, _ = classify_write_row(
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
    expected = [at, *close_address_binds(case, entity, pk, valid_end)]
    gate_rendered = has_temporal_gate(
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
    assert_write_values(case, expected, binds, statements[0])
    assert_inheritance_write_routing(case, entity, statements, [binds], dialect)


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
        if not rows_equal(actual, expected_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: table {table!r} state after the write "
                f"sequence != then.tableState.\n"
                f"  actual:   {actual!r}\n"
                f"  expected: {expected_rows!r}"
            )


# --- scenarios (m-unit-work) ----------------------------------------------------------


def _step_statements(step: dict[str, Any], dialect: str) -> list[str]:
    """The ordered golden SQL statements a scenario step lists for *dialect*."""
    return entry_statements(step.get("statements"), dialect)


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


def _scenario_step_resolving_reads(case: Case, step: dict[str, Any]) -> int:
    """The resolving reads ONE scenario step owes beside the SQL it lists.

    An UNGROUPED write step is its own choreography unit, so it owes what any
    unit owes (:func:`write_plan.unit_resolving_reads`). A GROUPED one owes none of its
    own: its group's find steps are what publish the values it settles against,
    and those finds already declare their own round trips (`m-case-format`
    *Resolving reads a write owes*). A find step owes none either — a read IS
    the SQL it lists.
    """
    if "write" not in step or isinstance(step.get("uow"), str):
        return 0
    return unit_resolving_reads(case, _scenario_write_entries(step))


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
    addresses (:func:`write_plan.statement_object`), never by the order the buffer names
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
            for statement, binds in entry_pairs(step.get("statements"), dialect)
            if is_existing_row_statement(statement)
        ]
        origin = case.scenario[step["on"]]
        aligned: set[int] = set()
        for entry in _scenario_write_entries(step):
            entity = case.model.entity(entry["entity"])
            row = _sole_settled_row(case, index, entity, entry)
            temporal = bool(temporal_axes(entity.runtime_facts))
            _, pk, _set_cols, _observed = classify_write_row(
                case, entity, row, mutation=entry["mutation"], opening=temporal
            )
            statement, binds = _settled_statement(case, index, entity, pk, settling, aligned)
            assert_inheritance_write_routing(case, entity, [statement], [binds], dialect)
            if not temporal:
                _assert_settled_version_binds(
                    case, entity, index, origin, pk, binds, statement, dialect
                )
                continue
            observed = _settled_milestone(case, entity, index, origin, pk)
            expected = [
                entry.get("at"),
                *close_address_binds(case, entity, pk, observed.valid_end),
            ]
            if case.concurrency_mode == "optimistic":
                expected.append(observed.tx_start)
            assert_write_values(case, expected, binds, statement)
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
    settling: Sequence[tuple[ObjectAddress, str, list[Any]]],
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
        if address.names_table(entity.table)
        and address.names_key_column(_pk_column(entity))
        and write_value_equal(address.key, pk)
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


def _statement_object(
    case: Case, index: int, statement: str, binds: list[Any], dialect: str
) -> ObjectAddress:
    """The object a settled scenario step's *statement* addresses.

    A settled write addresses the ONE object it survives as, so a golden here that
    renders no bound key address is a defect of the case rather than a statement
    with nothing to say — which is why the address is required at this step and
    optional to :func:`write_plan.statement_object`.
    """
    address = statement_object(statement, binds, dialect)
    if address is None:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] carries an existing-row golden whose "
            f"predicate does not open with a bound key equality for {dialect}: "
            f"{statement!r} — a settled write addresses the ONE object it survives as, "
            f"and its key leads that address."
        )
    return address


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
    version_col = version_column(entity)
    if version_col is None:
        return
    observed = _settled_generation(case, entity, index, origin, pk, version_col)
    if case.concurrency_mode == "optimistic" and (
        not binds or not write_value_equal(binds[-1], observed)
    ):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles {entity.name} against a find that "
            f"observed version {observed!r}, but its golden gate binds "
            f"{binds[-1] if binds else None!r}."
        )
    assigned = parse_set_columns(statement)
    if assigned is None:
        return
    spelling = quote_identifier(version_col, dialect)
    if spelling not in assigned:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles a versioned {entity.name} update "
            f"whose golden SET clause {assigned} assigns no {spelling!r} — a versioned "
            f"update advances the framework-owned version under either concurrency strategy."
        )
    position = assigned.index(spelling)
    advanced = binds[position] if position < len(binds) else None
    if not write_value_equal(advanced, observed + 1):
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
        if write_value_equal(row.get(key_column), pk)
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
    (:func:`~reference_harness.inheritance.query_position`), so one rule in this
    harness decides whether a read's rows carry a variant — of *origin*'s own query,
    because that is the read whose rows are being interrogated.
    """
    position = query_position(origin.get("objectQuery"), case.model.entity_defs)
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
    discriminator = tag(entity)
    if discriminator is not None and discriminator[0] in row:
        return write_value_equal(row[discriminator[0]], discriminator[1])
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


_ACTION_READ_VERBS = frozenset({"load", "access"})


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


def _is_runner_owned_step(step: Mapping[str, Any]) -> bool:
    """Whether Scenario orchestration, rather than the read oracle, owns *step*.

    "Is this a read step?" gets exactly one implementation by being written as its
    complement: the runner routes the closed set of kinds it owns — a write, an
    action whose verb neither loads nor accesses, and the zero-round-trip
    construction of a query-backed list that has not resolved — and every other
    step is a read the oracle asserts. ``ScenarioReads.assert_step`` reads the same
    classification from the other side and refuses a step it does not own, so a
    disagreement here surfaces as a refusal rather than as a mis-graded step.
    """
    if "write" in step:
        return True
    action = step.get("action")
    if action is not None:
        return action not in _ACTION_READ_VERBS
    return (
        not step.get("statements")
        and "stream" not in step
        and step.get("sameObjectAs") is None
        and step.get("on") is None
    )


def _assert_non_read_action(
    case: Case, index: int, step: dict[str, Any], db: DatabaseProvider, dialect: str
) -> None:
    """Execute a non-read-verb action step's golden DML and refuse any observable.

    A `flush` / `mergeBack` / `commit` commits its buffered statements on the unit
    of work's connection, and a `mutate` / `abort` / `detachCopy` commits whatever
    golden DML it authors (a Valid-Time-past correction's split write); none of
    them observes rows. Identity, state, and error observables on such a step are
    adapter-delegated — validated by the schema, graded by each language's API
    Conformance Suite — so the wire harness runs the DML and nothing else.

    A ROW observable on one of them is refused rather than skipped. Grading it
    would mean reading what an earlier read retained, which is private to the read
    oracle, so a case authoring one is stating an observable this lane cannot
    answer and must fail loudly rather than pass vacuously.
    """
    _assert_no_action_observables(case, index, step)
    assert_step_on_sources(case, index, step)
    for statement, binds in entry_pairs(step.get("statements"), dialect):
        db.execute(statement, binds)


def _assert_no_action_observables(case: Case, index: int, step: Mapping[str, Any]) -> None:
    """Refuse a row observable on a step whose verb observes no rows."""
    declared = [key for key in ("expectRows", "expectGraph", "sameObjectAs") if key in step]
    if declared:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] is a {step['action']!r} action step "
            f"declaring {declared}; only the read verbs {sorted(_ACTION_READ_VERBS)} "
            f"observe rows, so what such a step publishes is nothing to compare."
        )


def _assert_scenario(case: Case, db: DatabaseProvider) -> None:
    """Execute the scenario against the provisioned DB and assert its contract.

    The loop owns the Scenario, not its reads. It resolves each step's `uow`
    grouping, applies write DML and boundary-action DML, closes a group at its own
    last step, and hands every read-bearing step to :class:`ScenarioReads` with the
    reader that step's lifecycle selected — an index and a reader, and nothing
    about delivery, retained state, or read intent.

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

    groups = _scenario_uow_groups(case)
    group_states: dict[str, _UowGroupState] = {
        label: _UowGroupState(doomed=_uow_group_is_doomed(case, indices), last_step=indices[-1])
        for label, indices in groups.items()
    }

    reads = ScenarioReads(case)
    with contextlib.ExitStack() as stack:
        for index, step in enumerate(case.scenario):
            raw_label = step.get("uow")
            label = raw_label if isinstance(raw_label, str) else None
            state = group_states.get(label) if label is not None else None
            session: Any = None
            if state is not None:
                if state.session is None:
                    state.session = stack.enter_context(db.open_session())
                session = state.session

            if not _is_runner_owned_step(step):
                reads.assert_step(index, session if session is not None else db)
            elif "write" in step:
                pairs = entry_pairs(step.get("statements"), dialect)
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
            elif "action" in step:
                # The schema forbids `uow` on an action step (it routes through the
                # lifecycle-object engine path, which never observes grouping), so a
                # boundary action always executes on the provider's autocommit
                # connection rather than on any held session.
                _assert_non_read_action(case, index, step, db, dialect)
            else:
                # A query-backed list that has not resolved: zero round trips, no
                # rows, and no observation until the later step that accesses it
                # resolves its Object Query.
                pass
            _finish_uow_group(case, index, label, group_states, dialect)


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
    version_col = version_column(_scenario_root_entity(case))
    if version_col is None:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] declares a conflict abort but the "
            f"entity carries no optimistic-lock version column to gate on."
        )
    gated = [
        (sql, affected) for sql, affected in executed if has_version_gate(sql, version_col, dialect)
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
    return sorted(coerce_identity_key(row[identity_col]) for row in rows)


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
            if not rows_equal(actual, expected_rows, case.tolerance):
                raise CaseFailure(
                    f"{case.path.name}: table {table!r} state after the conflict "
                    f"case != then.tableState.\n"
                    f"  actual:   {actual!r}\n"
                    f"  expected: {expected_rows!r}"
                )


# --- conflict RETRY cases (m-opt-lock retry contract) ------------------------------


def _attempt_statements(attempt: dict[str, Any], dialect: str) -> list[str]:
    """The golden write statement(s) a retry attempt lists for *dialect*."""
    return entry_statements(attempt.get("statements"), dialect)


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
        if not rows_equal(actual, expected_rows, case.tolerance):
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
                statements.extend(entry_statements(step.get("statements"), dialect))
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
            pairs = entry_pairs(step.get("statements"), dialect) if isinstance(step, dict) else []
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
                statements.extend(entry_statements(step.get("statements"), dialect))
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
    compared via the order-insensitive :func:`case_assertions.rows_equal`, while a ``kind: write``
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
            pairs = entry_pairs(step.get("statements"), dialect) if isinstance(step, dict) else []
            if pairs:
                try:
                    if step.get("kind") == "read":
                        # A read step: fetch on the HELD session (a shared-lock SELECT
                        # takes its lock here) and compare the observed rows.
                        rows: list[dict[str, Any]] = []
                        for sql, binds in pairs:
                            rows = session.query(sql, binds)
                        expect = step.get("expectRows") or []
                        if not rows_equal(rows, expect, tolerance):
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
    return entry_statements(step.get("statements"), dialect)


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
            pairs = entry_pairs(step.get("statements"), dialect)
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
                rows = node.query(statement, binds)
            results.append(rows)

            observe = step.get("observeRows")
            if observe is not None and not rows_equal(rows, observe, tolerance):
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
    assert_case_read(case, db)  # layer 2 + 5 (every accepted Object Query observation)
