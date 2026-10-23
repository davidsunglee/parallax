from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol, cast

from parallax.core.base import INFINITY, TemporalBound
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityMetadata,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import (
    Bitemporal,
    TimeInterval,
    TransactionTimeOnly,
)
from parallax.core.temporal_write.coverage import (
    CoverageGap,
    CoverageTransform,
    Successor,
)
from parallax.core.write_plan.keys import ObjectStateKey
from parallax.core.write_plan.observe import AssignedComparison, PredecessorRow
from parallax.core.write_plan.payload import RowPayload, WritePayloadPreparer
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    BoundRange,
    CurrentRowOutput,
    Derivation,
    DerivedRow,
    Openings,
    TemporalRowCoordinates,
    TemporalWriteOwnership,
)
from parallax.core.write_plan.planned_rows import (
    resolve_row,
)
from parallax.core.write_plan.steps import (
    FAILED_PRECONDITION,
    NEW_LINEAGE,
    SUPERSEDED,
    TERMINATED,
    UNGATED,
    CarriedFrom,
    ChangedFrom,
    CloseCause,
    ExactCount,
    ExecutedMembers,
    Finite,
    MaxPlusOne,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedInsert,
    PlannedStep,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedValue,
    RowOrigin,
    TemporalConcurrency,
    TemporalGate,
    TemporalUpperBound,
    WriteRow,
    adopt_planned_assignments,
    adopt_planned_row,
    shortfall_classification,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_UPPER_BOUND

__all__ = [
    "ExpansionRole",
    "PredecessorExpander",
    "RowAudit",
    "TemporalFacts",
    "bitemporal_ends",
    "entry_endpoint",
    "entry_ends",
    "opening",
    "openings",
]

type ExpansionRole = Literal["coverage", "starting", "validation"]
"""How a write's driver asks one predecessor to be expanded: as coverage its
transform applies to, as coverage a caller's starting condition names, or as an
earlier observation it only validates and retires."""

type _ResolvedState = tuple[
    dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]
]

type _Overlay = tuple[
    Mapping[AttributeIdentity, PlannedValue], Mapping[ValueObjectIdentity, object]
]
"""Resolved assigned members a produced row overlays on its starting state."""


class RowAudit(Protocol):
    """How a temporal write's audit finalizes each row it produces and stamps
    each close it emits, already bound to the attempt's actor and instant."""

    def finalize_row(self, write_row: WriteRow, /) -> WriteRow: ...

    def decorate_close(self, close: PlannedClose, /) -> PlannedClose: ...


@dataclass(frozen=True, slots=True)
class TemporalFacts:
    """What one temporal write settles about its target before any predecessor
    is in hand: the target, its compiled family-effective view, the Temporal
    Shape whose axes bound its intervals, and the attempt's resolved instant.

    Every field is a value a facet or the clock produced, never the producer,
    so a deferred range may retain them and still decide nothing later.
    """

    entity: EntityMetadata
    view: InheritanceEntityView
    shape: TransactionTimeOnly | Bitemporal
    instant: dt.datetime


_NOTHING: Final[BoundRange] = BoundRange(steps=())

type _Extent = tuple[object, object, bool]
"""One successor's Valid-Time start and end — ``None`` both without Valid
Time — and whether it executes the write's assignments rather than carrying its
predecessor's state."""


