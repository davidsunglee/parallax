from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Callable, Mapping
from typing import Any, cast

import pytest

from parallax.conformance import _case_ingress, models
from parallax.conformance._mechanism.envelope import EngineError
from parallax.conformance._mechanism.transaction_control import transact, write_adapter
from parallax.conformance._wire_submission import (
    Buffered,
    Executed,
    Refused,
    Submission,
    WireSubmitter,
    read_submissions,
)
from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.simulated_temporal_store import SimulatedTemporalStore
from parallax.core.base import INFINITY
from parallax.core.db_port import MappingRow
from parallax.core.execution import KeyedWriteValueError, ServingModel, prepare_model
from parallax.core.metamodel import EntityIdentity
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.unit_work import KeyedWriteInstruction, WriteEvidenceError
from parallax.core.write_plan import ObjectKey
from parallax.snapshot import Database, TxnContext
from tests.unit.conformance._lanes._scripted_port import ScriptedPort
from tests.unit.conformance._recording_ports import FakeWritePort

_NOW = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
_ACCOUNT: MappingRow = {"id": 1, "owner": "Ada", "balance": decimal.Decimal("100.00"), "version": 1}


def _run[T](
    name: str,
    port: FakeWritePort | ScriptedPort,
    body: Callable[[WireSubmitter, TxnContext, AcceptedMetamodel], T],
    *,
    max_retries: int = 0,
    concurrency: str = "optimistic",
) -> T:
    domain = models.load_domain_model(models.default_models_dir() / f"{name}.yaml")
    model = models.accepted_model_of(domain)
    serving = ServingModel(prepare_model(domain, edition=name))
    with Database.connect(
        write_adapter(port, rollback=False), serving, clock=FixedClock(_NOW)
    ) as root:

        def attempt(tx: TxnContext) -> T:
            return body(WireSubmitter(tx, model), tx, model)

        return transact(
            root.using_database_login(),
            attempt,
            max_retries=max_retries,
            concurrency=cast("Any", concurrency),
        )


def _entry(
    mutation: str, row: Mapping[str, object], *, entity: str = "Account", **controls: object
) -> dict[str, object]:
    return {"mutation": mutation, "entity": entity, "rows": [row], **controls}


def _one(model: AcceptedMetamodel, entry: Mapping[str, object], *, step: int = 1) -> Submission:
    (submission,) = read_submissions(model, [entry], step=step)
    return submission


@pytest.mark.parametrize("mutation", ["amend", "replace", "delete"])
def test_keyed_verbs_submit_against_the_units_own_read(mutation: str) -> None:
    port = FakeWritePort(find_rows=[dict(_ACCOUNT)])
    row = {"id": 1} if mutation == "delete" else {"id": 1, "owner": "Grace", "balance": "105.00"}
    outcome = _run(
        "account",
        port,
        lambda submitter, tx, model: submitter.submit_unit(
            read_submissions(model, [_entry(mutation, row)])
        ),
    )
    assert outcome == (Buffered(),)
    assert len(port.reads) == len(port.writes) == 1
    assert port.writes[0][0].startswith("delete" if mutation == "delete" else "update")
    assert port.writes[0][1][-1] == 1


@pytest.mark.parametrize("mutation", ["amend", "replace", "delete"])
def test_target_verbs_need_no_resolving_read(mutation: str) -> None:
    port = FakeWritePort()
    row = {"id": 1} if mutation == "delete" else {"id": 1, "owner": "Grace", "balance": "105.00"}
    outcome = _run(
        "account",
        port,
        lambda submitter, tx, model: submitter.submit(
            _one(model, {"mutation": mutation, "entity": "Account", "row": row, "ifVersion": 1})
        ),
    )
    assert outcome == Buffered()
    assert port.reads == [] and len(port.writes) == 1


