from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from parallax.core import deep_fetch, inheritance
from parallax.core.db_port import DatabaseConnection
from parallax.core.dialect import LockMode
from parallax.core.document_codec import (
    MemberShape,
    PreparedEffectiveChange,
    prepare_effective_change,
)
from parallax.core.entity import AttributeAssignment
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import TransactionAttemptActivity
from parallax.core.inheritance import EntityMemberSelection
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    entity_by_name,
)
from parallax.core.object_query._fluent import ObjectQuery, mutation_selection
from parallax.core.object_query._validated import latest_temporal_selections
from parallax.core.predicate import QueryDefinitionError
from parallax.core.sql_gen._compile import compile_read
from parallax.core.temporal_read import NonTemporal, Pin, TemporalShape
from parallax.core.unit_work import (
    SELECTION_INTENT,
    ChunkedColumnBuilder,
    EntityStateRow,
    MaterializedWriteGroup,
    ObjectKey,
    ObservedStateKey,
    PredecessorColumns,
    PredecessorRow,
    PredecessorShape,
    PredicateMutation,
    PredicateSelection,
    PredicateWrite,
    TemporalColumns,
    TemporalObservation,
    UnitOfWork,
    VersionColumns,
    VersionObservation,
    WriteAssignment,
    instructions,
    observed_state_key,
    whole,
)
from parallax.core.unit_work.instructions import (
    PreparedPredicateWrite,
)
from parallax.core.unit_work.write_settlement import reject_readless_document_many
from parallax.snapshot.handle._concurrency import CONCURRENCY
from parallax.snapshot.handle._family import (
    assignment_member,
    entity_layout,
    entity_of,
    family_view,
    temporal_shape,
)
from parallax.snapshot.handle._materialization import FlatPageRead, Materializer, RowPublication
from parallax.snapshot.handle._read import entity_read_lock, execute_read
from parallax.snapshot.handle._write_inputs import reject_temporal_delete, validate_window
from parallax.snapshot.materialize import Page, RootView, require_publishable
from parallax.snapshot.materialize._page import ABSENT

# The predicate mutations that carry Assignments; the rest take none at all and
# their verbs' signatures say so.
_ASSIGNMENT_BEARING: Final[frozenset[PredicateMutation]] = frozenset({"update", "updateUntil"})


