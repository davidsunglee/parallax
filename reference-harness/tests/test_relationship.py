from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from reference_harness.relationship import validate_relationship_types
from reference_harness.schema_validate import _validate_models
from reference_harness.schemas import load_schemas
from reference_harness.value_object_resolve import RejectionError


def _definitions(
    source_type: str, target_type: str, *, qualified: bool = False
) -> list[dict[str, Any]]:
    return [
        {
            "name": "Parent",
            "namespace": "example.owner",
            "table": "parent",
            "attributes": [
                {
                    "name": "id",
                    "type": source_type,
                    **({} if source_type.startswith("decimal") else {"primaryKey": True}),
                }
            ],
            "relationships": [
                {
                    "name": "children",
                    "cardinality": "one-to-many",
                    "join": {
                        "source": "id",
                        "target": {
                            "entity": "example.owner.Child" if qualified else "Child",
                            "attribute": "parentId",
                        },
                    },
                }
            ],
        },
        {
            "name": "Child",
            "namespace": "example.owner",
            "table": "child",
            "attributes": [
                {"name": "id", "type": "int64", "primaryKey": True},
                {"name": "parentId", "type": target_type, "nullable": True},
            ],
            "relationships": [{"name": "parent", "reverseOf": "Parent.children"}],
        },
    ]


@pytest.mark.parametrize("type", ["int32", "int64", "string", "uuid", "decimal(18,2)"])
@pytest.mark.parametrize("qualified", [False, True])
def test_matching_declared_types(type: str, qualified: bool) -> None:
    validate_relationship_types(_definitions(type, type, qualified=qualified))


@pytest.mark.parametrize(
    ("source", "target"),
    [("int32", "int64"), ("string", "uuid"), ("uuid", "bytes"), ("decimal(18,2)", "decimal(18,4)")],
)
def test_mismatch_is_owned_by_the_defining_declaration(source: str, target: str) -> None:
    with pytest.raises(RejectionError) as failure:
        validate_relationship_types(_definitions(source, target))
    assert failure.value.rule == "relationship-join-type-mismatch"
    assert all(
        fact in failure.value.detail
        for fact in (
            "example.owner.Parent.children",
            "example.owner.Parent.id",
            "example.owner.Child.parentId",
            source,
            target,
        )
    )


@pytest.mark.parametrize("side", ["source", "target", "entity"])
def test_unresolved_endpoints_are_not_type_findings(side: str) -> None:
    definitions = _definitions("int32", "int64")
    join = definitions[0]["relationships"][0]["join"]
    if side == "source":
        join["source"] = "absent"
    else:
        join["target"]["entity" if side == "entity" else "attribute"] = "Absent"
    validate_relationship_types(definitions)


def test_reverse_declarations_do_not_compare_a_join() -> None:
    definitions = _definitions("int32", "int64")
    del definitions[0]["relationships"]
    validate_relationship_types(definitions)


@pytest.mark.parametrize("mismatch", [False, True])
def test_inherited_attributes_resolve_on_both_endpoints(mismatch: bool) -> None:
    parent, child = _definitions("uuid", "string" if mismatch else "uuid")
    roots = []
    for definition in (parent, child):
        root = deepcopy(definition)
        root["name"] += "Root"
        root.pop("table")
        root.pop("relationships")
        root["inheritance"] = {"role": "root", "strategy": "table-per-concrete-subtype"}
        definition["attributes"] = []
        definition["inheritance"] = {"role": "concrete-subtype", "parent": root["name"]}
        roots.append(root)
    if mismatch:
        with pytest.raises(RejectionError, match="unequal declared neutral types"):
            validate_relationship_types([*roots, parent, child])
    else:
        validate_relationship_types([*roots, parent, child])


def test_owner_relative_reference_never_falls_back_to_another_namespace() -> None:
    definitions = _definitions("int32", "int64")
    definitions[1]["namespace"] = "example.other"
    validate_relationship_types(definitions)
    definitions[0]["relationships"][0]["join"]["target"]["entity"] = "example.other.Child"
    with pytest.raises(RejectionError):
        validate_relationship_types(definitions)


def test_static_accepted_model_inventory_rejects_a_mutated_join(tmp_path: Path) -> None:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "mismatch.yaml").write_text(
        yaml.safe_dump({"entities": _definitions("int32", "int64")})
    )
    errors: list[str] = []
    _validate_models(tmp_path, load_schemas(Path(__file__))["metamodel.schema.json"], errors)
    assert len(errors) == 1
    assert "relationship-join-type-mismatch" in errors[0]
