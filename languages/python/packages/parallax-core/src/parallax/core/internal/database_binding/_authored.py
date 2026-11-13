from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from parallax.core.internal.dialect import Dialect
from parallax.core.internal.metamodel import EntityIdentity

__all__ = ["DatabaseBinding", "DatabaseLocation", "DatabaseSequence", "DatabaseTable"]


class DatabaseLocation(Protocol):
    """Where a backend keeps tables and sequences, as its qualifier components."""

    @property
    def qualifier(self) -> tuple[str, ...]: ...


class DatabaseTable(Protocol):
    """A binding's partial override for one mapping owner's table.

    An absent location or name leaves that part to the binding's defaults and
    the model's declared storage name.
    """

    @property
    def location(self) -> DatabaseLocation | None: ...
    @property
    def name(self) -> str | None: ...


class DatabaseSequence(Protocol):
    """A binding's partial override for one logical allocator's sequence."""

    @property
    def location(self) -> DatabaseLocation | None: ...
    @property
    def name(self) -> str | None: ...


class DatabaseBinding(Protocol):
    """One deployment's physical placement, independent of any model.

    ``namespaces`` is keyed by exact Entity Namespace, ``entities`` by exact
    mapping-owner identity, and ``sequences`` by logical allocator key.
    """

    @property
    def dialect(self) -> Dialect: ...
    @property
    def default(self) -> DatabaseLocation | None: ...
    @property
    def namespaces(self) -> Mapping[str, DatabaseLocation]: ...
    @property
    def entities(self) -> Mapping[EntityIdentity, DatabaseTable]: ...
    @property
    def sequences(self) -> Mapping[str, DatabaseSequence]: ...
