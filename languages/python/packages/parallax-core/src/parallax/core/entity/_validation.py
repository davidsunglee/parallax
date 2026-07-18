"""Package-internal entity-class validation (COR-3 Phase 7 increment 7
round-3, P3/Standards 3).

The single seam behind "is ``cls`` a compiled Parallax entity class":
:func:`~parallax.core.entity.base.metamodel`'s own entity-lookup
(``entity/base.py``) and :func:`~parallax.core.entity.meta.meta`'s
``_entity_of`` both need it, and previously each carried its own copy of the
identical ``None``-check-and-raise. Centralizing it here -- rather than
having either module import the check FROM the other -- keeps both edges
cycle-free: ``meta.py`` already imports from ``base.py`` at module level
(``entity_record_of``, among others), and ``base.py`` imports from
``statement.py`` at module level, so a NEW module-level edge from
``base.py`` back to ``meta.py`` (or vice versa) would close a cycle either
way. This module takes the ALREADY-LOOKED-UP record as a plain argument
(never :func:`~parallax.core.entity.base.entity_record_of` itself), so it
needs no import of ``base.py`` at all -- both callers do their own lookup
(each already has it in hand: ``entity_record_of`` for a class, ``meta.py``'s
``entity_registry()`` resolve for a name) and pass the result here.

A non-underscored function in an underscore-prefixed internal module (COR-3
Phase 7 increment 7 round-3, P2's own precedent): importable by both
``entity/base.py`` and ``entity/meta.py`` with no Pyright ``reportPrivateUsage``
suppression (the imported NAME carries no leading underscore -- only this
MODULE's own does), never re-exported through ``entity/__init__.py``, so it
adds no new name to the entity package's own public surface.
"""

from __future__ import annotations

from parallax.core.descriptor import Entity as EntityRecord

__all__ = ["require_entity_record"]


def require_entity_record(cls: type, record: EntityRecord | None) -> EntityRecord:
    """``record`` (``cls``'s own compiled metamodel record, already looked up
    by the caller), or a loud ``TypeError`` naming ``cls`` when the caller
    found none -- the shared validation both ``metamodel()``'s entity-lookup
    and ``meta()``'s ``_entity_of`` apply to a class argument. Each caller
    keeps its OWN error identity for a case this shared check does not cover
    (a bare canonical NAME unresolvable to any class at all, ``meta.py``'s
    own ``KeyError``) -- this centralizes only the class-in-hand validation
    the two callers previously duplicated."""
    if record is None:
        raise TypeError(f"{cls!r} is not a Parallax entity class")
    return record
