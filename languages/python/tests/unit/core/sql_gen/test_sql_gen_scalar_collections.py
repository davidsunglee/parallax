"""m-sql: reading a scalar collection's own structured Column.

A Columns collection is a Direct Column, but its Column holds a document, so a
read projects it as a document pair, keeps its storage key rather than a native
scalar lane's encoded one, and classifies it through the codec like any other
direct document. The corpus twins carry the end-to-end SQL and results.
"""

from __future__ import annotations

from parallax.conformance import models
from parallax.core.internal import predicate as oa
from parallax.core.internal.base import StructuredDocument
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.document_codec import UNAVAILABLE, DocumentFinding
from parallax.core.internal.entity._layout import CatalogedModel
from parallax.core.internal.metamodel import CompiledEntity, entity_by_name
from parallax.core.internal.read_delivery._row_decoding import member_classifiers
from tests._support.bindings import TEST_BINDING, bound_model
from tests._support.sql import compile_read
from tests.unit.core.sql_gen._delivery_support import deliver

_COLUMNS = models.load_model(
    models.default_models_dir() / "scalar-collection-layout-twin-columns.yaml"
)
_FOUND = entity_by_name(_COLUMNS, "parallax.compatibility.CollectionTwinItem")
assert _FOUND is not None
_ITEM: CompiledEntity = _FOUND


def test_a_bytes_collection_decodes_each_element_it_stores_encoded() -> None:
    compiled = compile_read(oa.TrueNode(), bound_model(_COLUMNS), POSTGRES, _ITEM)
    (row,) = deliver(_COLUMNS, compiled, [{"id": 1, "tags": ["b", "a"], "blobs": ["0a1b"]}])

    assert (row.members["tags"], row.members["blobs"]) == (("b", "a"), (b"\x0a\x1b",))


def test_a_collection_column_classifies_through_the_codec_with_its_logical_path() -> None:
    compiled = compile_read(oa.TrueNode(), bound_model(_COLUMNS), POSTGRES, _ITEM)
    layout = CatalogedModel(_COLUMNS, TEST_BINDING).layouts.entity(_ITEM.identity)
    sources = compiled.result_contract.sources(_ITEM.identity)
    classifiers = member_classifiers(
        compiled.result_contract,
        _ITEM.identity,
        layout.member_selection.bindings,
        sources.document_member_names(),
    )
    tags = layout.member_selection.attribute("tags")
    assert tags is not None
    classify = classifiers[layout.index_of[tags.identity]]
    assert classify is not None

    assert classify(StructuredDocument(["b", "a", "b"])) == (("b", "a", "b"), ())
    assert classify(StructuredDocument(["b", 5])) == (
        UNAVAILABLE,
        (DocumentFinding("leaf-undecodable", ("tags", 1), 5),),
    )
