"""Provisioning statement-generation unit tests (Docker-free).

The DDL and fixture-load statement generation is pure and proven here without a
container: ``create table`` DDL rendered from the model's compiled Table Layouts
(canonical slot order, effective physical nullability, the layout's physical
primary key, reserved identifiers quoted, documents as ``jsonb``), fixtures
resolved through each Entity Layout view with value-object documents wrapped for
a ``jsonb`` bind, and the reset statements. The container lifecycle itself is
proven by the Docker provider lane.
"""

from __future__ import annotations

import pytest
from _corpus_model_support import corpus, corpus_records, formed
from _document_layout_support import document_model

from parallax.conformance import provision
from parallax.core.db_port import JsonDocument
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.wire import WireDecodingError
from parallax.descriptor._records import (
    AsOfAxisMetadata,
    Attribute,
    Entity,
    Index,
    Inheritance,
    Metamodel,
    ValueObject,
    ValueObjectAttribute,
)

_RECORDS = corpus_records()
_MODELS = corpus()


def test_reset_statements() -> None:
    assert provision.reset_statements() == [
        "drop schema if exists public cascade",
        "create schema public",
    ]


def test_schema_statements_quote_reserved_and_order_columns() -> None:
    (ddl,) = provision.schema_statements(_MODELS["grade"])
    assert ddl == (
        'create table grade (id bigint not null, "order" integer not null, '
        "label varchar(32) not null, primary key (id))"
    )


def test_schema_statements_map_value_objects_to_jsonb() -> None:
    (ddl,) = [
        stmt
        for stmt in provision.schema_statements(_MODELS["customer"])
        if stmt.startswith("create table customer ")
    ]
    assert "address jsonb" in ddl
    assert "primary key (id)" in ddl


def test_schema_statements_temporal_pk_is_business_key_plus_to_columns() -> None:
    # A temporal entity's physical PK is the business key plus each axis's end column
    # (m-storage-layout): audit-only Balance keys on (bal_id, out_z) so successive
    # milestones sharing one business key coexist, and every close-update pins the
    # key columns.
    (audit,) = provision.schema_statements(_MODELS["balance"])
    assert "primary key (bal_id, out_z)" in audit
    # Bitemporal Position keys on the business key plus BOTH end columns, Valid Time
    # before Transaction Time (thru_z then out_z), which is the derived index's order.
    (bitemporal,) = provision.schema_statements(_MODELS["position"])
    assert "primary key (pos_id, thru_z, out_z)" in bitemporal


def test_schema_statements_create_the_shared_table_once() -> None:
    # Payment (abstract root) is tableless; its concrete subtypes share ONE table,
    # so exactly one `create table payment` is emitted (not one per subtype).
    tables = provision.schema_statements(_MODELS["payment"])
    payment_tables = [ddl for ddl in tables if ddl.startswith("create table payment ")]
    assert len(payment_tables) == 1


def test_schema_statements_tph_merges_the_whole_family_plus_the_tag_column() -> None:
    # The shared `payment` table physically carries the root's own columns, the
    # tag column, and EVERY concrete's own column (nullable — a card row leaves
    # `tendered` null and a cash row leaves `card_network` null). The tag occupies
    # its own Discriminator tier, immediately after the identity slots.
    (ddl,) = [stmt for stmt in provision.schema_statements(_MODELS["payment"]) if "payment" in stmt]
    assert ddl == (
        "create table payment (id bigint not null, kind varchar(32) not null, "
        "amount numeric(18, 2) not null, card_network varchar(16), "
        "tendered numeric(18, 2), primary key (id))"
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
        "create table invoice (id bigint not null, title varchar(64) not null, "
        "folder_id bigint, currency varchar(3) not null, "
        "amount_due numeric(18, 2) not null, primary key (id))"
    )
    (memo,) = [t for t in tables if t.startswith("create table memo ")]
    assert "currency" not in memo  # Memo does not descend from FinancialDocument
    assert "kind" not in invoice and "kind" not in memo


