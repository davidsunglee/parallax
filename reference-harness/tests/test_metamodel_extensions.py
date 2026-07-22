"""DB-free unit tests for the metamodel schema and derivation contract: the
inheritance and valueObject extensions, plus the typed attribute-default
encodings.

These pin the invariants that need no database:

* the metamodel schema **accepts** the two legal inheritance strategies
  (table-per-hierarchy with a ``tag``/``tagValue`` discriminator,
  table-per-concrete-subtype) and a valueObject mapped to the neutral ``json``
  storage mapping;
* it **rejects** the retired strategies (``table-per-class`` / ``table-per-leaf``)
  and vocabulary (``discriminator`` / ``discriminatorValue``), enforces the
  role-conditional ``table`` / ``attributes`` requirements (resolved Q5), and the
  harness derives a concrete subtype's full inherited attribute chain (plus, for
  table-per-hierarchy, the synthesized tag column) from the ancestry;
* the per-type ``default`` subschemas (m-descriptor "Value encodings") accept a
  well-encoded or explicit-null default for every neutral-type spelling and
  reject type-mismatched or malformed encodings at the schema phase.

The full tag-filter and Postgres read/write golden SQL is exercised end-to-end
against real Postgres by the compatibility suite (m-inheritance-*); these tests
cover the schema/derivation contract, which needs no database.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from reference_harness.case import Entity, Model, discover_cases, load_model
from reference_harness.case_runner import _assert_write_input_columns, _tag
from reference_harness.ddl_builder import _create_table, column_order, ddl_for
from reference_harness.inheritance import (
    INHERITANCE_ABSTRACT_NODE_FIXTURE_ROWS,
    assert_no_abstract_fixture_rows,
)
from reference_harness.paths import schemas_dir
from reference_harness.value_object_resolve import RejectionError

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
    # The abstract root declares the family strategy, tag column, and shared table.
    assert root.definition["inheritance"]["strategy"] == "table-per-hierarchy"
    assert root.definition["inheritance"]["role"] == "root"
    assert root.definition["inheritance"]["tag"]["column"] == "kind"
    assert root.is_abstract
    assert root.table == "payment"
    # Every concrete subtype resolves to the root-owned shared table.
    assert {e.table for e in model.entities if not e.is_abstract} == {"payment"}


def test_table_per_concrete_subtype_model_validates() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/document.yaml")
    assert _is_valid(model.descriptor)
    root = model.entity("Document")
    assert root.definition["inheritance"]["strategy"] == "table-per-concrete-subtype"
    assert root.is_abstract
    assert root.table == ""
    # The intermediate abstract subtype (FinancialDocument) is tableless too.
    assert model.entity("FinancialDocument").is_abstract
    assert model.entity("FinancialDocument").table == ""
    # Each concrete subtype maps to its OWN table (no shared table, no tag) —
    # Invoice/Receipt under FinancialDocument, plus the concrete sibling Memo. The
    # Phase 6 polymorphic owner `Folder` is a plain (non-inheritance) row-owning entity
    # with its own `folder` table.
    tables = {e.table for e in model.entities if not e.is_abstract}
    assert tables == {"invoice", "receipt", "memo", "folder"}
    for name in ("Invoice", "Receipt", "Memo"):
        assert "tag" not in model.entity(name).definition["inheritance"]
        assert "tagValue" not in model.entity(name).definition["inheritance"]


def test_valid_time_only_descriptor_is_outside_the_active_contract() -> None:
    descriptor = {
        "entity": {
            "name": "Reservation",
            "table": "reservation",
            "attributes": [
                {"name": "id", "type": "int64", "primaryKey": True},
                {"name": "valid_start", "type": "timestamp"},
                {"name": "valid_end", "type": "timestamp"},
            ],
            "asOfAxes": [
                {
                    "dimension": "validTime",
                    "startAttribute": "valid_start",
                    "endAttribute": "valid_end",
                }
            ],
        }
    }

    assert not _is_valid(descriptor)


def test_relationship_transition_preserves_exact_namespace_identity() -> None:
    descriptor = {
        "entities": [
            {
                "name": "Source",
                "namespace": "alpha",
                "table": "source",
                "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                "relationships": [
                    {
                        "name": "targets",
                        "cardinality": "one-to-many",
                        "join": {
                            "source": "id",
                            "target": {"entity": "beta.Target", "attribute": "sourceId"},
                        },
                    }
                ],
            },
            {
                "name": "Target",
                "namespace": "beta",
                "table": "target",
                "attributes": [
                    {"name": "id", "type": "int64", "primaryKey": True},
                    {"name": "sourceId", "type": "int64"},
                ],
                "relationships": [{"name": "source", "reverseOf": "alpha.Source.targets"}],
            },
            {
                "name": "Target",
                "namespace": "alpha",
                "table": "other_target",
                "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
            },
        ]
    }
    model = Model(Path("namespace-collision.yaml"), descriptor)

    source = model.entity("alpha.Source")
    declaration = source.relationship_by_name("targets")
    assert declaration["join"]["source"] == "id"
    relationship = source.relationship_metadata_by_name("targets")
    assert relationship["join"]["target"]["entity"] == "beta.Target"
    assert model.entity(relationship["join"]["target"]["entity"]).canonical_name == "beta.Target"
    with pytest.raises(KeyError):
        model.entity("Target")


def test_concrete_subtype_derives_the_full_inherited_attribute_chain() -> None:
    # A concrete subtype does not repeat inherited attributes; the harness derives
    # the full ancestry chain (root -> ... -> self). For table-per-hierarchy it also
    # synthesizes the framework-owned tag column after the primary key.
    payment = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    assert list(column_order(payment.entity("CardPayment"))) == [
        "id",
        "kind",
        "amount",
        "card_network",
    ]
    # table-per-concrete-subtype: the concrete table carries the full inherited chain,
    # with NO tag column. Invoice's chain threads the root (id, title, folder_id) and
    # the intermediate abstract subtype FinancialDocument (currency) before its own
    # amount_due. folder_id is the Phase 6 polymorphic-owner FK on the root Document.
    document = load_model(COMPATIBILITY_ROOT, "models/document.yaml")
    assert list(column_order(document.entity("Invoice"))) == [
        "id",
        "title",
        "folder_id",
        "currency",
        "amount_due",
    ]
    # The concrete sibling Memo sits directly under the root, so it inherits only the
    # root chain (id, title, folder_id) — NOT FinancialDocument's currency — plus body.
    assert list(column_order(document.entity("Memo"))) == ["id", "title", "folder_id", "body"]


def test_intermediate_abstract_subtype_inheritance_chain() -> None:
    # The animal family threads an intermediate abstract subtype (Pet) between the
    # root (Animal) and concrete leaves (Dog/Cat); a concrete sibling (WildBoar) sits
    # directly under the root, so it does NOT inherit Pet's licenseId.
    model = load_model(COMPATIBILITY_ROOT, "models/animal.yaml")
    assert _is_valid(model.descriptor)
    assert model.entity("Pet").is_abstract
    assert list(column_order(model.entity("Dog"))) == [
        "id",
        "kind",
        "name",
        "owner_id",
        "license_id",
        "bark_volume",
    ]
    # WildBoar is under Animal directly, so it inherits name + owner_id (root) but NOT
    # license_id (Pet).
    boar_columns = list(column_order(model.entity("WildBoar")))
    assert boar_columns == ["id", "kind", "name", "owner_id", "tusk_length"]
    assert "license_id" not in boar_columns


def test_value_object_model_validates_and_maps_to_dialect_json() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/customer.yaml")
    assert _is_valid(model.descriptor)
    (value_object,) = model.root_entity.value_objects
    assert "mapping" not in value_object
    assert value_object["multiplicity"] == "one"
    # The recursive shape does not change column order: scalar attributes first,
    # then the ONE structured-document column per top-level value object.
    assert list(column_order(model.root_entity)) == ["id", "name", "address"]
    assert value_object["column"] in column_order(model.root_entity)
    # customer.yaml gained a VO-bearing sibling `Location` table in COR-3 Phase 5b, so
    # `ddl_for` now returns one CREATE per table; select the root Customer's.
    (create,) = [c for c in ddl_for(model, "postgres") if "create table customer (" in c]
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
    assert nested["geo"].get("multiplicity", "one") == "one"
    assert nested["phones"]["multiplicity"] == "many"

    # Third-level nesting: geo -> point, with numeric lat/lon attributes.
    (point,) = nested["geo"]["valueObjects"]
    assert point["name"] == "point"
    assert {attribute["name"] for attribute in point["attributes"]} == {"lat", "lon"}

    # No nested value object and no inner attribute, at any depth, carries a
    # storage property — the whole composite lives in the one document column.
    def _assert_no_storage_props(vo: dict) -> None:
        for attribute in vo.get("attributes", []):
            assert "column" not in attribute, (
                f"attribute {attribute['name']} must not carry a column"
            )
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
        # customer.yaml gained a VO-bearing sibling `Location` table in COR-3 Phase 5b;
        # this per-table invariant is asserted on the root Customer's CREATE.
        (create,) = [c for c in ddl_for(model, dialect) if "create table customer (" in c]
        emitted = _emitted_columns(create)
        # Exactly the scalar attributes plus the one document column, in order.
        assert emitted == ["id", "name", "address"]
        # Exactly one document column, mapped to the dialect's structured type.
        assert f"address {document_type}" in create
        assert create.count(f" {document_type}") == 1
        # No nested member (value object or inner attribute) becomes a column.
        assert _NESTED_MEMBER_NAMES.isdisjoint(emitted)


# --- negative: table-per-class is rejected (the Phase 9 negative test) --------


@pytest.mark.parametrize("strategy", ["table-per-class", "table-per-leaf"])
def test_schema_rejects_rejected_strategies(strategy: str) -> None:
    """``table-per-class`` and ``table-per-leaf`` MUST fail metamodel validation.

    The strategy enum admits ONLY table-per-hierarchy and table-per-concrete-subtype
    (m-inheritance), so a descriptor declaring either rejected strategy is not a valid
    model — proving the exclusion mechanically rather than only in prose.
    """
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    descriptor["entities"][0]["inheritance"]["strategy"] = strategy
    assert not _is_valid(descriptor), f"{strategy} must be rejected by the metamodel schema"


def test_schema_rejects_legacy_discriminator_vocabulary() -> None:
    """The pre-ADR ``discriminator`` / ``discriminatorValue`` keys are REJECTED.

    The inheritance block is closed (``additionalProperties: false``) and names only
    ``tag`` / ``tagValue``, so the retired discriminator vocabulary fails validation.
    """
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    descriptor["entities"][0]["inheritance"]["discriminator"] = {"column": "kind"}
    assert not _is_valid(descriptor)

    descriptor = copy.deepcopy(model.descriptor)
    descriptor["entities"][1]["inheritance"]["discriminatorValue"] = "card"
    assert not _is_valid(descriptor)


def test_schema_rejects_subtype_without_parent() -> None:
    """A non-root participant that omits ``parent`` MUST fail validation (it always
    names the entity it extends)."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    subtype = descriptor["entities"][1]  # CardPayment
    assert subtype["inheritance"]["role"] == "concrete-subtype"
    del subtype["inheritance"]["parent"]
    assert not _is_valid(descriptor)