class PredecessorExpander:
    """The per-object rules of one temporal write: whether its transform reaches
    a predecessor, whether the predecessor is unchanged and how that is proven,
    how it is closed and gated, how the attempt's ownership disposes of it, and
    which successors it opens — and the new lineages the write opens from no
    predecessor at all, a pending insertion's surviving parts and a
    replacement's gaps.

    Built once per settled write — a range binding or a pending insertion — from the
    write's settled facts and the attempt's ownership as it stands then.
    ``key_value`` is a range's one object key. ``gated`` and ``guards`` say
    whether its closes gate and whether the database can prove an unchanged
    milestone by a guard. Where a source the attempt may still continue
    reaches a predecessor the write changes, the write describes what it
    leaves of that predecessor and the rows execution captures for it.
    ``audit`` finalizes each row the write produces, carried, changed, or new,
    once, and stamps each close it emits; ``payloads`` prepares what an
    object's produced rows persist, so that equal adjacent ones merge
    (:meth:`settle`).

    Every predecessor is settled by one decision (:func:`_disposition`) and
    realized by one construction of its own step (:func:`_own_step`) and its
    successors (:func:`_represented`). Each canonical assignment mapping is
    resolved, and its comparison with stored values prepared, once per expansion
    however many predecessors and gaps share it. Nothing returned retains the expansion
    or the ownership it read.
    """

    __slots__ = (
        "_audit",
        "_close_affected_rows",
        "_close_assignments",
        "_close_end_attributes",
        "_comparisons",
        "_facts",
        "_gated",
        "_guards",
        "_key_attributes",
        "_key_values",
        "_ownership",
        "_payloads",
        "_resolved",
        "_starting_close_affected_rows",
        "_transform",
    )

    def __init__(
        self,
        facts: TemporalFacts,
        transform: CoverageTransform,
        *,
        key_attribute: AttributeIdentity,
        key_value: object = None,
        gated: bool,
        guards: bool = False,
        ownership: TemporalWriteOwnership,
        audit: RowAudit,
        payloads: WritePayloadPreparer,
    ) -> None:
        self._facts = facts
        self._transform = transform
        self._key_attributes = (key_attribute,)
        self._key_values = (key_value,)
        self._gated = gated
        # Every close of the object assigns the same Transaction-Time end,
        # addresses the same axis ends, and expects the same affected row.
        shape = facts.shape
        self._close_assignments = PlannedAssignments(
            attributes={shape.transaction_time.end_attribute: facts.instant}
        )
        self._close_end_attributes = _end_attributes(shape)
        self._close_affected_rows = ExactCount(
            expected=1, on_shortfall=shortfall_classification(observing=True, gated=gated)
        )
        self._starting_close_affected_rows = (
            ExactCount(expected=1, on_shortfall=FAILED_PRECONDITION)
            if gated
            else self._close_affected_rows
        )
        self._guards = guards
        self._ownership = ownership
        self._audit = audit
        self._payloads = payloads
        self._resolved: list[tuple[Mapping[str, object], _ResolvedState, ExecutedMembers]] = []
        self._comparisons: list[tuple[Mapping[str, object], AssignedComparison]] = []

    def expand(
        self,
        predecessor: PredecessorRow,
        *,
        role: ExpansionRole,
        state: ObjectStateKey,
        coverage: TimeInterval | None,
    ) -> BoundRange:
        """``predecessor`` settled alone (:meth:`settle`): the steps and effects
        of an object whose only reached milestone it is."""
        return self.settle(((predecessor, role, state, coverage),))

    def closing(
        self,
        predecessor: PredecessorRow,
        coverage: TimeInterval | None,
        cause: CloseCause,
        *,
        starting: bool = False,
    ) -> PlannedClose:
        """The close of ``predecessor`` at its own address, gated on its
        observed Transaction-Time start where the write gates."""
        facts = self._facts
        gate: TemporalConcurrency = UNGATED
        if self._gated:
            start = facts.shape.transaction_time.start_attribute
            gate = TemporalGate(start_attribute=start, observed_start=predecessor.cell(start))
        return _planned_close(
            facts,
            key_attributes=self._key_attributes,
            key_values=self._key_values,
            observed_valid_end=None if coverage is None else coverage.end,
            cause=cause,
            gate=gate,
            assignments=self._close_assignments,
            end_attributes=self._close_end_attributes,
            affected_rows=(
                self._starting_close_affected_rows if starting else self._close_affected_rows
            ),
        )

    def _keeps(self, predecessor: PredecessorRow, owned: bool) -> bool:
        """Whether ``predecessor``, if unchanged, could be kept as it is
        (:func:`_provable`).

        Ownership proves only the row the attempt opened at the address it
        records. Every such row carries the attempt's instant, so a gated
        predecessor at another Transaction-Time start is an earlier milestone
        observed at an address the attempt has since reopened: it is never kept
        unchanged, and its disposal gates on its observed start."""
        gated = self._gated
        if owned and gated:
            start = self._facts.shape.transaction_time.start_attribute
            return predecessor.cell(start) == self._facts.instant
        return _provable(owned=owned, gated=gated, guards=self._guards)

    def _unchanged(
        self,
        predecessor: PredecessorRow,
        coverage: TimeInterval | None,
        successors: Sequence[Successor],
    ) -> bool:
        """Whether ``successors`` leave ``predecessor`` as it was: together they
        cover all of it, and each assigned member already holds its value there
        — an amendment's assignments and a replacement's complete writable state
        alike, compared by declared value."""
        if coverage is None:
            if len(successors) != 1:
                return False
        elif not _complete(successors, coverage):
            return False
        return all(
            successor.assigned is None or predecessor.holds(self._comparison(successor.assigned))
            for successor in successors
        )

    def _comparison(self, assigned: Mapping[str, object]) -> AssignedComparison:
        for mapping, comparison in self._comparisons:
            if mapping is assigned:
                return comparison
        comparison = AssignedComparison(self._facts.view.member_selection, assigned)
        self._comparisons.append((assigned, comparison))
        return comparison

    def _resolution(self, assigned: Mapping[str, object]) -> tuple[_ResolvedState, ExecutedMembers]:
        for mapping, maps, executed in self._resolved:
            if mapping is assigned:
                return maps, executed
        facts = self._facts
        maps = resolve_row(facts.entity, facts.view, assigned, context="insert")
        executed = _in_member_order(facts, (*maps[0], *maps[1]))
        self._resolved.append((assigned, maps, executed))
        return maps, executed

    def _candidate(self, predecessor: PredecessorRow, successor: Successor) -> WriteRow:
        """``successor`` of ``predecessor`` as the finalized row it produces."""
        coverage = successor.valid_time_coverage
        if coverage is None:
            start = end = None
        else:
            start, end = coverage.start, coverage.end
        assigned = successor.assigned
        if assigned is None:
            row = _successor_row(self._facts, predecessor, start, end)
        else:
            maps, executed = self._resolution(assigned)
            row = _successor_row(
                self._facts, predecessor, start, end, assigned=maps, executed=executed
            )
        return self._audit.finalize_row(row)

    def _new_lineage(
        self,
        seed: _ResolvedState,
        coverage: TimeInterval | None,
        assigned: Mapping[str, object] | None,
    ) -> WriteRow:
        """A new lineage over ``coverage`` carrying a fresh copy of ``seed``
        with ``assigned`` overlaid, finalized once."""
        start, end = (None, None) if coverage is None else (coverage.start, coverage.end)
        return self._audit.finalize_row(
            _represented(
                self._facts,
                dict(seed[0]),
                dict(seed[1]),
                start,
                end,
                NEW_LINEAGE,
                assigned=None if assigned is None else self._resolution(assigned)[0],
            )
        )

    def settle(
        self,
        predecessors: Iterable[
            tuple[PredecessorRow, ExpansionRole, ObjectStateKey, TimeInterval | None]
        ],
        *,
        lineage: tuple[_ResolvedState, TimeInterval] | None = None,
        gaps: Iterable[CoverageGap] = (),
    ) -> BoundRange:
        """One object settled whole: a pending insertion's surviving parts
        (``lineage``, its resolved seed over its own window), each predecessor
        expanded in its role, in the order its own effect runs, and a
        replacement's ``gaps`` — as the steps realizing them and the effects
        their success publishes (`m-temporal-write` *Merging produced
        successors*).

        Each predecessor is decided by itself first (:meth:`_reach`): reach,
        preservation and its proof, close and gate, and the rows it produces,
        each finalized by the write's audit once. Only then do the object's
        produced rows — successors, a pending insertion's surviving parts, a
        replacement's gaps — merge, in Valid-Time order: two adjacent ones whose
        persisted state outside their interval is identical, the final audit
        included, become one row over both. A cheap comparison of direct cells
        rejects most unequal neighbours before any structured value is
        prepared; a pair it cannot reject is prepared and compared whole, and
        the cells prepared are the ones lowering stores. A kept unchanged
        milestone, an untouched neighbour, and a gap no replacement fills
        produce nothing, so nothing merges across them.

        Merging chooses no address before it is done: a row the attempt opened
        whose own successor ends a merged run where the row ends is revised in
        place into the whole run by its own assignments, every other such row
        whose address a merged run absorbed is removed, and every remaining run
        is opened. Every predecessor's own effect keeps its order, ahead of
        every opening, so a lost condition fails before anything new is
        written, and every predecessor keeps its own effect however few rows
        the merge leaves. Openings follow in the order their first produced
        part was: the insertion's parts, each predecessor's successors, the
        gaps.

        Each changed predecessor a continuable source reaches is described
        with the rows it left (:class:`Derivation`), and each row produced
        from one, opened or revised, as an output execution captures
        (:class:`CurrentRowOutput`).
        """
        settlement = _Settlement()
        if lineage is not None:
            seed, window = lineage
            for successor in self._transform.successors_of(window):
                extent = successor.valid_time_coverage
                settlement.produce(
                    extent,
                    self._new_lineage(seed, extent, successor.assigned),
                    None,
                    kept=False,
                    shares=(extent,),
                )
        for predecessor, role, state, coverage in predecessors:
            self._reach(settlement, predecessor, role, state, coverage)
        for gap in gaps:
            window = gap.valid_time_window
            settlement.produce(
                window,
                self._new_lineage(
                    ({self._key_attributes[0]: self._key_values[0]}, {}), window, gap.assigned
                ),
                None,
                kept=False,
                shares=(),
            )
        return self._settled(settlement)

    def _reach(
        self,
        settlement: _Settlement,
        predecessor: PredecessorRow,
        role: ExpansionRole,
        state: ObjectStateKey,
        coverage: TimeInterval | None,
    ) -> None:
        """Add ``predecessor`` — the current row whose observed state is
        ``state`` and whose Valid Time is ``coverage`` (``None`` without Valid
        Time) — expanded in its ``role``.

        A transform that does not reach the predecessor leaves it alone. One
        it leaves exactly as it was is kept where that is proven, whether the
        write's source observed it, an insertion authorized the write, or a
        caller's condition named it (:meth:`_unchanged`). Otherwise the
        predecessor is closed — Superseded where a successor assigns,
        Terminated otherwise — and its nonempty successors produced, or the
        attempt's own row is revised or removed instead. A ``starting``
        predecessor's gate, a guard keeping it included, fails as its caller's
        precondition. A ``validation`` predecessor is retired as Terminated
        through the same disposal, producing nothing. Only an emitted close is
        stamped by the write's audit; a guard proving a kept milestone and the
        close a removal or revision addresses like are not.
        """
        facts = self._facts
        if role == "validation":
            closing = self.closing(predecessor, coverage, TERMINATED)
            own = _target_endpoint(facts, closing.target)
            owned = self._ownership.owns(own)
            code = _disposition(
                unchanged=False,
                owned=owned,
                gated=self._gated,
                guards=self._guards,
                extents=(),
                start=None,
                end=_valid_end(coverage),
            )
            settlement.reached.append(
                _Reached(
                    predecessor,
                    state,
                    coverage,
                    closing,
                    own,
                    owned,
                    code,
                    demanded=self._ownership.demanded(state, own if owned else None),
                )
            )
            return
        transform = self._transform
        if not transform.reaches(coverage):
            return
        successors = transform.successors_of(coverage)
        cause = (
            SUPERSEDED
            if any(successor.assigned is not None for successor in successors)
            else TERMINATED
        )
        closing = self.closing(predecessor, coverage, cause, starting=role == "starting")
        own = _target_endpoint(facts, closing.target)
        owned = self._ownership.owns(own)
        code = _disposition(
            unchanged=self._keeps(predecessor, owned)
            and self._unchanged(predecessor, coverage, successors),
            owned=owned,
            gated=self._gated,
            guards=self._guards,
            extents=tuple(_extent(successor) for successor in successors) if owned else (),
            start=None if coverage is None else coverage.start,
            end=_valid_end(coverage),
        )
        disposal = code & _DISPOSAL
        if disposal == _PRESERVE:
            return
        ownership = self._ownership
        inserted = (
            ownership.insertion_coverage(own, coverage)
            if owned and ownership.continues_insertion(own)
            else ()
        )
        if disposal == _GUARD:
            settlement.reached.append(
                _Reached(predecessor, state, coverage, closing, own, owned, code, inserted)
            )
            return
        reached = _Reached(
            predecessor,
            state,
            coverage,
            closing,
            own,
            owned,
            code,
            inserted,
            demanded=ownership.demanded(state, own if owned else None),
        )
        settlement.reached.append(reached)
        kept = _kept_index(code)
        # A row a successor may open shares one bindable predecessor; the
        # successor keeping an owned row's address is only ever revised into.
        bindable: PredecessorRow | None = None
        for index, successor in enumerate(successors):
            extent = successor.valid_time_coverage
            if index == kept:
                source = predecessor
            else:
                if bindable is None:
                    bindable = predecessor.with_bindable_document()
                source = bindable
            settlement.produce(
                extent,
                self._candidate(source, successor),
                reached,
                kept=index == kept,
                shares=_shares(extent, inserted),
            )

    def _settled(self, settlement: _Settlement) -> BoundRange:
        facts = self._facts
        reached = settlement.reached
        candidates = settlement.candidates
        if not reached and not candidates:
            return _NOTHING
        opened: list[_Opened] = []
        revised: list[_Filed] | None = None
        if len(candidates) < 2 or not isinstance(facts.shape, Bitemporal):
            for candidate in candidates:
                filed = _realize_alone(facts, candidate, opened)
                if filed is not None:
                    revised = _filing(revised, filed)
        else:
            for run in self._runs(candidates):
                filed = self._realize(run, opened)
                if filed is not None:
                    revised = _filing(revised, filed)
        effects, outputs = self._effects(reached)
        opened.sort(key=_first)
        entity = facts.entity.identity
        inserts = tuple(
            PlannedInsert(entity=entity, entries=(row,)) for _, row, _, _, _, _ in opened
        )
        endpoints = tuple(endpoint for _, _, _, _, _, endpoint in opened)
        demanded = any(record.demanded for record in reached)
        derived: tuple[Derivation, ...] = ()
        if demanded:
            outputs.extend(_opened_outputs(opened, endpoints))
            derived = self._derived(reached, candidates, _by_ends(endpoints, reached))
        return BoundRange(
            steps=(*effects, *inserts),
            changed=tuple(record.state for record in reached if _changes(record.code)),
            removed=tuple(record.own for record in reached if record.code & _DISPOSAL == _REMOVE),
            opened=_openings(opened, endpoints, revised or ()),
            derived=derived,
            current_outputs=tuple(outputs),
        )

    def _effects(
        self, reached: Sequence[_Reached]
    ) -> tuple[list[PlannedStep], list[CurrentRowOutput]]:
        """Each reached predecessor's own step, in order, and the output each
        revision into a row a continuable source reaches persists."""
        owned = [(record, self._own(record)) for record in reached]
        effects = [step for _record, step in owned if step is not None]
        outputs = [
            _revised_output(record, step)
            for record, step in owned
            if record.publishes and isinstance(step, PlannedTemporalRevision)
        ]
        return effects, outputs

    def _own(self, record: _Reached) -> PlannedStep | None:
        """The step ``record``'s predecessor finally takes of its own: its
        decorated close, a guard, a removal, a revision, or none."""
        disposal = record.code & _DISPOSAL
        if disposal == _CLOSE:
            return self._audit.decorate_close(record.closing)
        return (
            None
            if disposal == _KEEP
            else _own_step(
                self._facts, record.code, record.closing, record.realized, record.predecessor
            )
        )

    def _runs(self, candidates: list[_Candidate]) -> list[list[_Candidate]]:
        """A Bitemporal object's produced rows as the runs they merge into, in
        Valid-Time order: each adjacent pair is merged only once eligible and
        proven identical (:meth:`_joins`), never compared with any row but its
        neighbour."""
        runs: list[list[_Candidate]] = []
        for candidate in sorted(candidates, key=_candidate_start):
            if runs and self._joins(runs[-1][-1], candidate):
                runs[-1].append(candidate)
            else:
                runs.append([candidate])
        return runs

    def _joins(self, left: _Candidate, right: _Candidate) -> bool:
        """Whether ``right`` continues ``left`` as one row: it starts where
        ``left`` ends, both stand at the same Transaction-Time interval, and
        their persisted state outside their interval is identical."""
        if left.end != right.start:
            return False
        facts = self._facts
        transaction_time = facts.shape.transaction_time
        before, after = left.row.row.attributes, right.row.row.attributes
        if (
            before[transaction_time.start_attribute] != after[transaction_time.start_attribute]
            or before[transaction_time.end_attribute] != after[transaction_time.end_attribute]
        ):
            return False
        payloads = self._payloads
        if payloads.proven_unequal_non_interval(facts.entity.identity, left.row, right.row):
            return False
        return payloads.equal_non_interval(self._prepared(left), self._prepared(right))

    def _prepared(self, candidate: _Candidate) -> RowPayload:
        payload = candidate.payload
        if payload is None:
            payload = candidate.payload = self._payloads.row(
                self._facts.entity.identity, candidate.row
            )
        return payload

    def _realize(self, run: list[_Candidate], opened: list[_Opened]) -> _Filed | None:
        """Choose how ``run`` is stored: by the owned predecessor whose own
        successor ends it where that row ends, revised into the whole run by
        its own assignments, or else as one row added to ``opened``; an owned
        predecessor whose address the run absorbed otherwise is removed. A
        revision whose insertion parts it reports is answered."""
        edge = run[-1]
        if len(run) == 1:
            return _realize_alone(self._facts, edge, opened)
        shares = _joined_shares(run)
        start = run[0].start
        merged = _interval(start, edge.end)
        for member in run:
            member.merged = merged
        for member in run[:-1]:
            if member.kept:
                record = member.reached
                assert record is not None  # a kept successor keeps its predecessor's address
                record.code = _REMOVE
        facts = self._facts
        demanded = any(member.reached is not None and member.reached.demanded for member in run)
        if edge.kept:
            record = edge.reached
            assert record is not None  # a kept successor keeps its predecessor's address
            realized = _rebound_row(facts, edge.row, start, edge.end)
            if _revises(facts, realized, record.predecessor):
                record.code = _REVISE
                record.realized = realized
                record.realized_coverage = merged
                record.publishes = demanded
                return record.own, merged, shares
            # The run is the row's own state over its own coverage, which no
            # revision expresses: one that needed no statement was kept
            # unchanged already, so this one is removed under its gate and the
            # run opened.
            record.code = _REMOVE
        # The witness keeps no owned row's address, so its predecessor was made
        # bindable, and its cells were prepared whole when it was compared with
        # its neighbour.
        witness = next(member for member in reversed(run) if not member.kept)
        row = _rebound_row(facts, witness.row, start, edge.end)
        payload = witness.payload
        assert payload is not None  # a merged row was compared whole with its neighbour
        opened.append(
            (
                min(member.order for member in run),
                row.with_prepared(self._payloads.rebound(payload, row)),
                merged,
                shares,
                demanded,
                entry_endpoint(facts, row),
            )
        )
        return None

    def _derived(
        self,
        reached: Sequence[_Reached],
        candidates: Sequence[_Candidate],
        known: Mapping[tuple[TemporalUpperBound, ...], TemporalRowCoordinates],
    ) -> tuple[Derivation, ...]:
        """What the write left of each predecessor it changed that a source
        the attempt may still continue reaches: its state and coverage, its
        coordinates where the attempt owned it, and each row it contributed
        to — the row the write opens or revises there, by the upper ends
        ``known`` names it at, since every row of one object's write shares
        its key — with the Valid Time the row covers and the part it
        contributed."""
        rows: dict[int, list[DerivedRow]] = {}
        for candidate in candidates:
            record = candidate.reached
            if record is None or not record.demanded:
                continue
            contributed = _interval(candidate.start, candidate.end)
            extent = contributed if candidate.merged is None else candidate.merged
            ends = TRANSACTION_TIME_ENDS if extent is None else bitemporal_ends(extent.end)
            rows.setdefault(id(record), []).append(DerivedRow(known[ends], extent, contributed))
        return tuple(
            Derivation(
                predecessor=record.state,
                valid_time_coverage=record.coverage,
                input_coordinates=record.own if record.owned else None,
                rows=tuple(rows.get(id(record), ())),
            )
            for record in reached
            if record.demanded and _changes(record.code)
        )