def test_schema_statements_tpcs_temporal_pk_includes_the_root_declared_axes() -> None:
    # Rate (models/rate.yaml): a table-per-concrete-subtype family whose
    # bitemporal axes are declared on the abstract ROOT and inherited by every
    # concrete subtype (m-inheritance "Inherited members") — DepositRate/LoanRate
    # declare NO axes locally. The root derives the whole key, and each concrete
    # table carries it: the business key plus EACH axis's end column, never just
    # the business key alone, or a second milestone for the same id could not be
    # stored.
    tables = provision.schema_statements(_MODELS["rate"])
    (deposit,) = [t for t in tables if t.startswith("create table deposit_rate ")]
    assert "primary key (id, thru_z, out_z)" in deposit
    (loan,) = [t for t in tables if t.startswith("create table loan_rate ")]
    assert "primary key (id, thru_z, out_z)" in loan
    # Quote (models/quote.yaml): the audit-only (single-axis) TPCS counterpart.
    (spot,) = provision.schema_statements(_MODELS["quote"])
    assert "primary key (id, out_z)" in spot


def test_schema_statements_tph_temporal_pk_includes_the_root_declared_axes() -> None:
    # Instrument (models/instrument.yaml): a table-per-hierarchy family whose
    # bitemporal axes are declared on the abstract ROOT and inherited by every
    # concrete subtype — Bond/Stock declare NO axes locally. The shared table's
    # physical PK must still be the business key plus EACH axis's end column,
    # never just the business key alone.
    (ddl,) = [
        stmt for stmt in provision.schema_statements(_MODELS["instrument"]) if "instrument" in stmt
    ]
    assert "primary key (id, thru_z, out_z)" in ddl


def test_fixture_statements_tph_binds_the_tag_from_tagvalue_never_the_fixture_row() -> None:
    fixtures = provision.load_fixtures("models/payment.yaml")
    statements = provision.fixture_statements(_MODELS["payment"], fixtures)
    sql, binds = statements[0]
    # The tag column binds at its Discriminator-tier slot, from the concrete's OWN
    # declared `tagValue` — never authored in the fixture row (m-inheritance:
    # framework-owned metadata).
    assert sql.startswith("insert into payment (id, kind, ")
    assert binds[1] == "card"


def test_fixture_statements_tph_resolves_inherited_members_by_name() -> None:
    # A Dog fixture row authors `name` / `ownerId` (Animal's own, inherited) and
    # `licenseId` (Pet's own, inherited) BY NAME alongside its own `barkVolume`.
    fixtures = provision.load_fixtures("models/animal.yaml")
    statements = provision.fixture_statements(_MODELS["animal"], fixtures)
    dog_sql, dog_binds = next((sql, binds) for sql, binds in statements if "Rex" in binds)
    assert "name" in dog_sql and "license_id" in dog_sql and "bark_volume" in dog_sql
    assert "Rex" in dog_binds and "L-100" in dog_binds


def test_fixture_statements_load_multiple_milestones_sharing_one_business_key() -> None:
    # fixtures/rate.yaml's DepositRate carries TWO Transaction-Time milestones
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


def test_fixture_statements_key_shipped_rows_by_their_canonical_spelling() -> None:
    # The shipped corpus keys every fixture block by the Entity's canonical
    # spelling, so the loader's first lookup is the one that hits.
    fixtures = provision.load_fixtures("models/grade.yaml")
    assert set(fixtures) == {"parallax.compatibility.Grade"}
    assert len(provision.fixture_statements(_MODELS["grade"], fixtures)) == 3


def test_fixture_statements_still_accept_an_unambiguous_bare_key() -> None:
    # Input stays permissive: a bare key naming exactly one Entity of the model
    # loads its rows, which is what lets a hand-authored fixture stay terse. The
    # shipped corpus does not rely on this; only the loader's contract does.
    fixtures = {"Grade": [{"id": 1, "ordinal": 1, "label": "low"}]}
    (sql, binds) = provision.fixture_statements(_MODELS["grade"], fixtures)[0]
    assert sql == 'insert into grade (id, "order", label) values (?, ?, ?)'
    assert binds == [1, 1, "low"]


