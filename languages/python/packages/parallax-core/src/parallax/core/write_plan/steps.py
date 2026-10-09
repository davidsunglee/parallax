from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    ValueObjectIdentity,
)
from parallax.core.predicate._resolved import ResolvedPredicate
from parallax.core.write_plan.observe import PredecessorRow

if TYPE_CHECKING:
    from parallax.core.write_plan.payload import RowPayload

__all__ = [
    "ANY_COUNT",
    "FAILED_PRECONDITION",
    "INFINITY",
    "MAX_PLUS_ONE",
    "NEW_LINEAGE",
    "RETURNED_MAX_PLUS_ONE",
    "SUPERSEDED",
    "TERMINATED",
    "UNGATED",
    "UNVERSIONED",
    "AffectedRows",
    "AnyCount",
    "CarriedFrom",
    "ChangedFrom",
    "CloseCause",
    "ExactCount",
    "FailedPrecondition",
    "Finite",
    "KeyTarget",
    "MaxPlusOne",
    "MilestoneTarget",
    "MissingTarget",
    "NewLineage",
    "NonTemporalConcurrency",
    "OptimisticConflict",
    "PlannedAssignments",
    "PlannedClose",
    "PlannedDelete",
    "PlannedInsert",
    "PlannedRow",
    "PlannedTemporalGuard",
    "PlannedTemporalRemoval",
    "PlannedTemporalRevision",
    "PlannedUpdate",
    "PlannedValue",
    "PlannedWrite",
    "ResolvedMutationSelection",
    "RowOrigin",
    "SelfIncrement",
    "Shortfall",
    "StaleWrite",
    "TemporalConcurrency",
    "TemporalGate",
    "TemporalUpperBound",
    "VersionGate",
    "Versioned",
    "WriteRow",
    "WriteTarget",
    "admits_shortfall",
    "adopt_planned_assignments",
    "adopt_planned_row",
    "assignments_added",
    "shortfall_classification",
    "shortfall_for",
]


@dataclass(frozen=True, slots=True)
class MaxPlusOne:
    """The `max` primary-key allocation (m-pk-gen), as a planned cell value.

    The allocation folds into the emitted statement rather than binding a
    literal, so the planner decides *that* a cell is allocated this way and
    lowering decides how that reads in one dialect. A ``returned`` allocation
    is one the statement also answers, because the row it opens is recorded by
    its complete address and nothing else names the key.
    """

    returned: bool = False


MAX_PLUS_ONE: Final[MaxPlusOne] = MaxPlusOne()
RETURNED_MAX_PLUS_ONE: Final[MaxPlusOne] = MaxPlusOne(returned=True)


@dataclass(frozen=True, slots=True)
class SelfIncrement:
    """The `sequence` registry advance (m-pk-gen), as a planned cell value.

    The new value is the stored one plus ``amount``, computed by the database
    from the row it is advancing, so no reader supplies a prior value and no
    literal is bound for the result.
    """

    amount: int


type GeneratedValueExpression = MaxPlusOne | SelfIncrement
"""The closed set of database-computed cell values a planned cell may carry.

A generated value is decided during planning, from the target's declared
primary-key generation strategy, so no consumer re-classifies an authored
marker document by its shape. Both variants are `m-pk-gen` allocations: one
allocates at the position an insert opens, the other advances the registry an
update maintains. Each is legal only where the statement that renders it can
express it, and the two carriers enforce that between them: a Planned Row
admits only :class:`MaxPlusOne`, Planned Assignments only :class:`SelfIncrement`.
"""

type PlannedValue = object
"""One planned cell: a neutral value, an explicit null, or a
:data:`GeneratedValueExpression`.

Python carries every neutral value natively, so the alias names the position
rather than narrowing it; the generated-value arm is the only one a consumer
distinguishes structurally.
"""


@dataclass(frozen=True, slots=True)
class NewLineage:
    """An insert that begins a new Provenance Lineage."""


NEW_LINEAGE: Final[NewLineage] = NewLineage()


@dataclass(frozen=True, slots=True)
class CarriedFrom:
    """An insert whose represented state is its predecessor's, unchanged.

    A Bitemporal head or tail survivor and the surviving rectangles of a
    terminate all carry state this way: the mutation moved where the state
    applies without altering it.
    """

    predecessor: PredecessorRow


