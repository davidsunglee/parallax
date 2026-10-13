"""Synthetic accepted models the DDL and fixture lanes both build on.

No corpus model combines inheritance with a value object, and none declares two
Indices over one column, so these families are where the ancestry-derived and
duplicate-rule paths get a witness. Exported without a leading underscore:
importing an underscored name across modules is a `reportPrivateUsage` error
under pyright strict, so privacy is carried by this MODULE's underscore.
"""

from __future__ import annotations

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
from tests.unit._corpus_model_support import formed

__all__ = [
    "entity_with_two_indices_over_one_column",
    "tpcs_family_with_a_root_declared_unique_index",
    "tpcs_family_with_a_temporal_root",
    "tpcs_family_with_a_value_object",
    "tpcs_family_with_indices_at_every_level",
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


def tpcs_family_with_indices_at_every_level() -> AcceptedMetamodel:
    # The root, an abstract subtype, and a concrete each declare an Index over
    # their own member, so each reaches exactly the concrete Tables repeating
    # that member: the root's every Table, the abstract subtype's only its own
    # concrete descendant's, and the concrete's only its own.
    root = Entity(
        name="Doc",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        indices=(Index(name="doc_code_uq", attributes=("code",), unique=True),),
    )
    financial = Entity(
        name="Financial",
        inheritance=Inheritance(role="abstract-subtype", parent="Doc"),
        attributes=(Attribute(name="currency", type="string", column="currency", max_length=3),),
        indices=(Index(name="financial_currency", attributes=("currency",)),),
    )
    invoice = Entity(
        name="Invoice",
        table="invoice",
        inheritance=Inheritance(role="concrete-subtype", parent="Financial"),
        attributes=(Attribute(name="number", type="string", column="invoice_no", max_length=8),),
        indices=(Index(name="invoice_number_uq", attributes=("number",), unique=True),),
    )
    memo = Entity(
        name="Memo",
        table="memo",
        inheritance=Inheritance(role="concrete-subtype", parent="Doc"),
        attributes=(Attribute(name="topic", type="string", column="topic", max_length=8),),
    )
    return formed(Metamodel(entities=(root, financial, invoice, memo)))


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
