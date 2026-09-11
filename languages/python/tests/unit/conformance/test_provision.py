"""Provisioning statement-generation unit tests (Docker-free).

Fixture-load statement generation is pure and proven here without a container:
rows resolved through each Entity Layout view, with value-object documents
wrapped for a ``jsonb`` bind, beside the per-case reset statements. The container
lifecycle itself is proven by the Docker provider lane.

DDL is not this module's: ``schema_statements`` delegates to the shipped
generator and holds no composition of its own, so the statements themselves are
proven at that generator's interface (``test_schema_delta.py``) and only the
delegation is proven here.
"""

from __future__ import annotations

from typing import cast

import pytest
from _corpus_model_support import corpus, corpus_records, formed
from _document_layout_support import document_model
from _inheritance_family_support import tph_family_with_a_value_object
from _second_dialect import BACKTICKED

from parallax.conformance import provision
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.wire import WireDecodingError
from parallax.descriptor._records import (
    AsOfAxisMetadata,
    Attribute,
    Entity,
    Metamodel,
)
from parallax.evolution.model_evolution import ABSENT, evolve
from parallax.evolution.schema_delta import schema_delta

_RECORDS = corpus_records()
_MODELS = corpus()


def test_schema_statements_are_the_generator_s_provisioning_delta() -> None:
    # The provisioner composes no DDL: what it returns IS the Schema Delta for
    # the Unilateral Evolution from ABSENT, statement for statement.
    model = _MODELS["error-cases"]
    assert provision.schema_statements(model) == list(
        schema_delta(evolve(ABSENT, model), POSTGRES).statements
    )


def test_schema_statements_spell_through_the_dialect_they_are_given() -> None:
    # The provisioner passes its adapter's dialect straight through, so a second
    # dialect's quoting reaches the DDL without this path knowing a dialect name.
    (ddl,) = provision.schema_statements(_MODELS["grade"], BACKTICKED)
    assert "`id`" in ddl


def test_reset_statements() -> None:
    assert provision.reset_statements() == [
        "drop schema if exists public cascade",
        "create schema public",
    ]


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


def test_fixture_statements_preserve_unknown_value_object_members() -> None:
    fixtures = provision.load_fixtures("models/customer.yaml")
    statements = provision.fixture_statements(_MODELS["customer"], fixtures)
    location = next(
        binds
        for sql, binds in statements
        if sql.startswith("insert into location ") and binds[0] == 100
    )

    address = location[-1]
    assert isinstance(address, JsonDocument)
    document = cast("dict[str, object]", address.value)
    geo = cast("dict[str, object]", document["geo"])
    assert geo["zip"] == "0150"


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


# --------------------------------------------------------------------------- #
# Inheritance-family provisioning value objects (no corpus model combines      #
# inheritance with a value object today; a synthetic family proves the        #
# ancestry-derived DDL/fixture paths carry a value-object member correctly).   #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# TPH shared-table DDL derives from the whole family. This fixture declares a #
# value object and unique index only on a concrete subtype, proving that      #
# descendant-owned members still contribute to the root-owned table.         #
# --------------------------------------------------------------------------- #


def test_fixture_statements_tph_resolves_an_inherited_value_object_by_name() -> None:
    meta = tph_family_with_a_value_object()
    fixtures = {"Leaf": [{"id": 1, "x": 2, "meta": {"a": 1}}]}
    (sql, binds) = provision.fixture_statements(meta, fixtures)[0]
    assert "meta" in sql
    assert any(isinstance(bind, JsonDocument) for bind in binds)


# --------------------------------------------------------------------------- #
# TPCS-family DDL derives through the full ancestry chain. These synthetic    #
# families prove that root-declared unique indices and value objects are      #
# reproduced in each concrete subtype table.                                 #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# The focused Storage Layout composition model: one descriptor carrying the     #
# standalone, table-per-hierarchy, and table-per-concrete-subtype mapping forms #
# side by side, so DDL and fixture shaping are pinned against every layout      #
# answer the facet owns.                                                        #
# --------------------------------------------------------------------------- #


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
