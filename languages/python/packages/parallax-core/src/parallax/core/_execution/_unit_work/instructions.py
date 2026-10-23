from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final, Literal, cast, overload

from parallax.core import inheritance, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._unit_work.write_validate import WriteRejectedError, validate_write
from parallax.core.base import (
    INFINITY,
    TIMESTAMP,
    InstantError,
    NeutralType,
    coerce_neutral_input,
    matches_neutral_type,
    normalize_instant,
    retain_document_value,
)
from parallax.core.document_codec._authoring import (
    BORROWED_SOURCE_ACCESS,
    MAPPING_SOURCE_ACCESS,
    PreparedDocumentAuthoring,
    SourceAccess,
    prepare_authoring,
)
from parallax.core.metamodel import (
    AttributeMetadata,
    AuthoringViolation,
    EntityIdentity,
    EntityMetadata,
    Leaf,
    PrimaryKey,
    ValueObjectMetadata,
    WriteAssignmentError,
    entity_by_name,
    judge_assignment,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.metamodel._states import ambiguous_entity_spellings
from parallax.core.predicate import PredicateInterpretation, PredicateNode
from parallax.core.temporal_read import TimeInterval
from parallax.core.wire import WireDecodingError, WireValue, decode_wire, encode_wire
from parallax.core.write_plan.columns import freeze_retained_value
from parallax.core.write_plan.steps import ResolvedMutationSelection

__all__ = [
    "AMEND_MUTATIONS",
    "ASSIGNMENT_MUTATIONS",
    "BOUNDED_MUTATIONS",
    "DESTRUCTIVE_MUTATIONS",
    "INSERT_MUTATIONS",
    "REPLACE_MUTATIONS",
    "ExpectedTxStart",
    "ExpectedVersion",
    "InstructionRejectedError",
    "KeyedMutation",
    "KeyedWriteInstruction",
    "PredicateMutation",
    "PredicateSelection",
    "PredicateWriteInstruction",
    "PreparedInstruction",
    "PreparedKeyedInstruction",
    "PreparedPredicateInstruction",
    "PreparedTargetInstruction",
    "TargetExpectation",
    "TargetMutation",
    "TargetWriteInstruction",
    "WriteAssignment",
    "WriteInstruction",
    "WriteInstructionError",
    "addressed_members",
    "assigned_members",
    "coerce_typed_row",
    "derive_keyed_instruction",
    "deserialize",
    "keyed_instruction_from_target",
    "prepare_typed_write",
    "prepare_wire_write",
    "resolve_target",
    "serialize",
]

# The keyed write mutation surface (write-instruction.schema.json): the opening,
# amendment, complete-replacement, and destructive verbs, each with its bounded
# Valid-Time form.
KeyedMutation = Literal[
    "insert",
    "amend",
    "replace",
    "delete",
    "terminate",
    "insertUntil",
    "amendUntil",
    "replaceUntil",
    "terminateUntil",
]
# The predicate-selected (set-based) mutation surface: there is no `insert` — a
# predicate cannot select rows that do not yet exist. A readless target has no
# history to close and no Valid Time to bound, so no milestone verb or bounded
# form.
PredicateMutation = Literal["amend", "delete", "replace"]
# The target write mutation surface: an amendment, a complete
# replacement, a deletion, or a termination of one existing object, each with
# its bounded form where one exists.
TargetMutation = Literal[
    "amend", "amendUntil", "replace", "replaceUntil", "delete", "terminate", "terminateUntil"
]

# Which of the keyed and target verb surfaces a mutation arrived
# through. Carried only so a refusal can name methods the caller can act on: one
# mutation token is spelled by two methods, and answering a `terminate_if` call
# with "use `delete`" names the source-authorized verb, which takes no revision.
type _WriteSurface = Literal["keyed", "target"]

INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})
"""The keyed mutations that OPEN a row rather than write against an existing
one, which is what makes them the mutations that carry no State Observation
(`m-unit-work` "Absence is structural"). Shared so the admitted write's own
refusal and the planner's coalescing both answer "is this an insert?" from one
definition."""

AMEND_MUTATIONS: Final[frozenset[str]] = frozenset({"amend", "amendUntil"})
"""The mutations that assign the members they name and leave every other member
of each predecessor as it was."""

REPLACE_MUTATIONS: Final[frozenset[str]] = frozenset({"replace", "replaceUntil"})
"""The mutations that state an object's complete writable state, whose
Bitemporal window a replacement establishes across gaps."""

ASSIGNMENT_MUTATIONS: Final[frozenset[str]] = AMEND_MUTATIONS | REPLACE_MUTATIONS
"""The mutations that write an EXISTING object from assigned values, amendment
and replacement alike. Shared for :data:`INSERT_MUTATIONS`' reason: the frontend
refusal that asks which verb accepts a value and the planner's insert-then-amend
coalescing must answer "does this assign?" from one definition, or a verb one
folds is a verb the other refuses."""

DESTRUCTIVE_MUTATIONS: Final[frozenset[str]] = frozenset({"delete", "terminate", "terminateUntil"})
"""The keyed mutations that end a row's existence or its current milestone, and
so CANCEL a buffered insert of the same object still pending in the same flush
(`m-unit-work` "Insert-then-delete cancels"). Shared for
:data:`INSERT_MUTATIONS`' reason: the planner's cancellation rule and any
frontend gate that has to agree with it must answer "is this destructive?" from
one definition."""

_KEYED_MUTATIONS: Final[frozenset[str]] = (
    INSERT_MUTATIONS | ASSIGNMENT_MUTATIONS | DESTRUCTIVE_MUTATIONS
)
_PREDICATE_MUTATIONS: Final[frozenset[str]] = frozenset({"amend", "delete", "replace"})
_TARGET_MUTATIONS: Final[frozenset[str]] = ASSIGNMENT_MUTATIONS | DESTRUCTIVE_MUTATIONS

BOUNDED_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"insertUntil", "amendUntil", "terminateUntil", "replaceUntil"}
)
"""The mutations whose window is a PAIR of Valid-Time bounds, keyed and target
alike; every other form carries no `until` — its window runs `[validFrom,
infinity)`, or the target is non-temporal."""

# The framework-owned transaction observation is NOT durable instruction state, so
# these control keys are forbidden on a write row. All THREE that
# `write-instruction.schema.json`'s own `writeRow` forbids: the observed version,
# and BOTH halves of the observed milestone's own edge coordinate. Omitting either
# half would let a row carry a coordinate the instruction cannot mean — the
# milestone a temporal write observes is resolved at flush, never authored.
_FORBIDDEN_ROW_KEYS: Final[frozenset[str]] = frozenset(
    {"observedVersion", "observedTxStart", "observedValidStart"}
)


# The classification a plural keyed instruction on a temporal target is refused
# with, from the closed pre-SQL rejection vocabulary (`m-case-format` Rejected
# cases).
TEMPORAL_KEYED_WRITE_MULTI_ROW: Final[str] = "temporal-keyed-write-multi-row"

# The same vocabulary's classification of a bare Entity spelling two namespaces
# share, owned normatively by `m-predicate` (a property of the reference site,
# not of the model) and raised here for a write's own target reference.
REFERENCE_AMBIGUOUS_ENTITY_NAME: Final[str] = "reference-ambiguous-entity-name"

# The same vocabulary's classification of a predicate-selected write whose
# target needs an observation: a versioned or temporal Entity, which one
# readless statement cannot write (`m-batch-write`).
SET_BASED_WRITE_TARGET_UNSUPPORTED: Final[str] = "set-based-write-target-unsupported"


class WriteInstructionError(ValueError):
    """A write-instruction document is not a well-formed canonical instruction."""


class InstructionRejectedError(WriteInstructionError):
    """An instruction violates a model-aware rule of the closed pre-SQL rejection
    vocabulary, and ``rule`` is its exact classification.

    A subclass rather than a sibling because the violation IS a well-formedness
    verdict on the instruction — every layer already treating a
    :class:`WriteInstructionError` as the build-time refusal keeps doing so
    unchanged — while the added ``rule`` is what lets a negative-validation
    caller report which normative MUST was broken rather than only that one was.
    """

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


@dataclass(frozen=True, slots=True)
class KeyedWriteInstruction:
    """An authored keyed write: a ``mutation`` on one ``entity`` carrying flat
    attribute-named neutral write input (``rows``).

    ``valid_from`` / ``until`` are the Valid-Time bounds; a
    bounded ``*Until`` mutation carries both, a plain temporal mutation carries only
    ``valid_from`` (window ``[valid_from, infinity)``), and a non-temporal
    mutation carries neither. The Transaction-Time instant is never a field here.
    Whether the bounds suit the target is judged by preparation, not here.
    """

    mutation: KeyedMutation
    entity: str
    rows: tuple[Mapping[str, object], ...]
    valid_from: dt.datetime | None = None
    until: dt.datetime | None = None

    def __post_init__(self) -> None:
        row_names = {name for row in self.rows for name in row}
        forbidden = sorted(row_names & _FORBIDDEN_ROW_KEYS)
        if forbidden:
            raise WriteInstructionError(
                f"keyed write: row carries forbidden observation control key(s) {forbidden} "
                "(the transaction observation is attached at flush, never on the instruction)"
            )
        frozen = tuple(
            row if isinstance(row, MappingProxyType) else MappingProxyType(dict(row))
            for row in self.rows
        )
        object.__setattr__(self, "rows", frozen)


