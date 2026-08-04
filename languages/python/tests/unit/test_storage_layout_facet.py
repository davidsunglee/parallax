"""m-storage-layout: immutable canonical layouts, Entity views, and positions."""

from __future__ import annotations

import dataclasses
import enum
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import FrozenInstanceError
from typing import Any, Literal, cast, overload

import pytest
from _metamodel_support import (
    Declaration,
    accepted,
    attribute,
    identity,
    instant,
    key,
    source,
)

from parallax.core import inheritance, relationship, storage_layout
from parallax.core._formation_profile import BUILTIN_MANIFEST, BUILTIN_PROFILE, form_metamodel
from parallax.core.base import STRING
from parallax.core.metamodel import (
    METAMODEL_MODULE,
    AbstractRoot,
    AbstractSubtype,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeReference,
    Cardinality,
    Column,
    CompiledMetadata,
    ConcreteSubtype,
    Document,
    EntityIdentity,
    EntityMetadata,
    ExactEntityReference,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    RelationshipIdentity,
    Table,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    TemporalDimension,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedRelationshipJoin,
    ValueObjectAttributeDeclaration,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
    compile_metadata,
)
from parallax.core.model_formation import MODEL_FORMATION_MODULE, ModelCompilerRequirement
from parallax.core.storage_layout._compile import (
    _interned,  # pyright: ignore[reportPrivateUsage] - private allocation-policy regression only
    _interned_ordinal_selection,  # pyright: ignore[reportPrivateUsage] - private allocation-policy regression only
)


def _shape(name: str = "text") -> ValueObjectShapeDeclaration:
    return ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration(name, type=STRING),),
    )


def _require_layout(
    facet: storage_layout.StorageLayoutFacet, table: str
) -> storage_layout.TableLayout:
    layout = facet.table(Table(table))
    assert layout is not None
    return layout


def _require_entity(
    facet: storage_layout.StorageLayoutFacet, entity: EntityIdentity
) -> storage_layout.EntityLayoutView:
    view = facet.entity(entity)
    assert view is not None
    return view


def _require_slot(
    layout: storage_layout.TableLayout, contributor: storage_layout.ColumnContributor
) -> storage_layout.ColumnSlot:
    slot = layout.contribution(contributor)
    assert slot is not None
    return slot


def _column_names(layout: storage_layout.TableLayout) -> list[str]:
    return [slot.column.name for slot in layout.columns]


def _tier_values(layout: storage_layout.TableLayout) -> list[str]:
    return [slot.tier.value for slot in layout.columns]


class _VisitedEntities(Sequence[EntityMetadata]):
    def __init__(self, values: Sequence[EntityMetadata]) -> None:
        self._values = tuple(values)
        self.visits = 0

    def __len__(self) -> int:
        return len(self._values)

    @overload
    def __getitem__(self, index: int) -> EntityMetadata: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[EntityMetadata]: ...

    def __getitem__(self, index: int | slice) -> EntityMetadata | Sequence[EntityMetadata]:
        if isinstance(index, slice):
            values = self._values[index]
            self.visits += len(values)
            return values
        value = self._values[index]
        self.visits += 1
        return value


class _CountingMetadata:
    def __init__(self, metadata: CompiledMetadata) -> None:
        self._metadata = metadata
        self._entities = _VisitedEntities(metadata.entities)

    @property
    def entities(self) -> Sequence[EntityMetadata]:
        return self._entities

    @property
    def visits(self) -> int:
        return self._entities.visits

    def entity(self, identity: EntityIdentity) -> EntityMetadata | None:
        return self._metadata.entity(identity)


class _CountingInheritanceFacet:
    def __init__(self, facet: inheritance.InheritanceFacet) -> None:
        self._facet = facet
        self.visits = 0

    def entity(self, identity: EntityIdentity) -> inheritance.InheritanceEntityView | None:
        self.visits += 1
        return self._facet.entity(identity)

    def position(
        self, members: Sequence[EntityIdentity]
    ) -> inheritance.InheritancePositionView | None:
        return self._facet.position(members)


def _retained_size(value: object) -> int:
    seen: set[int] = set()

    def measure(current: object) -> int:
        if id(current) in seen:
            return 0
        seen.add(id(current))
        size = sys.getsizeof(current)
        if isinstance(current, enum.Enum):
            return size
        if dataclasses.is_dataclass(current) and not isinstance(current, type):
            return size + sum(
                measure(getattr(current, field.name)) for field in dataclasses.fields(current)
            )
        if isinstance(current, Mapping):
            entries = cast("Mapping[object, object]", current)
            return size + sum(measure(key) + measure(item) for key, item in entries.items())
        if isinstance(current, (tuple, list, set, frozenset)):
            values = cast("Iterable[object]", current)
            return size + sum(measure(item) for item in values)
        slots = getattr(type(current), "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        return size + sum(
            measure(getattr(current, slot))
            for slot in slots
            if isinstance(slot, str) and hasattr(current, slot)
        )

    return measure(value)


