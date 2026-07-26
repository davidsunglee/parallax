"""The six public doors of ``parallax.descriptor`` (spec §2 "Canonical descriptor input").

The three ``hub_from_*`` doors converge on one sealed fixed-source hub and share a
fixed phase order — syntax, schema, value, then every semantic model rule as a
``MetamodelValidationError`` inside the same call. The three export doors run the
same conversion over a class-backed or a descriptor-backed hub. These pin the
door-level contracts the private ingestion, adaptation, and export modules are
already tested through: which phase each door can fail in, that text input is
accepted as ``str`` or UTF-8 ``bytes``, that repeated document results are
structurally equal and repeated text results byte-identical, and that both
frontends export the same canonical document.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import cast

import pytest
import yaml

from parallax.core import (
    MANY_TO_ONE,
    Attr,
    Entity,
    MetamodelHub,
    MetamodelLookupError,
    Rel,
    attr,
    index,
    rel,
)
from parallax.core.model_formation import MetamodelValidationError
from parallax.descriptor import (
    DescriptorError,
    DescriptorExportError,
    DescriptorSchemaError,
    DescriptorSyntaxError,
    DescriptorValueError,
    export_document,
    export_json,
    export_yaml,
    hub_from_document,
    hub_from_json,
    hub_from_yaml,
)
from parallax.descriptor import _hub as hub_module

pytestmark = pytest.mark.unit

_YAML = """
entities:
  - name: Author
    namespace: bookshop
    table: author
    attributes:
      - name: id
        type: int64
        primaryKey: true
      - name: name
        type: string
        maxLength: 200
    relationships:
      - name: books
        reverseOf: Book.author
  - name: Book
    namespace: bookshop
    table: book
    attributes:
      - name: id
        type: int64
        primaryKey: true
      - name: title
        type: string
      - name: authorId
        type: int64
    relationships:
      - name: author
        cardinality: many-to-one
        join:
          source: authorId
          target: { entity: Author, attribute: id }
    indices:
      - name: book_author_id
        attributes: [authorId]
