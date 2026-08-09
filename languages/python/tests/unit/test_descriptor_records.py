"""m-descriptor derived facts: temporal classification, preserved local
declarations, and the family-root ancestry walk (``declaring_entity``)."""

from __future__ import annotations

import pytest

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.descriptor import _records
from parallax.descriptor._records import (
    AsOfAxisMetadata,
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    PkGenerator,
    Temporality,
    ValueObject,
    concrete_descendant_names,
    declaring_entity,
    family_root_name,
)

_MODELS = corpus_models.load_models(
    case_format.find_repo_root() / "core" / "compatibility" / "models"
)


@pytest.mark.parametrize(
    ("temporality", "expected"),
    [
        (None, "non-temporal"),
        ("nontemporal", "non-temporal"),
        ("transaction-time", "transaction-time-only"),
        ("bitemporal", "bitemporal"),
    ],
)
def test_temporal_is_derived_from_the_temporality_profile(
    temporality: Temporality | None, expected: str
) -> None:
    entity = Entity(
        name="E",
        table="e",
        temporality=temporality,
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    assert entity.temporal == expected
    assert entity.is_temporal is (expected != "non-temporal")


def test_corpus_temporal_classifications_match() -> None:
    assert _MODELS["account"].entity("Account").temporal == "non-temporal"
    assert _MODELS["balance"].entity("Balance").temporal == "transaction-time-only"


def test_primary_key_selects_declared_pk_attributes_in_order() -> None:
    balance = _MODELS["balance"].entity("Balance")
    assert tuple(a.name for a in balance.primary_key) == ("id",)


def test_records_preserve_local_declarations_and_their_effective_columns() -> None:
    account = _MODELS["account"].entity("Account")
    assert tuple((a.name, a.column) for a in account.attributes) == (
        ("id", "id"),
        ("owner", "owner"),
        ("balance", "balance"),
        ("version", "version"),
    )
    customer = _MODELS["customer"].entity("Customer")
    assert tuple((a.name, a.column) for a in customer.attributes) == (
        ("id", "id"),
        ("name", "name"),
    )
    assert tuple((v.name, v.storage_column) for v in customer.value_objects) == (
        ("address", "address"),
    )


def test_records_retain_the_tag_declaration_without_composing_a_column_sequence() -> None:
    # The framework-owned tag is a declaration on the root's strategy, and these
    # records carry it as one. Where it sits among the table's columns — and where
    # a document column sits — is `m-storage-layout`'s answer, not a descriptor fact.
    root = Entity(
        name="Animal",
        table="animal",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="name", type="string", column="name"),
        ),
        value_objects=(ValueObject(name="badge", column="badge"),),
    )
    assert root.inheritance is not None
    assert root.inheritance.tag_column == "kind"
    assert tuple(a.column for a in root.attributes) == ("id", "name")
    assert tuple(v.storage_column for v in root.value_objects) == ("badge",)
    assert not hasattr(_records, "column_order")


def test_pk_generator_generates_flags_max_and_sequence() -> None:
    assert PkGenerator(strategy="none").generates is False
    assert PkGenerator(strategy="max").generates is True
    assert PkGenerator(strategy="sequence", sequence_name="s").generates is True


