"""Unit tests for the Phase 9 metamodel extensions (inheritance + valueObject).

These pin the DB-free invariants of the two definitely-do metamodel features:

* the metamodel schema **accepts** the two legal inheritance strategies
  (table-per-hierarchy with a discriminator, table-per-leaf) and a valueObject
  mapped to the neutral ``json`` storage mapping, and
* it **rejects** a ``table-per-class`` descriptor (the negative test) and a
  subtype that omits its ``parent``.

The full discriminator-filter and Postgres JSONB read/filter golden SQL is
exercised end-to-end against real Postgres by the compatibility suite (cases
09xx); these tests cover only the schema contract, which needs no database.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from reference_harness.case import Entity, Model, discover_cases, load_model
from reference_harness.ddl_builder import _create_table, column_order, ddl_for
from reference_harness.paths import schemas_dir

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _metamodel_validator() -> Draft202012Validator:
    schema_path = schemas_dir(COMPATIBILITY_ROOT) / "metamodel.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _is_valid(descriptor: dict) -> bool:
    return not list(_metamodel_validator().iter_errors(descriptor))


# --- positive: the legal strategies + valueObject validate -------------------


def test_table_per_hierarchy_model_validates() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    assert _is_valid(model.descriptor)
    root = model.entity("Payment")
    assert root.definition["inheritance"]["strategy"] == "table-per-hierarchy"
    assert root.definition["inheritance"]["discriminator"]["column"] == "kind"
    # Every entity in the hierarchy maps to the SAME shared table.
    assert {e.table for e in model.entities} == {"payment"}


def test_table_per_leaf_model_validates() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/document.yaml")
    assert _is_valid(model.descriptor)
    # Each concrete leaf maps to its OWN table (no shared table).
    tables = {e.table for e in model.entities}
    assert {"invoice", "receipt"}.issubset(tables)


def test_value_object_model_validates_and_maps_to_dialect_json() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/customer.yaml")
    assert _is_valid(model.descriptor)
    (value_object,) = model.root_entity.value_objects
    assert value_object["mapping"] == "json"
    # The valueObject's neutral json column is part of the entity's column order
    # + Postgres DDL, where m-dialect maps it to jsonb.
    assert value_object["column"] in column_order(model.root_entity)
    (create,) = ddl_for(model, "postgres")
    assert f"{value_object['column']} jsonb" in create


# --- negative: table-per-class is rejected (the Phase 9 negative test) --------


def test_schema_rejects_table_per_class() -> None:
    """A ``table-per-class`` descriptor MUST fail metamodel validation (DQ9).

    The strategy enum admits only table-per-hierarchy and table-per-leaf, so a
    descriptor declaring table-per-class is not a valid model — proving the
    exclusion mechanically rather than only in prose.
    """
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    descriptor["entities"][0]["inheritance"]["strategy"] = "table-per-class"
    assert not _is_valid(descriptor), "table-per-class must be rejected by the metamodel schema"


def test_schema_rejects_subtype_without_parent() -> None:
    """A ``subtype`` that omits ``parent`` MUST fail validation (a subtype always
    names the entity it extends)."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    subtype = descriptor["entities"][1]  # CardPayment
    assert subtype["inheritance"]["role"] == "subtype"
    del subtype["inheritance"]["parent"]
    assert not _is_valid(descriptor)


def test_schema_requires_table_per_hierarchy_discriminator_metadata() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    descriptor = copy.deepcopy(model.descriptor)

    root = descriptor["entities"][0]
    del root["inheritance"]["discriminator"]
    assert not _is_valid(descriptor)

    descriptor = copy.deepcopy(model.descriptor)
    subtype = descriptor["entities"][1]
    del subtype["inheritance"]["discriminatorValue"]
    assert not _is_valid(descriptor)


def test_schema_rejects_table_per_leaf_discriminator_metadata() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/document.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    subtype = descriptor["entities"][1]
    assert subtype["inheritance"]["strategy"] == "table-per-leaf"

    subtype["inheritance"]["discriminator"] = {"column": "kind"}
    assert not _is_valid(descriptor)

    descriptor = copy.deepcopy(model.descriptor)
    subtype = descriptor["entities"][1]
    subtype["inheritance"]["discriminatorValue"] = "invoice"
    assert not _is_valid(descriptor)


