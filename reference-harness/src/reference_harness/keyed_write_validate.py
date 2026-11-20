"""Model-aware keyed instruction validation (m-unit-work).

The two other write validators judge a *payload*: `write_validate` walks a
neutral write row's value-object documents, `predicate_write_validate` judges a
predicate-selected instruction's target and assignments. This one judges the
**shape and assignment names of a keyed instruction** — its `mutation` and window
against what its target's temporal profile admits, then its row's member names —
refusing ``framework-owned-member-assigned`` when an amendment or replacement
names a framework-owned member as a caller assignment. Every authoring location a
keyed instruction reaches this harness through asks it here, so no lane can be
read as saying something different:

* a `scenario` step's own buffered write (:mod:`reference_harness.schema_validate`);
* the `rejected` lane's keyed `when.write`, a write-instruction document whose
  singular `row` is itself the input under test
  (:func:`~reference_harness.case_runner._validate_rejected_keyed_write`);
* a `when.writeSequence` step, whose `mutation` / `entity` / `rows` state keyed
  instructions' own members even though this harness grades the sequence by
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

FRAMEWORK_OWNED_MEMBER_ASSIGNED = "framework-owned-member-assigned"

KEYED_WRITE_REJECTED_RULES: frozenset[str] = frozenset({FRAMEWORK_OWNED_MEMBER_ASSIGNED})


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


def validate_keyed_assignment_members(
    entity: Entity,
    mutation: str,
    row: Mapping[str, Any],
) -> None:
    """Refuse caller assignments to framework-owned members before row values.

    Concrete-subtype metadata names are judged by the caller first.
    """
    if mutation not in {"amend", "amendUntil", "replace", "replaceUntil"}:
        return
    owned = framework_owned_names(entity)
    tag = tag_of(entity.runtime_facts)
    if tag is not None:
        owned -= {tag[0]}
    for name in row:
        if name in owned:
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
    """Judge operation and window before payload judgments."""
    mutation = instruction.get("mutation")
    if mutation == "delete" and entity.is_temporal:
        raise KeyedWriteApplicabilityError(f"{entity.name}: a temporal target takes no delete")
    if mutation in {"terminate", "terminateUntil"} and not entity.is_temporal:
        raise KeyedWriteApplicabilityError(
            f"{entity.name}: a non-temporal target takes no termination"
        )
    _validate_keyed_window(entity, instruction)


def validate_keyed_write(
    entity: Entity,
    instruction: Mapping[str, Any],
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
            validate_keyed_assignment_members(entity, str(mutation), row)
