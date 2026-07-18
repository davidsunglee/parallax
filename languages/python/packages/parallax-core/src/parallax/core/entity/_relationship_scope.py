"""Package-internal ``RelationshipPath`` scope registration (COR-3 Phase 7
increment 7 round-4, P2 regression fix).

``RelationshipPath._registry`` is a class-private field: Pyright's
``reportPrivateUsage`` flags reading it from anywhere outside
:class:`~parallax.core.entity.expressions.RelationshipPath`'s own method
bodies — even a same-file free function (confirmed the hard way in round 3,
the reason ``graph_state._view_key`` briefly derived scope from
``type(node)`` instead). The round-4 review proved that derivation a
behavioral regression: a multi-hop path's captured registry (the FIRST hop's
own, propagated unchanged through every later hop by
``RelationshipPath.__getattr__`` / ``.narrow()``) is AUTHORITATIVE, and can
resolve a WIDER effective concrete-subtype set than the node's own,
independent D-20 registration registry.

The seam: ``RelationshipPath.__post_init__`` (in-class, so touching
``self._registry`` draws no flag) hands its own captured scope to
:func:`register_scope`; :func:`scope_of` reads it back — keyed by the path
OBJECT'S OWN IDENTITY, never ``RelationshipPath.__eq__``/``__hash__`` (two
structurally identical paths built under two DIFFERENT registries must never
collide, the way a ``WeakKeyDictionary`` keyed by the dataclass's own value
equality would let them). ``id(path)`` doubles as the key, with a
:func:`weakref.finalize` callback removing the entry the moment ``path`` is
garbage-collected — an entry can never outlive, and its slot can never be
reused before, the ``RelationshipPath`` it describes is actually collected
(``RelationshipPath`` opts into ``weakref_slot=True`` for exactly this).

A non-underscored function in an underscore-prefixed internal module
(``inheritance/_position.py``'s own precedent, COR-3 Phase 7 increment 7
round-3): Pyright's ``reportPrivateUsage`` does not flag a symbol with no
leading underscore imported from an ``_module`` — only this MODULE's own
leading underscore keeps it out of :mod:`parallax.core.entity`'s public
surface (never re-exported through that package's ``__init__.py``). Both
type references below are ``TYPE_CHECKING``-only: this module needs neither
:class:`~parallax.core.entity.expressions.RelationshipPath` nor
:class:`~parallax.core.entity.base.EntityRegistry` at runtime (only ``id()``
and structural typing), so it carries no runtime import edge to either —
nothing for an import-linter contract to say anything about.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from weakref import finalize

if TYPE_CHECKING:
    from parallax.core.entity.base import EntityRegistry
    from parallax.core.entity.expressions import RelationshipPath

__all__ = ["register_scope", "scope_of"]

_SCOPES: dict[int, EntityRegistry] = {}


def register_scope(path: RelationshipPath, registry: EntityRegistry | None) -> None:
    """Record ``path``'s own captured D-20 registration scope. ``registry``
    is ``None`` for a ``RelationshipPath`` built outside ``Rel.__get__``
    (test-only direct construction, no ``_registry=`` supplied) — registers
    nothing, so :func:`scope_of` correctly reports it unregistered and the
    caller falls back the SAME way ``path``'s own resolution already does."""
    if registry is None:
        return
    key = id(path)
    _SCOPES[key] = registry
    finalize(path, _SCOPES.pop, key, None)


def scope_of(path: RelationshipPath) -> EntityRegistry | None:
    """The registry ``path`` registered at construction, or ``None`` if it
    never captured one (never a ``KeyError`` — ``dict.get``'s own default)."""
    return _SCOPES.get(id(path))