def _tiered_tph_model() -> tuple[Any, EntityIdentity, EntityIdentity, EntityIdentity]:
    root = identity("Record")
    alpha = identity("AlphaRecord")
    beta = identity("BetaRecord")
    tx_start = instant(root, "txStart")
    tx_end = instant(root, "txEnd")
    audit = attribute(root, "revisedBy", type=STRING)
    model = form_metamodel(
        source(
            Declaration(
                identity=root,
                container=Table("record"),
                attributes=(
                    key(root),
                    tx_start,
                    attribute(root, "rootDomain", type=STRING),
                    audit,
                    tx_end,
                ),
                as_of_axes=(
                    AsOfAxisMetadata(
                        TemporalDimension.TRANSACTION_TIME,
                        tx_start.identity,
                        tx_end.identity,
                    ),
                ),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=alpha,
                attributes=(attribute(alpha, "alphaDomain", type=STRING),),
                value_objects=(
                    ValueObjectOccurrenceDeclaration(
                        name="payload",
                        storage=Column("payload"),
                        shape=_shape(),
                        multiplicity=Multiplicity.ONE,
                    ),
                ),
                inheritance=ConcreteSubtype(ExactEntityReference(root), "alpha"),
            ),
            Declaration(
                identity=beta,
                attributes=(attribute(beta, "betaDomain", type=STRING),),
                inheritance=ConcreteSubtype(ExactEntityReference(root), "beta"),
            ),
        )
    )
    return model, root, alpha, beta


def _tpcs_model() -> tuple[Any, EntityIdentity, EntityIdentity, EntityIdentity]:
    root = identity("Document")
    invoice = identity("Invoice")
    memo = identity("Memo")
    model = form_metamodel(
        source(
            Declaration(
                identity=root,
                attributes=(key(root), attribute(root, "title", type=STRING)),
                inheritance=AbstractRoot(TablePerConcreteSubtype()),
            ),
            Declaration(
                identity=invoice,
                container=Table("invoice"),
                attributes=(attribute(invoice, "invoiceDetail", type=STRING, column="detail"),),
                inheritance=ConcreteSubtype(ExactEntityReference(root)),
            ),
            Declaration(
                identity=memo,
                container=Table("memo"),
                attributes=(attribute(memo, "memoDetail", type=STRING, column="detail"),),
                inheritance=ConcreteSubtype(ExactEntityReference(root)),
            ),
        )
    )
    return model, root, invoice, memo


def _ranked_temporal_model(
    mapping: Literal["standalone", "tph", "tpcs"], *, duplicate_start: bool
) -> tuple[Any, str, EntityIdentity]:
    root = identity(f"{mapping.title()}Temporal")
    concrete = identity(f"{mapping.title()}TemporalRow")
    valid_start = instant(root, "validStart")
    valid_end = instant(root, "validEnd")
    tx_start = valid_start if duplicate_start else instant(root, "txStart")
    tx_end = instant(root, "txEnd")
    attributes = tuple(dict.fromkeys((key(root), valid_start, valid_end, tx_start, tx_end)))
    axes = (
        AsOfAxisMetadata(
            TemporalDimension.TRANSACTION_TIME,
            tx_start.identity,
            tx_end.identity,
        ),
        AsOfAxisMetadata(
            TemporalDimension.VALID_TIME,
            valid_start.identity,
            valid_end.identity,
        ),
    )
    if mapping == "standalone":
        table = "standalone_temporal"
        declarations = (
            Declaration(
                identity=root,
                container=Table(table),
                attributes=attributes,
                as_of_axes=axes,
            ),
        )
    elif mapping == "tph":
        table = "tph_temporal"
        declarations = (
            Declaration(
                identity=root,
                container=Table(table),
                attributes=attributes,
                as_of_axes=axes,
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=concrete,
                inheritance=ConcreteSubtype(ExactEntityReference(root), "row"),
            ),
        )
    else:
        table = "tpcs_temporal"
        declarations = (
            Declaration(
                identity=root,
                attributes=attributes,
                as_of_axes=axes,
                inheritance=AbstractRoot(TablePerConcreteSubtype()),
            ),
            Declaration(
                identity=concrete,
                container=Table(table),
                inheritance=ConcreteSubtype(ExactEntityReference(root)),
            ),
        )
    return form_metamodel(source(*declarations)), table, root


def _large_tph_model(width: int) -> Any:
    root = identity(f"WideRoot{width}")
    declarations = [
        Declaration(
            identity=root,
            container=Table(f"wide_tph_{width}"),
            attributes=(
                key(root),
                *(attribute(root, f"shared{index}", type=STRING) for index in range(width)),
            ),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        )
    ]
    declarations.extend(
        Declaration(
            identity=(concrete := identity(f"WideConcrete{width}_{index}")),
            attributes=(attribute(concrete, f"local{index}", type=STRING),),
            inheritance=ConcreteSubtype(ExactEntityReference(root), f"row-{index}"),
        )
        for index in range(width)
    )
    return form_metamodel(source(*declarations))


def test_the_builtin_manifest_and_profile_install_the_typed_facet_after_its_prerequisites() -> None:
    (entry,) = (
        entry
        for entry in BUILTIN_MANIFEST.entries
        if entry.owner == storage_layout.STORAGE_LAYOUT_MODULE
    )
    assert entry.issue_codes == storage_layout.ISSUE_CODES
    assert entry.compiler == ModelCompilerRequirement(storage_layout.FACET_KEY)
    assert entry.required_modules == frozenset(
        {
            METAMODEL_MODULE,
            MODEL_FORMATION_MODULE,
            inheritance.INHERITANCE_MODULE,
            relationship.RELATIONSHIP_MODULE,
        }
    )
    assert entry.required_facets == frozenset({inheritance.FACET_KEY, relationship.FACET_KEY})
    assert storage_layout.RULE_SET in BUILTIN_PROFILE.rule_sets
    assert storage_layout.MODEL_COMPILER in BUILTIN_PROFILE.model_compilers
    assert storage_layout.MODEL_COMPILER.requires == frozenset(
        {inheritance.FACET_KEY, relationship.FACET_KEY}
    )
    owners = [compiler.owner for compiler in BUILTIN_PROFILE.model_compilers]
    assert owners.index(inheritance.INHERITANCE_MODULE) < owners.index(
        storage_layout.STORAGE_LAYOUT_MODULE
    )
    assert owners.index(relationship.RELATIONSHIP_MODULE) < owners.index(
        storage_layout.STORAGE_LAYOUT_MODULE
    )


