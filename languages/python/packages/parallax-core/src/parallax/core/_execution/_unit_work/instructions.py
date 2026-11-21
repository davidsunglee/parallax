from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, cast

from parallax.core.internal import predicate as predicate_algebra
from parallax.core.internal.base import (
    TIMESTAMP,
    NeutralType,
    UsageError,
    coerce_neutral_input,
)
from parallax.core.internal.batch_write import SET_BASED_WRITE_TARGET_UNSUPPORTED
from parallax.core.internal.planned_step.columns import freeze_retained_value
from parallax.core.internal.predicate import PredicateInterpretation, PredicateNode
from parallax.core.internal.wire import WireValue, decode_wire, encode_wire, located_refusal

__all__ = [
    "AMEND_MUTATIONS",
    "ASSIGNMENT_MUTATIONS",
    "ASSIGNMENT_REFERENCE",
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
    "KeyedMutation",
    "KeyedWriteInstruction",
    "PredicateMutation",
    "PredicateSelection",
    "PredicateWriteInstruction",
    "TargetMutation",
    "TargetWriteInstruction",
    "WriteAssignment",
    "WriteInstruction",
    "WriteRejectionCode",
    "deserialize",
    "refuse_observation_keys",
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

WRITE_INSTRUCTION_INVALID: Final = "write-instruction-invalid"

READ_ONLY_WRITE_TARGET: Final = "read-only-write-target"
"""Any write whose target family's effective Persistence Mode is ReadOnly
(`m-unit-work`)."""

FRAMEWORK_OWNED_MEMBER_ASSIGNED: Final = "framework-owned-member-assigned"
WRITE_REQUIRED_ATTRIBUTE_MISSING: Final = "write-required-attribute-missing"
WRITE_REQUIRED_VALUE_OBJECT_MISSING: Final = "write-required-value-object-missing"
WRITE_VALUE_TYPE_MISMATCH: Final = "write-value-type-mismatch"

# The framework-owned transaction observation is NOT durable instruction state, so
# these control keys are forbidden on a write row. All THREE that
# `write-instruction.schema.json`'s own `writeRow` forbids: the observed version,
# and BOTH halves of the observed milestone's own edge coordinate. Omitting either
# half would let a row carry a coordinate the instruction cannot mean — the
# milestone a temporal write observes is resolved at flush, never authored.
_FORBIDDEN_ROW_KEYS: Final[frozenset[str]] = frozenset(
    {"observedVersion", "observedTxStart", "observedValidStart"}
)


def refuse_observation_keys(names: Iterable[str]) -> None:
    """Refuse a write row naming a transaction observation control key."""
    forbidden = sorted(_FORBIDDEN_ROW_KEYS.intersection(names))
    if forbidden:
        raise UsageError(
            WRITE_INSTRUCTION_INVALID,
            f"write row carries forbidden observation control key(s) {forbidden} "
            "(the transaction observation is attached at flush, never on the instruction)",
        )


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


ASSIGNMENT_REFERENCE: Final = re.compile(
    r"^([a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*\.)?[A-Z][A-Za-z0-9]*\.[a-z][A-Za-z0-9_]*$"
)
"""The reference pattern a write assignment's ``attr`` must match, mirroring
identity.schema.json's ``attributeRef`` by way of write-instruction.schema.json
``$defs/writeAssignment``: an Entity spelling — canonical or bare — followed by
the member it assigns."""


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
        if not isinstance(attr, str) or ASSIGNMENT_REFERENCE.match(attr) is None:
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


def _decoded_wire(neutral_type: NeutralType, value: object, path: str) -> object:
    try:
        return freeze_retained_value(decode_wire(neutral_type, cast("WireValue", value)))
    except UsageError as error:
        raise located_refusal(error, path) from error