@dataclass(frozen=True, slots=True)
class ChangedFrom:
    """An insert whose represented state revises its predecessor's.

    The row holds the predecessor's own cells at every member nothing assigns,
    and its Write Row names what was assigned (:attr:`WriteRow.executed`), so
    an assignment equal to the stored value is still one the row executes.
    """

    predecessor: PredecessorRow


type ExecutedMembers = tuple[AttributeIdentity | ValueObjectIdentity, ...]
"""The members a Write Row states explicitly, each holding the value its row
holds, in its Entity's member order; rows the same assignments reach share one
selection."""

type RowOrigin = NewLineage | CarriedFrom | ChangedFrom
"""Where one Write Row's represented state came from.

Origin belongs to each row rather than to the whole step or to a parallel
array, so entries of different origins may share one Planned Insert.
"""


@dataclass(frozen=True, slots=True)
class PlannedRow:
    """The immutable, duplicate-free semantic contents of one Write Row.

    ``attributes`` holds every scalar member the row writes — including the
    framework-owned values the planner derived, which no caller authors — and
    ``value_objects`` holds one complete occurrence per top-level Value Object
    member. Both are frozen at construction; a row carrying no member at all is
    refused, because it names nothing to write. The only generated value an
    opening statement can express is the `max` allocation it folds in.
    """

    attributes: Mapping[AttributeIdentity, PlannedValue]
    value_objects: Mapping[ValueObjectIdentity, object] = field(
        default_factory=dict[ValueObjectIdentity, object]
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))
        object.__setattr__(self, "value_objects", MappingProxyType(dict(self.value_objects)))
        _validate_planned_row(self.attributes, self.value_objects)

    @property
    def members(self) -> frozenset[AttributeIdentity | ValueObjectIdentity]:
        """Every member identity this row writes, scalar and Value Object alike."""
        return frozenset(self.attributes) | frozenset(self.value_objects)


@dataclass(frozen=True, slots=True)
class WriteRow:
    """One represented row's state before settlement chooses how it is
    realized, and the origin of that state.

    ``executed`` names the members the row states explicitly — its authored
    assignments and the audit values finalization added — whose values are the
    row's own, shared by every row the same assignments reach. Every other
    member of a carried or changed row is its predecessor's own state. A new
    lineage writes every member it holds either way.

    ``prepared`` is persisted backing a payload preparer already derived from
    this row, which lowering reuses. It is not part of the row's meaning, so
    equality ignores it.
    """

    row: PlannedRow
    origin: RowOrigin
    executed: ExecutedMembers = ()
    prepared: RowPayload | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        row = self.row
        if not self.executed and isinstance(self.origin, ChangedFrom):
            raise ValueError("a changed Write Row names the members it executes")
        for member in self.executed:
            if member not in (
                row.attributes if isinstance(member, AttributeIdentity) else row.value_objects
            ):
                raise ValueError(f"{member}: an executed member is one its Write Row holds")

    def with_prepared(self, prepared: RowPayload) -> WriteRow:
        """This row carrying ``prepared``, which a preparer derived from it."""
        if not prepared.prepared_from(self):
            raise ValueError("a Write Row carries only the payload prepared from it")
        return replace(self, prepared=prepared)


@dataclass(frozen=True, slots=True)
class PlannedInsert:
    """One or more new rows of one Entity, planned as a single execution step.

    Membership *is* the batching decision, so there is no batch flag and no
    group identifier: every entry of one step names the same members and the
    same generated-value shape, and incompatible entries form separate steps.
    A Planned Insert carries no Write Target, no gate, and no Affected Rows
    Policy.
    """

    entity: EntityIdentity
    entries: tuple[WriteRow, ...]

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError(
                f"{self.entity.canonical}: a Planned Insert carries at least one entry"
            )
        first = self.entries[0].row
        for entry in self.entries[1:]:
            if entry.row.members != first.members:
                raise ValueError(
                    f"{self.entity.canonical}: every entry of one Planned Insert names the "
                    "same members, and these differ"
                )
            if _generated_values(entry.row) != _generated_values(first):
                raise ValueError(
                    f"{self.entity.canonical}: every entry of one Planned Insert carries the "
                    "same generated-value shape, and these differ"
                )


def _generated_values(row: PlannedRow) -> dict[AttributeIdentity, GeneratedValueExpression]:
    return {
        identity: value
        for identity, value in row.attributes.items()
        if isinstance(value, (MaxPlusOne, SelfIncrement))
    }