def test_a_formed_model_serves_storage_layout_through_its_typed_view() -> None:
    model, _, _, _ = _tiered_tph_model()
    assert storage_layout.view(model) == model.facet(storage_layout.FACET_KEY)


def test_empty_audit_tier_is_compiled_end_to_end_with_table_wide_tier_order() -> None:
    model, _, _, _ = _tiered_tph_model()
    layout = _require_layout(storage_layout.view(model), "record")
    assert _column_names(layout) == [
        "id",
        "kind",
        "root_domain",
        "revised_by",
        "alpha_domain",
        "beta_domain",
        "tx_start",
        "tx_end",
        "payload",
    ]
    assert _tier_values(layout) == [
        "identity",
        "discriminator",
        "domain",
        "domain",
        "domain",
        "domain",
        "temporal",
        "temporal",
        "document",
    ]
    assert all(slot.tier is not storage_layout.ColumnTier.AUDIT for slot in layout.columns)


def test_internal_audit_designations_cover_all_six_tiers_without_new_declarations() -> None:
    model, root, _, _ = _tiered_tph_model()
    revised_by = AttributeIdentity(root, "revisedBy")
    facet = storage_layout.compile_facet(
        cast(CompiledMetadata, model),
        inheritance.view(model),
        relationship.view(model),
        audit_designations=frozenset({revised_by}),
    )
    layout = _require_layout(facet, "record")
    assert _tier_values(layout) == [
        "identity",
        "discriminator",
        "domain",
        "domain",
        "domain",
        "temporal",
        "temporal",
        "audit",
        "document",
    ]
    revised_slot = layout.contribution(revised_by)
    assert revised_slot is not None
    assert revised_slot.tier is storage_layout.ColumnTier.AUDIT
    assert layout.placement(revised_by) == storage_layout.DirectColumn(revised_slot)


def test_temporal_revision_alias_is_one_temporal_slot_not_an_audit_duplicate() -> None:
    model, root, _, _ = _tiered_tph_model()
    tx_start = AttributeIdentity(root, "txStart")
    facet = storage_layout.compile_facet(
        cast(CompiledMetadata, model),
        inheritance.view(model),
        relationship.view(model),
        audit_designations=frozenset({tx_start}),
    )
    layout = _require_layout(facet, "record")
    matches = [slot for slot in layout.columns if slot.contributor == tx_start]
    assert len(matches) == 1
    assert matches[0].tier is storage_layout.ColumnTier.TEMPORAL


def test_physical_key_selects_existing_model_key_then_temporal_start_slots() -> None:
    model, root, _, _ = _tiered_tph_model()
    layout = _require_layout(storage_layout.view(model), "record")
    assert [slot.contributor for slot in layout.physical_primary_key] == [
        AttributeIdentity(root, "id"),
        AttributeIdentity(root, "txStart"),
    ]
    assert [layout.columns.index(key_slot) for key_slot in layout.physical_primary_key] == [0, 6]
    assert all(not key_slot.effective_nullable for key_slot in layout.physical_primary_key)


@pytest.mark.parametrize("mapping", ["standalone", "tph", "tpcs"])
def test_physical_key_temporal_starts_follow_dimension_rank_not_authored_axis_order(
    mapping: Literal["standalone", "tph", "tpcs"],
) -> None:
    model, table, root = _ranked_temporal_model(mapping, duplicate_start=False)
    layout = _require_layout(storage_layout.view(model), table)
    assert [slot.contributor for slot in layout.physical_primary_key] == [
        AttributeIdentity(root, "id"),
        AttributeIdentity(root, "validStart"),
        AttributeIdentity(root, "txStart"),
    ]


@pytest.mark.parametrize("mapping", ["standalone", "tph", "tpcs"])
def test_physical_key_deduplicates_a_start_designated_by_two_dimensions(
    mapping: Literal["standalone", "tph", "tpcs"],
) -> None:
    model, table, root = _ranked_temporal_model(mapping, duplicate_start=True)
    layout = _require_layout(storage_layout.view(model), table)
    assert [slot.contributor for slot in layout.physical_primary_key] == [
        AttributeIdentity(root, "id"),
        AttributeIdentity(root, "validStart"),
    ]


def test_an_independently_constructed_equal_slot_matches_by_structure() -> None:
    model, root, _, _ = _tiered_tph_model()
    layout = _require_layout(storage_layout.view(model), "record")
    slot = layout.contribution(AttributeIdentity(root, "rootDomain"))
    assert slot is not None
    equal = storage_layout.ColumnSlot(
        column=Column(slot.column.name),
        tier=slot.tier,
        contributor=AttributeIdentity(root, "rootDomain"),
        declaring_owner=EntityIdentity(root.namespace, root.name),
        effective_nullable=slot.effective_nullable,
        applicable_entities=frozenset(
            EntityIdentity(entity.namespace, entity.name) for entity in slot.applicable_entities
        ),
    )
    assert equal == slot
    assert layout.columns.index(equal) == layout.columns.index(slot)