def buffer_predicate(
    uow: UnitOfWork,
    model: CatalogedModel,
    conn: DatabaseConnection,
    mutation: PredicateMutation,
    query: ObjectQuery[Any, Any],
    assignments: Sequence[AttributeAssignment[Any]],
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None = None,
    attempt: TransactionAttemptActivity,
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
    the INSTRUCTION itself is stated by the prepared-write producers (step 5),
    so the two ingresses classify one instruction identically.

    1. **Mutation compatibility** (the Python binding "A query becomes a write
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
    4. **The bound-less destructive verb's applicability, then Valid-Time-bound
       validation and normalization** — ``delete_where`` offers no bound ARGUMENT
       at all, so a temporal target refuses the VERB before any bound is measured
       (:func:`~parallax.snapshot.handle._write_inputs.reject_temporal_delete`).
       Every other verb takes one, and the
       window gate judges what the call passed: the ``*Until`` forms state their
       window as a PAIR,
       and half of one is refused before either bound is measured; a Bitemporal
       target then requires ``valid_from`` and a Transaction-Time-Only or
       non-temporal target takes none; and ``valid_from < until`` — an equal or
       reversed window rejects HERE, at build, before any buffering
       (:func:`validate_window`, the one gate the keyed verbs and both
       representations run). The window half is typed-only: only this ingress
       takes ``dt.datetime`` arguments. The gate normalizes each bound to the
       managed UTC carrier retained by the prepared product; canonical text
       belongs only to serialized Wire output.
    5. **Build + prepare the canonical instruction** (the typed peer of the
       Wire ingress's ``prepare_wire_write`` path). ``prepare_typed_write`` measures the selecting
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
    meta = model.meta
    selection = mutation_selection(query)
    entity = entity_of(meta, selection.target.canonical)
    _reject_uncomposable_assignments(meta, selection.target, mutation, assignments)
    shape = temporal_shape(meta, entity)
    reject_temporal_delete(entity, shape, mutation, surface="predicate")
    valid_from_managed, until_managed = validate_window(
        family_view(meta, entity).root, shape, mutation, valid_from, until
    )
    instruction = PredicateWrite(
        mutation,
        PredicateSelection(selection.target.canonical, selection.predicate),
        tuple(
            WriteAssignment(str(assignment.attr), assignment.value) for assignment in assignments
        ),
        valid_from_managed,
        until_managed,
    )
    prepared = instructions.prepare_typed_write(instruction, meta)
    assert isinstance(prepared, PreparedPredicateWrite)
    buffer_predicate_instruction(uow, model, conn, prepared, attempt)


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
    model: CatalogedModel,
    conn: DatabaseConnection,
    instruction: PreparedPredicateWrite,
    attempt: TransactionAttemptActivity,
) -> None:
    """The neutral seam UNDERLYING every ``_where`` verb and the
    conformance engine's own predicate-write translation (`m-case-format`
    "predicate-shaped case entries deserialize
    to PredicateWrite through the existing serde and buffer through
    Transaction's own seam"): given an ALREADY-PREPARED
    :class:`~parallax.core.unit_work.PreparedPredicateWrite` product, reject an
    inheritance-family target (`m-inheritance`), then dispatch it READLESS
    (`m-batch-write`) or MATERIALIZE it (`m-opt-lock`, ADR 0014). The typed
    ``_where`` verbs (:func:`buffer_predicate`) build an authored instruction from
    a mutation-compatible :class:`~parallax.core.object_query.ObjectQuery` plus typed
    ``Attr.set(...)`` assignments first; the engine deserializes one from the
    case document. Both pass that authored value through the producer before this
    seam receives it.

    **Every caller passes its authored instruction through the corresponding
    prepared-write producer against ``meta`` first** —
    :func:`~parallax.core.unit_work.instructions.prepare_typed_write` for the
    typed ``_where`` verbs, and
    :func:`~parallax.core.unit_work.instructions.prepare_wire_write` for the
    Wire ones, the conformance engine included. Nearly every
    model-aware rule is stated there, in the
    order `m-case-format` fixes: the whole ``validate_predicate`` vocabulary
    over the selecting predicate, the
    inheritance-family rejection, member-name honesty and assignability, then
    the one target-profile quadrant that validator enforces — a milestone verb
    aimed at a target deriving no As-Of Axis, and no other pairing of profile
    against verb or bound. That call establishes the CALLER ORDERING — one
    classification whichever ingress an instruction arrives through.

    Target/verb applicability is settled HERE, both converse halves of it, so a
    ``_where`` verb a target does not take is refused at the verb whatever the
    target's profile: a milestone verb aimed at a target deriving no As-Of Axis,
    and ``delete_where`` aimed at one that does, which physically removes the
    rows a temporal target milestones and is spelled ``terminate_where`` there.
    The validator states only the first, so the second is this seam's alone;
    without it a temporal ``delete_where`` would run its resolving read and hear
    the flush's own planning refusal instead of a verb's. Each ``_where`` ingress
    settles that second half earlier still
    (:func:`~parallax.snapshot.handle._write_inputs.reject_temporal_delete`),
    ahead of the window gate a bound-less verb has no bound for.

    The refusals repeated here — an inheritance-family target, and that same
    milestone-verb quadrant — are this seam's OWN contract, not duplicates of
    those rules. Only the temporal-``delete`` half of that quadrant is reachable
    through an instruction anything can currently produce, because the producer
    above refuses the milestone pairing before a prepared product naming it
    exists; the milestone half stands because what this seam judges is its INPUT
    rather than its producer, and both halves are one judgement of one quadrant.
    This entry point is reachable in-package without going through
    an ingress, so it takes nothing on faith: without its own refusal an
    unvalidated instruction reaches
    :func:`_materialize_predicate_write`'s resolving read — real SQL on the
    caller's connection — and, when that read matches no row, buffers nothing
    for the flush-time
    :mod:`~parallax.core.unit_work.write_settlement` to refuse, so nothing refuses
    it at all. The planner's own structural refusal is the last line before SQL
    for what IS buffered; this one is the first line before the resolve.

    The Wire ``_where`` verbs route their instruction here too, so a caller
    holding no Entity Class reaches this seam exactly as a typed caller does.
    """
    meta = model.meta
    entity = instruction.selection.target
    assert entity is not None
    inheritance.reject_predicate_write(entity)
    shape = temporal_shape(meta, entity)
    version_attr = CONCURRENCY.version_attribute(meta, entity.identity)
    temporal = not isinstance(shape, NonTemporal)
    applicability = (
        instructions.temporal_delete_refusal(
            entity.identity.name, instruction.mutation, surface="predicate"
        )
        if temporal
        else instructions.non_temporal_milestone_refusal(
            entity.identity.name, instruction.mutation, surface="predicate"
        )
    )
    if applicability is not None:
        raise instructions.WriteInstructionError(applicability)
    if not temporal and version_attr is None:
        # Readless (`m-batch-write.md` "Predicate-selected readless forms"):
        # one statement, no materialization, no equality-elimination pass.
        reject_readless_document_many(entity, instruction)
        uow.buffer(instruction)
        return
    _materialize_predicate_write(
        uow,
        model,
        conn,
        instruction,
        entity,
        shape,
        version_attr,
        attempt,
    )


def _materialize_predicate_write(
    uow: UnitOfWork,
    model: CatalogedModel,
    conn: DatabaseConnection,
    instruction: PreparedPredicateWrite,
    entity: EntityMetadata,
    family_shape: TemporalShape,
    version_attr: AttributeIdentity | None,
    attempt: TransactionAttemptActivity,
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
    mutation-compatible Object Query carries no temporal clause),
    so this internal authoring boundary adds one explicit Latest selection per
    declared dimension before routing the resolve through the SAME
    :func:`~parallax.core.deep_fetch.plan` root-canonicalization every
    other read uses (:func:`~parallax.snapshot.handle.find`) rather than
    compiling the raw predicate directly — otherwise a temporal target's
    resolve would match every historical milestone too, not just the open
    one(s).
    """
    meta = model.meta
    layout = entity_layout(meta, entity)
    if layout is None:  # pragma: no cover - a predicate-write target always owns rows
        raise ValueError(f"{entity.identity.canonical}: predicate-write target has no Table")
    lock: LockMode | None = entity_read_lock(meta, entity.identity, uow.settings.concurrency)
    root = inheritance.root_metadata(inheritance.view(meta), meta, entity.identity)
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
    # NOT themselves reassign. Every target's carried state is the resolved
    # row itself, streamed whole into the group's Predecessor Columns (below);
    # there is no separate audit-only merge.
    #
    # COMPARISON need: an assignment-bearing verb's per-row no-op
    # elimination (the codec's prepared effective-change comparison, below)
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
    predecessor_need = version_attr is None and not isinstance(family_shape, NonTemporal)
    selection = layout.member_selection
    key = family_view(meta, entity).primary_key.identity
    acquisition = _Acquisition(
        instruction=instruction,
        entity=entity.identity,
        selection=selection,
        key=key.name,
        key_position=selection.position(key),
        family_shape=family_shape,
        change=_effective_change(instruction, selection.shape),
    )
    version_position = None if version_attr is None else selection.position(version_attr)

    # The resolve is a Read of its own (`m-execution-lifecycle`: every
    # statement-reaching operation belongs to exactly one Read, Write Batch, or
    # Stream Batch), opened INSIDE the force-flush so the dependency batch it
    # forces out is its ordered sibling rather than its parent, and spanning its
    # own planning, lowering, and its one traversal of the resolved roots, so a
    # compile refusal or a root holding invalid stored data is a FAILED Read
    # rather than work outside every activity. It is row-form, so it names the
    # internal `rows` interface — no caller ever sees its result, which is
    # exactly why it is not published through either public one. Its Database
    # Call brackets through the package's one read-call seam, never a second
    # copy of those rules.
    #
    # Row form is what answers BOTH projection needs above at once: a family
    # predicate write is rejected before SQL, so the compiled row transform is
    # the identity under `Columns` layout and the document fan-out under
    # Relational Document Layout, and every per-row step below reads the one
    # positional member state the read materialized over the target's own
    # member selection. The fan-out drops the raw Structured Column it decoded
    # from while the materialized row carries that document beside its
    # values, so a temporal target's Predecessor Row retains it (`m-unit-work`)
    # — which is what lets a successor be patched from the document the row
    # actually held — without a second extraction that could disagree with the
    # first.
    #
    # Nothing reaches the Unit of Work until every root has been judged and the
    # group sealed: a root refused later in the traversal leaves only the local
    # builders, which nothing else reaches.
    def resolve() -> _Acquired | None:
        with attempt.read(entity.identity, "rows") as read:
            query = deep_fetch.plan_mutation_read(
                instruction,
                model=meta,
                temporal=latest_temporal_selections(root),
                projection=deep_fetch.ReadProjectionRequest(
                    "all" if predecessor_need else "none",
                    predecessor_need,
                ),
            )
            compiled = compile_read(
                query,
                meta,
                conn.dialect,
                result_form="row",
                lock=lock,
            )
            stage = Materializer().read_page(
                FlatPageRead(model, compiled, lambda: execute_read(conn, compiled, read), Pin())
            )
            if version_position is not None:
                return _acquire_versioned(stage.page, acquisition, version_position)
            return _acquire_temporal(
                stage, acquisition, documents=compiled.structured_column is not None
            )

    acquired = uow.read(resolve)
    if acquired is None:
        return
    group, selected = acquired
    uow.buffer(group)
    _claim_selected_states(uow, selected)


type _Acquired = tuple[MaterializedWriteGroup, list[ObservedStateKey]]


@dataclass(frozen=True, slots=True)
class _Acquisition:
    """One materializing write's facts, read once before its resolve.

    ``change`` is absent for a verb carrying no assignments, whose every
    resolved row is retained.
    """

    instruction: PreparedPredicateWrite
    entity: EntityIdentity
    selection: EntityMemberSelection
    key: str
    key_position: int
    family_shape: TemporalShape
    change: PreparedEffectiveChange | None

    def selects(self, row: tuple[object, ...]) -> bool:
        """Whether ``row`` joins the group rather than being eliminated as a no-op
        (`m-opt-lock` per-row no-op elimination)."""
        change = self.change
        return change is None or change.any_effective(row)

    def object_key(self, row: tuple[object, ...]) -> ObjectKey:
        return ObjectKey(self.entity, ((self.key, row[self.key_position]),))


def _effective_change(
    instruction: PreparedPredicateWrite, shape: MemberShape
) -> PreparedEffectiveChange | None:
    """The codec's effective-change comparison for an assignment-bearing verb,
    prepared once for the whole write from the assignments as authored."""
    if instruction.mutation not in _ASSIGNMENT_BEARING:
        return None
    return prepare_effective_change(
        shape,
        {
            assignment_member(assignment.attr): assignment.value
            for assignment in instruction.managed_assignments
        },
        absent=ABSENT,
    )


def _publishable_member_rows(page: Page) -> Iterator[tuple[object, ...]]:
    """Each resolved root's positional member row, in resolution order, from the
    one traversal that refuses a root holding invalid stored data.

    A predicate write has no in-band channel for a stored-data verdict, so the
    publication gate runs before a row contributes anything.
    """
    return Materializer().roots(page, _publishable_member_row)


def _publishable_member_row(root: RootView, _position: int) -> Iterator[tuple[object, ...]]:
    require_publishable(root)
    (node,) = root.roots
    if node is None:  # pragma: no cover - a publishable flat root resolves its node
        raise ValueError("predicate-write staging requires one Entity State per resolved row")
    yield root.member_values(node)


def _acquire_versioned(
    page: Page, acquisition: _Acquisition, version_position: int
) -> _Acquired | None:
    """A versioned target's group: the key and observed version of every row
    that is not a no-op."""
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    selected: list[ObservedStateKey] = []
    for row in _publishable_member_rows(page):
        if not acquisition.selects(row):
            continue
        version = cast("int", row[version_position])
        keys.append(row[acquisition.key_position])
        versions.append(version)
        selected.append(
            observed_state_key(
                acquisition.object_key(row),
                VersionObservation(observed_version=version),
                acquisition.family_shape,
            )
        )
    if not selected:
        return None
    group = MaterializedWriteGroup(
        mutation=acquisition.instruction,
        key_attributes=(acquisition.key,),
        key_columns=(whole(keys.build()),),
        observations=VersionColumns(versions=whole(versions.build())),
    )
    return group, selected


def _acquire_temporal(
    stage: RowPublication, acquisition: _Acquisition, *, documents: bool
) -> _Acquired | None:
    """A temporal target's group: the complete Predecessor Row of every row that
    is not a no-op (`m-unit-work` "A Predecessor Row is the complete, immutable
    persisted state").

    Every member position contributes exactly one cell, an absent marker
    included, so the columns stay aligned, and the raw Structured Column rides
    beside them by the row's position in the traversal. The short-lived view
    over each row exists only to derive its observed-state key and is not
    retained.
    """
    selection = acquisition.selection
    names = tuple(member.name for member in selection.shape.members)
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    members = tuple(ChunkedColumnBuilder[object]() for _ in names)
    retained: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    selected: list[ObservedStateKey] = []
    for position, row in enumerate(_publishable_member_rows(stage.page)):
        if not acquisition.selects(row):
            continue
        keys.append(row[acquisition.key_position])
        state = EntityStateRow.over_declared_members(selection, row, absent=ABSENT)
        for builder, (_name, value) in zip(members, state.items(), strict=True):
            builder.append(value)
        if documents:
            retained.append(stage.documents[position])
        selected.append(
            observed_state_key(
                acquisition.object_key(row),
                TemporalObservation(predecessor=PredecessorRow(state)),
                acquisition.family_shape,
            )
        )
    if not selected:
        return None
    count = selection.attribute_count
    columns = tuple(whole(builder.build()) for builder in members)
    predecessors = PredecessorColumns(
        shape=PredecessorShape(attributes=names[:count], value_objects=names[count:]),
        attribute_columns=columns[:count],
        value_object_columns=columns[count:],
        documents=whole(retained.build()) if documents else None,
    )
    group = MaterializedWriteGroup(
        mutation=acquisition.instruction,
        key_attributes=(acquisition.key,),
        key_columns=(whole(keys.build()),),
        observations=TemporalColumns(predecessors=predecessors),
    )
    return group, selected


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
