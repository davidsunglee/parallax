"""Provisioning statement-generation unit tests (Docker-free).

Fixture-load statement generation is pure and proven here without a container:
rows resolved through each Entity Layout view, with value-object documents
wrapped for a ``jsonb`` bind. The container lifecycle itself is proven by the
Docker provider lane.

DDL is not this module's: ``schema_statements`` delegates to the shipped
generator and holds no composition of its own, so the statements themselves are
proven at that generator's interface (``test_schema_delta.py``) and only the
dialect it is handed is proven here.
"""

from __future__ import annotations

from typing import cast

import pytest

from parallax.conformance import provision
from parallax.core.internal.base import UsageError
from parallax.core.internal.db_port import StructuredDocument
from tests.unit._corpus_model_support import corpus
from tests.unit._document_layout_support import document_model
from tests.unit._inheritance_family_support import tph_family_with_a_value_object
from tests.unit._second_dialect import BACKTICKED

_MODELS = corpus()


def test_schema_statements_spell_through_the_dialect_they_are_given() -> None:
    # The provisioner passes its adapter's dialect straight through, so a second
    # dialect's quoting reaches the DDL without this path knowing a dialect name.
    (ddl,) = provision.schema_statements(_MODELS["grade"], BACKTICKED)
    assert "`id`" in ddl


def test_fixture_statements_tpcs_has_no_tag_assignment() -> None:
    fixtures = provision.load_fixtures("models/document.yaml")
    statements = provision.fixture_statements(_MODELS["document"], fixtures)
    (invoice_sql, _binds) = statements[0]
    assert "kind" not in invoice_sql


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


def test_fixture_statements_preserve_unknown_value_object_members() -> None:
    fixtures = provision.load_fixtures("models/customer.yaml")
    statements = provision.fixture_statements(_MODELS["customer"], fixtures)
    location = next(
        binds
        for sql, binds in statements
        if sql.startswith("insert into location ") and binds[0] == 100
    )

    address = location[-1]
    assert isinstance(address, StructuredDocument)
    document = cast("dict[str, object]", address.document)
    geo = cast("dict[str, object]", document["geo"])
    assert geo["zip"] == "0150"


def test_load_fixtures_missing_model_is_empty() -> None:
    assert provision.load_fixtures("models/does-not-exist.yaml") == {}


_GRADE_ROW = {"id": 1, "ordinal": 1, "label": "low"}


@pytest.mark.parametrize(
    ("model", "fixtures", "refusal"),
    [
        ("grade", {"parallax.compatibility.Grade": "not-a-list"}, "must be a list of rows"),
        ("grade", {"parallax.compatibility.Grade": None}, "must be a list of rows"),
        (
            "grade",
            {"parallax.compatibility.Grade": [_GRADE_ROW, "not-a-mapping"]},
            "must be a mapping",
        ),
        (
            "grade",
            {"parallax.compatibility.Grade": [{**_GRADE_ROW, "unknownKey": "x"}]},
            r"names \['unknownKey'\]",
        ),
        (
            "grade",
            {"parallax.compatibility.Grdae": [_GRADE_ROW]},
            "'parallax.compatibility.Grdae' names no Entity",
        ),
        (
            "grade",
            {"parallax.compatibility.Grade": [_GRADE_ROW], "Grade": [_GRADE_ROW]},
            "blocks 'parallax.compatibility.Grade' and 'Grade' both name",
        ),
        ("document", {"FinancialDocument": [{"id": 1}]}, "which owns no rows"),
        ("shared-local-name", {"SharedVariant": [{"id": 7}]}, "'SharedVariant' is ambiguous"),
        (
            "shared-local-name",
            {"archive.SharedVariant": [{"id": 1}], "SharedVariant": [{"id": 7}]},
            "'SharedVariant' is ambiguous",
        ),
    ],
)
def test_fixture_statements_refuse_a_malformed_fixture(
    model: str, fixtures: dict[str, object], refusal: str
) -> None:
    with pytest.raises(ValueError, match=refusal):
        provision.fixture_statements(_MODELS[model], fixtures)


def test_fixture_statements_refuse_infinity_for_an_ordinary_timestamp() -> None:
    fixtures = {"Event": [{"id": 1, "occurredAt": "infinity"}]}

    with pytest.raises(UsageError):
        provision.fixture_statements(_MODELS["event"], fixtures)


def test_fixture_statements_tph_resolves_an_inherited_value_object_by_name() -> None:
    meta = tph_family_with_a_value_object()
    fixtures = {"Leaf": [{"id": 1, "x": 2, "meta": {"a": 1}}]}
    (sql, binds) = provision.fixture_statements(meta, fixtures)[0]
    assert "meta" in sql
    assert any(isinstance(bind, StructuredDocument) for bind in binds)


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
        StructuredDocument(
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
    assert binds[1] == StructuredDocument({"displayName": None, "tags": []})


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
    assert binds == [3, StructuredDocument({})]


def test_fixture_statements_spell_every_collection_element_and_keep_a_malformed_carrier() -> None:
    fixtures = {
        "parallax.compatibility.CollectionTwinItem": [
            {"id": 1, "amounts": ["1.50", "7.00"], "tags": "not-an-array", "parts": []}
        ]
    }

    ((_sql, columns_binds),) = provision.fixture_statements(
        _MODELS["scalar-collection-layout-twin-columns"], fixtures
    )
    ((_sql, document_binds),) = provision.fixture_statements(
        _MODELS["scalar-collection-layout-twin-document"], fixtures
    )

    amounts, tags = (cast("StructuredDocument", bind).document for bind in columns_binds[1:3])
    assert (amounts, tags) == (("1.50", "7.00"), "not-an-array")
    document = cast("dict[str, object]", cast("StructuredDocument", document_binds[1]).document)
    assert (document["amounts"], document["tags"], document["flags"]) == (
        ("1.50", "7.00"),
        "not-an-array",
        (),
    )
