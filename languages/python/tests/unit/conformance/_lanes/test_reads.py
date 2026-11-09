"""The read lanes, compiled purely and run against a fake in-memory
``m-db-port`` (no Docker): the golden the compile lane matches, the driver
translation and wire rendering the `then.rows` run reports, the envelope the
graph-form and milestone-set runs report around production's Wire result, the
streamed delivery's refusals, and every refusal the lanes translate into an
``UnclassifiedEngineError`` naming the case.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import case_format
from parallax.conformance._lanes import reads
from parallax.conformance._lifecycle_observation import lifecycle_run
from parallax.conformance._mechanism.envelope import UnclassifiedEngineError
from parallax.core import UnsupportedError
from parallax.core.base import INFINITY, DocumentValue, StructuredDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import MappingRow
from parallax.core.execution import (
    TxnOptions,
)
from parallax.core.execution_lifecycle import ReadStarted
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    MemberIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.read_delivery import InvalidData, StoredDataIssue
from parallax.core.temporal_read import Pin
from parallax.core.write_plan import ObjectKey
from tests._support.case_corpus import case as corpus_case
from tests._support.case_corpus import cases as corpus_cases
from tests.unit.conformance._recording_ports import FakeDbPort, QueueDbPort


def _rows(row: MappingRow | None, key: str) -> list[MappingRow]:
    """A graph leaf's relationship-attached rows, typed for test-side assertions
    (`then.graph`'s wire shape is intentionally a plain ``dict[str, object]``)."""
    assert row is not None
    return cast("list[MappingRow]", row[key])


def _node(nodes: list[MappingRow | None], index: int) -> MappingRow:
    """One published graph position that carries a value.

    A position whose stored state contradicted the model carries ``null``, so a
    test asserting about the node itself states that it expected one.
    """
    node = nodes[index]
    assert node is not None
    return node


def _entry(entry: dict[str, object], key: str) -> MappingRow:
    """A milestone-set `{pin, graph}` entry's own member, typed for test-side
    assertions (`then.graphs`' wire shape is a plain ``dict[str, object]``)."""
    return cast("MappingRow", entry[key])


def _case(case_id: str) -> case_format.Case:
    return corpus_case(case_id, reachable=True)


def _load_case(case_id: str) -> case_format.Case:
    # Loads by id directly from the corpus, independent of `sweep.
    # IMPLEMENTED_MODULES` reachability: these lane-level tests exercise the
    # entry point on its own terms, never gated on whether the case has ALSO
    # been flipped visible in the sweep.
    return corpus_case(case_id)


def test_compile_read_case_matches_golden() -> None:
    emissions, database_calls = reads.compile_read_case(_case("m-value-object-001"), "postgres")
    assert database_calls == 1
    assert emissions[0].case_pointer == "/objectQuery"
    assert emissions[0].sql == (
        "select t0.id, t0.name, not t0.address is null, t0.address from customer t0 "
        "where jsonb_extract_path_text(t0.address, ?) = ?"
    )
    assert emissions[0].binds == ("city", "Oslo")
    assert emissions[0].to_json()["casePointer"] == "/objectQuery"


def test_run_read_case_executes_driver_sql_and_records_rows() -> None:
    port = FakeDbPort([{"id": 1, "name": "Grace"}])
    emissions, rows, database_calls = reads.run_read_case(_case("m-value-object-001"), port)
    assert database_calls == 1
    assert rows == [{"id": 1, "name": "Grace"}]
    assert emissions[0].sql == (
        "select t0.id, t0.name, not t0.address is null, t0.address from customer t0 "
        "where jsonb_extract_path_text(t0.address, ?) = ?"
    )
    driver_sql, driver_binds = port.executed[0]
    assert "%s" in driver_sql and "?" not in driver_sql
    assert driver_binds == ["city", "Oslo"]


def test_run_read_case_materializes_the_type_from_the_tph_tag_column() -> None:
    # m-inheritance-003 (Payment root, table-per-hierarchy): the compiled SELECT
    # projects the raw `kind` tag column; run_read_case materializes `_type`
    # from the tag metadata map at row construction and never leaves the raw tag key
    # on the wire row (m-case-format: an abstract-target row carries `_type`,
    # never the framework-owned tag).
    port = FakeDbPort(
        [
            {
                "id": 1,
                "amount": decimal.Decimal("100.00"),
                "card_network": "Visa",
                "tendered": None,
                "kind": "card",
            }
        ]
    )
    _emissions, rows, _database_calls = reads.run_read_case(_case("m-inheritance-003"), port)
    assert rows == [
        {
            "id": 1,
            "amount": "100.00",
            "card_network": "Visa",
            "tendered": None,
            "_type": "parallax.compatibility.CardPayment",
        }
    ]


def test_run_read_case_materializes_the_type_from_the_tpcs_literal_column() -> None:
    # m-inheritance-050 (Document root, table-per-concrete-subtype): the compiled
    # union-all projects the `family_variant` literal per branch; run_read_case just
    # renames the wire key, no tag map involved.
    port = FakeDbPort(
        [
            {
                "id": 1,
                "title": "Invoice-A",
                "folder_id": 100,
                "currency": "USD",
                "amount_due": decimal.Decimal("120.00"),
                "body": None,
                "paid_amount": None,
                "family_variant": "Invoice",
            }
        ]
    )
    _emissions, rows, _database_calls = reads.run_read_case(_case("m-inheritance-050"), port)
    assert rows[0]["_type"] == "parallax.compatibility.Invoice"
    assert "family_variant" not in rows[0]


def test_run_read_case_concrete_target_read_carries_its_type() -> None:
    # m-inheritance-001 (CardPayment, concrete target): the compiled SELECT never
    # projects a tag/literal column, so the variant is the node's concrete Entity.
    port = FakeDbPort([{"id": 1, "amount": decimal.Decimal("100.00"), "card_network": "Visa"}])
    _emissions, rows, _database_calls = reads.run_read_case(_case("m-inheritance-001"), port)
    assert rows == [
        {
            "id": 1,
            "amount": "100.00",
            "card_network": "Visa",
            "_type": "parallax.compatibility.CardPayment",
        }
    ]


def test_run_read_case_reports_an_unresolvable_target_as_an_engine_error() -> None:
    # The lane's one refusal translation: whatever production raises while
    # resolving, building, or running the request is reported against the case
    # file, so a corpus defect names the case rather than a production frame.
    case = _case("m-value-object-001")
    document = dict(case.document)
    when = dict(cast("Mapping[str, object]", document["when"]))
    query = dict(cast("Mapping[str, object]", when["objectQuery"]))
    query["target"] = "parallax.compatibility.NoSuchEntity"
    when["objectQuery"] = query
    document["when"] = when
    with pytest.raises(UnclassifiedEngineError, match=case.path.name):
        reads.run_read_case(dataclasses.replace(case, document=document), FakeDbPort([]))


def test_the_compile_lane_refuses_a_deferred_execution_feature() -> None:
    # The compile lane runs production's own read gate, Deferred Execution Feature
    # classification included: an adapter whose compile lane accepted a query its
    # own executor would refuse would claim two different supported surfaces. No
    # corpus case authors the combination, so the witness is synthetic — and it
    # never reaches SQL generation, which is the whole point.
    case = case_format.Case(
        path=Path("m-snapshot-read-999-synthetic.yaml"),
        case_id="m-snapshot-read-999",
        shape="read",
        tags=("m-snapshot-read", "slice-snapshot-1"),
        model="models/policy.yaml",
        document={
            "model": "models/policy.yaml",
            "when": {
                "objectQuery": {
                    "target": "parallax.compatibility.Policy",
                    "predicate": {"true": {}},
                    "temporal": {
                        "valid-time": {"asOf": "latest"},
                        "transaction-time": {"history": {}},
                    },
                    "includes": [
                        {"segments": [{"rel": "parallax.compatibility.Policy.coverages"}]}
                    ],
                }
            },
        },
    )
    with pytest.raises(UnclassifiedEngineError) as caught:
        reads.compile_read_case(case, "postgres")
    refusal = caught.value.__cause__
    assert isinstance(refusal, UnsupportedError)
    assert refusal.code == "execution-feature-deferred"
    assert "has deferred snapshot-history-includes and" in refusal.args[1]


def test_compile_rejects_non_read_shape() -> None:
    write_seq = next(c for c in corpus_cases() if c.shape == "writeSequence")
    with pytest.raises(UnclassifiedEngineError, match="only `read`-shape compile"):
        reads.compile_read_case(write_seq, "postgres")


def _synthetic(document: dict[str, object]) -> case_format.Case:
    return case_format.Case(
        path=Path("m-predicate-999-synthetic.yaml"),
        case_id="m-predicate-999",
        shape="read",
        tags=("m-predicate", "slice-snapshot-1"),
        model="models/orders.yaml",
        document=document,
    )


@pytest.mark.parametrize(
    "document, message",
    [
        ({"model": "models/orders.yaml"}, "no `when`"),
        ({"model": "models/orders.yaml", "when": {}}, "no `objectQuery`"),
    ],
)
def test_compile_read_case_reports_missing_fields(
    document: dict[str, object], message: str
) -> None:
    with pytest.raises(UnclassifiedEngineError, match=message):
        reads.compile_read_case(_synthetic(document), "postgres")


# --------------------------------------------------------------------------- #
# Graph reads (m-read-planning / m-snapshot-read): the                            #
# `run_graph_case` / `run_graphs_case` envelope lane. What a root LOOKS like   #
# is the wire materializer's own contract (`test_wire_reads.py`); what is left #
# here is the envelope.                                                        #
# --------------------------------------------------------------------------- #
def test_run_graph_case_renders_root_class_keyed_graph_with_relationships() -> None:
    port = QueueDbPort(
        [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "sku": "A-100",
                    "qty": 5,
                    "price": decimal.Decimal("10.50"),
                    "active": True,
                    "ordered_on": dt.date(2024, 1, 5),
                }
            ],
            [
                {
                    "id": 12,
                    "order_id": 1,
                    "sku": "B-200",
                    "quantity": 1,
                    "shipped_on": dt.date(2024, 2, 15),
                },
                {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
            ],
            [
                {
                    "id": 12,
                    "order_id": 1,
                    "sku": "B-200",
                    "quantity": 1,
                    "shipped_on": dt.date(2024, 2, 15),
                },
                {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
            ],
        ]
    )
    emissions, graph, database_calls, stored_data_issues = reads.run_graph_case(
        _case("m-snapshot-read-001"), port
    )
    assert database_calls == 3
    assert len(emissions) == 3
    assert stored_data_issues is None
    assert [item["id"] for item in _rows(graph["Order"][0], "items")] == [12, 11]
    assert _rows(graph["Order"][0], "itemsByShipDate")[0]["shippedOn"] == "2024-02-15"


def test_run_graph_case_unwinds_a_back_reference_finitely() -> None:
    port = QueueDbPort(
        [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "sku": "A-100",
                    "qty": 5,
                    "price": decimal.Decimal("10.50"),
                    "active": True,
                    "ordered_on": dt.date(2024, 1, 5),
                }
            ],
            [
                {
                    "id": 12,
                    "order_id": 1,
                    "sku": "B-200",
                    "quantity": 1,
                    "shipped_on": dt.date(2024, 2, 15),
                },
                {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
            ],
        ]
    )
    _emissions, graph, database_calls, stored_data_issues = reads.run_graph_case(
        _case("m-snapshot-read-011"), port
    )
    assert database_calls == 2
    assert stored_data_issues is None
    # The back-reference renders its target ONCE, in full, and terminates: the
    # include tree — not a cycle detector — is what bounds the value, so the
    # position carries the ancestor's own members rather than a primary-key stub.
    back = _rows(graph["Order"][0], "items")[0]["order"]
    assert isinstance(back, Mapping)
    assert back["id"] == 1
    assert back["name"] == "Ada"
    assert "items" not in back