@dataclass(slots=True)
class _Reached:
    """One predecessor a write settles a statement or a successor for: what its
    disposition decided before the object's produced rows merged and what it
    finally is once they have, the parts of it an insertion contributed where
    the attempt owned it, and the row it is revised into, if any, over its
    Valid Time.

    ``demanded`` says a source the attempt may still continue reaches the
    predecessor, and ``publishes`` that one reaches the row it is revised
    into, so execution captures that row."""

    predecessor: PredecessorRow
    state: ObjectStateKey
    coverage: TimeInterval | None
    closing: PlannedClose
    own: TemporalRowCoordinates
    owned: bool
    code: int
    inserted: tuple[TimeInterval | None, ...] = ()
    realized: WriteRow | None = None
    realized_coverage: TimeInterval | None = None
    demanded: bool = False
    publishes: bool = False


@dataclass(slots=True)
class _Candidate:
    """One row a write produces for its object before produced rows merge: its
    Valid-Time extent (``None`` both without Valid Time), the finalized row,
    the predecessor it succeeds where one does and whether it keeps that
    owned predecessor's address, the parts of it an admitted insertion
    contributed, its place among the write's openings, its prepared cells once
    a comparison demanded them, and the Valid Time of the row it merged into
    with its neighbours, if it did."""

    start: object
    end: object
    row: WriteRow
    reached: _Reached | None
    kept: bool
    shares: tuple[TimeInterval | None, ...]
    order: int
    payload: RowPayload | None = None
    merged: TimeInterval | None = None


