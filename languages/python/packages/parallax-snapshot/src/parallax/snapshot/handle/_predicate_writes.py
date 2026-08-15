"""``parallax.snapshot.handle._predicate_writes`` — the predicate-selected (``_where``) write lane.

The set-based half of the spec §5 write surface, as
free functions rather than :class:`~parallax.snapshot.handle.Transaction`
methods: mutation-compatibility, Assignment composition, and Valid-Time-window
validation into a canonical
:class:`~parallax.core.unit_work.PredicateWrite`, the readless-vs-materialize
dispatch, the minimal resolving read, per-row no-op elimination, and
Materialized Write Group buffering.

Every entry point threads ``(uow, meta, conn, dialect)`` — the four pieces of
transaction state this lane actually reads — mirroring
:func:`~parallax.snapshot.handle._write_inputs.retain_evidence`'s own shape.
``meta`` is the accepted Metamodel; family shape comes from the Inheritance,
Temporal, and Optimistic Lock facets through :mod:`parallax.snapshot.handle._family`,
and every physical column comes from the target's Storage Layout view, resolved
once here and carried into the per-row column builders
:func:`_materialize_predicate_write` streams into.
``Transaction`` keeps five thin ``_where`` delegates and the Wire lane keeps its
own five, both routing the instruction they built here, so this module buffers
through ``uow.buffer`` directly and never reaches back into ``Transaction``.

Depends on :mod:`parallax.snapshot.handle._family` (the declaring root, version
attribute, and the layout member-to-column map),
:mod:`parallax.snapshot.handle._write_inputs` (window validation and the per-row
column contributions), and :mod:`parallax.snapshot.handle._read` for both
:func:`~parallax.snapshot.handle._read.execute_read` and
:func:`~parallax.snapshot.handle._read.stage_publishable_rows` — the resolving
read records its Database Call through the package's one read-call seam, then
passes its materialized rows through the shared publication gate before this
lane derives observations or writes.

Names crossing a module boundary are spelled bare; a helper whose every caller
lives here keeps its underscore. Privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, never by per-name
underscores.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any, Final, cast

from parallax.core import deep_fetch, inheritance
from parallax.core import predicate as predicate_algebra
from parallax.core.db_port import DbPort, Row
from parallax.core.dialect import Dialect, LockMode
from parallax.core.entity import AttributeAssignment
from parallax.core.execution_log import AttemptRecorder
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    TemporalDimension,
    entity_by_name,
)
from parallax.core.object_query import (
    AsOf,
    ObjectQueryNode,
    TemporalSelection,
    object_query,
)
from parallax.core.object_query import TemporalDimension as TemporalDimensionName
from parallax.core.object_query._fluent import ObjectQuery, mutation_selection
from parallax.core.predicate import PredicateNode, QueryDefinitionError
from parallax.core.sql_gen import compile_read
from parallax.core.storage_layout import DocumentPath
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    SELECTION_INTENT,
    ChunkedColumnBuilder,
    MaterializedWriteGroup,
    ObjectKey,
    ObservedStateKey,
    PredecessorColumns,
    PredecessorRow,
    PredecessorShape,
    PredicateMutation,
    PredicateWrite,
    TemporalColumns,
    TemporalObservation,
    UnitOfWork,
    VersionColumns,
    VersionObservation,
    WriteObservation,
    WriteRejectedError,
    instructions,
    observed_state_key,
    whole,
)
from parallax.core.unit_work.write_planner import assigned_many_path
from parallax.snapshot.handle._family import (
    assignment_member,
    declaring,
    entity_layout,
    entity_of,
    family_primary_key,
    members,
    placed_members,
    slot_column,
    version_attribute,
)
from parallax.snapshot.handle._read import (
    entity_read_lock,
    execute_read,
    stage_publishable_rows,
)
from parallax.snapshot.handle._write_inputs import (
    is_no_op_assignment,
    key_column_values,
    normalize_assignment_values,
    predecessor_payload,
    validate_window,
)
from parallax.snapshot.materialize import observable_columns

# The predicate mutations that carry Assignments; the rest take none at all and
# their verbs' signatures say so.
_ASSIGNMENT_BEARING: Final[frozenset[PredicateMutation]] = frozenset({"update", "updateUntil"})


def _current_selection(
    target: EntityIdentity, predicate: PredicateNode, entity: EntityMetadata
) -> ObjectQueryNode:
    """The internal resolving query: the write's own predicate, pinned at Latest
    on every declared dimension."""
    temporal: dict[TemporalDimensionName, TemporalSelection] = {
        (
            "valid-time" if axis.dimension is TemporalDimension.VALID_TIME else "transaction-time"
        ): AsOf(coordinate="latest")
        for axis in entity.declared_as_of_axes
    }
    return object_query(target, predicate, temporal=temporal)


def buffer_predicate(
    uow: UnitOfWork,
    meta: Metamodel,
    conn: DbPort,
    dialect: Dialect,
    mutation: PredicateMutation,
    query: ObjectQuery[Any, Any],
    assignments: Sequence[AttributeAssignment[Any]],
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None = None,
    attempt: AttemptRecorder,
) -> None:
    """The typed-authoring entry to the predicate-write lane: it turns a
    mutation-compatible :class:`~parallax.core.object_query.ObjectQuery` plus typed
    ``Attr.set(...)`` assignments into the canonical
    :class:`~parallax.core.unit_work.PredicateWrite` the conformance engine
    builds directly from a case document, then hands it to the shared
    :func:`buffer_predicate_instruction` seam.

    Steps 1, 2, and 4 are TYPED-ONLY — they judge inputs the canonical
    instruction has no way to carry (a query's clauses, an Assignment list
    composed against a query, a ``dt.datetime`` bound). Every rule that measures
    the INSTRUCTION itself is stated in ``validate_instruction`` (step 5), which
    the conformance engine calls too, so the two ingresses classify one
    instruction identically.

    1. **Mutation compatibility** (`python.md` §5 "A query becomes a write
       target only in its mutation-compatible form") — one carrying nothing but
       a target and a predicate; every result-shaping, temporal, narrowing, and
       deep-fetch clause is rejected
       (:func:`~parallax.core.object_query.mutation_selection`,
       ``query-not-mutation-compatible``). Typed-only: it has no
       instruction-level counterpart, because the canonical instruction carries a
       :class:`PredicateNode` and no clause has a spelling there to refuse. What
       it answers is the ephemeral Predicate Selection the rest of this function
       reads, which never leaves this lane.
    2. **Target resolution** — the write-side spelling of a read's preflight
       (:func:`entity_of`, ``query-target-not-in-model``): an Object Query the
       connected model declares no Entity for is refused as a query, before
       anything is built from it. The query retains its Entity Identity, so the
       lookup is by exact spelling rather than by a bare name two namespaces
       could share.
    3. **Assignment-list and exact-target composition** — an assignment-bearing
       mutation needs at least one Assignment, no two naming one member, and
       every one addressing the query's exact target Entity
       (``query-assignment-target-mismatch``). Typed-only: only this ingress
       COMPOSES independently authored Assignments with a query, and it is
       refused before anything is built from either. It follows target resolution
       because the exact-target rule resolves each Assignment's Entity spelling
       against the connected model, so a query whose own target that model does
       not declare is named as the target failure it is rather than as a
       composition failure of every Assignment addressing it.
    4. **Valid-Time-bound validation and rendering** — the ``*Until`` forms
       state their window as a PAIR, and half of one is refused before either
       bound is measured; a Bitemporal target then requires ``valid_from`` and a
       Transaction-Time-Only or non-temporal target takes none; and
       ``valid_from < until`` — an equal or reversed window rejects HERE, at
       build, before any buffering (:func:`validate_window`, the one gate the
       keyed verbs and both representations run). Typed-only: only
       this ingress takes ``dt.datetime`` arguments, and this step is the sole
       place one is touched — the gate normalizes each bound to UTC and RETURNS
       the canonical instant literal step 5 writes into the instruction. It runs
       BEFORE that build so a :class:`~parallax.core.unit_work.PredicateWrite`
       is canonical from the moment it exists: a bound slot only ever holds
       what `write-instruction.schema.json` defines an instant to be — an
       ISO-8601 UTC timestamp, or the open-bound sentinel — so nothing
       downstream of this lane, the buffering seam and the planner and SQL
       generation alike, has to defend against anything else.
    5. **Build + validate the canonical instruction** (the SAME
       deserialize/`validate_instruction` round trip a keyed write buys in
       ``Transaction._buffer``). ``validate_instruction`` measures the selecting
       predicate with the whole ``validate_predicate`` vocabulary, then rejects
       an inheritance-family target, then the assignments — so an inverted
       ``between`` window, an attribute outside the active position, or a
       set-based family write is refused here, at build, before every buffer and
       before the resolving read's own force-flush.
    6. **Hand off** to :func:`buffer_predicate_instruction`, which dispatches
       READLESS (one statement, `m-batch-write`) or MATERIALIZING
       (``_materialize_predicate_write``, ADR 0014).

    Steps 4 and 5 both refuse a write, so a call carrying an invalid bound AND
    an invalid predicate classifies by its bound. Either refusal is correct;
    only which one surfaces first is fixed here, and it is fixed in favour of
    never constructing a non-canonical instruction.
    """
    selection = mutation_selection(query)
    entity = entity_of(meta, selection.target.canonical)
    _reject_uncomposable_assignments(meta, selection.target, mutation, assignments)
    declaring_entity = declaring(meta, entity)
    valid_from_literal, until_literal = validate_window(
        declaring_entity, mutation, valid_from, until
    )
    doc: dict[str, object] = {
        "mutation": mutation,
        "target": {
            "entity": selection.target.canonical,
            "predicate": predicate_algebra.serialize(selection.predicate),
        },
    }
    if assignments:
        doc["assignments"] = [{"attr": str(a.attr), "value": a.value} for a in assignments]
    if valid_from_literal is not None:
        doc["validFrom"] = valid_from_literal
    if until_literal is not None:
        doc["until"] = until_literal
    instruction = instructions.deserialize(doc)
    assert isinstance(instruction, PredicateWrite)  # this seam always builds the predicate shape
    instructions.validate_instruction(instruction, meta)
    buffer_predicate_instruction(uow, meta, conn, dialect, instruction, attempt)


def _reject_uncomposable_assignments(
    meta: Metamodel,
    target: EntityIdentity,
    mutation: PredicateMutation,
    assignments: Sequence[AttributeAssignment[Any]],
) -> None:
    """Refuse an Assignment list that does not compose with ``target``.

    An Assignment is already valid on its own — ``.set(...)`` judged it against
    the member it was built from — so what is left is whether the list and the
    query compose: an assignment-bearing mutation assigns something, assigns each
    member once, and assigns only members of the position it writes. The last is
    the exact-target rule: a set-based write names one Entity, and an Assignment
    built through an ancestor addresses that ancestor's position rather than this
    one. Ancestry never rescues it, because a set-based write over an inheritance
    family is unsupported outright — which the canonical instruction's own
    validation states, one step later and for both ingresses.

    The exact-target rule compares IDENTITIES: an Assignment's Entity spelling is
    resolved against ``meta`` before it is measured, so a canonical spelling names
    the Entity it denotes while a bare one two namespaces share resolves nowhere
    and is refused rather than silently matched against the target's local name.

    Delete and terminate forms take no Assignments at all, which their signatures
    already state; the emptiness rule is therefore asked only of the mutations
    that carry them.
    """
    if mutation in _ASSIGNMENT_BEARING and not assignments:
        raise QueryDefinitionError(
            code="query-assignment-target-mismatch",
            message=f"a predicate-selected {mutation} requires at least one assignment",
        )
    seen: set[str] = set()
    for assignment in assignments:
        ref = assignment.attr
        owner = entity_by_name(meta, ref.entity)
        if owner is None or owner.identity != target:
            raise QueryDefinitionError(
                code="query-assignment-target-mismatch",
                message=(
                    f"{ref}: a predicate-selected write assigns members of its exact target "
                    f"{target.canonical}, and this assignment addresses {ref.entity}"
                ),
            )
        if ref.attribute in seen:
            raise QueryDefinitionError(
                code="query-assignment-target-mismatch",
                message=f"{ref}: assigned twice in one predicate-selected write",
            )
        seen.add(ref.attribute)


def buffer_predicate_instruction(
    uow: UnitOfWork,
    meta: Metamodel,
    conn: DbPort,
    dialect: Dialect,
    instruction: PredicateWrite,
    attempt: AttemptRecorder,
) -> None:
    """The neutral seam UNDERLYING every ``_where`` verb and the
    conformance engine's own predicate-write translation (`m-case-format`
    "predicate-shaped case entries deserialize
    to PredicateWrite through the existing serde and buffer through
    Transaction's own seam"): given an ALREADY-BUILT
    :class:`~parallax.core.unit_work.PredicateWrite` instruction, reject an
    inheritance-family target (`m-inheritance`), then dispatch it READLESS
    (`m-batch-write`) or MATERIALIZE it (`m-opt-lock`, ADR 0014). The typed
    ``_where`` verbs (:func:`buffer_predicate`) build ``instruction`` from
    a mutation-compatible :class:`~parallax.core.object_query.ObjectQuery` plus typed
    ``Attr.set(...)`` assignments first; the engine builds it directly
    from the case's own canonical write-instruction document.

    **Every caller passes ``instruction`` through
    :func:`~parallax.core.unit_work.instructions.validate_instruction` against
    ``meta`` first** — :func:`buffer_predicate` at its step 5 for the typed
    ``_where`` verbs, and
    :func:`~parallax.snapshot.handle._wire_writes.wire_predicate_write` for the
    Wire ones, the conformance engine included. EVERY
    model-aware rule is stated there, in the
    order `m-case-format` fixes: the whole ``validate_predicate`` vocabulary
    over the selecting predicate, the
    inheritance-family rejection, member-name honesty and assignability, then
    the one target-profile quadrant that validator enforces — a milestone verb
    aimed at a target deriving no As-Of Axis, and no other pairing of profile
    against verb or bound. That call establishes the CALLER ORDERING — one
    classification whichever ingress an instruction arrives through.

    The two refusals repeated here — an inheritance-family target, and that same
    milestone-verb quadrant — are this seam's OWN contract, not duplicates of
    those rules. This entry point is reachable in-package without going through
    an ingress, so it takes nothing on faith: without its own refusal an
    unvalidated instruction reaches
    :func:`_materialize_predicate_write`'s resolving read — real SQL on the
    caller's connection — and, when that read matches no row, buffers nothing
    for the flush-time
    :mod:`~parallax.core.unit_work.write_planner` to refuse, so nothing refuses
    it at all. The planner's own structural refusal is the last line before SQL
    for what IS buffered; this one is the first line before the resolve.

    The Wire ``_where`` verbs route their instruction here too, so a caller
    holding no Entity Class reaches this seam exactly as a typed caller does.
    """
    entity = entity_of(meta, instruction.target.entity)
    inheritance.reject_predicate_write(entity)
    declaring_entity = declaring(meta, entity)
    version_attr = version_attribute(meta, declaring_entity)
    is_temporal = bool(declaring_entity.declared_as_of_axes)
    if not is_temporal:
        refusal = instructions.non_temporal_milestone_refusal(
            entity.identity.name, instruction.mutation
        )
        if refusal is not None:
            raise instructions.WriteInstructionError(refusal)
    if not is_temporal and version_attr is None:
        # Readless (`m-batch-write.md` "Predicate-selected readless forms"):
        # one statement, no materialization, no equality-elimination pass.
        _reject_readless_document_many(meta, entity, instruction)
        uow.buffer(instruction)
        return
    _materialize_predicate_write(
        uow, meta, conn, dialect, instruction, entity, declaring_entity, version_attr, attempt
    )


def _reject_readless_document_many(
    meta: Metamodel, entity: EntityMetadata, instruction: PredicateWrite
) -> None:
    layout = entity_layout(meta, entity)
    if layout is None:  # pragma: no cover - accepted entities always have a layout view
        return
    by_name = {
        occurrence.identity.path[-1]: occurrence for occurrence in entity.declared_value_objects
    }
    assigned = {assignment_member(assignment.attr) for assignment in instruction.assignments}
    for name in assigned:
        occurrence = by_name.get(name)
        if occurrence is None:
            continue
        placement = layout.layout.placement(occurrence.identity)
        assignment = next(
            item for item in instruction.assignments if assignment_member(item.attr) == name
        )
        nested_many = assigned_many_path(occurrence, assignment.value)
        if isinstance(placement, DocumentPath) and (
            occurrence.multiplicity is Multiplicity.MANY or nested_many is not None
        ):
            path = name if nested_many is None else ".".join((name, *nested_many))
            raise WriteRejectedError(
                "predicate-write-readless-document-many-unsupported",
                f"{entity.identity.canonical}.{path}: a readless predicate write cannot assign "
                "a document-resident `many` occurrence",
            )


def _materialize_predicate_write(
    uow: UnitOfWork,
    meta: Metamodel,
    conn: DbPort,
    dialect: Dialect,
    instruction: PredicateWrite,
    entity: EntityMetadata,
    declaring_entity: EntityMetadata,
    version_attr: AttributeMetadata | None,
    attempt: AttemptRecorder,
) -> None:
    """Materialize a predicate write on a VERSIONED or TEMPORAL target
    (`m-opt-lock` "Predicate-selected writes materialize when observations
    are needed"; ADR 0014): resolve the predicate through a MINIMAL
    row-form read on THIS transaction's own connection (never instance-form
    — the resolve constructs no object, though it projects whichever Document
    slots the write's own observation and comparison needs require, below),
    then stream each matched row's key and observation values directly into
    bounded column builders — never a per-row keyed-write wrapper, never a
    parallel pending-observation list — and buffer the sealed result as one
    compact :class:`~parallax.core.unit_work.MaterializedWriteGroup` (`m-unit-
    work` "Materialized Write Groups") at the call position. Zero resolved
    rows, or every resolved row eliminated as a no-op, means no group is
    buffered at all. The lock suffix on the resolve derives from the TARGET
    Entity's Effective Concurrency Strategy — this transaction's Concurrency
    Preference resolved against that Entity's own Optimistic Lock Facet —
    through the SAME seam a real ``Transaction.find`` derives it. Reaching here
    means the target is versioned or temporal, so it is the preference alone
    that decides: the default resolves the target to Optimistic and the resolve
    takes no lock.

    A TEMPORAL target's raw predicate carries no as-of term (a
    mutation-compatible Object Query carries no temporal clause, python.md §5),
    so this internal authoring boundary adds one explicit Latest selection per
    declared dimension before routing the resolve through the SAME
    :func:`~parallax.core.deep_fetch.plan` root-canonicalization every
    other read uses (:func:`~parallax.snapshot.handle.find`) rather than
    compiling the raw predicate directly — otherwise a temporal target's
    resolve would match every historical milestone too, not just the open
    one(s).
    """
    layout = entity_layout(meta, entity)
    if layout is None:  # pragma: no cover - a predicate-write target always owns rows
        raise ValueError(f"{entity.identity.canonical}: predicate-write target has no Table")
    lock: LockMode | None = entity_read_lock(meta, entity.identity, uow.settings.concurrency)
    selection = _current_selection(entity.identity, instruction.target.predicate, declaring_entity)
    plan_ = deep_fetch.plan(entity, selection, meta)
    assignments = {
        assignment_member(assignment.attr): assignment.value
        for assignment in instruction.assignments
    }
    is_temporal = bool(declaring_entity.declared_as_of_axes)
    # Need-sensitive projection (`m-case-format` "Predicate-selected write
    # instruction"): the resolving read projects the resolved row's own
    # value-object document(s) for TWO independent needs, on EVERY target
    # class — never gated on temporality alone.
    #
    # OBSERVATION need: a TEMPORAL target's per-row observation retains the
    # whole predecessor milestone (`m-unit-work` "A Predecessor Row is the
    # complete, immutable persisted state a Temporal Observation retains"),
    # so its resolving read projects EVERY declared document whatever the
    # verb goes on to do with it. Completeness belongs to the OBSERVATION,
    # not to the topology a verb happens to produce: a decorator must
    # distinguish carried from changed state without a second read (ADR
    # 0042), so a close-only shape — an AUDIT-ONLY `terminate`, which chains
    # nothing — records the same complete predecessor a chain-bearing one
    # does. This subsumes the carry-forward need: a BITEMPORAL rectangle
    # split (`bitemp_write.plan`) carries the old payload into its head and
    # tail on EVERY close-bearing mutation, and an AUDIT-ONLY `update`
    # (`txtime_write.plan`) carries it into its chained row. It is also why
    # EVERY declared document is projected rather than only the assigned
    # ones — a carried row must keep whichever documents the assignments do
    # NOT themselves reassign. Every target's carried state reads through the
    # SAME Predecessor Row (`predecessor_payload`, below); there is no
    # separate audit-only merge.
    #
    # COMPARISON need: an assignment-bearing verb's per-row no-op
    # elimination (below, `is_no_op_assignment`)
    # compares each assigned member's new value against the resolved
    # row's own — a value-object member's comparison can only ever see
    # the managed occurrence decoded from storage when this read actually
    # projected its column
    # (`m-opt-lock` "when all assignments already equal that row's values,
    # it issues no DML, advances no version"). A VERSIONED NON-TEMPORAL
    # target reaches this need ALONE: it retains only the observed version,
    # never a predecessor row (`m-opt-lock`/`m-descriptor`: versioned and
    # temporal are mutually exclusive). Minimal-read discipline (`m-sql`)
    # then projects the ASSIGNED value-object document(s) only — never every
    # declared one, matching an ordinary read's own need-driven projection.
    assignment_bearing = instruction.mutation in _ASSIGNMENT_BEARING
    predecessor_need = version_attr is None and is_temporal
    member_columns = members(placed_members(meta, entity, layout))
    occurrences = {
        occurrence.identity.path[-1]: occurrence for occurrence in entity.declared_value_objects
    }
    comparison_assignments = normalize_assignment_values(assignments, occurrences)
    needs_documents: bool | frozenset[str]
    if predecessor_need:
        needs_documents = True
    elif assignment_bearing:
        needs_documents = frozenset(member for member in assignments if member_columns[member][1])
    else:
        needs_documents = False
    # A materializing predicate write's resolving read is row-form over a
    # non-family target (a family predicate write is rejected before SQL), so
    # its compiled row transform is the identity under `Columns` layout. Under
    # Relational Document Layout it is the document fan-out instead, and every
    # per-row helper below reads a member by name, so each driver row is
    # materialized here rather than consumed raw. Materializing is what answers
    # BOTH needs at once: the fan-out drops the raw Structured Column it decoded
    # from, and the materialized row carries that document beside its values, so
    # a temporal target's Predecessor Row retains it (`m-unit-work`) — which is
    # what lets a successor be patched from the document the row actually held —
    # without a second extraction that could disagree with the first.
    compiled = compile_read(
        plan_.root,
        meta,
        dialect,
        result_form="row",
        lock=lock,
        include_value_objects=needs_documents,
    )
    structured_column = compiled.structured_column
    # The resolving read reaches the database, so it is bracketed and recorded
    # like any other read (`m-execution-log`) — through the package's one
    # read-call seam, never a second copy of its rules.
    with attempt.read_trace() as recorder:
        driver_rows = uow.read(
            lambda: execute_read(
                conn,
                dialect,
                compiled.statement,
                recorder,
                document_reads=compiled.document_reads,
            )
        )
    stage = stage_publishable_rows(meta, compiled, driver_rows, pin=Pin())
    resolved = stage.rows
    if not resolved:
        return
    contexts = stage.contexts
    rows = [
        observable_columns(
            materialized.values,
            context,
            classified_members=materialized.classified_members,
        )
        for materialized, context in zip(resolved, contexts, strict=True)
    ]
    pk_attrs = family_primary_key(meta, entity)
    key_attributes = tuple(attr.identity.name for attr in pk_attrs)
    key_builders = tuple(ChunkedColumnBuilder[object]() for _ in pk_attrs)
    matched = 0

    def append_key(row: Row) -> None:
        for builder, value in zip(
            key_builders, key_column_values(pk_attrs, layout, row), strict=True
        ):
            builder.append(value)

    declaring_entity = declaring(meta, entity)
    selected: list[ObservedStateKey] = []

    def select_state(row: Row, observation: WriteObservation) -> None:
        keys = zip(key_attributes, key_column_values(pk_attrs, layout, row), strict=True)
        object_key = ObjectKey(entity.identity, tuple(keys))
        selected.append(observed_state_key(object_key, observation, declaring_entity))

    if version_attr is not None:
        version_builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
        for row in rows:
            if assignment_bearing and is_no_op_assignment(
                member_columns, comparison_assignments, row, occurrences
            ):
                continue  # per-row no-op elimination (assignment-bearing verbs only)
            append_key(row)
            version = cast("int", row[slot_column(layout, version_attr.identity)])
            version_builder.append(version)
            select_state(row, VersionObservation(observed_version=version))
            matched += 1
        if matched == 0:
            return
        uow.buffer(
            MaterializedWriteGroup(
                mutation=instruction,
                key_attributes=key_attributes,
                key_columns=tuple(whole(builder.build()) for builder in key_builders),
                observations=VersionColumns(versions=whole(version_builder.build())),
            )
        )
        _claim_selected_states(uow, selected)
        return

    attribute_names = tuple(name for name, (_column, is_vo) in member_columns.items() if not is_vo)
    value_object_names = tuple(name for name, (_column, is_vo) in member_columns.items() if is_vo)
    attribute_builders = {name: ChunkedColumnBuilder[object]() for name in attribute_names}
    value_object_builders = {name: ChunkedColumnBuilder[object]() for name in value_object_names}
    document_builder: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    for materialized, row in zip(resolved, rows, strict=True):
        if assignment_bearing and is_no_op_assignment(
            member_columns, comparison_assignments, row, occurrences
        ):
            continue  # per-row no-op elimination (assignment-bearing verbs only)
        append_key(row)
        payload = predecessor_payload(member_columns, row)
        for name in attribute_names:
            attribute_builders[name].append(payload[name])
        for name in value_object_names:
            value_object_builders[name].append(payload[name])
        if structured_column is not None:
            document_builder.append(materialized.document)
        select_state(row, TemporalObservation(predecessor=PredecessorRow(payload)))
        matched += 1
    if matched == 0:
        return
    predecessors = PredecessorColumns(
        shape=PredecessorShape(attributes=attribute_names, value_objects=value_object_names),
        attribute_columns=tuple(
            whole(attribute_builders[name].build()) for name in attribute_names
        ),
        value_object_columns=tuple(
            whole(value_object_builders[name].build()) for name in value_object_names
        ),
        documents=None if structured_column is None else whole(document_builder.build()),
    )
    uow.buffer(
        MaterializedWriteGroup(
            mutation=instruction,
            key_attributes=key_attributes,
            key_columns=tuple(whole(builder.build()) for builder in key_builders),
            observations=TemporalColumns(predecessors=predecessors),
        )
    )
    _claim_selected_states(uow, selected)


def _claim_selected_states(uow: UnitOfWork, selected: Sequence[ObservedStateKey]) -> None:
    """Register the group's claim on every state its predicate resolved
    (`m-unit-work` "Observed-State Coalescing").

    A Materialized Write Group owns those observations outright: it is one
    compact indivisible unit, so a later keyed write of a state it selected has
    nothing to join and is refused rather than merged in — which would mean
    indexing and mutating the group. The reverse order needs no claim at all,
    because the resolving read force-flushes the buffer first and therefore
    selects state no pending intent still holds.
    """
    for state in selected:
        uow.claim(state, SELECTION_INTENT)