def test_run_read_case_states_the_scalars_of_a_read_that_carried_its_value_object() -> None:
    port = FakeDbPort(
        [{"id": 1, "name": "Grace", "address": StructuredDocument({"street": "1 Main"})}]
    )
    _emissions, rows, _database_calls = reads.run_read_case(_case("m-value-object-001"), port)
    assert rows == [{"id": 1, "name": "Grace"}]


def _flattening_refused(*_arguments: object, **_keywords: object) -> list[MappingRow]:
    raise AssertionError("a record reached the flat renderer")


def _rows_case(model: str, target: str) -> case_format.Case:
    """A `then.rows` read of every ``target`` under ``model``."""
    return dataclasses.replace(
        _synthetic(
            {
                "model": model,
                "when": {
                    "objectQuery": {
                        "target": f"parallax.compatibility.{target}",
                        "predicate": {"true": {}},
                    }
                },
                "then": {"rows": []},
            }
        ),
        model=model,
    )


def _traveler_rows_case() -> case_format.Case:
    """A read of Relational Document Layout's Traveler, whose members are all
    document-resident beside the `id` Column: four scalars and two top-level Value
    Objects sharing the one `payload` document."""
    return _rows_case("models/document-layout.yaml", "Traveler")


def _traveler(payload: dict[str, DocumentValue]) -> MappingRow:
    return {"id": 1, "payload": StructuredDocument(payload)}