def test_tph_slots_retain_provenance_applicability_and_effective_nullability() -> None:
    model, root, alpha, beta = _tiered_tph_model()
    layout = _require_layout(storage_layout.view(model), "record")
    root_domain = layout.contribution(AttributeIdentity(root, "rootDomain"))
    alpha_domain = layout.contribution(AttributeIdentity(alpha, "alphaDomain"))
    discriminator = layout.contribution(storage_layout.InheritanceDiscriminator(root))
    document = layout.contribution(ValueObjectIdentity(alpha, ("payload",)))
    assert root_domain is not None
    assert alpha_domain is not None
    assert discriminator is not None
    assert document is not None
    assert root_domain.declaring_owner == root
    assert root_domain.applicable_entities == frozenset({alpha, beta})
    assert not root_domain.effective_nullable
    assert alpha_domain.applicable_entities == frozenset({alpha})
    assert alpha_domain.effective_nullable
    assert discriminator.applicable_entities == frozenset({alpha, beta})
    assert not discriminator.effective_nullable
    assert document.applicable_entities == frozenset({alpha})
    assert document.effective_nullable


# --------------------------------------------------------------------------- #
# Member Placement: the sole logical locator, total over both layouts.         #
# --------------------------------------------------------------------------- #


def _nested_shape() -> ValueObjectShapeDeclaration:
    """A `contact` occurrence holding one leaf and one nested `geo` occurrence."""
    return ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration("city", type=STRING),),
        value_objects=(
            NestedValueObjectOccurrenceDeclaration(
                name="geo",
                shape=ValueObjectShapeDeclaration(
                    key=ValueObjectShapeKey(),
                    attributes=(ValueObjectAttributeDeclaration("country", type=STRING),),
                ),
            ),
        ),
    )


def _nested_value_object_model() -> tuple[Any, EntityIdentity]:
    entity = identity("Contact")
    return (
        form_metamodel(
            source(
                Declaration(
                    identity=entity,
                    container=Table("contact"),
                    attributes=(key(entity), attribute(entity, "name", type=STRING)),
                    value_objects=(
                        ValueObjectOccurrenceDeclaration(
                            name="address",
                            storage=Column("address"),
                            shape=_nested_shape(),
                        ),
                    ),
                )
            )
        ),
        entity,
    )


def test_placement_and_contribution_agree_for_every_conventional_top_level_member() -> None:
    # Under `Columns` every top-level member is placed over the slot its own
    # contributor owns, so conventional behavior is one case of this contract
    # rather than a parallel path.
    model, entity = _nested_value_object_model()
    layout = _require_layout(storage_layout.view(model), "contact")
    for member in (
        AttributeIdentity(entity, "id"),
        AttributeIdentity(entity, "name"),
        ValueObjectIdentity(entity, ("address",)),
    ):
        assert layout.placement(member) == storage_layout.DirectColumn(
            _require_slot(layout, member)
        )


def test_a_conventional_value_object_leaf_is_placed_inside_its_own_structured_column() -> None:
    # Conventional storage already has Document Paths: a leaf's path begins at
    # the first segment below the occurrence, over that occurrence's own column.
    model, entity = _nested_value_object_model()
    layout = _require_layout(storage_layout.view(model), "contact")
    address = ValueObjectIdentity(entity, ("address",))
    slot = layout.contribution(address)
    assert slot is not None
    geo = ValueObjectIdentity(entity, ("address", "geo"))
    assert layout.placement(ValueObjectAttributeIdentity(address, "city")) == (
        storage_layout.DocumentPath(slot, ("city",))
    )
    assert layout.placement(geo) == storage_layout.DocumentPath(slot, ("geo",))
    assert layout.placement(ValueObjectAttributeIdentity(geo, "country")) == (
        storage_layout.DocumentPath(slot, ("geo", "country"))
    )


def test_a_document_path_names_at_least_one_member() -> None:
    # Every path is relative to the root of the document its slot carries, so an
    # empty one would name the document itself, which is not a member.
    model, entity = _nested_value_object_model()
    layout = _require_layout(storage_layout.view(model), "contact")
    slot = _require_slot(layout, ValueObjectIdentity(entity, ("address",)))
    with pytest.raises(ValueError, match="at least one member"):
        storage_layout.DocumentPath(slot, ())


def test_placement_is_absent_for_a_member_the_table_does_not_carry() -> None:
    # Absence is a lookup miss, never a "not resolved yet": the facet is
    # published whole and after every Rule Set has succeeded.
    model, entity = _nested_value_object_model()
    layout = _require_layout(storage_layout.view(model), "contact")
    address = ValueObjectIdentity(entity, ("address",))
    assert layout.placement(AttributeIdentity(entity, "absent")) is None
    assert layout.placement(ValueObjectAttributeIdentity(address, "absent")) is None
    assert layout.placement(ValueObjectIdentity(identity("Other"), ("address",))) is None


def _document_family() -> tuple[CompiledMetadata, EntityIdentity, EntityIdentity, EntityIdentity]:
    """A TPH family whose root selects Relational Document Layout.

    Built through the Metadata Compiler rather than whole-model formation,
    because the capability gate refuses every Document layout this build cannot
    execute end to end.
    """
    root = identity("Record")
    alpha = identity("AlphaRecord")
    beta = identity("BetaRecord")
    return (
        _unvalidated(
            Declaration(
                identity=root,
                container=Table("record"),
                layout=Document(Column("doc")),
                attributes=(key(root), attribute(root, "rootDomain", type=STRING)),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=alpha,
                attributes=(attribute(alpha, "alphaDomain", type=STRING),),
                value_objects=(
                    ValueObjectOccurrenceDeclaration(
                        name="payload", storage=Column("payload"), shape=_nested_shape()
                    ),
                ),
                inheritance=ConcreteSubtype(ExactEntityReference(root), "alpha"),
            ),
            Declaration(
                identity=beta,
                attributes=(attribute(beta, "betaDomain", type=STRING),),
                inheritance=ConcreteSubtype(ExactEntityReference(root), "beta"),
            ),
        ),
        root,
        alpha,
        beta,
    )


