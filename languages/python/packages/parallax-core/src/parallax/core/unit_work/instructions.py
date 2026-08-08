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

- **The instant surface is dimension-explicit.** Valid-Time bounds are named
  ``validFrom`` / ``until``; a bounded ``*Until`` mutation carries BOTH.
  The **Transaction-Time instant** is NOT an instruction field — it is Clock-supplied
  flush context, so the corpus's ``at`` authoring alias is an
  UNEXPECTED key here and :func:`deserialize` rejects it (the caller-facing shape
  cannot smuggle one in).
- **The transaction observation is not an instruction field.** The reserved
  control keys ``observedVersion`` / ``observedTxStart`` are FORBIDDEN on a durable
  write row; the observation is attached per materialized row at flush
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
from parallax.core.metamodel import (
    EntityMetadata,
    ambiguous_entity_spellings,
    entity_by_name,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.op_algebra import Operation

__all__ = [
    "INSERT_MUTATIONS",
    "MILESTONE_MUTATIONS",
    "TEMPORAL_KEYED_WRITE_MULTI_ROW",
    "InstructionRejectedError",
    "KeyedMutation",
    "KeyedWrite",
    "PredicateMutation",
    "PredicateSelection",
    "PredicateWrite",
    "WriteAssignment",
    "WriteInstruction",
    "WriteInstructionError",
    "deserialize",
    "non_temporal_milestone_refusal",
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

INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})
"""The keyed mutations that OPEN a row rather than write against an existing
one, which is what makes them the mutations that carry no Write Observation
(`m-unit-work` "Absence is structural"). Shared so the buffered carrier's own
refusal and the planner's coalescing both answer "is this an insert?" from one
definition."""

MILESTONE_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"insertUntil", "terminate", "terminateUntil", "updateUntil"}
)
"""The mutations that OPEN, SPLIT, or CLOSE a milestone rather than writing a row
outright, keyed and predicate-selected alike. Membership answers ONE direction of
target/mutation applicability: a target that derives no As-Of Axis admits no
member of this set, because it has no axis to hold the milestone
(`m-txtime-write` / `m-bitemp-write`).

Non-membership grants nothing in the other direction. The complement — `insert`,
`update`, `delete` — is not a triad every target admits: a temporal target spells
its removal `terminate` and rejects `delete` (`python.md` "Write verbs and
temporal spellings"), and `insert` is not on the predicate-selected surface at
all. What a TEMPORAL target admits is a question this set does not answer."""

_KEYED_MUTATIONS: Final[frozenset[str]] = INSERT_MUTATIONS | frozenset(
    {"update", "delete", "terminate", "updateUntil", "terminateUntil"}
)
_PREDICATE_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"update", "delete", "terminate", "updateUntil", "terminateUntil"}
)
# The bounded `*Until` forms carry BOTH Valid-Time bounds; every other form carries
# no `until` (its window runs `[validFrom, infinity)` or is non-temporal).
_BOUNDED_MUTATIONS: Final[frozenset[str]] = frozenset(
    {"insertUntil", "updateUntil", "terminateUntil"}
)
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
# share, owned normatively by `m-op-algebra` (a property of the reference site,
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
    """A keyed write: a ``mutation`` on one ``entity`` carrying the flat
    attribute-named neutral write input (``rows``).

    ``valid_from`` / ``until`` are the Valid-Time bounds; a
    bounded ``*Until`` mutation carries both, a plain temporal mutation carries only
    ``valid_from`` (window ``[valid_from, infinity)``), and a non-temporal
    mutation carries neither. The Transaction-Time instant is never a field here.
    """

    mutation: KeyedMutation
    entity: str
    rows: tuple[Mapping[str, object], ...]
    valid_from: str | None = None
    until: str | None = None

    def __post_init__(self) -> None:
        # Freeze each row into a read-only view so the buffered instruction stays
        # immutable (frozen/slots); equality is by row content either way.
        frozen = tuple(MappingProxyType(dict(row)) for row in self.rows)
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
    """The entity a predicate-selected write begins from plus its bare
    ``m-op-algebra`` predicate (a canonical operation node).

    This is the instruction-level carrier a buffered :class:`PredicateWrite`
    authors, distinct from the finalized :class:`~parallax.core.unit_work.
    planned.WriteTarget` a Planned Write settles into.
    """

    entity: str
    predicate: Operation


