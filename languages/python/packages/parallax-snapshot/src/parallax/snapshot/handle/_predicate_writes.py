from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Final

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
from parallax.core.metamodel import AttributeIdentity, EntityMetadata
from parallax.core.object_query._fluent import ObjectQuery, mutation_selection
from parallax.core.object_query._validated import latest_temporal_selections
from parallax.core.sql_gen._compile import compile_read
from parallax.core.temporal_read import NonTemporal, Pin, TemporalShape
from parallax.core.unit_work import (
    MaterializedWriteGroup,
    PredecessorRows,
    PredecessorRowsBuilder,
    PredicateMutation,
    PredicateSelection,
    PredicateWrite,
    UnitOfWork,
    VersionedEvidence,
    VersionedEvidenceBuilder,
    WriteAssignment,
    instructions,
)
from parallax.core.unit_work.instructions import (
    PreparedPredicateWrite,
)
from parallax.core.unit_work.write_settlement import reject_readless_document_many
from parallax.snapshot.handle._concurrency import CONCURRENCY
from parallax.snapshot.handle._family import (
    assignment_member,
    entity_layout,
    family_view,
    temporal_shape,
)
from parallax.snapshot.handle._materialization import FlatPageRead, Materializer, RowPublication
from parallax.snapshot.handle._read import entity_read_lock, execute_read
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
    """The Typed entry to the predicate-write lane: a mutation-compatible
    :class:`~parallax.core.object_query.ObjectQuery` plus ``Attr.set(...)``
    assignments, stated as the canonical
    :class:`~parallax.core.unit_work.PredicateWrite` every ingress prepares.

    Only the query's own form is judged here: a query carrying a result-shaping,
    temporal, narrowing, or deep-fetch clause is no write target
    (:func:`~parallax.core.object_query.mutation_selection`,
    ``query-not-mutation-compatible``), and no instruction has a spelling for
    such a clause. Everything the instruction states — its target, verb, window,
    predicate, and assignments — is judged by
    :func:`~parallax.core.unit_work.instructions.prepare_typed_write` before
    :func:`buffer_predicate_instruction` dispatches the prepared product.
    """
    selection = mutation_selection(query)
    instruction = PredicateWrite(
        mutation,
        PredicateSelection(selection.target.canonical, selection.predicate),
        tuple(
            WriteAssignment(str(assignment.attr), assignment.value) for assignment in assignments
        ),
        valid_from,
        until,
    )
    prepared = instructions.prepare_typed_write(instruction, model.meta)
    assert isinstance(prepared, PreparedPredicateWrite)
    buffer_predicate_instruction(uow, model, conn, prepared, attempt)


def buffer_predicate_instruction(
    uow: UnitOfWork,
    model: CatalogedModel,
    conn: DatabaseConnection,
    instruction: PreparedPredicateWrite,
    attempt: TransactionAttemptActivity,
) -> None:
    """Dispatch a prepared predicate write READLESS (`m-batch-write`) or
    MATERIALIZE it (`m-opt-lock`, ADR 0014) — the seam both representations'
    ``_where`` verbs share.

    The prepared product already carries its admissibility: preparation refused
    an inheritance-family target and a verb the target does not take. What is
    decided here is execution: an unversioned non-temporal target settles as one
    statement, after refusing a document-resident ``many`` assignment no
    readless statement can express; every other target materializes.
    """
    meta = model.meta
    entity = instruction.selection.target
    shape = temporal_shape(meta, entity)
    version_attr = CONCURRENCY.version_attribute(meta, entity.identity)
    if isinstance(shape, NonTemporal) and version_attr is None:
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
    then append each matched row's evidence directly to its bounded evidence
    builder — never a per-row keyed-write wrapper, never a parallel
    pending-observation list — and buffer the sealed result as one
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
    # row itself, retained whole as the group's Predecessor Rows (below);
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
    acquisition = _Acquisition(
        selection=selection,
        key_position=selection.position(family_view(meta, entity).primary_key.identity),
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
    # first. The Page is private to this resolve, so its judged rows and the
    # documents it decoded transfer to the group by reference.
    #
    # Nothing reaches the Unit of Work until every root has been judged and the
    # evidence sealed: a root refused later in the traversal leaves only the
    # local builder, which nothing else reaches. Buffering the group then
    # installs its selection claims with it, or neither.
    def resolve() -> VersionedEvidence | PredecessorRows | None:
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

    evidence = uow.read(resolve)
    if evidence is not None:
        uow.buffer(MaterializedWriteGroup(mutation=instruction, evidence=evidence))


@dataclass(frozen=True, slots=True)
class _Acquisition:
    """One materializing write's facts, read once before its resolve.

    ``change`` is absent for a verb carrying no assignments, whose every
    resolved row is retained.
    """

    selection: EntityMemberSelection
    key_position: int
    change: PreparedEffectiveChange | None

    def selects(self, row: tuple[object, ...]) -> bool:
        """Whether ``row`` joins the group rather than being eliminated as a no-op
        (`m-opt-lock` per-row no-op elimination)."""
        change = self.change
        return change is None or change.any_effective(row)


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
) -> VersionedEvidence | None:
    """A versioned target's evidence: the key and observed version of every row
    that is not a no-op."""
    evidence = VersionedEvidenceBuilder(
        key_position=acquisition.key_position, version_position=version_position
    )
    for row in _publishable_member_rows(page):
        if acquisition.selects(row):
            evidence.append(row)
    return evidence.seal()


def _acquire_temporal(
    stage: RowPublication, acquisition: _Acquisition, *, documents: bool
) -> PredecessorRows | None:
    """A temporal target's evidence: the complete Predecessor Row of every row
    that is not a no-op (`m-unit-work` "A Predecessor Row is the complete,
    immutable persisted state").

    Each judged member row is retained whole, the absent marker included at any
    member it does not hold, and its raw Structured Column rides beside it by
    the row's position in the traversal.
    """
    evidence = PredecessorRowsBuilder(
        acquisition.selection,
        key_position=acquisition.key_position,
        absent=ABSENT,
        documents=documents,
    )
    raw = stage.documents
    for position, row in enumerate(_publishable_member_rows(stage.page)):
        if acquisition.selects(row):
            evidence.append(row, raw[position] if documents else None)
    return evidence.seal()