def _document_facet(metadata: CompiledMetadata) -> storage_layout.StorageLayoutFacet:
    return storage_layout.compile_facet(
        metadata,
        inheritance.compile_facet(metadata),
        relationship.compile_facet(metadata),
    )


def test_a_document_layout_contributes_one_shared_not_null_structured_column_last() -> None:
    metadata, root, alpha, beta = _document_family()
    layout = _require_layout(_document_facet(metadata), "record")
    assert _column_names(layout) == ["id", "kind", "doc"]
    structured = layout.columns[-1]
    assert structured.contributor == storage_layout.RelationalDocument(root)
    assert structured.tier is storage_layout.ColumnTier.DOCUMENT
    assert structured.declaring_owner == root
    assert not structured.effective_nullable
    assert structured.applicable_entities == frozenset({alpha, beta})


def test_document_resident_members_contribute_no_slot_and_are_placed_by_path() -> None:
    metadata, root, alpha, _ = _document_family()
    layout = _require_layout(_document_facet(metadata), "record")
    structured = layout.columns[-1]
    payload = ValueObjectIdentity(alpha, ("payload",))
    assert layout.contribution(AttributeIdentity(root, "rootDomain")) is None
    assert layout.contribution(payload) is None
    assert layout.placement(AttributeIdentity(root, "id")) == storage_layout.DirectColumn(
        _require_slot(layout, AttributeIdentity(root, "id"))
    )
    assert layout.placement(AttributeIdentity(root, "rootDomain")) == (
        storage_layout.DocumentPath(structured, ("rootDomain",))
    )
    assert layout.placement(payload) == storage_layout.DocumentPath(structured, ("payload",))
    assert layout.placement(ValueObjectAttributeIdentity(payload, "city")) == (
        storage_layout.DocumentPath(structured, ("payload", "city"))
    )
    assert layout.placement(
        ValueObjectAttributeIdentity(ValueObjectIdentity(alpha, ("payload", "geo")), "country")
    ) == storage_layout.DocumentPath(structured, ("payload", "geo", "country"))


def test_a_tpcs_family_receives_one_structured_column_per_concrete_table() -> None:
    # One root declares one layout policy and one Structured Column name that
    # every concrete Table in the family receives, so each concrete Table has its
    # own slot naming the same owner and the same Column.
    root = identity("Ledger")
    invoice = identity("Invoice")
    memo = identity("Memo")
    metadata = _unvalidated(
        Declaration(
            identity=root,
            layout=Document(Column("doc")),
            attributes=(key(root), attribute(root, "title", type=STRING)),
            inheritance=AbstractRoot(TablePerConcreteSubtype()),
        ),
        Declaration(
            identity=invoice,
            container=Table("invoice"),
            attributes=(attribute(invoice, "invoiceDetail", type=STRING),),
            inheritance=ConcreteSubtype(ExactEntityReference(root)),
        ),
        Declaration(
            identity=memo,
            container=Table("memo"),
            attributes=(attribute(memo, "memoDetail", type=STRING),),
            inheritance=ConcreteSubtype(ExactEntityReference(root)),
        ),
    )
    facet = _document_facet(metadata)
    contributor = storage_layout.RelationalDocument(root)
    slots = {
        table: _require_slot(_require_layout(facet, table), contributor)
        for table in ("invoice", "memo")
    }
    assert {table: slot.column.name for table, slot in slots.items()} == {
        "invoice": "doc",
        "memo": "doc",
    }
    assert slots["invoice"] != slots["memo"]
    for table, owned in (("invoice", invoice), ("memo", memo)):
        layout = _require_layout(facet, table)
        assert _column_names(layout) == ["id", "doc"]
        assert layout.placement(AttributeIdentity(root, "title")) == storage_layout.DocumentPath(
            slots[table], ("title",)
        )
        assert layout.placement(
            AttributeIdentity(owned, f"{owned.name.lower()}Detail")
        ) == storage_layout.DocumentPath(slots[table], (f"{owned.name.lower()}Detail",))


def test_an_inherited_join_endpoint_keeps_the_direct_column_its_role_earns_it() -> None:
    # The compiler reads endpoints from compiled directions, which address an
    # inherited Attribute at the position naming it, and classifies declarations,
    # which carry the declaring Entity's Identity. Resolving one to the other is
    # what keeps the endpoint's required Column in the Table: without it the
    # join's own Attribute would be written into the document and the Table would
    # have no Column to join on.
    root = identity("Ledger")
    entry = identity("Entry")
    holder = identity("Holder")
    owner_id = attribute(root, "ownerId", column="owner_key")
    metadata = _unvalidated(
        Declaration(
            identity=root,
            layout=Document(Column("doc")),
            attributes=(key(root), owner_id, attribute(root, "title", type=STRING)),
            inheritance=AbstractRoot(TablePerConcreteSubtype()),
        ),
        Declaration(
            identity=entry,
            container=Table("entry"),
            inheritance=ConcreteSubtype(ExactEntityReference(root)),
            relationships=(
                UnresolvedDefiningRelationshipDeclaration(
                    identity=RelationshipIdentity(entry, "owner"),
                    cardinality=Cardinality.MANY_TO_ONE,
                    join=UnresolvedRelationshipJoin(
                        source=AttributeIdentity(entry, "ownerId"),
                        target=AttributeReference(ExactEntityReference(holder), "id"),
                    ),
                ),
            ),
        ),
        Declaration(identity=holder, container=Table("holder"), attributes=(key(holder),)),
    )
    layout = _require_layout(_document_facet(metadata), "entry")
    assert _column_names(layout) == ["id", "owner_key", "doc"]
    assert layout.placement(owner_id.identity) == storage_layout.DirectColumn(
        _require_slot(layout, owner_id.identity)
    )
    assert layout.placement(AttributeIdentity(root, "title")) == storage_layout.DocumentPath(
        layout.columns[-1], ("title",)
    )
    holder_layout = _require_layout(_document_facet(metadata), "holder")
    assert _column_names(holder_layout) == ["id"]