def test_schema_requires_table_per_hierarchy_root_tag() -> None:
    """A table-per-hierarchy root MUST declare its ``tag`` column; a non-root MUST NOT."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    del descriptor["entities"][0]["inheritance"]["tag"]
    assert not _is_valid(descriptor)

    # A concrete subtype (non-root) MUST NOT declare a tag.
    descriptor = copy.deepcopy(model.descriptor)
    descriptor["entities"][1]["inheritance"]["tag"] = {"column": "kind"}
    assert not _is_valid(descriptor)


def test_schema_rejects_table_per_concrete_subtype_root_tag() -> None:
    """A table-per-concrete-subtype root MUST NOT declare a tag (no shared table)."""
    model = load_model(COMPATIBILITY_ROOT, "models/document.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    assert descriptor["entities"][0]["inheritance"]["strategy"] == "table-per-concrete-subtype"
    descriptor["entities"][0]["inheritance"]["tag"] = {"column": "kind"}
    assert not _is_valid(descriptor)


def test_schema_conditionally_requires_table_and_attributes() -> None:
    """Structural table ownership and inherited-only attribute omission are enforced."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")

    # A table-per-hierarchy root MUST own the shared table.
    descriptor = copy.deepcopy(model.descriptor)
    del descriptor["entities"][0]["table"]
    assert not _is_valid(descriptor)

    # A concrete subtype declaring ONLY inherited attributes MAY omit `attributes`.
    descriptor = copy.deepcopy(model.descriptor)
    del descriptor["entities"][1]["attributes"]
    assert _is_valid(descriptor), "a concrete subtype with only inherited attributes may omit them"


