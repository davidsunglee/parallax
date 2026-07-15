"""Provisioning statement-generation unit tests (Docker-free).

The DDL and fixture-load statement generation is pure and proven here without a
container: descriptor-derived ``create table`` DDL in column order (reserved
identifiers quoted, value objects as ``jsonb``), fixtures mapped attribute-name →
column with value-object documents wrapped for a ``jsonb`` bind, and the reset
statements. The container lifecycle itself is proven by the Docker provider lane.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models, provision
from parallax.core.db_port import JsonDocument
from parallax.core.descriptor import (
    AsOfAttribute,
    Attribute,
    Entity,
    Index,
    Inheritance,
    Metamodel,
    ValueObject,
)

pytestmark = pytest.mark.unit

_MODELS = models.load_models()


def test_reset_statements() -> None:
    assert provision.reset_statements() == [
        "drop schema if exists public cascade",
        "create schema public",
    ]


def test_schema_statements_quote_reserved_and_order_columns() -> None:
    (ddl,) = provision.schema_statements(_MODELS["grade"])
    assert ddl == (
        'create table grade (id bigint, "order" integer, label varchar(32), primary key (id))'
    )


def test_schema_statements_map_value_objects_to_jsonb() -> None:
    (ddl,) = [
        stmt
        for stmt in provision.schema_statements(_MODELS["customer"])
        if stmt.startswith("create table customer ")
    ]
    assert "address jsonb" in ddl
    assert "primary key (id)" in ddl


def test_schema_statements_temporal_pk_is_business_key_plus_from_columns() -> None:
    # A temporal entity's physical PK is the business key plus each axis's fromColumn
    # (m-descriptor): audit-only Balance keys on (bal_id, in_z) so successive
    # milestones sharing one business key coexist.
    (audit,) = provision.schema_statements(_MODELS["balance"])
    assert "primary key (bal_id, in_z)" in audit
    # Bitemporal Position keys on the business key plus BOTH from-columns, business
    # axis before processing (from_z then in_z), matching its declared composite index.
    (bitemporal,) = provision.schema_statements(_MODELS["position"])
    assert "primary key (pos_id, from_z, in_z)" in bitemporal


def test_schema_statements_create_the_shared_table_once() -> None:
    # Payment (abstract root) is tableless; its concrete subtypes share ONE table,
    # so exactly one `create table payment` is emitted (not one per subtype).
    tables = provision.schema_statements(_MODELS["payment"])
    payment_tables = [ddl for ddl in tables if ddl.startswith("create table payment ")]
    assert len(payment_tables) == 1


def test_schema_statements_tph_merges_the_whole_family_plus_the_tag_column() -> None:
    # The shared `payment` table physically carries the root's own columns, the
    # tag column, and EVERY concrete's own column (nullable — a card row leaves
    # `tendered` null and a cash row leaves `card_network` null).
    (ddl,) = [stmt for stmt in provision.schema_statements(_MODELS["payment"]) if "payment" in stmt]
    assert ddl == (
        "create table payment (id bigint, amount numeric(18, 2), kind varchar(32), "
        "card_network varchar(16), tendered numeric(18, 2), primary key (id))"
    )


def test_schema_statements_tph_intermediate_abstract_subtype_columns_are_merged_once() -> None:
    # Animal's shared table carries Pet's own `license_id` exactly once, even though
    # two of its three concretes (Dog, Cat) pass through the abstract subtype Pet.
    (ddl,) = [stmt for stmt in provision.schema_statements(_MODELS["animal"]) if "animal" in stmt]
    assert ddl.count("license_id") == 1
    assert "kind varchar(32)" in ddl
    assert "bark_volume integer" in ddl
    assert "indoor boolean" in ddl
    assert "tusk_length numeric(18, 2)" in ddl


def test_schema_statements_tpcs_creates_one_table_per_concrete_with_its_own_ancestry() -> None:
    # Table-per-concrete-subtype: no shared table, no tag column — each concrete's
    # OWN table physically carries its full ancestry-derived chain.
    tables = provision.schema_statements(_MODELS["document"])
    (invoice,) = [t for t in tables if t.startswith("create table invoice ")]
    assert invoice == (
        "create table invoice (id bigint, title varchar(64), folder_id bigint, "
        "currency varchar(3), amount_due numeric(18, 2), primary key (id))"
    )
    (memo,) = [t for t in tables if t.startswith("create table memo ")]
    assert "currency" not in memo  # Memo does not descend from FinancialDocument
    assert "kind" not in invoice and "kind" not in memo


def test_schema_statements_tpcs_temporal_pk_includes_the_root_declared_axes() -> None:
    # Rate (models/rate.yaml): a table-per-concrete-subtype family whose
    # bitemporal axes are declared on the abstract ROOT and inherited by every
    # concrete subtype (m-inheritance "Inherited members") — DepositRate/LoanRate
    # declare NO `asOfAttributes` locally. The physical PK must still be the
    # business key plus EACH axis's from-column (`m-descriptor`), never just the
    # business key alone, or a second milestone for the same id could not be
    # stored.
    tables = provision.schema_statements(_MODELS["rate"])
    (deposit,) = [t for t in tables if t.startswith("create table deposit_rate ")]
    assert "primary key (id, from_z, in_z)" in deposit
    (loan,) = [t for t in tables if t.startswith("create table loan_rate ")]
    assert "primary key (id, from_z, in_z)" in loan
    # Quote (models/quote.yaml): the audit-only (single-axis) TPCS counterpart.
    (spot,) = provision.schema_statements(_MODELS["quote"])
    assert "primary key (id, in_z)" in spot


def test_schema_statements_tph_temporal_pk_includes_the_root_declared_axes() -> None:
    # Instrument (models/instrument.yaml): a table-per-hierarchy family whose
    # bitemporal axes are declared on the abstract ROOT and inherited by every
    # concrete subtype — Bond/Stock declare NO `asOfAttributes` locally. The
    # shared table's physical PK must still be the business key plus EACH
    # axis's from-column, never just the business key alone.
    (ddl,) = [
        stmt for stmt in provision.schema_statements(_MODELS["instrument"]) if "instrument" in stmt
    ]
    assert "primary key (id, from_z, in_z)" in ddl


def test_fixture_statements_tph_binds_the_tag_from_tagvalue_never_the_fixture_row() -> None:
    fixtures = provision.load_fixtures("models/payment.yaml")
    statements = provision.fixture_statements(_MODELS["payment"], fixtures)
    sql, binds = statements[0]
    # The tag column is bound first, from the concrete's OWN declared `tagValue` —
    # never authored in the fixture row (m-inheritance: framework-owned metadata).
    assert sql.startswith("insert into payment (kind, ")
    assert binds[0] == "card"


def test_fixture_statements_tph_resolves_inherited_members_by_name() -> None:
    # A Dog fixture row authors `name` / `ownerId` (Animal's own, inherited) and
    # `licenseId` (Pet's own, inherited) BY NAME alongside its own `barkVolume`.
    fixtures = provision.load_fixtures("models/animal.yaml")
    statements = provision.fixture_statements(_MODELS["animal"], fixtures)
    dog_sql, dog_binds = statements[0]
    assert "name" in dog_sql and "license_id" in dog_sql and "bark_volume" in dog_sql
    assert "Rex" in dog_binds and "L-100" in dog_binds


def test_fixture_statements_load_multiple_milestones_sharing_one_business_key() -> None:
    # fixtures/rate.yaml's DepositRate carries TWO processing milestones
    # sharing business key id=1 (a closed historical correction plus the
    # current row) — the temporal-PK fix (`(id, from_z, in_z)`, never `(id)`)
    # is what admits the second row at all; this is the statement-generation
    # half of that proof (the Docker-backed `m-inheritance-100` API-conformance
    # story provisions it for real).
    fixtures = provision.load_fixtures("models/rate.yaml")
    statements = provision.fixture_statements(_MODELS["rate"], fixtures)
    deposit_inserts = [
        sql for sql, _binds in statements if sql.startswith("insert into deposit_rate")
    ]
    assert len(deposit_inserts) == 2
    binds = [b for sql, b in statements if sql.startswith("insert into deposit_rate")]
    ids = [row[0] for row in binds]
    assert ids == [1, 1]  # same business key, both milestones


def test_fixture_statements_tpcs_has_no_tag_assignment() -> None:
    fixtures = provision.load_fixtures("models/document.yaml")
    statements = provision.fixture_statements(_MODELS["document"], fixtures)
    (invoice_sql, _binds) = statements[0]
    assert "kind" not in invoice_sql


def test_fixture_statements_map_names_to_columns() -> None:
    fixtures = provision.load_fixtures("models/grade.yaml")
    statements = provision.fixture_statements(_MODELS["grade"], fixtures)
    assert len(statements) == 3
    sql, binds = statements[0]
    assert sql == 'insert into grade (id, "order", label) values (?, ?, ?)'
    assert binds == [1, 1, "low"]


def test_fixture_statements_follow_descriptor_column_order_not_mapping_order() -> None:
    # Re-spelling a fixture row with permuted keys must emit byte-identical SQL:
    # columns and binds follow the descriptor `column_order`, never `row.items()`.
    canonical = {"Grade": [{"id": 1, "ordinal": 1, "label": "low"}]}
    permuted = {"Grade": [{"label": "low", "id": 1, "ordinal": 1}]}
    assert provision.fixture_statements(
        _MODELS["grade"], canonical
    ) == provision.fixture_statements(_MODELS["grade"], permuted)
    (sql, binds) = provision.fixture_statements(_MODELS["grade"], permuted)[0]
    assert sql == 'insert into grade (id, "order", label) values (?, ?, ?)'
    assert binds == [1, 1, "low"]


def test_fixture_statements_skip_a_column_the_row_omits() -> None:
    # A fixture row omitting a (nullable) member emits only the present columns,
    # still in descriptor column order — the omitted `label` is skipped.
    fixtures = {"Grade": [{"ordinal": 2, "id": 5}]}
    (sql, binds) = provision.fixture_statements(_MODELS["grade"], fixtures)[0]
    assert sql == 'insert into grade (id, "order") values (?, ?)'
    assert binds == [5, 2]


def test_fixture_statements_wrap_value_objects() -> None:
    fixtures = provision.load_fixtures("models/customer.yaml")
    statements = provision.fixture_statements(_MODELS["customer"], fixtures)
    _sql, binds = statements[0]
    assert any(isinstance(bind, JsonDocument) for bind in binds)


def test_load_fixtures_missing_model_is_empty() -> None:
    assert provision.load_fixtures("models/does-not-exist.yaml") == {}


def test_fixture_statements_skip_non_list_and_non_mapping_rows() -> None:
    fixtures = {
        "Grade": [
            {"id": 1, "ordinal": 1, "label": "low", "unknownKey": "ignored"},
            "not-a-mapping",
        ],
        "Missing": {"not": "a list"},
    }
    statements = provision.fixture_statements(_MODELS["grade"], fixtures)
    # Only the one valid mapping row produces a statement; the unknown key is dropped.
    assert len(statements) == 1
    _sql, binds = statements[0]
    assert binds == [1, 1, "low"]


def test_fixture_statements_skip_a_non_list_entity_block() -> None:
    # An entity whose fixture value is not a list contributes no insert statements.
    assert provision.fixture_statements(_MODELS["customer"], {"Customer": "not-a-list"}) == []


def test_schema_statements_enforce_unique_secondary_indices() -> None:
    # The m-db-error uniqueViolation-via-secondary-index triggers (m-db-error-002/-008)
    # need the declared unique index on Tag.name enforced; the PK-matching indices
    # (widget_pk / tag_pk) emit no redundant constraint beside `primary key (...)`.
    ddl = provision.schema_statements(_MODELS["error-cases"])
    (tag,) = [stmt for stmt in ddl if stmt.startswith("create table tag ")]
    assert "unique (name)" in tag
    (widget,) = [stmt for stmt in ddl if stmt.startswith("create table widget ")]
    assert "unique" not in widget


def test_schema_statements_skip_the_milestone_index_the_temporal_pk_enforces() -> None:
    # A temporal model's declared composite unique index names the as-of attribute
    # (`processingFrom` -> in_z); the physical PK already enforces exactly that
    # column set, so no duplicate `unique (...)` constraint is emitted.
    (audit,) = provision.schema_statements(_MODELS["balance"])
    assert "unique" not in audit


def test_schema_statements_reject_an_unresolvable_unique_index() -> None:
    import dataclasses

    meta = _MODELS["error-cases"]
    (tag_entity,) = [e for e in meta.entities if e.name == "Tag"]
    broken_index = dataclasses.replace(tag_entity.indices[1], attributes=("noSuchAttr",))
    broken_entity = dataclasses.replace(tag_entity, indices=(broken_index,))
    broken_meta = dataclasses.replace(meta, entities=(broken_entity,))
    with pytest.raises(ValueError, match="noSuchAttr"):
        provision.schema_statements(broken_meta)


# --------------------------------------------------------------------------- #
# Inheritance-family provisioning value objects (no corpus model combines      #
# inheritance with a value object today; a synthetic family proves the        #
# ancestry-derived DDL/fixture paths carry a value-object member correctly).   #
# --------------------------------------------------------------------------- #
def _tph_family_with_a_value_object() -> Metamodel:
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(ValueObject(name="meta", column="meta"),),
    )
    leaf = Entity(
        name="Leaf",
        table="root_tbl",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return Metamodel(entities=(root, leaf))


def _tpcs_family_with_a_value_object() -> Metamodel:
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    leaf = Entity(
        name="Leaf",
        table="leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
        value_objects=(ValueObject(name="meta", column="meta"),),
    )
    return Metamodel(entities=(root, leaf))


def test_schema_statements_tph_maps_a_value_object_to_jsonb() -> None:
    (ddl,) = provision.schema_statements(_tph_family_with_a_value_object())
    assert "meta jsonb" in ddl


def test_schema_statements_tpcs_maps_a_value_object_to_jsonb() -> None:
    (ddl,) = provision.schema_statements(_tpcs_family_with_a_value_object())
    assert "meta jsonb" in ddl


def test_fixture_statements_tph_resolves_an_inherited_value_object_by_name() -> None:
    meta = _tph_family_with_a_value_object()
    fixtures = {"Leaf": [{"id": 1, "x": 2, "meta": {"a": 1}}]}
    (sql, binds) = provision.fixture_statements(meta, fixtures)[0]
    assert "meta" in sql
    assert any(isinstance(bind, JsonDocument) for bind in binds)


# --------------------------------------------------------------------------- #
# TPCS-family DDL derivation through the FULL ancestry chain (review Spec-4    #
# fix): as-of axes are already proven against the corpus's own Rate/Quote     #
# family above; these two synthetic families prove the root-declared unique   #
# secondary index and the root-declared value object, neither of which any    #
# corpus model combines with table-per-concrete-subtype today.                #
# --------------------------------------------------------------------------- #
def _tpcs_family_with_a_root_declared_unique_index() -> Metamodel:
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        indices=(Index(name="root_code_uq", attributes=("code",), unique=True),),
    )
    leaf = Entity(
        name="Leaf",
        table="leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return Metamodel(entities=(root, leaf))


def test_schema_statements_tpcs_surfaces_a_root_declared_unique_index() -> None:
    # `code` is declared only on the ROOT, and the index that constrains it is
    # ALSO declared only on the root — invisible from the concrete descriptor
    # alone; the concrete's own generated table must still enforce it.
    (ddl,) = provision.schema_statements(_tpcs_family_with_a_root_declared_unique_index())
    assert "unique (code)" in ddl


def _tpcs_family_with_a_temporal_root_and_matching_index() -> Metamodel:
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        as_of_attributes=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
        indices=(Index(name="root_pk", attributes=("id", "processingDate"), unique=True),),
    )
    leaf = Entity(
        name="Leaf",
        table="leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return Metamodel(entities=(root, leaf))


def test_schema_statements_tpcs_skips_a_root_index_matching_the_temporal_pk() -> None:
    # The root's OWN declared composite unique index names exactly the physical
    # primary key (business key + from-column) the temporal-PK fix already
    # derives; it must not ALSO appear as a redundant `unique (...)` constraint.
    (ddl,) = provision.schema_statements(_tpcs_family_with_a_temporal_root_and_matching_index())
    assert "primary key (id, in_z)" in ddl
    assert "unique" not in ddl


def _tpcs_family_with_a_redundantly_declared_index() -> Metamodel:
    # A malformed-but-tolerated declaration: the ROOT and the CONCRETE each
    # declare their OWN unique index over the SAME resolved column — the chain
    # walk must emit that constraint exactly once, never twice.
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        indices=(Index(name="root_code_uq", attributes=("code",), unique=True),),
    )
    leaf = Entity(
        name="Leaf",
        table="leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
        indices=(Index(name="leaf_code_uq", attributes=("code",), unique=True),),
    )
    return Metamodel(entities=(root, leaf))


def test_schema_statements_tpcs_deduplicates_a_redundant_index_across_the_chain() -> None:
    (ddl,) = provision.schema_statements(_tpcs_family_with_a_redundantly_declared_index())
    assert ddl.count("unique (code)") == 1