def test_branch_placements_are_the_branch_layouts_own_answers_in_member_order() -> None:
    model, root, alpha, beta = _tiered_tph_model()
    view = storage_layout.view(model).position((alpha, beta))
    assert view is not None
    assert tuple(view.members) == (
        AttributeIdentity(root, "id"),
        AttributeIdentity(root, "txStart"),
        AttributeIdentity(root, "rootDomain"),
        AttributeIdentity(root, "revisedBy"),
        AttributeIdentity(root, "txEnd"),
        AttributeIdentity(alpha, "alphaDomain"),
        AttributeIdentity(beta, "betaDomain"),
        ValueObjectIdentity(alpha, ("payload",)),
    )
    (branch,) = view.branches
    assert branch.placements == tuple(branch.layout.placement(member) for member in view.members)


def test_a_position_over_disjoint_branches_answers_placement_per_branch() -> None:
    model, invoice, memo = _tpcs_model()[0], _tpcs_model()[2], _tpcs_model()[3]
    view = storage_layout.view(model).position((invoice, memo))
    assert view is not None
    assert len(view.branches) == 2
    for branch in view.branches:
        assert len(branch.placements) == len(view.members)
        for member, placement in zip(view.members, branch.placements, strict=True):
            assert placement == branch.layout.placement(member) or placement is None


def test_rowless_tph_branch_still_contributes_to_the_complete_shared_layout() -> None:
    root = identity("Record")
    concrete = identity("ConcreteRecord")
    dormant = identity("DormantRecord")
    model = form_metamodel(
        source(
            Declaration(
                identity=root,
                container=Table("record"),
                attributes=(key(root),),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=dormant,
                attributes=(attribute(dormant, "dormantValue", type=STRING),),
                inheritance=AbstractSubtype(ExactEntityReference(root)),
            ),
            Declaration(
                identity=concrete,
                inheritance=ConcreteSubtype(ExactEntityReference(root), "record"),
            ),
        )
    )
    facet = storage_layout.view(model)
    layout = _require_layout(facet, "record")
    dormant_slot = layout.contribution(AttributeIdentity(dormant, "dormantValue"))
    assert dormant_slot is not None
    assert dormant_slot.applicable_entities == frozenset()
    assert dormant_slot.effective_nullable
    concrete_view = _require_entity(facet, concrete)
    assert dormant_slot not in concrete_view.columns


def test_private_applicability_intern_deduplicates_structurally_equal_keys() -> None:
    alpha = identity("Alpha")
    beta = identity("Beta")
    intern: dict[frozenset[EntityIdentity], frozenset[EntityIdentity]] = {}
    first = _interned({alpha, beta}, intern)
    second = _interned({beta, alpha}, intern)
    assert first == second
    assert len(intern) == 1


def test_private_entity_slot_selections_are_compact_and_interned_by_ordinals() -> None:
    model, _, alpha, _ = _tiered_tph_model()
    layout = _require_layout(storage_layout.view(model), "record")
    intern: dict[int, Any] = {}
    first = _interned_ordinal_selection(layout, alpha, intern)
    second = _interned_ordinal_selection(layout, alpha, intern)
    assert first == second
    assert len(intern) == 1
    assert (
        first.materialize(layout.columns)
        == _require_entity(storage_layout.view(model), alpha).columns
    )


def test_entity_views_reference_table_slots_and_assign_concrete_discriminators() -> None:
    model, root, alpha, beta = _tiered_tph_model()
    facet = storage_layout.view(model)
    alpha_view = _require_entity(facet, alpha)
    beta_view = _require_entity(facet, beta)
    assert alpha_view.layout == beta_view.layout
    assert [slot.column.name for slot in alpha_view.columns] == [
        "id",
        "kind",
        "root_domain",
        "revised_by",
        "alpha_domain",
        "tx_start",
        "tx_end",
        "payload",
    ]
    assert alpha_view.discriminator is not None
    assert alpha_view.discriminator.value == "alpha"
    assert alpha_view.discriminator.slot == alpha_view.layout.contribution(
        storage_layout.InheritanceDiscriminator(root)
    )
    assert beta_view.discriminator is not None
    assert beta_view.discriminator.value == "beta"
    assert facet.entity(root) is None


def test_tpcs_compiles_one_ancestry_derived_layout_per_concrete_table() -> None:
    model, root, invoice, memo = _tpcs_model()
    facet = storage_layout.view(model)
    assert [layout.table.name for layout in facet.tables] == ["invoice", "memo"]
    invoice_layout = _require_layout(facet, "invoice")
    memo_layout = _require_layout(facet, "memo")
    assert _column_names(invoice_layout) == ["id", "title", "detail"]
    assert _column_names(memo_layout) == ["id", "title", "detail"]
    invoice_key = invoice_layout.contribution(AttributeIdentity(root, "id"))
    memo_key = memo_layout.contribution(AttributeIdentity(root, "id"))
    assert invoice_key is not None
    assert memo_key is not None
    assert invoice_key.applicable_entities == frozenset({invoice})
    assert memo_key.applicable_entities == frozenset({memo})
    assert invoice_key != memo_key
    assert _require_entity(facet, invoice).discriminator is None


