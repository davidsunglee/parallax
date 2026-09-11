"""The read lanes, compiled purely and run against a fake in-memory
``m-db-port`` (no Docker): the golden the compile lane matches, the driver
translation and wire rendering the row-form run reports, the envelope the
graph-form and milestone-set runs report around production's Wire result, the
streamed delivery's refusals, and every refusal the lanes translate into an
``EngineError`` naming the case.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import functools
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import case_format, sweep
from parallax.conformance._lanes import reads
from parallax.conformance._mechanism.envelope import EngineError
from parallax.core.base import INFINITY, PresentDocument
from parallax.core.db_port import Row
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.snapshot import DeferredFeatureError
from tests.unit.conformance._recording_ports import FakeDbPort, QueueDbPort


def _rows(row: Row | None, key: str) -> list[Row]:
    """A graph leaf's relationship-attached rows, typed for test-side assertions
    (`then.graph`'s wire shape is intentionally a plain ``dict[str, object]``)."""
    assert row is not None
    return cast("list[Row]", row[key])


def _node(nodes: list[Row | None], index: int) -> Row:
    """One published graph position that carries a value.

    A position whose stored state contradicted the model carries ``null``, so a
    test asserting about the node itself states that it expected one.
    """
    node = nodes[index]
    assert node is not None
    return node


def _entry(entry: dict[str, object], key: str) -> Row:
    """A milestone-set `{pin, graph}` entry's own member, typed for test-side
    assertions (`then.graphs`' wire shape is a plain ``dict[str, object]``)."""
    return cast("Row", entry[key])


@functools.cache
def _corpus() -> tuple[case_format.Case, ...]:
    return tuple(case_format.load_cases())


@functools.cache
def _reachable_by_id() -> Mapping[str, case_format.Case]:
    return {case.case_id: case for case in sweep.reachable_cases(cases=list(_corpus()))}


@functools.cache
def _corpus_by_id() -> Mapping[str, case_format.Case]:
    return {case.case_id: case for case in _corpus()}


def _case(case_id: str) -> case_format.Case:
    return _reachable_by_id()[case_id]


def _load_case(case_id: str) -> case_format.Case:
    # Loads by id directly from the corpus, independent of `sweep.
    # IMPLEMENTED_MODULES` reachability: these lane-level tests exercise the
    # entry point on its own terms, never gated on whether the case has ALSO
    # been flipped visible in the sweep.
    return _corpus_by_id()[case_id]


def test_compile_read_case_matches_golden() -> None:
    emissions, round_trips = reads.compile_read_case(_case("m-value-object-001"), "postgres")
    assert round_trips == 1
    assert emissions[0].case_pointer == "/objectQuery"
    assert emissions[0].sql == (
        "select t0.id, t0.name from customer t0 where jsonb_extract_path_text(t0.address, ?) = ?"
    )
    assert emissions[0].binds == ("city", "Oslo")
    assert emissions[0].to_json()["casePointer"] == "/objectQuery"


def test_run_read_case_executes_driver_sql_and_records_rows() -> None:
    port = FakeDbPort([{"id": 1, "name": "Grace"}])
    emissions, rows, round_trips = reads.run_read_case(_case("m-value-object-001"), port)
    assert round_trips == 1
    assert rows == [{"id": 1, "name": "Grace"}]
    assert emissions[0].sql.count("?") == 2
    driver_sql, driver_binds = port.executed[0]
    assert "%s" in driver_sql and "?" not in driver_sql
    assert driver_binds == ["city", "Oslo"]


def test_run_read_case_materializes_family_variant_from_the_tph_tag_column() -> None:
    # m-inheritance-003 (Payment root, table-per-hierarchy): the compiled SELECT
    # projects the raw `kind` tag column; run_read_case materializes `familyVariant`
    # from the tag metadata map at row construction and never leaves the raw tag key
    # on the wire row (m-case-format: an abstract-target row carries `familyVariant`,
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
    _emissions, rows, _round_trips = reads.run_read_case(_case("m-inheritance-003"), port)
    assert rows == [
        {
            "id": 1,
            "amount": "100.00",
            "card_network": "Visa",
            "tendered": None,
            "familyVariant": "CardPayment",
        }
    ]


def test_run_read_case_materializes_family_variant_from_the_tpcs_literal_column() -> None:
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
    _emissions, rows, _round_trips = reads.run_read_case(_case("m-inheritance-050"), port)
    assert rows[0]["familyVariant"] == "Invoice"
    assert "family_variant" not in rows[0]


def test_run_read_case_concrete_target_read_carries_no_family_variant() -> None:
    # m-inheritance-001 (CardPayment, concrete target): the compiled SELECT never
    # projects a tag/literal column, so the row passes through wire rendering alone.
    port = FakeDbPort([{"id": 1, "amount": decimal.Decimal("100.00"), "card_network": "Visa"}])
    _emissions, rows, _round_trips = reads.run_read_case(_case("m-inheritance-001"), port)
    assert rows == [{"id": 1, "amount": "100.00", "card_network": "Visa"}]
    assert "familyVariant" not in rows[0]


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
    with pytest.raises(EngineError, match=case.path.name):
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
                    "predicate": {"all": {}},
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
    with pytest.raises(DeferredFeatureError) as caught:
        reads.compile_read_case(case, "postgres")
    assert caught.value.features == ("snapshot-history-includes",)


def test_compile_rejects_non_read_shape() -> None:
    write_seq = next(c for c in _corpus() if c.shape == "writeSequence")
    with pytest.raises(EngineError, match="only `read`-shape compile"):
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
    with pytest.raises(EngineError, match=message):
        reads.compile_read_case(_synthetic(document), "postgres")


# --------------------------------------------------------------------------- #
# Graph reads (m-deep-fetch / m-snapshot-read): the                            #
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
    emissions, graph, round_trips, stored_data_issues = reads.run_graph_case(
        _case("m-snapshot-read-001"), port
    )
    assert round_trips == 3
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
    _emissions, graph, round_trips, stored_data_issues = reads.run_graph_case(
        _case("m-snapshot-read-011"), port
    )
    assert round_trips == 2
    assert stored_data_issues is None
    # The back-reference renders its target ONCE, in full, and terminates: the
    # include tree — not a cycle detector — is what bounds the value, so the
    # position carries the ancestor's own members rather than a primary-key stub.
    back = _rows(graph["Order"][0], "items")[0]["order"]
    assert isinstance(back, Mapping)
    assert back["id"] == 1
    assert back["name"] == "Ada"
    assert "items" not in back


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
                {"id": 1, "profile": PresentDocument({"street": "1 Main", "city": None})},
                {"id": 2, "profile": PresentDocument({"city": "Oslo"})},
            ],
            [{"id": 12, "item_id": 2, "profile": PresentDocument({"street": "12 Main"})}],
        ]
    )
    _emissions, graph, _round_trips, stored_data_issues = reads.run_graph_case(
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
    # The other arm of the same observation: a leaf no declared decoding admits
    # leaves the position with no value at all, so the graph carries `null` and
    # `hydrated` is what says the null means "unhydrated" rather than "collapsed".
    port = QueueDbPort(
        [
            # The case's own `given.corrupt` reads the addressed document back
            # before it writes over it (m-case-format), ahead of the read.
            [{"profile": {"street": "4 Main", "city": "Boston"}}],
            [{"id": 1, "profile": PresentDocument({"street": "1 Main", "city": 7})}],
            [],
        ]
    )
    _emissions, graph, _round_trips, stored_data_issues = reads.run_graph_case(
        _load_case("m-storage-layout-027"), port
    )
    assert graph["ClassificationTwinItem"] == [None]
    assert stored_data_issues is not None
    (record,) = stored_data_issues
    assert record["hydrated"] is False
    assert [issue["code"] for issue in cast("list[Row]", record["issues"])] == [
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


def test_run_read_case_refuses_a_row_form_position_the_read_classified() -> None:
    # The row-form observation has no place to carry a record, so the lane names
    # the shape rather than grading a classification as though it were a row.
    port = FakeDbPort([{"id": 4, "name": None}])
    with pytest.raises(EngineError, match="published an InvalidData record"):
        reads.run_read_case(_load_case("m-value-object-007"), port)


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
    _emissions, graph, _round_trips, _stored_data_issues = reads.run_graph_case(
        _case("m-descriptor-002"), port
    )
    row = _node(graph["MemberColumnDefaults"], 0)
    assert row["mailingAddress"] == {"city": "Oslo"}
    assert "mailing_address" not in row


# --------------------------------------------------------------------------- #
# Docker-free error paths (m-conformance-adapter's lane-honest ``EngineError``  #
# wrapping): a compiled/found query that fails inside `m-sql` / `m-navigate`  #
# / `m-temporal-read` is caught and re-raised as one `EngineError`, never a     #
# leaked lower-layer exception type.                                           #
# --------------------------------------------------------------------------- #
def test_compile_read_case_wraps_a_sql_gen_error() -> None:
    case = _synthetic(
        {
            "model": "models/orders.yaml",
            "when": {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.doesNotExist", "value": 1}},
                },
            },
        }
    )
    with pytest.raises(EngineError, match="names no declared attribute"):
        reads.compile_read_case(case, "postgres")


def test_run_graph_case_wraps_a_temporal_read_error_from_the_find_executor() -> None:
    case = _synthetic(
        {
            "model": "models/balance.yaml",
            "when": {
                "objectQuery": {
                    "target": "Balance",
                    "predicate": {"all": {}},
                    "temporal": {"valid-time": {"asOf": "latest"}},
                },
            },
            "then": {"graph": {}},
        }
    )
    with pytest.raises(EngineError, match="undeclared"):
        reads.run_graph_case(case, QueueDbPort([]))


def test_run_graphs_case_renders_ordered_milestone_pin_graphs() -> None:
    port = QueueDbPort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": decimal.Decimal("75.00"),
                    "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
                    "out_z": INFINITY,
                },
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": decimal.Decimal("50.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                    "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
                },
            ]
        ]
    )
    emissions, graphs, round_trips = reads.run_graphs_case(_case("m-snapshot-read-013"), port)
    assert round_trips == 1
    assert len(emissions) == 1
    assert [_entry(g, "pin")["transaction-time"] for g in graphs] == [
        "2024-01-01T00:00:00.000000Z",
        "2024-04-01T00:00:00.000000Z",
    ]
    assert [_rows(_entry(g, "graph"), "InvoiceLine")[0]["amount"] for g in graphs] == [
        "50.00",
        "75.00",
    ]


