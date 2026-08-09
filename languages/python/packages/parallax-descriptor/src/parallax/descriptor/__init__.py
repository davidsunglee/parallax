"""``parallax.descriptor`` — the optional Descriptor Frontend (m-descriptor).

Three doors create a descriptor-backed :class:`~parallax.core.DomainModel` from
a canonical model descriptor — an already-decoded document, JSON text, or YAML
text — and three export a class-backed or descriptor-backed hub back to that
canonical form. A seventh door classifies the inheritance-family defects that
keep a document from forming at all, which the six above can only report as a
refusal to build a model. The record vocabulary, the canonical-schema machinery,
serde, type-spelling conversion, and the Unresolved Metamodel adaptation stay
private: a descriptor document is the interchange surface, not the records behind
it.

The seven error types below are the frontend's whole failure vocabulary, none of
them re-exported from ``parallax.core``. ``m-descriptor`` reaches the common
runtime through ``m-core``, ``m-metamodel``, and — for the family rule
vocabulary alone — ``m-inheritance``; the private ``parallax.descriptor._hub``
child scope alone reaches the Hub-construction seam.
"""

from __future__ import annotations

from parallax.descriptor._errors import (
    DescriptorError,
    DescriptorSchemaError,
    DescriptorSchemaViolation,
    DescriptorSyntaxError,
    DescriptorValueError,
    DescriptorValueViolation,
)
from parallax.descriptor._export import DescriptorExportError
from parallax.descriptor._family import validate_inheritance_families
from parallax.descriptor._hub import (
    export_document,
    export_json,
    export_yaml,
    hub_from_document,
    hub_from_json,
    hub_from_yaml,
)

__all__ = [
    "DescriptorError",
    "DescriptorExportError",
    "DescriptorSchemaError",
    "DescriptorSchemaViolation",
    "DescriptorSyntaxError",
    "DescriptorValueError",
    "DescriptorValueViolation",
    "export_document",
    "export_json",
    "export_yaml",
    "hub_from_document",
    "hub_from_json",
    "hub_from_yaml",
    "validate_inheritance_families",
]