@dataclass(frozen=True, slots=True)
class WriteAssignment:
    """One ordered predicate-write assignment: ``attr`` (a ``Class.member`` reference)
    set to ``value`` (a neutral literal / document). List order is DATA order only —
    the emitted SET columns follow the target's canonical Table Layout order at
    lowering."""

    attr: str
    value: object


@dataclass(frozen=True, slots=True)
class PredicateSelection:
    """The entity a predicate-selected write begins from plus its
    ``m-predicate`` selection: a canonical Predicate node, or the adapter that
    interprets a frontend's own captured predicate at the checked target.

    This is the instruction-level carrier an authored :class:`PredicateWriteInstruction`
    holds, distinct from the prepared product buffering retains and from the
    finalized :class:`~parallax.core.unit_work.
    planned.WriteTarget` a Planned Step settles into. Preparation resolves
    either form once and retains only the resolved predicate.
    """

    entity: str
    predicate: PredicateNode | PredicateInterpretation


@dataclass(frozen=True, slots=True)
class PredicateWriteInstruction:
    """A predicate-selected (set-based) write: a ``mutation`` on every row of
    ``target`` matching its predicate. An amendment carries ``assignments`` —
    none at all being the empty amendment — and a replacement the ``row``
    stating each selected object's complete writable state; a deletion carries
    neither."""

    mutation: PredicateMutation
    target: PredicateSelection
    assignments: tuple[WriteAssignment, ...] = ()
    row: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.assignments and self.mutation not in AMEND_MUTATIONS:
            raise WriteInstructionError(
                f"predicate write: `{self.mutation}` assigns no members and carries no "
                "`assignments`"
            )
        replaces = self.mutation in REPLACE_MUTATIONS
        if self.row is None:
            if replaces:
                raise WriteInstructionError(
                    f"predicate write: `{self.mutation}` states each selected object's whole "
                    "writable state and carries a `row`"
                )
            return
        if not replaces:
            raise WriteInstructionError(
                f"predicate write: `{self.mutation}` states no whole state and carries no `row`"
            )
        forbidden = sorted(set(self.row) & _FORBIDDEN_ROW_KEYS)
        if forbidden:
            raise WriteInstructionError(
                f"predicate write: row carries forbidden observation control key(s) {forbidden} "
                "(a predicate-selected write observes nothing)"
            )
        if not isinstance(self.row, MappingProxyType):
            object.__setattr__(self, "row", MappingProxyType(dict(self.row)))


@dataclass(frozen=True, slots=True)
class TargetWriteInstruction:
    """An authored target write of one existing ``entity`` object.

    ``row`` names the object by its primary key beside the members the write
    states: the assignments of an ``amend``, the complete writable state of a
    ``replace``, and nothing for a deletion or termination. ``if_version`` and
    ``if_tx_start`` are the caller's revision condition exactly as stated,
    judged by preparation against the target's own revision kind; neither is
    ever read off the row or off any read's evidence. ``stated`` names the
    conditions a caller named, where its interface tells naming a condition —
    even as ``None`` — from omitting it; ``None`` reads every condition
    carrying a value as stated.
    """

    mutation: TargetMutation
    entity: str
    row: Mapping[str, object]
    if_version: int | None = None
    if_tx_start: dt.datetime | None = None
    valid_from: dt.datetime | None = None
    until: dt.datetime | None = None
    stated: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        forbidden = sorted(set(self.row) & _FORBIDDEN_ROW_KEYS)
        if forbidden:
            raise WriteInstructionError(
                f"target write: row carries forbidden observation control key(s) {forbidden} "
                "(a target write's condition is its own revision argument, never a row member)"
            )
        if not isinstance(self.row, MappingProxyType):
            object.__setattr__(self, "row", MappingProxyType(dict(self.row)))


WriteInstruction = KeyedWriteInstruction | PredicateWriteInstruction | TargetWriteInstruction


@dataclass(frozen=True, slots=True, init=False)
class PreparedKeyedInstruction:
    """A keyed mutation over an exact resolved target and owned managed rows.

    ``valid_time_window`` is the judged window, ``None`` for a target without
    Valid Time. ``assigns`` is whether some row states a member beside the key:
    a member equal to the value its source published is still stated, so an
    amendment assigns nothing only when it expresses no member at all. Only this
    module's producers construct one, so holding one means the write was judged
    admissible against its target.
    """

    mutation: KeyedMutation
    assigns: bool
    target: EntityMetadata
    rows: tuple[Mapping[str, object], ...]
    valid_time_window: TimeInterval | None


@dataclass(frozen=True, slots=True, init=False)
class PreparedPredicateInstruction:
    """A predicate mutation over a resolved selection and the managed row it
    assigns every selected object: the members an amendment names or a
    replacement completes, never the key, and nothing for a deletion.

    Only this module's producers construct one, so holding one means the write
    was judged admissible against its target, which one readless statement
    writes.
    """

    mutation: PredicateMutation
    selection: ResolvedMutationSelection
    row: Mapping[str, object]

    @property
    def assigns(self) -> bool:
        return bool(self.row)


@dataclass(frozen=True, slots=True)
class ExpectedVersion:
    """A versioned target's caller-stated starting version."""

    version: int


@dataclass(frozen=True, slots=True)
class ExpectedTxStart:
    """A temporal target's caller-stated starting milestone: the
    Transaction-Time start the caller observed, never the writing attempt's own
    instant."""

    instant: dt.datetime


type TargetExpectation = ExpectedVersion | ExpectedTxStart
"""What a target write's caller requires of the state it starts from."""


@dataclass(frozen=True, slots=True, init=False)
class PreparedTargetInstruction:
    """A target write over an exact resolved target, its owned managed
    row, its judged Valid-Time window — ``None`` for a target without Valid
    Time — and its validated starting expectation.

    ``mutation`` is the exact verb, kept so a deletion or termination, whose row
    states nothing beside the key, never reads as an empty patch. ``assigns``
    is whether the row states any member beside the key. Only this module's
    producers construct one, so holding one means the write was judged
    admissible against its target.
    """

    mutation: TargetMutation
    assigns: bool
    target: EntityMetadata
    row: Mapping[str, object]
    valid_time_window: TimeInterval | None
    expectation: TargetExpectation


PreparedInstruction = PreparedKeyedInstruction | PreparedPredicateInstruction
"""A prepared keyed or predicate instruction: a unit of work admits a keyed one
to its buffer and executes a predicate one at the call."""


def _prepared_keyed_instruction(
    mutation: KeyedMutation,
    assigns: bool,
    target: EntityMetadata,
    rows: tuple[Mapping[str, object], ...],
    valid_time_window: TimeInterval | None,
) -> PreparedKeyedInstruction:
    prepared = object.__new__(PreparedKeyedInstruction)
    object.__setattr__(prepared, "mutation", mutation)
    object.__setattr__(prepared, "assigns", assigns)
    object.__setattr__(prepared, "target", target)
    object.__setattr__(prepared, "rows", rows)
    object.__setattr__(prepared, "valid_time_window", valid_time_window)
    return prepared


def _prepared_predicate_instruction(
    mutation: PredicateMutation,
    selection: ResolvedMutationSelection,
    row: Mapping[str, object],
) -> PreparedPredicateInstruction:
    prepared = object.__new__(PreparedPredicateInstruction)
    object.__setattr__(prepared, "mutation", mutation)
    object.__setattr__(prepared, "selection", selection)
    object.__setattr__(prepared, "row", row)
    return prepared


def _prepared_target_instruction(
    mutation: TargetMutation,
    assigns: bool,
    target: EntityMetadata,
    row: Mapping[str, object],
    valid_time_window: TimeInterval | None,
    expectation: TargetExpectation,
) -> PreparedTargetInstruction:
    prepared = object.__new__(PreparedTargetInstruction)
    object.__setattr__(prepared, "mutation", mutation)
    object.__setattr__(prepared, "assigns", assigns)
    object.__setattr__(prepared, "target", target)
    object.__setattr__(prepared, "row", row)
    object.__setattr__(prepared, "valid_time_window", valid_time_window)
    object.__setattr__(prepared, "expectation", expectation)
    return prepared


def keyed_instruction_from_target(prepared: PreparedTargetInstruction) -> PreparedKeyedInstruction:
    """The keyed write a prepared target write executes as: its own verb and
    row, written against the object its key names, over its window.

    The verb carries the replacement or destructive intent, so every admitted
    write and composition the write later travels through keeps it whatever
    authorized the write; nothing is judged again.
    """
    return _prepared_keyed_instruction(
        prepared.mutation,
        prepared.assigns,
        prepared.target,
        (prepared.row,),
        prepared.valid_time_window,
    )


