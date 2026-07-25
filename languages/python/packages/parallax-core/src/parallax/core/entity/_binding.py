"""The Entity Class to Metamodel Binding association.

One module-level mapping carries every claim in the process. It is rebuilt
copy-on-write and swapped under a single lock, so a reader takes an unlocked
dictionary lookup and always sees a consistent snapshot: a hub's complete class
set becomes visible in one step, never partially. That is what lets the claim be
both the sole synchronization point of hub construction and the last step that
can fail — a constructor raising here has published nothing.

A claim is permanent for the class object's lifetime. There is no unbind, close,
reset hook, or weak-reference expiry, and no edge back to the hub module: a
runtime consumer receives the Binding, never the concrete hub.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

from parallax.core.entity._errors import (
    METAMODEL_CLASS_ALREADY_BOUND,
    MetamodelStateError,
)
from parallax.core.metamodel import EntityIdentity, Metamodel

__all__ = ["MetamodelBinding", "binding_of", "claim"]


class MetamodelBinding:
    """What one sealed class-backed hub publishes about its Entity Classes.

    It combines the opaque exact-hub identity, the sole accepted Metamodel, and
    the immutable bidirectional Entity Identity to Entity Class index. It copies
    no model fact and exposes no hub lifecycle, export, connection, or
    construction surface; the owning hub is retained privately so a bound class
    keeps its model reachable, and is never handed back.

    Hub identity is a bare sentinel compared by ``is``. That makes it
    deliberately unserializable: it is a process-local consistency check, so it
    can never leak into a serialized operation, and any future remote mode has
    to adopt an operation into the receiving hub explicitly.
    """

    __slots__ = ("_by_class", "_by_identity", "_hub_identity", "_model", "_owner")

    _hub_identity: object
    _model: Metamodel
    _by_class: Mapping[type, EntityIdentity]
    _by_identity: Mapping[EntityIdentity, type]
    _owner: object

    def __init__(
        self, *, model: Metamodel, classes: Mapping[type, EntityIdentity], owner: object
    ) -> None:
        self._hub_identity = object()
        self._model = model
        self._by_class = MappingProxyType(dict(classes))
        self._by_identity = MappingProxyType({identity: cls for cls, identity in classes.items()})
        self._owner = owner

    @property
    def hub_identity(self) -> object:
        """The opaque identity every operation node built from a bound class carries."""
        return self._hub_identity

    @property
    def claims(self) -> Sequence[tuple[type, EntityIdentity]]:
        """Every Entity Class Binding this Metamodel Binding publishes."""
        return tuple(self._by_class.items())

    @property
    def model(self) -> Metamodel:
        """The one accepted Metamodel this hub sealed."""
        return self._model

    def identity_of(self, cls: type) -> EntityIdentity | None:
        """The Entity Identity ``cls`` is bound to here, or ``None``."""
        return self._by_class.get(cls)

    def class_of(self, identity: EntityIdentity) -> type | None:
        """The Entity Class bound to ``identity`` here, or ``None``."""
        return self._by_identity.get(identity)


_CLAIM_LOCK: Final = threading.Lock()
_bindings: Mapping[type, MetamodelBinding] = MappingProxyType({})


def claim(binding: MetamodelBinding) -> None:
    """Bind every class ``binding`` indexes to it, or bind none of them.

    Raises :class:`MetamodelStateError` with
    :data:`~parallax.core.entity._errors.METAMODEL_CLASS_ALREADY_BOUND` when any
    class already belongs to another sealed hub, naming every conflicting Entity
    Identity in canonical order. Two hubs racing over a shared class therefore
    have exactly one winner, and the loser leaves the mapping untouched.
    """
    global _bindings
    with _CLAIM_LOCK:
        conflicts = sorted(
            (identity for cls, identity in binding.claims if cls in _bindings),
            key=lambda identity: identity.sort_key,
        )
        if conflicts:
            named = ", ".join(identity.canonical for identity in conflicts)
            raise MetamodelStateError(
                code=METAMODEL_CLASS_ALREADY_BOUND,
                message=(
                    f"another sealed hub already owns {named}; a class belongs to exactly "
                    "one hub for its lifetime, so a second model needs fresh class objects"
                ),
                entities=conflicts,
            )
        _bindings = MappingProxyType(
            {**_bindings, **dict.fromkeys((cls for cls, _ in binding.claims), binding)}
        )


def binding_of(cls: type) -> MetamodelBinding | None:
    """The Binding that claimed ``cls``, or ``None`` when no hub has.

    Total and nonthrowing: the caller decides which of its own rejections an
    unclaimed class deserves.
    """
    return _bindings.get(cls)
