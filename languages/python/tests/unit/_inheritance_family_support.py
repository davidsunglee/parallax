"""Synthetic accepted models the DDL and fixture lanes both build on.

No corpus model combines inheritance with a value object, and none declares two
Indices over one column, so these families are where the ancestry-derived and
duplicate-rule paths get a witness. Exported without a leading underscore:
importing an underscored name across modules is a `reportPrivateUsage` error
under pyright strict, so privacy is carried by this MODULE's underscore.
"""

from __future__ import annotations

from _corpus_model_support import formed

from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.descriptor._records import (
    AsOfAxisMetadata,
    Attribute,
    Entity,
    Index,
    Inheritance,
    Metamodel,
    ValueObject,
    ValueObjectAttribute,
)

__all__ = [
    "entity_with_two_indices_over_one_column",
    "tpcs_family_with_a_root_declared_unique_index",
    "tpcs_family_with_a_temporal_root",
    "tpcs_family_with_a_value_object",
    "tph_family_with_a_descendant_declared_value_object_and_index",
    "tph_family_with_a_value_object",
]


def tph_family_with_a_value_object() -> AcceptedMetamodel:
    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="meta",
                column="meta",
                attributes=(ValueObjectAttribute(name="note", type="string"),),
            ),
        ),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return formed(Metamodel(entities=(root, leaf)))


def tpcs_family_with_a_value_object() -> AcceptedMetamodel:
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    leaf = Entity(
        name="Leaf",
        table="leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
        value_objects=(
            ValueObject(
                name="meta",
                column="meta",
                attributes=(ValueObjectAttribute(name="note", type="string"),),
            ),
        ),
    )
    return formed(Metamodel(entities=(root, leaf)))


def tph_family_with_a_descendant_declared_value_object_and_index() -> AcceptedMetamodel:
    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(
            Attribute(name="x", type="int32", column="x"),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        value_objects=(
            ValueObject(
                name="meta",
                column="meta",
                attributes=(ValueObjectAttribute(name="note", type="string"),),
            ),
        ),
        indices=(Index(name="leaf_code_uq", attributes=("code",), unique=True),),
    )
    return formed(Metamodel(entities=(root, leaf)))


def tpcs_family_with_a_root_declared_unique_index() -> AcceptedMetamodel:
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        indices=(Index(name="root_code_uq", attributes=("code",), unique=True),),
    )
    leaf = Entity(
        name="Leaf",
        table="leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return formed(Metamodel(entities=(root, leaf)))


def tpcs_family_with_a_temporal_root() -> AcceptedMetamodel:
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
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
    leaf = Entity(
        name="Leaf",
        table="leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return formed(Metamodel(entities=(root, leaf)))


def entity_with_two_indices_over_one_column() -> AcceptedMetamodel:
    # One entity declaring two DISTINCT unique indices over the SAME resolved
    # column. Each authored Index is its own constraint, so both are emitted: a
    # unique Index is not suppressed for spanning the columns another spans. A
    # cross-member duplicate cannot form (an index names only local attributes,
    # the resolver's `metamodel-index-attribute-not-local`), so a single entity
    # is where a duplicate resolved-column set can legally arise.
    widget = Entity(
        name="Widget",
        table="widget",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        indices=(
            Index(name="widget_code_uq", attributes=("code",), unique=True),
            Index(name="widget_code_uq_dup", attributes=("code",), unique=True),
        ),
    )
    return formed(Metamodel(entities=(widget,)))