def derive_keyed_instruction(
    prepared: PreparedKeyedInstruction,
    rows: tuple[Mapping[str, object], ...],
    *,
    mutation: KeyedMutation | None = None,
    assigns: bool | None = None,
) -> PreparedKeyedInstruction:
    """Derive a keyed prepared product while retaining owned values by identity,
    under ``mutation`` where composition changed the verb over the same window.

    ``rows`` keep ``prepared``'s ``assigns`` unless ``assigns`` states another:
    a derivation keeping or splitting its assigning rows keeps it, and one
    overlaying another write's members states whether either assigns."""
    sealed = tuple(cast("Mapping[str, object]", retain_document_value(row)) for row in rows)
    return _prepared_keyed_instruction(
        prepared.mutation if mutation is None else mutation,
        prepared.assigns if assigns is None else assigns,
        prepared.target,
        sealed,
        prepared.valid_time_window,
    )


# The reference pattern a predicate-write assignment `attr` must match, mirroring
# identity.schema.json's `attributeRef` by way of write-instruction.schema.json
# `$defs/writeAssignment`: an Entity spelling — canonical or bare — followed by
# the member it assigns.
_ASSIGNMENT_REF = re.compile(
    r"^([a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*\.)?[A-Z][A-Za-z0-9]*\.[a-z][A-Za-z0-9_]*$"
)


def deserialize(doc: object) -> WriteInstruction:
    """Parse a canonical write-instruction document into a frozen instruction.

    Discriminates the three shapes by their required carrier (``rows`` -> keyed,
    ``target`` -> predicate, ``row`` -> target, unless it rides
    beside a predicate replacement's ``target``), validates the closed
    shape, the mutation enum, the keyed and target Valid-Time-bound
    pairing rules (a bounded ``*Until`` carries both bounds, every other form
    carries no ``until``; a predicate write carries no bound at all), that a
    target write states exactly one revision, and — for a keyed write
    — that no row carries a forbidden observation control key or a smuggled
    Transaction-Time instant.

    Each bound is a finite canonical ``timestamp`` decoded by the Wire codec, whose
    refusals keep their ``neutral-literal-*`` classification; ``infinity`` is no
    authored bound, since an open upper end is spelled by omitting ``until``.
    """
    if not isinstance(doc, Mapping):
        raise WriteInstructionError(
            f"write instruction must be a mapping, got {type(doc).__name__}"
        )
    node = cast("Mapping[str, object]", doc)
    # A predicate-selected replacement states its `row` beside its `target`.
    carriers = [
        key
        for key in ("rows", "target", "row")
        if key in node and not (key == "row" and "target" in node)
    ]
    if len(carriers) > 1:
        raise WriteInstructionError(
            f"write instruction is ambiguous: it carries {carriers}, and `rows` (keyed), "
            "`target` (predicate), and `row` (target write) each name a different shape"
        )
    if carriers == ["rows"]:
        return _keyed(node)
    if carriers == ["target"]:
        return _predicate(node)
    if carriers == ["row"]:
        return _target_write(node)
    raise WriteInstructionError(
        "write instruction must carry `rows` (keyed), `target` (predicate), or `row` (target write)"
    )


def _reject_extra(node: Mapping[str, object], allowed: frozenset[str], shape: str) -> None:
    extra = sorted(set(node) - allowed)
    if extra:
        # `at` is the corpus's Clock-context alias, an UNEXPECTED key here — the
        # canonical instruction never carries a Transaction-Time instant.
        raise WriteInstructionError(f"{shape}: unexpected key(s) {extra}")


def _require(node: Mapping[str, object], keys: tuple[str, ...], shape: str) -> None:
    missing = sorted(k for k in keys if k not in node)
    if missing:
        raise WriteInstructionError(f"{shape}: missing required key(s) {missing}")


def _mutation(node: Mapping[str, object], allowed: frozenset[str], shape: str) -> str:
    value = node.get("mutation")
    if not isinstance(value, str) or value not in allowed:
        raise WriteInstructionError(f"{shape}: `mutation` must be one of {sorted(allowed)}")
    return value


def _entity_name(node: Mapping[str, object], key: str, shape: str) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value:
        raise WriteInstructionError(f"{shape}: `{key}` must be a non-empty entity name")
    return value


def _bound(node: Mapping[str, object], key: str, shape: str) -> dt.datetime | None:
    if key not in node:
        return None
    value = node[key]
    if not isinstance(value, str) or not value:
        raise WriteInstructionError(f"{shape}: `{key}` must be a non-empty instant string")
    return cast("dt.datetime", _decoded_wire(TIMESTAMP, value, f"{shape} `{key}`"))


def _check_valid_time_bounds(
    mutation: str, valid_from: dt.datetime | None, until: dt.datetime | None, shape: str
) -> None:
    """Enforce the schema's Valid-Time-bound pairing: a bounded ``*Until``
    mutation carries BOTH ``validFrom`` and ``until``, and every other mutation
    carries no ``until``.

    Verb shape only. Whether ``validFrom`` is required, optional, or forbidden
    follows from the TARGET's temporal profile, which deserialization has no
    model to ask; preparation judges it, together with the window's order.
    """
    if mutation in BOUNDED_MUTATIONS:
        if valid_from is None or until is None:
            raise WriteInstructionError(
                f"{shape}: `{mutation}` is bounded and MUST carry both `validFrom` and `until`"
            )
    elif until is not None:
        raise WriteInstructionError(
            f"{shape}: `{mutation}` is unbounded and MUST NOT carry `until`"
        )


def _rows(node: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = node.get("rows")
    if not isinstance(raw, list) or not raw:
        raise WriteInstructionError("keyed write: `rows` must be a non-empty list")
    rows: list[Mapping[str, object]] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, Mapping):
            raise WriteInstructionError("keyed write: each row must be a mapping")
        row = cast("Mapping[str, object]", item)
        forbidden = sorted(set(row) & _FORBIDDEN_ROW_KEYS)
        if forbidden:
            raise WriteInstructionError(
                f"keyed write: row carries forbidden observation control key(s) {forbidden} "
                "(the transaction observation is attached at flush, never on the instruction)"
            )
        # A neutral write-row value is opaque JSON (a scalar, a one-key DB-computed
        # marker, or a whole value-object document); its metamodel role decides its
        # meaning at lowering, not its shape, so the serde keeps it verbatim.
        rows.append(dict(row))
    return tuple(rows)


def _keyed(node: Mapping[str, object]) -> KeyedWriteInstruction:
    _reject_extra(
        node, frozenset({"mutation", "entity", "rows", "validFrom", "until"}), "keyed write"
    )
    _require(node, ("mutation", "entity", "rows"), "keyed write")
    mutation = _mutation(node, _KEYED_MUTATIONS, "keyed write")
    entity = _entity_name(node, "entity", "keyed write")
    rows = _rows(node)
    valid_from = _bound(node, "validFrom", "keyed write")
    until = _bound(node, "until", "keyed write")
    _check_valid_time_bounds(mutation, valid_from, until, "keyed write")
    return KeyedWriteInstruction(
        mutation=cast("KeyedMutation", mutation),
        entity=entity,
        rows=rows,
        valid_from=valid_from,
        until=until,
    )


def _target(node: Mapping[str, object]) -> PredicateSelection:
    raw = node.get("target")
    if not isinstance(raw, Mapping):
        raise WriteInstructionError("predicate write: `target` must be a mapping")
    target = cast("Mapping[str, object]", raw)
    _reject_extra(target, frozenset({"entity", "predicate"}), "predicate write target")
    _require(target, ("entity", "predicate"), "predicate write target")
    entity = _entity_name(target, "entity", "predicate write target")
    predicate_doc = target.get("predicate")
    if not isinstance(predicate_doc, Mapping):
        raise WriteInstructionError("predicate write: `target.predicate` must be a mapping")
    # The embedded predicate is a canonical m-predicate node — the sole write-side
    # reach into the algebra; predicate rejects a malformed one.
    predicate = predicate_algebra.deserialize(cast("Mapping[str, object]", predicate_doc))
    return PredicateSelection(entity=entity, predicate=predicate)


def _assignments(node: Mapping[str, object]) -> tuple[WriteAssignment, ...]:
    raw = node.get("assignments")
    if not isinstance(raw, list):
        raise WriteInstructionError("predicate write: `assignments` must be a list")
    out: list[WriteAssignment] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, Mapping):
            raise WriteInstructionError("predicate write: each assignment must be a mapping")
        assignment = cast("Mapping[str, object]", item)
        _reject_extra(assignment, frozenset({"attr", "value"}), "predicate write assignment")
        _require(assignment, ("attr", "value"), "predicate write assignment")
        attr = assignment.get("attr")
        if not isinstance(attr, str) or _ASSIGNMENT_REF.match(attr) is None:
            raise WriteInstructionError(
                f"predicate write: assignment `attr` must be a `Class.member` "
                f"reference, got {attr!r}"
            )
        out.append(WriteAssignment(attr=attr, value=assignment["value"]))
    return tuple(out)