def test_run_streamed_graphs_case_groups_a_delivery_back_into_edge_ranked_graphs() -> None:
    # A delivery publishes ROOTS, in the Continuation Order — the key, then the
    # edge — so two objects standing at one milestone reach the caller in two
    # runs. The observation groups them wherever they fall and ranks the entries
    # by edge, which is what makes it the same `then.graphs` the eager read of
    # the same query states, at any page size.
    def line(key: int, amount: str, in_z: dt.datetime, out_z: object) -> Row:
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
    emissions, graphs, round_trips = reads.run_streamed_graphs_case(case, port)
    assert round_trips == 3
    assert len(emissions) == 3
    assert [_entry(g, "pin")["transaction-time"] for g in graphs] == [
        "2024-01-01T00:00:00.000000Z",
        "2024-04-01T00:00:00.000000Z",
    ]
    assert [
        [row["amount"] for row in _rows(_entry(g, "graph"), "InvoiceLine")] for g in graphs
    ] == [["50.00", "25.00"], ["75.00"]]


def test_run_graphs_case_wraps_an_error_from_the_find_executor() -> None:
    case = _synthetic(
        {
            "model": "models/invoice.yaml",
            "when": {
                "objectQuery": {
                    "target": "InvoiceLine",
                    "predicate": {"all": {}},
                    "temporal": {"valid-time": {"history": {}}},
                },
            },
            "then": {"graphs": []},
        }
    )
    with pytest.raises(EngineError, match="undeclared"):
        reads.run_graphs_case(case, QueueDbPort([]))


