"""A lazily-constructed, deliberately mis-annotated ``ValueObject`` field —
exercises ``value_object.py``'s own ``_attr_inner`` LIVE-annotation fallback
(python.md §2's ``Attr[...]``-only field-annotation contract: every declared
field must be ``Attr[T]``, never a bare Python type). This module avoids
``from __future__ import annotations`` so the metaclass reads the field's
LIVE (non-stringized) annotation object directly — mirroring how
``value_object_models.py`` / ``snapshot_models.py`` themselves avoid it. The
offending class is built lazily (inside a function, never at module import
time) so importing this module never raises.
"""

from parallax.core.entity.value_object import ValueObject


def build_non_attr_annotated_value_object() -> type[ValueObject]:
    class BadAnnotation(ValueObject, frozen=True):
        plain: int

    return BadAnnotation