@pytest.mark.parametrize("mutation", ["amend", "replace", "delete"])
def test_predicate_verbs_execute_readlessly_and_return_their_count(mutation: str) -> None:
    port = FakeWritePort(affected_script=[3])
    entry: dict[str, object] = {
        "mutation": mutation,
        "target": {
            "entity": "Wallet",
            "predicate": {"greaterThan": {"path": "Wallet.id", "value": 0}},
        },
    }
    if mutation == "amend":
        entry["assignments"] = [{"attr": "Wallet.owner", "value": "Grace"}]
    elif mutation == "replace":
        entry["row"] = {"owner": "Grace", "balance": "10.00"}
    outcome = _run(
        "wallet",
        port,
        lambda submitter, tx, model: submitter.submit_unit(read_submissions(model, entry)),
    )
    assert outcome == (Executed(3),)
    assert port.reads == [] and len(port.writes) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "insert",
        "insertUntil",
        "amend",
        "amendUntil",
        "replace",
        "replaceUntil",
        "terminate",
        "terminateUntil",
    ],
)
def test_temporal_verbs_keep_their_bounds(mutation: str) -> None:
    start = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    row: MappingRow = {
        "pos_id": 1,
        "acct_num": "A",
        "val": decimal.Decimal("100.00"),
        "from_z": start,
        "thru_z": INFINITY,
        "in_z": start,
        "out_z": INFINITY,
    }
    port = FakeWritePort(find_rows=[row])
    payload: dict[str, object] = {"id": 2 if mutation.startswith("insert") else 1}
    if not mutation.startswith("terminate"):
        payload.update({"acctNum": "B", "value": "150.00"})
    entry = _entry(mutation, payload, entity="Position", validFrom="2024-01-01T00:00:00Z")
    if mutation.endswith("Until"):
        entry["until"] = "2024-06-01T00:00:00Z"
    outcome = _run(
        "position",
        port,
        lambda submitter, tx, model: submitter.submit_unit(read_submissions(model, [entry])),
    )
    assert outcome == (Buffered(),)
    assert port.writes
    assert any(start in binds for _, binds in port.writes)


@pytest.mark.parametrize("on,expected", [(None, 2), (0, 1), (1, 2)])
def test_named_find_and_latest_read_keep_distinct_generations(
    on: int | None, expected: int
) -> None:
    port = ScriptedPort(read_rows=[[dict(_ACCOUNT)], [dict(_ACCOUNT) | {"version": 2}]])

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        submitter.record_find(0, tx.wire.find({"target": "Account", "predicate": {"true": {}}}))
        submitter.record_find(
            1, tx.wire.find({"target": "Account", "predicate": {"true": {}}, "limit": 1})
        )
        assert (
            submitter.submit(
                _one(model, _entry("amend", {"id": 1, "owner": "Grace"}, on=on), step=2)
            )
            == Buffered()
        )

    _run("account", port, body)
    assert port.writes[0][1][-1] == expected


@pytest.mark.parametrize(
    "on,reason",
    [
        ([0, 1], "ONE find step"),
        (False, "ONE find step"),
        (4, "not an EARLIER find"),
        ("/scenario/4/write/0", "opened no value"),
    ],
)
def test_missing_forward_foreign_or_non_scalar_references_never_fall_back(
    on: object, reason: str
) -> None:
    port = FakeWritePort(find_rows=[dict(_ACCOUNT)])

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        submitter.record_find(0, tx.wire.find({"target": "Account", "predicate": {"true": {}}}))
        submitter.submit(_one(model, _entry("amend", {"id": 1, "owner": "Grace"}, on=on)))

    with pytest.raises(EngineError, match=reason):
        _run("account", port, body)
    assert port.writes == []


def test_a_named_empty_find_refuses_even_with_another_same_key_read() -> None:
    port = FakeWritePort(read_script=[[], [dict(_ACCOUNT)]])

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        submitter.record_find(0, tx.wire.find({"target": "Account", "predicate": {"true": {}}}))
        submitter.record_find(
            1, tx.wire.find({"target": "Account", "predicate": {"true": {}}, "limit": 1})
        )
        submitter.submit(_one(model, _entry("amend", {"id": 1, "owner": "Grace"}, on=0), step=2))

    with pytest.raises(EngineError, match="published 0 rows"):
        _run("account", port, body)
    assert port.writes == []


@pytest.mark.parametrize("key", [90, 91])
@pytest.mark.parametrize("named", [False, True])
def test_own_insertion_and_multi_row_pointer_need_no_read(key: int, named: bool) -> None:
    port = FakeWritePort(affected_script=[2])

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        insertions = read_submissions(
            model,
            [
                {
                    "mutation": "insert",
                    "entity": "Account",
                    "rows": [
                        {"id": value, "owner": "Ada", "balance": "10.00"} for value in (90, 91)
                    ],
                }
            ],
            step=0,
        )
        for insertion in insertions:
            assert submitter.submit(insertion) == Buffered()
        controls = {"on": "/scenario/0/write/0"} if named else {}
        assert (
            submitter.submit(
                _one(model, _entry("amend", {"id": key, "owner": "Grace"}, **controls))
            )
            == Buffered()
        )

    _run("account", port, body)
    assert port.reads == [] and len(port.writes) == 1
    assert "Grace" in port.writes[0][1]


