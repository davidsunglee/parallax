from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest

from parallax.conformance import case_format, models
from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance.graph_stories import GRAPH_STORIES
from parallax.conformance.identifier_models import IDENTIFIER_TYPES
from parallax.core import (
    Attr,
    DomainModel,
    Entity,
    EntityDefinitionError,
    Float32,
    Int32,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.core.metamodel import APPLICATION_ASSIGNED, MAX, PrimaryKey, Sequence
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
    ["m-relationship-001", "m-relationship-002", "m-relationship-003", "m-relationship-004"],
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
        (models.default_models_dir() / "identifier-types.yaml").read_text()
    )
    domain = descriptor if descriptor_backed else IDENTIFIER_TYPES
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
        key = UUID(expected["id"]) if root_entity == "UuidParent" else expected["id"]
        assert parent.id == key
        assert parent.label == expected["label"]
        assert len(parent.children) == 1
        assert parent.children[0].parent_id == key
        assert parent.children[0].parent is parent
        child_key = expected["children"][0]["id"]
        assert parent.children[0].id == (
            UUID(child_key) if root_entity == "UuidParent" else child_key
        )
    assert observation.round_trips == document["then"]["roundTrips"]