def test_fixture_statements_prefer_the_canonical_key_to_a_bare_one() -> None:
    # A document spelling the same Entity both ways is answered by the exact
    # spelling — the bare key is a fallback, never a competing block.
    fixtures = {
        "parallax.compatibility.Grade": [{"id": 1, "ordinal": 1, "label": "low"}],
        "Grade": [{"id": 2, "ordinal": 2, "label": "mid"}],
    }
    statements = provision.fixture_statements(_MODELS["grade"], fixtures)
    assert [binds for _sql, binds in statements] == [[1, 1, "low"]]


def test_fixture_statements_follow_the_entity_layout_order_not_mapping_order() -> None:
    # Re-spelling a fixture row with permuted keys must emit byte-identical SQL:
    # columns and binds follow the Entity Layout's slot order, never `row.items()`.
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
    # still in Entity Layout slot order — the omitted `label` is skipped.
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


def test_fixture_statements_refuse_infinity_for_an_ordinary_timestamp() -> None:
    fixtures = {"Event": [{"id": 1, "occurredAt": "infinity"}]}

    with pytest.raises(WireDecodingError):
        provision.fixture_statements(_MODELS["event"], fixtures)


def test_fixture_statements_preserve_infinity_for_a_temporal_end_attribute() -> None:
    fixtures = {
        "Balance": [
            {
                "id": 1,
                "acctNum": "A",
                "value": "1.00",
                "txStart": "2026-01-01T00:00:00Z",
                "txEnd": "infinity",
            }
        ]
    }

    ((_sql, binds),) = provision.fixture_statements(_MODELS["balance"], fixtures)
    assert binds[-1] == "infinity"


def test_schema_statements_enforce_unique_secondary_indices() -> None:
    # The m-db-error uniqueViolation-via-secondary-index triggers (m-db-error-002/-008)
    # need the declared unique index on Tag.name enforced; the derived primary-key
    # indices emit no `unique (...)` constraint beside `primary key (...)`.
    ddl = provision.schema_statements(_MODELS["error-cases"])
    (tag,) = [stmt for stmt in ddl if stmt.startswith("create table tag ")]
    assert "unique (name)" in tag
    (widget,) = [stmt for stmt in ddl if stmt.startswith("create table widget ")]
    assert "unique" not in widget


def test_schema_statements_emit_the_milestone_key_only_as_the_primary_key() -> None:
    # A temporal model authors no primary-key index; the derived one becomes
    # `primary key (...)` and is never also emitted as a `unique (...)`.
    (audit,) = provision.schema_statements(_MODELS["balance"])
    assert "unique" not in audit


def test_an_index_naming_an_undeclared_attribute_never_reaches_provisioning() -> None:
    # An accepted model's every Index names a declared Attribute (the resolver's
    # `metamodel-index-attribute-missing`), so provisioning's own unresolvable-
    # column guard is unreachable defensive code — the defect is caught before a
    # model can form.
    import dataclasses

    broken = dataclasses.replace(
        _RECORDS["error-cases"],
        entities=tuple(
            dataclasses.replace(
                entity,
                indices=(dataclasses.replace(entity.indices[0], attributes=("noSuchAttr",)),),
            )
            if entity.name == "Tag"
            else entity
            for entity in _RECORDS["error-cases"].entities
        ),
    )
    with pytest.raises(MetamodelValidationError, match="metamodel-index-attribute"):
        formed(
            dataclasses.replace(
                broken, entities=(next(e for e in broken.entities if e.name == "Tag"),)
            )
        )


# --------------------------------------------------------------------------- #
# Inheritance-family provisioning value objects (no corpus model combines      #
# inheritance with a value object today; a synthetic family proves the        #
# ancestry-derived DDL/fixture paths carry a value-object member correctly).   #
# --------------------------------------------------------------------------- #
def _tph_family_with_a_value_object() -> AcceptedMetamodel:
    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="meta",
                column="meta",
                attributes=(ValueObjectAttribute(name="note", type="string"),),
            ),
        ),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return formed(Metamodel(entities=(root, leaf)))


def _tpcs_family_with_a_value_object() -> AcceptedMetamodel:
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
        value_objects=(
            ValueObject(
                name="meta",
                column="meta",
                attributes=(ValueObjectAttribute(name="note", type="string"),),
            ),
        ),
    )
    return formed(Metamodel(entities=(root, leaf)))