def test_shared_hierarchy_table_ddl_unions_subtype_columns_and_the_derived_tag() -> None:
    """The table-per-hierarchy shared table is the UNION of every concrete subtype's
    columns plus the framework-derived tag column (m-inheritance), even though each
    concrete subtype declares only its own subtype-specific column."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    statements = ddl_for(model, "postgres")
    assert len(statements) == 1, "one shared table for the whole family"
    (create,) = statements
    assert "kind varchar" in create  # the framework-derived tag column
    assert "card_network varchar(16)" in create  # CardPayment's declared column
    assert "tendered numeric(18,2)" in create  # CashPayment's declared column
    assert "amount numeric(18,2)" in create  # the inherited root column


# --- negative: optimistic-lock x temporal composition is rejected (COR-14) ---


def test_schema_rejects_optimistic_locking_on_temporal_entity() -> None:
    """A temporal (as-of) entity that ALSO declares an ``optimisticLocking``
    attribute MUST fail metamodel validation (m-descriptor/m-temporal-read/m-opt-lock, COR-14).

    A Transaction-Time temporal entity DERIVES its optimistic key from the
    Transaction-Time start column (`in_z` is the version analogue), so it carries no
    version column; combining `asOfAxes` with an explicit `optimisticLocking`
    attribute on one entity is invalid. Proven with an inline descriptor (a
    deep-copied real Balance model with the combination injected) rather than a
    fixture file, mirroring the other metamodel-negative tests.
    """
    model = load_model(COMPATIBILITY_ROOT, "models/balance.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    # Balance is a single-`entity` descriptor with `asOfAxes` (processing).
    # Inject `optimisticLocking` on its `value` attribute -> the forbidden combo.
    value_attr = next(a for a in descriptor["entity"]["attributes"] if a["name"] == "value")
    value_attr["optimisticLocking"] = True
    assert not _is_valid(descriptor), (
        "an entity combining optimisticLocking with asOfAxes must be rejected"
    )


# --- negative: at-most-one optimisticLocking attribute per entity (schema level) ---


def test_schema_rejects_two_optimistic_locking_attributes_on_one_entity() -> None:
    """An entity's OWN `attributes` array may CONTAIN at most one item with
    `optimisticLocking: true` (m-descriptor `attribute` / m-opt-lock "The version
    column"; `metamodel.schema.json`'s 2020-12 `contains`/`minContains: 0`/
    `maxContains: 1`). A SCHEMA-level regression pin for that constraint itself:
    without `maxContains: 1`, this two-flag shape passes `just core-schemas` and
    only the language-level descriptor validator (`validate_entity`) would catch
    it — reproduced red (the block temporarily removed) before this test was
    authored.
    """
    model = load_model(COMPATIBILITY_ROOT, "models/wallet.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    # Wallet is plain (non-inheritance, non-temporal): inject TWO int64 attributes
    # each declaring `optimisticLocking: true`, so the ONLY violated rule is
    # "at most one" — not the int32/int64 type restriction (m-opt-lock/DQ8b,
    # already satisfied) or the temporal-composition rule (Wallet declares no
    # `asOfAxes`, covered separately above).
    descriptor["entity"]["attributes"].append(
        {"name": "version", "type": "int64", "column": "version", "optimisticLocking": True}
    )
    descriptor["entity"]["attributes"].append(
        {"name": "revision", "type": "int64", "column": "revision", "optimisticLocking": True}
    )
    assert not _is_valid(descriptor), (
        "an entity declaring two optimisticLocking attributes must be rejected "
        "at the schema level (maxContains: 1)"
    )


# --- typed attribute defaults: encodings are schema-constrained per type -----


def test_default_bearing_model_validates() -> None:
    """The default-bearing corpus model carries every `default` presence form the
    contract distinguishes (m-descriptor "Value encodings"): a canonical decimal
    string at the declared scale, a UTC `+00:00` timestamp instant, a native
    boolean, and an explicit `default: null` (`DefaultValue(null)`, distinct from
    the omitted-key `NoDefault` on `id`)."""
    model = load_model(COMPATIBILITY_ROOT, "models/preference.yaml")
    assert _is_valid(model.descriptor)
    attributes = {a["name"]: a for a in model.root_entity.definition["attributes"]}
    assert "default" not in attributes["id"]  # omitted key == NoDefault
    assert attributes["threshold"]["default"] == "12.30"
    assert attributes["activatedAt"]["default"] == "2024-01-01T00:00:00+00:00"
    assert attributes["notify"]["default"] is True
    assert "default" in attributes["nickname"]  # present null == DefaultValue(null)
    assert attributes["nickname"]["default"] is None


@pytest.mark.parametrize(
    ("attribute", "bad_default"),
    [
        ("threshold", 12.30),  # decimal must be a canonical string, not a JSON number
        ("threshold", "12.3.0"),  # not a decimal digit string
        ("activatedAt", "2024-01-01"),  # timestamp needs the full UTC instant form
        ("activatedAt", "2024-01-01T00:00:00Z"),  # the offset spelling is +00:00, never Z
        ("id", "7"),  # int64 must be a JSON integer, not a digit string
        ("notify", "true"),  # boolean must be a JSON boolean, not a string
    ],
)
def test_schema_rejects_type_mismatched_defaults(attribute: str, bad_default: object) -> None:
    """A `default` whose encoding does not match the declared `type` MUST fail the
    schema phase (the per-type `if/then` subschemas), never leak through to the
    semantic phase as typed garbage."""
    model = load_model(COMPATIBILITY_ROOT, "models/preference.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    target = next(a for a in descriptor["entity"]["attributes"] if a["name"] == attribute)
    target["default"] = bad_default
    assert not _is_valid(descriptor), f"{attribute} default {bad_default!r} must be rejected"


def _descriptor_with_appended_default(spelling: str, default: object) -> dict:
    """A deep copy of the preference model with one synthetic attribute of the
    given neutral-type spelling carrying the given default appended."""
    model = load_model(COMPATIBILITY_ROOT, "models/preference.yaml")
    descriptor = copy.deepcopy(model.descriptor)
    descriptor["entity"]["attributes"].append(
        {"name": "probe", "type": spelling, "column": "probe", "default": default}
    )
    return descriptor


# One well-encoded default per neutral-type spelling (m-descriptor "Value
# encodings"). `json` is the deliberately unconstrained branch: its value space
# is the JSON data model's structured content, so a nested null inside it is
# ordinary content (m-core), while a TOP-LEVEL null on any spelling is always
# DefaultValue(null) — covered by the null-parametrized test below.
_WELL_ENCODED_DEFAULTS = [
    ("boolean", True),
    ("int32", 7),
    ("int64", 9000000000),
    ("float32", 0.5),
    ("float64", -2.5),
    ("decimal(9,2)", "12.30"),
    ("string", "plain"),
    ("bytes", "AQID"),
    ("date", "2024-01-01"),
    ("time", "08:30:00.25"),
    ("timestamp", "2024-06-01T12:00:00.000001+00:00"),
    ("uuid", "123e4567-e89b-12d3-a456-426614174000"),
    ("json", {"tags": ["a", None], "note": None}),
]

_ALL_SPELLINGS = [spelling for spelling, _ in _WELL_ENCODED_DEFAULTS]

# Encodings each constrained spelling's subschema must reject: plain type
# mismatches plus the regex boundaries (canonical decimal digits, two-digit
# date/time fields, the microsecond fractional-digit cap, base64 padding,
# lowercase uuid hex). `json` has no entry — every JSON value is a legal
# `json` default by design.
_REJECTED_DEFAULTS = [
    ("boolean", "true"),  # boolean must be a JSON boolean, not a string
    ("int32", "7"),  # int must be a JSON integer, not a digit string
    ("int64", 7.5),  # a fractional number is not an integer
    ("float32", "0.5"),  # float must be a JSON number, not a string
    ("float64", "NaN"),  # no NaN encoding exists; the string spelling is a mismatch
    ("decimal(9,2)", "012.30"),  # superfluous leading zero breaks the canonical digits
    ("decimal(9,2)", "+12.30"),  # a leading + is invalid; only - is a legal sign
    ("string", 7),  # string must be a JSON string
    ("bytes", "%%not-base64%%"),  # not base64 at all
    ("bytes", "AQI"),  # missing RFC 4648 padding
    ("date", "2024-1-1"),  # calendar fields are two-digit
    ("time", "8:30"),  # wall-clock fields are two-digit hh:mm:ss
    ("time", "08:30:00.1234567"),  # seven fractional digits exceed microseconds
    ("timestamp", "2024-06-01T12:00:00.1234567+00:00"),  # microsecond cap again
    ("uuid", "not-a-uuid"),  # not a hyphenated UUID
    ("uuid", "123E4567-E89B-12D3-A456-426614174000"),  # uppercase is non-canonical
]


@pytest.mark.parametrize(("spelling", "default"), _WELL_ENCODED_DEFAULTS)
def test_schema_accepts_a_well_encoded_default_for_every_spelling(
    spelling: str, default: object
) -> None:
    """Every neutral-type spelling admits a default in its declared wire encoding
    (m-descriptor "Value encodings") — the per-type subschemas constrain, never
    forbid, a typed default."""
    assert _is_valid(_descriptor_with_appended_default(spelling, default)), (
        f"well-encoded {spelling} default {default!r} must validate"
    )


@pytest.mark.parametrize("spelling", _ALL_SPELLINGS)
def test_schema_accepts_a_null_default_for_every_spelling(spelling: str) -> None:
    """`default: null` is `DefaultValue(null)` and is legal for every declared type
    (m-descriptor "`default` presence semantics") — each per-type subschema admits
    null alongside the typed encoding."""
    assert _is_valid(_descriptor_with_appended_default(spelling, None)), (
        f"default: null on a {spelling} attribute must validate"
    )


@pytest.mark.parametrize(("spelling", "bad_default"), _REJECTED_DEFAULTS)
def test_schema_rejects_a_malformed_default_for_every_constrained_spelling(
    spelling: str, bad_default: object
) -> None:
    """A default whose encoding mismatches the declared spelling — wrong JSON type
    or a string outside the canonical pattern — fails the schema phase for every
    constrained spelling (all but the deliberately unconstrained `json`)."""
    assert not _is_valid(_descriptor_with_appended_default(spelling, bad_default)), (
        f"{spelling} default {bad_default!r} must be rejected"
    )


# --- the authored 09xx cases self-describe -----------------------------------


def test_phase9_cases_are_discovered() -> None:
    cases = {c.path.stem: c for c in discover_cases(COMPATIBILITY_ROOT)}
    inheritance = [c for c in cases.values() if "m-inheritance" in c.tags]
    nested = [c for c in cases.values() if "nested" in c.tags]
    assert inheritance, "no inheritance cases discovered"
    assert nested, "no nested/valueObject cases discovered"


# --- inheritance WRITE: the discriminator is derived from the metamodel ------


def test_table_per_hierarchy_write_derives_the_tag_column() -> None:
    """A TPH write derives the tag column from the concrete subtype's declared
    ``tagValue`` (m-inheritance) — it is never carried in the neutral write input.
    The metamodel is the source of the value; the corpus insert case
    (m-inheritance-007) cross-checks against it. The abstract root owns no rows and
    no tagValue, so it derives no tag."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    # A concrete subtype's tag (shared column, own value) comes from the model.
    assert _tag(model.entity("CardPayment")) == ("kind", "card")
    assert _tag(model.entity("CashPayment")) == ("kind", "cash")
    # The abstract root is rowless and carries no tagValue.
    assert _tag(model.entity("Payment")) is None

    cases = {c.path.stem: c for c in discover_cases(COMPATIBILITY_ROOT)}
    tph_insert = cases["m-inheritance-007-tph-insert"]
    # The golden INSERT includes the tag column with the tagValue as its bind, and the
    # ① ↔ ② cross-check accepts the derived column.
    (insert,) = tph_insert.golden_statements("postgres")
    assert "kind" in insert
    assert tph_insert.statement_binds(0)[1] == "card"
    _assert_write_input_columns(tph_insert, "postgres")