def test_tpcs_position_has_one_logical_order_and_slot_or_absence_branch_maps() -> None:
    model, root, invoice, memo = _tpcs_model()
    position = storage_layout.view(model).position((invoice, memo))
    assert position is not None
    assert [column.contributor for column in position.columns] == [
        AttributeIdentity(root, "id"),
        AttributeIdentity(root, "title"),
        AttributeIdentity(invoice, "invoiceDetail"),
        AttributeIdentity(memo, "memoDetail"),
    ]
    assert [branch.layout.table.name for branch in position.branches] == ["invoice", "memo"]
    assert [slot is not None for slot in position.branches[0].slots] == [True, True, True, False]
    assert [slot is not None for slot in position.branches[1].slots] == [True, True, False, True]
    assert all(branch.discriminator_slot is None for branch in position.branches)


def test_tph_position_filters_applicability_without_creating_a_new_table_order() -> None:
    model, root, alpha, _ = _tiered_tph_model()
    facet = storage_layout.view(model)
    position = facet.position((alpha,))
    assert position is not None
    assert len(position.branches) == 1
    branch = position.branches[0]
    assert branch.layout == facet.tables[0]
    assert branch.discriminator_slot == branch.layout.contribution(
        storage_layout.InheritanceDiscriminator(root)
    )
    assert all(slot is not None for slot in branch.slots)
    assert AttributeIdentity(identity("BetaRecord"), "betaDomain") not in {
        column.contributor for column in position.columns
    }


def test_empty_unknown_noncanonical_and_cross_family_positions_are_total() -> None:
    model, _, invoice, memo = _tpcs_model()
    facet = storage_layout.view(model)
    empty = facet.position(())
    assert empty is not None
    assert tuple(empty.concrete_entities) == ()
    assert tuple(empty.columns) == ()
    assert tuple(empty.branches) == ()
    assert facet.position((memo, invoice)) is None
    assert facet.position((invoice, invoice)) is None
    assert facet.position((EntityIdentity("elsewhere", "Invoice"),)) is None
    standalone = identity("Standalone")
    other_model = form_metamodel(
        source(
            Declaration(
                identity=standalone,
                container=Table("standalone"),
                attributes=(key(standalone),),
            )
        )
    )
    assert storage_layout.view(other_model).position((standalone,)) is not None


def test_a_position_spanning_two_families_is_absent_rather_than_a_merged_shape() -> None:
    # A position is one family's concrete selection. Two independently rooted
    # row owners, canonically ordered so the order guard cannot answer first,
    # name no single logical contributor sequence and no branch alignment.
    first = identity("FirstStandalone")
    second = identity("SecondStandalone")
    model = form_metamodel(
        source(
            Declaration(identity=first, container=Table("first"), attributes=(key(first),)),
            Declaration(identity=second, container=Table("second"), attributes=(key(second),)),
        )
    )
    facet = storage_layout.view(model)
    assert facet.position((first,)) is not None
    assert facet.position((second,)) is not None
    assert facet.position((first, second)) is None


def test_unknown_table_column_contributor_and_entity_lookups_return_absence() -> None:
    model, root, _, _ = _tiered_tph_model()
    facet = storage_layout.view(model)
    layout = _require_layout(facet, "record")
    assert facet.table(Table("absent")) is None
    assert facet.entity(EntityIdentity(None, "Absent")) is None
    assert layout.column(Column("absent")) is None
    assert layout.contribution(AttributeIdentity(root, "absent")) is None


# --------------------------------------------------------------------------- #
# Compiler-contract refusals. The compiler composes accepted values and decides #
# no validity, so an input the Rule Sets would have rejected is a caller        #
# contract failure: it is refused with the violated invariant named, never      #
# published as a layout that quietly drops or invents a Column.                 #
# --------------------------------------------------------------------------- #
def _unvalidated(*declarations: Declaration) -> CompiledMetadata:
    """Compiled Metadata over ``declarations`` with no Rule Set run."""
    return compile_metadata(accepted(source(*declarations)))


class _AbsentInheritanceFacet:
    def entity(self, identity: EntityIdentity) -> inheritance.InheritanceEntityView | None:
        return None

    def position(
        self, members: Sequence[EntityIdentity]
    ) -> inheritance.InheritancePositionView | None:
        return None


def test_compiling_without_an_inheritance_view_refuses_rather_than_guessing_a_family() -> None:
    entity = identity("Unviewed")
    metadata = _unvalidated(
        Declaration(identity=entity, container=Table("unviewed"), attributes=(key(entity),))
    )
    with pytest.raises(RuntimeError, match="no Inheritance Facet view"):
        storage_layout.compile_facet(
            metadata,
            cast(inheritance.InheritanceFacet, _AbsentInheritanceFacet()),
            relationship.compile_facet(metadata),
        )


def test_compiling_a_twice_claimed_column_refuses_rather_than_composing_one_slot() -> None:
    entity = identity("Colliding")
    metadata = _unvalidated(
        Declaration(
            identity=entity,
            container=Table("colliding"),
            attributes=(
                key(entity),
                attribute(entity, "first", type=STRING, column="shared"),
                attribute(entity, "second", type=STRING, column="shared"),
            ),
        )
    )
    with pytest.raises(RuntimeError, match="duplicate Column or contributor"):
        storage_layout.compile_facet(
            metadata,
            inheritance.compile_facet(metadata),
            relationship.compile_facet(metadata),
        )