@dataclass(slots=True)
class _Settlement:
    """What settling one object accumulates before its rows merge: each
    predecessor whose own effect runs, in order, and each produced row, in the
    order its opening would run."""

    reached: list[_Reached] = field(default_factory=list[_Reached])
    candidates: list[_Candidate] = field(default_factory=list[_Candidate])

    def produce(
        self,
        extent: TimeInterval | None,
        row: WriteRow,
        reached: _Reached | None,
        *,
        kept: bool,
        shares: tuple[TimeInterval | None, ...],
    ) -> None:
        start, end = (None, None) if extent is None else (extent.start, extent.end)
        candidates = self.candidates
        candidates.append(_Candidate(start, end, row, reached, kept, shares, len(candidates)))


type _Opened = tuple[
    int,
    WriteRow,
    TimeInterval | None,
    tuple[TimeInterval | None, ...],
    bool,
    TemporalRowCoordinates | None,
]
"""One run opened as a row: its place among the write's openings, the row, its
Valid Time, the parts of it an insertion contributed, whether a source the
attempt may still continue reaches it, and the address it opens at where its
key is known."""

type _Filed = tuple[TemporalRowCoordinates, TimeInterval | None, tuple[TimeInterval | None, ...]]
"""One owned row a run registers, opened or revised into it: its address, its
Valid Time, and the parts of it an insertion contributed."""


