"""Model-aware keyed instruction validation (m-unit-work).

The two other write validators judge a *payload*: `write_validate` walks a
neutral write row's value-object documents, `predicate_write_validate` judges a
predicate-selected instruction's target and assignments. This one judges the
**shape and assignment names of a keyed instruction** — its `mutation` and window
against what its target's temporal profile admits, then its row's member names —
refusing ``framework-owned-member-assigned`` when an opening, amendment, or
replacement names a framework-owned member as caller authoring, and a
destructive row stating any member beside its key. Every authoring location a
keyed instruction reaches this harness through asks it here, so no lane can be
read as saying something different:

* a `scenario` step's own buffered write (:mod:`reference_harness.schema_validate`);
* the `rejected` lane's keyed `when.write`, a write-instruction document whose
  singular `row` is itself the input under test
  (:func:`~reference_harness.case_runner._validate_rejected_keyed_write`);
* a `when.writeSequence` step, whose `mutation` / `entity` / `rows` (a target
  step's `row`) state write instructions' own members even though this harness
  grades the sequence by executing its golden DML
  (:func:`~reference_harness.case_runner._assert_write_input_columns`); and
* a settled scenario write's entry, on the way to the one row the find it names
  handed over (:func:`~reference_harness.unit_work_scenario.judge._settled_row`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .case import Entity, write_entry_rows
from .inheritance import tag_of
from .value_object_resolve import RejectionError
from .write_validate import framework_owned_names, undeclared_members, window_violation

FRAMEWORK_OWNED_MEMBER_ASSIGNED = "framework-owned-member-assigned"

KEYED_WRITE_REJECTED_RULES: frozenset[str] = frozenset({FRAMEWORK_OWNED_MEMBER_ASSIGNED})

_DESTRUCTIVE_MUTATIONS = frozenset({"delete", "terminate", "terminateUntil"})


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
    unknown: set[str] = set()
    for row in write_entry_rows(instruction):
        if isinstance(row, Mapping):
            unknown |= set(undeclared_members(entity, row))
    return sorted(unknown)


def validate_keyed_assignment_members(
    entity: Entity,
    mutation: str,
    row: Mapping[str, Any],
) -> None:
    """Refuse a caller-authored framework-owned member before row values: an
    opening's, an amendment's, or a replacement's, never a destructive write's
    identity.

    Concrete-subtype metadata names are judged by the caller first.
    """
    if mutation in _DESTRUCTIVE_MUTATIONS:
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
    """A keyed operation, window, or destructive row does not fit its target."""


def validate_keyed_identity(entity: Entity, mutation: str, row: Mapping[str, Any]) -> None:
    """Refuse a destructive row stating a member beside its key: it names its
    object by that key alone (`m-unit-work`). No rule of the closed vocabulary
    names the refusal, so it is a case-authoring failure. A name *entity* does
    not declare is left to member honesty, and the flush-time
    ``observedVersion`` names no member."""
    if mutation not in _DESTRUCTIVE_MUTATIONS:
        return
    beside_key = {
        attribute["name"] for attribute in entity.attributes if not attribute.get("primaryKey")
    }
    beside_key.update(value_object["name"] for value_object in entity.value_objects)
    beside = sorted(beside_key.intersection(row))
    if beside:
        raise KeyedWriteApplicabilityError(
            f"{entity.name}: a keyed {mutation!r} names its object by its key alone, and its "
            f"row also states {beside}"
        )


def _validate_keyed_window(entity: Entity, instruction: Mapping[str, Any]) -> None:
    violation = window_violation(entity, instruction)
    if violation is not None:
        raise KeyedWriteApplicabilityError(violation)


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

    This judges instruction shape, the framework-owned assignment names, and a
    destructive row's identity of each row the entry carries: a writeSequence
    step's ``rows`` or a submission's one ``row``. A caller also judging subtype
    shape and membership, as the rejected lane does, asks
    :func:`validate_keyed_write_shape`, :func:`validate_keyed_assignment_members`,
    and :func:`validate_keyed_identity` itself around those judgments.
    """
    validate_keyed_write_shape(entity, instruction)
    mutation = str(instruction.get("mutation"))
    for row in write_entry_rows(instruction):
        if isinstance(row, Mapping):
            validate_keyed_assignment_members(entity, mutation, row)
            validate_keyed_identity(entity, mutation, row)
