"""Closed-world relationship load-state introspection (spec §3).

``is_loaded`` / ``narrowed`` read the frozen node the snapshot materializer
produced: a plain relationship name checks the relationship descriptor's own
per-instance storage (the ``UNLOADED`` sentinel versus a loaded value), while a
narrowed-view request — a relationship path carrying a ``.narrow(...)`` hop —
checks the node's private narrowed-view mapping instead, keyed by the same
derived view key deep fetch produced when it planned the read.
"""

from __future__ import annotations

from parallax.core.entity._entity import wire_names_of
from parallax.core.entity._errors import UnloadedRelationshipError
from parallax.core.entity._expressions import UNLOADED, RelationshipPath

__all__ = ["is_loaded", "narrowed"]

_NARROWED_ATTR = "__parallax_narrowed__"


def _view_key(path: str | RelationshipPath) -> str:
    """The relationship-name-or-narrowed-view key ``path`` names.

    A bare string passes through unchanged; a relationship path derives its key
    from its own last segment, and a narrowed hop appends the effective
    concrete-subtype set the read keyed the view by.
    """
    if isinstance(path, str):
        return path
    last = path.segments[-1]
    _, _, rel_local = last.rel.rpartition(".")
    if not last.narrow:
        return rel_local
    return f"{rel_local}[{','.join(sorted(last.narrow))}]"


def is_loaded(node: object, path: str | RelationshipPath) -> bool:
    """Whether ``node``'s relationship (or narrowed view) ``path`` names was
    included by the find that produced it — never raises, never issues SQL
    (spec §3)."""
    key = _view_key(path)
    if "[" in key:
        views = getattr(node, _NARROWED_ATTR, {})
        return key in views
    names = wire_names_of(type(node))
    py_name = names.relationship_py.get(key)
    if py_name is None:
        return False
    value = node.__dict__.get(py_name, UNLOADED)
    return value is not UNLOADED


def narrowed(node: object, path: str | RelationshipPath) -> object:
    """The narrowed view ``path`` names (spec §3): a to-many hop's own tuple, or
    the related node / ``None`` for a to-one narrowed view. Raises
    :class:`~parallax.core.entity._errors.UnloadedRelationshipError` naming the
    derived view key when ``path`` was not requested by the read that produced
    ``node``."""
    key = _view_key(path)
    views = getattr(node, _NARROWED_ATTR, {})
    if key not in views:
        raise UnloadedRelationshipError(key)
    return views[key]
