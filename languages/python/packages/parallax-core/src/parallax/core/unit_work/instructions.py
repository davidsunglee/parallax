from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, cast, overload

from parallax.core import inheritance, temporal_read
from parallax.core import predicate as predicate_algebra
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
    SourceAccess,
    prepare_authoring,
    prepare_member_authoring,
)
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Leaf,
    PrimaryKey,
    ValueObjectMetadata,
    VoDocumentViolation,
    WriteAssignmentError,
    entity_by_name,
    judge_assignment,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.metamodel._states import ambiguous_entity_spellings
from parallax.core.predicate import PredicateNode
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work.write_validate import WriteRejectedError, validate_write
from parallax.core.wire import WireDecodingError, WireValue, decode_wire, encode_wire
from parallax.core.write_plan.columns import freeze_retained_value
from parallax.core.write_plan.planned_rows import PreparedAssignment
from parallax.core.write_plan.steps import UNVERSIONED, Unversioned, ValidatedMutationSelection

__all__ = [
    "BOUNDED_MUTATIONS",
    "DESTRUCTIVE_MUTATIONS",
    "INSERT_MUTATIONS",
    "UPDATE_MUTATIONS",
    "ExpectedTxStart",
    "ExpectedVersion",
    "InstructionRejectedError",
    "KeyedMutation",
    "KeyedWrite",
    "PredicateMutation",
    "PredicateSelection",
    "PredicateWrite",
    "PreparedKeyedWrite",
    "PreparedPredicateWrite",
    "PreparedTargetWrite",
    "PreparedWrite",
    "TargetExpectation",
    "TargetMutation",
    "TargetWrite",
    "WriteAssignment",
    "WriteInstruction",
    "WriteInstructionError",
    "coerce_typed_row",
    "derive_keyed_write",
    "derive_opening",
    "deserialize",
    "prepare_typed_write",
    "prepare_wire_write",
    "resolve_target",
    "serialize",
    "target_instruction",
]

# The keyed write mutation surface: the MVP non-temporal / audit-only verbs plus
# the full-bitemporal bounded rectangle split (write-instruction.schema.json).
KeyedMutation = Literal[
    "insert", "update", "delete", "terminate", "insertUntil", "updateUntil", "terminateUntil"
]
# The predicate-selected (set-based) mutation surface: there is no `insert` — a
# predicate cannot select rows that do not yet exist.
PredicateMutation = Literal["update", "delete", "terminate", "updateUntil", "terminateUntil"]
# The caller-addressed (target) mutation surface: a sparse patch or a complete
# replacement of one existing object, each with its bounded form.
TargetMutation = Literal["update", "updateUntil", "replace", "replaceUntil"]

# Which of the keyed and predicate verb surfaces a mutation arrived through. Carried only
# so a refusal can name methods the caller can act on: one mutation token is
# spelled by two methods, and answering a `terminate_where` call with "use
# `delete`" names the addressed verb, which selects nothing.
type _WriteSurface = Literal["keyed", "predicate"]

INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})
"""The keyed mutations that OPEN a row rather than write against an existing
one, which is what makes them the mutations that carry no Write Observation
(`m-unit-work` "Absence is structural"). Shared so the buffered carrier's own
refusal and the planner's coalescing both answer "is this an insert?" from one
definition."""

UPDATE_MUTATIONS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})
"""The keyed mutations that write an EXISTING row from a value's own effective
changes. Shared for :data:`INSERT_MUTATIONS`' reason: the frontend refusal that
asks which verb accepts a value and the planner's insert-then-update coalescing
must answer "is this an update?" from one definition, or a verb one folds is a
verb the other refuses."""

DESTRUCTIVE_MUTATIONS: Final[frozenset[str]] = frozenset({"delete", "terminate", "terminateUntil"})
"""The keyed mutations that end a row's existence or its current milestone, and
so CANCEL a buffered insert of the same object still pending in the same flush
(`m-unit-work` "Insert-then-delete cancels"). Shared for
:data:`INSERT_MUTATIONS`' reason: the planner's cancellation rule and any
frontend gate that has to agree with it must answer "is this destructive?" from
one definition."""

