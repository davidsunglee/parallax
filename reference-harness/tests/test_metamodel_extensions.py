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


def _emitted_columns(create_table_sql: str) -> list[str]:
    """The column identifiers a ``create table`` statement declares, in order.

    Each column / constraint clause is emitted on its own indented line; this
    returns the leading identifier of every *column* clause (skipping the
    ``primary key`` / ``unique`` constraint clauses), so a test can assert exactly
    which columns the DDL emits.
    """
    columns: list[str] = []
    for raw_line in create_table_sql.splitlines():
        line = raw_line.strip().rstrip(",")
        if not line or line.startswith("create table") or line == ")":
            continue
        token = line.split()[0]
        if token in {"primary", "unique", "foreign", "constraint", "check"}:
            continue
        columns.append(token)
    return columns


# The members declared INSIDE the `address` value object (nested value objects and
# inner attributes at every depth) — none of which may ever surface as a physical
# column: they all live in the one `address` document column. Kept in sync with
# models/customer.yaml.
_NESTED_MEMBER_NAMES = frozenset(
    {
        "street",
        "city",
        "geo",
        "country",
        "elevation",
        "point",
        "lat",
        "lon",
        "phones",
        "type",
        "number",
    }
)


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
    assert value_object["cardinality"] == "one"
    # The recursive shape does not change column order: scalar attributes first,
    # then the ONE structured-document column per top-level value object.
    assert list(column_order(model.root_entity)) == ["id", "name", "address"]
    assert value_object["column"] in column_order(model.root_entity)
    (create,) = ddl_for(model, "postgres")
    assert f"{value_object['column']} jsonb" in create


def test_value_object_declares_recursive_typed_structure() -> None:
    """The `address` value object declares typed attributes, nested value objects
    to arbitrary depth (geo -> point), and a to-many member (phones) — and no
    nested value object or inner attribute carries a storage `column`/`mapping`."""
    model = load_model(COMPATIBILITY_ROOT, "models/customer.yaml")
    (address,) = model.root_entity.value_objects
    assert [attribute["name"] for attribute in address["attributes"]] == ["street", "city"]

    nested = {vo["name"]: vo for vo in address["valueObjects"]}
    assert set(nested) == {"geo", "phones"}
    # geo is to-one (defaulted), phones is to-many.
    assert nested["geo"].get("cardinality", "one") == "one"
    assert nested["phones"]["cardinality"] == "many"

    # Third-level nesting: geo -> point, with numeric lat/lon attributes.
    (point,) = nested["geo"]["valueObjects"]
    assert point["name"] == "point"
    assert {attribute["name"] for attribute in point["attributes"]} == {"lat", "lon"}

    # No nested value object and no inner attribute, at any depth, carries a
    # storage property — the whole composite lives in the one document column.
    def _assert_no_storage_props(vo: dict) -> None:
        for attribute in vo.get("attributes", []):
            assert "column" not in attribute, f"attribute {attribute['name']} must not carry a column"
        for child in vo.get("valueObjects", []):
            assert "column" not in child, f"nested {child['name']} must not carry a column"
            assert "mapping" not in child, f"nested {child['name']} must not carry a mapping"
            _assert_no_storage_props(child)

    _assert_no_storage_props(address)


def test_value_object_ddl_emits_one_document_column_and_no_nested_columns() -> None:
    """DDL emits exactly ONE structured-document column per top-level value object
    and NEVER a column for any nested value object or inner attribute — on every
    dialect. The two-loop ddl_builder shape never walks the nested structure."""
    model = load_model(COMPATIBILITY_ROOT, "models/customer.yaml")
    for dialect, document_type in {"postgres": "jsonb", "mariadb": "json"}.items():
        (create,) = ddl_for(model, dialect)
        emitted = _emitted_columns(create)
        # Exactly the scalar attributes plus the one document column, in order.
        assert emitted == ["id", "name", "address"]
        # Exactly one document column, mapped to the dialect's structured type.
        assert f"address {document_type}" in create
        assert create.count(f" {document_type}") == 1
        # No nested member (value object or inner attribute) becomes a column.
        assert _NESTED_MEMBER_NAMES.isdisjoint(emitted)


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
