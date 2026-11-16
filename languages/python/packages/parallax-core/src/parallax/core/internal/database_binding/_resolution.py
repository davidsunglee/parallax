from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from parallax.core.internal.base import Int32, Int64, integer_bounds
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
    ResolvedDocumentRootConstraint,
    ResolvedSequence,
    ResolvedTable,
    ResolvedTemporalConstraints,
)
from parallax.core.internal.dialect import Dialect
from parallax.core.internal.inheritance import inheritance_facet_of
from parallax.core.internal.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    KeySequence,
    Metamodel,
    PrimaryKey,
    Sequence,
)
from parallax.core.internal.storage_layout import (
    TableLayout,
    document_root_check_name,
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
    "BINDING_SEQUENCE_UNREPRESENTABLE",
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
BINDING_SEQUENCE_UNREPRESENTABLE: Final = "binding-sequence-unrepresentable"
"""The binding's backend cannot hold a native allocator's declared settings: it
has no native sequence, its physical step exceeds the key range, or its initial
value lies outside it."""

_IDENTIFIER_INVALID: Final = "binding-identifier-invalid"


type _Declared = tuple[Sequence | KeySequence, AttributeMetadata]


def _logical_allocators(model: Metamodel) -> Mapping[str, _Declared]:
    """Every logical allocator key ``model`` declares, once each, in codepoint
    order, beside the first declaration of it and the key Attribute declaring it.

    Equal keys name one shared allocator, and a family's key is declared by its
    root alone, so each key appears once however many Entities draw from it.
    Formation has already refused declarations of one key that disagree.
    """
    declared: dict[str, _Declared] = {}
    for entity in sorted(model.entities, key=lambda entity: entity.identity.sort_key):
        for attribute in entity.declared_attributes:
            key = attribute.primary_key
            if isinstance(key, PrimaryKey) and isinstance(key.generation, Sequence | KeySequence):
                declared.setdefault(key.generation.name, (key.generation, attribute))
    return {allocator: declared[allocator] for allocator in sorted(declared)}


def _consumers(
    model: Metamodel, tables: Mapping[EntityIdentity, ResolvedTable]
) -> Mapping[str, tuple[ResolvedTable, ...]]:
    """Each allocator's consuming tables: every resolved table whose family key
    it generates, in canonical owner order."""
    families = inheritance_facet_of(model)
    consumers: dict[str, list[ResolvedTable]] = {}
    for owner, table in tables.items():
        view = families.entity(owner)
        key = None if view is None else view.primary_key.primary_key
        if isinstance(key, PrimaryKey) and isinstance(key.generation, KeySequence):
            consumers.setdefault(key.generation.name, []).append(table)
    return {allocator: tuple(held) for allocator, held in consumers.items()}


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
        self,
        allocators: Mapping[str, _Declared],
        tables: Mapping[EntityIdentity, ResolvedTable],
        consumers: Mapping[str, tuple[ResolvedTable, ...]],
    ) -> dict[str, PhysicalSequence | ResolvedSequence]:
        relations = {table.physical: owner for owner, table in tables.items()}
        sequences: dict[str, PhysicalSequence | ResolvedSequence] = {}
        by_sequence: dict[PhysicalSequence, str] = {}
        for allocator, (generation, attribute) in allocators.items():
            physical = self.sequence(allocator)
            if physical is None:
                continue
            if isinstance(generation, KeySequence):
                resolved = self.native(
                    allocator, physical, generation, attribute, consumers.get(allocator, ())
                )
                if resolved is not None:
                    sequences[allocator] = resolved
            else:
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

    def native(
        self,
        allocator: str,
        physical: PhysicalSequence,
        declaration: KeySequence,
        attribute: AttributeMetadata,
        consumers: tuple[ResolvedTable, ...],
    ) -> ResolvedSequence | None:
        """``allocator`` as the native sequence ``physical`` holds, or ``None``
        having reported why this backend cannot represent its settings."""
        provider = self.dialect.sequence_bounds
        if provider is None:
            self.issue(
                BINDING_SEQUENCE_UNREPRESENTABLE,
                _sequence_path(allocator),
                f"the {self.dialect.name} backend has no native sequence to allocate keys from",
            )
            return None
        key_type = attribute.type
        assert isinstance(key_type, Int32 | Int64)  # metadata admits no other generated key
        type_low, type_high = integer_bounds(key_type)
        low, high = max(type_low, provider[0]), min(type_high, provider[1])
        step = declaration.batch_size * declaration.increment_size
        problems: list[str] = []
        if step > provider[1] or step > high - low:
            problems.append(
                f"its physical increment, batch size {declaration.batch_size} times increment "
                f"size {declaration.increment_size}, is {step}, which a sequence over "
                f"[{low}, {high}] cannot step by"
            )
        if not low <= declaration.initial_value <= high:
            problems.append(
                f"its initial value {declaration.initial_value} lies outside the key range "
                f"[{low}, {high}]"
            )
        if problems:
            self.issue(
                BINDING_SEQUENCE_UNREPRESENTABLE, _sequence_path(allocator), "; ".join(problems)
            )
            return None
        return ResolvedSequence(
            allocator=allocator,
            physical=physical,
            sql=self.dialect.render_table(physical),
            key_sequence=declaration,
            data_type=self.dialect.column_type(key_type, None),
            key_range=(low, high),
            consuming_tables=consumers,
        )

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
        root = layout.document_root_constraint
        document_root = (
            None
            if root is None
            else ResolvedDocumentRootConstraint(
                definition=root, check_name=document_root_check_name(name, root)
            )
        )
        return ResolvedTable(
            mapping_owner=owner,
            physical=physical,
            sql=self.dialect.render_table(physical),
            layout=layout,
            temporal_constraints=constraints,
            document_root_constraint=document_root,
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
) -> tuple[
    Mapping[EntityIdentity, ResolvedTable], Mapping[str, PhysicalSequence | ResolvedSequence]
]:
    """Every mapping owner's table and every allocator's sequence ``binding`` places.

    Raises :class:`BindingError` with every resolution issue at once.
    """
    resolver = _Resolver(binding)
    owners = {layout.mapping_owner: layout for layout in storage_layout_facet_of(meta).tables}
    allocators = _logical_allocators(meta)
    resolver.keys(meta, owners, frozenset(allocators))
    tables = resolver.tables(owners)
    sequences = resolver.sequences(allocators, tables, _consumers(meta, tables))
    if resolver.issues:
        raise BindingError(BINDING_RESOLUTION_REJECTED, resolver.issues)
    return MappingProxyType(tables), MappingProxyType(sequences)