@pytest.mark.parametrize(
    "address",
    [
        pytest.param({"street": "1 Main", "geo": "unknown"}, id="wrong-kind-one"),
        pytest.param({"street": "1 Main", "phones": "555-0000"}, id="wrong-kind-many"),
        pytest.param({"city": "Oslo"}, id="required-attribute-absent"),
    ],
)
def test_a_record_with_every_issue_under_a_value_object_reads_as_a_row(
    address: dict[str, DocumentValue],
) -> None:
    port = FakeDbPort([{"id": 6, "name": "Rin", "address": StructuredDocument(address)}])
    _emissions, rows, _database_calls = reads.run_read_case(_case("m-value-object-001"), port)
    assert rows == [{"id": 6, "name": "Rin"}]


@pytest.mark.parametrize(
    "occurrence",
    [pytest.param({"address": "unknown"}, id="one"), pytest.param({"tags": "x"}, id="many")],
)
def test_a_document_resident_value_object_issue_leaves_the_scalars_beside_it_stated(
    occurrence: dict[str, DocumentValue],
) -> None:
    port = FakeDbPort([_traveler({"displayName": "Ada", "score": 7, **occurrence})])
    _emissions, rows, _database_calls = reads.run_read_case(_traveler_rows_case(), port)
    assert rows == [{"id": 1, "display_name": "Ada", "score": 7, "joined_on": None, "note": None}]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"displayName": 7}, id="undecodable-scalar"),
        pytest.param({"displayName": 7, "address": "unknown"}, id="beside-a-value-object-issue"),
    ],
)
def test_a_document_resident_scalar_issue_is_refused_before_flattening(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, DocumentValue]
) -> None:
    monkeypatch.setattr(reads, "flat_rows", _flattening_refused)
    with pytest.raises(UnclassifiedEngineError, match="published an InvalidData record"):
        reads.run_read_case(_traveler_rows_case(), FakeDbPort([_traveler(payload)]))


@pytest.mark.parametrize(
    ("model", "row"),
    [
        pytest.param(
            "models/scalar-collection-layout-twin-columns.yaml",
            {"id": 1, "tags": StructuredDocument("not-a-collection")},
            id="own-column",
        ),
        pytest.param(
            "models/scalar-collection-layout-twin-document.yaml",
            {"id": 1, "payload": StructuredDocument({"tags": "not-a-collection"})},
            id="document-resident",
        ),
    ],
)
def test_a_scalar_collection_issue_is_refused_before_flattening(
    monkeypatch: pytest.MonkeyPatch, model: str, row: MappingRow
) -> None:
    monkeypatch.setattr(reads, "flat_rows", _flattening_refused)
    with pytest.raises(UnclassifiedEngineError, match="published an InvalidData record"):
        reads.run_read_case(_rows_case(model, "CollectionTwinItem"), FakeDbPort([row]))


def test_a_value_object_issue_with_no_hydrated_data_is_refused_before_flattening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reads, "flat_rows", _flattening_refused)
    address = StructuredDocument({"street": "1 Main", "city": 7})
    port = FakeDbPort([{"id": 1, "name": "Ada", "address": address}])
    with pytest.raises(UnclassifiedEngineError, match="published an InvalidData record"):
        reads.run_read_case(_case("m-value-object-001"), port)


def test_a_non_hydrating_scalar_issue_is_refused_before_flattening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reads, "flat_rows", _flattening_refused)
    port = FakeDbPort(
        [
            {
                "bal_id": 1,
                "acct_num": "A",
                "val": decimal.Decimal("100.00"),
                "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "out_z": None,
            }
        ]
    )
    with pytest.raises(UnclassifiedEngineError, match="published an InvalidData record"):
        reads.run_read_case(_load_case("m-temporal-read-004"), port)


def _classified_item_port(root_profile: dict[str, DocumentValue]) -> QueueDbPort:
    """`m-storage-layout-027`'s read of one item under ``root_profile``, whose
    included child stores a `profile` omitting its required `street`."""
    return QueueDbPort(
        [
            [{"profile": {"street": "4 Main", "city": "Boston"}}],
            [{"id": 1, "profile": StructuredDocument(root_profile)}],
            [{"id": 12, "item_id": 1, "profile": StructuredDocument({"city": "Oslo"})}],
        ]
    )


@pytest.mark.parametrize(
    "root_profile",
    [
        pytest.param({"street": "1 Main", "city": None}, id="alone"),
        pytest.param({"city": None}, id="mixed-with-the-roots-own-value-object-issue"),
    ],
)
def test_an_issue_under_an_included_nodes_value_object_is_refused_before_flattening(
    monkeypatch: pytest.MonkeyPatch, root_profile: dict[str, DocumentValue]
) -> None:
    monkeypatch.setattr(reads, "flat_rows", _flattening_refused)
    case = _load_case("m-storage-layout-027")
    _emissions, _graph, _calls, records = reads.run_graph_case(
        case, _classified_item_port(root_profile)
    )
    assert records is not None
    assert [record["hydrated"] for record in records] == [True]
    with pytest.raises(UnclassifiedEngineError, match="published an InvalidData record"):
        reads.run_read_case(case, _classified_item_port(root_profile))


_ALPHA_TARGET: Final = "snapshot.materialization.Alpha"


def _same_family_reentry_case() -> case_format.Case:
    """A read of Alpha reaching its own family again through Node.owner → Owner.nodes."""
    model = "models/materialization-stress-columns.yaml"
    query: dict[str, object] = {
        "target": _ALPHA_TARGET,
        "predicate": {"true": {}},
        "includes": [
            {
                "segments": [
                    {"rel": "snapshot.materialization.Node.owner"},
                    {"rel": "snapshot.materialization.Owner.nodes"},
                ]
            }
        ],
    }
    document: dict[str, object] = {
        "model": model,
        "when": {"objectQuery": query},
        "then": {"rows": []},
    }
    return dataclasses.replace(_synthetic(document), model=model)


def _alpha(node_id: int, primary_tag: DocumentValue) -> MappingRow:
    return {
        "id": node_id,
        "owner_id": 7,
        "kind": "alpha",
        "primary_tag": StructuredDocument(primary_tag),
    }


def _same_family_reentry_port(
    root_tag: DocumentValue, included_tag: DocumentValue = None
) -> QueueDbPort:
    root = _alpha(1, root_tag)
    return QueueDbPort(
        [
            [root],
            [{"id": 7, "name": "Owner", "favorite_id": None}],
            [root, _alpha(2, included_tag)],
        ]
    )


_WRONG_KIND_TAG: Final[DocumentValue] = {"details": 42}


def test_an_issue_on_an_included_node_of_the_roots_own_family_is_refused_before_flattening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reads, "flat_rows", _flattening_refused)
    case = _same_family_reentry_case()
    _emissions, _graph, _calls, records = reads.run_graph_case(
        case, _same_family_reentry_port(None, _WRONG_KIND_TAG)
    )
    assert records is not None
    with pytest.raises(UnclassifiedEngineError, match="published an InvalidData record"):
        reads.run_read_case(case, _same_family_reentry_port(None, _WRONG_KIND_TAG))


