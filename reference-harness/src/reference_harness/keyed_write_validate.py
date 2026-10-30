"""Model-aware keyed instruction validation (m-unit-work).

The two other write validators judge a *payload*: `write_validate` walks a
neutral write row's value-object documents, `predicate_write_validate` judges a
predicate-selected instruction's target and assignments. This one judges the
**shape and assignment names of a keyed instruction** — the members `mutation` / `entity` /
`rows` carry *together* — against what its target's temporal profile admits:

* ``temporal-keyed-write-multi-row`` — a keyed instruction on a **temporal**
  target carries more than one row. Each row of a milestone chain closes its own
  current milestone, settles against its own Temporal Observation, and opens its own
  successors, and a temporal target never collapses into a set-based statement
  (`m-batch-write`), so several rows under one instruction denote several
  independent chains rather than one wider write. Settling the first row and
  discarding the rest is what the rule forbids, which is why refusing is the only
  conforming answer even when the discarded rows would each have lowered to
  well-formed SQL of their own.
* ``framework-owned-member-assigned`` — an amendment or replacement names a
  framework-owned member as a caller assignment. Choreography callers may admit
  internal scalar framework markers separately from caller-authored input.

It also answers one PROVENANCE question about those same members — whether the
instruction states a DB-computed write marker, the framework's own bookkeeping
rather than a write a caller authors (:func:`states_framework_marker`) — because
that answer depends on the target's declared member roles just as the shape rule
depends on its temporal profile.

The bound is model-dependent — it exists only for a temporal target — so the
shared case schema states the general one-or-more `rows` bound and leaves this to
a validator that can see the model. Every authoring location a keyed instruction
reaches this harness through asks it here, so no lane can be read as saying
something different:

* a `scenario` step's own buffered write (:mod:`reference_harness.schema_validate`);
* the `rejected` lane's keyed `when.write`, where the instruction is itself the
  input under test (:func:`~reference_harness.case_runner._validate_rejected_keyed_write`);
* a `when.writeSequence` step, whose `mutation` / `entity` / `rows` ARE a keyed
  instruction's own members even though this harness grades the sequence by
  executing its golden DML
  (:func:`~reference_harness.case_runner._assert_write_input_columns`); and
* a settled scenario write's entry, on the way to the one row the find it names
  handed over (:func:`~reference_harness.case_runner._sole_settled_row`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from .case import Entity
from .inheritance import tag_of
from .portable_literal import decode_timestamp
from .temporality import temporal_axes
from .value_object_resolve import RejectionError
from .write_validate import framework_owned_names, undeclared_members

TEMPORAL_KEYED_WRITE_MULTI_ROW = "temporal-keyed-write-multi-row"
FRAMEWORK_OWNED_MEMBER_ASSIGNED = "framework-owned-member-assigned"

KEYED_WRITE_REJECTED_RULES: frozenset[str] = frozenset(
    {TEMPORAL_KEYED_WRITE_MULTI_ROW, FRAMEWORK_OWNED_MEMBER_ASSIGNED}
)


def undeclared_row_members(entity: Entity, instruction: Mapping[str, Any]) -> list[str]:
    """The row keys *instruction* names that *entity* does not declare, sorted.

    Member honesty is a payload judgment, after instruction applicability: a row
    naming nothing real is a case-authoring defect rather than a portable rule.

    It is asked AFTER the concrete-subtype payload-shape rules, which own every
    name the FAMILY declares (`m-inheritance`): a sibling branch's attribute is not
    a member of the target either, and reporting it here would replace the specific
    rule the family violated with a generic authoring failure.

    The judgement itself is the neutral write row's
    (:func:`~reference_harness.write_validate.undeclared_members`), applied to each
    row the instruction carries; this function only spreads it over them, so a row
    is judged the same whether an instruction or a bare `when.write` carries it.
    """
    rows = instruction.get("rows")
    unknown: set[str] = set()
    for row in rows if isinstance(rows, list) else ():
        if isinstance(row, Mapping):
            unknown |= set(undeclared_members(entity, row))
    return sorted(unknown)


_FRAMEWORK_MARKER_KEYS = (frozenset({"computed"}), frozenset({"increment"}))


def is_framework_marker(value: Any) -> bool:
    """Whether a scalar attribute's ① value is a DB-computed write marker rather than a
    literal (`m-value-object` "Writing")."""
    return isinstance(value, dict) and frozenset(value) in _FRAMEWORK_MARKER_KEYS


def states_framework_marker(entity: Entity, instruction: Mapping[str, Any]) -> bool:
    """Whether *instruction* assigns a DB-computed write marker AT A SCALAR
    ATTRIBUTE — the `m-value-object` "Writing" markers (`{computed: …}` /
    `{increment: …}`) that name the framework's own pk-gen allocation or version
    advance rather than a value a caller authored.

    The member's declared metamodel role decides, never the value's shape: a
    value object binds its whole literal document even when that document is
    shaped like a marker, and the marker form is scalar-attribute-only
    (`m-case-format` *Write-sequence cases*).
    """
    scalars = {attribute["name"] for attribute in entity.attributes}
    rows = instruction.get("rows")
    return any(
        name in scalars and is_framework_marker(value)
        for row in (rows if isinstance(rows, list) else ())
        if isinstance(row, Mapping)
        for name, value in row.items()
    )


def validate_keyed_assignment_members(
    entity: Entity,
    mutation: str,
    row: Mapping[str, Any],
    *,
    allow_framework_markers: bool = False,
) -> None:
    """Refuse caller assignments to framework-owned members before row values.

    Concrete-subtype metadata names are judged by the caller first. Only a
    choreography caller may admit scalar framework markers as bookkeeping.
    """
    if mutation not in {"amend", "amendUntil", "replace", "replaceUntil"}:
        return
    owned = framework_owned_names(entity)
    tag = tag_of(entity.runtime_facts)
    if tag is not None:
        owned -= {tag[0]}
    for name, value in row.items():
        if name in owned and not (allow_framework_markers and is_framework_marker(value)):
            raise RejectionError(
                FRAMEWORK_OWNED_MEMBER_ASSIGNED,
                f"{entity.canonical_name}.{name}: framework-owned members may not be assigned",
            )


class KeyedWriteApplicabilityError(ValueError):
    """A keyed operation or window does not fit its target."""


def _keyed_bound(instruction: Mapping[str, Any], name: str) -> dt.datetime:
    value = instruction[name]
    instant = decode_timestamp(value) if isinstance(value, str) else None
    if instant is None:
        raise KeyedWriteApplicabilityError(f"{name} must state a finite timestamp")
    return instant


def _validate_keyed_window(entity: Entity, instruction: Mapping[str, Any]) -> None:
    mutation = str(instruction.get("mutation"))
    bounded = mutation.endswith("Until")
    bitemporal = any(axis.dimension == "valid-time" for axis in temporal_axes(entity.runtime_facts))
    has_start = "validFrom" in instruction
    has_end = "until" in instruction
    if not bitemporal and (bounded or has_start or has_end):
        raise KeyedWriteApplicabilityError(f"{entity.name}: this target takes no Valid-Time window")
    if bitemporal and (not has_start or has_end != bounded):
        raise KeyedWriteApplicabilityError(
            f"{entity.name}: {mutation!r} requires validFrom and "
            + ("until" if bounded else "no until")
        )
    if has_start:
        start = _keyed_bound(instruction, "validFrom")
        if has_end:
            end = _keyed_bound(instruction, "until")
            if start >= end:
                raise KeyedWriteApplicabilityError(f"{entity.name}: validFrom must precede until")


def validate_keyed_write_shape(entity: Entity, instruction: Mapping[str, Any]) -> None:
    """Judge operation, window, and temporal row count before payload judgments."""
    mutation = instruction.get("mutation")
    if mutation == "delete" and entity.is_temporal:
        raise KeyedWriteApplicabilityError(f"{entity.name}: a temporal target takes no delete")
    if mutation in {"terminate", "terminateUntil"} and not entity.is_temporal:
        raise KeyedWriteApplicabilityError(
            f"{entity.name}: a non-temporal target takes no termination"
        )
    _validate_keyed_window(entity, instruction)
    rows = instruction.get("rows")
    if not isinstance(rows, list) or not entity.is_temporal or len(rows) <= 1:
        return
    mutation = instruction.get("mutation")
    raise RejectionError(
        TEMPORAL_KEYED_WRITE_MULTI_ROW,
        f"a keyed {mutation!r} on the temporal entity {entity.name!r} carries {len(rows)} rows "
        f"— a temporal keyed instruction carries exactly one (m-unit-work), since each row "
        f"closes its own milestone, settles against its own observation, and chains its own "
        f"successors; author one instruction per row",
    )


def validate_keyed_write(
    entity: Entity,
    instruction: Mapping[str, Any],
    *,
    allow_framework_markers: bool = False,
) -> None:
    """Reject *instruction* pre-SQL if inadmissible for *entity*.

    *entity* is the effective definition of the instruction's own ``entity``
    handle, so a concrete subtype inherits the root's temporality unchanged
    (`m-inheritance`). Raises :class:`RejectionError` naming the violated rule.

    This judges instruction shape and framework-owned assignment names. A caller
    also judging subtype shape and membership applies those judgments per row.
    """
    validate_keyed_write_shape(entity, instruction)
    rows = instruction.get("rows")
    if not isinstance(rows, list):
        return
    mutation = instruction.get("mutation")
    for row in rows:
        if isinstance(row, Mapping):
            validate_keyed_assignment_members(
                entity, str(mutation), row, allow_framework_markers=allow_framework_markers
            )
