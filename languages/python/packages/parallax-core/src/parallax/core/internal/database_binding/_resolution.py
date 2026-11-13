from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from parallax.core.internal.database_binding._authored import DatabaseBinding, DatabaseLocation
from parallax.core.internal.database_binding._errors import (
    BINDING_RESOLUTION_REJECTED,
    BindingError,
    BindingIssue,
    BindingPath,
)
from parallax.core.internal.database_binding._physical import (
    PhysicalSequence,
    PhysicalTable,
    ResolvedTable,
    ResolvedTemporalConstraints,
)
from parallax.core.internal.dialect import Dialect
from parallax.core.internal.metamodel import EntityIdentity, Metamodel, PrimaryKey, Sequence
from parallax.core.internal.storage_layout import (
    TableLayout,
    storage_layout_facet_of,
    temporal_constraint_names,
)

__all__ = [
    "BINDING_ENTITY_OWNS_NO_TABLE",
    "BINDING_ENTITY_UNKNOWN",
    "BINDING_NAMESPACE_UNKNOWN",
    "BINDING_SEQUENCE_COLLISION",
    "BINDING_SEQUENCE_TABLE_COLLISION",
    "BINDING_SEQUENCE_UNKNOWN",
    "BINDING_SEQUENCE_UNRESOLVED",
    "BINDING_TABLE_COLLISION",
    "BINDING_TABLE_UNRESOLVED",
    "resolve",
]

BINDING_ENTITY_UNKNOWN: Final = "binding-entity-unknown"
"""An ``entities`` key names no Entity the model declares."""
BINDING_ENTITY_OWNS_NO_TABLE: Final = "binding-entity-owns-no-table"
"""An ``entities`` key names an Entity that is no mapping owner, such as a
table-per-hierarchy descendant."""
BINDING_NAMESPACE_UNKNOWN: Final = "binding-namespace-unknown"
"""A ``namespaces`` key names no Entity Namespace the model declares an Entity in."""
BINDING_SEQUENCE_UNKNOWN: Final = "binding-sequence-unknown"
"""A ``sequences`` key names no logical allocator the model declares."""
BINDING_TABLE_UNRESOLVED: Final = "binding-table-unresolved"
"""No entry supplies a mapping owner's location."""
BINDING_SEQUENCE_UNRESOLVED: Final = "binding-sequence-unresolved"
"""No entry supplies a logical allocator's location."""
BINDING_TABLE_COLLISION: Final = "binding-table-collision"
"""Two mapping owners resolve to one physical table."""
BINDING_SEQUENCE_COLLISION: Final = "binding-sequence-collision"
"""Two logical allocators resolve to one physical sequence."""
BINDING_SEQUENCE_TABLE_COLLISION: Final = "binding-sequence-table-collision"
"""A physical sequence and a physical table share one name in one location."""

_IDENTIFIER_INVALID: Final = "binding-identifier-invalid"


def _logical_allocators(model: Metamodel) -> tuple[str, ...]:
    """Every logical allocator key ``model`` declares, once each, in codepoint order.

    Equal keys name one shared allocator, and a family's key is declared by its
    root alone, so each key appears once however many Entities draw from it.
    """
    return tuple(
        sorted(
            {
                key.generation.name
                for entity in model.entities
                for attribute in entity.declared_attributes
                if isinstance(key := attribute.primary_key, PrimaryKey)
                and isinstance(key.generation, Sequence)
            }
        )
    )


def _owner_path(owner: EntityIdentity) -> BindingPath:
    return ("entities", owner.canonical)


def _sequence_path(allocator: str) -> BindingPath:
    return ("sequences", allocator)