def _first(entry: _Opened) -> int:
    return entry[0]


def _candidate_start(candidate: _Candidate) -> dt.datetime:
    start = candidate.start
    assert isinstance(start, dt.datetime)  # only Bitemporal rows are ordered to merge
    return start


def _partly(record: _Reached) -> bool:
    """Whether an insertion contributed only some parts of ``record``'s owned
    row, so that its revision reports which parts it still holds."""
    inserted = record.inserted
    return bool(inserted) and inserted != (record.coverage,)


def _shares(
    extent: TimeInterval | None, inserted: tuple[TimeInterval | None, ...]
) -> tuple[TimeInterval | None, ...]:
    """The parts of a successor over ``extent`` an insertion contributed, from
    the parts ``inserted`` of the predecessor it contributed."""
    if not inserted or extent is None:
        return inserted
    parts: list[TimeInterval | None] = []
    for part in inserted:
        assert part is not None  # a Bitemporal row's parts lie on Valid Time
        shared = part.intersection(extent)
        if shared is not None:
            parts.append(shared)
    return tuple(parts)


def _joined_shares(run: Sequence[_Candidate]) -> tuple[TimeInterval | None, ...]:
    """The parts an insertion contributed to the row ``run`` merges into, in
    order, adjacent parts joined."""
    joined: list[TimeInterval] = []
    for member in run:
        for part in member.shares:
            assert part is not None  # only Bitemporal rows merge
            if joined and joined[-1].meets(part):
                joined[-1] = TimeInterval(joined[-1].start, part.end)
            else:
                joined.append(part)
    return tuple(joined)


def _openings(
    opened: Sequence[_Opened],
    endpoints: Sequence[TemporalRowCoordinates | None],
    revised: Sequence[_Filed],
) -> Openings:
    """The owned rows a write's ``opened`` runs, at their ``endpoints``, and
    its ``revised`` rows register, each by the parts of it an insertion
    contributed: none, all of it, or only those."""
    if not revised and not any(parts for _, _, _, parts, _, _ in opened):
        return Openings(
            fresh=tuple(coordinates for coordinates in endpoints if coordinates is not None)
        )
    fresh: list[TemporalRowCoordinates] = []
    continued: list[TemporalRowCoordinates] = []
    shared: list[tuple[TemporalRowCoordinates, tuple[TimeInterval, ...]]] = []
    for (_order, _row, extent, parts, _demanded, _endpoint), endpoint in zip(
        opened, endpoints, strict=True
    ):
        if endpoint is not None:
            _file(endpoint, extent, parts, fresh, continued, shared)
    for endpoint, extent, parts in revised:
        _file(endpoint, extent, parts, fresh, continued, shared)
    return Openings(fresh=tuple(fresh), continued=tuple(continued), shared=tuple(shared))


def _file(
    endpoint: TemporalRowCoordinates,
    extent: TimeInterval | None,
    parts: tuple[TimeInterval | None, ...],
    fresh: list[TemporalRowCoordinates],
    continued: list[TemporalRowCoordinates],
    shared: list[tuple[TemporalRowCoordinates, tuple[TimeInterval, ...]]],
) -> None:
    if not parts:
        fresh.append(endpoint)
    elif parts == (extent,):
        continued.append(endpoint)
    else:
        shared.append((endpoint, cast("tuple[TimeInterval, ...]", parts)))


def _realize_alone(
    facts: TemporalFacts, candidate: _Candidate, opened: list[_Opened]
) -> _Filed | None:
    """Store ``candidate``, merged with no neighbour: at the owned address it
    keeps, answering a revision whose insertion parts it reports, or else as
    one row added to ``opened``."""
    record = candidate.reached
    extent = _interval(candidate.start, candidate.end)
    if candidate.kept:
        assert record is not None  # a kept successor keeps its predecessor's address
        record.realized = candidate.row
        record.realized_coverage = extent
        record.publishes = record.demanded
        if (record.code & _DISPOSAL) == _REVISE and _partly(record):
            return record.own, extent, candidate.shares
        return None
    payload = candidate.payload
    row = candidate.row if payload is None else candidate.row.with_prepared(payload)
    opened.append(
        (
            candidate.order,
            row,
            extent,
            candidate.shares,
            record is not None and record.demanded,
            _unmerged_endpoint(facts, row, record),
        )
    )
    return None


