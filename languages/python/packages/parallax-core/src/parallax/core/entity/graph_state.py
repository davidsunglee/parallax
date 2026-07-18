"""Closed-world relationship load-state introspection (spec §3).

``is_loaded`` / ``narrowed`` read the frozen-node wrapping the snapshot
materializer attaches (``parallax.snapshot.wrap``, COR-3 Phase 7 increment
6a): a PLAIN relationship name checks the ``Rel[T]`` descriptor's own
per-instance storage (the ``UNLOADED`` sentinel vs. a loaded value); a
NARROWED-view request — a :class:`~parallax.core.entity.expressions.RelationshipPath`
carrying a ``.narrow(...)`` hop — checks the node's own private narrowed-view
mapping instead, keyed by the SAME derived view key
(``rel[Concrete,…]``, the RESOLVED effective concrete-subtype set, never the
authored subtype names verbatim) ``m-deep-fetch``'s own view-key derivation
produces — resolved via the shared ``resolve_narrow_position`` seam
(``parallax.core.inheritance``) the identical way, so the two can never
drift (COR-3 Phase 7 increment 7 round-3, P2).
"""

from __future__ import annotations

from parallax.core.entity.base import metamodel, registry_of, wire_names_of
from parallax.core.entity.expressions import (
    UNLOADED,
    RelationshipPath,
    UnloadedRelationshipError,
)
from parallax.core.inheritance._position import resolve_narrow_position

__all__ = ["is_loaded", "narrowed"]

_NARROWED_ATTR = "__parallax_narrowed__"


def _view_key(node: object, path: str | RelationshipPath) -> str:
    """The relationship-name-or-narrowed-view key ``path`` names: a bare
    string passes through unchanged; a :class:`RelationshipPath` derives it
    from its own LAST segment. A narrowed hop's view key is keyed by the
    RESOLVED effective concrete-subtype set, never the authored names
    (mirrors ``m-deep-fetch``'s own ``_resolve_position`` so the two can
    never drift, via the shared ``resolve_narrow_position`` seam, COR-3
    Phase 7 increment 7 round-3): resolved within ``node``'s OWN D-20
    registration scope (:func:`~parallax.core.entity.base.metamodel` /
    :func:`~parallax.core.entity.base.registry_of` over ``type(node)`` --
    the SAME already-public bridge :func:`~parallax.core.entity.meta.meta`
    composes, ledger D-20), never a private reach into ``path``'s own
    captured registry (``RelationshipPath`` gains nothing public for this)."""
    if isinstance(path, str):
        return path
    last = path.segments[-1]
    _, _, rel_local = last.rel.partition(".")
    if not last.narrow:
        return rel_local
    registry = registry_of(metamodel([type(node)]))
    position = resolve_narrow_position(registry.metamodel(), last.narrow)
    return f"{rel_local}[{','.join(position)}]"


def is_loaded(node: object, path: str | RelationshipPath) -> bool:
    """Whether ``node``'s relationship (or narrowed view) ``path`` names was
    included by the find that produced it — never raises, never issues SQL
    (spec §3)."""
    key = _view_key(node, path)
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
    """The narrowed view ``path`` names (spec §3): a to-many hop's own
    ``tuple``, or the related node / ``None`` for a to-one narrowed view.
    Raises :class:`~parallax.core.entity.expressions.UnloadedRelationshipError`
    naming the derived view key when ``path`` was not requested by the read
    that produced ``node``."""
    key = _view_key(node, path)
    views = getattr(node, _NARROWED_ATTR, {})
    if key not in views:
        raise UnloadedRelationshipError(key)
    return views[key]
