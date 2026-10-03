from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest

from parallax.conformance import case_format, models
from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance.class_models import MODELS
from parallax.conformance.graph_stories import GRAPH_STORIES
from parallax.core import (
    MANY_TO_ONE,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    EntityDefinitionError,
    Float32,
    Int32,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    rel,
    relationship,
    storage_layout,
)
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    AttributeIdentity,
    AttributeLocation,
    EntityIdentity,
    PrimaryKey,
    RelationshipIdentity,
    RelationshipLocation,
    Sequence,
    TablePerConcreteSubtype,
)
from parallax.core.model_formation import MetamodelValidationError
from parallax.descriptor import (
    DescriptorSchemaError,
    domain_model_from_document,
    domain_model_from_yaml,
)
from parallax.snapshot import connect
from tests._support.corpus import case_document, case_fixtures
from tests._support.root_ownership import own_root

_ALLOWED: tuple[tuple[str, type, dict[str, Any]], ...] = (
    ("int32", int, {"type": Int32}),
    ("int64", int, {}),
    ("string", str, {}),
    ("uuid", UUID, {}),
)
_EXCLUDED: tuple[tuple[str, type, dict[str, Any]], ...] = (
    ("boolean", bool, {}),
    ("float32", float, {"type": Float32}),
    ("float64", float, {}),
    ("decimal(18,2)", Decimal, {"precision": 18, "scale": 2}),
    ("bytes", bytes, {}),
    ("date", dt.date, {}),
    ("time", dt.time, {}),
    ("timestamp", dt.datetime, {}),
)


def _declared(carrier: Any, options: dict[str, Any], key: Any) -> type[Entity]:
    return type(
        "Identifier",
        (Entity,),
        {
            "__module__": __name__,
            "__annotations__": {"id": Attr[carrier]},
            "id": attr(primary_key=key, **options),
        },
        table="identifier",
    )


def _descriptor(spelling: str, **options: object) -> dict[str, Any]:
    return {
        "entity": {
            "name": "Identifier",
            "table": "identifier",
            "attributes": [
                {"name": "id", "type": spelling, "primaryKey": True, **options},
            ],
        }
    }


@pytest.mark.parametrize(("spelling", "carrier", "options"), _ALLOWED)
@pytest.mark.parametrize(
    "explicit",
    [False, True],
    ids=["descriptor-default-generation", "descriptor-explicit-generation"],
)
def test_both_frontends_accept_every_application_assigned_identifier(
    spelling: str, carrier: Any, options: dict[str, Any], explicit: bool
) -> None:
    typed = DomainModel(_declared(carrier, options, True))
    descriptor = domain_model_from_document(
        _descriptor(spelling, **({"pkGeneration": "application-assigned"} if explicit else {}))
    )
    left, right = (
        typed.meta("Identifier").attribute("id"),
        descriptor.meta("Identifier").attribute("id"),
    )
    assert left is not None and right is not None
    assert left.type == right.type
    assert left.primary_key == right.primary_key == PrimaryKey(APPLICATION_ASSIGNED)


@pytest.mark.parametrize(("spelling", "carrier", "options"), _EXCLUDED)
def test_excluded_scalar_identifiers_fail_at_the_frontend_boundary(
    spelling: str, carrier: Any, options: dict[str, Any]
) -> None:
    with pytest.raises(EntityDefinitionError) as typed:
        _declared(carrier, options, True)
    assert typed.value.code == "entity-option-context-invalid"
    with pytest.raises(DescriptorSchemaError) as descriptor:
        domain_model_from_document(_descriptor(spelling))
    assert descriptor.value.code == "descriptor-schema-invalid"
    assert [(v.path, v.rule) for v in descriptor.value.violations] == [
        (("entity", "attributes", 0, "type"), "enum")
    ]