def _unmerged_endpoint(
    facts: TemporalFacts, row: WriteRow, record: _Reached | None
) -> TemporalRowCoordinates | None:
    """The address ``row``, a successor of ``record``'s predecessor merged with
    no neighbour, opens at: the predecessor's own address where the finalized
    row keeps its key and Valid-Time end, or else the address its finalized
    cells name (:func:`entry_endpoint`)."""
    if record is None:
        return entry_endpoint(facts, row)
    attributes = row.row.attributes
    value = attributes.get(facts.view.primary_key.identity)
    if value is None or isinstance(value, MaxPlusOne):
        return None
    own = record.own
    if value != own.key[0]:
        return entry_endpoint(facts, row)
    shape = facts.shape
    if isinstance(shape, Bitemporal) and attributes[shape.valid_time.end_attribute] != _valid_end(
        record.coverage
    ):
        return TemporalRowCoordinates(facts.entity.identity, own.key, entry_ends(facts, attributes))
    return own


def _revised_output(record: _Reached, step: PlannedTemporalRevision) -> CurrentRowOutput:
    """The output ``step``, revising ``record``'s owned predecessor in place,
    persists."""
    realized = record.realized
    assert realized is not None  # a revision states the row it revises into
    return CurrentRowOutput(
        coordinates=record.own,
        valid_time_coverage=record.realized_coverage,
        row=realized,
        emitter=step,
        predecessor_document=record.predecessor.document,
    )


def _opened_outputs(
    opened: Sequence[_Opened], endpoints: Sequence[TemporalRowCoordinates | None]
) -> list[CurrentRowOutput]:
    """Each opened row a continuable source reaches whose key is known, at
    its ``endpoints``, as the output its insert entry persists."""
    return [
        CurrentRowOutput(coordinates=coordinates, valid_time_coverage=extent, row=row, emitter=row)
        for (_order, row, extent, _parts, demanded, _endpoint), coordinates in zip(
            opened, endpoints, strict=True
        )
        if demanded and coordinates is not None
    ]


def _by_ends(
    endpoints: Sequence[TemporalRowCoordinates | None], reached: Sequence[_Reached]
) -> dict[tuple[TemporalUpperBound, ...], TemporalRowCoordinates]:
    """Every row one object's write opens at ``endpoints`` or keeps at an
    owned predecessor's address, by its upper ends."""
    known = {record.own.ends: record.own for record in reached if record.owned}
    for coordinates in endpoints:
        if coordinates is not None:
            known[coordinates.ends] = coordinates
    return known


def _filing(revised: list[_Filed] | None, filed: _Filed) -> list[_Filed]:
    if revised is None:
        return [filed]
    revised.append(filed)
    return revised


def _rebound_row(facts: TemporalFacts, write_row: WriteRow, start: object, end: object) -> WriteRow:
    """``write_row`` over the Valid Time ``[start, end)`` of the run it
    realizes, its state, origin, and executed members otherwise its own."""
    shape = facts.shape
    assert isinstance(shape, Bitemporal)  # only Bitemporal rows merge
    row = write_row.row
    valid_time = shape.valid_time
    attributes = dict(row.attributes)
    attributes[valid_time.start_attribute] = start
    attributes[valid_time.end_attribute] = end
    return WriteRow(
        row=adopt_planned_row(attributes, row.value_objects),
        origin=write_row.origin,
        executed=write_row.executed,
    )


def _extent(successor: Successor) -> _Extent:
    coverage = successor.valid_time_coverage
    changed = successor.assigned is not None
    if coverage is None:
        return None, None, changed
    return coverage.start, coverage.end, changed


# One predecessor's settled disposition, packed into one small integer: what
# becomes of the predecessor itself, and which successor keeps an owned row's
# address.
_CLOSE: Final = 0
_REMOVE: Final = 1
_REVISE: Final = 2
_KEEP: Final = 3
_GUARD: Final = 4
_PRESERVE: Final = 5
_DISPOSAL: Final = 7
_KEPT_SHIFT: Final = 3


def _provable(*, owned: bool, gated: bool, guards: bool) -> bool:
    """Whether a milestone left exactly as it was can be kept without changing
    it (`m-temporal-write` *Unchanged milestones*): the attempt's ownership
    proves a row it opened, the shared lock proves one under Locking, and under
    Optimistic only a guard can, which a database must count to give."""
    return owned or not gated or guards


def _disposition(
    *,
    unchanged: bool,
    owned: bool,
    gated: bool,
    guards: bool,
    extents: Sequence[_Extent],
    start: object,
    end: object,
) -> int:
    """What becomes of one reached predecessor covering ``[start, end)`` —
    ``None`` both without Valid Time — whose nonempty successors lie over
    ``extents``, read only where the attempt ``owned`` it.

    A predecessor judged ``unchanged`` is kept wherever that is provable
    (:func:`_provable`): by a guard on its own address under Optimistic, and
    with no statement at all where the attempt opened it or Locking holds it.
    Otherwise one the attempt did not open is closed and every successor
    opened. One it opened is revised in place into the one successor ending
    where it ends — its complete physical address — wherever that successor
    executes the write's assignments or starts later, else left in place, and
    removed where no successor keeps its address."""
    if unchanged and _provable(owned=owned, gated=gated, guards=guards):
        return _PRESERVE if owned or not gated else _GUARD
    if not owned:
        return _CLOSE
    kept = _keeping((extent[1] for extent in extents), end)
    if kept is None:
        return _REMOVE
    kept_start, _kept_end, changed = extents[kept]
    disposal = _REVISE if changed or kept_start != start else _KEEP
    return disposal | kept << _KEPT_SHIFT


def _kept_index(code: int) -> int | None:
    """Which successor keeps an owned predecessor's address, in order."""
    disposal = code & _DISPOSAL
    if disposal in (_REVISE, _KEEP):
        return code >> _KEPT_SHIFT
    return None


def _changes(code: int) -> bool:
    """Whether the predecessor is closed, removed, or revised: the change to
    its observed state its write publishes."""
    return code & _DISPOSAL in (_CLOSE, _REMOVE, _REVISE)