def test_shared_hierarchy_table_ddl_includes_later_subtype_columns() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    root = descriptor["entities"][0]
    root["attributes"] = [
        attribute
        for attribute in root["attributes"]
        if attribute["column"] not in {"card_network", "tendered"}
    ]
    sparse_root_model = Model(path=model.path, descriptor=descriptor)

    (create,) = ddl_for(sparse_root_model, "postgres")

    assert "card_network varchar(16)" in create
    assert "tendered numeric(18,2)" in create
    assert len(ddl_for(sparse_root_model, "postgres")) == 1


# --- negative: optimistic-lock x temporal composition is rejected (COR-14) ---


def test_schema_rejects_optimistic_locking_on_temporal_entity() -> None:
    """A temporal (as-of) entity that ALSO declares an ``optimisticLocking``
    attribute MUST fail metamodel validation (m-descriptor/m-temporal-read/m-opt-lock, COR-14).

    A processing-axis temporal entity DERIVES its optimistic key from the
    processing-from column (`in_z` is the version analogue), so it carries no
    version column; combining `asOfAttributes` with an explicit `optimisticLocking`
    attribute on one entity is invalid. Proven with an inline descriptor (a
    deep-copied real Balance model with the combination injected) rather than a
    fixture file, mirroring the other metamodel-negative tests.
    """
    model = load_model(COMPATIBILITY_ROOT, "models/balance.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    # Balance is a single-`entity` descriptor with `asOfAttributes` (processing).
    # Inject `optimisticLocking` on its `value` attribute -> the forbidden combo.
    value_attr = next(a for a in descriptor["entity"]["attributes"] if a["name"] == "value")
    value_attr["optimisticLocking"] = True
    assert not _is_valid(descriptor), (
        "an entity combining optimisticLocking with asOfAttributes must be rejected"
    )


# --- the authored 09xx cases self-describe -----------------------------------


def test_phase9_cases_are_discovered() -> None:
    cases = {c.path.stem: c for c in discover_cases(COMPATIBILITY_ROOT)}
    inheritance = [c for c in cases.values() if "m-inheritance" in c.tags]
    nested = [c for c in cases.values() if "nested" in c.tags]
    assert inheritance, "no inheritance cases discovered"
    assert nested, "no nested/valueObject cases discovered"


# --- unique-index DDL emission (Task 5) --------------------------------------


def _entity_with_unique_index() -> Entity:
    return Entity(
        definition={
            "name": "Tag",
            "table": "tag",
            "attributes": [
                {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
                {"name": "name", "type": "string", "column": "name", "maxLength": 64},
            ],
            "indices": [
                {"name": "tag_pk", "attributes": ["id"], "unique": True},
                {"name": "tag_name_uq", "attributes": ["name"], "unique": True},
            ],
        }
    )


def test_non_pk_unique_index_emits_unique_constraint() -> None:
    ddl = _create_table(_entity_with_unique_index(), "postgres")
    assert "primary key (id)" in ddl
    assert "unique (name)" in ddl
    # The PK-backed unique index is NOT re-emitted as a separate UNIQUE clause.
    assert "unique (id)" not in ddl


def test_unique_index_emitted_for_mariadb_too() -> None:
    ddl = _create_table(_entity_with_unique_index(), "mariadb")
    assert "unique (name)" in ddl


def test_temporal_full_key_unique_index_is_not_re_emitted() -> None:
    # A temporal entity whose unique index lists the FULL physical key (declared
    # PK + the as-of fromColumns) is the primary key, not a secondary unique
    # index -- it must NOT produce a redundant `unique (...)` alongside the PK.
    entity = Entity(
        definition={
            "name": "Milestone",
            "table": "milestone",
            "attributes": [
                {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
                {"name": "businessFrom", "type": "timestamp", "column": "from_z"},
                {"name": "businessTo", "type": "timestamp", "column": "thru_z"},
            ],
            "asOfAttributes": [
                {
                    "name": "businessDate",
                    "fromColumn": "from_z",
                    "toColumn": "thru_z",
                    "axis": "business",
                    "toIsInclusive": False,
                    "infinity": "infinity",
                    "default": "now",
                },
            ],
            "indices": [
                {"name": "milestone_pk", "attributes": ["id", "businessFrom"], "unique": True},
            ],
        }
    )
    ddl = _create_table(entity, "postgres")
    assert "primary key (id, from_z)" in ddl
    assert "unique (" not in ddl  # the PK-backed unique index is not re-emitted