@dataclass(frozen=True, slots=True)
class PredicateWrite:
    """A predicate-selected (set-based) write: a ``mutation`` on every row of
    ``target`` matching its predicate, with ``assignments`` on the update forms."""

    mutation: PredicateMutation
    target: PredicateSelection
    assignments: tuple[WriteAssignment, ...] = ()
    valid_from: str | None = None
    until: str | None = None


WriteInstruction = KeyedWrite | PredicateWrite

# The reference pattern a predicate-write assignment `attr` must match, mirroring
# identity.schema.json's `attributeRef` by way of write-instruction.schema.json
# `$defs/writeAssignment`: an Entity spelling — canonical or bare — followed by
# the member it assigns.
_ASSIGNMENT_REF = re.compile(
    r"^([a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*\.)?[A-Z][A-Za-z0-9]*\.[a-z][A-Za-z0-9_]*$"
)

# The result modifiers a write target's predicate may never carry, by canonical
# wire tag (`m-case-format` `target.predicate`: "it is a bare write predicate,
# never a result modifier"; `python.md` §5: "`order_by`, `limit`, `include`,
# `as_of`, `history` / `as_of_range`, and `narrow` are all rejected on any write
# target"). A READ composes every one of them legally, which is why this is a
# rule of the write instruction and carries its own refusal rather than joining
# `validate_operation`'s vocabulary.
#
# `narrow` is the one entry of that enumeration NOT listed here, because it is
# the one whose meaning depends on its position rather than on its tag
# (`_reject_non_bare_predicate`). Every wrapper here means the same thing
# wherever it appears.
_NON_BARE_PREDICATES: Final[Mapping[type[object], str]] = MappingProxyType(
    {
        op_algebra.OrderBy: "orderBy",
        op_algebra.Limit: "limit",
        op_algebra.Distinct: "distinct",
        op_algebra.DeepFetch: "deepFetch",
        op_algebra.AsOf: "asOf",
        op_algebra.AsOfRange: "asOfRange",
        op_algebra.History: "history",
    }
)