@pytest.mark.parametrize(("spelling", "carrier", "options"), (*_ALLOWED, *_EXCLUDED))
@pytest.mark.parametrize("sequence", [False, True], ids=["max", "sequence"])
def test_generated_identifiers_remain_integral(
    spelling: str, carrier: Any, options: dict[str, Any], sequence: bool
) -> None:
    generation = Sequence("identifiers") if sequence else MAX
    descriptor_generation: object = (
        {"strategy": "sequence", "name": "identifiers"} if sequence else "max"
    )
    document = _descriptor(spelling, pkGeneration=descriptor_generation)
    if spelling in ("int32", "int64"):
        typed = DomainModel(_declared(carrier, options, generation))
        descriptor = domain_model_from_document(document)
        left, right = (
            typed.meta("Identifier").attribute("id"),
            descriptor.meta("Identifier").attribute("id"),
        )
        assert left is not None and right is not None
        assert left.primary_key == right.primary_key == PrimaryKey(generation)
    else:
        with pytest.raises(EntityDefinitionError) as typed_error:
            _declared(carrier, options, generation)
        assert typed_error.value.code == "entity-option-context-invalid"
        with pytest.raises(DescriptorSchemaError) as descriptor_error:
            domain_model_from_document(document)
        assert all(
            v.path == ("entity", "attributes", 0, "type") and v.rule == "enum"
            for v in descriptor_error.value.violations
        )


@pytest.mark.parametrize(("spelling", "carrier", "options"), _EXCLUDED)
@pytest.mark.parametrize("flag", [False, None], ids=["explicit-non-key", "omitted-non-key"])
def test_excluded_identifier_types_remain_ordinary_scalars(
    spelling: str, carrier: Any, options: dict[str, Any], flag: bool | None
) -> None:
    value_options = dict(options)
    if flag is not None:
        value_options["primary_key"] = flag
    ordinary: type[Entity] = type(
        "Payload",
        (Entity,),
        {
            "__module__": __name__,
            "__annotations__": {"id": Attr[int], "value": Attr[carrier]},
            "id": attr(primary_key=True),
            "value": attr(**value_options),
        },
        table="payload",
    )
    document = _descriptor("int64")
    document["entity"]["attributes"].append(
        {"name": "value", "type": spelling, **({"primaryKey": flag} if flag is not None else {})}
    )
    left = DomainModel(cast("type[Entity]", ordinary)).meta("Payload").attribute("value")
    right = domain_model_from_document(document).meta("Identifier").attribute("value")
    assert left is not None and right is not None
    assert left.type == right.type


def test_key_nullability_is_not_a_new_declaration_restriction() -> None:
    typed = DomainModel(_declared(int | None, {}, True))
    descriptor = domain_model_from_document(_descriptor("int64", nullable=True))
    left, right = (
        typed.meta("Identifier").attribute("id"),
        descriptor.meta("Identifier").attribute("id"),
    )
    assert left is not None and right is not None
    assert left.nullable is True
    assert right.nullable is True


def test_structured_and_collection_identifiers_still_fail_at_class_creation() -> None:
    class Label(ValueObject):
        text: Attr[str]

    for carrier in (Label, tuple[Label, ...], tuple[int, ...]):
        with pytest.raises(EntityDefinitionError):
            _declared(carrier, {}, True)


@pytest.mark.parametrize(
    "case_id",
    [
        "m-relationship-001",
        "m-relationship-002",
        "m-relationship-003",
        "m-relationship-004",
        "m-relationship-008",
        "m-relationship-009",
    ],
)
@pytest.mark.parametrize("descriptor_backed", [False, True], ids=["typed", "descriptor-wire"])
def test_every_identifier_executes_its_matching_graph(
    profile_run: Any, case_id: str, descriptor_backed: bool
) -> None:
    case = next(case for case in case_format.load_cases() if case.case_id == case_id)
    document = case_document(case)
    root_entity = document["when"]["objectQuery"]["target"].rsplit(".", 1)[-1]
    story = next(story for story in GRAPH_STORIES if story.case_id == case_id)
    descriptor = domain_model_from_yaml(
        (models.default_models_dir() / f"{story.model}.yaml").read_text()
    )
    domain = descriptor if descriptor_backed else MODELS[story.model]
    profile_run.reset(model_of(domain), case_fixtures(case))
    observation = LifecycleObservation()
    db = own_root(
        connect(profile_run.port, domain, lifecycle_provider=observation.provider)
    ).using_database_login()
    if descriptor_backed:
        roots = db.wire.find(document["when"]["objectQuery"]).results()
        assert roots == document["then"]["graph"][root_entity]
    else:
        roots = story.run(db).results()
        expected = document["then"]["graph"][root_entity][0]
        (parent,) = roots
        key = UUID(expected["id"]) if root_entity.startswith("Uuid") else expected["id"]
        assert parent.id == key
        assert parent.label == expected["label"]
        assert len(parent.children) == 1
        assert parent.children[0].parent_id == key
        assert parent.children[0].parent is parent
        child_key = expected["children"][0]["id"]
        assert parent.children[0].id == (
            UUID(child_key) if root_entity.startswith("Uuid") else child_key
        )
    assert observation.round_trips == document["then"]["roundTrips"]