def test_schema_statements_tph_maps_a_value_object_to_jsonb() -> None:
    (ddl,) = provision.schema_statements(_tph_family_with_a_value_object())
    assert "meta jsonb" in ddl


# --------------------------------------------------------------------------- #
# TPH shared-table DDL derives from the whole family. This fixture declares a #
# value object and unique index only on a concrete subtype, proving that      #
# descendant-owned members still contribute to the root-owned table.         #
# --------------------------------------------------------------------------- #
def _tph_family_with_a_descendant_declared_value_object_and_index() -> AcceptedMetamodel:
    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(
            Attribute(name="x", type="int32", column="x"),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        value_objects=(
            ValueObject(
                name="meta",
                column="meta",
                attributes=(ValueObjectAttribute(name="note", type="string"),),
            ),
        ),
        indices=(Index(name="leaf_code_uq", attributes=("code",), unique=True),),
    )
    return formed(Metamodel(entities=(root, leaf)))


def test_schema_statements_tph_surfaces_a_descendant_declared_value_object_and_index() -> None:
    # `meta` and the unique index over `code` are declared ONLY on the
    # concrete subtype `Leaf`, never the root — invisible from `root.
    # value_objects` / `_unique_constraints((root,), ...)` alone; the shared
    # table's DDL must still carry both.
    (ddl,) = provision.schema_statements(
        _tph_family_with_a_descendant_declared_value_object_and_index()
    )
    assert "meta jsonb" in ddl
    assert "unique (code)" in ddl


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
# TPCS-family DDL derives through the full ancestry chain. These synthetic    #
# families prove that root-declared unique indices and value objects are      #
# reproduced in each concrete subtype table.                                 #
# --------------------------------------------------------------------------- #
def _tpcs_family_with_a_root_declared_unique_index() -> AcceptedMetamodel:
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
    return formed(Metamodel(entities=(root, leaf)))


def test_schema_statements_tpcs_surfaces_a_root_declared_unique_index() -> None:
    # `code` is declared only on the ROOT, and the index that constrains it is
    # ALSO declared only on the root — invisible from the concrete descriptor
    # alone; the concrete's own generated table must still enforce it.
    (ddl,) = provision.schema_statements(_tpcs_family_with_a_root_declared_unique_index())
    assert "unique (code)" in ddl