def test_the_roots_own_value_object_issue_reads_as_a_row_beside_a_conforming_reentry() -> None:
    _emissions, rows, _calls = reads.run_read_case(
        _same_family_reentry_case(), _same_family_reentry_port(_WRONG_KIND_TAG)
    )
    assert [row["id"] for row in rows] == [1]


_CUSTOMER: Final = EntityIdentity("parallax.compatibility", "Customer")
_ADDRESS: Final = ValueObjectIdentity(_CUSTOMER, ("address",))
_ROOT_KEY: Final = ObjectKey(_CUSTOMER, (("id", 1),))


def _hydrated_record(
    *members: MemberIdentity | None, affected: ObjectKey | None = _ROOT_KEY
) -> InvalidData[object]:
    issues = frozenset(
        StoredDataIssue(
            "stored-data-many-wrong-kind",
            _CUSTOMER,
            member,
            affected,
            path=(),
            stored_value="wrong",
        )
        for member in members
    )
    return InvalidData(issues, {"id": 1}, _ROOT_KEY, None, None, 0)


@pytest.mark.parametrize(
    "member",
    [
        pytest.param(_ADDRESS, id="the-occurrence"),
        pytest.param(ValueObjectIdentity(_CUSTOMER, ("address", "geo")), id="nested-occurrence"),
        pytest.param(ValueObjectAttributeIdentity(_ADDRESS, "city"), id="attribute"),
        pytest.param(
            ValueObjectAttributeIdentity(
                ValueObjectIdentity(_CUSTOMER, ("address", "geo")), "country"
            ),
            id="nested-attribute",
        ),
    ],
)
def test_an_issue_under_an_omitted_occurrence_keeps_the_records_data(
    member: MemberIdentity,
) -> None:
    conforming = reads._conforming_row(  # pyright: ignore[reportPrivateUsage] - unit test drives the reads lane's private helper directly
        _case("m-value-object-001"), frozenset({_ADDRESS}), _hydrated_record(member)
    )
    assert conforming == {"id": 1}


@pytest.mark.parametrize(
    "member",
    [
        pytest.param(None, id="no-member"),
        pytest.param(AttributeIdentity(_CUSTOMER, "name"), id="attribute"),
        pytest.param(ValueObjectIdentity(_CUSTOMER, ("mailing",)), id="another-occurrence"),
        pytest.param(
            ValueObjectIdentity(EntityIdentity("parallax.compatibility", "Location"), ("address",)),
            id="another-entity",
        ),
    ],
)
def test_an_issue_outside_every_omitted_occurrence_is_refused(
    member: MemberIdentity | None,
) -> None:
    for record in (_hydrated_record(member), _hydrated_record(_ADDRESS, member)):
        with pytest.raises(UnclassifiedEngineError, match="published an InvalidData record"):
            reads._conforming_row(  # pyright: ignore[reportPrivateUsage] - unit test drives the reads lane's private helper directly
                _case("m-value-object-001"), frozenset({_ADDRESS}), record
            )


@pytest.mark.parametrize(
    "affected",
    [
        pytest.param(ObjectKey(_CUSTOMER, (("id", 2),)), id="another-object"),
        pytest.param(None, id="an-object-whose-identity-did-not-decode"),
    ],
)
def test_an_omitted_occurrence_issue_on_another_object_is_refused(
    affected: ObjectKey | None,
) -> None:
    with pytest.raises(UnclassifiedEngineError, match="published an InvalidData record"):
        reads._conforming_row(  # pyright: ignore[reportPrivateUsage] - unit test drives the reads lane's private helper directly
            _case("m-value-object-001"),
            frozenset({_ADDRESS}),
            _hydrated_record(_ADDRESS, affected=affected),
        )


def test_run_read_case_observes_a_wire_read() -> None:
    port = FakeDbPort(
        [{"id": 3, "owner": "Grace", "balance": decimal.Decimal("10.00"), "version": 1}]
    )
    run = lifecycle_run(None)
    reads.run_read_case(_load_case("m-execution-lifecycle-001"), port, run)
    (root,) = run.roots
    started = root.events[0]
    assert isinstance(started, ReadStarted)
    assert started.purpose == "wire"


def test_run_graph_case_reports_the_records_a_classified_root_published() -> None:
    # A `then.graph` position whose stored state contradicted the model carries the
    # collapsed node the classification hydrated, and the diagnosis rides the
    # separate `storedDataIssues` observation — one entry per invalid position, in
    # result order, naming the concrete Entity, the member path inside the
    # occurrence, and the affected object's own key.
    port = QueueDbPort(
        [
            # The case's own `given.corrupt` reads the addressed document back
            # before it writes over it (m-case-format), ahead of the read.
            [{"profile": {"street": "4 Main", "city": "Boston"}}],
            [
                {"id": 1, "profile": StructuredDocument({"street": "1 Main", "city": None})},
                {"id": 2, "profile": StructuredDocument({"city": "Oslo"})},
            ],
            [{"id": 12, "item_id": 2, "profile": StructuredDocument({"street": "12 Main"})}],
        ]
    )
    _emissions, graph, _database_calls, stored_data_issues = reads.run_graph_case(
        _load_case("m-storage-layout-027"), port
    )
    assert _node(graph["ClassificationTwinItem"], 0)["profile"] == {
        "street": "1 Main",
        "city": None,
    }
    assert _node(graph["ClassificationTwinItem"], 1)["profile"] == {"city": "Oslo"}
    assert stored_data_issues == [
        {
            "ordinal": 1,
            "hydrated": True,
            "issues": [
                {
                    "code": "stored-data-required-member-absent",
                    "entity": "parallax.compatibility.ClassificationTwinItem",
                    "member": "parallax.compatibility.ClassificationTwinItem.profile.street",
                    "objectKey": {
                        "entity": "parallax.compatibility.ClassificationTwinItem",
                        "key": {"id": 2},
                    },
                }
            ],
        }
    ]


def test_run_graph_case_publishes_null_where_nothing_could_be_hydrated() -> None:
    # The other case of the same observation: a leaf no declared decoding admits
    # leaves the position with no value at all, so the graph carries `null` and
    # `hydrated` is what says the null means "unhydrated" rather than "collapsed".
    port = QueueDbPort(
        [
            # The case's own `given.corrupt` reads the addressed document back
            # before it writes over it (m-case-format), ahead of the read.
            [{"profile": {"street": "4 Main", "city": "Boston"}}],
            [{"id": 1, "profile": StructuredDocument({"street": "1 Main", "city": 7})}],
            [],
        ]
    )
    _emissions, graph, _database_calls, stored_data_issues = reads.run_graph_case(
        _load_case("m-storage-layout-027"), port
    )
    assert graph["ClassificationTwinItem"] == [None]
    assert stored_data_issues is not None
    (record,) = stored_data_issues
    assert record["hydrated"] is False
    assert [issue["code"] for issue in cast("list[MappingRow]", record["issues"])] == [
        "stored-data-leaf-undecodable"
    ]