"""


def _document() -> Mapping[str, object]:
    return cast("Mapping[str, object]", yaml.safe_load(_YAML))


def _class_backed() -> tuple[MetamodelHub, type]:
    """The same model as classes, with one of its Entity Classes.

    A successful construction claims its classes permanently, so every caller
    declares fresh class objects rather than sharing a module-level model.
    """

    class Author(Entity, table="author", namespace="bookshop"):
        id: Attr[int] = attr(primary_key=True)
        name: Attr[str] = attr(max_length=200)
        books: Rel[tuple[Book, ...]] = rel(reverse_of="author")

    class Book(
        Entity,
        table="book",
        namespace="bookshop",
        indices=(index("book_author_id", "author_id"),),
    ):
        id: Attr[int] = attr(primary_key=True)
        title: Attr[str] = attr()
        author_id: Attr[int] = attr(name="authorId", column="authorId")
        author: Rel[Author] = rel(cardinality=MANY_TO_ONE, join=("author_id", "id"))

    return MetamodelHub(Author, Book), Author


# --------------------------------------------------------------------------- #
# The three doors agree, and each yields a sealed hub.                         #
# --------------------------------------------------------------------------- #
def test_every_door_yields_the_same_sealed_model() -> None:
    document = _document()
    hubs = [
        hub_from_document(document),
        hub_from_json(json.dumps(document)),
        hub_from_yaml(_YAML),
    ]
    exported = [export_document(hub) for hub in hubs]
    assert exported[0] == exported[1] == exported[2]
    for built in hubs:
        assert built.meta("bookshop.Author").identity.name == "Author"
        assert [entity.identity.canonical for entity in built.entities] == [
            "bookshop.Author",
            "bookshop.Book",
        ]


def test_a_descriptor_backed_hub_claims_no_class() -> None:
    # A descriptor-backed hub creates no Metamodel Binding, so a class key is not
    # a lookup it can answer at all — the identity spelling is.
    _, author_class = _class_backed()
    built = hub_from_yaml(_YAML)
    with pytest.raises(MetamodelLookupError) as caught:
        built.meta(author_class)
    assert caught.value.code == "metamodel-class-not-bound"


def test_the_text_doors_accept_utf8_bytes() -> None:
    document = _document()
    assert export_document(hub_from_json(json.dumps(document).encode())) == export_document(
        hub_from_json(json.dumps(document))
    )
    assert export_document(hub_from_yaml(_YAML.encode())) == export_document(hub_from_yaml(_YAML))


def test_repeated_document_export_is_structurally_equal_and_freshly_built() -> None:
    built = hub_from_yaml(_YAML)
    first, second = export_document(built), export_document(built)
    assert first == second
    assert first is not second
    first["entities"] = []
    assert export_document(built) == second


# --------------------------------------------------------------------------- #
# The fixed phase order.                                                      #
# --------------------------------------------------------------------------- #
def test_undecodable_bytes_fail_as_a_syntax_defect_of_the_declared_format() -> None:
    for door, spelling in ((hub_from_json, "json"), (hub_from_yaml, "yaml")):
        with pytest.raises(DescriptorSyntaxError) as caught:
            door(b"\xff\xfe not utf-8")
        assert caught.value.code == "descriptor-invalid-syntax"
        assert caught.value.format == spelling
        assert isinstance(caught.value.cause, UnicodeDecodeError)


def test_malformed_text_fails_in_the_syntax_phase() -> None:
    with pytest.raises(DescriptorSyntaxError) as caught:
        hub_from_json("{not json")
    assert caught.value.format == "json"
    with pytest.raises(DescriptorSyntaxError) as caught:
        hub_from_yaml("entities: [\n")
    assert caught.value.format == "yaml"


def test_the_document_door_has_no_syntax_phase() -> None:
    # Schema validation is its first gate, so a document that would be a syntax
    # failure as text is simply a schema failure here.
    with pytest.raises(DescriptorSchemaError) as caught:
        hub_from_document(cast("Mapping[str, object]", {"entity": "not a mapping"}))
    assert caught.value.code == "descriptor-schema-invalid"
    assert not isinstance(caught.value, DescriptorSyntaxError)


def test_a_schema_valid_but_unconstructible_value_fails_in_the_value_phase() -> None:
    text = _YAML.replace("type: string\n        maxLength: 200", "type: decimal(0,9)")
    with pytest.raises(DescriptorValueError) as caught:
        hub_from_yaml(text)
    assert caught.value.code == "descriptor-value-invalid"
    assert [v.rule for v in caught.value.violations] == ["type-spelling-invalid"]


def test_a_semantic_model_rule_fails_last_and_is_not_a_descriptor_error() -> None:
    # An unresolvable relationship target is a Model Formation concern, so it
    # survives every ingestion phase and fails inside the same call as the
    # representation-independent error — never as a `DescriptorError`.
    text = _YAML.replace(
        "target: { entity: Author, attribute: id }", "target: { entity: Ghost, attribute: id }"
    )
    with pytest.raises(MetamodelValidationError) as caught:
        hub_from_yaml(text)
    assert not isinstance(caught.value, DescriptorError)


# --------------------------------------------------------------------------- #
# Export over both frontends.                                                 #
# --------------------------------------------------------------------------- #
def test_both_frontends_export_the_same_canonical_document() -> None:
    class_backed, _ = _class_backed()
    assert export_document(class_backed) == export_document(hub_from_yaml(_YAML))


def test_exported_text_is_byte_identical_on_repeat_and_re_ingests() -> None:
    built = hub_from_yaml(_YAML)
    as_json, as_yaml = export_json(built), export_yaml(built)
    assert (export_json(built), export_yaml(built)) == (as_json, as_yaml)
    assert export_document(hub_from_json(as_json)) == export_document(built)
    assert export_document(hub_from_yaml(as_yaml)) == export_document(built)


def test_export_reads_a_json_compatible_tree_of_ordinary_containers() -> None:
    document = export_document(hub_from_yaml(_YAML))
    assert type(document) is dict
    entities = document["entities"]
    assert type(entities) is list
    assert all(type(entity) is dict for entity in cast("list[object]", entities))
    assert json.loads(json.dumps(document)) == document


@pytest.mark.parametrize(
    ("door", "serializer", "target"),
    [(export_json, "json", "json"), (export_yaml, "yaml", "yaml")],
)
def test_a_serialization_defect_surfaces_as_an_export_error_with_no_partial_output(
    monkeypatch: pytest.MonkeyPatch,
    door: Callable[[MetamodelHub], str],
    serializer: str,
    target: str,
) -> None:
    # Export renews no validation, so the only way a text door can fail is an
    # implementation defect in the serializer it composes. Inducing one is the
    # only way to reach that boundary.
    built = hub_from_yaml(_YAML)
    before = export_document(built)

    class _Broken:
        @staticmethod
        def dumps(*_args: object, **_kwargs: object) -> str:
            raise TypeError("induced serialization defect")

        safe_dump = dumps

    monkeypatch.setattr(hub_module, serializer, _Broken)
    with pytest.raises(DescriptorExportError) as caught:
        door(built)
    assert caught.value.code == "descriptor-export-failed"
    assert caught.value.target == target
    assert isinstance(caught.value.cause, TypeError)
    assert not isinstance(caught.value, DescriptorError)
    monkeypatch.undo()
    assert export_document(built) == before
