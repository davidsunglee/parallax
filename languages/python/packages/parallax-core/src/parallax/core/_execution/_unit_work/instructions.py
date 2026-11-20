from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import chain, islice
from types import MappingProxyType
from typing import Final, Literal, cast

from parallax.core._execution._unit_work._errors import WRITE_KEY_ABSENT
from parallax.core._execution._unit_work.preparation import (
    TYPED,
    UNSTATED,
    WRITE_INSTRUCTION_INVALID,
    CompletePayload,
    EntityPreparation,
    PartialPayload,
    StatedMember,
    TargetRevisionArguments,
    Unstated,
    WritePreparation,
    WriteRepresentation,
    refuse_observation_keys,
)
from parallax.core.internal import inheritance, temporal_read
from parallax.core.internal import predicate as predicate_algebra
from parallax.core.internal.base import (
    INFINITY,
    INSTANT_INVALID,
    TIMESTAMP,
    InvalidValueError,
    NeutralType,
    UsageError,
    coerce_neutral_input,
    normalize_instant,
)
from parallax.core.internal.batch_write import (
    SET_BASED_WRITE_TARGET_UNSUPPORTED,
    judge_readless_target,
)
from parallax.core.internal.document_codec._plan import AuthoringRefusal
from parallax.core.internal.metamodel import (
    WRITE_ASSIGNMENT_VALUE_TYPE_MISMATCH,
    AuthoringViolation,
    CompiledEntity,
    EntityIdentity,
    MemberDefinition,
    MemberShape,
    Multiplicity,
    PersistenceMode,
    ScalarDefinition,
    entity_by_name,
    judge_assignment,
)
from parallax.core.internal.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.internal.metamodel._states import ambiguous_entity_spellings
from parallax.core.internal.planned_step.columns import freeze_retained_value
from parallax.core.internal.planned_step.managed_row import ManagedRow, empty_row, managed_row
from parallax.core.internal.planned_step.steps import (
    ResolvedMutationSelection,
)
from parallax.core.internal.predicate import (
    REFERENCE_AMBIGUOUS_ENTITY_NAME,
    PredicateInterpretation,
    PredicateNode,
)
from parallax.core.internal.temporal_read import TimeInterval
from parallax.core.internal.wire import (
    WireValue,
    decode_wire,
    encode_wire,
    is_decoding_refusal,
    located_refusal,
)

