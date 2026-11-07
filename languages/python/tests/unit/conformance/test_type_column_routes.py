"""Every route an Entity is declared through refuses a Column spelled ``_type``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from parallax.conformance import models
from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core.model_formation import MetamodelValidationError
from parallax.descriptor import DescriptorError, domain_model_from_document

_COLLISION = "inheritance-materialization-key-collision"
_KEY = {"name": "id", "type": "int64", "primaryKey": True}


def _ticket(**members: Any) -> dict[str, Any]:
    attributes = [_KEY, *members.pop("attributes", ())]
    return {"entity": {"name": "Ticket", "table": "ticket", "attributes": attributes, **members}}


_ATTRIBUTE = {"attributes": [{"name": "marker", "type": "string", "column": "_type"}]}
_VALUE_OBJECT = {
    "valueObjects": [
        {
            "name": "profile",
            "column": "_type",
            "attributes": [{"name": "label", "type": "string"}],
        }
    ]
}


@pytest.mark.parametrize("members", [_ATTRIBUTE, _VALUE_OBJECT], ids=["attribute", "value-object"])
def test_a_descriptor_may_not_declare_the_type_column(members: dict[str, Any]) -> None:
    with pytest.raises(MetamodelValidationError) as refused:
        domain_model_from_document(_ticket(**members))
    assert [issue.code for issue in refused.value.issues] == [_COLLISION]


def test_a_class_may_not_declare_the_type_column() -> None:
    class Ticket(Entity, table="ticket"):
        id: Attr[int] = attr(primary_key=True)
        marker: Attr[str] = attr(column="_type")

    with pytest.raises(MetamodelValidationError) as refused:
        DomainModel(Ticket)
    assert [issue.code for issue in refused.value.issues] == [_COLLISION]


@pytest.mark.parametrize("members", [_ATTRIBUTE, _VALUE_OBJECT], ids=["attribute", "value-object"])
def test_an_evolution_endpoint_may_not_declare_the_type_column(
    tmp_path: Path, members: dict[str, Any]
) -> None:
    later = tmp_path / "later.yaml"
    later.write_text(yaml.safe_dump(_ticket(**members)))
    with pytest.raises(MetamodelValidationError) as refused:
        models.load_model(later)
    assert [issue.code for issue in refused.value.issues] == [_COLLISION]


def test_a_descriptor_member_cannot_spell_the_type_key() -> None:
    member = {"name": "_type", "type": "string"}
    with pytest.raises(DescriptorError):
        domain_model_from_document(_ticket(attributes=[member]))


def test_a_class_member_cannot_spell_the_type_key() -> None:
    with pytest.raises(ValueError, match="name different sets"):

        class Ticket(Entity, table="ticket"):
            id: Attr[int] = attr(primary_key=True)
            _type: Attr[str]

        DomainModel(Ticket)


def test_a_tag_column_may_spell_the_type_key_because_it_renders_no_key() -> None:
    domain_model_from_document(
        {
            "entities": [
                {
                    "name": "Record",
                    "table": "record",
                    "inheritance": {
                        "role": "root",
                        "strategy": "table-per-hierarchy",
                        "tag": {"column": "_type"},
                    },
                    "attributes": [_KEY],
                },
                {
                    "name": "Note",
                    "inheritance": {
                        "role": "concrete-subtype",
                        "parent": "Record",
                        "tagValue": "note",
                    },
                },
            ]
        }
    )