def test_a_diagnosis_names_its_member_by_the_path_the_corpus_addresses_one_by() -> None:
    # The three member arms a diagnosis can name, in the one dotted spelling a
    # nested predicate already authors: a top-level Attribute, a Value Object
    # occurrence at any containment depth, and a scalar inside one.
    entity = EntityIdentity("parallax.compatibility", "Customer")
    occurrence = ValueObjectIdentity(entity, ("address", "geo"))
    assert reads._member_path(AttributeIdentity(entity, "name")) == (  # pyright: ignore[reportPrivateUsage] - unit test drives the reads lane's private helper directly
        "parallax.compatibility.Customer.name"
    )
    assert reads._member_path(occurrence) == (  # pyright: ignore[reportPrivateUsage] - unit test drives the reads lane's private helper directly
        "parallax.compatibility.Customer.address.geo"
    )
    assert reads._member_path(ValueObjectAttributeIdentity(occurrence, "country")) == (  # pyright: ignore[reportPrivateUsage] - unit test drives the reads lane's private helper directly
        "parallax.compatibility.Customer.address.geo.country"
    )


def test_run_read_case_accepts_provider_normalized_native_columns() -> None:
    port = FakeDbPort([{"id": 4, "name": None}])
    _emissions, rows, _database_calls = reads.run_read_case(_load_case("m-value-object-007"), port)
    assert rows == [{"id": 4, "name": None}]


def test_run_graph_case_keys_value_objects_by_canonical_member_name() -> None:
    port = FakeDbPort(
        [
            {
                "id": 1,
                "person_id": "person-1",
                "tax_i_d": "TAX-1",
                "line2_item": 2,
                "already_snake": "ready",
                "legacy__i_d": "legacy",
                "mailing_address": {"city": "Oslo"},
            }
        ]
    )
    _emissions, graph, _database_calls, _stored_data_issues = reads.run_graph_case(
        _case("m-descriptor-002"), port
    )
    row = _node(graph["MemberColumnDefaults"], 0)
    assert row["mailingAddress"] == {"city": "Oslo"}
    assert "mailing_address" not in row


# --------------------------------------------------------------------------- #
# Docker-free error paths (m-conformance-adapter's lane-honest ``UnclassifiedEngineError``  #
# wrapping): a compiled/found query that fails inside `m-sql` / `m-navigate`  #
# / `m-temporal-read` is caught and re-raised as one `UnclassifiedEngineError`, never a     #
# leaked lower-layer exception type.                                           #
# --------------------------------------------------------------------------- #
def test_compile_read_case_wraps_a_sql_gen_error() -> None:
    case = _synthetic(
        {
            "model": "models/orders.yaml",
            "when": {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"path": "Order.doesNotExist", "value": 1}},
                },
            },
        }
    )
    with pytest.raises(UnclassifiedEngineError, match="names no declared member"):
        reads.compile_read_case(case, "postgres")


def test_run_graph_case_wraps_a_temporal_read_error_from_the_find_executor() -> None:
    case = _synthetic(
        {
            "model": "models/balance.yaml",
            "when": {
                "objectQuery": {
                    "target": "Balance",
                    "predicate": {"true": {}},
                    "temporal": {"valid-time": {"asOf": "latest"}},
                },
            },
            "then": {"graph": {}},
        }
    )
    with pytest.raises(UnclassifiedEngineError, match="undeclared"):
        reads.run_graph_case(case, QueueDbPort([]))


def test_run_graphs_case_renders_ordered_milestone_pin_graphs() -> None:
    port = QueueDbPort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": decimal.Decimal("50.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                    "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
                },
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": decimal.Decimal("75.00"),
                    "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
                    "out_z": INFINITY,
                },
            ]
        ]
    )
    emissions, graphs, database_calls = reads.run_graphs_case(_case("m-snapshot-read-013"), port)
    assert database_calls == 1
    assert len(emissions) == 1
    assert [_entry(g, "pin")["transaction-time"] for g in graphs] == [
        "2024-01-01T00:00:00.000000Z",
        "2024-04-01T00:00:00.000000Z",
    ]
    assert [_rows(_entry(g, "graph"), "InvoiceLine")[0]["amount"] for g in graphs] == [
        "50.00",
        "75.00",
    ]


def test_run_streamed_graphs_case_groups_a_delivery_back_into_milestone_ranked_graphs() -> None:
    # A delivery publishes ROOTS, in the Continuation Order — the key, then the
    # edge — so two objects standing at one milestone reach the caller in two
    # runs. The observation groups them wherever they fall and ranks the entries
    # by edge, which is what makes it the same `then.graphs` the eager read of
    # the same query states, at any page size.
    def line(key: int, amount: str, in_z: dt.datetime, out_z: object) -> MappingRow:
        return {
            "id": key,
            "invoice_id": 100,
            "amount": decimal.Decimal(amount),
            "in_z": in_z,
            "out_z": out_z,
        }

    january = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    april = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    port = QueueDbPort(
        [
            [line(1000, "50.00", january, april), line(1000, "75.00", april, INFINITY)],
            [line(1000, "75.00", april, INFINITY), line(1001, "25.00", january, INFINITY)],
            [line(1001, "25.00", january, INFINITY)],
        ]
    )
    case = _doctored("m-snapshot-read-013", stream={"batchSize": 1})
    emissions, graphs, database_calls = reads.run_streamed_graphs_case(case, port)
    assert database_calls == 3
    assert len(emissions) == 3
    assert [_entry(g, "pin")["transaction-time"] for g in graphs] == [
        "2024-01-01T00:00:00.000000Z",
        "2024-04-01T00:00:00.000000Z",
    ]
    assert [
        [row["amount"] for row in _rows(_entry(g, "graph"), "InvoiceLine")] for g in graphs
    ] == [["50.00", "25.00"], ["75.00"]]


def test_run_streamed_graphs_case_ranks_a_milestone_delivered_after_a_later_one() -> None:
    def line(key: int, in_z: dt.datetime) -> MappingRow:
        return {
            "id": key,
            "invoice_id": 100,
            "amount": decimal.Decimal("50.00"),
            "in_z": in_z,
            "out_z": INFINITY,
        }

    port = QueueDbPort(
        [[line(1000, _APRIL), line(1001, _JANUARY)], [line(1001, _JANUARY)]],
    )
    case = _doctored("m-snapshot-read-013", stream={"batchSize": 1})
    _emissions, graphs, _calls = reads.run_streamed_graphs_case(case, port)
    assert [_entry(g, "pin")["transaction-time"] for g in graphs] == [
        "2024-01-01T00:00:00.000000Z",
        "2024-04-01T00:00:00.000000Z",
    ]


