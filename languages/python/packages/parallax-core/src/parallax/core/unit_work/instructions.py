"""The write-instruction IR (m-unit-work write-instruction vocabulary).

Frozen ``slots`` dataclasses for the two canonical write-instruction shapes a unit
of work buffers — the write-side analogue of the operation algebra — plus the
serde that round-trips them through ``core/schemas/write-instruction.schema.json``
(``serialize(deserialize(x)) == x``, JSON and YAML). There are exactly two shapes:

- a **keyed** instruction (:class:`KeyedWrite`) — a ``mutation`` on one ``entity``
  carrying the flat attribute-named neutral write input (``rows``);
- a **predicate-selected** instruction (:class:`PredicateWrite`) — a ``mutation``
  on every row of a ``target`` (entity + a bare ``m-op-algebra`` predicate)
  matching that predicate, with ``assignments`` on the update forms.

The embedded predicate is a canonical ``m-op-algebra`` node — the sole place the
write side reaches the algebra — deserialized through :mod:`parallax.core.op_algebra`
so a malformed predicate is rejected, exactly as the schema defers predicate
validation to ``operation.schema.json``. Two structural rules keep the instruction
framework-honest and are enforced here:

- **The instant surface is axis-explicit.** Business bounds are named uniformly
  ``businessFrom`` / ``businessTo``; a bounded ``*Until`` mutation carries BOTH.
  The **processing instant** is NOT an instruction field — it is Clock-supplied
  flush context (ADR 0010), so the corpus's ``at`` authoring alias is an
  UNEXPECTED key here and :func:`deserialize` rejects it (the caller-facing shape
  cannot smuggle one in).
- **The transaction observation is not an instruction field.** The reserved
  control keys ``observedVersion`` / ``observedInZ`` are FORBIDDEN on a durable
  write row (ADR 0013); the observation is attached per materialized row at flush
  (:mod:`parallax.core.unit_work.planner`), never carried on the instruction.

Construction is value-only (mirroring ``m-op-algebra`` nodes): structural shape is
validated by :func:`deserialize`; member-name honesty against a metamodel is
:func:`validate_instruction`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, cast

from parallax.core import inheritance, op_algebra
from parallax.core.descriptor import Entity, Metamodel
from parallax.core.op_algebra import Operation

__all__ = [
    "KeyedMutation",
    "KeyedWrite",
    "PredicateMutation",
    "PredicateWrite",
    "WriteAssignment",
    "WriteInstruction",
    "WriteInstructionError",
    "WriteTarget",
    "deserialize",
    "serialize",
    "validate_instruction",
]

# The keyed write mutation surface: the MVP non-temporal / audit-only verbs plus
# the full-bitemporal bounded rectangle split (write-instruction.schema.json).
KeyedMutation = Literal[
    "insert", "update", "delete", "terminate", "insertUntil", "updateUntil", "terminateUntil"
]
# The predicate-selected (set-based) mutation surface: there is no `insert` — a
# predicate cannot select rows that do not yet exist.
PredicateMutation = Literal["update", "delete", "terminate", "updateUntil", "terminateUntil"]

_KEYED_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"insert", "update", "delete", "terminate", "insertUntil", "updateUntil", "terminateUntil"}
)
_PREDICATE_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"update", "delete", "terminate", "updateUntil", "terminateUntil"}
)
# The bounded `*Until` forms carry BOTH business bounds; every other form carries
# no `businessTo` (its window runs `[businessFrom, infinity)` or is non-temporal).
_BOUNDED_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"insertUntil", "updateUntil", "terminateUntil"}
)
# The assignment-bearing predicate verbs; the others name nothing to assign.
_ASSIGNMENT_MUTATIONS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})

# The framework-owned transaction observation is NOT durable instruction state
# (ADR 0013): these control keys are forbidden on a write row.
_FORBIDDEN_ROW_KEYS: Final[frozenset[str]] = frozenset({"observedVersion", "observedInZ"})


class WriteInstructionError(ValueError):
    """A write-instruction document is not a well-formed canonical instruction."""


@dataclass(frozen=True, slots=True)
class KeyedWrite:
    """A keyed write: a ``mutation`` on one ``entity`` carrying the flat
    attribute-named neutral write input (``rows``).

    ``business_from`` / ``business_to`` are the axis-explicit business bounds; a
    bounded ``*Until`` mutation carries both, a plain temporal mutation carries only
    ``business_from`` (window ``[business_from, infinity)``), and a non-temporal
    mutation carries neither. The processing instant is never a field here.
    """

    mutation: KeyedMutation
    entity: str
    rows: tuple[Mapping[str, object], ...]
    business_from: str | None = None
    business_to: str | None = None

    def __post_init__(self) -> None:
        # Freeze each row into a read-only view so the buffered instruction stays
        # immutable (frozen/slots); equality is by row content either way.
        frozen = tuple(MappingProxyType(dict(row)) for row in self.rows)
        object.__setattr__(self, "rows", frozen)


@dataclass(frozen=True, slots=True)
class WriteAssignment:
    """One ordered predicate-write assignment: ``attr`` (a ``Class.member`` reference)
    set to ``value`` (a neutral literal / document). List order is DATA order only —
    the emitted SET columns follow the descriptor ``columnOrder`` at lowering."""

    attr: str
    value: object


@dataclass(frozen=True, slots=True)
class WriteTarget:
    """The entity a predicate-selected write begins from plus its bare
    ``m-op-algebra`` predicate (a canonical operation node)."""

    entity: str
    predicate: Operation


@dataclass(frozen=True, slots=True)
class PredicateWrite:
    """A predicate-selected (set-based) write: a ``mutation`` on every row of
    ``target`` matching its predicate, with ``assignments`` on the update forms."""

    mutation: PredicateMutation
    target: WriteTarget
    assignments: tuple[WriteAssignment, ...] = ()
    business_from: str | None = None
    business_to: str | None = None


WriteInstruction = KeyedWrite | PredicateWrite

# The reference pattern a predicate-write assignment `attr` must match
# (write-instruction.schema.json `$defs/writeAssignment`): a qualified
# `Class.member` descriptor reference.
_ASSIGNMENT_REF = re.compile(r"^[A-Za-z][A-Za-z0-9]*\.[a-z][A-Za-z0-9]*$")


# --------------------------------------------------------------------------- #
# Deserialize (canonical write-instruction document -> frozen instruction).    #
# --------------------------------------------------------------------------- #
def deserialize(doc: object) -> WriteInstruction:
    """Parse a canonical write-instruction document into a frozen instruction.

    Discriminates the two shapes by their required carrier (``rows`` -> keyed,
    ``target`` -> predicate), validates the closed shape, the mutation enum, the
    business-bound pairing rules (a bounded ``*Until`` carries both bounds, every
    other form carries no ``businessTo``), and — for a keyed write — that no row
    carries a forbidden observation control key or a smuggled processing instant.
    """
    if not isinstance(doc, Mapping):
        raise WriteInstructionError(
            f"write instruction must be a mapping, got {type(doc).__name__}"
        )
    node = cast("Mapping[str, object]", doc)
    has_rows = "rows" in node
    has_target = "target" in node
    if has_rows and has_target:
        raise WriteInstructionError(
            "write instruction is ambiguous: it carries both `rows` (keyed) "
            "and `target` (predicate)"
        )
    if has_rows:
        return _keyed(node)
    if has_target:
        return _predicate(node)
    raise WriteInstructionError(
        "write instruction must carry `rows` (keyed) or `target` (predicate)"
    )


def _reject_extra(node: Mapping[str, object], allowed: frozenset[str], shape: str) -> None:
    extra = sorted(set(node) - allowed)
    if extra:
        # `at` is the corpus's Clock-context alias, an UNEXPECTED key here — the
        # canonical instruction never carries a processing instant (ADR 0010).
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


def _bound(node: Mapping[str, object], key: str, shape: str) -> str | None:
    if key not in node:
        return None
    value = node[key]
    if not isinstance(value, str) or not value:
        raise WriteInstructionError(f"{shape}: `{key}` must be a non-empty instant string")
    return value


def _check_business_bounds(
    mutation: str, business_from: str | None, business_to: str | None, shape: str
) -> None:
    """Enforce the schema's business-bound pairing: a bounded ``*Until`` carries
    BOTH bounds; every other form carries no ``businessTo``."""
    if mutation in _BOUNDED_MUTATIONS:
        if business_from is None or business_to is None:
            raise WriteInstructionError(
                f"{shape}: `{mutation}` is bounded and MUST carry both "
                "`businessFrom` and `businessTo`"
            )
    elif business_to is not None:
        raise WriteInstructionError(
            f"{shape}: `{mutation}` is unbounded and MUST NOT carry `businessTo`"
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
        node, frozenset({"mutation", "entity", "rows", "businessFrom", "businessTo"}), "keyed write"
    )
    _require(node, ("mutation", "entity", "rows"), "keyed write")
    mutation = _mutation(node, _KEYED_MUTATIONS, "keyed write")
    entity = _entity_name(node, "entity", "keyed write")
    rows = _rows(node)
    business_from = _bound(node, "businessFrom", "keyed write")
    business_to = _bound(node, "businessTo", "keyed write")
    _check_business_bounds(mutation, business_from, business_to, "keyed write")
    return KeyedWrite(
        mutation=cast("KeyedMutation", mutation),
        entity=entity,
        rows=rows,
        business_from=business_from,
        business_to=business_to,
    )


def _target(node: Mapping[str, object]) -> WriteTarget:
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
    # The embedded predicate is a canonical m-op-algebra node — the sole write-side
    # reach into the algebra; op_algebra rejects a malformed one.
    predicate = op_algebra.deserialize(cast("Mapping[str, object]", predicate_doc))
    return WriteTarget(entity=entity, predicate=predicate)


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
        frozenset({"mutation", "target", "assignments", "businessFrom", "businessTo"}),
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
    business_from = _bound(node, "businessFrom", "predicate write")
    business_to = _bound(node, "businessTo", "predicate write")
    _check_business_bounds(mutation, business_from, business_to, "predicate write")
    return PredicateWrite(
        mutation=cast("PredicateMutation", mutation),
        target=target,
        assignments=assignments,
        business_from=business_from,
        business_to=business_to,
    )


# --------------------------------------------------------------------------- #
# Serialize (frozen instruction -> canonical minimal document).                #
# --------------------------------------------------------------------------- #
def serialize(instruction: WriteInstruction) -> dict[str, object]:
    """Emit the canonical minimal write-instruction document for one instruction."""
    if isinstance(instruction, KeyedWrite):
        keyed_body: dict[str, object] = {
            "mutation": instruction.mutation,
            "entity": instruction.entity,
            "rows": [dict(row) for row in instruction.rows],
        }
        _emit_bounds(keyed_body, instruction.business_from, instruction.business_to)
        return keyed_body
    predicate_body: dict[str, object] = {
        "mutation": instruction.mutation,
        "target": {
            "entity": instruction.target.entity,
            "predicate": op_algebra.serialize(instruction.target.predicate),
        },
    }
    if instruction.assignments:
        predicate_body["assignments"] = [
            {"attr": a.attr, "value": a.value} for a in instruction.assignments
        ]
    _emit_bounds(predicate_body, instruction.business_from, instruction.business_to)
    return predicate_body


def _emit_bounds(
    body: dict[str, object], business_from: str | None, business_to: str | None
) -> None:
    # An omitted bound stays omitted (the canonical minimal form), so a non-temporal
    # or plain-temporal instruction round-trips without gaining a null bound.
    if business_from is not None:
        body["businessFrom"] = business_from
    if business_to is not None:
        body["businessTo"] = business_to


# --------------------------------------------------------------------------- #
# Member-name honesty (metamodel-aware build-time validator).                  #
# --------------------------------------------------------------------------- #
def validate_instruction(instruction: WriteInstruction, meta: Metamodel) -> None:
    """Validate an instruction's member names against the metamodel (D-1).

    A keyed write row key must name a declared attribute or value object of the
    entity — for an inheritance-family participant, ANCESTRY-EFFECTIVE: every
    member declared anywhere in the family (`inheritance.family_attributes` /
    `inheritance.superset_value_objects`), never just the target's own LOCAL
    declarations, else a well-formed concrete-subtype write naming a root- or
    abstract-subtype-inherited member (`CardPayment`'s inherited `id`/`amount`)
    would be wrongly rejected as "undeclared" (a family participant's own
    compiled record carries only its OWN attributes — m-inheritance "Inherited
    members"). Sibling-branch and framework-owned-metadata fields are already
    caught more specifically, and FIRST, by `validate_write`'s subtype rules
    (COR-3 Phase 8 increment 2) — this gate only ever sees whatever THAT pass
    left unexamined, so widening it to the whole family never re-opens a hole
    the more specific check already closes. A predicate write's assignment
    `attr` must name a `target.entity` member, same family-effective set. This
    is the member-name honesty gate — the flush-time refusing compile port (M4)
    is the structural enforcer of the remaining typed / columnOrder
    classification, mirroring the predicate-write materialization split.
    """
    if isinstance(instruction, KeyedWrite):
        entity = _entity(meta, instruction.entity)
        members = _declared_members(entity, meta)
        for row in instruction.rows:
            unknown = sorted(key for key in row if key not in members)
            if unknown:
                raise WriteInstructionError(
                    f"{entity.name}: keyed write row names undeclared member(s) {unknown}"
                )
    else:
        entity = _entity(meta, instruction.target.entity)
        members = _declared_members(entity, meta)
        seen: set[str] = set()
        for assignment in instruction.assignments:
            owner, _, member = assignment.attr.partition(".")
            if owner != entity.name or member not in members:
                raise WriteInstructionError(
                    f"{entity.name}: assignment {assignment.attr!r} does not name a declared member"
                )
            if member in seen:
                raise WriteInstructionError(
                    f"{entity.name}: assignment {assignment.attr!r} is duplicated — each field "
                    "may be assigned at most once (python.md §5)"
                )
            seen.add(member)


def _entity(meta: Metamodel, name: str) -> Entity:
    try:
        return meta.entity(name)
    except KeyError:
        raise WriteInstructionError(f"unknown entity {name!r}") from None


def _declared_members(entity: Entity, meta: Metamodel) -> frozenset[str]:
    """The declared attribute + value-object names a write may reference (business
    names, never physical columns) — ``entity``'s whole inheritance FAMILY for a
    participant, its own declarations otherwise (`inheritance.family_attributes`
    / `inheritance.superset_value_objects` already degrade to the plain
    single-entity view for a non-participant, so no branch is needed here)."""
    attrs = inheritance.family_attributes(meta, entity)
    value_objects = inheritance.superset_value_objects(meta, (entity.name,))
    return frozenset({attr.name for attr in attrs} | {vo.name for vo in value_objects})