__all__ = [
    "AMEND_MUTATIONS",
    "ASSIGNMENT_MUTATIONS",
    "BOUNDED_MUTATIONS",
    "DESTRUCTIVE_MUTATIONS",
    "FRAMEWORK_OWNED_MEMBER_ASSIGNED",
    "INSERT_MUTATIONS",
    "READ_ONLY_WRITE_TARGET",
    "REPLACE_MUTATIONS",
    "SET_BASED_WRITE_TARGET_UNSUPPORTED",
    "WRITE_INSTRUCTION_INVALID",
    "WRITE_REQUIRED_ATTRIBUTE_MISSING",
    "WRITE_REQUIRED_VALUE_OBJECT_MISSING",
    "WRITE_VALUE_TYPE_MISMATCH",
    "ExpectedTxStart",
    "ExpectedVersion",
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
    "WriteRejectionCode",
    "derive_keyed_instruction",
    "deserialize",
    "key_absent_refusal",
    "keyed_instruction_from_target",
    "prepare_insert",
    "prepare_keyed_write",
    "prepare_predicate_write",
    "prepare_target_write",
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

type WriteRejectionCode = Literal[
    "write-instruction-invalid",
    "set-based-write-target-unsupported",
    "read-only-write-target",
    "framework-owned-member-assigned",
    "write-required-attribute-missing",
    "write-required-value-object-missing",
    "write-value-type-mismatch",
    "write-assignment-value-type-mismatch",
]
"""Why a write instruction is refused before any SQL, as a
:class:`~parallax.core.internal.base.UsageError`.

``write-instruction-invalid`` is this binding's own: the instruction is not a
well-formed canonical instruction its target can mean.
``write-assignment-value-type-mismatch`` is the assignment judgement's own: a
value assigned beside the key does not fit its member. Every other code is the
core ``rejectedRule`` spelling of a model-aware rule the instruction breaks.
The two value-type mismatches and the two required-member codes are raised as
:class:`~parallax.core.internal.base.InvalidValueError`.
"""

READ_ONLY_WRITE_TARGET: Final = "read-only-write-target"
"""Any write whose target family's effective Persistence Mode is ReadOnly
(`m-unit-work`)."""

FRAMEWORK_OWNED_MEMBER_ASSIGNED: Final = "framework-owned-member-assigned"
WRITE_REQUIRED_ATTRIBUTE_MISSING: Final = "write-required-attribute-missing"
WRITE_REQUIRED_VALUE_OBJECT_MISSING: Final = "write-required-value-object-missing"
WRITE_VALUE_TYPE_MISMATCH: Final = "write-value-type-mismatch"


@dataclass(frozen=True, slots=True)
class KeyedWriteInstruction:
    """An authored keyed write: a ``mutation`` on one ``entity`` carrying one
    flat attribute-named neutral write ``row``.

    ``valid_from`` / ``until`` are the Valid-Time bounds; a
    bounded ``*Until`` mutation carries both, a plain temporal mutation carries only
    ``valid_from`` (window ``[valid_from, infinity)``), and a non-temporal
    mutation carries neither. The Transaction-Time instant is never a field here.
    Whether the bounds suit the target is judged by preparation, not here.
    """

    mutation: KeyedMutation
    entity: str
    row: Mapping[str, object]
    valid_from: dt.datetime | None = None
    until: dt.datetime | None = None

    def __post_init__(self) -> None:
        refuse_observation_keys(self.row)
        if not isinstance(self.row, MappingProxyType):
            object.__setattr__(self, "row", MappingProxyType(dict(self.row)))


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
    finalized :class:`~parallax.core.internal.unit_work.
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
            raise UsageError(
                WRITE_INSTRUCTION_INVALID,
                f"predicate write: `{self.mutation}` assigns no members and carries no "
                "`assignments`",
            )
        replaces = self.mutation in REPLACE_MUTATIONS
        if self.row is None:
            if replaces:
                raise UsageError(
                    WRITE_INSTRUCTION_INVALID,
                    f"predicate write: `{self.mutation}` states each selected object's whole "
                    "writable state and carries a `row`",
                )
            return
        if not replaces:
            raise UsageError(
                WRITE_INSTRUCTION_INVALID,
                f"predicate write: `{self.mutation}` states no whole state and carries no `row`",
            )
        refuse_observation_keys(self.row)
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
    ever read off the row or off any read's evidence.
    """

    mutation: TargetMutation
    entity: str
    row: Mapping[str, object]
    if_version: int | None = None
    if_tx_start: dt.datetime | None = None
    valid_from: dt.datetime | None = None
    until: dt.datetime | None = None

    def __post_init__(self) -> None:
        refuse_observation_keys(self.row)
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
    target: CompiledEntity
    rows: tuple[ManagedRow, ...]
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
    row: ManagedRow

    @property
    def assigns(self) -> bool:
        return self.row.presence != 0


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
    target: CompiledEntity
    row: ManagedRow
    valid_time_window: TimeInterval | None
    expectation: TargetExpectation


PreparedInstruction = PreparedKeyedInstruction | PreparedPredicateInstruction
"""A prepared keyed or predicate instruction: a unit of work admits a keyed one
to its buffer and executes a predicate one at the call."""


def _prepared_keyed_instruction(
    mutation: KeyedMutation,
    assigns: bool,
    target: CompiledEntity,
    rows: tuple[ManagedRow, ...],
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
    row: ManagedRow,
) -> PreparedPredicateInstruction:
    prepared = object.__new__(PreparedPredicateInstruction)
    object.__setattr__(prepared, "mutation", mutation)
    object.__setattr__(prepared, "selection", selection)
    object.__setattr__(prepared, "row", row)
    return prepared


def _prepared_target_instruction(
    mutation: TargetMutation,
    assigns: bool,
    target: CompiledEntity,
    row: ManagedRow,
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


def key_absent_refusal(entity: EntityIdentity, mutation: str) -> UsageError:
    """The refusal of a ``mutation`` other than an insert handed a value of
    ``entity`` whose key is absent (:data:`WRITE_KEY_ABSENT`)."""
    return UsageError(
        WRITE_KEY_ABSENT,
        f"{entity.canonical}: `{mutation}` addresses the object a value's key names, and this "
        "value has no key; insert it to give it one, and write the value the insert answers",
    )


def key_null_refusal(entity: EntityIdentity, key: str) -> InvalidValueError:
    """The refusal of a write stating ``entity``'s ``key`` as null, which the
    key's own non-null type refuses (:data:`WRITE_REQUIRED_ATTRIBUTE_MISSING`)."""
    return InvalidValueError(
        WRITE_REQUIRED_ATTRIBUTE_MISSING,
        f"{entity.name}.{key}: required attribute is absent (or null)",
    )


def derive_keyed_instruction(
    prepared: PreparedKeyedInstruction,
    rows: tuple[ManagedRow, ...],
    *,
    mutation: KeyedMutation | None = None,
    assigns: bool | None = None,
) -> PreparedKeyedInstruction:
    """Derive a keyed prepared product over already-managed ``rows``, under
    ``mutation`` where composition changed the verb over the same window.

    ``rows`` keep ``prepared``'s ``assigns`` unless ``assigns`` states another:
    a derivation keeping or splitting its assigning rows keeps it, and one
    overlaying another write's members states whether either assigns."""
    return _prepared_keyed_instruction(
        prepared.mutation if mutation is None else mutation,
        prepared.assigns if assigns is None else assigns,
        prepared.target,
        rows,
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

    Discriminates the three shapes in order: ``target`` names a predicate write
    (whose replacement carries its ``row`` beside it), a stated revision
    (``ifVersion`` or ``ifTxStart``) a target write, and anything else a keyed
    write, whose ``row`` carries no revision. It validates the closed
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
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"write instruction must be a mapping, got {type(doc).__name__}",
        )
    node = cast("Mapping[str, object]", doc)
    if "target" in node:
        return _predicate(node)
    if "ifVersion" in node or "ifTxStart" in node:
        return _target_write(node)
    return _keyed(node)


def _reject_extra(node: Mapping[str, object], allowed: frozenset[str], shape: str) -> None:
    extra = sorted(set(node) - allowed)
    if extra:
        # `at` is the corpus's Clock-context alias, an UNEXPECTED key here — the
        # canonical instruction never carries a Transaction-Time instant.
        raise UsageError(WRITE_INSTRUCTION_INVALID, f"{shape}: unexpected key(s) {extra}")


def _require(node: Mapping[str, object], keys: tuple[str, ...], shape: str) -> None:
    missing = sorted(k for k in keys if k not in node)
    if missing:
        raise UsageError(WRITE_INSTRUCTION_INVALID, f"{shape}: missing required key(s) {missing}")


def _mutation(node: Mapping[str, object], allowed: frozenset[str], shape: str) -> str:
    value = node.get("mutation")
    if not isinstance(value, str) or value not in allowed:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID, f"{shape}: `mutation` must be one of {sorted(allowed)}"
        )
    return value


def _entity_name(node: Mapping[str, object], key: str, shape: str) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID, f"{shape}: `{key}` must be a non-empty entity name"
        )
    return value


def _bound(node: Mapping[str, object], key: str, shape: str) -> dt.datetime | None:
    if key not in node:
        return None
    value = node[key]
    if not isinstance(value, str) or not value:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID, f"{shape}: `{key}` must be a non-empty instant string"
        )
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
            raise UsageError(
                WRITE_INSTRUCTION_INVALID,
                f"{shape}: `{mutation}` is bounded and MUST carry both `validFrom` and `until`",
            )
    elif until is not None:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{shape}: `{mutation}` is unbounded and MUST NOT carry `until`",
        )


def _row(node: Mapping[str, object], shape: str) -> dict[str, object]:
    raw = node.get("row")
    if not isinstance(raw, Mapping):
        raise UsageError(WRITE_INSTRUCTION_INVALID, f"{shape}: `row` must be a mapping")
    # A neutral write-row value is opaque JSON (a scalar or a whole value-object
    # document); its metamodel role decides its meaning at preparation, not its
    # shape, so the serde keeps it verbatim.
    return dict(cast("Mapping[str, object]", raw))


def _keyed(node: Mapping[str, object]) -> KeyedWriteInstruction:
    _reject_extra(
        node, frozenset({"mutation", "entity", "row", "validFrom", "until"}), "keyed write"
    )
    _require(node, ("mutation", "entity", "row"), "keyed write")
    mutation = _mutation(node, _KEYED_MUTATIONS, "keyed write")
    entity = _entity_name(node, "entity", "keyed write")
    row = _row(node, "keyed write")
    valid_from = _bound(node, "validFrom", "keyed write")
    until = _bound(node, "until", "keyed write")
    _check_valid_time_bounds(mutation, valid_from, until, "keyed write")
    return KeyedWriteInstruction(
        mutation=cast("KeyedMutation", mutation),
        entity=entity,
        row=row,
        valid_from=valid_from,
        until=until,
    )


def _target(node: Mapping[str, object]) -> PredicateSelection:
    raw = node.get("target")
    if not isinstance(raw, Mapping):
        raise UsageError(WRITE_INSTRUCTION_INVALID, "predicate write: `target` must be a mapping")
    target = cast("Mapping[str, object]", raw)
    _reject_extra(target, frozenset({"entity", "predicate"}), "predicate write target")
    _require(target, ("entity", "predicate"), "predicate write target")
    entity = _entity_name(target, "entity", "predicate write target")
    predicate_doc = target.get("predicate")
    if not isinstance(predicate_doc, Mapping):
        raise UsageError(
            WRITE_INSTRUCTION_INVALID, "predicate write: `target.predicate` must be a mapping"
        )
    # The embedded predicate is a canonical m-predicate node — the sole write-side
    # reach into the algebra; predicate rejects a malformed one.
    predicate = predicate_algebra.deserialize(cast("Mapping[str, object]", predicate_doc))
    return PredicateSelection(entity=entity, predicate=predicate)


def _assignments(node: Mapping[str, object]) -> tuple[WriteAssignment, ...]:
    raw = node.get("assignments")
    if not isinstance(raw, list):
        raise UsageError(WRITE_INSTRUCTION_INVALID, "predicate write: `assignments` must be a list")
    out: list[WriteAssignment] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, Mapping):
            raise UsageError(
                WRITE_INSTRUCTION_INVALID, "predicate write: each assignment must be a mapping"
            )
        assignment = cast("Mapping[str, object]", item)
        _reject_extra(assignment, frozenset({"attr", "value"}), "predicate write assignment")
        _require(assignment, ("attr", "value"), "predicate write assignment")
        attr = assignment.get("attr")
        if not isinstance(attr, str) or _ASSIGNMENT_REF.match(attr) is None:
            raise UsageError(
                WRITE_INSTRUCTION_INVALID,
                f"predicate write: assignment `attr` must be a `Class.member` "
                f"reference, got {attr!r}",
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
            raise UsageError(
                WRITE_INSTRUCTION_INVALID, f"predicate write: `{mutation}` MUST carry `{key}`"
            )
        if key != payload and key in node:
            raise UsageError(
                WRITE_INSTRUCTION_INVALID, f"predicate write: `{mutation}` MUST NOT carry `{key}`"
            )
    return PredicateWriteInstruction(
        mutation=cast("PredicateMutation", mutation),
        target=target,
        assignments=_assignments(node) if payload == "assignments" else (),
        row=_row(node, "predicate write") if payload == "row" else None,
    )


def _target_write(node: Mapping[str, object]) -> TargetWriteInstruction:
    _reject_extra(
        node,
        frozenset({"mutation", "entity", "row", "ifVersion", "ifTxStart", "validFrom", "until"}),
        "target write",
    )
    _require(node, ("mutation", "entity", "row"), "target write")
    mutation = _mutation(node, _TARGET_MUTATIONS, "target write")
    entity = _entity_name(node, "entity", "target write")
    row = _row(node, "target write")
    if "ifVersion" in node and "ifTxStart" in node:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            "target write: states both `ifVersion` and `ifTxStart`, and a target has one "
            "revision to state",
        )
    if_version: int | None = None
    if "ifVersion" in node:
        version = node["ifVersion"]
        if isinstance(version, bool) or not isinstance(version, int):
            raise UsageError(
                WRITE_INSTRUCTION_INVALID, "target write: `ifVersion` must be an integer version"
            )
        if_version = version
    valid_from = _bound(node, "validFrom", "target write")
    until = _bound(node, "until", "target write")
    _check_valid_time_bounds(mutation, valid_from, until, "target write")
    return TargetWriteInstruction(
        mutation=cast("TargetMutation", mutation),
        entity=entity,
        row=row,
        if_version=if_version,
        if_tx_start=_bound(node, "ifTxStart", "target write"),
        valid_from=valid_from,
        until=until,
    )


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
            "row": dict(instruction.row),
        }
        _emit_bounds(keyed_body, instruction.valid_from, instruction.until)
        return keyed_body
    predicate = instruction.target.predicate
    if not isinstance(predicate, PredicateNode):
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{instruction.target.entity}: a predicate write selecting through an interpreted "
            "predicate has no canonical write-instruction document",
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


def prepare_insert(
    preparation: WritePreparation,
    representation: WriteRepresentation,
    mutation: KeyedMutation,
    target: CompiledEntity,
    payload: CompletePayload,
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None,
) -> PreparedKeyedInstruction:
    """Judge one opening of ``target``: its family's persistence, its verb and
    window, then its payload's member names and its values in member order."""
    if mutation not in INSERT_MUTATIONS:
        raise ValueError(f"{mutation!r} opens no row")
    entity_preparation, _ = _writable_preparation(preparation, target)
    window = _admitted_window(preparation, target, mutation, valid_from, until, surface="keyed")
    row = _managed_row(
        preparation, entity_preparation, target, representation, mutation, payload, "keyed"
    )
    return _prepared_keyed_instruction(
        mutation, _assigns(entity_preparation, row), target, (row,), window
    )


def prepare_keyed_write(
    preparation: WritePreparation,
    representation: WriteRepresentation,
    mutation: KeyedMutation,
    target: CompiledEntity,
    payload: CompletePayload | PartialPayload,
    *,
    assignments: Sequence[WriteAssignment] = (),
    restated_key: object = UNSTATED,
    valid_from: dt.datetime | None,
    until: dt.datetime | None,
) -> PreparedKeyedInstruction:
    """Judge one keyed write of the existing object of ``target`` that
    ``payload``'s key, its source's identity, names: its family's persistence,
    its verb and window, ``assignments`` resolved into the payload, then the
    payload's member names, its key, and its other values.

    ``restated_key`` is a key the caller stated beside that identity, which
    must name the same object and is then set aside.
    """
    if mutation in INSERT_MUTATIONS:
        raise ValueError(f"{mutation!r} opens a row")
    entity_preparation, family = _writable_preparation(preparation, target)
    window = _admitted_window(preparation, target, mutation, valid_from, until, surface="keyed")
    payload = _payload_with_assignments(
        preparation.meta, entity_preparation, target, family, payload, assignments
    )
    row = _managed_row(
        preparation,
        entity_preparation,
        target,
        representation,
        mutation,
        payload,
        "keyed",
        restated_key=restated_key,
    )
    return _prepared_keyed_instruction(
        mutation, _assigns(entity_preparation, row), target, (row,), window
    )


def prepare_target_write(
    preparation: WritePreparation,
    representation: WriteRepresentation,
    mutation: TargetMutation,
    target: CompiledEntity,
    payload: CompletePayload | PartialPayload,
    *,
    assignments: Sequence[WriteAssignment] = (),
    revision: TargetRevisionArguments,
    valid_from: dt.datetime | None,
    until: dt.datetime | None,
) -> PreparedTargetInstruction:
    """Judge one caller-conditioned write of the object ``payload``'s key
    names: its family's persistence, whether that key names an object at all,
    its verb and window, its revision, then ``assignments`` resolved into the
    payload, and the payload's member names, its key, and its other values.

    The revision is judged ahead of the payload because it decides what the
    write may be at all.
    """
    entity_preparation, family = _writable_preparation(preparation, target)
    key, payload = _judged_target_key(entity_preparation, target, mutation, payload)
    window = _admitted_window(preparation, target, mutation, valid_from, until, surface="target")
    expectation = _target_expectation(preparation.meta, family, target, mutation, revision)
    if representation is TYPED:
        _refuse_structured_key(target, key)
    payload = _payload_with_assignments(
        preparation.meta, entity_preparation, target, family, payload, assignments
    )
    row = _managed_row(
        preparation, entity_preparation, target, representation, mutation, payload, "target"
    )
    return _prepared_target_instruction(
        mutation, _assigns(entity_preparation, row), target, row, window, expectation
    )


def prepare_predicate_write(
    preparation: WritePreparation,
    representation: WriteRepresentation,
    mutation: PredicateMutation,
    target: CompiledEntity,
    selection: PredicateNode | PredicateInterpretation,
    payload: CompletePayload | PartialPayload | None = None,
    *,
    assignments: Sequence[WriteAssignment] = (),
) -> PreparedPredicateInstruction:
    """Judge one predicate-selected write of every object of ``target``
    ``selection`` selects: its family's persistence, whether ``target`` can be
    written without being read, the predicate and the family, then the
    members its payload or ``assignments`` state and only then their values.

    An amendment names no key, since the predicate selects the objects it
    writes; a replacement's key is judged and then dropped.
    """
    entity_preparation, family = _writable_preparation(preparation, target)
    judge_readless_target(preparation.meta, target, family, mutation)
    resolved = _resolved_selection(preparation.meta, target, selection)
    if mutation not in ASSIGNMENT_MUTATIONS:
        return _prepared_predicate_instruction(
            mutation, resolved, empty_row(entity_preparation.selection)
        )
    payload = _payload_with_assignments(
        preparation.meta, entity_preparation, target, family, payload, assignments
    )
    if mutation in AMEND_MUTATIONS and isinstance(payload, PartialPayload):
        _refuse_key_assignment(entity_preparation, target, payload)
    row = _managed_row(
        preparation, entity_preparation, target, representation, mutation, payload, "predicate"
    )
    return _prepared_predicate_instruction(
        mutation, resolved, row.without(1 << entity_preparation.key_position)
    )


def _writable_preparation(
    preparation: WritePreparation, target: CompiledEntity
) -> tuple[EntityPreparation, inheritance.InheritanceEntityView]:
    """``target``'s preparation and family view, once its family's Persistence
    Mode admits a write."""
    family = _inheritance_entity_view(preparation.meta, target)
    _judge_write_persistence(target, family)
    return preparation.entity(target.identity), family


def _admitted_window(
    preparation: WritePreparation,
    target: CompiledEntity,
    mutation: str,
    valid_from: object,
    until: object,
    *,
    surface: _WriteSurface,
) -> TimeInterval | None:
    """The judged window of a keyed or target write, once its verb suits
    ``target`` (:func:`_judge_applicability`)."""
    model = preparation.meta
    shape = temporal_read.temporal_facet_of(model).shape(target.identity)
    return _judge_applicability(model, target, shape, mutation, valid_from, until, surface=surface)


def _judged_target_key(
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    mutation: str,
    payload: CompletePayload | PartialPayload,
) -> tuple[object, CompletePayload | PartialPayload]:
    """The key a target write's payload states, refused where it names no
    object, beside the payload still holding every value it stated."""
    if isinstance(payload, CompletePayload):
        key, values = _split_key(entity_preparation, payload.values)
        payload = CompletePayload(values, payload.unlisted_names)
    else:
        key = _stated_key(entity_preparation, payload)
    if key is entity_preparation.selection.absent:
        raise key_absent_refusal(target.identity, mutation)
    if key is None:
        raise key_null_refusal(target.identity, entity_preparation.key_name)
    return key, payload


def _refuse_structured_key(target: CompiledEntity, key: object) -> None:
    """Refuse a Typed key that is a carrier of several values rather than one
    scalar."""
    if isinstance(key, Mapping | tuple | list | set | frozenset):
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{target.identity.name}: key is the object's one scalar primary-key value, "
            f"and a {type(cast('object', key)).__name__} is no such value",
        )


def _target_expectation(
    model: AcceptedMetamodel,
    family: inheritance.InheritanceEntityView,
    target: CompiledEntity,
    mutation: str,
    revision: TargetRevisionArguments,
) -> TargetExpectation:
    """The starting condition a target write states, judged against the
    family's own revision kind (`m-concurrency`): a versioned family takes
    ``version`` and a temporal one ``tx_start``.

    An unversioned Non-Temporal family has no revision a caller could state,
    so it is refused before any argument is weighed. Otherwise stating more
    than one is refused first, because no family has two revisions; then a
    misstated kind, then a missing one, then the value itself — a stated
    ``None`` included.
    """
    root = family.root
    shape = temporal_read.temporal_facet_of(model).shape(target.identity)
    if not _requires_observation(family, shape):
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{root.name}: {mutation!r} states a revision its caller observed, and "
            f"{root.name!r} is unversioned and non-temporal, so it has none to state and no "
            "write could detect a change since that observation; read it in the writing "
            "transaction and write through that read instead",
        )
    stated = revision.stated
    if len(stated) > 1:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{root.name}: {mutation!r} states {list(stated)}, and a target has one condition "
            "to state",
        )
    required = "version" if _is_versioned(family) else "tx_start"
    if stated and required not in stated:
        (misstated,) = stated
        raise UsageError(WRITE_INSTRUCTION_INVALID, _misstated(root, mutation, misstated, required))
    if not stated:
        raise UsageError(WRITE_INSTRUCTION_INVALID, _missing(root, mutation, required))
    # A runtime caller may state a condition as any value, whatever the
    # annotation promises, so each is judged as the object it is.
    value = cast("object", revision.if_version if required == "version" else revision.if_tx_start)
    if value is None:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{root.name}: {mutation!r} states {required}=None, which names no revision; state "
            f"the {required} its caller observed",
        )
    if required == "version":
        if isinstance(value, bool) or not isinstance(value, int):
            raise UsageError(
                WRITE_INSTRUCTION_INVALID,
                f"{root.name}: {mutation!r} takes an integer version, and "
                f"{type(value).__name__} is no version",
            )
        return ExpectedVersion(value)
    return ExpectedTxStart(normalize_instant(_stated_instant(root, mutation, "tx_start", value)))


def _resolved_selection(
    model: AcceptedMetamodel,
    target: CompiledEntity,
    selection: PredicateNode | PredicateInterpretation,
) -> ResolvedMutationSelection:
    """``selection`` measured at ``target`` with the whole
    ``validate_predicate`` vocabulary — a canonical node validated, an
    interpreting adapter invoked once at the target's own position — and then
    an inheritance-family target refused before any member, so ancestry
    resolution never arises for one."""
    validated = (
        predicate_algebra.validate_predicate(target, selection, model)
        if isinstance(selection, PredicateNode)
        else selection(target, predicate_algebra.root_position(model, target))
    )
    inheritance.reject_predicate_write(target)
    return ResolvedMutationSelection(target, validated)


def _payload_with_assignments(
    model: AcceptedMetamodel,
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    family: inheritance.InheritanceEntityView,
    payload: CompletePayload | PartialPayload | None,
    assignments: Sequence[WriteAssignment],
) -> CompletePayload | PartialPayload:
    """``payload`` stating each of ``assignments`` after its own members, every
    assignment resolved before any value is judged; no payload at all states
    the assignments alone."""
    if payload is None:
        return PartialPayload(
            _resolved_assignments(model, entity_preparation, target, family, assignments)
        )
    if not assignments:
        return payload
    partial = _as_partial(payload, "an assigning write")
    assigned = _resolved_assignments(model, entity_preparation, target, family, assignments)
    return PartialPayload((*partial.stated, *assigned), partial.unlisted_names)


def _resolved_assignments(
    model: AcceptedMetamodel,
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    family: inheritance.InheritanceEntityView,
    assignments: Sequence[WriteAssignment],
) -> tuple[StatedMember, ...]:
    """The members ``assignments`` assign to one object of ``target``, in
    authored order.

    A reference names the member through its owner, RESOLVED rather than
    compared as text: the owner must be ``target`` or one of its ancestors and
    must itself declare or inherit the member, so an inherited member assigned
    through its declaring ancestor applies while a descendant's, a sibling's,
    or a stranger's member, or an ambiguous bare owner, is refused rather than
    having its qualifier discarded. The key addresses the object and is never
    assigned, and each member is assigned at most once.
    """
    ancestry = frozenset(family.ancestry)
    shape = entity_preparation.selection.members.shape
    resolved: list[StatedMember] = []
    assigned: set[int] = set()
    for assignment in assignments:
        attr = assignment.attr
        owner_spelling, _, name = attr.rpartition(".")
        owner = entity_by_name(model, owner_spelling) if _ASSIGNMENT_REF.match(attr) else None
        if (
            owner is None
            or owner.identity not in ancestry
            or _member_selection(model, owner).binding(name) is None
        ):
            raise UsageError(
                WRITE_INSTRUCTION_INVALID,
                f"{target.identity.name}: assignment {attr!r} does not name a declared member "
                f"of {target.identity.canonical}",
            )
        position = cast("int", shape.position(name))
        if position == entity_preparation.key_position:
            raise _key_assignment_refusal(entity_preparation, target)
        if position in assigned:
            raise UsageError(
                WRITE_INSTRUCTION_INVALID,
                f"{target.identity.name}: assignment {attr!r} is duplicated — each member may "
                "be assigned at most once",
            )
        assigned.add(position)
        resolved.append((position, assignment.value))
    return tuple(resolved)


def _refuse_key_assignment(
    entity_preparation: EntityPreparation, target: CompiledEntity, payload: PartialPayload
) -> None:
    """Refuse a predicate amendment stating the key, which addresses nothing
    there: the predicate selects the objects."""
    if _stated_key(entity_preparation, payload) is not entity_preparation.selection.absent:
        raise _key_assignment_refusal(entity_preparation, target)


def _key_assignment_refusal(
    entity_preparation: EntityPreparation, target: CompiledEntity
) -> UsageError:
    return UsageError(
        WRITE_INSTRUCTION_INVALID,
        f"{target.identity.canonical}.{entity_preparation.key_name}: primary-key fields may not "
        "be assigned — the key addresses the object a write changes",
    )


def _managed_row(
    preparation: WritePreparation,
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    representation: WriteRepresentation,
    mutation: str,
    payload: CompletePayload | PartialPayload,
    described: str,
    *,
    restated_key: object = UNSTATED,
) -> ManagedRow:
    """``payload`` judged as the row ``mutation`` writes: every member name
    first, then the key that addresses the object, then the rest.

    An opening's key is content its Entity may allocate, not an address, so
    an opening is judged in member order. A complete payload's values are read
    once, and copied only where their names must be judged before them.
    """
    if mutation in INSERT_MUTATIONS or mutation in REPLACE_MUTATIONS:
        complete = _as_complete(payload, mutation)
        values = complete.values
        authored = representation.complete_payload_cells == "authored"
        if authored or target.inheritance is not None or complete.unlisted_names:
            values = tuple(values)
            carried = 0 if authored else _carried(entity_preparation, mutation)
            absent = entity_preparation.selection.absent
            _judge_payload_names(
                preparation.meta,
                entity_preparation,
                target,
                mutation,
                (
                    (position, raw)
                    for position, raw in enumerate(values)
                    if raw is not absent and not carried >> position & 1
                ),
                complete.unlisted_names,
                authored=authored,
                described=described,
            )
        if mutation in INSERT_MUTATIONS:
            return _opening_row(entity_preparation, target, representation, values)
        key, values = _split_key(entity_preparation, values)
        admitted = _admitted_key(entity_preparation, target, representation, key, restated_key)
        return _replacement_row(entity_preparation, target, representation, values, admitted)
    partial = _as_partial(payload, mutation)
    _judge_payload_names(
        preparation.meta,
        entity_preparation,
        target,
        mutation,
        partial.stated,
        partial.unlisted_names,
        authored=not partial.judged_at_edit,
        described=described,
    )
    destructive = mutation in DESTRUCTIVE_MUTATIONS
    if destructive:
        _refuse_members_beside_key(entity_preparation, target, mutation, partial, described)
    key = _stated_key(entity_preparation, partial)
    admitted = _admitted_key(entity_preparation, target, representation, key, restated_key)
    if destructive or partial.judged_at_edit:
        return _stated_row(entity_preparation, target, representation, partial.stated, admitted)
    return _amendment_row(entity_preparation, target, representation, partial.stated, admitted)


def _as_complete(payload: CompletePayload | PartialPayload, write: str) -> CompletePayload:
    if not isinstance(payload, CompletePayload):
        raise ValueError(f"{write!r} states a whole state, which a partial payload is not")
    return payload


def _as_partial(payload: CompletePayload | PartialPayload, write: str) -> PartialPayload:
    if not isinstance(payload, PartialPayload):
        raise ValueError(f"{write!r} states some members, which a complete payload is not")
    return payload


def _carried(entity_preparation: EntityPreparation, mutation: str) -> int:
    """The members a carried complete payload holds that its caller never
    authored: framework-owned ones, and in a replacement read-only ones too."""
    if mutation in REPLACE_MUTATIONS:
        return entity_preparation.framework_owned | entity_preparation.read_only
    return entity_preparation.framework_owned


def _judge_payload_names(
    model: AcceptedMetamodel,
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    mutation: str,
    stated: Iterable[StatedMember],
    unlisted_names: tuple[str, ...],
    *,
    authored: bool,
    described: str,
) -> None:
    """Refuse a payload naming a member its target's family cannot write: a
    sibling-branch or derived member first, then a framework-owned one its
    caller ``authored``, then one the target does not declare."""
    if target.inheritance is not None:
        stated = tuple(stated)
        inheritance.validate_subtype_write(
            model, target, _payload_names(entity_preparation, mutation, stated, unlisted_names)
        )
    if authored and entity_preparation.framework_owned:
        _refuse_framework_owned_names(entity_preparation, target, stated)
    if unlisted_names:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{target.identity.name}: {described} write row names undeclared member(s) "
            f"{sorted(unlisted_names)}",
        )


def _payload_names(
    entity_preparation: EntityPreparation,
    mutation: str,
    stated: Iterable[StatedMember],
    unlisted_names: tuple[str, ...],
) -> dict[str, None]:
    """Every member a payload names, by name. An opening also names the key
    its Entity allocates where the caller omitted it, since the insert states
    that key before the row names its object."""
    members = entity_preparation.selection.members.shape.members
    names = {members[position].name: None for position, _ in stated}
    names.update({name: None for name in unlisted_names})
    allocation = entity_preparation.key_allocation
    if allocation is not None and mutation in INSERT_MUTATIONS:
        names.setdefault(members[allocation.position].name, None)
    return names


def _refuse_framework_owned_names(
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    stated: Iterable[StatedMember],
) -> None:
    """Refuse the first framework-owned member ``stated`` names, by its
    assignment rule and before any value is judged: its name alone refuses
    it."""
    owned = entity_preparation.framework_owned
    for position, raw in stated:
        if owned >> position & 1:
            try:
                entity_preparation.assignment_rules(position, raw)
            except UsageError as error:
                raise UsageError(
                    FRAMEWORK_OWNED_MEMBER_ASSIGNED,
                    f"{target.identity.canonical}.{error.args[1]}",
                ) from error


def _refuse_members_beside_key(
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    mutation: str,
    payload: PartialPayload,
    described: str,
) -> None:
    """Refuse a destructive write stating any member but the key that names
    its object."""
    members = entity_preparation.selection.members.shape.members
    key = entity_preparation.key_position
    beside = sorted(members[position].name for position, _ in payload.stated if position != key)
    if beside:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{target.identity.name}: a {described} {mutation!r} names its object by its "
            f"primary key alone, and this row also states {beside}",
        )


def _stated_key(entity_preparation: EntityPreparation, payload: PartialPayload) -> object:
    """The key ``payload`` states, or the preparation's ``absent``."""
    key = entity_preparation.key_position
    return next(
        (raw for position, raw in payload.stated if position == key),
        entity_preparation.selection.absent,
    )


def _split_key(
    entity_preparation: EntityPreparation, values: Iterable[object]
) -> tuple[object, Iterable[object]]:
    """The key complete ``values`` state, beside every value they state, a
    one-shot input read only as far as its key."""
    position = entity_preparation.key_position
    if isinstance(values, tuple):
        return values[position], values
    remaining = iter(values)
    prefix = tuple(islice(remaining, position + 1))
    return prefix[position], chain(prefix, remaining)


def _admitted_key(
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    representation: WriteRepresentation,
    key: object,
    restated_key: object,
) -> tuple[int, object] | None:
    """The key cell that addresses the object, the first value a payload has
    judged, beside its position; ``None`` where the payload leaves the key
    unstated or null for its row to judge.

    A key its caller restated beside it is converted next and must name the
    same object, before any other value is judged.
    """
    if key is entity_preparation.selection.absent or key is None:
        return None
    position = entity_preparation.key_position
    cell = _key_cell(entity_preparation, target, representation, key)
    if not isinstance(restated_key, Unstated) and (
        _key_cell(entity_preparation, target, representation, restated_key) != cell
    ):
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{target.identity.canonical}.{entity_preparation.key_name}: the document names "
            f"{restated_key!r}, and the source this write addresses is another object — a key "
            "member addresses the write and never changes it",
        )
    return position, cell


def _key_cell(
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    representation: WriteRepresentation,
    raw: object,
) -> object:
    """``raw`` converted as the key, refused as a stated row's key is."""
    try:
        return entity_preparation.plan.scalar_cell(
            representation.lane, entity_preparation.key_position, raw
        )
    except AuthoringRefusal as refusal:
        error = _row_refusal(target, entity_preparation.selection.members.shape, refusal)
        raise error from error.__cause__


def _opening_row(
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    representation: WriteRepresentation,
    values: Iterable[object],
) -> ManagedRow:
    """The row an opening states, ``values`` judged in member order.

    A framework-owned member is read as unstated whatever ``values`` holds
    there: the framework supplies it when the row settles. A key the Entity
    allocates may be left unstated, for the insert to allocate, but is never
    stated as null.
    """
    allocation = entity_preparation.key_allocation
    try:
        prepared = entity_preparation.plan.complete_row(
            values,
            lane=representation.lane,
            required=entity_preparation.insert_required,
            omitted=entity_preparation.framework_owned,
            nonnull=0 if allocation is None else 1 << allocation.position,
        )
    except AuthoringRefusal as refusal:
        error = _row_refusal(target, entity_preparation.selection.members.shape, refusal)
        raise error from error.__cause__
    return managed_row(entity_preparation.selection, prepared.cells, prepared.presence)


def _stated_row(
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    representation: WriteRepresentation,
    stated: tuple[StatedMember, ...],
    admitted: tuple[int, object] | None,
) -> ManagedRow:
    """The row stating exactly the members ``stated`` positions, judged as
    content in the order it states them: a destructive write's identity, or
    the members an edit chain already judged as assignments."""
    try:
        prepared = entity_preparation.plan.partial_row(
            stated, lane=representation.lane, admitted=admitted
        )
    except AuthoringRefusal as refusal:
        error = _row_refusal(target, entity_preparation.selection.members.shape, refusal)
        raise error from error.__cause__
    return managed_row(entity_preparation.selection, prepared.cells, prepared.presence)


def _amendment_row(
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    representation: WriteRepresentation,
    stated: tuple[StatedMember, ...],
    admitted: tuple[int, object] | None,
) -> ManagedRow:
    """The row assigning one existing object the members ``stated``
    positions, each beside the key judged as an assignment in that order."""
    try:
        prepared = entity_preparation.plan.partial_row(
            stated,
            lane=representation.lane,
            check=entity_preparation.assignment_rules,
            admitted=admitted,
        )
    except UsageError as error:
        raise _restated_assignment_refusal(target, error) from error
    except AuthoringRefusal as refusal:
        refused = _assignment_refusal(entity_preparation, target, refusal)
        raise refused from refused.__cause__
    return managed_row(entity_preparation.selection, prepared.cells, prepared.presence)


def _replacement_row(
    entity_preparation: EntityPreparation,
    target: CompiledEntity,
    representation: WriteRepresentation,
    values: Iterable[object],
    admitted: tuple[int, object] | None,
) -> ManagedRow:
    """The row stating one existing object's complete writable state,
    ``values`` judged in member order as assignments beside the key that
    addresses it.

    A replacement states that state whatever authorized it: an omitted
    required member is refused where it falls, an omitted nullable one is
    written empty, and an omitted ``many`` the empty collection, so no value
    is ever carried forward from the state it replaces. That state excludes
    framework-owned and read-only members, which are never completed, and a
    carried payload's own are read as unstated.
    """
    excluded = entity_preparation.framework_owned | entity_preparation.read_only
    try:
        prepared = entity_preparation.plan.complete_row(
            values,
            lane=representation.lane,
            required=entity_preparation.replace_required,
            omitted=excluded if representation.complete_payload_cells == "carried" else 0,
            nulled=entity_preparation.replace_nulled,
            excluded=excluded,
            check=entity_preparation.assignment_rules,
            admitted=admitted,
        )
    except UsageError as error:
        raise _restated_assignment_refusal(target, error) from error
    except AuthoringRefusal as refusal:
        refused = _replacement_refusal(entity_preparation, target, refusal)
        raise refused from refused.__cause__
    return managed_row(entity_preparation.selection, prepared.cells, prepared.presence)


def _assigns(entity_preparation: EntityPreparation, row: ManagedRow) -> bool:
    """Whether ``row`` states a member beside the key."""
    return row.presence & ~(1 << entity_preparation.key_position) != 0


def _restated_assignment_refusal(entity: CompiledEntity, error: UsageError) -> UsageError:
    """The assignment judgement's ``error`` restated as the refusal of a write
    to ``entity``: a value its member does not admit keeps the judgement's own
    code, and a designation that admits no assignment is the binding's
    ``write-instruction-invalid``."""
    message = f"{entity.identity.canonical}.{error.args[1]}"
    if error.code == WRITE_ASSIGNMENT_VALUE_TYPE_MISMATCH:
        return InvalidValueError(WRITE_ASSIGNMENT_VALUE_TYPE_MISMATCH, message)
    return UsageError(WRITE_INSTRUCTION_INVALID, message)


def _row_refusal(
    entity: CompiledEntity, shape: MemberShape, refusal: AuthoringRefusal
) -> Exception:
    """``refusal`` worded as the refusal of a stated row's member, caused by
    the conversion failure where one raised it."""
    member = shape.members[refusal.position]
    cause = refusal.cause
    if is_decoding_refusal(cause):
        path = joined_path(f"{entity.identity.canonical}.{member.name}", refusal.violation.path)
        return located_refusal(cause, path)
    error = _member_refusal(entity.identity.name, member, refusal.violation)
    error.__cause__ = cause
    return error


def _assignment_refusal(
    entry: EntityPreparation, entity: CompiledEntity, refusal: AuthoringRefusal
) -> Exception:
    """``refusal`` worded as the refusal of an assignment where it refuses a
    member beside the key, caused by the assignment rule's verdict, and as a
    stated row's at the key."""
    position = refusal.position
    shape = entry.selection.members.shape
    if position == entry.key_position or is_decoding_refusal(refusal.cause):
        return _row_refusal(entity, shape, refusal)
    member = entry.selection.members.bindings[position]
    violation = refusal.violation
    definition = shape.members[position]
    scalar = (
        isinstance(definition, ScalarDefinition) and definition.multiplicity is Multiplicity.ONE
    )
    value = violation.value if scalar else _STATED
    try:
        judge_assignment(member, value, known_violation=violation, known_value_valid=False)
    except UsageError as error:
        refused = _restated_assignment_refusal(entity, error)
        refused.__cause__ = error
        return refused
    raise AssertionError(f"{violation} is no assignment's refusal")  # pragma: no cover


def _replacement_refusal(
    entry: EntityPreparation, entity: CompiledEntity, refusal: AuthoringRefusal
) -> Exception:
    """``refusal`` worded as a replacement's: an unstated required member as
    one the complete state omits, any other as :func:`_assignment_refusal`
    words it."""
    violation = refusal.violation
    if not violation.path and violation.reason in ("attribute-missing", "value-object-missing"):
        name = entry.selection.members.shape.members[refusal.position].name
        rule = (
            WRITE_REQUIRED_ATTRIBUTE_MISSING
            if violation.reason == "attribute-missing"
            else WRITE_REQUIRED_VALUE_OBJECT_MISSING
        )
        return InvalidValueError(
            rule,
            f"{entity.identity.name}.{name}: a replacement states every required member, and "
            "this one is absent",
        )
    return _assignment_refusal(entry, entity, refusal)


_STATED: Final = object()
"""The value a structured member's assignment judgment is handed where only
its structural finding is weighed."""


def _member_refusal(
    owner: str, member: MemberDefinition, violation: AuthoringViolation
) -> InvalidValueError:
    """The refusal of a stated row's top-level ``member`` for ``violation``."""
    base = f"{owner}.{member.name}"
    scalar = isinstance(member, ScalarDefinition)
    many = member.multiplicity is Multiplicity.MANY
    if not violation.path and violation.reason in ("attribute-missing", "value-object-missing"):
        rule = WRITE_REQUIRED_ATTRIBUTE_MISSING if scalar else WRITE_REQUIRED_VALUE_OBJECT_MISSING
        kind = "attribute" if scalar else "value object"
        if many:
            return InvalidValueError(rule, f"{base}: a `many` {kind} is never null")
        return InvalidValueError(rule, f"{base}: required {kind} is absent (or null)")
    path = joined_path(base, violation.path)
    if violation.reason == "not-a-list":
        expected = "a list of scalar values" if scalar else "a list of documents"
        kind = "attribute" if scalar else "value object"
        return InvalidValueError(
            WRITE_VALUE_TYPE_MISMATCH,
            f"{path}: a `many` {kind} must bind {expected}, got {type(violation.value).__name__}",
        )
    if violation.reason == "not-a-document":
        return InvalidValueError(
            WRITE_VALUE_TYPE_MISMATCH,
            f"{path}: expected a document (mapping), got {type(violation.value).__name__}",
        )
    if violation.reason == "attribute-missing":
        return InvalidValueError(
            WRITE_REQUIRED_ATTRIBUTE_MISSING, f"{path}: required attribute is absent (or null)"
        )
    if violation.reason == "value-object-missing":
        return InvalidValueError(
            WRITE_REQUIRED_VALUE_OBJECT_MISSING,
            f"{path}: required value object is absent (or null)",
        )
    return InvalidValueError(
        WRITE_VALUE_TYPE_MISMATCH,
        f"{path}: value {violation.value!r} does not match the declared type "
        f"{violation.declared_type!r}",
    )


def joined_path(base: str, path: str) -> str:
    """``base`` plus a violation's own relative ``path``: a nested member
    dot-joins, and a ``many`` element index attaches bracket-first with no
    dot (``"Supplier.address.phones[0].number"``)."""
    if not path:
        return base
    if path.startswith("["):
        return f"{base}{path}"
    return f"{base}.{path}"


def _judge_write_persistence(
    entity: CompiledEntity, position: inheritance.InheritanceEntityView
) -> None:
    """Refuse any write to an Entity whose family's effective Persistence Mode
    is ReadOnly (`m-unit-work`)."""
    if position.persistence is PersistenceMode.READ_ONLY:
        raise UsageError(
            READ_ONLY_WRITE_TARGET,
            f"{entity.identity.canonical}: its family's Persistence Mode is ReadOnly, which "
            "accepts no persistence write of any kind",
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
    entity: CompiledEntity,
    shape: temporal_read.TemporalShape | None,
    mutation: str,
    valid_from: object,
    until: object,
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
        refusal = _temporal_delete_refusal(name, mutation, surface=surface)
        if refusal is not None:
            raise UsageError(WRITE_INSTRUCTION_INVALID, refusal)
    window = _judge_window(_family_root(model, entity), shape, mutation, valid_from, until)
    if not temporal:
        refusal = _non_temporal_milestone_refusal(name, mutation, surface=surface)
        if refusal is not None:
            raise UsageError(WRITE_INSTRUCTION_INVALID, refusal)
    return window


def _judge_window(
    root: EntityIdentity,
    shape: temporal_read.TemporalShape | None,
    mutation: str,
    valid_from: object,
    until: object,
) -> TimeInterval | None:
    """One write's Valid-Time window, judged once per call: ``[valid_from,
    until)``, through :data:`~parallax.core.internal.base.INFINITY` where ``until`` is
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
    input (``write-instruction-invalid``); a bound that is no instant keeps
    `m-core`'s ``instant-invalid``. Refusals name the family by its root.
    """
    if mutation in BOUNDED_MUTATIONS:
        if not isinstance(shape, temporal_read.Bitemporal):
            raise UsageError(
                WRITE_INSTRUCTION_INVALID,
                f"{root.name}: {_profile(shape)} {mutation!r} takes no until "
                f"({root.name!r} declares no Valid-Time dimension to bound)",
            )
        missing = "valid_from" if valid_from is None else "until" if until is None else None
        if missing is not None:
            raise UsageError(
                WRITE_INSTRUCTION_INVALID,
                f"{root.name}: a bounded {mutation!r} states its window as a pair, "
                f"and {missing} is absent — an unbounded write omits until rather than "
                "stating none",
            )
    elif until is not None:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{root.name}: {mutation!r} is unbounded and takes no until "
            "(its window runs to infinity)",
        )
    if isinstance(shape, temporal_read.Bitemporal):
        if valid_from is None:
            raise UsageError(
                WRITE_INSTRUCTION_INVALID,
                f"{root.name}: a bitemporal {mutation!r} requires valid_from "
                "(the mutation's own Valid-Time instant)",
            )
        managed_from = normalize_instant(_stated_instant(root, mutation, "valid_from", valid_from))
    elif valid_from is not None:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{root.name}: {_profile(shape)} {mutation!r} takes no valid_from "
            f"({root.name!r} declares no Valid-Time dimension to bound)",
        )
    else:
        # A target without Valid Time is refused any stated `until` above.
        return None
    if until is None:
        return TimeInterval(managed_from, INFINITY)
    managed_until = normalize_instant(_stated_instant(root, mutation, "until", until))
    if managed_until <= managed_from:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"{root.name}: {mutation!r} requires valid_from < until "
            f"— got valid_from={valid_from!r}, until={until!r}",
        )
    return TimeInterval(managed_from, managed_until)


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
    ``instant-invalid`` — the code a naive datetime earns one step later —
    rather than leaving an ``AttributeError`` where a verdict belongs.
    """
    if not isinstance(value, dt.datetime):
        raise UsageError(
            INSTANT_INVALID,
            f"{root.name}: {mutation!r} takes an aware datetime for {bound}, "
            f"and {type(value).__name__} is no `timestamp`",
        )
    return value


def _inheritance_entity_view(
    model: AcceptedMetamodel, entity: CompiledEntity
) -> inheritance.InheritanceEntityView:
    position = inheritance.inheritance_facet_of(model).entity(entity.identity)
    if position is None:
        raise RuntimeError(f"{entity.identity.canonical}: no Inheritance Facet view")
    return position


def _member_selection(
    model: AcceptedMetamodel, entity: CompiledEntity
) -> inheritance.EntityMemberSelection:
    """``entity``'s family-effective members: the whole inheritance FAMILY's
    applicable members for a participant, its own declarations otherwise."""
    return _inheritance_entity_view(model, entity).member_selection


def _family_root(model: AcceptedMetamodel, entity: CompiledEntity) -> EntityIdentity:
    return _inheritance_entity_view(model, entity).root


def _decoded_wire(neutral_type: NeutralType, value: object, path: str) -> object:
    try:
        return freeze_retained_value(decode_wire(neutral_type, cast("WireValue", value)))
    except UsageError as error:
        raise located_refusal(error, path) from error


def resolve_target(model: AcceptedMetamodel, name: str) -> CompiledEntity:
    """The accepted Metadata a write's bare-or-canonical target names, by
    :func:`~parallax.core.internal.metamodel.entity_by_name`'s ambiguity-rejecting rule.

    That rule answers a miss for two different mistakes, and this is the boundary
    every externally produced instruction crosses, so the two are classified
    apart: a bare spelling two namespaces share is the normative
    `reference-ambiguous-entity-name` refusal (`m-predicate` "Entity spellings
    in a reference position"), naming the canonical spellings that would
    resolve; anything else names no declared Entity at all and is refused as
    ``write-instruction-invalid``. Classifying here is also what keeps an
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
        raise UsageError(
            REFERENCE_AMBIGUOUS_ENTITY_NAME,
            f"the bare Entity spelling {name!r} is shared by {list(shared)}, so it names no "
            "single Entity in this model and the write resolves nowhere (m-predicate reference "
            "resolution); spell the one this write means",
        )
    raise UsageError(
        WRITE_INSTRUCTION_INVALID, f"the connected model declares no entity {name!r} for this write"
    )