def _predicate(node: Mapping[str, object]) -> PredicateWriteInstruction:
    _reject_extra(node, frozenset({"mutation", "target", "assignments", "row"}), "predicate write")
    _require(node, ("mutation", "target"), "predicate write")
    mutation = _mutation(node, _PREDICATE_MUTATIONS, "predicate write")
    target = _target(node)
    payload = (
        "assignments"
        if mutation in AMEND_MUTATIONS
        else "row"
        if mutation in REPLACE_MUTATIONS
        else None
    )
    for key in ("assignments", "row"):
        if key == payload and key not in node:
            raise WriteInstructionError(f"predicate write: `{mutation}` MUST carry `{key}`")
        if key != payload and key in node:
            raise WriteInstructionError(f"predicate write: `{mutation}` MUST NOT carry `{key}`")
    return PredicateWriteInstruction(
        mutation=cast("PredicateMutation", mutation),
        target=target,
        assignments=_assignments(node) if payload == "assignments" else (),
        row=_predicate_row(node) if payload == "row" else None,
    )


def _predicate_row(node: Mapping[str, object]) -> Mapping[str, object]:
    raw = node.get("row")
    if not isinstance(raw, Mapping):
        raise WriteInstructionError("predicate write: `row` must be a mapping")
    return dict(cast("Mapping[str, object]", raw))


def _target_write(node: Mapping[str, object]) -> TargetWriteInstruction:
    _reject_extra(
        node,
        frozenset({"mutation", "entity", "row", "ifVersion", "ifTxStart", "validFrom", "until"}),
        "target write",
    )
    _require(node, ("mutation", "entity", "row"), "target write")
    mutation = _mutation(node, _TARGET_MUTATIONS, "target write")
    entity = _entity_name(node, "entity", "target write")
    raw = node.get("row")
    if not isinstance(raw, Mapping):
        raise WriteInstructionError("target write: `row` must be a mapping")
    row = dict(cast("Mapping[str, object]", raw))
    if "ifVersion" in node and "ifTxStart" in node:
        raise WriteInstructionError(
            "target write: states both `ifVersion` and `ifTxStart`, and a target has one "
            "revision to state"
        )
    if_version: int | None = None
    if "ifVersion" in node:
        version = node["ifVersion"]
        if isinstance(version, bool) or not isinstance(version, int):
            raise WriteInstructionError("target write: `ifVersion` must be an integer version")
        if_version = version
    valid_from = _bound(node, "validFrom", "target write")
    until = _bound(node, "until", "target write")
    _check_valid_time_bounds(mutation, valid_from, until, "target write")
    instruction = TargetWriteInstruction(
        mutation=cast("TargetMutation", mutation),
        entity=entity,
        row=row,
        if_version=if_version,
        if_tx_start=_bound(node, "ifTxStart", "target write"),
        valid_from=valid_from,
        until=until,
    )
    if instruction.if_version is None and instruction.if_tx_start is None:
        raise WriteInstructionError(
            "target write: states no revision, and a target write states exactly one "
            "of `ifVersion` and `ifTxStart`"
        )
    return instruction


def serialize(instruction: WriteInstruction) -> dict[str, object]:
    """Emit the canonical minimal write-instruction document for one instruction."""
    if isinstance(instruction, TargetWriteInstruction):
        target_body: dict[str, object] = {
            "mutation": instruction.mutation,
            "entity": instruction.entity,
            "row": dict(instruction.row),
        }
        if instruction.if_version is not None:
            target_body["ifVersion"] = instruction.if_version
        if instruction.if_tx_start is not None:
            target_body["ifTxStart"] = _wire_bound(instruction.if_tx_start)
        _emit_bounds(target_body, instruction.valid_from, instruction.until)
        return target_body
    if isinstance(instruction, KeyedWriteInstruction):
        keyed_body: dict[str, object] = {
            "mutation": instruction.mutation,
            "entity": instruction.entity,
            "rows": [dict(row) for row in instruction.rows],
        }
        _emit_bounds(keyed_body, instruction.valid_from, instruction.until)
        return keyed_body
    predicate = instruction.target.predicate
    if not isinstance(predicate, PredicateNode):
        raise WriteInstructionError(
            f"{instruction.target.entity}: a predicate write selecting through an interpreted "
            "predicate has no canonical write-instruction document"
        )
    predicate_body: dict[str, object] = {
        "mutation": instruction.mutation,
        "target": {
            "entity": instruction.target.entity,
            "predicate": predicate_algebra.serialize(predicate),
        },
    }
    if instruction.mutation in AMEND_MUTATIONS:
        predicate_body["assignments"] = [
            {"attr": a.attr, "value": a.value} for a in instruction.assignments
        ]
    if instruction.row is not None:
        predicate_body["row"] = dict(instruction.row)
    return predicate_body


def _emit_bounds(
    body: dict[str, object],
    valid_from: dt.datetime | None,
    until: dt.datetime | None,
) -> None:
    # An omitted bound stays omitted (the canonical minimal form), so a non-temporal
    # or plain-temporal instruction round-trips without gaining a null bound.
    if valid_from is not None:
        body["validFrom"] = _wire_bound(valid_from)
    if until is not None:
        body["until"] = _wire_bound(until)


def _wire_bound(value: dt.datetime) -> object:
    return encode_wire(TIMESTAMP, cast("dt.datetime", coerce_neutral_input(value, TIMESTAMP)))


def _spelled(mutation: str, surface: _WriteSurface) -> str:
    """``mutation``'s METHOD name on ``surface``, which is the only spelling a
    caller can act on. Scoped to the two applicability refusals below, whose
    verbs state no window; every other message in this module still names the
    token it was given."""
    return mutation if surface == "keyed" else f"{mutation}_if"


def _temporal_delete_refusal(
    entity_name: str, mutation: str, *, surface: _WriteSurface
) -> str | None:
    """Why a TEMPORAL target refuses ``mutation``'s VERB, or ``None`` when this
    rule has nothing to say about it.

    ``delete`` is physical row removal and carries no temporal meaning at all,
    so a target that milestones its rows spells its removal ``terminate`` and
    rejects ``delete`` outright (`m-temporal-write`). Settling
    one anyway would erase the history the target exists to keep.
    """
    if mutation != "delete":
        return None
    return (
        f"Temporal objects like {entity_name!r} do not support "
        f"{_spelled(mutation, surface)!r}, which physically removes rows. "
        f"Use {_spelled('terminate', surface)!r} instead."
    )


def _non_temporal_milestone_refusal(
    entity_name: str, mutation: str, *, surface: _WriteSurface
) -> str | None:
    """Why a NON-TEMPORAL target refuses ``mutation``'s VERB, or ``None`` when
    this rule has nothing to say about it.

    ``terminate`` closes a milestone, and a non-temporal target has no axis to
    hold one; settling it anyway would keep its row effect and silently drop its
    temporal meaning, so the refusal names ``delete``, which keeps the row
    effect (`m-temporal-write`). Every bounded milestone verb
    states an ``until``, which the window judgment has already refused.
    """
    if mutation != "terminate":
        return None
    return (
        f"Non-temporal objects like {entity_name!r} do not support "
        f"{_spelled(mutation, surface)!r}, which closes a row's history instead of "
        f"removing it. Use {_spelled('delete', surface)!r} instead."
    )


def _temporal_singleton_refusal(entity_name: str, instruction: KeyedWriteInstruction) -> str | None:
    """Why a TEMPORAL target refuses ``instruction``'s ROW COUNT, or ``None``
    when this rule has nothing to say about it.

    Each row of a milestone chain closes its own current milestone, settles
    against its own Temporal Observation, and opens its own successors, and a
    temporal entity never collapses into a set-based statement (`m-batch-write`),
    so several rows under one keyed instruction denote several independent chains
    rather than one wider write (`m-unit-work` "A temporal keyed instruction
    carries exactly one row").
    """
    if len(instruction.rows) == 1:
        return None
    return (
        f"{entity_name!r}: a keyed {instruction.mutation!r} on a temporal target carries "
        f"{len(instruction.rows)} rows — a temporal keyed instruction carries exactly one "
        "(m-unit-work), since each row closes its own milestone, settles against its "
        "own observation, and chains its own successors; author one instruction per row"
    )