_KEYED_MUTATIONS: Final[frozenset[str]] = INSERT_MUTATIONS | frozenset(
    {"update", "delete", "terminate", "updateUntil", "terminateUntil"}
)
_PREDICATE_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"update", "delete", "terminate", "updateUntil", "terminateUntil"}
)
_TARGET_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"update", "updateUntil", "replace", "replaceUntil"}
)
_REPLACEMENTS: Final[frozenset[str]] = frozenset({"replace", "replaceUntil"})

BOUNDED_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"insertUntil", "updateUntil", "terminateUntil", "replaceUntil"}
)
"""The mutations whose window is a PAIR of Valid-Time bounds, keyed,
predicate-selected, and target alike; every other form carries no `until` — its
window runs `[validFrom, infinity)`, or the target is non-temporal."""
# The assignment-bearing predicate verbs; the others name nothing to assign.
_ASSIGNMENT_MUTATIONS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})

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
class KeyedWrite:
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
    ``m-predicate`` selection (a canonical Predicate node).

    This is the instruction-level carrier an authored :class:`PredicateWrite`
    holds, distinct from the prepared product buffering retains and from the
    finalized :class:`~parallax.core.unit_work.
    planned.WriteTarget` a Planned Write settles into.
    """

    entity: str
    predicate: PredicateNode


@dataclass(frozen=True, slots=True)
class PredicateWrite:
    """A predicate-selected (set-based) write: a ``mutation`` on every row of
    ``target`` matching its predicate, with ``assignments`` on the update forms."""

    mutation: PredicateMutation
    target: PredicateSelection
    assignments: tuple[WriteAssignment, ...] = ()
    valid_from: dt.datetime | None = None
    until: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class TargetWrite:
    """An authored caller-addressed write of one existing ``entity`` object.

    ``row`` names the object by its primary key beside the members the write
    states: the assignments of an ``update`` patch, or the complete writable
    state of a ``replace``. ``if_version`` and ``if_tx_start`` are the caller's
    revision arguments exactly as stated, judged by preparation against the
    target's own revision kind; neither is ever read off the row or off any
    read's evidence.
    """

    mutation: TargetMutation
    entity: str
    row: Mapping[str, object]
    if_version: int | None = None
    if_tx_start: dt.datetime | None = None
    valid_from: dt.datetime | None = None
    until: dt.datetime | None = None

    def __post_init__(self) -> None:
        forbidden = sorted(set(self.row) & _FORBIDDEN_ROW_KEYS)
        if forbidden:
            raise WriteInstructionError(
                f"target write: row carries forbidden observation control key(s) {forbidden} "
                "(a target write's condition is its own revision argument, never a row member)"
            )
        if not isinstance(self.row, MappingProxyType):
            object.__setattr__(self, "row", MappingProxyType(dict(self.row)))


WriteInstruction = KeyedWrite | PredicateWrite | TargetWrite


@dataclass(frozen=True, slots=True, init=False)
class PreparedKeyedWrite:
    """A keyed mutation over an exact resolved target and owned managed rows.

    ``valid_time_window`` is the judged window, ``None`` for a target without
    Valid Time. Only this module's producers construct one, so holding one
    means the write was judged admissible against its target.
    """

    mutation: KeyedMutation
    target: EntityMetadata
    rows: tuple[Mapping[str, object], ...]
    valid_time_window: TimeInterval | None


@dataclass(frozen=True, slots=True, init=False)
class PreparedPredicateWrite:
    """A predicate mutation over a resolved selection and managed assignments.

    ``valid_time_window`` is the judged window, ``None`` for a target without
    Valid Time. Only this module's producers construct one, so holding one
    means the write was judged admissible against its target.
    """

    mutation: PredicateMutation
    selection: ValidatedMutationSelection
    managed_assignments: tuple[PreparedAssignment, ...]
    valid_time_window: TimeInterval | None


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


type TargetExpectation = ExpectedVersion | ExpectedTxStart | Unversioned
"""What a target write's caller requires of the state it starts from. An
unversioned target has no revision to state, which is its own answer rather
than a missing one."""


@dataclass(frozen=True, slots=True, init=False)
class PreparedTargetWrite:
    """A caller-addressed write over an exact resolved target, its owned managed
    row, its judged Valid-Time window — ``None`` for a target without Valid
    Time — and its validated starting expectation.

    ``replaces`` distinguishes a complete replacement, whose row states every
    writable member, from a sparse patch, whose row states only the members it
    assigns; ``assigns`` is whether the row states any member beside the key.
    Only this module's producers construct one, so holding one means the write
    was judged admissible against its target.
    """

    replaces: bool
    assigns: bool
    target: EntityMetadata
    row: Mapping[str, object]
    valid_time_window: TimeInterval | None
    expectation: TargetExpectation


PreparedWrite = PreparedKeyedWrite | PreparedPredicateWrite
"""A prepared write a unit of work buffers as it is."""


def _prepared_keyed_write(
    mutation: KeyedMutation,
    target: EntityMetadata,
    rows: tuple[Mapping[str, object], ...],
    valid_time_window: TimeInterval | None,
) -> PreparedKeyedWrite:
    prepared = object.__new__(PreparedKeyedWrite)
    object.__setattr__(prepared, "mutation", mutation)
    object.__setattr__(prepared, "target", target)
    object.__setattr__(prepared, "rows", rows)
    object.__setattr__(prepared, "valid_time_window", valid_time_window)
    return prepared


def _prepared_predicate_write(
    mutation: PredicateMutation,
    selection: ValidatedMutationSelection,
    managed_assignments: tuple[PreparedAssignment, ...],
    valid_time_window: TimeInterval | None,
) -> PreparedPredicateWrite:
    prepared = object.__new__(PreparedPredicateWrite)
    object.__setattr__(prepared, "mutation", mutation)
    object.__setattr__(prepared, "selection", selection)
    object.__setattr__(prepared, "managed_assignments", managed_assignments)
    object.__setattr__(prepared, "valid_time_window", valid_time_window)
    return prepared


def _prepared_target_write(
    replaces: bool,
    assigns: bool,
    target: EntityMetadata,
    row: Mapping[str, object],
    valid_time_window: TimeInterval | None,
    expectation: TargetExpectation,
) -> PreparedTargetWrite:
    prepared = object.__new__(PreparedTargetWrite)
    object.__setattr__(prepared, "replaces", replaces)
    object.__setattr__(prepared, "assigns", assigns)
    object.__setattr__(prepared, "target", target)
    object.__setattr__(prepared, "row", row)
    object.__setattr__(prepared, "valid_time_window", valid_time_window)
    object.__setattr__(prepared, "expectation", expectation)
    return prepared


def target_instruction(prepared: PreparedTargetWrite) -> PreparedKeyedWrite:
    """The keyed update a prepared target write executes as: its row, written
    against the object its key names, over its window.

    A replacement's row already states every writable member, so the update
    is the replacement; nothing is judged again.
    """
    window = prepared.valid_time_window
    return _prepared_keyed_write(
        "update" if window is None or window.end is INFINITY else "updateUntil",
        prepared.target,
        (prepared.row,),
        window,
    )


@dataclass(frozen=True, slots=True)
class _TransformedRow:
    row: Mapping[str, object]
    failures: Mapping[int, VoDocumentViolation]


def derive_keyed_write(
    prepared: PreparedKeyedWrite, rows: tuple[Mapping[str, object], ...]
) -> PreparedKeyedWrite:
    """Derive a keyed prepared product while retaining owned values by identity."""
    sealed = tuple(cast("Mapping[str, object]", retain_document_value(row)) for row in rows)
    return _prepared_keyed_write(
        prepared.mutation, prepared.target, sealed, prepared.valid_time_window
    )


def derive_opening(
    prepared: PreparedKeyedWrite,
    row: Mapping[str, object],
    *,
    valid_time_window: TimeInterval,
) -> PreparedKeyedWrite:
    """One piece of an admitted Bitemporal opening: ``row`` opened over
    ``valid_time_window``.

    The piece states the same target and an already-judged window inside the
    opening's own, so nothing is judged again.
    """
    sealed = (cast("Mapping[str, object]", retain_document_value(row)),)
    return _prepared_keyed_write(
        "insert" if valid_time_window.end is INFINITY else "insertUntil",
        prepared.target,
        sealed,
        valid_time_window,
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
    ``target`` -> predicate, ``row`` -> caller-addressed), validates the closed
    shape, the mutation enum, the
    Valid-Time-bound pairing rules (a bounded ``*Until`` carries both bounds, every
    other form carries no ``until``), and — for a keyed write — that no row
    carries a forbidden observation control key or a smuggled Transaction-Time instant.

    Each bound is a finite canonical ``timestamp`` decoded by the Wire codec, whose
    refusals keep their ``neutral-literal-*`` classification; ``infinity`` is no
    authored bound, since an open upper end is spelled by omitting ``until``.
    """
    if not isinstance(doc, Mapping):
        raise WriteInstructionError(
            f"write instruction must be a mapping, got {type(doc).__name__}"
        )
    node = cast("Mapping[str, object]", doc)
    carriers = [key for key in ("rows", "target", "row") if key in node]
    if len(carriers) > 1:
        raise WriteInstructionError(
            f"write instruction is ambiguous: it carries {carriers}, and `rows` (keyed), "
            "`target` (predicate), and `row` (caller-addressed) each name a different shape"
        )
    if carriers == ["rows"]:
        return _keyed(node)
    if carriers == ["target"]:
        return _predicate(node)
    if carriers == ["row"]:
        return _target_write(node)
    raise WriteInstructionError(
        "write instruction must carry `rows` (keyed), `target` (predicate), or `row` "
        "(caller-addressed)"
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


def _keyed(node: Mapping[str, object]) -> KeyedWrite:
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
    return KeyedWrite(
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
    if not isinstance(raw, list) or not raw:
        raise WriteInstructionError("predicate write: `assignments` must be a non-empty list")
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


def _predicate(node: Mapping[str, object]) -> PredicateWrite:
    _reject_extra(
        node,
        frozenset({"mutation", "target", "assignments", "validFrom", "until"}),
        "predicate write",
    )
    _require(node, ("mutation", "target"), "predicate write")
    mutation = _mutation(node, _PREDICATE_MUTATIONS, "predicate write")
    target = _target(node)
    has_assignments = "assignments" in node
    if mutation in _ASSIGNMENT_MUTATIONS:
        if not has_assignments:
            raise WriteInstructionError(f"predicate write: `{mutation}` MUST carry `assignments`")
        assignments = _assignments(node)
    else:
        if has_assignments:
            raise WriteInstructionError(
                f"predicate write: `{mutation}` names nothing to assign "
                "and MUST NOT carry `assignments`"
            )
        assignments = ()
    valid_from = _bound(node, "validFrom", "predicate write")
    until = _bound(node, "until", "predicate write")
    _check_valid_time_bounds(mutation, valid_from, until, "predicate write")
    return PredicateWrite(
        mutation=cast("PredicateMutation", mutation),
        target=target,
        assignments=assignments,
        valid_from=valid_from,
        until=until,
    )


def _target_write(node: Mapping[str, object]) -> TargetWrite:
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
    return TargetWrite(
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
    if isinstance(instruction, TargetWrite):
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
    if isinstance(instruction, KeyedWrite):
        keyed_body: dict[str, object] = {
            "mutation": instruction.mutation,
            "entity": instruction.entity,
            "rows": [dict(row) for row in instruction.rows],
        }
        _emit_bounds(keyed_body, instruction.valid_from, instruction.until)
        return keyed_body
    predicate_body: dict[str, object] = {
        "mutation": instruction.mutation,
        "target": {
            "entity": instruction.target.entity,
            "predicate": predicate_algebra.serialize(instruction.target.predicate),
        },
    }
    if instruction.assignments:
        predicate_body["assignments"] = [
            {"attr": a.attr, "value": a.value} for a in instruction.assignments
        ]
    _emit_bounds(predicate_body, instruction.valid_from, instruction.until)
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
    return mutation if surface == "keyed" else f"{mutation}_where"


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


def _temporal_singleton_refusal(
    entity_name: str, instruction: KeyedWrite | PredicateWrite
) -> str | None:
    """Why a TEMPORAL target refuses ``instruction``'s ROW COUNT, or ``None``
    when this rule has nothing to say about it.

    Each row of a milestone chain closes its own current milestone, consumes its
    own Temporal Observation, and opens its own successors, and a temporal
    entity never collapses into a set-based statement (`m-batch-write`), so
    several rows under one keyed instruction denote several independent chains
    rather than one wider write (`m-unit-work` "A temporal keyed instruction
    carries exactly one row").
    """
    if not isinstance(instruction, KeyedWrite) or len(instruction.rows) == 1:
        return None
    return (
        f"{entity_name!r}: a keyed {instruction.mutation!r} on a temporal target carries "
        f"{len(instruction.rows)} rows — a temporal keyed instruction carries exactly one "
        "(m-unit-work), since each row closes its own milestone, consumes its own "
        "observation, and chains its own successors; author one instruction per row"
    )


@overload
def prepare_typed_write(
    instruction: TargetWrite, model: AcceptedMetamodel
) -> PreparedTargetWrite: ...
@overload
def prepare_typed_write(
    instruction: KeyedWrite, model: AcceptedMetamodel
) -> PreparedKeyedWrite: ...
@overload
def prepare_typed_write(
    instruction: PredicateWrite, model: AcceptedMetamodel
) -> PreparedPredicateWrite: ...
@overload
def prepare_typed_write(
    instruction: WriteInstruction, model: AcceptedMetamodel
) -> PreparedWrite | PreparedTargetWrite: ...
def prepare_typed_write(
    instruction: WriteInstruction, model: AcceptedMetamodel
) -> PreparedWrite | PreparedTargetWrite:
    """Coerce developer values once, then judge and freeze the write."""
    return _prepare_write(
        instruction,
        model,
        converter=_coerce_typed_leaf,
        source_access=BORROWED_SOURCE_ACCESS,
        authored_members=None,
    )


@overload
def prepare_wire_write(
    instruction: TargetWrite,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
) -> PreparedTargetWrite: ...
@overload
def prepare_wire_write(
    instruction: KeyedWrite,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
) -> PreparedKeyedWrite: ...
@overload
def prepare_wire_write(
    instruction: PredicateWrite,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
) -> PreparedPredicateWrite: ...
@overload
def prepare_wire_write(
    instruction: WriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
) -> PreparedWrite | PreparedTargetWrite: ...
def prepare_wire_write(
    instruction: WriteInstruction,
    model: AcceptedMetamodel,
    *,
    authored_members: Set[str] | None = None,
) -> PreparedWrite | PreparedTargetWrite:
    """Decode one serialized instruction, then judge and freeze the write.

    ``authored_members`` names the row members a Wire caller explicitly wrote:
    an insert's payload keys, judged as insert authoring, or an update's change
    keys, judged as assignments. A neutral instruction omits it, and its row is
    judged as row content alone. A caller-addressed write judges every member
    its row states beside the key as an assignment either way.
    """
    return _prepare_write(
        instruction,
        model,
        converter=_decode_wire_leaf,
        source_access=MAPPING_SOURCE_ACCESS,
        authored_members=authored_members,
    )


def _prepare_write(
    instruction: WriteInstruction,
    model: AcceptedMetamodel,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
    authored_members: Set[str] | None,
) -> PreparedWrite | PreparedTargetWrite:
    """The sole admissibility judgment of a write: its target first, then its
    payload.

    The target stage resolves the Entity, then asks whether it admits the verb
    (both halves of temporal applicability), the window, and the row count.
    Only then is the payload measured — a keyed row's subtype shape, members,
    and values, or a predicate write's selecting predicate, family refusal, and
    assignments in authored order — so a call whose verb or window is wrong for
    its target hears that before any complaint about what it carries.
    """
    if isinstance(instruction, TargetWrite):
        return _prepare_target_write(
            instruction,
            model,
            converter=converter,
            source_access=source_access,
            authored_members=authored_members,
        )
    keyed = isinstance(instruction, KeyedWrite)
    entity = resolve_target(model, instruction.entity if keyed else instruction.target.entity)
    window = _judge_target(model, entity, instruction)
    selection = _member_selection(model, entity)
    if isinstance(instruction, KeyedWrite):
        return _prepare_keyed_payload(
            instruction,
            model,
            entity,
            selection,
            window,
            converter=converter,
            source_access=source_access,
            authored_members=authored_members,
        )
    return _prepare_predicate_payload(
        instruction,
        model,
        entity,
        selection,
        window,
        converter=converter,
        source_access=source_access,
    )


def _judge_target(
    model: AcceptedMetamodel, entity: EntityMetadata, instruction: KeyedWrite | PredicateWrite
) -> TimeInterval | None:
    """Judge the verb, window, and row count against ``entity``'s Temporal
    Shape, and answer the managed window, ``None`` for a target without Valid
    Time.

    A temporal ``delete`` is refused before the window: ``delete`` states no
    bound in any spelling, so answering it by naming the ``valid_from`` a
    Bitemporal target requires would ask for an argument the verb has no place
    for. A milestone verb aimed at a non-temporal target is refused after it:
    every such verb takes a bound, so a call stating one hears a true verdict on
    an argument it can drop, while a boundless ``terminate`` clears the window
    and is refused for its verb.
    """
    surface: _WriteSurface = "keyed" if isinstance(instruction, KeyedWrite) else "predicate"
    name = entity.identity.name
    shape = temporal_read.view(model).shape(entity.identity)
    temporal = isinstance(shape, temporal_read.TransactionTimeOnly | temporal_read.Bitemporal)
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
    if temporal:
        plural = _temporal_singleton_refusal(name, instruction)
        if plural is not None:
            raise InstructionRejectedError(TEMPORAL_KEYED_WRITE_MULTI_ROW, plural)
    else:
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
    instruction: TargetWrite,
    model: AcceptedMetamodel,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
    authored_members: Set[str] | None,
) -> PreparedTargetWrite:
    """Judge a caller-addressed write: its target and window, then its revision
    arguments, then its payload.

    The revision arguments are judged ahead of the payload because they decide
    what the write may be at all — a target whose revision kind the caller
    misstated, or whose required revision is missing, is refused before any
    member it names is weighed.
    """
    entity = resolve_target(model, instruction.entity)
    shape = temporal_read.view(model).shape(entity.identity)
    root = _family_root(model, entity)
    window = _judge_window(
        root, shape, instruction.mutation, instruction.valid_from, instruction.until
    )
    position = _family_position(model, entity)
    expectation = _judge_expectation(root, shape, position, instruction)
    row, assigns = _prepare_target_payload(
        instruction,
        model,
        entity,
        position,
        converter=converter,
        source_access=source_access,
        authored_members=authored_members,
    )
    return _prepared_target_write(
        instruction.mutation in _REPLACEMENTS, assigns, entity, row, window, expectation
    )


def _judge_expectation(
    root: EntityIdentity,
    shape: temporal_read.TemporalShape | None,
    position: inheritance.InheritanceEntityView,
    instruction: TargetWrite,
) -> TargetExpectation:
    """The starting condition a target write's revision arguments state, judged
    against the family's own revision kind (`m-opt-lock`): a versioned family
    takes ``if_version``, a temporal one ``if_tx_start``, and an
    unversioned Non-Temporal one neither.

    Stating both is refused first, because no family has two revisions; then a
    misstated kind, then a missing one, then the value itself.
    """
    mutation = instruction.mutation
    # A runtime caller may state either argument as any value, whatever the
    # annotation promises, so each is judged as the object it is.
    version = cast("object", instruction.if_version)
    tx_start = cast("object", instruction.if_tx_start)
    if version is not None and tx_start is not None:
        raise WriteInstructionError(
            f"{root.name}: {mutation!r} states both if_version and if_tx_start, and a target "
            "has one revision to state"
        )
    versioned = any(attribute.optimistic_locking for attribute in position.applicable_attributes)
    if versioned:
        if tx_start is not None:
            raise WriteInstructionError(
                f"{root.name}: {mutation!r} takes if_version, not if_tx_start — "
                f"{root.name!r} is versioned, so its revision is its version"
            )
        if version is None:
            raise WriteInstructionError(
                f"{root.name}: {mutation!r} requires if_version, the version of the state the "
                "write starts from as its caller last observed it"
            )
        if isinstance(version, bool) or not isinstance(version, int):
            raise WriteInstructionError(
                f"{root.name}: {mutation!r} takes an integer if_version, and "
                f"{type(version).__name__} is no version"
            )
        return ExpectedVersion(version)
    if isinstance(shape, temporal_read.TransactionTimeOnly | temporal_read.Bitemporal):
        if version is not None:
            raise WriteInstructionError(
                f"{root.name}: {mutation!r} takes if_tx_start, not if_version — {root.name!r} "
                "is temporal, so its revision is its milestone's Transaction-Time start"
            )
        if tx_start is None:
            raise WriteInstructionError(
                f"{root.name}: {mutation!r} requires if_tx_start, the Transaction-Time start of "
                "the milestone the write starts from as its caller last observed it"
            )
        return ExpectedTxStart(
            normalize_instant(_stated_instant(root, mutation, "if_tx_start", tx_start))
        )
    if version is not None or tx_start is not None:
        raise WriteInstructionError(
            f"{root.name}: {mutation!r} takes no revision argument — {root.name!r} is unversioned, "
            "so it has no revision for a caller to state"
        )
    return UNVERSIONED


def _prepare_target_payload(
    instruction: TargetWrite,
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    position: inheritance.InheritanceEntityView,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
    authored_members: Set[str] | None,
) -> tuple[Mapping[str, object], bool]:
    """A target write's row, judged, and whether it assigns any member.

    The primary key names the object and is no assignment. Every other member
    the row states is judged as an assignment, whatever produced the row — so a
    framework-owned, read-only, or ill-typed member is refused as it is for an
    update. A replacement states the object's complete writable state: an
    omitted required member is refused, an omitted nullable one is written
    empty, and an omitted ``many`` the empty collection, so no value is ever
    carried forward from the state it replaces.
    """
    selection = position.member_selection
    row = instruction.row
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
            f"{entity.identity.name}: target write row names undeclared member(s) {unknown}"
        )
    key = position.primary_key.identity.name
    if key not in row:
        raise WriteInstructionError(
            f"{entity.identity.name}: a target write names the object it writes by its primary "
            f"key, and this row states no {key!r}"
        )
    replaces = instruction.mutation in _REPLACEMENTS
    transformed = _transform_row(
        selection,
        entity,
        row,
        converter=converter,
        source_access=source_access,
        fill_missing_many=replaces,
    )
    prepared = transformed.row if not replaces else _completed(entity, position, transformed.row)
    for name, value in prepared.items():
        if name == key:
            continue
        failure = _member_failure(selection, name, transformed.failures)
        _judge_prepared_assignment(
            entity,
            _declared_member(selection, name),
            value,
            known_vo_violation=failure,
            known_value_valid=failure is None,
        )
    validate_write(entity, prepared, model, mutation="update", known_failures=transformed.failures)
    return prepared, any(name != key for name in prepared)


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
    instruction: KeyedWrite,
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    selection: inheritance.EntityMemberSelection,
    valid_time_window: TimeInterval | None,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
    authored_members: Set[str] | None,
) -> PreparedKeyedWrite:
    """Judge a keyed write's rows: subtype shape, members, then values.

    A keyed row key must name a member the target's family makes applicable —
    ANCESTRY-EFFECTIVE, so a concrete subtype's write naming an inherited key is
    declared. Sibling-branch and framework-owned-metadata fields are classified
    more specifically, and first, by ``inheritance.validate_subtype_write``.

    An explicit Wire insert payload may name an application-assigned primary key
    but never a framework-owned member: the interval bounds are stamped from the
    Clock Strategy and the version is derived. A neutral instruction row states
    content rather than authorship, so it carries such cells unjudged here. An
    explicit Wire update judges each changed member as an assignment.
    """
    inserting = instruction.mutation in INSERT_MUTATIONS
    members = selection.shape.by_name
    for row in instruction.rows:
        try:
            inheritance.validate_subtype_write(model, entity, row)
        except inheritance.InheritanceError as error:
            raise WriteRejectedError(error.rule, str(error)) from error
        if inserting and authored_members is not None:
            _refuse_framework_owned(entity, selection, authored_members)
        unknown = sorted(name for name in row if name not in members)
        if unknown:
            raise WriteInstructionError(
                f"{entity.identity.name}: keyed write row names undeclared member(s) {unknown}"
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
                only.row[name],
                known_vo_violation=failure,
                known_value_valid=failure is None,
            )
    for result in transformed:
        validate_write(
            entity,
            result.row,
            model,
            mutation=instruction.mutation,
            known_failures=result.failures,
        )
    return _prepared_keyed_write(
        instruction.mutation,
        entity,
        tuple(result.row for result in transformed),
        valid_time_window,
    )


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
    instruction: PredicateWrite,
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    selection: inheritance.EntityMemberSelection,
    valid_time_window: TimeInterval | None,
    *,
    converter: _LeafConverter,
    source_access: SourceAccess,
) -> PreparedPredicateWrite:
    """Judge a predicate write's payload in `m-case-format`'s order: the
    selecting predicate, the family refusal, then the assignments.

    The predicate is measured with the whole ``validate_predicate``
    vocabulary. An inheritance-family target is then refused
    (``subtype-write-set-based-unsupported``) before any assignment, so
    ancestry resolution never arises for one.

    Each assignment is completed before the next is visited: its reference must
    name a member of the exact target, once, before its value is prepared and
    judged. The first failing assignment therefore wins, and a reference fault
    outranks a bad value on the same assignment. Authored order is data order
    only; lowering emits columns in the target's Table Layout order.
    """
    validated = predicate_algebra.validate_predicate(entity, instruction.target.predicate, model)
    inheritance.reject_predicate_write(entity)
    _judge_assignment_shape(entity, instruction.mutation, instruction.assignments)
    seen: set[str] = set()
    prepared: list[PreparedAssignment] = []
    for assignment in instruction.assignments:
        # The owner segment is RESOLVED rather than compared as text, so a
        # canonical spelling names the target it denotes while an ambiguous
        # bare one — which resolves nowhere — stays refused.
        owner_spelling, _, name = assignment.attr.rpartition(".")
        owner = entity_by_name(model, owner_spelling)
        member = selection.binding(name)
        if owner is None or owner.identity != entity.identity or member is None:
            raise WriteInstructionError(
                f"{entity.identity.name}: assignment {assignment.attr!r} does not name a "
                f"declared member of {entity.identity.canonical}"
            )
        if name in seen:
            raise WriteInstructionError(
                f"{entity.identity.name}: assignment {assignment.attr!r} is duplicated — each "
                "member may be assigned at most once"
            )
        seen.add(name)
        authored = prepare_member_authoring(
            member.definition,
            assignment.value,
            source_access=source_access,
            normalize_leaf=converter,
            path=assignment.attr,
            allow_marker=isinstance(member, AttributeMetadata),
        )
        _judge_prepared_assignment(
            entity,
            member,
            authored.value,
            known_vo_violation=authored.failure,
            known_value_valid=authored.failure is None,
        )
        prepared.append(PreparedAssignment(member, authored.value))
    return _prepared_predicate_write(
        instruction.mutation,
        ValidatedMutationSelection(entity, validated),
        tuple(prepared),
        valid_time_window,
    )


