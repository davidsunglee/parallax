"""Closed-world relationship load-state introspection (spec §3).

``is_loaded`` / ``narrowed`` read the frozen-node wrapping the snapshot
materializer attaches (``parallax.snapshot.handle``): a PLAIN relationship
name checks the ``Rel[T]`` descriptor's own
per-instance storage (the ``UNLOADED`` sentinel vs. a loaded value); a
NARROWED-view request — a :class:`~parallax.core.entity.expressions.RelationshipPath`
carrying a ``.narrow(...)`` hop — checks the node's own private narrowed-view
mapping instead, keyed by the SAME derived view key
(``rel[Concrete,…]``, the RESOLVED effective concrete-subtype set, never the
authored subtype names verbatim) ``m-deep-fetch``'s own view-key derivation
produces — resolved through the Inheritance Facet's ``position(...)`` the
identical way, so the two can never drift.
"""

from __future__ import annotations

from parallax.core import inheritance
from parallax.core.descriptor import Metamodel as MetamodelRecord
from parallax.core.entity.base import (
    EntityRegistry,
    default_registry,
    resolve_entity_metadata,
    wire_names_of,
)
from parallax.core.entity.expressions import (
    UNLOADED,
    RelationshipPath,
    UnloadedRelationshipError,
)
from parallax.core.model_formation import MetamodelValidationError

__all__ = ["is_loaded", "narrowed"]


def _narrow_position(registry: EntityRegistry, names: tuple[str, ...]) -> tuple[str, ...]:
    """The resolved effective concrete-subtype set of an authored narrow within
    ``registry``'s scope, through the Inheritance Facet.

    A registry chain that merges an unsatisfiable Entity (a shadowed name that
    leaves a sibling's reverse relationship dangling) cannot form the accepted
    model the facet needs; the narrow position depends only on the inheritance
    family, which the descriptor family walk resolves without forming
    references, so it is the fallback for that pathological chain."""
    try:
        model = registry.metamodel()
    except MetamodelValidationError:
        records = MetamodelRecord(entities=tuple(registry.records().values()))
        resolved: set[str] = set()
        for name in names:
            resolved.update(inheritance.effective_concrete_subtypes(records, name))
        return tuple(sorted(resolved))
    members = [
        metadata.identity
        for name in names
        if (metadata := resolve_entity_metadata(model, name)) is not None
    ]
    position = inheritance.view(model).position(members)
    if position is None:
        return ()
    return tuple(identity.name for identity in position.concrete_subtypes)


_NARROWED_ATTR = "__parallax_narrowed__"


def _view_key(path: str | RelationshipPath) -> str:
    """The relationship-name-or-narrowed-view key ``path`` names: a bare
    string passes through unchanged; a :class:`RelationshipPath` derives it
    from its own LAST segment. A narrowed hop's view key is keyed by the
    RESOLVED effective concrete-subtype set, never the authored names
    (mirrors ``m-deep-fetch``'s own ``_resolve_position`` so the two can
    never drift, through the Inheritance Facet's ``position(...)``): resolved
    within ``path``'s OWN captured registration scope — read directly off
    ``path.__parallax_registry__`` (an intrinsic dunder-named field,
    never a side table keyed by identity), never the checked node's own
    class. A multi-hop path propagates its FIRST hop's registry through
    every later hop unchanged (``RelationshipPath.__getattr__`` /
    ``.narrow()``), so ``path``'s own scope can resolve a WIDER effective
    concrete-subtype set than the node's own, independent registration
    registry would — deriving from the node's own class instead would
    compute the narrower set and silently under-report load state; the
    path's own scope is authoritative, exactly the scope ``m-deep-fetch``'s
    own planning resolved the SAME position within when it built the node's
    wire key in the first place. ``None`` (a ``RelationshipPath`` built
    outside ``Rel.__get__`` — test-only direct construction, or any copy/
    deepcopy/unpickle of one) falls back to the process default registry,
    mirroring ``RelationshipPath``'s own fallback."""
    if isinstance(path, str):
        return path
    last = path.segments[-1]
    _, _, rel_local = last.rel.rpartition(".")
    if not last.narrow:
        return rel_local
    registry = path.__parallax_registry__
    if registry is None:
        registry = default_registry()
    concretes = _narrow_position(registry, last.narrow)
    return f"{rel_local}[{','.join(concretes)}]"


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
    """The narrowed view ``path`` names (spec §3): a to-many hop's own
    ``tuple``, or the related node / ``None`` for a to-one narrowed view.
    Raises :class:`~parallax.core.entity.expressions.UnloadedRelationshipError`
    naming the derived view key when ``path`` was not requested by the read
    that produced ``node``."""
    key = _view_key(path)
    views = getattr(node, _NARROWED_ATTR, {})
    if key not in views:
        raise UnloadedRelationshipError(key)
    return views[key]