def _join_documents(
    key_type: str, referring_type: str, strategy: str, document: bool
) -> dict[str, Any]:
    hierarchy = strategy == "table-per-hierarchy"
    return {
        "entities": [
            {
                "name": "Root",
                "namespace": "identifiers",
                **({"table": "family"} if hierarchy else {}),
                **({"layout": {"document": {"column": "payload"}}} if document else {}),
                "inheritance": {
                    "role": "root",
                    "strategy": strategy,
                    **({"tag": {"column": "kind"}} if hierarchy else {}),
                },
                "attributes": [
                    {"name": "id", "type": key_type, "primaryKey": True},
                    {"name": "label", "type": "string"},
                ],
            },
            {
                "name": "Leaf",
                "namespace": "identifiers",
                **({} if hierarchy else {"table": "leaf"}),
                "inheritance": {
                    "role": "concrete-subtype",
                    "parent": "Root",
                    **({"tagValue": "leaf"} if hierarchy else {}),
                },
                "relationships": [{"name": "links", "reverseOf": "Link.parent"}],
            },
            {
                "name": "Link",
                "namespace": "identifiers",
                "table": "link",
                **({"layout": {"document": {"column": "payload"}}} if document else {}),
                "attributes": [
                    {"name": "id", "type": "int64", "primaryKey": True},
                    {"name": "parentId", "type": referring_type, "nullable": True},
                    {"name": "label", "type": "string"},
                ],
                "relationships": [
                    {
                        "name": "parent",
                        "cardinality": "many-to-one",
                        "join": {
                            "source": "parentId",
                            "target": {"entity": "Leaf", "attribute": "id"},
                        },
                    }
                ],
            },
        ]
    }


def _join_classes(
    key_carrier: Any,
    key_options: dict[str, Any],
    referring_carrier: Any,
    referring_options: dict[str, Any],
    strategy: str,
    document: bool,
) -> tuple[type[Entity], ...]:
    hierarchy = strategy == "table-per-hierarchy"
    root: type[Entity] = type(
        "Root",
        (Entity,),
        {
            "__module__": __name__,
            "__annotations__": {"id": Attr[key_carrier], "label": Attr[str]},
            "id": attr(primary_key=True, **key_options),
        },
        namespace="identifiers",
        inheritance=AbstractRoot(
            TablePerHierarchy("kind") if hierarchy else TablePerConcreteSubtype()
        ),
        **({"table": "family"} if hierarchy else {}),
        **({"layout": Document()} if document else {}),
    )
    leaf: type[Entity] = type(
        "Leaf",
        (root,),
        {
            "__module__": __name__,
            "__annotations__": {"links": "Rel[tuple[Link, ...]]"},
            "links": rel(reverse_of="parent"),
        },
        namespace="identifiers",
        inheritance=ConcreteSubtype(tag_value="leaf") if hierarchy else ConcreteSubtype(),
        **({} if hierarchy else {"table": "leaf"}),
    )
    link: type[Entity] = type(
        "Link",
        (Entity,),
        {
            "__module__": __name__,
            "__annotations__": {
                "id": Attr[int],
                "parent_id": Attr[referring_carrier | None],
                "label": Attr[str],
                "parent": Rel[leaf | None],
            },
            "id": attr(primary_key=True),
            "parent_id": attr(**referring_options),
            "parent": rel(cardinality=MANY_TO_ONE, join=("parent_id", "id")),
        },
        table="link",
        namespace="identifiers",
        **({"layout": Document()} if document else {}),
    )
    return root, leaf, link


