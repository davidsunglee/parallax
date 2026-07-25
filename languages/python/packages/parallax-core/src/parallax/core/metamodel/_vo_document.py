"""Structural conformance of a document to a Value Object occurrence (m-metamodel).

A write input carries a whole Value Object occurrence as one document, so
"does this value instantiate that occurrence?" is a question about accepted
Metadata alone: the occurrence's own multiplicity, its scalar leaves' declared
types and nullability, and the required-ness of each nested occurrence inside an
already-present document. That makes it a Metadata reading rather than a
behavioral policy, and it lives here because the scopes that ask it may not
import one another.

Error-neutral: :func:`vo_document_violation` returns the first structural
violation it finds, or absence for a well-formed document, and never raises.
This module owns no message text and no exception type, so each caller
classifies the violation into its own rule vocabulary and renders its own
wording.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from parallax.core.base import NeutralType, coerce_neutral_input, matches_neutral_type
from parallax.core.metamodel._states import NestedValueObjectMetadata, ValueObjectMetadata
from parallax.core.metamodel._values import Multiplicity

__all__ = ["VoDocumentViolation", "vo_document_violation"]

type _Container = ValueObjectMetadata | NestedValueObjectMetadata


@dataclass(frozen=True, slots=True)
class VoDocumentViolation:
    """A Value Object document walk's first structural violation.

    ``path`` locates the offending member relative to the walked occurrence's own
    root: ``""`` for a violation at that root — a to-many occurrence bound to a
    non-list, or a to-one occurrence bound to a non-document — a nested member
    joined with ``"."``, and a to-many element attached as ``"[index]"`` with no
    separating dot.

    ``reason`` names which of the five ways a walk can fail:

    - ``"not-a-list"`` — a to-many occurrence's own value is not a sequence
      (``str`` and ``bytes`` excluded).
    - ``"not-a-document"`` — a to-one occurrence's value, or a to-many
      occurrence's element, is not a mapping.
    - ``"attribute-missing"`` — a non-nullable scalar leaf is absent or null.
    - ``"value-object-missing"`` — a non-nullable nested occurrence is absent or
      null. A nested occurrence is required-if-declared the moment its parent
      document is present: a document binds atomically, so there is no sparse
      write below its boundary.
    - ``"type-mismatch"`` — a scalar leaf's value is neither a member of its
      declared value space nor one of the adjacent forms the developer input
      policy widens (`~parallax.core.base.coerce_neutral_input`).

    ``value`` carries the offending runtime value for the three reasons that have
    one, and ``declared_type`` the leaf's declared type for ``"type-mismatch"``
    alone — together enough for a caller to render its own wording without this
    module producing any text.
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
    declared_type: NeutralType | None = None


def vo_document_violation(container: _Container, value: object) -> VoDocumentViolation | None:
    """``value``'s first structural violation against ``container``, or absence.

    ``value`` is already present: whether an absent or null occurrence is a
    violation depends on the position it sits at, which is the caller's own
    contract. The occurrence's own multiplicity — a list of documents for
    to-many, one document for to-one — and every nested occurrence's presence
    inside an already-present document are this walk's concern.
    """
    if container.multiplicity is Multiplicity.MANY:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return VoDocumentViolation("", "not-a-list", value)
        elements = cast("Sequence[object]", value)
        for index, element in enumerate(elements):
            violation = _element_violation(container, element)
            if violation is not None:
                return _prefixed(f"[{index}]", violation)
        return None
    return _element_violation(container, value)


def _element_violation(container: _Container, value: object) -> VoDocumentViolation | None:
    if not isinstance(value, Mapping):
        return VoDocumentViolation("", "not-a-document", value)
    document = cast("Mapping[str, object]", value)
    for attribute in container.attributes:
        name = attribute.identity.name
        leaf = document.get(name)
        if name not in document or leaf is None:
            if not attribute.nullable:
                return VoDocumentViolation(name, "attribute-missing")
            continue
        if not matches_neutral_type(coerce_neutral_input(leaf, attribute.type), attribute.type):
            return VoDocumentViolation(name, "type-mismatch", leaf, attribute.type)
    for nested in container.value_objects:
        name = nested.identity.path[-1]
        nested_value = document.get(name)
        if name not in document or nested_value is None:
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