# --------------------------------------------------------------------------- #
# Deserialize (canonical write-instruction document -> frozen instruction).    #
# --------------------------------------------------------------------------- #
def deserialize(doc: object) -> WriteInstruction:
    """Parse a canonical write-instruction document into a frozen instruction.

    Discriminates the two shapes by their required carrier (``rows`` -> keyed,
    ``target`` -> predicate), validates the closed shape, the mutation enum, the
    Valid-Time-bound pairing rules (a bounded ``*Until`` carries both bounds, every
    other form carries no ``until``), and — for a keyed write — that no row
    carries a forbidden observation control key or a smuggled Transaction-Time instant.
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


def _bound(node: Mapping[str, object], key: str, shape: str) -> str | None:
    if key not in node:
        return None
    value = node[key]
    if not isinstance(value, str) or not value:
        raise WriteInstructionError(f"{shape}: `{key}` must be a non-empty instant string")
    return value


def _check_valid_time_bounds(
    mutation: str, valid_from: str | None, until: str | None, shape: str
) -> None:
    """Enforce the schema's Valid-Time-bound pairing: a bounded ``*Until``
    mutation carries BOTH ``validFrom`` and ``until``, and every other mutation
    carries no ``until``.

    Verb shape only. Whether ``validFrom`` is required, optional, or forbidden
    follows from the TARGET's temporal profile, which deserialization has no
    model to ask, so nothing here rejects a ``validFrom`` on a write whose target
    turns out to be non-temporal or Transaction-Time-Only, nor a Bitemporal
    write that omits one.
    """
    if mutation in _BOUNDED_MUTATIONS:
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
    # The embedded predicate is a canonical m-op-algebra node — the sole write-side
    # reach into the algebra; op_algebra rejects a malformed one.
    predicate = op_algebra.deserialize(cast("Mapping[str, object]", predicate_doc))
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
        _emit_bounds(keyed_body, instruction.valid_from, instruction.until)
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
    _emit_bounds(predicate_body, instruction.valid_from, instruction.until)
    return predicate_body


def _emit_bounds(body: dict[str, object], valid_from: str | None, until: str | None) -> None:
    # An omitted bound stays omitted (the canonical minimal form), so a non-temporal
    # or plain-temporal instruction round-trips without gaining a null bound.
    if valid_from is not None:
        body["validFrom"] = valid_from
    if until is not None:
        body["until"] = until


# --------------------------------------------------------------------------- #
# Target/mutation applicability (metamodel-aware, shared across the layers).   #
# --------------------------------------------------------------------------- #
def non_temporal_milestone_refusal(entity_name: str, mutation: str) -> str | None:
    """Why a NON-TEMPORAL target refuses ``mutation``'s VERB, or ``None`` when
    this rule has nothing to say about it.

    ``None`` is not a verdict that the target admits the write: the verb is all
    that is measured, and the temporal coordinates the profile does or does not
    use go unexamined here and at every caller.

    Reached only once the caller has established that ``entity_name``'s
    inheritance family derives no As-Of Axis, because temporality is the whole
    question: a milestone verb names a milestone to open, split, or close, and a
    non-temporal target has no axis to hold one. Settling one anyway would keep
    the verb's row effect and silently drop its temporal meaning — a bounded
    ``updateUntil`` becoming an ordinary overwrite of the row it addressed.

    A MESSAGE rather than a refusal, because the same rule is owed by layers
    that classify differently: the build-time validator raises
    :class:`WriteInstructionError`, the buffering seam refuses before it can
    resolve a materializing target against a real connection, and
    :mod:`parallax.core.unit_work.write_planner` raises its own planning error as
    the last structural refusal before SQL. One wording, so an ingress cannot
    describe the mismatch differently from the flush that would otherwise settle
    it.
    """
    if mutation not in MILESTONE_MUTATIONS:
        return None
    return (
        f"{mutation!r} is a temporal milestone verb, and {entity_name!r} declares no "
        "temporal dimension — a milestone verb never applies to a non-temporal entity "
        "(m-txtime-write / m-bitemp-write)"
    )


def temporal_singleton_refusal(entity_name: str, instruction: WriteInstruction) -> str | None:
    """Why a TEMPORAL target refuses ``instruction``'s ROW COUNT, or ``None``
    when this rule has nothing to say about it.

    Reached only once the caller has established that ``entity_name``'s
    inheritance family DOES derive an As-Of Axis — the converse half of
    :func:`non_temporal_milestone_refusal`'s quadrant, and temporality is again
    the whole question. Each row of a milestone chain closes its own current
    milestone, consumes its own Temporal Observation, and opens its own
    successors, and a temporal entity never collapses into a set-based statement
    (`m-batch-write`), so several rows under one keyed instruction denote several
    independent chains rather than one wider write (`m-unit-work` "A temporal
    keyed instruction carries exactly one row").

    ``None`` for a predicate-selected instruction, which carries no rows at all,
    and for the single-row keyed shape the rule admits.
    """
    if not isinstance(instruction, KeyedWrite) or len(instruction.rows) == 1:
        return None
    return (
        f"{entity_name!r}: a keyed {instruction.mutation!r} on a temporal target carries "
        f"{len(instruction.rows)} rows — a temporal keyed instruction carries exactly one "
        "(m-unit-work), since each row closes its own milestone, consumes its own "
        "observation, and chains its own successors; author one instruction per row"
    )


def _derives_as_of_axes(model: AcceptedMetamodel, entity: EntityMetadata) -> bool:
    """Whether ``entity``'s inheritance FAMILY derives an As-Of Axis.

    Temporality is family-level metadata only the root may declare
    (`m-inheritance`), so a descendant's own accepted Metadata carries no axis
    even when every one of its rows is milestoned.
    """
    position = inheritance.view(model).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return bool(entity.declared_as_of_axes)
    root = model.entity(position.root)
    return bool((entity if root is None else root).declared_as_of_axes)


# --------------------------------------------------------------------------- #
# Member-name honesty (metamodel-aware build-time validator).                  #
# --------------------------------------------------------------------------- #
def validate_instruction(instruction: WriteInstruction, model: AcceptedMetamodel) -> None:
    """Validate an instruction against the metamodel: its selecting predicate,
    then its member names.

    A predicate-selected instruction's ``target.predicate`` is measured twice,
    in the order `m-case-format` states ("The model-aware validator validates
    the predicate ..., checks entity scope and bare-predicate rules, [then]
    rejects ... unassignable assignments"), and BEFORE the assignments for that
    reason:

    - the WHOLE ``validate_operation`` vocabulary from its own resolved root —
      an attribute reference outside the active position, an ambiguous Entity
      spelling, an inverted ``between`` window, a literal disagreeing with its
      member's declared type;
    - the BARE-PREDICATE rule (:func:`_reject_non_bare_predicate`), which
      ``validate_operation`` cannot carry because it is shared with the read
      path, where a result modifier is legal and must stay legal.

    An inheritance-family target is then rejected
    (``subtype-write-set-based-unsupported``, `m-inheritance` "Per-object
    writes are keyed; set-based inheritance writes are out of scope") — after
    the predicate rules, which the spec orders first, and BEFORE the
    assignments, which `python.md` §5 requires: "every assigned attribute or
    value-object member must be declared by the exact target entity — set-based
    writes already reject inheritance-family targets, so ancestry resolution
    never arises."

    Every predicate-write ingress reaches these rules through here — the typed
    ``_where`` verbs and the conformance engine's own translation both call this
    before the buffering seam — so both classify the same instruction the same
    way, and a rejection precedes buffering, the materializing resolve, and any
    SQL.

    A keyed write row key must name a declared attribute or value object of the
    entity — for an inheritance-family participant, ANCESTRY-EFFECTIVE: every
    member the Inheritance Facet's applicable-member view carries, never just
    the target's own LOCAL declarations, else a well-formed concrete-subtype
    write naming a root- or abstract-subtype-inherited member (`CardPayment`'s
    inherited `id`/`amount`) would be wrongly rejected as "undeclared" (a family
    participant's own accepted Metadata carries only its OWN attributes —
    m-inheritance "Inherited members"). Sibling-branch and
    framework-owned-metadata fields are already caught more specifically, and
    FIRST, by `validate_write`'s subtype rules — this gate only ever sees
    whatever THAT pass left unexamined, so widening it to the whole family never
    re-opens a hole the more specific check already closes. A predicate write's
    assignment `attr` must name a `target.entity` member, same family-effective
    set. This is the member-name honesty gate — the flush-time refusing compile
    port is the structural enforcer of the remaining typed / Table Layout slot
    classification, mirroring the predicate-write materialization split.

    Once a predicate-write assignment's `attr` names a genuinely declared
    member, `inheritance.validate_write_assignment` additionally rejects a
    primary-key or framework-owned (version) target and any scalar value that
    does not conform to its declared neutral type
    (`python.md:667-676`/`m-case-format.md:700` -- the SAME classification a
    `.set(...)`-built assignment and an `Entity.edit(**changes)` entry are
    rejected with at build time (`entity._expressions.AttributeExpr.set`,
    `entity._entity.Entity.edit`); one validator, three callers, which is
    the sharing neither scope could otherwise reach across the
    `core/spec/modules.md` section 7 DAG).

    Last, for BOTH shapes, the target's temporal profile decides one rule per
    side. A target whose family derives NO As-Of Axis refuses a milestone verb
    (:func:`non_temporal_milestone_refusal`); a target whose family DOES derive
    one refuses a plural keyed instruction
    (:func:`temporal_singleton_refusal`, classified
    ``temporal-keyed-write-multi-row``). Both are rules about the target rather
    than about the instruction alone, so they are asked here rather than in
    :func:`deserialize`, and both are asked of the whole write surface. Without
    the first, a milestone verb aimed at a versioned non-temporal target reaches
    the materializing resolve and settles as an ordinary row write, keeping the
    row effect and dropping the bounded-temporal meaning the verb was chosen
    for. Without the second, a plural chain survives to
    :mod:`parallax.core.unit_work.write_planner`, whose own settle-time refusal
    stays the last structural backstop before SQL but can no longer name the
    ingress that authored it.

    Those two are the whole of it, and `m-case-format`'s rule that the
    model-aware validator "requires only the temporal coordinates the target
    profile uses" is NOT yet enforced here. A TEMPORAL target's verb goes
    unmeasured, so a `delete` `python.md` rejects is accepted, and no bound is
    measured against a profile at all: a `validFrom` on a non-temporal or
    Transaction-Time-Only target passes, and so does a Bitemporal write that
    omits the one it requires.
    """
    if isinstance(instruction, KeyedWrite):
        entity = _entity(model, instruction.entity)
        members = _declared_members(model, entity)
        for row in instruction.rows:
            unknown = sorted(key for key in row if key not in members)
            if unknown:
                raise WriteInstructionError(
                    f"{entity.identity.name}: keyed write row names undeclared member(s) {unknown}"
                )
    else:
        entity = _entity(model, instruction.target.entity)
        op_algebra.validate_operation(entity, instruction.target.predicate, model)
        _reject_non_bare_predicate(entity.identity.name, instruction.target.predicate)
        inheritance.reject_predicate_write(entity)
        members = _declared_members(model, entity)
        seen: set[str] = set()
        for assignment in instruction.assignments:
            # The owner segment is RESOLVED rather than compared as text, so a
            # canonical spelling names the target it denotes while an ambiguous
            # bare one — which resolves nowhere — stays refused.
            owner_spelling, _, member = assignment.attr.rpartition(".")
            owner = entity_by_name(model, owner_spelling)
            if owner is None or owner.identity != entity.identity or member not in members:
                raise WriteInstructionError(
                    f"{entity.identity.name}: assignment {assignment.attr!r} does not name a "
                    "declared member"
                )
            if member in seen:
                raise WriteInstructionError(
                    f"{entity.identity.name}: assignment {assignment.attr!r} is duplicated — each "
                    "field may be assigned at most once (python.md §5)"
                )
            seen.add(member)
            try:
                inheritance.validate_write_assignment(model, entity, member, assignment.value)
            except inheritance.WriteAssignmentError as exc:
                raise WriteInstructionError(str(exc)) from exc
    if _derives_as_of_axes(model, entity):
        plural = temporal_singleton_refusal(entity.identity.name, instruction)
        if plural is not None:
            raise InstructionRejectedError(TEMPORAL_KEYED_WRITE_MULTI_ROW, plural)
    else:
        refusal = non_temporal_milestone_refusal(entity.identity.name, instruction.mutation)
        if refusal is not None:
            raise WriteInstructionError(refusal)


def _reject_non_bare_predicate(entity_name: str, predicate: Operation) -> None:
    """Refuse a write target's predicate that is not BARE (`m-case-format`
    `target.predicate`, `python.md` §5) — a result modifier, a temporal
    wrapper, or a deep fetch anywhere in it, and whole-result narrowing at the
    result position.

    ``narrow`` is the one member of that enumeration whose meaning is
    POSITIONAL, and `m-op-algebra` draws the line: a top-level ``narrow`` is
    "the node a whole-result narrowing produces", while "a `narrow` appearing
    as a predicate term inside a boolean combinator is a filter" over the
    unchanged position. The same distinction admits a ``narrow`` inside a
    navigation filter's ``op``, where it narrows the relationship target the
    hop reaches rather than the written rows. So a whole-result narrow is
    refused — it is `python.md` §5's ``.narrow()`` CLAUSE on the write target —
    and a predicate-scoped one is a filter the write's own selection is made
    of, exactly like the ``exists`` that carries it.

    The result position is the ROOT here, and only the root. `m-op-algebra`
    fixes the closed set of wrappers that may carry a whole-result narrow up to
    it — ``orderBy`` / ``limit`` / ``distinct`` / ``deepFetch`` / ``asOf`` /
    ``asOfRange`` / ``history``, the same set
    :func:`~parallax.core.op_algebra.validate._ordered_scope` resolves an order
    key's position through — and every one of them is itself refused above, at
    any position. Nothing else passes the position through, so no other node
    can hold a whole-result narrow.

    Everything else is checked at every position rather than only at the root
    because the algebra admits a directive as a boolean operand
    (``and(limit(...), eq(...))`` round-trips), and a nested one reaches
    exactly the same lowering the root one does.
    """
    if isinstance(predicate, op_algebra.Narrow):
        raise WriteInstructionError(
            f"{entity_name}: a `narrow` wrapping the whole write predicate is whole-result "
            "narrowing, not a bare write predicate — a predicate-selected write target "
            "carries nothing but a predicate (a `narrow` used as a predicate term, inside "
            "a boolean combinator or a navigation filter, is a filter and is accepted)"
        )
    _reject_result_modifier(entity_name, predicate)


def _reject_result_modifier(entity_name: str, predicate: Operation) -> None:
    """Refuse a result modifier, temporal wrapper, or deep fetch at ANY position
    within a write target's predicate (:func:`_reject_non_bare_predicate`)."""
    wrapper = _NON_BARE_PREDICATES.get(type(predicate))
    if wrapper is not None:
        raise WriteInstructionError(
            f"{entity_name}: `{wrapper}` is a result modifier, not a bare write predicate — "
            "a predicate-selected write target carries nothing but a predicate"
        )
    match predicate:
        case op_algebra.And(operands=operands) | op_algebra.Or(operands=operands):
            for operand in operands:
                _reject_result_modifier(entity_name, operand)
        case (
            op_algebra.Not(operand=operand)
            | op_algebra.Group(operand=operand)
            | op_algebra.Narrow(operand=operand)
        ):
            _reject_result_modifier(entity_name, operand)
        case (
            op_algebra.Navigate(op=nested)
            | op_algebra.Exists(op=nested)
            | op_algebra.NotExists(op=nested)
        ):
            if nested is not None:
                _reject_result_modifier(entity_name, nested)
        case _:
            return


def _entity(model: AcceptedMetamodel, name: str) -> EntityMetadata:
    """The accepted Metadata a write's bare-or-canonical target names, by
    :func:`~parallax.core.metamodel.entity_by_name`'s ambiguity-rejecting rule.

    That rule answers a miss for two different mistakes, and this is the boundary
    every externally produced instruction crosses, so the two are classified
    apart: a bare spelling two namespaces share is the normative
    `reference-ambiguous-entity-name` refusal
    (:class:`InstructionRejectedError`, `m-op-algebra` "Entity spellings in a
    reference position"), naming the canonical spellings that would resolve;
    anything else names no declared Entity at all and stays a plain
    :class:`WriteInstructionError`. Classifying here is also what keeps an
    ambiguous instruction out of the planner, whose own target lookup would
    answer the same miss by leaving the write unbound to any observation.
    """
    entity = entity_by_name(model, name)
    if entity is not None:
        return entity
    shared = ambiguous_entity_spellings(model, name)
    if shared:
        raise InstructionRejectedError(
            REFERENCE_AMBIGUOUS_ENTITY_NAME,
            f"the bare Entity spelling {name!r} is shared by {list(shared)}, so it names no "
            "single Entity in this model and the write resolves nowhere (m-op-algebra reference "
            "resolution); spell the one this write means",
        )
    raise WriteInstructionError(f"unknown entity {name!r}")


def _declared_members(model: AcceptedMetamodel, entity: EntityMetadata) -> frozenset[str]:
    """The declared attribute + value-object names a write may reference (business
    names, never physical columns) — ``entity``'s whole inheritance FAMILY for a
    participant, its own declarations otherwise (the Inheritance Facet's
    applicable-member view already degrades to the plain single-entity view for a
    non-participant, so no branch is needed here)."""
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return frozenset()
    attrs = {attribute.identity.name for attribute in view.applicable_attributes}
    value_objects = {vo.identity.path[-1] for vo in view.applicable_value_objects}
    return frozenset(attrs | value_objects)