def test_run_graph_case_refuses_a_case_whose_read_answers_a_milestone_set() -> None:
    case = _synthetic(
        {
            "model": "models/invoice.yaml",
            "when": {
                "objectQuery": {
                    "target": "InvoiceLine",
                    "predicate": {"all": {}},
                    "temporal": {"transaction-time": {"history": {}}},
                },
            },
            "then": {"graph": {}},
        }
    )
    with pytest.raises(EngineError, match=r"asserts `then\.graphs`"):
        reads.run_graph_case(case, QueueDbPort([[]]))


def test_run_graphs_case_refuses_a_case_whose_read_answers_one_graph() -> None:
    case = _synthetic(
        {
            "model": "models/invoice.yaml",
            "when": {
                "objectQuery": {
                    "target": "InvoiceLine",
                    "predicate": {"all": {}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                },
            },
            "then": {"graphs": []},
        }
    )
    with pytest.raises(EngineError, match=r"asserts `then\.graph`"):
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
    _emissions, graph, _round_trips, _stored_data_issues = reads.run_graph_case(
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
    """*case_id*'s case with its `when` members replaced — a document no schema
    admits, reaching the engine entry point the way a mis-authored corpus would."""
    case = _load_case(case_id)
    document = dict(case.document)
    document["when"] = {**cast("Mapping[str, Any]", document["when"]), **members}
    return dataclasses.replace(case, document=document)


_STREAM_CASE_ID: Final[str] = "m-snapshot-read-029"


def test_run_stream_case_refuses_a_page_size_that_is_not_a_positive_int() -> None:
    case = _doctored(_STREAM_CASE_ID, stream={"batchSize": 0})
    with pytest.raises(EngineError, match="positive integer"):
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

    with pytest.raises(EngineError, match=re.escape("declares `when.stream.batchSize`")):
        reads.run_stream_case(dataclasses.replace(case, document=document), FakeDbPort([]))


def test_run_stream_case_refuses_a_milestone_set_read() -> None:
    # The two streamed lanes answer the two result members, exactly as the two
    # eager ones do: a milestone-set delivery publishes one root per milestone at
    # its own edge pin, which is `then.graphs`, so the `then.graph` lane refuses
    # it rather than reporting one flat graph the case never stated.
    case = _doctored("m-snapshot-read-013", stream={"batchSize": 2})
    with pytest.raises(EngineError, match=re.escape("asserts `then.graphs`")):
        reads.run_stream_case(case, FakeDbPort([]))


def test_run_streamed_graphs_case_refuses_a_single_instant_read() -> None:
    # And the converse: a delivery of a single-instant read publishes roots at
    # one pin the query itself states, so there is no milestone partition to
    # report and the case's own member says so.
    case = _doctored(_STREAM_CASE_ID)
    with pytest.raises(EngineError, match=re.escape("asserts `then.graph`")):
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
    with pytest.raises(EngineError):
        reads.run_stream_case(case, port)
    assert port.executed == []