def _own_step(
    facts: TemporalFacts,
    code: int,
    closing: PlannedClose,
    kept: WriteRow | None,
    predecessor: PredecessorRow | None,
) -> PlannedStep:
    """The one step of its own a predecessor of disposition ``code`` takes,
    addressed as ``closing`` addresses it: that close — decorated already — a
    guard proving it unchanged, its removal, or its revision into ``kept``,
    the successor keeping its address."""
    disposal = code & _DISPOSAL
    if disposal == _CLOSE:
        return closing
    if disposal == _GUARD:
        concurrency = closing.concurrency
        assert isinstance(concurrency, TemporalGate)  # only a gating write is proven by a guard
        return PlannedTemporalGuard(
            entity=closing.entity,
            target=closing.target,
            concurrency=concurrency,
            affected_rows=closing.affected_rows,
        )
    if disposal == _REMOVE:
        return PlannedTemporalRemoval(
            entity=closing.entity,
            target=closing.target,
            concurrency=closing.concurrency,
            affected_rows=closing.affected_rows,
        )
    assert disposal == _REVISE and kept is not None and predecessor is not None
    return PlannedTemporalRevision(
        entity=closing.entity,
        target=closing.target,
        assignments=_revision_assignments(facts, kept, predecessor),
        concurrency=closing.concurrency,
        affected_rows=closing.affected_rows,
        predecessor_document_is_object=isinstance(predecessor.document, Mapping),
    )


def _interval(start: object, end: object) -> TimeInterval | None:
    """The Valid Time ``[start, end)`` — ``None`` both without Valid Time."""
    if start is None:
        return None
    return TimeInterval(cast("dt.datetime", start), cast("TemporalBound", end))


def _complete(successors: Sequence[Successor], coverage: TimeInterval) -> bool:
    """Whether ``successors``, in order, cover exactly ``coverage``, each
    meeting the next."""
    if not successors:
        return False
    first = successors[0].valid_time_coverage
    last = successors[-1].valid_time_coverage
    assert first is not None and last is not None  # Bitemporal successors lie on Valid Time
    if first.start != coverage.start or last.end != coverage.end:
        return False
    previous = first
    for successor in successors[1:]:
        extent = successor.valid_time_coverage
        assert extent is not None  # Bitemporal successors lie on Valid Time
        if not previous.meets(extent):
            return False
        previous = extent
    return True


def _successor_row(
    facts: TemporalFacts,
    predecessor: PredecessorRow,
    valid_start: object,
    valid_end: object,
    *,
    assigned: _Overlay | None = None,
    executed: ExecutedMembers = (),
) -> WriteRow:
    """One successor of ``predecessor`` over ``[valid_start, valid_end)`` —
    ignored without Valid Time — as the row it represents.

    A successor starts from its predecessor's own cells. A carried one keeps
    them all (:class:`CarriedFrom`); a changed one (:class:`ChangedFrom`)
    overlays every ``assigned`` member, whatever value the predecessor already
    holds there, and states them as its ``executed`` members.
    """
    attributes, value_objects = predecessor.identity_maps(facts.view.member_selection)
    return _represented(
        facts,
        attributes,
        value_objects,
        valid_start,
        valid_end,
        CarriedFrom(predecessor=predecessor)
        if assigned is None
        else ChangedFrom(predecessor=predecessor),
        assigned=assigned,
        executed=executed,
    )


def _represented(
    facts: TemporalFacts,
    attributes: dict[AttributeIdentity, PlannedValue],
    value_objects: dict[ValueObjectIdentity, object],
    valid_start: object,
    valid_end: object,
    origin: RowOrigin,
    *,
    assigned: _Overlay | None = None,
    executed: ExecutedMembers = (),
) -> WriteRow:
    """The row a write produces over ``[valid_start, valid_end)`` from its
    starting ``attributes`` and ``value_objects``, which it adopts: a
    predecessor's cells or a new lineage's authored state, with ``assigned``
    overlaid and the row stamped as every opened row is."""
    if assigned is not None:
        attributes.update(assigned[0])
        value_objects.update(assigned[1])
    _stamp(facts, attributes, valid_start, valid_end)
    return WriteRow(
        row=adopt_planned_row(attributes, value_objects), origin=origin, executed=executed
    )


def _in_member_order(
    facts: TemporalFacts, members: Iterable[AttributeIdentity | ValueObjectIdentity]
) -> ExecutedMembers:
    """``members`` in the Entity's member order, so one assignment set selects
    one sequence however it was authored."""
    return tuple(sorted(members, key=facts.view.member_selection.index.__getitem__))


def opening(
    facts: TemporalFacts,
    attributes: dict[AttributeIdentity, PlannedValue],
    value_objects: dict[ValueObjectIdentity, object],
    valid_time_window: TimeInterval | None,
) -> WriteRow:
    """A new lineage's row: resolved authored ``attributes`` and
    ``value_objects``, which it adopts, over ``valid_time_window`` — ``None``
    without Valid Time — stamped as every opened row is."""
    if valid_time_window is None:
        return _represented(facts, attributes, value_objects, None, None, NEW_LINEAGE)
    return _represented(
        facts,
        attributes,
        value_objects,
        valid_time_window.start,
        valid_time_window.end,
        NEW_LINEAGE,
    )


def _stamp(
    facts: TemporalFacts,
    attributes: dict[AttributeIdentity, object],
    valid_start: object,
    valid_end: object,
) -> None:
    """Write an opened row's temporal bounds. Every opened row carries the fresh
    Transaction-Time interval ``[instant, infinity)``: it is current when it is
    written, whatever Valid Time it covers."""
    shape = facts.shape
    if isinstance(shape, Bitemporal):
        valid_time = shape.valid_time
        attributes[valid_time.start_attribute] = valid_start
        attributes[valid_time.end_attribute] = valid_end
    transaction_time = shape.transaction_time
    attributes[transaction_time.start_attribute] = facts.instant
    attributes[transaction_time.end_attribute] = INFINITY


def _keeping(ends: Iterable[object], end: object) -> int | None:
    """Which of a row's successors, by the Valid-Time ``ends`` they reach in
    order, keeps the row's complete physical address: the one ending where the
    row ends, ``end`` — ``None`` throughout without Valid Time, where the one
    successor keeps it. Successors are disjoint and nonempty, so at most one
    does; ``None`` where none does. No successor assigns the key, and the
    Transaction-Time end is invariantly open."""
    for index, successor_end in enumerate(ends):
        if successor_end == end:
            return index
    return None


def _valid_end(coverage: TimeInterval | None) -> object:
    return None if coverage is None else coverage.end


