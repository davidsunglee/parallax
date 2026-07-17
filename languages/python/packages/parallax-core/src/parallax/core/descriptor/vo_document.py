"""Shared, error-neutral value-object DOCUMENT validation (m-descriptor).

`parallax.core.unit_work.write_validate`'s own PRESENT-value-object-document
walk (a neutral keyed write row's document members, `m-value-object`
"Writing") and `parallax.core.inheritance.validate_write_assignment`'s
VO-targeted assignment-value check (a `.set(...)`-built or case-authored
predicate-write assignment, COR-3 Phase 8 confirmation-pass residual P2/P3)
both need to confirm a value-object-shaped Python value (a plain
dict/list — never a live ``ValueObject`` instance; every caller already
serializes one to its canonical document first, `parallax.core.entity.base.
_serialize_member` / `entity.expressions._serialize_assignment_value`) is a
WELL-FORMED instance of its declared composite. `m-unit-work` may depend on
`m-inheritance` but not the reverse, and NEITHER may import `m-value-object`
(`core/spec/modules.md` §7 DAG) — but both already depend on `m-descriptor`
directly, so the walk lives HERE rather than staying duplicated (mirroring
this scope's own `vo_path` precedent).

Error-neutral, mirroring `vo_path.VoPathMiss`: :func:`vo_document_violation`
returns the FIRST structural violation found (or ``None`` for a well-formed
document) and never raises — this module owns no message text and no
exception type; each caller classifies the violation into its own rule
vocabulary and renders its own message.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from parallax.core.descriptor.neutral_type import type_matches
from parallax.core.descriptor.records import NestedValueObject, ValueObject

__all__ = ["VoDocumentViolation", "vo_document_violation"]

_VoContainer = ValueObject | NestedValueObject


@dataclass(frozen=True, slots=True)
class VoDocumentViolation:
    """A value-object document walk's FIRST structural violation.

    ``path`` is the dotted/indexed member path from the WALKED container's own
    root to the offending member (``""`` for a violation AT the container's
    own top — a ``many`` container's non-list value, or a ``one`` container's
    non-mapping value); a nested value-object member prefixes with
    ``".name"``, a ``many`` element prefixes with ``"[index]"`` (bracket-
    attached, no dot) — the SAME two conventions `write_validate`'s own
    (pre-extraction) owner-string threading used, so a caller's rendered
    message stays byte-identical after delegating here.

    ``reason`` names which of the five ways a walk can fail:

    - ``"not-a-list"`` — a ``many`` container's own value is not a sequence
      (excluding ``str``/``bytes``).
    - ``"not-a-document"`` — a ``one`` container's value, or a ``many``
      container's element, is not a mapping.
    - ``"attribute-missing"`` — a non-nullable SCALAR attribute leaf is
      absent or null.
    - ``"value-object-missing"`` — a non-nullable NESTED value object is
      absent or null (a nested value object is always required-if-declared
      once its parent document is present — `m-value-object` "one atomic
      document bind", there is no sparse write below the document boundary).
    - ``"type-mismatch"`` — a scalar leaf's value does not match its
      declared `m-core` neutral type.

    ``value`` carries the OFFENDING runtime value (``"not-a-list"`` /
    ``"not-a-document"`` / ``"type-mismatch"``, ``None`` otherwise);
    ``declared_type`` carries the leaf's own declared neutral type
    (``"type-mismatch"`` only, ``None`` otherwise) — together enough for
    each caller to reconstruct its own established message wording without
    this module ever rendering text itself.
    """

    path: str
    reason: Literal[
        "not-a-list",
        "not-a-document",
        "attribute-missing",
        "value-object-missing",
        "type-mismatch",
    ]
    value: object = None
    declared_type: str | None = None


def vo_document_violation(container: _VoContainer, value: object) -> VoDocumentViolation | None:
    """The FIRST structural violation ``value`` has against ``container``'s
    declared composite — ``None`` when well-formed.

    ``value`` MUST already be present (never ``None`` — an absent/null member
    is each caller's OWN required-ness concern, since "required" varies by
    context: a keyed write row's mutation-aware sparseness for a TOP-level
    member, versus an assignment's own value always being present by
    construction); a container's OWN cardinality (``many`` -> a list of
    documents, ``one`` -> a single document) and every nested value object's
    absence/presence INSIDE an already-present document ARE this function's
    concern (`m-value-object` "one atomic document bind").
    """
    if container.cardinality == "many":
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return VoDocumentViolation("", "not-a-list", value)
        elements = cast("Sequence[object]", value)
        for index, element in enumerate(elements):
            violation = _element_violation(container, element)
            if violation is not None:
                return _prefixed(f"[{index}]", violation)
        return None
    return _element_violation(container, value)


def _element_violation(container: _VoContainer, value: object) -> VoDocumentViolation | None:
    if not isinstance(value, Mapping):
        return VoDocumentViolation("", "not-a-document", value)
    document = cast("Mapping[str, object]", value)
    for attribute in container.attributes:
        name = attribute.name
        present = name in document
        leaf = document.get(name)
        if not present or leaf is None:
            if not attribute.nullable:
                return VoDocumentViolation(name, "attribute-missing")
            continue
        if not type_matches(leaf, attribute.type):
            return VoDocumentViolation(name, "type-mismatch", leaf, attribute.type)
    for nested in container.value_objects:
        name = nested.name
        present = name in document
        nested_value = document.get(name)
        if not present or nested_value is None:
            if not nested.nullable:
                return VoDocumentViolation(name, "value-object-missing")
            continue
        violation = vo_document_violation(nested, nested_value)
        if violation is not None:
            return _prefixed(name, violation)
    return None


def _prefixed(prefix: str, violation: VoDocumentViolation) -> VoDocumentViolation:
    if not violation.path:
        path = prefix
    elif violation.path.startswith("["):
        path = f"{prefix}{violation.path}"
    else:
        path = f"{prefix}.{violation.path}"
    return VoDocumentViolation(path, violation.reason, violation.value, violation.declared_type)