def test_compiling_a_tagless_shared_table_variant_refuses_rather_than_omitting_it() -> None:
    root = identity("Untagged")
    concrete = identity("UntaggedRow")
    metadata = _unvalidated(
        Declaration(
            identity=root,
            container=Table("untagged"),
            attributes=(key(root),),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=concrete,
            inheritance=ConcreteSubtype(ExactEntityReference(root)),
        ),
    )
    with pytest.raises(RuntimeError, match="no tag value"):
        storage_layout.compile_facet(
            metadata,
            inheritance.compile_facet(metadata),
            relationship.compile_facet(metadata),
        )


def test_compiling_a_tableless_shared_family_root_refuses_rather_than_inventing_a_table() -> None:
    root = identity("Rootless")
    concrete = identity("RootlessRow")
    metadata = _unvalidated(
        Declaration(
            identity=root,
            attributes=(key(root),),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=concrete,
            inheritance=ConcreteSubtype(ExactEntityReference(root), "rootless"),
        ),
    )
    with pytest.raises(RuntimeError, match=r"TPH root .* has no Table"):
        storage_layout.compile_facet(
            metadata,
            inheritance.compile_facet(metadata),
            relationship.compile_facet(metadata),
        )


def test_compiling_a_tableless_branch_concrete_refuses_rather_than_inventing_a_table() -> None:
    root = identity("Branchless")
    concrete = identity("BranchlessRow")
    metadata = _unvalidated(
        Declaration(
            identity=root,
            attributes=(key(root),),
            inheritance=AbstractRoot(TablePerConcreteSubtype()),
        ),
        Declaration(identity=concrete, inheritance=ConcreteSubtype(ExactEntityReference(root))),
    )
    with pytest.raises(RuntimeError, match=r"TPCS concrete .* has no Table"):
        storage_layout.compile_facet(
            metadata,
            inheritance.compile_facet(metadata),
            relationship.compile_facet(metadata),
        )


def test_compiling_a_twice_owned_table_refuses_rather_than_merging_two_mappings() -> None:
    first = identity("Alpha")
    second = identity("Beta")
    metadata = _unvalidated(
        Declaration(identity=first, container=Table("shared"), attributes=(key(first),)),
        Declaration(identity=second, container=Table("shared"), attributes=(key(second),)),
    )
    with pytest.raises(RuntimeError, match="has multiple mapping owners"):
        storage_layout.compile_facet(
            metadata,
            inheritance.compile_facet(metadata),
            relationship.compile_facet(metadata),
        )


def test_layout_values_and_sequences_are_immutable() -> None:
    model, _, _, _ = _tiered_tph_model()
    facet = storage_layout.view(model)
    layout = facet.tables[0]
    assert isinstance(facet.tables, tuple)
    assert isinstance(layout.columns, tuple)
    assert isinstance(layout.physical_primary_key, tuple)
    with pytest.raises(FrozenInstanceError):
        cast(Any, layout.columns[0]).effective_nullable = True
    with pytest.raises(FrozenInstanceError):
        cast(Any, layout).table = Table("changed")
    with pytest.raises(AttributeError):
        cast(Any, facet).tables = ()


def test_repeated_compilation_and_operation_scoped_positions_are_structurally_deterministic() -> (
    None
):
    model, _, alpha, beta = _tiered_tph_model()
    first = storage_layout.compile_facet(
        cast(CompiledMetadata, model), inheritance.view(model), relationship.view(model)
    )
    second = storage_layout.compile_facet(
        cast(CompiledMetadata, model), inheritance.view(model), relationship.view(model)
    )
    assert tuple(first.tables) == tuple(second.tables)
    first_position = first.position((alpha, beta))
    second_position = first.position((alpha, beta))
    assert first_position == second_position


@pytest.mark.parametrize("count", [24, 96, 192])
def test_family_fact_compilation_visits_standalone_inputs_linearly(count: int) -> None:
    declarations = tuple(
        Declaration(
            identity=(entity := identity(f"Standalone{index}")),
            container=Table(f"standalone_{index}"),
            attributes=(key(entity),),
        )
        for index in range(count)
    )
    model = form_metamodel(source(*declarations))
    counted = _CountingMetadata(cast(CompiledMetadata, model))
    counted_inheritance = _CountingInheritanceFacet(inheritance.view(model))
    storage_layout.compile_facet(
        counted,
        cast(inheritance.InheritanceFacet, counted_inheritance),
        relationship.view(model),
    )
    assert counted.visits == count
    assert counted_inheritance.visits == count


def test_large_tph_retained_layout_size_scales_with_schema_not_entity_slot_tuples() -> None:
    small = storage_layout.view(_large_tph_model(24))
    large = storage_layout.view(_large_tph_model(48))
    assert _retained_size(large) < _retained_size(small) * 2.7


def test_entity_columns_are_materialized_on_demand_without_retained_position_growth() -> None:
    model, _, alpha, beta = _tiered_tph_model()
    facet = storage_layout.view(model)
    before = _retained_size(facet)
    alpha_view = _require_entity(facet, alpha)
    expected = tuple(alpha_view.columns)
    for _ in range(32):
        assert tuple(_require_entity(facet, alpha).columns) == expected
        assert facet.position((alpha, beta)) == facet.position((alpha, beta))
    assert _retained_size(facet) == before


def test_the_public_facet_surface_contains_only_bounded_layout_and_lookup_operations() -> None:
    model, _, _, _ = _tiered_tph_model()
    facet = storage_layout.view(model)
    assert {name for name in dir(facet) if not name.startswith("_")} == {
        "entity",
        "position",
        "table",
        "tables",
    }