@pytest.mark.parametrize(("spelling", "carrier", "options"), _ALLOWED)
@pytest.mark.parametrize("strategy", ["table-per-hierarchy", "table-per-concrete-subtype"])
@pytest.mark.parametrize("document", [False, True], ids=["columns", "document"])
def test_every_identifier_forms_inherited_joins_through_both_frontends(
    spelling: str,
    carrier: Any,
    options: dict[str, Any],
    strategy: str,
    document: bool,
) -> None:
    typed = DomainModel(*_join_classes(carrier, options, carrier, options, strategy, document))
    descriptor = domain_model_from_document(_join_documents(spelling, spelling, strategy, document))
    for domain in (typed, descriptor):
        model = model_of(domain)
        directions = relationship.view(model)
        parent = directions.relationship(
            RelationshipIdentity(EntityIdentity("identifiers", "Link"), "parent")
        )
        links = directions.relationship(
            RelationshipIdentity(EntityIdentity("identifiers", "Leaf"), "links")
        )
        assert parent is not None and links is not None
        assert parent.join.source == links.join.target
        assert parent.join.target == links.join.source
        referring = domain.meta("identifiers.Link").attribute("parentId")
        assert referring is not None and referring.nullable is True
        for entity_name, members in (
            ("Leaf", (("Root", "id"),)),
            ("Link", (("Link", "id"), ("Link", "parentId"))),
        ):
            layout = storage_layout.view(model).entity(EntityIdentity("identifiers", entity_name))
            assert layout is not None
            for owner, member in members:
                assert isinstance(
                    layout.layout.placement(
                        AttributeIdentity(EntityIdentity("identifiers", owner), member)
                    ),
                    storage_layout.DirectColumn,
                )
            payload_owner = "Root" if entity_name == "Leaf" else "Link"
            payload = layout.layout.placement(
                AttributeIdentity(EntityIdentity("identifiers", payload_owner), "label")
            )
            assert isinstance(
                payload, storage_layout.DocumentPath if document else storage_layout.DirectColumn
            )


@pytest.mark.parametrize(
    ("key_index", "referring_index"), [(0, 1), (1, 0), (2, 3), (3, 2), (1, 2), (2, -1)]
)
@pytest.mark.parametrize("strategy", ["table-per-hierarchy", "table-per-concrete-subtype"])
@pytest.mark.parametrize("document", [False, True], ids=["columns", "document"])
def test_both_frontends_report_inherited_addressed_types_before_execution(
    key_index: int,
    referring_index: int,
    strategy: str,
    document: bool,
) -> None:
    key_spelling, key_carrier, key_options = _ALLOWED[key_index]
    ref_spelling, ref_carrier, ref_options = (
        ("bytes", bytes, {}) if referring_index == -1 else _ALLOWED[referring_index]
    )
    for build in (
        lambda: DomainModel(
            *_join_classes(key_carrier, key_options, ref_carrier, ref_options, strategy, document)
        ),
        lambda: domain_model_from_document(
            _join_documents(key_spelling, ref_spelling, strategy, document)
        ),
    ):
        with pytest.raises(MetamodelValidationError) as failure:
            build()
        (issue,) = failure.value.issues
        assert issue.code == "relationship-join-type-mismatch"
        assert issue.location == RelationshipLocation(
            RelationshipIdentity(EntityIdentity("identifiers", "Link"), "parent")
        )
        assert issue.related == (
            AttributeLocation(AttributeIdentity(EntityIdentity("identifiers", "Link"), "parentId")),
            AttributeLocation(AttributeIdentity(EntityIdentity("identifiers", "Leaf"), "id")),
        )
        assert all(
            fact in issue.message for fact in ("identifiers.Link.parentId", "identifiers.Leaf.id")
        )
        type_names = {
            "int32": "Int32",
            "int64": "Int64",
            "string": "String",
            "uuid": "Uuid",
            "bytes": "Bytes",
        }
        assert type_names[key_spelling] in issue.message
        assert type_names[ref_spelling] in issue.message
