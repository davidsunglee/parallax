"""Package-internal validation for compiled Parallax entity classes."""

from __future__ import annotations

from parallax.core.descriptor import Entity as EntityRecord

__all__ = ["require_entity_record"]


def require_entity_record(cls: type, record: EntityRecord | None) -> EntityRecord:
    """``record`` (``cls``'s own compiled metamodel record, already looked up
    by the caller), or a loud ``TypeError`` naming ``cls`` when absent."""
    if record is None:
        raise TypeError(f"{cls!r} is not a Parallax entity class")
    return record