def test_run_streamed_graphs_case_ranks_valid_time_before_transaction_time() -> None:
    def position(key: int, from_z: dt.datetime, in_z: dt.datetime) -> MappingRow:
        return {
            "pos_id": key,
            "acct_num": "A",
            "val": decimal.Decimal("90.00"),
            "from_z": from_z,
            "thru_z": INFINITY,
            "in_z": in_z,
            "out_z": INFINITY,
        }

    port = QueueDbPort(
        [
            [position(1, _APRIL, _JANUARY), position(2, _JANUARY, _APRIL)],
            [position(2, _JANUARY, _APRIL)],
        ]
    )
    _emissions, graphs, _calls = reads.run_streamed_graphs_case(_case("m-snapshot-read-037"), port)
    assert [_entry(g, "pin") for g in graphs] == [
        {
            "valid-time": "2024-01-01T00:00:00.000000Z",
            "transaction-time": "2024-04-01T00:00:00.000000Z",
        },
        {
            "valid-time": "2024-04-01T00:00:00.000000Z",
            "transaction-time": "2024-01-01T00:00:00.000000Z",
        },
    ]


def _invoice_line(amount: str, in_z: object, out_z: object) -> MappingRow:
    return {
        "id": 1000,
        "invoice_id": 100,
        "amount": decimal.Decimal(amount),
        "in_z": in_z,
        "out_z": out_z,
    }


_JANUARY: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_APRIL: Final = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)


def test_run_graphs_case_closes_a_partition_wherever_the_pin_changes() -> None:
    # Eager roots arrive in chronological milestone order, so a pin met again is
    # a milestone a scan answered twice: adjacency keeps it apart.
    port = QueueDbPort(
        [
            [
                _invoice_line("50.00", _JANUARY, _APRIL),
                _invoice_line("75.00", _APRIL, INFINITY),
                _invoice_line("50.00", _JANUARY, _APRIL),
            ]
        ]
    )
    _emissions, graphs, _calls = reads.run_graphs_case(_case("m-snapshot-read-013"), port)
    assert [_entry(g, "pin")["transaction-time"] for g in graphs] == [
        "2024-01-01T00:00:00.000000Z",
        "2024-04-01T00:00:00.000000Z",
        "2024-01-01T00:00:00.000000Z",
    ]


def test_a_milestone_observation_states_the_pin_production_retained_rather_than_the_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def retained(_node: object) -> Pin:
        return Pin(tx_time=dt.datetime(2030, 1, 1, tzinfo=dt.UTC))

    monkeypatch.setattr(reads, "pin_of", retained)
    port = QueueDbPort([[_invoice_line("50.00", _JANUARY, INFINITY)]])
    _emissions, graphs, _calls = reads.run_graphs_case(_case("m-snapshot-read-013"), port)
    assert [_entry(g, "pin") for g in graphs] == [
        {"transaction-time": "2030-01-01T00:00:00.000000Z"}
    ]


def _run_eager_milestones(port: QueueDbPort) -> object:
    return reads.run_graphs_case(_case("m-snapshot-read-013"), port)


def _run_streamed_milestones(port: QueueDbPort) -> object:
    case = _doctored("m-snapshot-read-013", stream={"batchSize": 10})
    return reads.run_streamed_graphs_case(case, port)


_MILESTONE_LANES: Final = pytest.mark.parametrize(
    "run",
    [
        pytest.param(_run_eager_milestones, id="eager"),
        pytest.param(_run_streamed_milestones, id="streamed"),
    ],
)


@_MILESTONE_LANES
@pytest.mark.parametrize("start", [None, INFINITY], ids=["null-start", "infinite-start"])
def test_a_milestone_root_retaining_the_empty_pin_is_no_observation(
    run: Callable[[QueueDbPort], object], start: object
) -> None:
    with pytest.raises(UnclassifiedEngineError, match="no decoded milestone start"):
        run(QueueDbPort([[_invoice_line("50.00", start, INFINITY)]]))


@_MILESTONE_LANES
def test_a_non_hydrating_milestone_root_has_no_pin_to_observe(
    run: Callable[[QueueDbPort], object],
) -> None:
    with pytest.raises(UnclassifiedEngineError, match="published no value to pin"):
        run(QueueDbPort([[_invoice_line("50.00", _JANUARY, None)]]))


def test_a_hydrated_diagnostic_milestone_root_observes_its_own_retained_pin() -> None:
    row = {
        "br_id": 1,
        "name": "Central",
        "address": {"street": "1 Main", "city": "Oslo", "phones": {"type": "x"}},
        "from_z": _JANUARY,
        "thru_z": INFINITY,
        "in_z": _APRIL,
        "out_z": INFINITY,
    }
    case = dataclasses.replace(
        _synthetic(
            {
                "model": "models/branch.yaml",
                "when": {
                    "objectQuery": {
                        "target": "Branch",
                        "predicate": {"true": {}},
                        "temporal": {
                            "valid-time": {"history": {}},
                            "transaction-time": {"history": {}},
                        },
                    },
                },
                "then": {"graphs": []},
            }
        ),
        model="models/branch.yaml",
    )
    _emissions, graphs, _calls = reads.run_graphs_case(case, QueueDbPort([[row]]))
    assert [_entry(g, "pin") for g in graphs] == [
        {
            "valid-time": "2024-01-01T00:00:00.000000Z",
            "transaction-time": "2024-04-01T00:00:00.000000Z",
        }
    ]


def test_run_graphs_case_wraps_an_error_from_the_find_executor() -> None:
    case = _synthetic(
        {
            "model": "models/invoice.yaml",
            "when": {
                "objectQuery": {
                    "target": "InvoiceLine",
                    "predicate": {"true": {}},
                    "temporal": {"valid-time": {"history": {}}},
                },
            },
            "then": {"graphs": []},
        }
    )
    with pytest.raises(UnclassifiedEngineError, match="undeclared"):
        reads.run_graphs_case(case, QueueDbPort([]))


def test_run_graph_case_refuses_a_case_whose_read_answers_a_milestone_set() -> None:
    case = _synthetic(
        {
            "model": "models/invoice.yaml",
            "when": {
                "objectQuery": {
                    "target": "InvoiceLine",
                    "predicate": {"true": {}},
                    "temporal": {"transaction-time": {"history": {}}},
                },
            },
            "then": {"graph": {}},
        }
    )
    with pytest.raises(UnclassifiedEngineError, match=r"asserts `then\.graphs`"):
        reads.run_graph_case(case, QueueDbPort([[]]))