@dataclass(frozen=True, slots=True)
class PlannedAssignments:
    """The immutable, duplicate-free replacement values one revising step writes.

    Unlike a Planned Row this names only the members the step changes, including
    the framework-owned advance a versioned update derives; the members it does
    not name keep their stored values. It carries no authored assignment
    expression — nothing a caller composes out of the Predicate algebra — and the
    only expression it admits at all is the `m-pk-gen` registry advance, which a
    revising statement computes from the very row it is rewriting.
    """

    attributes: Mapping[AttributeIdentity, PlannedValue]
    value_objects: Mapping[ValueObjectIdentity, object] = field(
        default_factory=dict[ValueObjectIdentity, object]
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))
        object.__setattr__(self, "value_objects", MappingProxyType(dict(self.value_objects)))
        _validate_planned_assignments(self.attributes, self.value_objects)

    @property
    def members(self) -> frozenset[AttributeIdentity | ValueObjectIdentity]:
        """Every member identity this step assigns, scalar and Value Object alike."""
        return frozenset(self.attributes) | frozenset(self.value_objects)


def adopt_planned_row(
    attributes: Mapping[AttributeIdentity, PlannedValue],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> PlannedRow:
    """Adopt trusted final row storage without copying its shallow maps."""
    row = object.__new__(PlannedRow)
    object.__setattr__(row, "attributes", _adopt_mapping(attributes))
    object.__setattr__(row, "value_objects", _adopt_mapping(value_objects))
    _validate_planned_row(row.attributes, row.value_objects)
    return row


def adopt_planned_assignments(
    attributes: Mapping[AttributeIdentity, PlannedValue],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> PlannedAssignments:
    """Adopt trusted final assignment storage without copying its shallow maps."""
    assignments = object.__new__(PlannedAssignments)
    object.__setattr__(assignments, "attributes", _adopt_mapping(attributes))
    object.__setattr__(assignments, "value_objects", _adopt_mapping(value_objects))
    _validate_planned_assignments(assignments.attributes, assignments.value_objects)
    return assignments


def _validate_planned_row(
    attributes: Mapping[AttributeIdentity, PlannedValue],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> None:
    if not attributes and not value_objects:
        raise ValueError("a Planned Row carries at least one member")
    for identity, value in attributes.items():
        if isinstance(value, SelfIncrement):
            raise ValueError(
                f"{identity.name}: the registry advance is computed from the stored row "
                "it revises, so it is a Planned Assignment and never a Planned Row cell"
            )


def _validate_planned_assignments(
    attributes: Mapping[AttributeIdentity, PlannedValue],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> None:
    if not attributes and not value_objects:
        raise ValueError("Planned Assignments name at least one member to write")
    for identity, value in attributes.items():
        if isinstance(value, MaxPlusOne):
            raise ValueError(
                f"{identity.name}: the `max` allocation folds into the row an insert "
                "opens, so it is a Planned Row cell and never a Planned Assignment"
            )


def _adopt_mapping[K, V](values: Mapping[K, V]) -> Mapping[K, V]:
    if isinstance(values, MappingProxyType):
        return values
    if not isinstance(values, dict):
        raise TypeError("trusted planned storage must be a final dict or mapping proxy")
    return MappingProxyType(values)


@dataclass(frozen=True, slots=True)
class KeyTarget:
    """A selection of whole rows by primary key.

    The canonical key shape is stored once and each addressed row contributes one
    aligned value tuple, in planner order. A singleton and a compatible multi-key
    selection are cardinalities of one target kind, not two.
    """

    key_attributes: tuple[AttributeIdentity, ...]
    key_values: tuple[tuple[object, ...], ...]

    def __post_init__(self) -> None:
        if not self.key_attributes:
            raise ValueError("a Key Target names at least one primary-key Attribute")
        if not self.key_values:
            raise ValueError("a Key Target addresses at least one row")
        arity = len(self.key_attributes)
        for values in self.key_values:
            if len(values) != arity:
                raise ValueError(
                    f"a Key Target's every value tuple is complete: expected {arity} value(s), "
                    f"got {len(values)}"
                )
            for value in values:
                if value is None or isinstance(value, Mapping):
                    raise ValueError(
                        f"a Key Target's key values are concrete and non-null, and {value!r} is not"
                    )
        if len(set(self.key_values)) != len(self.key_values):
            raise ValueError(
                "a Key Target's addressed rows are distinct — a repeated authored key is "
                "invalid rather than silently deduplicated"
            )


@dataclass(frozen=True, slots=True)
class ResolvedMutationSelection:
    """A resolved mutation target and its occurrence-local semantic predicate.

    It carries the predicate and nothing else: the enclosing step already names
    the Entity, and a Resolved Mutation Selection's presence already implies an unversioned
    Non-Temporal step, an unbounded expected effect, and ordering-barrier
    behavior.
    """

    target: EntityMetadata
    predicate: ResolvedPredicate


@dataclass(frozen=True, slots=True)
class Finite:
    """A finite exclusive upper bound on one As-Of Axis."""

    instant: object


@dataclass(frozen=True, slots=True)
class Infinity:
    """The open exclusive upper bound: the axis runs on without end."""


INFINITY: Final[Infinity] = Infinity()

type TemporalUpperBound = Finite | Infinity
"""One axis's write-required exclusive upper bound in a Milestone Target."""


@dataclass(frozen=True, slots=True)
class MilestoneTarget:
    """The current milestone slot one close, revision, removal, or guard addresses.

    The address is one complete key tuple plus one exclusive upper bound per
    As-Of Axis, in canonical axis order: the observed predecessor's Valid-Time
    end where that axis exists, and the invariant `Infinity` for Transaction
    Time. The Valid-Time end may be finite — a bounded rectangle a prior split
    left behind — and binding a constant `Infinity` on both axes would address
    the open rectangle and silently miss every bounded sibling.

    It carries no axis start, gate, observation, or concurrency mode, and it is
    derived identically in both concurrency modes; only the gate differs.
    """

    key_attributes: tuple[AttributeIdentity, ...]
    key_values: tuple[object, ...]
    end_attributes: tuple[AttributeIdentity, ...]
    end_values: tuple[TemporalUpperBound, ...]

    def __post_init__(self) -> None:
        if not self.key_attributes:
            raise ValueError("a Milestone Target names at least one primary-key Attribute")
        if len(self.key_values) != len(self.key_attributes):
            raise ValueError(
                "a Milestone Target addresses one complete key tuple: expected "
                f"{len(self.key_attributes)} value(s), got {len(self.key_values)}"
            )
        for value in self.key_values:
            if value is None or isinstance(value, Mapping):
                raise ValueError(
                    f"a Milestone Target's key values are concrete and non-null, and {value!r} "
                    "is not"
                )
        if not self.end_attributes:
            raise ValueError(
                "a Milestone Target names one exclusive upper bound per As-Of Axis, and a "
                "temporal target declares at least one"
            )
        if len(set(self.end_attributes)) != len(self.end_attributes):
            raise ValueError("a Milestone Target names each As-Of Axis end at most once")
        if len(self.end_values) != len(self.end_attributes):
            raise ValueError(
                "a Milestone Target binds one upper bound per named axis end: expected "
                f"{len(self.end_attributes)} value(s), got {len(self.end_values)}"
            )


type WriteTarget = KeyTarget | ResolvedMutationSelection | MilestoneTarget
"""The semantic row selection of a Planned Write, distinct from observed
predecessor state and from any concurrency condition."""


@dataclass(frozen=True, slots=True)
class VersionGate:
    """The extra equality predicate an optimistic-mode versioned write renders.

    It carries only what the predicate binds. The version Attribute it compares
    is named once by the enclosing :class:`Versioned` decision, the advanced
    version is an assignment rather than a gate member, and the transaction's
    concurrency mode is consumed while the gate is being decided rather than
    repeated here.
    """

    observed_version: int


@dataclass(frozen=True, slots=True)
class TemporalGate:
    """The extra equality predicate an optimistic-mode close renders.

    A temporal Entity carries no version column, so the observed
    Transaction-Time start of the milestone being closed is the version
    analogue: a concurrently chained current row carries a newer start and the
    gate matches nothing.
    """

    start_attribute: AttributeIdentity
    observed_start: object


@dataclass(frozen=True, slots=True)
class Ungated:
    """The explicit decision that a step renders no gate predicate.

    Locking mode records this rather than a null gate, which is what makes gate
    applicability structural.
    """


UNGATED: Final[Ungated] = Ungated()

type TemporalConcurrency = TemporalGate | Ungated
"""The settled concurrency decision a Planned Close carries.

Every close requires a temporal observation, so a close has no unversioned case
and carries the gate decision directly.
"""


@dataclass(frozen=True, slots=True)
class Unversioned:
    """The target declares no optimistic-lock version, so no gate can apply."""


UNVERSIONED: Final[Unversioned] = Unversioned()


@dataclass(frozen=True, slots=True)
class Versioned:
    """The target declares an optimistic-lock version, and the mode decided the
    gate.

    ``attribute`` is the version Attribute planning settled, which both
    concurrency modes advance and only a :class:`VersionGate` compares.
    """

    attribute: AttributeIdentity
    gate: VersionGate | Ungated


type NonTemporalConcurrency = Unversioned | Versioned
"""The settled concurrency decision a Planned Update or Planned Delete carries."""


@dataclass(frozen=True, slots=True)
class MissingTarget:
    """The addressed rows do not all exist."""


MISSING_TARGET: Final[MissingTarget] = MissingTarget()


@dataclass(frozen=True, slots=True)
class StaleWrite:
    """An ungated observation-requiring write reached fewer rows than it observed."""


STALE_WRITE: Final[StaleWrite] = StaleWrite()


@dataclass(frozen=True, slots=True)
class OptimisticConflict:
    """A gated write's condition no longer holds."""


OPTIMISTIC_CONFLICT: Final[OptimisticConflict] = OptimisticConflict()


@dataclass(frozen=True, slots=True)
class FailedPrecondition:
    """A gate binding a caller's stated starting revision no longer held: the
    state the caller addressed is gone, or a later revision replaced it."""


FAILED_PRECONDITION: Final[FailedPrecondition] = FailedPrecondition()

type Shortfall = MissingTarget | StaleWrite | OptimisticConflict | FailedPrecondition
"""The neutral outcome class a shortfall against an exact count names.

The plan names an outcome class, never a language's exception type.
"""


@dataclass(frozen=True, slots=True)
class AnyCount:
    """No expectation: any number of affected rows, zero included, succeeds."""


ANY_COUNT: Final[AnyCount] = AnyCount()


@dataclass(frozen=True, slots=True)
class ExactCount:
    """Exactly ``expected`` rows must be affected.

    ``on_shortfall`` classifies a smaller count. An excess is always Cardinality
    Corruption — an invariant failure rather than a concurrency outcome — so it
    is not one of the shortfall tags and is never carried here.
    """

    expected: int
    on_shortfall: Shortfall

    def __post_init__(self) -> None:
        if self.expected < 1:
            raise ValueError(f"an exact affected-row count is positive, got {self.expected}")


type AffectedRows = AnyCount | ExactCount
"""The fully resolved Affected Rows Policy every surviving non-insert step
carries before lowering."""


def shortfall_classification(*, observing: bool, gated: bool) -> Shortfall:
    """How a shortfall classifies from the two facts that decide it.

    Classification follows the settled **gate**, never the verb (ADR 0044/0047):
    a gated shortfall is the detected lost update a re-read could resolve; an
    ungated one on an observation-requiring write is the non-retriable stale
    outcome, since no gate could have caused it; and an observation-free keyed
    write observed nothing, so its shortfall says only that the addressed rows
    are not there. One decision therefore admits exactly one classification,
    which is why every addressed step derives it rather than accepting it.

    Both facts are settled per mutation, before any row of it is observed, so a
    caller holding them answers here directly rather than standing a version in
    for one it has not seen. :func:`shortfall_for` is the same rule read off a
    concrete decision.
    """
    if not observing:
        return MISSING_TARGET
    return OPTIMISTIC_CONFLICT if gated else STALE_WRITE


def admits_shortfall(
    concurrency: NonTemporalConcurrency | TemporalConcurrency, shortfall: Shortfall
) -> bool:
    """Whether ``shortfall`` classifies a shortfall against ``concurrency``: the
    classification :func:`shortfall_for` derives, or — where the decision gates
    — a failed precondition, because a gate may bind a caller's stated revision
    rather than an observation."""
    if shortfall == shortfall_for(concurrency):
        return True
    gated = isinstance(concurrency, TemporalGate) or (
        isinstance(concurrency, Versioned) and isinstance(concurrency.gate, VersionGate)
    )
    return gated and isinstance(shortfall, FailedPrecondition)


def shortfall_for(concurrency: NonTemporalConcurrency | TemporalConcurrency) -> Shortfall:
    """How a shortfall against one settled concurrency decision classifies.

    The rule is uniform across update, delete, and close, so a versioned write's
    decision and a close's bare gate decision answer through one function: this
    reads the two deciding facts off the decision's shape and
    :func:`shortfall_classification` applies them.
    """
    match concurrency:
        case Unversioned():
            return shortfall_classification(observing=False, gated=False)
        case Versioned(gate=gate):
            return shortfall_classification(observing=True, gated=isinstance(gate, VersionGate))
        case TemporalGate():
            return shortfall_classification(observing=True, gated=True)
        case Ungated():
            return shortfall_classification(observing=True, gated=False)


def _settle(
    entity: EntityIdentity,
    target: WriteTarget,
    concurrency: NonTemporalConcurrency,
    affected_rows: AffectedRows,
) -> None:
    """Refuse a target, concurrency decision, and expected effect that cannot
    describe one row selection together."""
    match target:
        case MilestoneTarget():
            raise ValueError(
                f"{entity.canonical}: a Milestone Target addresses a temporal milestone, so it "
                "belongs to a Planned Close, a Planned Temporal Revision, Removal, or Guard — "
                "never to a Non-Temporal update or delete"
            )
        case ResolvedMutationSelection():
            if not isinstance(concurrency, Unversioned) or not isinstance(affected_rows, AnyCount):
                raise ValueError(
                    f"{entity.canonical}: a Resolved Mutation Selection is readless, "
                    "so it implies "
                    "Unversioned concurrency and an unbounded expected effect"
                )
        case KeyTarget():
            if not isinstance(affected_rows, ExactCount) or affected_rows.expected != len(
                target.key_values
            ):
                raise ValueError(
                    f"{entity.canonical}: a Key Target expects exactly as many rows as it "
                    f"addresses ({len(target.key_values)})"
                )
            if not admits_shortfall(concurrency, affected_rows.on_shortfall):
                raise ValueError(
                    f"{entity.canonical}: the concurrency decision classifies a shortfall as "
                    f"{type(shortfall_for(concurrency)).__name__}, and this policy says "
                    f"{type(affected_rows.on_shortfall).__name__}"
                )
            if (
                isinstance(concurrency, Versioned)
                and isinstance(concurrency.gate, VersionGate)
                and len(target.key_values) != 1
            ):
                raise ValueError(
                    f"{entity.canonical}: a Version Gate binds one row's observed version, so "
                    "it requires a singleton Key Target"
                )


@dataclass(frozen=True, slots=True)
class PlannedUpdate:
    """A revision of existing Non-Temporal rows in place.

    Its assignments are uniform across every row its target selects; differing
    per-key assignments remain distinct steps. Being a Planned Update already
    carries the fact that existing rows were revised, so there is nothing to
    label.
    """

    entity: EntityIdentity
    target: WriteTarget
    assignments: PlannedAssignments
    concurrency: NonTemporalConcurrency
    affected_rows: AffectedRows

    def __post_init__(self) -> None:
        _settle(self.entity, self.target, self.concurrency, self.affected_rows)


@dataclass(frozen=True, slots=True)
class PlannedDelete:
    """A physical removal of existing Non-Temporal rows.

    It carries no row, assignments, predecessor, Row Origin, or Close Cause:
    represented-state absence on a temporal target is a close, not a delete.
    """

    entity: EntityIdentity
    target: WriteTarget
    concurrency: NonTemporalConcurrency
    affected_rows: AffectedRows

    def __post_init__(self) -> None:
        _settle(self.entity, self.target, self.concurrency, self.affected_rows)


@dataclass(frozen=True, slots=True)
class Superseded:
    """The closed milestone was replaced by newer represented state."""


SUPERSEDED: Final[Superseded] = Superseded()


@dataclass(frozen=True, slots=True)
class Terminated:
    """The closed milestone's represented state ended.

    A Bitemporal terminate may still leave head or tail survivors; the cause
    records the absence the mutation created, and each survivor is
    independently carried.
    """


TERMINATED: Final[Terminated] = Terminated()

type CloseCause = Superseded | Terminated
"""Why one current milestone stopped being current."""


@dataclass(frozen=True, slots=True)
class PlannedClose:
    """The close of one current temporal milestone.

    Its assignments carry the Transaction-Time end alone: a close ends a
    milestone's currency and revises no represented value, because the new state
    arrives as its Planned Insert successors. Its expected effect is always
    exactly one row — a close that reaches none would otherwise chain a
    duplicate or an orphaned current row.
    """

    entity: EntityIdentity
    target: MilestoneTarget
    assignments: PlannedAssignments
    cause: CloseCause
    concurrency: TemporalConcurrency
    affected_rows: ExactCount

    def __post_init__(self) -> None:
        _require_one_milestone(self.entity, self.concurrency, self.affected_rows, "Planned Close")


def _require_one_milestone(
    entity: EntityIdentity, concurrency: TemporalConcurrency, affected_rows: ExactCount, kind: str
) -> None:
    if affected_rows.expected != 1:
        raise ValueError(
            f"{entity.canonical}: a {kind} addresses one current milestone, so it expects "
            f"exactly one row and this policy expects {affected_rows.expected}"
        )
    if not admits_shortfall(concurrency, affected_rows.on_shortfall):
        raise ValueError(
            f"{entity.canonical}: the concurrency decision classifies a shortfall as "
            f"{type(shortfall_for(concurrency)).__name__}, and this policy says "
            f"{type(affected_rows.on_shortfall).__name__}"
        )


@dataclass(frozen=True, slots=True)
class PlannedTemporalRevision:
    """An in-place revision of one current milestone this attempt opened.

    Its target is the row's complete physical address, which the revision
    preserves: it assigns writable payload and, on a Bitemporal row, the
    Valid-Time start, never the logical key, an axis end, or the
    Transaction-Time start. Only a row the attempt itself opened is revised in
    place; a row that existed before the attempt is closed instead, so its
    history survives.
    """

    entity: EntityIdentity
    target: MilestoneTarget
    assignments: PlannedAssignments
    concurrency: TemporalConcurrency
    affected_rows: ExactCount

    def __post_init__(self) -> None:
        _require_one_milestone(self.entity, self.concurrency, self.affected_rows, "revision")


@dataclass(frozen=True, slots=True)
class PlannedTemporalRemoval:
    """The physical removal of one current milestone this attempt opened.

    It removes uncommitted state of the attempt's own, which no history
    records; a row that existed before the attempt is closed instead.
    """

    entity: EntityIdentity
    target: MilestoneTarget
    concurrency: TemporalConcurrency
    affected_rows: ExactCount

    def __post_init__(self) -> None:
        _require_one_milestone(self.entity, self.concurrency, self.affected_rows, "removal")


@dataclass(frozen=True, slots=True)
class PlannedTemporalGuard:
    """The proof that one current milestone that existed before the attempt
    still stands as it was observed, for a write that leaves its represented
    state unchanged.

    It addresses the row exactly as a close would and gates on the same
    observed Transaction-Time start, but assigns nothing it represents: the
    milestone, its Transaction-Time start and its history stay as they are.
    Matching the row is the proof, so a database whose write count reports
    only rows an update changed cannot prove it (`m-dialect`), and the
    unchanged write is closed and chained instead.
    """

    entity: EntityIdentity
    target: MilestoneTarget
    concurrency: TemporalGate
    affected_rows: ExactCount

    def __post_init__(self) -> None:
        if not isinstance(self.concurrency, TemporalGate):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError(
                f"{self.entity.canonical}: a guard proves an observed Transaction-Time start, "
                "so it is gated"
            )
        _require_one_milestone(self.entity, self.concurrency, self.affected_rows, "guard")


type PlannedWrite = (
    PlannedInsert
    | PlannedUpdate
    | PlannedClose
    | PlannedDelete
    | PlannedTemporalRevision
    | PlannedTemporalRemoval
    | PlannedTemporalGuard
)
"""The closed algebra of finalized semantic execution steps."""


def assignments_added(
    stated: PlannedAssignments | None, final: PlannedAssignments | None
) -> PlannedAssignments | None:
    """The assignments ``final`` makes beyond ``stated``, which it keeps, or
    ``None`` where it makes no other.

    What an audit hook added to a row, close, or update, so compact backing can
    hold that alone and lay it over the value it rebuilds on demand.
    """
    if final is None or final is stated:
        return None
    if stated is None:
        return final
    attributes = {
        identity: value
        for identity, value in final.attributes.items()
        if identity not in stated.attributes
    }
    value_objects = {
        identity: value
        for identity, value in final.value_objects.items()
        if identity not in stated.value_objects
    }
    if not attributes and not value_objects:
        return None
    return adopt_planned_assignments(attributes, value_objects)