class _Resolver:
    __slots__ = ("binding", "dialect", "issues")

    def __init__(self, binding: DatabaseBinding) -> None:
        self.binding = binding
        self.dialect: Dialect = binding.dialect
        self.issues: list[BindingIssue] = []

    def issue(
        self, code: str, path: BindingPath, message: str, related: tuple[BindingPath, ...] = ()
    ) -> None:
        self.issues.append(BindingIssue(code, path, related, message=message))

    def components(self, components: tuple[str, ...], path: BindingPath) -> bool:
        valid = True
        for component in components:
            problem = self.dialect.identifier_issue(component)
            if problem is not None:
                self.issue(_IDENTIFIER_INVALID, path, f"{component!r}: {problem}")
                valid = False
        return valid

    def keys(
        self,
        meta: Metamodel,
        owners: Mapping[EntityIdentity, TableLayout],
        allocators: frozenset[str],
    ) -> None:
        for owner in self.binding.entities:
            if meta.entity(owner) is None:
                self.issue(
                    BINDING_ENTITY_UNKNOWN, _owner_path(owner), "the model declares no such Entity"
                )
            elif owner not in owners:
                self.issue(
                    BINDING_ENTITY_OWNS_NO_TABLE,
                    _owner_path(owner),
                    "this Entity owns no table; its family's mapping owner does",
                )
        declared = {entity.identity.namespace for entity in meta.entities}
        for namespace in self.binding.namespaces:
            if namespace not in declared:
                self.issue(
                    BINDING_NAMESPACE_UNKNOWN,
                    ("namespaces", namespace),
                    "the model declares no Entity in this namespace",
                )
        for allocator in self.binding.sequences:
            if allocator not in allocators:
                self.issue(
                    BINDING_SEQUENCE_UNKNOWN,
                    _sequence_path(allocator),
                    "the model declares no such logical allocator",
                )

    def tables(
        self, owners: Mapping[EntityIdentity, TableLayout]
    ) -> dict[EntityIdentity, ResolvedTable]:
        tables: dict[EntityIdentity, ResolvedTable] = {}
        by_table: dict[PhysicalTable, EntityIdentity] = {}
        for owner in sorted(owners, key=lambda identity: identity.sort_key):
            resolved = self.table(owner, owners[owner])
            if resolved is None:
                continue
            tables[owner] = resolved
            first = by_table.setdefault(resolved.physical, owner)
            if first != owner:
                self.issue(
                    BINDING_TABLE_COLLISION,
                    _owner_path(owner),
                    f"resolves to the physical table {first.canonical} already holds",
                    (_owner_path(first),),
                )
        return tables

    def sequences(
        self, allocators: tuple[str, ...], tables: Mapping[EntityIdentity, ResolvedTable]
    ) -> dict[str, PhysicalSequence]:
        relations = {table.physical: owner for owner, table in tables.items()}
        sequences: dict[str, PhysicalSequence] = {}
        by_sequence: dict[PhysicalSequence, str] = {}
        for allocator in allocators:
            physical = self.sequence(allocator)
            if physical is None:
                continue
            sequences[allocator] = physical
            first = by_sequence.setdefault(physical, allocator)
            if first != allocator:
                self.issue(
                    BINDING_SEQUENCE_COLLISION,
                    _sequence_path(allocator),
                    f"resolves to the physical sequence allocator {first!r} already uses",
                    (_sequence_path(first),),
                )
            clash = relations.get(PhysicalTable(physical.qualifier, physical.name))
            if clash is not None:
                self.issue(
                    BINDING_SEQUENCE_TABLE_COLLISION,
                    _sequence_path(allocator),
                    f"names the relation {clash.canonical}'s table already holds",
                    (_owner_path(clash),),
                )
        return sequences

    def location(self, owner: EntityIdentity) -> tuple[DatabaseLocation, BindingPath] | None:
        entry = self.binding.entities.get(owner)
        if entry is not None and entry.location is not None:
            return entry.location, _owner_path(owner)
        namespace = owner.namespace
        if namespace is not None and (found := self.binding.namespaces.get(namespace)) is not None:
            return found, ("namespaces", namespace)
        if self.binding.default is not None:
            return self.binding.default, ("default",)
        return None

    def table(self, owner: EntityIdentity, layout: TableLayout) -> ResolvedTable | None:
        located = self.location(owner)
        if located is None:
            self.issue(
                BINDING_TABLE_UNRESOLVED,
                _owner_path(owner),
                "no entry, namespace, or default supplies this table's location",
            )
            return None
        location, location_path = located
        entry = self.binding.entities.get(owner)
        name = layout.table.name if entry is None or entry.name is None else entry.name
        qualifier = location.qualifier
        valid = self.components(qualifier, location_path)
        valid = self.components((name,), (*_owner_path(owner), "table")) and valid
        if not valid:
            return None
        physical = PhysicalTable(qualifier, name)
        definition = layout.temporal_constraints
        constraints = None
        if definition is not None:
            names = temporal_constraint_names(name, definition)
            constraints = ResolvedTemporalConstraints(
                definition=definition,
                primary_key_name=names.primary_key,
                transaction_check_name=names.transaction_check,
                valid_check_name=names.valid_check,
                exclusion_name=names.exclusion,
            )
        return ResolvedTable(
            mapping_owner=owner,
            physical=physical,
            sql=self.dialect.render_table(physical),
            layout=layout,
            temporal_constraints=constraints,
        )

    def sequence(self, allocator: str) -> PhysicalSequence | None:
        entry = self.binding.sequences.get(allocator)
        if entry is not None and entry.location is not None:
            location, location_path = entry.location, _sequence_path(allocator)
        elif self.binding.default is not None:
            location, location_path = self.binding.default, ("default",)
        else:
            self.issue(
                BINDING_SEQUENCE_UNRESOLVED,
                _sequence_path(allocator),
                "no entry or default supplies this sequence's location",
            )
            return None
        name = allocator if entry is None or entry.name is None else entry.name
        valid = self.components(location.qualifier, location_path)
        valid = self.components((name,), (*_sequence_path(allocator), "sequence")) and valid
        return PhysicalSequence(location.qualifier, name) if valid else None


def resolve(
    meta: Metamodel, binding: DatabaseBinding
) -> tuple[Mapping[EntityIdentity, ResolvedTable], Mapping[str, PhysicalSequence]]:
    """Every mapping owner's table and every allocator's sequence ``binding`` places.

    Raises :class:`BindingError` with every resolution issue at once.
    """
    resolver = _Resolver(binding)
    owners = {layout.mapping_owner: layout for layout in storage_layout_facet_of(meta).tables}
    allocators = _logical_allocators(meta)
    resolver.keys(meta, owners, frozenset(allocators))
    tables = resolver.tables(owners)
    sequences = resolver.sequences(allocators, tables)
    if resolver.issues:
        raise BindingError(BINDING_RESOLUTION_REJECTED, resolver.issues)
    return MappingProxyType(tables), MappingProxyType(sequences)