def test_table_per_concrete_subtype_write_has_no_tag() -> None:
    """A table-per-concrete-subtype write targets the subtype's own table with no tag
    column (m-inheritance): ``_tag`` is None and the golden INSERT names the concrete
    subtype's table, not a shared family table."""
    cases = {c.path.stem: c for c in discover_cases(COMPATIBILITY_ROOT)}
    tpcs_insert = cases["m-inheritance-010-tpcs-insert"]
    assert _tag(tpcs_insert.model.entity("Invoice")) is None
    (insert,) = tpcs_insert.golden_statements("postgres")
    assert insert.startswith("insert into invoice(")
    _assert_write_input_columns(tpcs_insert, "postgres")


# --- fixture rows are keyed to concrete subtypes only ------------------------


def test_abstract_node_fixture_rows_are_rejected() -> None:
    """An abstract node is rowless (m-inheritance): fixture rows keyed to an abstract
    root / abstract subtype are refused before load."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    assert_no_abstract_fixture_rows(model)  # the migrated corpus model is clean
    # Injecting rows keyed to the abstract root is refused with the named rule.
    bad = Model(
        path=model.path,
        descriptor=model.descriptor,
        fixtures={"Payment": [{"id": 99, "amount": 1.0}]},
    )
    with pytest.raises(RejectionError) as exc:
        assert_no_abstract_fixture_rows(bad)
    assert exc.value.rule == INHERITANCE_ABSTRACT_NODE_FIXTURE_ROWS


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
    # PK + the as-of start columns) is the primary key, not a secondary unique
    # index -- it must NOT produce a redundant `unique (...)` alongside the PK.
    entity = Entity(
        definition={
            "name": "Milestone",
            "table": "milestone",
            "attributes": [
                {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
                {"name": "tx_start", "type": "timestamp", "column": "in_z"},
                {"name": "tx_end", "type": "timestamp", "column": "out_z"},
            ],
            "asOfAxes": [
                {
                    "dimension": "transactionTime",
                    "startAttribute": "tx_start",
                    "endAttribute": "tx_end",
                },
            ],
            "indices": [
                {"name": "milestone_pk", "attributes": ["id", "tx_start"], "unique": True},
            ],
        }
    )
    ddl = _create_table(entity, "postgres")
    assert "primary key (id, in_z)" in ddl
    assert "unique (" not in ddl  # the PK-backed unique index is not re-emitted