def test_run_graphs_case_refuses_a_case_whose_read_answers_one_graph() -> None:
    case = _synthetic(
        {
            "model": "models/invoice.yaml",
            "when": {
                "objectQuery": {
                    "target": "InvoiceLine",
                    "predicate": {"true": {}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                },
            },
            "then": {"graphs": []},
        }
    )
    with pytest.raises(UnclassifiedEngineError, match=r"asserts `then\.graph`"):
        reads.run_graphs_case(case, QueueDbPort([[]]))


def test_render_value_recurses_into_a_nested_value_object_document() -> None:
    port = FakeDbPort(
        [
            {
                "id": 1,
                "name": "Ada",
                "address": {"street": "x", "city": "Oslo", "geo": {"country": "NO"}},
            }
        ]
    )
    _emissions, graph, _database_calls, _stored_data_issues = reads.run_graph_case(
        _case("m-value-object-024"), port
    )
    rendered = _node(graph["Customer"], 0)
    assert rendered["address"] == {
        "street": "x",
        "city": "Oslo",
        "geo": {"country": "NO"},
        "phones": [],
    }


# --------------------------------------------------------------------------- #
# Streamed delivery (m-case-format "Streamed reads"): the three inputs the      #
# streamed run lane refuses before or during the delivery.                      #
# --------------------------------------------------------------------------- #
def _doctored(case_id: str, **members: Any) -> case_format.Case:
    """*case_id*'s case with its `when` members replaced, reaching the engine
    entry point as a document the corpus does not carry."""
    case = _load_case(case_id)
    document = dict(case.document)
    document["when"] = {**cast("Mapping[str, Any]", document["when"]), **members}
    return dataclasses.replace(case, document=document)


_STREAM_CASE_ID: Final[str] = "m-snapshot-read-029"


def test_run_stream_case_refuses_a_page_size_that_is_not_a_positive_int() -> None:
    case = _doctored(_STREAM_CASE_ID, stream={"batchSize": 0})
    with pytest.raises(UnclassifiedEngineError, match="positive integer"):
        reads.run_stream_case(case, FakeDbPort([]))


def test_run_stream_case_refuses_a_case_declaring_no_delivery() -> None:
    # The streamed entry point is dispatched on the member's presence, so a case
    # reaching it without one is a mis-authored corpus rather than an eager read.
    # It is refused by name rather than falling back to a page size nobody asked
    # for — which would report a delivery the case never stated.
    case = _load_case(_STREAM_CASE_ID)
    when = cast("Mapping[str, Any]", case.document["when"])
    document = dict(case.document)
    document["when"] = {key: value for key, value in when.items() if key != "stream"}

    with pytest.raises(
        UnclassifiedEngineError, match=re.escape("declares `when.stream.batchSize`")
    ):
        reads.run_stream_case(dataclasses.replace(case, document=document), FakeDbPort([]))


def test_run_stream_case_refuses_a_milestone_set_read() -> None:
    # The two streamed lanes answer the two result members, exactly as the two
    # eager ones do: a milestone-set delivery publishes one root per milestone at
    # its own milestone pin, which is `then.graphs`, so the `then.graph` lane refuses
    # it rather than reporting one flat graph the case never stated.
    case = _doctored("m-snapshot-read-013", stream={"batchSize": 2})
    with pytest.raises(UnclassifiedEngineError, match=re.escape("asserts `then.graphs`")):
        reads.run_stream_case(case, FakeDbPort([]))


def test_run_streamed_graphs_case_refuses_a_single_instant_read() -> None:
    # And the converse: a delivery of a single-instant read publishes roots at
    # one pin the query itself states, so there is no milestone partition to
    # report and the case's own member says so.
    case = _doctored(_STREAM_CASE_ID)
    with pytest.raises(UnclassifiedEngineError, match=re.escape("asserts `then.graph`")):
        reads.run_streamed_graphs_case(case, FakeDbPort([]))


def test_run_stream_case_reports_a_refused_delivery_as_an_engine_error() -> None:
    # The delivery's own refusals reach the caller as the lane's error rather
    # than as an implementation exception. A Sort Key naming a member outside the
    # read's own position is refused by the gate the stream crosses at scope
    # entry, so it is raised before any statement runs.
    case = _doctored(
        _STREAM_CASE_ID,
        objectQuery={
            **cast("Mapping[str, Any]", _load_case(_STREAM_CASE_ID).document["when"])[
                "objectQuery"
            ],
            "orderBy": [{"attr": "parallax.compatibility.OrderItem.sku"}],
        },
        stream={"batchSize": 2},
    )
    port = FakeDbPort([])
    with pytest.raises(UnclassifiedEngineError):
        reads.run_stream_case(case, port)
    assert port.executed == []


# --------------------------------------------------------------------------- #
# Root configuration (m-case-format *Root configuration*): the record          #
# `given.databaseOptions` states reaches the Handle every read lane connects,  #
# and governs only the transactions that Handle opens.                          #
# --------------------------------------------------------------------------- #
def _rooted(case_id: str, *, uow: dict[str, object] | None = None) -> case_format.Case:
    """*case_id*'s case under a conspicuous root — every field away from its
    built-in — with `when.uow` replaced by ``uow`` (dropped when ``None``)."""
    case = _load_case(case_id)
    document = dict(case.document)
    document["given"] = {
        **cast("Mapping[str, Any]", document.get("given") or {}),
        "databaseOptions": {
            "retry": {"maxRetries": 0},
            "concurrency": "locking",
            "isolation": "serializable",
        },
    }
    when = {k: v for k, v in cast("Mapping[str, Any]", document["when"]).items() if k != "uow"}
    document["when"] = when if uow is None else {**when, "uow": uow}
    return dataclasses.replace(case, document=document)


def test_a_standalone_read_under_a_locking_root_opens_no_transaction_and_takes_no_lock() -> None:
    # The root configures `locking`, and the case requests nothing: the read
    # stays the standalone `db.wire.find` every other unrequesting read is, so
    # no boundary is asked for at all and the emitted statement carries no lock
    # suffix — the root's defaults govern transactions, and this read opens none.
    port = FakeDbPort([{"id": 1, "name": "Grace"}])
    emissions, rows, _calls = reads.run_read_case(_rooted("m-value-object-001"), port)
    assert rows == [{"id": 1, "name": "Grace"}]
    assert port.levels == []
    assert "for share" not in emissions[0].sql


def test_a_transactional_read_resolves_what_it_omits_against_the_case_root() -> None:
    # An authored `when.uow` puts the read inside `db.transact`, and every
    # field the request leaves out is then production's to resolve against the
    # root this lane connected: the boundary is asked for the root's
    # Serializable, which nothing in `when.uow` named.
    port = FakeDbPort([{"id": 1, "name": "Grace"}])
    reads.run_read_case(_rooted("m-value-object-001", uow={"concurrency": "optimistic"}), port)
    assert port.levels == ["serializable"]


def test_a_read_carrying_an_empty_uow_block_under_a_locking_root_locks_in_both_lanes() -> None:
    # The block's PRESENCE is the boundary and its contents are the request: a
    # `when.uow` that requests nothing still runs the read in a transaction,
    # whose preference production resolves against the locking root, so the
    # executed statement carries the suffix — and the compile lane, planning
    # under the same resolved preference, renders the same golden. The
    # standalone sibling (`-063`) differs from this case by the block alone.
    locking = _load_case("m-concurrency-064")
    standalone = _load_case("m-concurrency-063")
    assert cast("Mapping[str, Any]", locking.document["when"])["uow"] == {}
    port = FakeDbPort(
        [{"id": 2, "owner": "Linus", "balance": decimal.Decimal("250.00"), "version": 1}]
    )
    emissions, _rows, _calls = reads.run_read_case(locking, port)
    assert port.levels == ["read_committed"]
    assert emissions[0].sql.endswith("for share of t0")
    compiled, _calls = reads.compile_read_case(locking, "postgres")
    assert compiled[0].sql == emissions[0].sql
    assert not reads.compile_read_case(standalone, "postgres")[0][0].sql.endswith("for share of t0")


def test_an_explicit_optimistic_request_under_a_locking_root_plans_and_runs_lock_free() -> None:
    # The override half of the same rule on the versioned Account: the request
    # names `optimistic`, so neither lane renders the suffix the root alone
    # would have produced.
    locking = _load_case("m-concurrency-064")
    when = cast("Mapping[str, Any]", locking.document["when"])
    case = dataclasses.replace(
        locking,
        document={**locking.document, "when": {**when, "uow": {"concurrency": "optimistic"}}},
    )
    port = FakeDbPort(
        [{"id": 2, "owner": "Linus", "balance": decimal.Decimal("250.00"), "version": 1}]
    )
    emissions, _rows, _calls = reads.run_read_case(case, port)
    assert port.levels == ["read_committed"]
    assert "for share" not in emissions[0].sql
    assert "for share" not in reads.compile_read_case(case, "postgres")[0][0].sql


@pytest.mark.parametrize("case_id", ["m-concurrency-068", "m-concurrency-069"])
def test_a_read_only_case_plans_and_runs_in_a_read_only_boundary_taking_no_lock(
    case_id: str,
) -> None:
    case = _load_case(case_id)
    port = FakeDbPort([{"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00")}])
    emissions, _rows, _calls = reads.run_read_case(case, port)
    assert port.modes == ["read_only"]
    assert "for share" not in emissions[0].sql
    compiled, _calls = reads.compile_read_case(case, "postgres")
    assert compiled[0].sql == emissions[0].sql