def _revision_assignments(
    facts: TemporalFacts, write_row: WriteRow, predecessor: PredecessorRow
) -> PlannedAssignments:
    """What revising ``predecessor`` in place into ``write_row``'s state
    assigns, once :func:`_disposition` decided to revise it: the successor
    keeping its address executes assignments or starts later.

    Every member the row executes, plus a moved Valid-Time start. The key, every
    axis end, and the Transaction-Time start belong to the address the revision
    preserves.
    """
    shape = facts.shape
    addressed = _addressed(facts)
    row = write_row.row
    attributes: dict[AttributeIdentity, PlannedValue] = {}
    value_objects: dict[ValueObjectIdentity, object] = {}
    for member in write_row.executed:
        if isinstance(member, ValueObjectIdentity):
            value_objects[member] = row.value_objects[member]
        elif member not in addressed:
            attributes[member] = row.attributes[member]
    if isinstance(shape, Bitemporal):
        valid_start = shape.valid_time.start_attribute
        moved_to = row.attributes[valid_start]
        if moved_to != predecessor.cell(valid_start):
            attributes[valid_start] = moved_to
    assert attributes or value_objects  # payload construction never reverses the decision
    return adopt_planned_assignments(attributes, value_objects)


def _revises(facts: TemporalFacts, write_row: WriteRow, predecessor: PredecessorRow) -> bool:
    """Whether revising ``predecessor`` in place into ``write_row`` assigns
    anything (:func:`_revision_assignments`)."""
    shape = facts.shape
    if isinstance(shape, Bitemporal):
        valid_start = shape.valid_time.start_attribute
        if write_row.row.attributes[valid_start] != predecessor.cell(valid_start):
            return True
    addressed = _addressed(facts)
    return any(member not in addressed for member in write_row.executed)


def _addressed(facts: TemporalFacts) -> frozenset[AttributeIdentity]:
    """The members of a row's physical address a same-address revision keeps:
    the key, every axis end, and the Transaction-Time start."""
    shape = facts.shape
    transaction_time = shape.transaction_time
    address = (
        facts.view.primary_key.identity,
        transaction_time.start_attribute,
        transaction_time.end_attribute,
    )
    if isinstance(shape, Bitemporal):
        return frozenset((*address, shape.valid_time.end_attribute))
    return frozenset(address)


def openings(
    facts: TemporalFacts, inserts: Sequence[PlannedInsert]
) -> tuple[TemporalRowCoordinates, ...]:
    """The owned address of every row ``inserts`` opens whose key is known."""
    endpoints: list[TemporalRowCoordinates] = []
    for insert in inserts:
        for entry in insert.entries:
            endpoint = entry_endpoint(facts, entry)
            if endpoint is not None:
                endpoints.append(endpoint)
    return tuple(endpoints)


def entry_endpoint(facts: TemporalFacts, entry: WriteRow) -> TemporalRowCoordinates | None:
    attributes = entry.row.attributes
    value = attributes.get(facts.view.primary_key.identity)
    # A key the database allocates is named only once its insert answers it.
    if value is None or isinstance(value, MaxPlusOne):
        return None
    return TemporalRowCoordinates(facts.entity.identity, (value,), entry_ends(facts, attributes))


def entry_ends(
    facts: TemporalFacts, attributes: Mapping[AttributeIdentity, PlannedValue]
) -> tuple[TemporalUpperBound, ...]:
    shape = facts.shape
    if isinstance(shape, Bitemporal):
        return bitemporal_ends(attributes[shape.valid_time.end_attribute])
    return TRANSACTION_TIME_ENDS


def _target_endpoint(facts: TemporalFacts, target: MilestoneTarget) -> TemporalRowCoordinates:
    return TemporalRowCoordinates(facts.entity.identity, target.key_values, target.end_values)


def bitemporal_ends(valid_end: object) -> tuple[TemporalUpperBound, ...]:
    if valid_end is TemporalBound.INFINITY:
        return OPEN_BITEMPORAL_ENDS
    return (Finite(instant=valid_end), OPEN_UPPER_BOUND)


def _planned_close(
    facts: TemporalFacts,
    *,
    key_attributes: tuple[AttributeIdentity, ...],
    key_values: tuple[object, ...],
    observed_valid_end: object | None,
    cause: CloseCause,
    gate: TemporalConcurrency,
    assignments: PlannedAssignments,
    end_attributes: tuple[AttributeIdentity, ...],
    affected_rows: ExactCount,
) -> PlannedClose:
    """One settled close of the current milestone ``key_values`` addresses.

    Its assignments carry the Transaction-Time end alone — a close ends a
    milestone's currency and revises no represented value — and it expects
    exactly one row in every mode: a close reaching none would otherwise chain
    a duplicate or an orphaned current row, so the shortfall is an outcome
    rather than a silent success. ``assignments``, ``end_attributes``, and
    ``affected_rows`` are what every close of the object shares.
    """
    entity = facts.entity
    shape = facts.shape
    return PlannedClose(
        entity=entity.identity,
        target=MilestoneTarget(
            key_attributes=key_attributes,
            key_values=key_values,
            end_attributes=end_attributes,
            end_values=_end_values(shape, observed_valid_end),
        ),
        assignments=assignments,
        cause=cause,
        concurrency=gate,
        affected_rows=affected_rows,
    )


def _end_attributes(shape: TransactionTimeOnly | Bitemporal) -> tuple[AttributeIdentity, ...]:
    """One exclusive-end Attribute per As-Of Axis, in canonical order."""
    match shape:
        case TransactionTimeOnly(transaction_time=transaction_time):
            return (transaction_time.end_attribute,)
        case Bitemporal(valid_time=valid_time, transaction_time=transaction_time):
            return (valid_time.end_attribute, transaction_time.end_attribute)


def _end_values(
    shape: TransactionTimeOnly | Bitemporal,
    observed_valid_end: object | None,
) -> tuple[TemporalUpperBound, ...]:
    """One exclusive upper bound per As-Of Axis, in canonical order.

    Transaction Time is invariantly `Infinity`, which is what keeps an
    operational close on a row still current. Valid Time is whatever the
    observed predecessor carries — `Infinity` for a rectangle running to the
    open bound, and a finite instant for a bounded one a prior split left
    behind, so binding a constant on both axes would silently miss every
    bounded sibling.
    """
    if isinstance(shape, TransactionTimeOnly):
        return TRANSACTION_TIME_ENDS
    assert observed_valid_end is not None  # every Bitemporal predecessor covers Valid Time
    return bitemporal_ends(observed_valid_end)