def test_a_refused_insert_opens_no_pointer_to_an_earlier_insertion() -> None:
    port = FakeWritePort()

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        insert = _entry("insert", {"id": 90, "owner": "Ada", "balance": "10.00"})
        submitter.submit(_one(model, insert, step=0))
        with pytest.raises(KeyedWriteValueError, match="write-value-already-stored"):
            submitter.submit(_one(model, insert, step=1))
        submitter.submit(
            _one(
                model,
                _entry("amend", {"id": 90, "owner": "Grace"}, on="/scenario/1/write/0"),
                step=2,
            )
        )

    with pytest.raises(EngineError, match="opened no value"):
        _run("account", port, body)
    assert port.writes == [] and port.reads == []


@pytest.mark.parametrize("expected", ["write-evidence-unavailable", "some-other-refusal", None])
def test_only_the_declared_evidence_error_is_a_refused_outcome(
    expected: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = FakeWritePort(find_rows=[dict(_ACCOUNT)])

    def refuse(*args: object, **kwargs: object) -> Any:
        raise WriteEvidenceError(
            code="write-evidence-unavailable",
            message="test refusal",
            object_key=ObjectKey(EntityIdentity("parallax.compatibility", "Account"), (("id", 1),)),
        )

    from parallax.snapshot import WireTransactionView

    monkeypatch.setattr(WireTransactionView, "amend", refuse)

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> object:
        return submitter.submit_unit(
            read_submissions(
                model, [_entry("amend", {"id": 1, "owner": "Grace"}, expectError=expected)], step=1
            )
        )

    if expected == "write-evidence-unavailable":
        assert _run("account", port, body) == (Refused("/scenario/1/write/0", expected),)
    else:
        with pytest.raises(WriteEvidenceError):
            _run("account", port, body)
    assert port.writes == []


@pytest.mark.parametrize("unit", [False, True])
def test_framework_markers_are_flagged_then_refused(unit: bool) -> None:
    port = FakeWritePort()

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        submissions = read_submissions(
            model, [_entry("amend", {"id": 1, "version": {"increment": 1}})]
        )
        assert submissions[0].is_framework_marker
        submitter.submit_unit(submissions) if unit else submitter.submit(submissions[0])

    with pytest.raises(EngineError, match="framework bookkeeping"):
        _run("account", port, body)
    assert port.reads == [] and port.writes == []


@pytest.mark.parametrize("document", [{"increment": 1}, {"computed": "maxPlusOne"}])
def test_marker_shaped_value_objects_are_literal_submission_values(
    document: dict[str, object],
) -> None:
    model = models.load_models()["customer"]
    (submission,) = read_submissions(
        model, [_entry("insert", {"id": 1, "name": "Ada", "address": document}, entity="Customer")]
    )
    assert not submission.is_framework_marker
    assert isinstance(submission.instruction, KeyedWriteInstruction)
    assert submission.instruction.rows[0]["address"] == document


def test_submit_unit_reads_every_source_before_its_hook_and_any_write() -> None:
    port = FakeWritePort(find_rows=[dict(_ACCOUNT)])
    hooks: list[int] = []

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        def before() -> None:
            assert len(port.reads) == 1 and port.writes == []
            hooks.append(len(port.reads))

        submitter.submit_unit(
            read_submissions(
                model, [_entry("amend", {"id": 1, "owner": "Grace"}), _entry("delete", {"id": 1})]
            ),
            before_writes=before,
        )

    _run("account", port, body)
    assert hooks == [1]
    assert len(port.reads) == len(port.writes) == 1
    assert port.writes[0][0].startswith("delete")


def test_a_retried_attempt_gets_fresh_submitter_and_source() -> None:
    port = FakeWritePort(
        read_script=[[dict(_ACCOUNT)], [dict(_ACCOUNT) | {"version": 2}]], affected_script=[0, 1]
    )
    attempts: list[WireSubmitter] = []

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        attempts.append(submitter)
        submitter.submit_unit(
            read_submissions(model, [_entry("amend", {"id": 1, "owner": "Grace"})])
        )

    _run("account", port, body, max_retries=1)
    assert len(attempts) == 2 and attempts[0] is not attempts[1]
    assert [binds[-1] for _, binds in port.writes] == [1, 2]
    assert port.rollbacks == port.commits == 1


def test_ordinary_submissions_never_prepare_or_simulate_a_peer_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("Wire submission entered compile machinery")

    monkeypatch.setattr(SimulatedTemporalStore, "__init__", refuse)
    monkeypatch.setattr(_case_ingress, "prepare_case_write", refuse)
    port = FakeWritePort(find_rows=[dict(_ACCOUNT)])
    assert _run(
        "account",
        port,
        lambda submitter, tx, model: submitter.submit_unit(
            read_submissions(model, [_entry("amend", {"id": 1, "owner": "Grace"})])
        ),
    ) == (Buffered(),)
    assert port.writes


def test_read_submissions_parses_a_multi_row_entry_once_and_keeps_each_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.core._execution._unit_work import instructions

    original = instructions.deserialize
    parsed: list[object] = []

    def deserialize(document: object) -> Any:
        parsed.append(document)
        return original(document)

    monkeypatch.setattr(instructions, "deserialize", deserialize)
    model = models.load_models()["account"]
    submissions = read_submissions(
        model,
        [
            {
                "mutation": "amend",
                "entity": "Account",
                "rows": [
                    {"id": 1, "owner": "Grace", "observedVersion": 3},
                    {"id": 2, "owner": "Ada", "observedVersion": 7},
                ],
            }
        ],
        step=5,
    )
    assert len(parsed) == 1
    assert len(submissions) == 2
    assert [
        s.declared_observation.observed_version if s.declared_observation else None
        for s in submissions
    ] == [3, 7]
    assert [s.pointer for s in submissions] == ["/scenario/5/write/0"] * 2
    assert all(
        isinstance(s.instruction, KeyedWriteInstruction)
        and "observedVersion" not in s.instruction.rows[0]
        for s in submissions
    )


@pytest.mark.parametrize("named", [False, True])
def test_a_pinned_bitemporal_source_is_selected_by_the_writes_start(named: bool) -> None:
    start = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    row = {
        "pos_id": 1,
        "acct_num": "A",
        "val": decimal.Decimal("100.00"),
        "from_z": start,
        "thru_z": INFINITY,
        "in_z": start,
        "out_z": INFINITY,
    }
    port = FakeWritePort(find_rows=[row])

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        snapshot = tx.wire.find(
            {
                "target": "Position",
                "predicate": {"true": {}},
                "temporal": {
                    "valid-time": {"asOf": "2024-01-01T00:00:00Z"},
                    "transaction-time": {"asOf": "latest"},
                },
            }
        )
        submitter.record_find(0, snapshot)
        entry = _entry(
            "amend",
            {"id": 1, "value": "105.00"},
            entity="Position",
            validFrom="2024-02-01T00:00:00Z",
            **({"on": 0} if named else {}),
        )
        submitter.submit(_one(model, entry))

    with pytest.raises(
        EngineError, match="another Valid-Time instant" if named else "no read of its own"
    ):
        _run("position", port, body)
    assert port.writes == []


def test_record_find_walks_a_streams_checked_delivery_values() -> None:
    port = FakeWritePort(find_rows=[dict(_ACCOUNT)])

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        with tx.wire.stream(
            {"target": "Account", "predicate": {"true": {}}}, batch_size=2
        ) as delivery:
            roots = tuple(delivery.checked())
        submitter.record_find(0, roots)
        submitter.submit(_one(model, _entry("amend", {"id": 1, "owner": "Grace"}, on=0)))

    _run("account", port, body)
    assert len(port.writes) == 1


def test_a_named_insertion_must_be_the_submissions_own_object() -> None:
    port = FakeWritePort()

    def body(submitter: WireSubmitter, tx: TxnContext, model: AcceptedMetamodel) -> None:
        submitter.submit(
            _one(model, _entry("insert", {"id": 90, "owner": "Ada", "balance": "10.00"}), step=0)
        )
        submitter.submit(
            _one(model, _entry("amend", {"id": 91, "owner": "Grace"}, on="/scenario/0/write/0"))
        )

    with pytest.raises(EngineError, match="published 0 rows"):
        _run("account", port, body)
    assert port.writes == []


@pytest.mark.parametrize(
    "mutation", ["amend", "amendUntil", "replace", "replaceUntil", "terminate", "terminateUntil"]
)
def test_temporal_target_verbs_use_the_declared_revision_and_bounds(mutation: str) -> None:
    start = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    row: MappingRow = {
        "pos_id": 1,
        "acct_num": "A",
        "val": decimal.Decimal("100.00"),
        "from_z": start,
        "thru_z": INFINITY,
        "in_z": start,
        "out_z": INFINITY,
    }
    port = FakeWritePort(find_rows=[row])
    payload: dict[str, object] = {"id": 1}
    if not mutation.startswith("terminate"):
        payload.update({"acctNum": "B", "value": "150.00"})
    entry: dict[str, object] = {
        "mutation": mutation,
        "entity": "Position",
        "row": payload,
        "ifTxStart": "2024-01-01T00:00:00Z",
        "validFrom": "2024-01-01T00:00:00Z",
    }
    if mutation.endswith("Until"):
        entry["until"] = "2024-06-01T00:00:00Z"
    outcome = _run(
        "position", port, lambda submitter, tx, model: submitter.submit(_one(model, entry))
    )
    assert outcome == Buffered()
    assert port.writes
    assert any(start in binds for _, binds in port.writes)
