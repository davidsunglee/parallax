"""The finalized Planned Write algebra (m-unit-work).

A Planned Write is one finalized semantic execution step: its target, row
topology, concurrency decision, and expected effect are all settled, so SQL
lowering answers a purely physical question about it. The algebra is **closed**
and **semantic** — it carries Attribute and Value Object identities, never a
physical column, dialect object, driver value, or SQL fragment — and it admits
no generic disposition field: an Insert Origin exists only on an insert entry,
so a label a variant could contradict is unrepresentable rather than merely
invalid.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from parallax.core.metamodel import AttributeIdentity, EntityIdentity, ValueObjectIdentity
from parallax.core.op_algebra import Operation

__all__ = [
    "ANY_COUNT",
    "MAX_PLUS_ONE",
    "MISSING_TARGET",
    "NEW_LINEAGE",
    "OPTIMISTIC_CONFLICT",
    "STALE_WRITE",
    "UNGATED",
    "UNVERSIONED",
    "AffectedRows",
    "AnyCount",
    "ExactCount",
    "GeneratedValueExpression",
    "InsertEntry",
    "InsertOrigin",
    "KeyTarget",
    "MaxPlusOne",
    "MissingTarget",
    "NewLineage",
    "NonTemporalConcurrency",
    "OptimisticConflict",
    "PlannedAssignments",
    "PlannedDelete",
    "PlannedInsert",
    "PlannedRow",
    "PlannedUpdate",
    "PlannedValue",
    "PlannedWrite",
    "PredicateTarget",
    "SelfIncrement",
    "Shortfall",
    "StaleWrite",
    "Ungated",
    "Unversioned",
    "VersionGate",
    "Versioned",
    "WriteTarget",
    "shortfall_for",
]


@dataclass(frozen=True, slots=True)
class MaxPlusOne:
    """The `max` primary-key allocation (m-pk-gen), as a planned cell value.

    The allocation folds into the emitted statement rather than binding a
    literal, so the planner decides *that* a cell is allocated this way and
    lowering decides how that reads in one dialect.
    """


MAX_PLUS_ONE: Final[MaxPlusOne] = MaxPlusOne()


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

type InsertOrigin = NewLineage
"""Where one insert entry's represented state came from.

Origin belongs to each entry rather than to the whole step or to a parallel
array, so entries of different origins may share one Planned Insert.
"""


@dataclass(frozen=True, slots=True)
class PlannedRow:
    """The immutable, duplicate-free semantic contents of one insert entry.

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
        if not self.attributes and not self.value_objects:
            raise ValueError("a Planned Row carries at least one member")
        for identity, value in self.attributes.items():
            if isinstance(value, SelfIncrement):
                raise ValueError(
                    f"{identity.name}: the registry advance is computed from the stored row "
                    "it revises, so it is a Planned Assignment and never a Planned Row cell"
                )

    @property
    def members(self) -> frozenset[AttributeIdentity | ValueObjectIdentity]:
        """Every member identity this row writes, scalar and Value Object alike."""
        return frozenset(self.attributes) | frozenset(self.value_objects)


@dataclass(frozen=True, slots=True)
class InsertEntry:
    """One row of a Planned Insert, with the origin of the state it carries."""

    row: PlannedRow
    origin: InsertOrigin


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
    entries: tuple[InsertEntry, ...]

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
    expression — nothing a caller composes out of the operation algebra — and the
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
        if not self.attributes and not self.value_objects:
            raise ValueError("Planned Assignments name at least one member to write")
        for identity, value in self.attributes.items():
            if isinstance(value, MaxPlusOne):
                raise ValueError(
                    f"{identity.name}: the `max` allocation folds into the row an insert "
                    "opens, so it is a Planned Row cell and never a Planned Assignment"
                )

    @property
    def members(self) -> frozenset[AttributeIdentity | ValueObjectIdentity]:
        """Every member identity this step assigns, scalar and Value Object alike."""
        return frozenset(self.attributes) | frozenset(self.value_objects)


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
class PredicateTarget:
    """A readless selection of every row matching one typed predicate.

    It carries the predicate and nothing else: the enclosing step already names
    the Entity, and a Predicate Target's presence already implies an unversioned
    Non-Temporal step, an unbounded expected effect, and ordering-barrier
    behavior.
    """

    predicate: Operation


type WriteTarget = KeyTarget | PredicateTarget
"""The semantic row selection of a Planned Write, distinct from observed
predecessor state and from any concurrency condition."""


@dataclass(frozen=True, slots=True)
class VersionGate:
    """The extra equality predicate an optimistic-mode versioned write renders.

    It carries only what the predicate binds. The advanced version is an
    assignment, not a gate member, and the transaction's concurrency mode is
    consumed while the gate is being decided rather than repeated here.
    """

    attribute: AttributeIdentity
    observed_version: int


@dataclass(frozen=True, slots=True)
class Ungated:
    """The explicit decision that a step renders no gate predicate.

    Locking mode records this rather than a null gate, which is what makes gate
    applicability structural.
    """


UNGATED: Final[Ungated] = Ungated()


@dataclass(frozen=True, slots=True)
class Unversioned:
    """The target declares no optimistic-lock version, so no gate can apply."""


UNVERSIONED: Final[Unversioned] = Unversioned()


@dataclass(frozen=True, slots=True)
class Versioned:
    """The target declares an optimistic-lock version, and the mode decided the
    gate."""

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

type Shortfall = MissingTarget | StaleWrite | OptimisticConflict
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


def shortfall_for(concurrency: NonTemporalConcurrency) -> Shortfall:
    """How a shortfall against an addressed Non-Temporal write classifies.

    Classification follows the settled **gate**, never the verb (ADR 0044/0047):
    a gated shortfall is the detected lost update a re-read could resolve; an
    ungated one on an observation-requiring write is the non-retriable stale
    outcome, since no gate could have caused it; and an observation-free keyed
    write observed nothing, so its shortfall says only that the addressed rows
    are not there. One decision therefore admits exactly one classification,
    which is why a Planned Update and a Planned Delete derive it here rather
    than accepting it.
    """
    if not isinstance(concurrency, Versioned):
        return MISSING_TARGET
    return OPTIMISTIC_CONFLICT if isinstance(concurrency.gate, VersionGate) else STALE_WRITE


def _settle(
    entity: EntityIdentity,
    target: WriteTarget,
    concurrency: NonTemporalConcurrency,
    affected_rows: AffectedRows,
) -> None:
    """Refuse a target, concurrency decision, and expected effect that cannot
    describe one row selection together."""
    match target:
        case PredicateTarget():
            if not isinstance(concurrency, Unversioned) or not isinstance(affected_rows, AnyCount):
                raise ValueError(
                    f"{entity.canonical}: a Predicate Target is readless, so it implies "
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
            expected = shortfall_for(concurrency)
            if affected_rows.on_shortfall != expected:
                raise ValueError(
                    f"{entity.canonical}: the concurrency decision classifies a shortfall as "
                    f"{type(expected).__name__}, and this policy says "
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

    It carries no row, assignments, predecessor, Insert Origin, or Close Cause:
    represented-state absence on a temporal target is a close, not a delete.
    """

    entity: EntityIdentity
    target: WriteTarget
    concurrency: NonTemporalConcurrency
    affected_rows: AffectedRows

    def __post_init__(self) -> None:
        _settle(self.entity, self.target, self.concurrency, self.affected_rows)


type PlannedWrite = PlannedInsert | PlannedUpdate | PlannedDelete
"""The closed algebra of finalized semantic execution steps."""