@overload
def prepare_typed_write(
    instruction: TargetWriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedTargetInstruction: ...
@overload
def prepare_typed_write(
    instruction: KeyedWriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedKeyedInstruction: ...
@overload
def prepare_typed_write(
    instruction: PredicateWriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedPredicateInstruction: ...
@overload
def prepare_typed_write(
    instruction: WriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedInstruction | PreparedTargetInstruction: ...
def prepare_typed_write(
    instruction: WriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedInstruction | PreparedTargetInstruction:
    """Coerce developer values once, then judge and freeze the write.

    ``authored_members`` names the members a caller assigned explicitly rather
    than through an edit chain that already judged them, so each is judged as
    an assignment. ``members`` produces explicit assignments a keyed or
    target write adds to its one row: it is asked only once the
    target, the window, and any condition admit the write, so a fault in what
    it judges is heard after theirs, and each member it answers is judged as
    an assignment."""
    return _prepare_write(
        instruction,
        model,
        converter=_coerce_typed_leaf,
        source_access=BORROWED_SOURCE_ACCESS,
        authored_members=authored_members,
        members=members,
    )


@overload
def prepare_wire_write(
    instruction: TargetWriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedTargetInstruction: ...
@overload
def prepare_wire_write(
    instruction: KeyedWriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedKeyedInstruction: ...
@overload
def prepare_wire_write(
    instruction: PredicateWriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedPredicateInstruction: ...
@overload
def prepare_wire_write(
    instruction: WriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedInstruction | PreparedTargetInstruction: ...
def prepare_wire_write(
    instruction: WriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedInstruction | PreparedTargetInstruction:
    """Decode one serialized instruction, then judge and freeze the write.

    ``authored_members`` names the row members a Wire caller explicitly wrote:
    an insert's payload keys, judged as insert authoring, or an update's change
    keys, judged as assignments. A neutral instruction omits it, and its row is
    judged as row content alone. A target write judges every member
    its row states beside the key as an assignment either way. ``members``
    follows :func:`prepare_typed_write`'s rule.
    """
    return _prepare_write(
        instruction,
        model,
        converter=_decode_wire_leaf,
        source_access=MAPPING_SOURCE_ACCESS,
        authored_members=authored_members,
        members=members,
    )


def _prepare_write(
    instruction: WriteInstruction,
    model: AcceptedMetamodel,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
    authored_members: Set[str] | None,
    members: Callable[[], Mapping[str, object]] | None,
) -> PreparedInstruction | PreparedTargetInstruction:
    """The sole admissibility judgment of a write, each family's target first
    and then its payload, so a call whose verb or window is wrong for its
    target hears that before any complaint about what it carries."""
    if isinstance(instruction, TargetWriteInstruction):
        return _prepare_target_write(
            instruction,
            model,
            converter=converter,
            source_access=source_access,
            authored_members=authored_members,
            members=members,
        )
    if isinstance(instruction, KeyedWriteInstruction):
        return _prepare_keyed_write(
            instruction,
            model,
            converter=converter,
            source_access=source_access,
            authored_members=authored_members,
            members=members,
        )
    # A predicate write states its payload whole, and its readless target
    # declares no framework-owned member for an authored one to name.
    assert members is None
    return _prepare_predicate_write(
        instruction, model, converter=converter, source_access=source_access
    )


def _prepare_keyed_write(
    instruction: KeyedWriteInstruction,
    model: AcceptedMetamodel,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
    authored_members: Set[str] | None,
    members: Callable[[], Mapping[str, object]] | None,
) -> PreparedKeyedInstruction:
    """Judge a keyed write: its verb and window against its target, then its
    row count, then its rows' subtype shape, members, and values."""
    entity = resolve_target(model, instruction.entity)
    shape = temporal_read.view(model).shape(entity.identity)
    window = _judge_applicability(model, entity, shape, instruction, surface="keyed")
    if _is_temporal(shape):
        plural = _temporal_singleton_refusal(entity.identity.name, instruction)
        if plural is not None:
            raise InstructionRejectedError(TEMPORAL_KEYED_WRITE_MULTI_ROW, plural)
    if members is not None:
        assigned = members()
        (row,) = instruction.rows
        instruction = replace(instruction, rows=({**row, **assigned},))
        authored_members = assigned.keys()
    return _prepare_keyed_payload(
        instruction,
        model,
        entity,
        _family_position(model, entity),
        window,
        converter=converter,
        source_access=source_access,
        authored_members=authored_members,
    )


def _prepare_predicate_write(
    instruction: PredicateWriteInstruction,
    model: AcceptedMetamodel,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
) -> PreparedPredicateInstruction:
    """Judge a predicate write: whether its target can be written without
    being read at all, then its selecting predicate, family, and payload."""
    entity = resolve_target(model, instruction.target.entity)
    position = _family_position(model, entity)
    _judge_readless_family(model, entity, position, instruction.mutation)
    return _prepare_predicate_payload(
        instruction,
        model,
        entity,
        position,
        converter=converter,
        source_access=source_access,
    )


def _judge_readless_family(
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    position: inheritance.InheritanceEntityView,
    mutation: PredicateMutation,
) -> None:
    """Refuse a predicate write whose target cannot be written by one readless
    statement (`m-batch-write`).

    Each selected object of a versioned or temporal family needs its own
    observation before it is written, so the write needs its caller to read
    first; the refusal names the verbs that write through such a read or a
    revision the caller holds."""
    shape = temporal_read.view(model).shape(entity.identity)
    if _requires_observation(position, shape):
        raise InstructionRejectedError(
            SET_BASED_WRITE_TARGET_UNSUPPORTED,
            _readless_family_advice(entity, position, shape, mutation),
        )


def _readless_family_advice(
    entity: EntityMetadata,
    position: inheritance.InheritanceEntityView,
    shape: temporal_read.TemporalShape | None,
    mutation: PredicateMutation,
) -> str:
    temporal = _is_temporal(shape)
    # A deletion's keyed sibling is the destructive verb the target's kind admits.
    sibling = mutation if mutation != "delete" else "terminate" if temporal else "delete"
    revision = "version" if _is_versioned(position) else "tx_start"
    return (
        f"{entity.identity.name} is {'temporal' if temporal else 'versioned'}, so "
        f"{mutation}_where cannot change it without reading it. Read it (find / stream) and "
        f"{sibling} each object, or use {sibling}_if with the {revision} you hold."
    )


def _requires_observation(
    position: inheritance.InheritanceEntityView, shape: temporal_read.TemporalShape | None
) -> bool:
    """Whether every write of the family must be judged against an observation
    of the object it changes: its version, or the milestone it closes."""
    return _is_versioned(position) or _is_temporal(shape)


def _is_versioned(position: inheritance.InheritanceEntityView) -> bool:
    return any(attribute.optimistic_locking for attribute in position.applicable_attributes)


def _is_temporal(shape: temporal_read.TemporalShape | None) -> bool:
    return isinstance(shape, temporal_read.TransactionTimeOnly | temporal_read.Bitemporal)


def _judge_applicability(
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    shape: temporal_read.TemporalShape | None,
    instruction: KeyedWriteInstruction | TargetWriteInstruction,
    *,
    surface: _WriteSurface,
) -> TimeInterval | None:
    """Judge the verb and window against ``entity``'s Temporal Shape, and
    answer the managed window, ``None`` for a target without Valid Time.

    A temporal ``delete`` is refused before the window: ``delete`` states no
    bound in any spelling, so answering it by naming the ``valid_from`` a
    Bitemporal target requires would ask for an argument the verb has no place
    for. A milestone verb aimed at a non-temporal target is refused after it:
    every such verb takes a bound, so a call stating one hears a true verdict on
    an argument it can drop, while a boundless ``terminate`` clears the window
    and is refused for its verb.
    """
    name = entity.identity.name
    temporal = _is_temporal(shape)
    if temporal:
        refusal = _temporal_delete_refusal(name, instruction.mutation, surface=surface)
        if refusal is not None:
            raise WriteInstructionError(refusal)
    window = _judge_window(
        _family_root(model, entity),
        shape,
        instruction.mutation,
        instruction.valid_from,
        instruction.until,
    )
    if not temporal:
        refusal = _non_temporal_milestone_refusal(name, instruction.mutation, surface=surface)
        if refusal is not None:
            raise WriteInstructionError(refusal)
    return window


def _judge_window(
    root: EntityIdentity,
    shape: temporal_read.TemporalShape | None,
    mutation: str,
    valid_from: object,
    until: object,
) -> TimeInterval | None:
    """One write's Valid-Time window, judged once per call: ``[valid_from,
    until)``, through :data:`~parallax.core.base.INFINITY` where ``until`` is
    omitted, or ``None`` for a target without Valid Time.

    Four questions in a fixed order, because each presupposes the one before
    it. Does the target's Temporal Shape admit a bounded form at all — only a
    Bitemporal target has a Valid-Time window to bound? Is the window stated as
    the verb's form requires — a ``*Until`` window is a PAIR, and no other form
    carries ``until``? Does the target's Temporal Shape admit ``valid_from`` — a
    Bitemporal target requires it, every other takes none? Is each bound an
    instant, and is the window ordered?

    A bounded form on a target without Valid Time, a half-stated window, an
    inadmissible bound, and an unordered one are this write's own verdict on its
    input (:class:`WriteInstructionError`); a bound that is no instant keeps
    `m-core`'s :class:`~parallax.core.base.InstantError`. Refusals name the
    family by its root.
    """
    if mutation in BOUNDED_MUTATIONS:
        if not isinstance(shape, temporal_read.Bitemporal):
            raise WriteInstructionError(
                f"{root.name}: {_profile(shape)} {mutation!r} takes no until "
                f"({root.name!r} declares no Valid-Time dimension to bound)"
            )
        missing = "valid_from" if valid_from is None else "until" if until is None else None
        if missing is not None:
            raise WriteInstructionError(
                f"{root.name}: a bounded {mutation!r} states its window as a pair, "
                f"and {missing} is absent — an unbounded write omits until rather than "
                "stating none"
            )
    elif until is not None:
        raise WriteInstructionError(
            f"{root.name}: {mutation!r} is unbounded and takes no until "
            "(its window runs to infinity)"
        )
    if isinstance(shape, temporal_read.Bitemporal):
        if valid_from is None:
            raise WriteInstructionError(
                f"{root.name}: a bitemporal {mutation!r} requires valid_from "
                "(the mutation's own Valid-Time instant)"
            )
        managed_from = normalize_instant(_stated_instant(root, mutation, "valid_from", valid_from))
    elif valid_from is not None:
        raise WriteInstructionError(
            f"{root.name}: {_profile(shape)} {mutation!r} takes no valid_from "
            f"({root.name!r} declares no Valid-Time dimension to bound)"
        )
    else:
        # A target without Valid Time is refused any stated `until` above.
        return None
    if until is None:
        return TimeInterval(managed_from, INFINITY)
    managed_until = normalize_instant(_stated_instant(root, mutation, "until", until))
    if managed_until <= managed_from:
        raise WriteInstructionError(
            f"{root.name}: {mutation!r} requires valid_from < until "
            f"— got valid_from={valid_from!r}, until={until!r}"
        )
    return TimeInterval(managed_from, managed_until)


def _prepare_target_write(
    instruction: TargetWriteInstruction,
    model: AcceptedMetamodel,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
    authored_members: Set[str] | None,
    members: Callable[[], Mapping[str, object]] | None,
) -> PreparedTargetInstruction:
    """Judge a target write: its verb and window, then its revision
    arguments, then its payload.

    The verb's applicability follows the keyed rule
    (:func:`_judge_applicability`). The revision arguments are judged ahead of
    the payload because they decide what the write may be at all — a target
    with no revision, one whose revision kind the caller misstated, or one
    whose required revision is missing is refused before any member it names
    is weighed.
    """
    entity = resolve_target(model, instruction.entity)
    shape = temporal_read.view(model).shape(entity.identity)
    window = _judge_applicability(model, entity, shape, instruction, surface="target")
    position = _family_position(model, entity)
    expectation = _judge_expectation(position.root, shape, position, instruction)
    if members is not None:
        instruction = replace(instruction, row={**instruction.row, **members()})
    row, assigns = _prepare_target_payload(
        instruction,
        model,
        entity,
        position,
        converter=converter,
        source_access=source_access,
        authored_members=authored_members,
    )
    return _prepared_target_instruction(
        instruction.mutation, assigns, entity, row, window, expectation
    )


def _judge_expectation(
    root: EntityIdentity,
    shape: temporal_read.TemporalShape | None,
    position: inheritance.InheritanceEntityView,
    instruction: TargetWriteInstruction,
) -> TargetExpectation:
    """The starting condition a target write states, judged against the
    family's own revision kind (`m-opt-lock`): a versioned family takes
    ``version`` and a temporal one ``tx_start``.

    An unversioned Non-Temporal family has no revision a caller could state,
    so it is refused before any argument is weighed. Otherwise stating more
    than one is refused first, because no family has two revisions; then a
    misstated kind, then a missing one, then the value itself — a stated
    ``None`` included.
    """
    mutation = instruction.mutation
    if not _requires_observation(position, shape):
        raise WriteInstructionError(
            f"{root.name}: {mutation!r} states a revision its caller observed, and "
            f"{root.name!r} is unversioned and non-temporal, so it has none to state and no "
            "write could detect a change since that observation; read it in the writing "
            "transaction and write through that read instead"
        )
    stated = _stated_conditions(instruction)
    if len(stated) > 1:
        raise WriteInstructionError(
            f"{root.name}: {mutation!r} states {list(stated)}, and a target has one condition "
            "to state"
        )
    required = "version" if _is_versioned(position) else "tx_start"
    if stated and required not in stated:
        (misstated,) = stated
        raise WriteInstructionError(_misstated(root, mutation, misstated, required))
    if not stated:
        raise WriteInstructionError(_missing(root, mutation, required))
    # A runtime caller may state a condition as any value, whatever the
    # annotation promises, so each is judged as the object it is.
    value = cast(
        "object", instruction.if_version if required == "version" else instruction.if_tx_start
    )
    if value is None:
        raise WriteInstructionError(
            f"{root.name}: {mutation!r} states {required}=None, which names no revision; state "
            f"the {required} its caller observed"
        )
    if required == "version":
        if isinstance(value, bool) or not isinstance(value, int):
            raise WriteInstructionError(
                f"{root.name}: {mutation!r} takes an integer version, and "
                f"{type(value).__name__} is no version"
            )
        return ExpectedVersion(value)
    return ExpectedTxStart(normalize_instant(_stated_instant(root, mutation, "tx_start", value)))


def _stated_conditions(instruction: TargetWriteInstruction) -> tuple[str, ...]:
    """The conditions a target write states: the ones its caller named where
    its interface tells naming from omission, else every one carrying a
    value."""
    if instruction.stated is not None:
        return instruction.stated
    stated: tuple[str, ...] = ()
    if instruction.if_version is not None:
        stated += ("version",)
    if instruction.if_tx_start is not None:
        stated += ("tx_start",)
    return stated


_REVISIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "version": "the version of the state the write starts from as its caller last observed it",
        "tx_start": "the Transaction-Time start of the milestone the write starts from as its "
        "caller last observed it",
    }
)


def _misstated(root: EntityIdentity, mutation: str, stated: str, required: str) -> str:
    kind = {
        "version": "versioned, so its revision is its version",
        "tx_start": "temporal, so its revision is its milestone's Transaction-Time start",
    }[required]
    return f"{root.name}: {mutation!r} takes {required}, not {stated} — {root.name!r} is {kind}"


def _missing(root: EntityIdentity, mutation: str, required: str) -> str:
    return f"{root.name}: {mutation!r} requires {required}, {_REVISIONS[required]}"


def _prepare_target_payload(
    instruction: TargetWriteInstruction,
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    position: inheritance.InheritanceEntityView,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
    authored_members: Set[str] | None,
) -> tuple[Mapping[str, object], bool]:
    """A target write's row, judged, and whether it assigns any member.

    The primary key names the object and is no assignment. A deletion or
    termination names nothing else, so any other member it states is refused,
    and its key is judged as a keyed destruction's identity row is. Every other
    member an amendment or replacement states is judged as an assignment,
    whatever produced the row — so a framework-owned, read-only, or ill-typed
    member is refused as it is for an amendment. A replacement completes the
    object's writable state exactly as a source-authorized one does
    (:func:`_assigned_row`).
    """
    row = instruction.row
    key = position.primary_key.identity.name
    _judge_row_members(model, entity, position.member_selection, row, authored_members, "target")
    if key not in row:
        raise WriteInstructionError(
            f"{entity.identity.name}: a target write names the object it writes by its primary "
            f"key, and this row states no {key!r}"
        )
    if instruction.mutation in DESTRUCTIVE_MUTATIONS:
        stated = sorted(name for name in row if name != key)
        if stated:
            raise WriteInstructionError(
                f"{entity.identity.name}: a target {instruction.mutation!r} names its "
                f"object by its primary key alone, and this row also states {stated}"
            )
        identity = _transform_row(
            position.member_selection,
            entity,
            row,
            converter=converter,
            source_access=source_access,
            fill_missing_many=False,
        )
        validate_write(
            entity,
            identity.value,
            model,
            mutation=instruction.mutation,
            known_failures=identity.failures,
        )
        return identity.value, False
    prepared = _assigned_row(
        model,
        entity,
        position,
        row,
        replaces=instruction.mutation in REPLACE_MUTATIONS,
        converter=converter,
        source_access=source_access,
    )
    return prepared, _states_beside(key, (prepared,))


def _judge_row_members(
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    selection: inheritance.EntityMemberSelection,
    row: Mapping[str, object],
    authored_members: Set[str] | None,
    described: str,
) -> None:
    """Refuse a row whose members its target's family cannot write: a
    sibling-branch or derived member first, then an authored framework-owned
    one, then an undeclared one."""
    try:
        inheritance.validate_subtype_write(model, entity, row)
    except inheritance.InheritanceError as error:
        raise WriteRejectedError(error.rule, str(error)) from error
    if authored_members is not None:
        _refuse_framework_owned(entity, selection, authored_members)
    members = selection.shape.by_name
    unknown = sorted(name for name in row if name not in members)
    if unknown:
        raise WriteInstructionError(
            f"{entity.identity.name}: {described} write row names undeclared member(s) {unknown}"
        )


def _assigned_row(
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    position: inheritance.InheritanceEntityView,
    row: Mapping[str, object],
    *,
    replaces: bool,
    converter: _LeafConverter,
    source_access: SourceAccess,
) -> Mapping[str, object]:
    """``row`` prepared as the members one existing object is assigned, every
    member but its key judged as an assignment.

    A replacement states the object's complete writable state, whatever
    authorized it: an omitted required member is refused, an omitted nullable
    one is written empty, and an omitted ``many`` the empty collection, so no
    value is ever carried forward from the state it replaces.
    """
    selection = position.member_selection
    key = position.primary_key.identity.name
    transformed = _transform_row(
        selection,
        entity,
        row,
        converter=converter,
        source_access=source_access,
        fill_missing_many=replaces,
    )
    prepared = _completed(entity, position, transformed.value) if replaces else transformed.value
    for name, value in prepared.items():
        if name == key:
            continue
        failure = _member_failure(selection, name, transformed.failures)
        _judge_prepared_assignment(
            entity,
            _declared_member(selection, name),
            value,
            known_violation=failure,
            known_value_valid=failure is None,
        )
    if transformed.failures:
        # Every other check a sparse row's validation makes is one the
        # judgement above already made, since no `many` member is nullable;
        # an authoring failure, the key's included, is what is left to report.
        validate_write(
            entity, prepared, model, mutation="amend", known_failures=transformed.failures
        )
    return prepared


def _completed(
    entity: EntityMetadata,
    position: inheritance.InheritanceEntityView,
    row: Mapping[str, object],
) -> Mapping[str, object]:
    """``row`` with every writable member it omits written empty, or refused
    where the member is required."""
    owner = entity.identity.name
    completed = dict(row)
    for attribute in position.applicable_attributes:
        name = attribute.identity.name
        if (
            name in row
            or attribute.framework_owned
            or attribute.read_only
            or isinstance(attribute.primary_key, PrimaryKey)
        ):
            continue
        if not attribute.nullable:
            raise WriteRejectedError(
                "write-required-attribute-missing",
                f"{owner}.{name}: a replacement states every required member, and this one "
                "is absent",
            )
        completed[name] = None
    for value_object in position.applicable_value_objects:
        name = value_object.identity.path[-1]
        if name in row:
            continue
        if not value_object.nullable:
            raise WriteRejectedError(
                "write-required-value-object-missing",
                f"{owner}.{name}: a replacement states every required member, and this one "
                "is absent",
            )
        completed[name] = None
    return MappingProxyType(completed)


def _profile(shape: temporal_read.TemporalShape | None) -> str:
    return (
        "a Transaction-Time-Only"
        if isinstance(shape, temporal_read.TransactionTimeOnly)
        else "a non-temporal"
    )


def _stated_instant(root: EntityIdentity, mutation: str, bound: str, value: object) -> dt.datetime:
    """``value`` as the ``timestamp`` a Valid-Time bound has to be.

    Total over what a caller can actually pass, which a type annotation is not:
    a value of another type is no `m-core` instant at all, so it keeps
    :class:`~parallax.core.base.InstantError` — the class a naive datetime earns
    one step later — rather than leaving an ``AttributeError`` where a verdict
    belongs.
    """
    if not isinstance(value, dt.datetime):
        raise InstantError(
            f"{root.name}: {mutation!r} takes an aware datetime for {bound}, "
            f"and {type(value).__name__} is no `timestamp`"
        )
    return value


def _prepare_keyed_payload(
    instruction: KeyedWriteInstruction,
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    position: inheritance.InheritanceEntityView,
    valid_time_window: TimeInterval | None,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
    authored_members: Set[str] | None,
) -> PreparedKeyedInstruction:
    """Judge a keyed write's rows: subtype shape, members, then values, and
    whether any of them assigns a member beside the key.

    A keyed row key must name a member the target's family makes applicable —
    ANCESTRY-EFFECTIVE, so a concrete subtype's write naming an inherited key is
    declared. Sibling-branch and framework-owned-metadata fields are classified
    more specifically, and first, by ``inheritance.validate_subtype_write``.

    An explicit Wire insert payload may name an application-assigned primary key
    but never a framework-owned member: the interval bounds are stamped from the
    Clock Strategy and the version is derived. A neutral instruction row states
    content rather than authorship, so it carries such cells unjudged here. An
    explicit amendment judges each assigned member as an assignment, and a
    replacement completes and judges the object's whole writable state exactly
    as a caller-conditioned one does.
    """
    selection = position.member_selection
    key = position.primary_key.identity.name
    inserting = instruction.mutation in INSERT_MUTATIONS
    for row in instruction.rows:
        _judge_row_members(
            model,
            entity,
            selection,
            row,
            authored_members if inserting else None,
            "keyed",
        )
    if instruction.mutation in REPLACE_MUTATIONS:
        replaced = tuple(
            _assigned_row(
                model,
                entity,
                position,
                row,
                replaces=True,
                converter=converter,
                source_access=source_access,
            )
            for row in instruction.rows
        )
        return _prepared_keyed_instruction(
            instruction.mutation,
            _states_beside(key, replaced),
            entity,
            replaced,
            valid_time_window,
        )
    transformed = tuple(
        _transform_row(
            selection,
            entity,
            row,
            converter=converter,
            source_access=source_access,
            fill_missing_many=inserting,
        )
        for row in instruction.rows
    )
    if authored_members is not None and not inserting:
        if len(transformed) != 1:
            raise WriteInstructionError(
                "a keyed assignment set applies only to one addressed write row"
            )
        (only,) = transformed
        for name in authored_members:
            failure = _member_failure(selection, name, only.failures)
            _judge_prepared_assignment(
                entity,
                _declared_member(selection, name),
                only.value[name],
                known_violation=failure,
                known_value_valid=failure is None,
            )
    for result in transformed:
        validate_write(
            entity,
            result.value,
            model,
            mutation=instruction.mutation,
            known_failures=result.failures,
        )
    rows = tuple(result.value for result in transformed)
    return _prepared_keyed_instruction(
        instruction.mutation, _states_beside(key, rows), entity, rows, valid_time_window
    )


def _states_beside(key: str, rows: tuple[Mapping[str, object], ...]) -> bool:
    return any(name != key for row in rows for name in row)


def _refuse_framework_owned(
    entity: EntityMetadata,
    selection: inheritance.EntityMemberSelection,
    authored_members: Set[str],
) -> None:
    for name in authored_members:
        attribute = selection.attribute(name)
        if attribute is not None and attribute.framework_owned:
            raise WriteInstructionError(
                f"{entity.identity.canonical}.{name}: framework-owned fields may not be "
                "assigned — the interval bounds are stamped from the Clock Strategy and the "
                "optimistic-lock version is derived"
            )


def _prepare_predicate_payload(
    instruction: PredicateWriteInstruction,
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    position: inheritance.InheritanceEntityView,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
) -> PreparedPredicateInstruction:
    """Judge a predicate write's payload in `m-case-format`'s order: the
    selecting predicate, the family refusal, then the row it assigns.

    The predicate is measured with the whole ``validate_predicate``
    vocabulary: a canonical node is validated, an interpreting adapter invoked,
    once, at the target's own position. An inheritance-family target is then refused
    (``subtype-write-set-based-unsupported``) before any member, so
    ancestry resolution never arises for one.

    An amendment's assignments form the one row it assigns every selected
    object: each reference is judged before any value, and then the row is
    judged member by member as an amendment of one object's row is. Assigning
    nothing is the empty amendment, judged like any other. A replacement's row
    names declared members only, and is completed and judged exactly as every
    other replacement's is (:func:`_assigned_row`). A key it states addresses
    nothing, since the predicate selects the rows, so it is dropped once the
    row is judged and is never written.
    """
    predicate = instruction.target.predicate
    validated = (
        predicate_algebra.validate_predicate(entity, predicate, model)
        if isinstance(predicate, PredicateNode)
        else predicate(entity, predicate_algebra.root_position(model, entity))
    )
    inheritance.reject_predicate_write(entity)
    selection = ResolvedMutationSelection(entity, validated)
    if instruction.mutation not in ASSIGNMENT_MUTATIONS:
        return _prepared_predicate_instruction(instruction.mutation, selection, _NO_ROW)
    row = instruction.row
    if row is None:
        row = _row_from_assignments(model, entity, position, instruction.assignments)
    else:
        _judge_row_members(model, entity, position.member_selection, row, None, "predicate")
    assigned = _assigned_row(
        model,
        entity,
        position,
        row,
        replaces=instruction.mutation in REPLACE_MUTATIONS,
        converter=converter,
        source_access=source_access,
    )
    key = position.primary_key.identity.name
    if key in assigned:
        assigned = MappingProxyType(
            {name: value for name, value in assigned.items() if name != key}
        )
    return _prepared_predicate_instruction(instruction.mutation, selection, assigned)


_NO_ROW: Final[Mapping[str, object]] = MappingProxyType({})


def _row_from_assignments(
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    position: inheritance.InheritanceEntityView,
    assignments: Sequence[WriteAssignment],
) -> dict[str, object]:
    """The member-name row ``assignments`` assign, in authored order.

    A reference must name a member of the exact target, once, and never its
    primary key, which a predicate-selected write never changes. The owner
    segment is RESOLVED rather than compared as text, so a canonical spelling
    names the target it denotes while an ambiguous bare one — which resolves
    nowhere — stays refused.
    """
    selection = position.member_selection
    row: dict[str, object] = {}
    for assignment in assignments:
        owner_spelling, _, name = assignment.attr.rpartition(".")
        owner = entity_by_name(model, owner_spelling)
        member = selection.binding(name)
        if owner is None or owner.identity != entity.identity or member is None:
            raise WriteInstructionError(
                f"{entity.identity.name}: assignment {assignment.attr!r} does not name a "
                f"declared member of {entity.identity.canonical}"
            )
        if name in row:
            raise WriteInstructionError(
                f"{entity.identity.name}: assignment {assignment.attr!r} is duplicated — each "
                "member may be assigned at most once"
            )
        if isinstance(member, AttributeMetadata) and isinstance(member.primary_key, PrimaryKey):
            _judge_prepared_assignment(
                entity, member, assignment.value, known_violation=None, known_value_valid=True
            )
        row[name] = assignment.value
    return row


def _judge_prepared_assignment(
    target: EntityMetadata,
    member: _DeclaredMember,
    value: object,
    *,
    known_violation: AuthoringViolation | None,
    known_value_valid: bool,
) -> None:
    """Judge one already-resolved assignment, as the addressed target's refusal.

    The shared judgment names the member relative to its own owner, so the
    reason is qualified with the target the write addressed.
    """
    try:
        judge_assignment(
            member,
            value,
            known_violation=known_violation,
            known_value_valid=known_value_valid,
        )
    except WriteAssignmentError as error:
        raise WriteInstructionError(f"{target.identity.canonical}.{error}") from error


def assigned_members(
    model: AcceptedMetamodel, entity: EntityMetadata, assignments: Sequence[WriteAssignment]
) -> dict[str, object]:
    """The members ``assignments`` assign to one object of ``entity``, keyed by
    name, each reference judged before any of them is flattened into a row.

    A reference names the member through its owner: the owner must be
    ``entity`` or one of its ancestors, and must itself declare or inherit the
    member, so an inherited member assigned through its declaring ancestor
    applies to a concrete descendant while a descendant's, a sibling's, or a
    stranger's member is refused rather than having its qualifier discarded. Each member is
    assigned at most once; a second assignment of it is refused rather than
    silently overwriting the first. The values are judged as assignments when
    the row they form is prepared.
    """
    position = _family_position(model, entity)
    ancestry = frozenset(position.ancestry)
    key = position.primary_key.identity.name
    row: dict[str, object] = {}
    for assignment in assignments:
        attr = assignment.attr
        owner_spelling, _, name = attr.rpartition(".")
        owner = entity_by_name(model, owner_spelling) if _ASSIGNMENT_REF.match(attr) else None
        if (
            owner is None
            or owner.identity not in ancestry
            or _member_selection(model, owner).binding(name) is None
        ):
            raise WriteInstructionError(
                f"{entity.identity.name}: assignment {attr!r} does not name a member "
                f"{entity.identity.canonical} declares or inherits"
            )
        if name == key:
            raise WriteInstructionError(
                f"{entity.identity.canonical}.{name}: primary-key fields may not be assigned — "
                "the key addresses the object a write changes"
            )
        if name in row:
            raise WriteInstructionError(
                f"{entity.identity.name}: assignment {attr!r} is duplicated — each member may "
                "be assigned at most once"
            )
        row[name] = assignment.value
    return row


def addressed_members(
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    address: tuple[tuple[str, object], ...],
    document: Mapping[str, object],
) -> Mapping[str, object]:
    """``document``'s members other than the key, once every key member it
    states is judged to name the object whose key members ``address`` pairs
    with their values.

    A source supplies the address a source-authorized write addresses, so a
    key member its caller also states is addressing data the write checks and
    then sets aside: never an assignment, a replacement member, or an override
    of that address. Each is decoded through the key's declared type first, so
    a key member that is no value of that type is refused as such, and one
    naming another object is refused before anything is buffered.
    """
    stated = {name: addressed for name, addressed in address if name in document}
    key = _family_position(model, entity).primary_key
    for name, addressed in stated.items():
        value = _decoded_wire(key.type, document[name], f"{entity.identity.canonical}.{name}")
        if value != addressed:
            raise WriteInstructionError(
                f"{entity.identity.canonical}.{name}: the document names {document[name]!r}, and "
                "the source this write addresses is another object — a key member addresses "
                "the write and never changes it"
            )
    return {name: member for name, member in document.items() if name not in stated}


def coerce_typed_row(
    row: Mapping[str, object], model: AcceptedMetamodel, entity: EntityMetadata
) -> Mapping[str, object]:
    """``row``'s members in the managed carriers :func:`prepare_typed_write`
    produces, judged by nothing.

    For the state a write is addressed AGAINST, read back to be weighed against
    what that write's caller authored. Every rule preparation applies is a rule
    about what a caller states in the call being prepared, and this side states
    nothing in it, so no name, value, assignment, or temporal rule is applied
    here, and this is never a door for caller input.

    Coercion rather than decoding, because a runtime argument already carries a
    native value: what this side owes the weighing is the width projection and
    normalization the authoring producer applies and nothing else, so a member
    restored to the `float32` its own read published is the same value on both
    sides rather than differing by the projection alone.

    Judging it would refuse the write that repairs it. State a write is addressed
    against is state some earlier door admitted, and a constraint tightened since
    then makes correcting that member the whole point of the call.
    """
    return _transform_row(
        _member_selection(model, entity),
        entity,
        row,
        converter=_coerce_typed_leaf,
        source_access=BORROWED_SOURCE_ACCESS,
        fill_missing_many=False,
    ).value


type _LeafConverter = Callable[[Leaf, object, str], tuple[object, bool]]
type _DeclaredMember = AttributeMetadata | ValueObjectMetadata


def _family_position(
    model: AcceptedMetamodel, entity: EntityMetadata
) -> inheritance.InheritanceEntityView:
    position = inheritance.view(model).entity(entity.identity)
    if position is None:
        raise RuntimeError(f"{entity.identity.canonical}: no Inheritance Facet view")
    return position


def _member_selection(
    model: AcceptedMetamodel, entity: EntityMetadata
) -> inheritance.EntityMemberSelection:
    """``entity``'s family-effective members: the whole inheritance FAMILY's
    applicable members for a participant, its own declarations otherwise."""
    return _family_position(model, entity).member_selection


def _family_root(model: AcceptedMetamodel, entity: EntityMetadata) -> EntityIdentity:
    return _family_position(model, entity).root


def _declared_member(selection: inheritance.EntityMemberSelection, name: str) -> _DeclaredMember:
    member = selection.binding(name)
    if member is None:  # pragma: no cover - member honesty already refused an undeclared name
        raise WriteInstructionError(f"{name!r} names no declared member")
    return member


def _transform_row(
    selection: inheritance.EntityMemberSelection,
    entity: EntityMetadata,
    row: Mapping[str, object],
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
    fill_missing_many: bool,
) -> PreparedDocumentAuthoring:
    return prepare_authoring(
        selection.shape,
        row,
        source_access=source_access,
        normalize_leaf=converter,
        path=entity.identity.canonical,
        fill_missing_many=fill_missing_many,
        allow_root_markers=True,
    )


def _member_failure(
    selection: inheritance.EntityMemberSelection,
    name: str,
    failures: Mapping[int, AuthoringViolation],
) -> AuthoringViolation | None:
    if not failures:
        return None
    position = selection.shape.position(name)
    return None if position is None else failures.get(position)


def _coerce_typed_leaf(leaf: Leaf, value: object, path: str) -> tuple[object, bool]:
    neutral_type = leaf.type
    managed = coerce_neutral_input(value, neutral_type)
    return freeze_retained_value(managed), matches_neutral_type(managed, neutral_type)


def _decode_wire_leaf(leaf: Leaf, value: object, path: str) -> tuple[object, bool]:
    return _decoded_wire(leaf.type, value, path), True


def _decoded_wire(neutral_type: NeutralType, value: object, path: str) -> object:
    try:
        return freeze_retained_value(decode_wire(neutral_type, cast("WireValue", value)))
    except WireDecodingError as error:
        raise InstructionRejectedError(
            f"neutral-literal-{error.reason}",
            f"{path}: {error}",
        ) from error


def resolve_target(model: AcceptedMetamodel, name: str) -> EntityMetadata:
    """The accepted Metadata a write's bare-or-canonical target names, by
    :func:`~parallax.core.metamodel.entity_by_name`'s ambiguity-rejecting rule.

    That rule answers a miss for two different mistakes, and this is the boundary
    every externally produced instruction crosses, so the two are classified
    apart: a bare spelling two namespaces share is the normative
    `reference-ambiguous-entity-name` refusal
    (:class:`InstructionRejectedError`, `m-predicate` "Entity spellings in a
    reference position"), naming the canonical spellings that would resolve;
    anything else names no declared Entity at all and stays a plain
    :class:`WriteInstructionError`. Classifying here is also what keeps an
    ambiguous instruction out of the planner, whose own target lookup would
    answer the same miss by leaving the write unbound to any observation.

    Exported because a Wire insert must resolve the Entity it names before its
    source facts can be judged, and has to reach the same classifications the
    instruction itself would have earned one step later.
    """
    entity = entity_by_name(model, name)
    if entity is not None:
        return entity
    shared = ambiguous_entity_spellings(model, name)
    if shared:
        raise InstructionRejectedError(
            REFERENCE_AMBIGUOUS_ENTITY_NAME,
            f"the bare Entity spelling {name!r} is shared by {list(shared)}, so it names no "
            "single Entity in this model and the write resolves nowhere (m-predicate reference "
            "resolution); spell the one this write means",
        )
    raise WriteInstructionError(f"the connected model declares no entity {name!r} for this write")
