"""Unit tests for the Phase 9 metamodel extensions (inheritance + valueObject).

These pin the DB-free invariants of the two definitely-do metamodel features:

* the metamodel schema **accepts** the two legal inheritance strategies
  (table-per-hierarchy with a discriminator, table-per-leaf) and a valueObject
  mapped to JSONB, and
* it **rejects** a ``table-per-class`` descriptor (the negative test) and a
  subtype that omits its ``parent``.

The full discriminator-filter and JSONB read/filter golden SQL is exercised
end-to-end against real Postgres by the compatibility suite (cases 09xx); these
tests cover only the schema contract, which needs no database.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from reference_harness.case import discover_cases, load_model
from reference_harness.ddl_builder import column_order, ddl_for
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


def test_value_object_model_validates_and_maps_to_jsonb() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/customer.yaml")
    assert _is_valid(model.descriptor)
    (value_object,) = model.root_entity.value_objects
    assert value_object["mapping"] == "jsonb"
    # The valueObject's JSONB column is part of the entity's column order + DDL.
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
    assert not _is_valid(descriptor), (
        "table-per-class must be rejected by the metamodel schema"
    )


def test_schema_rejects_subtype_without_parent() -> None:
    """A ``subtype`` that omits ``parent`` MUST fail validation (a subtype always
    names the entity it extends)."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    subtype = descriptor["entities"][1]  # CardPayment
    assert subtype["inheritance"]["role"] == "subtype"
    del subtype["inheritance"]["parent"]
    assert not _is_valid(descriptor)


# --- the authored 09xx cases self-describe -----------------------------------


def test_phase9_cases_are_discovered() -> None:
    cases = {c.path.stem: c for c in discover_cases(COMPATIBILITY_ROOT)}
    inheritance = [c for c in cases.values() if "inheritance" in c.tags]
    nested = [c for c in cases.values() if "nested" in c.tags]
    assert inheritance, "no inheritance cases discovered"
    assert nested, "no nested/valueObject cases discovered"
