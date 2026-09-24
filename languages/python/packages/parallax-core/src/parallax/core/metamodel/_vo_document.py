from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from parallax.core.base import NeutralType

__all__ = ["VoDocumentViolation"]


@dataclass(frozen=True, slots=True)
class VoDocumentViolation:
    """A shared authoring traversal's first structural violation.

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
    - ``"value-object-missing"`` — a non-nullable nested ``one`` occurrence is
      absent or null, or a nested ``many`` occurrence is present as an explicit
      null. A nested ``one`` is required-if-declared the moment its parent
      document is present: a document binds atomically, so there is no sparse
      write below its boundary. An **absent** ``many`` is not a violation —
      absence and the empty array are one logical zero state, so an unnamed
      ``many`` occurrence is the empty collection rather than a missing member.
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