# --------------------------------------------------------------------------- #
# Temporality is a family-wide property: only the root may declare it, and    #
# every descendant — abstract-subtype or concrete-subtype — inherits exactly  #
# the axes the root's profile derives. `declaring_entity` always resolves to  #
# the family root; a non-root participant that declares its own profile is    #
# rejected pre-SQL (`parallax.descriptor.validate_inheritance_families`).     #
# --------------------------------------------------------------------------- #
def _synthetic_temporal_family() -> Metamodel:
    """A THREE-level TPH family — Root (temporal) -> Mid (abstract-subtype) ->
    Leaf (concrete) — proving `declaring_entity` resolves to the root from
    EVERY position in the chain, not just the immediate parent."""
    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        temporality="transaction-time",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="txStart", type="timestamp", column="in_z"),
            Attribute(name="txEnd", type="timestamp", column="out_z"),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transaction-time", start_attribute="txStart", end_attribute="txEnd"
            ),
        ),
    )
    mid = Entity(
        name="Mid",
        inheritance=Inheritance(role="abstract-subtype", parent="Root"),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Mid", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return Metamodel(entities=(root, mid, leaf))


def _cyclic_pair() -> Metamodel:
    attrs = (Attribute(name="id", type="int64", column="id", primary_key=True),)
    return Metamodel(
        entities=(
            Entity(
                name="A",
                table="a",
                inheritance=Inheritance(role="concrete-subtype", parent="B"),
                attributes=attrs,
            ),
            Entity(
                name="B",
                table="b",
                inheritance=Inheritance(role="concrete-subtype", parent="A"),
                attributes=attrs,
            ),
        )
    )


def test_family_root_name_resolves_a_root_and_reports_none_off_a_family() -> None:
    meta = _synthetic_temporal_family()
    for name in ("Root", "Mid", "Leaf"):
        assert family_root_name(meta, meta.entity(name)) == "Root", name
    plain = Entity(name="Solo", table="solo", attributes=())
    assert family_root_name(Metamodel(entities=(plain,)), plain) is None


def test_family_root_name_spells_a_namespaced_root_canonically() -> None:
    # The value identifies a family, and a bare root name is not an identity: a
    # model may declare the same local name in two namespaces, so the local
    # spelling would give two independent families one answer.
    root = Entity(
        name="Record",
        namespace="catalog",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    leaf = Entity(
        name="Variant",
        namespace="catalog",
        table="variant",
        inheritance=Inheritance(role="concrete-subtype", parent="catalog.Record"),
    )
    meta = Metamodel(entities=(root, leaf))
    assert family_root_name(meta, leaf) == "catalog.Record"
    assert family_root_name(meta, root) == "catalog.Record"


def test_family_root_name_is_none_for_an_ancestry_that_reaches_no_root() -> None:
    cyclic = _cyclic_pair()
    assert family_root_name(cyclic, cyclic.entity("A")) is None


def test_concrete_descendant_names_collects_every_concrete_at_or_below() -> None:
    # A concrete node that is itself a parent contributes BOTH itself and its
    # concrete descendants: the effective set is every concrete node at or below
    # the position, so descent never stops at the first concrete one.
    attrs = (Attribute(name="id", type="int64", column="id", primary_key=True),)
    meta = Metamodel(
        entities=(
            Entity(
                name="Root",
                inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
                attributes=attrs,
            ),
            Entity(
                name="Middle",
                table="middle",
                inheritance=Inheritance(role="concrete-subtype", parent="Root"),
                attributes=attrs,
            ),
            Entity(
                name="Below",
                table="below",
                inheritance=Inheritance(role="concrete-subtype", parent="Middle"),
                attributes=attrs,
            ),
        )
    )
    assert concrete_descendant_names(meta, "Root") == frozenset({"Middle", "Below"})
    assert concrete_descendant_names(meta, "Middle") == frozenset({"Middle", "Below"})
    assert concrete_descendant_names(meta, "Below") == frozenset({"Below"})


def test_concrete_descendant_names_terminates_on_a_cyclic_family() -> None:
    assert concrete_descendant_names(_cyclic_pair(), "A") == frozenset({"A", "B"})


def test_declaring_entity_resolves_to_the_family_root_from_every_position() -> None:
    meta = _synthetic_temporal_family()
    for name in ("Root", "Mid", "Leaf"):
        declaring = declaring_entity(meta, meta.entity(name))
        assert declaring.name == "Root", name
        assert declaring.as_of_axes == meta.entity("Root").as_of_axes


def test_declaring_entity_walks_a_chain_that_repeats_a_local_name() -> None:
    # A local Entity name may be declared in more than one namespace, so two
    # positions of ONE valid chain may share it. The cycle guard therefore has
    # to remember canonical identities: keyed on the bare name, reaching the
    # second `Node` looks like a revisit, the walk reports a cycle the
    # descriptor never declared, and the leaf loses its root-declared key.
    root = Entity(
        name="Root",
        namespace="top",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    mid = Entity(
        name="Node",
        namespace="mid",
        inheritance=Inheritance(role="abstract-subtype", parent="top.Root"),
    )
    leaf = Entity(
        name="Node",
        namespace="leaf",
        table="leaf_node",
        inheritance=Inheritance(role="concrete-subtype", parent="mid.Node"),
    )
    meta = Metamodel(entities=(root, mid, leaf))
    assert declaring_entity(meta, leaf) is root
    assert family_root_name(meta, leaf) == "top.Root"


def test_declaring_entity_resolves_a_bare_parent_within_its_own_namespace() -> None:
    # A bare parent reference is relative to the declaring entity's namespace.
    # Each leaf below reaches its OWN root even though the local name `Record`
    # admits no unambiguous model-wide spelling, so a model-wide lookup would
    # leave both leaves without the root that declares their key.
    catalog_root = Entity(
        name="Record",
        namespace="catalog",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    archive_root = Entity(
        name="Record",
        namespace="archive",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="archiveId", type="int64", column="id", primary_key=True),),
    )
    catalog_leaf = Entity(
        name="CatalogLeaf",
        namespace="catalog",
        table="catalog_leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Record"),
    )
    archive_leaf = Entity(
        name="ArchiveLeaf",
        namespace="archive",
        table="archive_leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Record"),
    )
    meta = Metamodel(entities=(catalog_root, archive_root, catalog_leaf, archive_leaf))
    assert declaring_entity(meta, catalog_leaf) is catalog_root
    assert declaring_entity(meta, archive_leaf) is archive_root


def test_declaring_entity_reads_no_bare_parent_across_a_namespace_boundary() -> None:
    # Resolution has no model-wide unique-name fallback: a bare parent the
    # declaring namespace does not declare reaches nothing, even when exactly
    # one entity of the whole model carries that local name. Adopting the other
    # namespace's `Record` would hand this leaf a foreign family's primary key.
    root = Entity(
        name="Record",
        namespace="catalog",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    stray = Entity(
        name="StrayLeaf",
        namespace="elsewhere",
        table="stray_leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Record"),
    )
    meta = Metamodel(entities=(root, stray))
    assert declaring_entity(meta, stray) is stray
    assert family_root_name(meta, stray) is None


def test_declaring_entity_is_the_entity_itself_outside_a_family() -> None:
    # A non-inheritance temporal entity remains unaffected: `declaring_entity`
    # is a strict identity for it (m-inheritance only applies within a family).
    plain = Entity(
        name="Balance",
        table="balance",
        temporality="transaction-time",
        attributes=(
            Attribute(name="id", type="int64", column="bal_id", primary_key=True),
            Attribute(name="txStart", type="timestamp", column="in_z"),
            Attribute(name="txEnd", type="timestamp", column="out_z"),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transaction-time", start_attribute="txStart", end_attribute="txEnd"
            ),
        ),
    )
    meta = Metamodel(entities=(plain,))
    assert declaring_entity(meta, plain) is plain