_GRAPH_RUNS: Final = [
    pytest.param(reads.run_graph_case, "m-snapshot-read-001", {}, id="graph"),
    pytest.param(reads.run_graphs_case, "m-snapshot-read-013", {}, id="graphs"),
    pytest.param(reads.run_stream_case, _STREAM_CASE_ID, {}, id="stream"),
    pytest.param(
        reads.run_streamed_graphs_case,
        "m-snapshot-read-013",
        {"stream": {"batchSize": 2}},
        id="streamed-graphs",
    ),
]


@pytest.mark.parametrize(("run", "case_id", "members"), _GRAPH_RUNS)
@pytest.mark.parametrize(
    ("uow", "mode", "level"),
    [
        (
            {"accessMode": "read-only", "isolation": "repeatable-read"},
            "read_only",
            "repeatable_read",
        ),
        ({"isolation": "serializable"}, "read_write", "serializable"),
    ],
)
def test_a_graph_case_runs_in_the_boundary_its_uow_requests(
    run: Any,
    case_id: str,
    members: dict[str, object],
    uow: dict[str, object],
    mode: str,
    level: str,
) -> None:
    port = FakeDbPort([])
    run(_doctored(case_id, uow=uow, **members), port)
    assert port.modes == [mode]
    assert port.levels == [level]


@pytest.mark.parametrize(("run", "case_id", "members"), _GRAPH_RUNS)
def test_a_graph_case_without_uow_opens_no_boundary(
    run: Any, case_id: str, members: dict[str, object]
) -> None:
    port = FakeDbPort([])
    run(_doctored(case_id, **members), port)
    assert port.modes == []


def _order(order_id: int) -> MappingRow:
    return {
        "id": order_id,
        "name": f"order-{order_id}",
        "sku": "A-100",
        "qty": 1,
        "price": decimal.Decimal("1.00"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 1),
        "parallax_seek_0": order_id,
    }


def test_a_retried_streamed_case_reports_only_the_succeeding_attempts_roots() -> None:
    serialization_failure = DatabaseError(
        category="deadlock", native_code="40001", message="could not serialize access"
    )
    port = FakeDbPort(
        [],
        read_script=[
            [_order(1), _order(2), _order(3)],
            serialization_failure,
            [_order(1), _order(2), _order(3)],
            [_order(3), _order(42)],
        ],
    )
    case = _doctored(_STREAM_CASE_ID, uow={"accessMode": "read-only", "isolation": "serializable"})
    _, graph, _, _ = reads.run_stream_case(case, port)
    assert [cast("Mapping[str, object]", root)["id"] for root in graph["Order"]] == [1, 2, 3, 42]
    assert port.modes == ["read_only", "read_only"]


def test_a_writable_case_runs_in_a_read_write_boundary() -> None:
    port = FakeDbPort([{"id": 1, "name": "Grace"}])
    reads.run_read_case(_rooted("m-value-object-001", uow={"concurrency": "optimistic"}), port)
    assert port.modes == ["read_write"]


def test_an_authored_level_overrides_the_case_roots_level_on_a_transactional_read() -> None:
    port = FakeDbPort([{"id": 1, "name": "Grace"}])
    reads.run_read_case(
        _rooted(
            "m-value-object-001", uow={"concurrency": "optimistic", "isolation": "repeatable-read"}
        ),
        port,
    )
    assert port.levels == ["repeatable_read"]


def test_case_database_connects_with_the_cases_own_root_record() -> None:
    # The seam every read lane composes its Handle through: the record it hands
    # `connect` is the case's `given.databaseOptions`, decoded by the case format,
    # and an unconfigured case connects the record's own defaults.
    port = FakeDbPort([])
    provider = lifecycle_run(None).observation().provider
    with reads.case_database(_rooted("m-value-object-001"), port, provider) as root:
        db = root.using_database_login()
        assert db.transact(lambda tx: tx.options) == case_format.database_options(
            _rooted("m-value-object-001")
        )
    assert port.levels == ["serializable"]
    with reads.case_database(_load_case("m-value-object-001"), FakeDbPort([]), provider) as root:
        db = root.using_database_login()
        assert db.transact(lambda tx: tx.options) == TxnOptions()
