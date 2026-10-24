"""Row decoding over compiled result contracts.

Compilation supplies each contract and every row is laid out positionally as
its statement selects it; what is graded is how binding prepares a row's
member sources and how the decoder classifies and refuses a row against them.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import replace

import pytest

from parallax.core import predicate as oa
from parallax.core.base import DocumentValue, PresentDocument
from parallax.core.deep_fetch import ResolvedReadProjection
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import locate_raw_entity_member
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import AttributeMetadata, Metamodel, ValueObjectIdentity
from parallax.core.read_delivery._page import ROOT_LEVEL, PageBuilder, ViewSchema
from parallax.core.read_delivery._row_converter import bind
from parallax.core.read_delivery._row_decoding import member_classifiers, row_identity
from parallax.core.sql_gen import SqlGenError
from parallax.core.sql_gen._compile import CompiledRead
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import formed, model, target
from tests.unit._document_layout_support import columns_model, document_model, entity
from tests.unit._prepared_read_support import bound_cells

ORDERS = model("orders")
DOCUMENT = document_model()
COLUMNS = columns_model()

# One person, spelled the two ways the two layouts store it. Every leaf inside
# the document carries the codec's own portable spelling, which is what a
# document-resident member reads back as before it is decoded.
_DOCUMENT_VALUE: DocumentValue = {
    "displayName": "Ada",
    "score": 7,
    "joinedOn": "2026-01-15",
    "address": {"city": "Oslo", "geo": {"country": "NO"}},
    "tags": [{"label": "founder"}],
}
_DOCUMENT_CELLS = {
    "id": 1,
    "payload": PresentDocument(_DOCUMENT_VALUE),
}
_COLUMNS_CELLS = {
    "id": 1,
    "display_name": "Ada",
    "score": 7,
    "joined_on": dt.date(2026, 1, 15),
    "address": PresentDocument({"city": "Oslo", "geo": {"country": "NO"}}),
    "tags": PresentDocument([{"label": "founder"}]),
}


def test_a_positional_row_is_refused_at_the_wrong_arity() -> None:
    compiled = compile_read(oa.TrueNode(), ORDERS, POSTGRES, target(ORDERS, "Order"))

    with pytest.raises(ValueError, match="does not match row arity"):
        row_identity(compiled.result_contract, ())


def _classifiers(
    meta: Metamodel, compiled: CompiledRead
) -> dict[str, Callable[[object], tuple[object, tuple[object, ...]]]]:
    """``compiled``'s prepared classifiers for its target, by member name."""
    layout = CatalogedModel(meta).layouts.entity(compiled.target)
    sources = compiled.result_contract.sources(compiled.target)
    return {
        (
            member.identity.name
            if isinstance(member, AttributeMetadata)
            else member.identity.path[-1]
        ): classifier
        for member, classifier in zip(
            layout.member_selection.bindings,
            member_classifiers(
                compiled.result_contract,
                compiled.target,
                layout.member_selection.bindings,
                sources.document_member_names(),
            ),
            strict=True,
        )
        if classifier is not None
    }


def test_document_classification_reads_the_resolved_member_off_a_folded_carrier() -> None:
    document = compile_read(
        oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"), result_form="instance"
    )
    classifiers = _classifiers(DOCUMENT, document)
    assert set(classifiers) == {"displayName", "score", "joinedOn", "address", "tags"}
    assert classifiers["displayName"](locate_raw_entity_member(_DOCUMENT_VALUE, "displayName")) == (
        "Ada",
        (),
    )
    assert classifiers["address"](locate_raw_entity_member(_DOCUMENT_VALUE, "address")) == (
        ("Oslo", ("NO",)),
        (),
    )

    columns = compile_read(
        oa.TrueNode(), COLUMNS, POSTGRES, entity(COLUMNS, "Person"), result_form="instance"
    )
    column_classifiers = _classifiers(COLUMNS, columns)
    assert set(column_classifiers) == {"address", "tags"}
    classify_address = column_classifiers["address"]
    assert classify_address(_COLUMNS_CELLS["address"])[0] == ("Oslo", ("NO",))
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        classify_address({"city": "Oslo"})


def test_binding_refuses_sources_laid_out_for_another_member_order() -> None:
    orders = compile_read(oa.TrueNode(), ORDERS, POSTGRES, target(ORDERS, "Order"))
    item = compile_read(oa.TrueNode(), ORDERS, POSTGRES, target(ORDERS, "OrderItem"))
    (sources,) = orders.result_contract.entity_sources
    (item_sources,) = item.result_contract.entity_sources
    misaligned = replace(
        orders.result_contract,
        entity_sources=(
            replace(
                sources,
                selection=item_sources.selection,
                sources=(None,) * len(item_sources.sources),
            ),
        ),
    )
    with pytest.raises(ValueError, match="not this model's member order"):
        bind(CatalogedModel(ORDERS), misaligned, orders.projection)


def test_an_occurrence_only_entity_document_still_requires_a_folded_carrier() -> None:
    from parallax.descriptor._records import (
        Attribute,
        DocumentLayout,
        Entity,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )

    holder = Entity(
        name="Holder",
        table="holder",
        layout=DocumentLayout(column="payload"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="profile",
                attributes=(ValueObjectAttribute(name="label", type="string"),),
            ),
        ),
    )
    holder_model = formed(Metamodel(entities=(holder,)))
    compiled = compile_read(
        oa.TrueNode(),
        holder_model,
        POSTGRES,
        entity(holder_model, "Holder"),
        result_form="instance",
    )
    converter = bind(CatalogedModel(holder_model), compiled.result_contract, compiled.projection)
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        converter.convert_row(
            (1, {"profile": {"label": "x"}}), PageBuilder(ViewSchema.of()), source=ROOT_LEVEL
        )


def test_predecessor_document_retention_requires_a_folded_carrier() -> None:
    compiled = compile_read(
        oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Marker"), result_form="instance"
    )
    with pytest.raises(SqlGenError, match="not a DocumentRead"):
        row_identity(compiled.result_contract, (1, {}))


def test_binding_prepares_each_occurrence_selection_once_rather_than_per_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled = compile_read(
        oa.TrueNode(), DOCUMENT, POSTGRES, entity(DOCUMENT, "Person"), result_form="instance"
    )
    model = CatalogedModel(DOCUMENT)
    checked: list[ValueObjectIdentity] = []
    includes = ResolvedReadProjection.includes_value_object

    def counted(self: ResolvedReadProjection, identity: ValueObjectIdentity) -> bool:
        checked.append(identity)
        return includes(self, identity)

    monkeypatch.setattr(ResolvedReadProjection, "includes_value_object", counted)
    converter, row = bound_cells(model, compiled, _DOCUMENT_CELLS)
    occurrences = [
        occurrence.identity
        for identity in compiled.result_contract.resolvable
        for occurrence in model.layouts.entity(identity).occurrences
    ]
    assert sorted(map(repr, checked)) == sorted(map(repr, occurrences))

    builder = PageBuilder(ViewSchema.of())
    for _ in range(3):
        converter.convert_row(row, builder, source=ROOT_LEVEL)
    assert len(checked) == len(occurrences)