def _judge_assignment_shape(
    entity: EntityMetadata,
    mutation: PredicateMutation,
    assignments: Sequence[WriteAssignment],
) -> None:
    if mutation in _ASSIGNMENT_MUTATIONS:
        if not assignments:
            raise WriteInstructionError(
                f"{entity.identity.name}: a predicate-selected {mutation!r} requires at least "
                "one assignment"
            )
    elif assignments:
        raise WriteInstructionError(
            f"{entity.identity.name}: a predicate-selected {mutation!r} names nothing to "
            "assign and takes no assignments"
        )


def _judge_prepared_assignment(
    target: EntityMetadata,
    member: _DeclaredMember,
    value: object,
    *,
    known_vo_violation: VoDocumentViolation | None,
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
            known_vo_violation=known_vo_violation,
            known_value_valid=known_value_valid,
        )
    except WriteAssignmentError as error:
        raise WriteInstructionError(f"{target.identity.canonical}.{error}") from error


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
    ).row


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
) -> _TransformedRow:
    prepared = prepare_authoring(
        selection.shape,
        row,
        source_access=source_access,
        normalize_leaf=converter,
        path=entity.identity.canonical,
        fill_missing_many=fill_missing_many,
        allow_root_markers=True,
    )
    return _TransformedRow(prepared.value, prepared.failures)


def _member_failure(
    selection: inheritance.EntityMemberSelection,
    name: str,
    failures: Mapping[int, VoDocumentViolation],
) -> VoDocumentViolation | None:
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