def _tpcs_family_with_a_temporal_root() -> AcceptedMetamodel:
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="txStart", type="timestamp", column="in_z"),
            Attribute(name="txEnd", type="timestamp", column="out_z"),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transaction-time", start_attribute="txStart", end_attribute="txEnd"
            ),
        ),
    )
    leaf = Entity(
        name="Leaf",
        table="leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return formed(Metamodel(entities=(root, leaf)))


def test_schema_statements_tpcs_key_comes_from_the_tableless_root_derived_index() -> None:
    # The tableless root declares both the key and the axes, so it is the Entity
    # that derives the Index; the concrete table it maps carries those components
    # as its `primary key (...)` and no `unique (...)` beside it.
    (ddl,) = provision.schema_statements(_tpcs_family_with_a_temporal_root())
    assert "primary key (id, out_z)" in ddl
    assert "unique" not in ddl


def _entity_with_two_indices_over_one_column() -> AcceptedMetamodel:
    # One entity declaring two DISTINCT unique indices over the SAME resolved
    # column. Each authored Index is its own constraint, so both are emitted: a
    # unique Index is not suppressed for spanning the columns another spans. A
    # cross-member duplicate cannot form (an index names only local attributes,
    # the resolver's `metamodel-index-attribute-not-local`), so a single entity
    # is where a duplicate resolved-column set can legally arise.
    widget = Entity(
        name="Widget",
        table="widget",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        indices=(
            Index(name="widget_code_uq", attributes=("code",), unique=True),
            Index(name="widget_code_uq_dup", attributes=("code",), unique=True),
        ),
    )
    return formed(Metamodel(entities=(widget,)))


def test_schema_statements_renders_every_unique_index_over_one_column() -> None:
    (ddl,) = provision.schema_statements(_entity_with_two_indices_over_one_column())
    assert ddl.count("unique (code)") == 2


# --------------------------------------------------------------------------- #
# The focused Storage Layout composition model: one descriptor carrying the     #
# standalone, table-per-hierarchy, and table-per-concrete-subtype mapping forms #
# side by side, so DDL and fixture shaping are pinned against every layout      #
# answer the facet owns.                                                        #
# --------------------------------------------------------------------------- #
def _storage_layout_ddl(table: str) -> str:
    (ddl,) = [
        statement
        for statement in provision.schema_statements(_MODELS["storage-layout"])
        if statement.startswith(f"create table {table} ")
    ]
    return ddl


def test_schema_statements_standalone_slots_carry_declared_nullability() -> None:
    # A standalone Entity's slots apply to its table's only row owner, so each
    # keeps its declared answer; the identity slot is non-null because the
    # physical primary key selects it. The one top-level document occupies a
    # single `jsonb` column after every scalar tier.
    assert _storage_layout_ddl("layout_profile") == (
        "create table layout_profile (id bigint not null, label varchar(32) not null, "
        "note varchar(64), contact jsonb not null, primary key (id))"
    )


def test_schema_statements_tph_requires_family_wide_but_not_subtype_only_slots() -> None:
    # `amount` is declared on the root, so it applies to every row owner of the
    # shared table and stays physically non-null. `cardNetwork` and `tendered` are
    # each REQUIRED of the concrete Entity declaring them, yet neither applies to
    # the sibling variant's rows, so both physical columns must permit NULL. The
    # framework-owned discriminator is never nullable.
    assert _storage_layout_ddl("layout_payment") == (
        "create table layout_payment (id bigint not null, kind varchar(32) not null, "
        "amount numeric(18, 2) not null, card_network varchar(16), "
        "tendered numeric(18, 2), primary key (id))"
    )


def test_schema_statements_tpcs_tables_repeat_ancestry_and_may_reuse_a_column() -> None:
    # Each concrete table carries the root-owned ancestry slots followed by its own
    # member. The two sibling members are distinct contributors that map to the same
    # physical column spelling in structurally different tables, so each keeps its
    # declared non-null answer.
    assert _storage_layout_ddl("layout_audit") == (
        "create table layout_audit (id bigint not null, title varchar(64) not null, "
        "detail varchar(32) not null, primary key (id))"
    )
    assert _storage_layout_ddl("layout_survey") == (
        "create table layout_survey (id bigint not null, title varchar(64) not null, "
        "detail varchar(32) not null, primary key (id))"
    )


def test_fixture_statements_follow_each_entity_layout_selection() -> None:
    fixtures = provision.load_fixtures("models/storage-layout.yaml")
    statements = provision.fixture_statements(_MODELS["storage-layout"], fixtures)
    emitted = dict(statements)
    card = "insert into layout_payment (id, kind, amount, card_network) values (?, ?, ?, ?)"
    cash = "insert into layout_payment (id, kind, amount, tendered) values (?, ?, ?, ?)"
    # Each shared-table variant binds only its own applicable slots, with the
    # discriminator derived at its canonical position.
    assert emitted[card][:2] == [1, "card"]
    assert emitted[cash][:2] == [2, "cash"]
    # A sibling concrete table's reused column spelling resolves through its own
    # layout rather than the sibling's declaration.
    assert emitted["insert into layout_audit (id, title, detail) values (?, ?, ?)"] == [
        1,
        "Quarterly audit",
        "Ingrid",
    ]
    assert emitted["insert into layout_survey (id, title, detail) values (?, ?, ?)"] == [
        1,
        "Annual survey",
        "Bjorn",
    ]


def test_fixture_statements_omit_an_absent_cell_and_keep_the_document_last() -> None:
    fixtures = provision.load_fixtures("models/storage-layout.yaml")
    statements = provision.fixture_statements(_MODELS["storage-layout"], fixtures)
    profile = [
        (sql, binds) for sql, binds in statements if sql.startswith("insert into layout_profile ")
    ]
    complete, omitted = profile
    assert complete[0] == (
        "insert into layout_profile (id, label, note, contact) values (?, ?, ?, ?)"
    )
    assert isinstance(complete[1][3], JsonDocument)
    # Python omits the absent optional cell entirely rather than binding NULL; the
    # document keeps the final position among the columns that remain.
    assert omitted[0] == "insert into layout_profile (id, label, contact) values (?, ?, ?)"
    assert isinstance(omitted[1][2], JsonDocument)


# --------------------------------------------------------------------------- #
# Relational Document Layout (m-storage-layout). The model is compiled from     #
# Declarations and accepted directly (`_document_layout_support`), installing   #
# only the facets this lane reads; DDL derivation and fixture composition below #
# are the production ones.                                                      #
# --------------------------------------------------------------------------- #
_DOCUMENT = document_model()


def test_schema_statements_render_the_structured_column_last_and_not_null() -> None:
    (marker, person) = provision.schema_statements(_DOCUMENT)
    assert person == (
        "create table person (id bigint not null, payload jsonb not null, primary key (id))"
    )
    # An Entity with no document-resident member still gets the column: the
    # layout is root-owned and every governed row carries a document.
    assert marker == (
        "create table marker (id bigint not null, payload jsonb not null, primary key (id))"
    )
    assert "default" not in person


def test_fixture_statements_compose_one_document_from_the_rows_own_members() -> None:
    (statement,) = provision.fixture_statements(
        _DOCUMENT,
        {
            "parallax.test.Person": [
                {
                    "id": 1,
                    "displayName": "Ada",
                    "score": 7,
                    "joinedOn": "2026-01-15",
                    "address": {"city": "Oslo", "geo": {"country": "NO"}},
                    "tags": [{"label": "founder"}],
                }
            ]
        },
    )
    sql, binds = statement
    assert sql == "insert into person (id, payload) values (?, ?)"
    # Each leaf is authored as the ordinary neutral wire value a direct Column
    # would take and the codec spells it, so one fixture file describes one
    # logical row under either layout.
    assert binds == [
        1,
        JsonDocument(
            {
                "displayName": "Ada",
                "score": 7,
                "joinedOn": "2026-01-15",
                "address": {"city": "Oslo", "geo": {"country": "NO"}},
                "tags": [{"label": "founder"}],
            }
        ),
    ]


def test_fixture_statements_keep_the_three_presence_states_apart() -> None:
    (statement,) = provision.fixture_statements(
        _DOCUMENT,
        {"parallax.test.Person": [{"id": 2, "displayName": None}]},
    )
    _, binds = statement
    # An omitted member contributes no key, an authored null contributes JSON
    # null, and a `many` occurrence always contributes its array.
    assert binds[1] == JsonDocument({"displayName": None, "tags": []})


def test_fixture_statements_refuse_a_non_mapping_many_occurrence_element() -> None:
    fixtures = {
        "parallax.test.Person": [
            {"id": 2, "displayName": "Ada", "tags": [{"label": "one"}, "dropped"]}
        ]
    }
    with pytest.raises(ValueError, match="every many occurrence element must be a mapping"):
        provision.fixture_statements(_DOCUMENT, fixtures)


def test_fixture_statements_bind_the_empty_document_for_a_row_with_no_document_member() -> None:
    (statement,) = provision.fixture_statements(_DOCUMENT, {"parallax.test.Marker": [{"id": 3}]})
    sql, binds = statement
    assert sql == "insert into marker (id, payload) values (?, ?)"
    assert binds == [3, JsonDocument({})]


def test_an_axis_naming_an_unknown_attribute_never_reaches_provisioning() -> None:
    # An accepted model's As-Of Axes reference declared Attributes (the
    # resolver's `metamodel-as-of-attribute-missing`), so provisioning never
    # resolves a milestone column against an unknown attribute.
    malformed = Entity(
        name="MalformedTemporal",
        table="malformed_temporal",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transaction-time",
                start_attribute="missing_tx_start",
                end_attribute="missing_tx_end",
            ),
        ),
    )
    with pytest.raises(MetamodelValidationError, match="metamodel-as-of-attribute"):
        formed(Metamodel(entities=(malformed,)))
