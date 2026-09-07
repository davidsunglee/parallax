"""Two editions serving one connection's reads, A then B, against real Postgres
(spec §4 *Every result retains the edition it was read under* and *A standalone
stream adopts at entry*, §2 *Sources across editions*, m-api-conformance).

The Docker-free suites grade adoption and the stamp over fake ports. What only a
real database shows is that a delivery keeps reading under the selection it
entered with while a publication lands between its pages, that a refusal a
result under A delays until an accessor inside a transaction under B keeps A
while the transaction reports B, that a result read under A still licenses a
keyed write validated under B — Typed and Wire alike, through the shared
ingress, on the evidence the earlier read retained — and that the committed row
is what B's transaction wrote.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _support.adoption import raises_contextualized
from _support.corpus import case_fixtures
from parallax.conformance import case_format, engine
from parallax.conformance.boundary_runner import TARGET_ID
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.object_query import deserialize
from parallax.snapshot import InvalidDataError, ServingModel, connect, prepare_model
from parallax.snapshot.handle import Transaction

_CASE_ID = "m-execution-lifecycle-004"
_ACCOUNT = "parallax.compatibility.Account"
_INVALID_CASE_ID = "m-value-object-017"
_CUSTOMER = "parallax.compatibility.Customer"


def _case(case_id: str) -> case_format.Case:
    return next(case for case in case_format.load_cases() if case.case_id == case_id)


def _seeded(profile_run: Any, case_id: str = _CASE_ID) -> Any:
    case = _case(case_id)
    profile_run.reset(engine.load_case_metamodel(case), case_fixtures(case))
    return profile_run.port


def _editions() -> tuple[Any, Any, ServingModel]:
    a = prepare_model(MODELS["account"], edition="2026-09-a")
    b = prepare_model(MODELS["account"], edition="2026-09-b")
    return a, b, ServingModel(a)


def _target_node() -> dict[str, object]:
    return {
        "target": _ACCOUNT,
        "predicate": {"eq": {"attr": f"{_ACCOUNT}.id", "value": TARGET_ID}},
    }


def _balance_of(profile_run: Any) -> Decimal:
    verify = connect(profile_run.port, MODELS["account"])
    return verify.find(Account.where(Account.id == TARGET_ID)).result().balance


def test_a_publication_after_a_read_leaves_every_envelope_it_published_on_a(
    profile_run: Any,
) -> None:
    a, b, serving = _editions()
    db = connect(_seeded(profile_run), serving)

    typed = db.find(Account.where(Account.id == TARGET_ID))
    wired = db.wire.find(_target_node())
    rows = db.read_rows(deserialize(_target_node()))
    serving.publish(b, expected=a)

    assert (typed.edition, typed.checked().edition, wired.edition, rows.edition) == (
        "2026-09-a",
    ) * 4
    assert typed.result().balance == Decimal("250.00")
    # The next operation on the same handle adopts what is serving by then.
    assert db.find(Account.where(Account.id == TARGET_ID)).edition == "2026-09-b"
    assert db.wire.find(_target_node()).edition == "2026-09-b"


def test_a_publication_during_a_stream_leaves_every_page_on_a(profile_run: Any) -> None:
    a, b, serving = _editions()
    db = connect(_seeded(profile_run), serving)
    delivered: list[int] = []

    with db.stream(Account.where(Account.id >= 1), batch_size=1) as stream:
        assert stream.edition == "2026-09-a"
        for account in stream:
            delivered.append(account.id)
            if len(delivered) == 1:
                serving.publish(b, expected=a)
            # Later pages are still read under the selection the scope
            # entered with, and the stamp does not move.
            assert stream.edition == "2026-09-a"

    assert delivered == [1, 2, 3]
    assert db.find(Account.where(Account.id == TARGET_ID)).edition == "2026-09-b"


def test_a_delayed_refusal_from_a_reports_a_inside_an_execution_failure_under_b(
    profile_run: Any,
) -> None:
    # The Customer fixture holds stored states that contradict the model, so a
    # read over it publishes invalid roots its default accessor refuses later.
    # Reaching that accessor inside a transaction adopted under B starts no
    # execution and adopts nothing: the transaction's failure names B, and the
    # refusal it carries is still the one A's result settled.
    port = _seeded(profile_run, _INVALID_CASE_ID)
    a = prepare_model(MODELS["customer"], edition="2026-09-a")
    b = prepare_model(MODELS["customer"], edition="2026-09-b")
    serving = ServingModel(a)
    db = connect(port, serving)

    snapshot = db.wire.find({"target": _CUSTOMER, "predicate": {"all": {}}})
    serving.publish(b, expected=a)

    with raises_contextualized(InvalidDataError) as failed:
        db.transact(lambda _tx: snapshot.results())

    assert failed.edition == "2026-09-b"
    assert failed.value.edition == "2026-09-a" == snapshot.edition
    assert failed.value.invalid_data


def test_a_typed_value_read_under_a_licenses_a_keyed_write_validated_under_b(
    profile_run: Any,
) -> None:
    a, b, serving = _editions()
    db = connect(_seeded(profile_run), serving)

    account = db.find(Account.where(Account.id == TARGET_ID)).result()
    serving.publish(b, expected=a)

    def body(tx: Transaction) -> str:
        # Validated under B's model, licensed by the observation A's read
        # retained on the value: no reread, no evidence upgrade, no refusal.
        tx.update(account.edit(balance=account.balance + Decimal("1.00")))
        return tx.edition

    assert db.transact(body) == "2026-09-b"
    assert _balance_of(profile_run) == Decimal("251.00")


def test_a_wire_value_read_under_a_licenses_a_keyed_write_validated_under_b(
    profile_run: Any,
) -> None:
    a, b, serving = _editions()
    db = connect(_seeded(profile_run), serving)

    node = db.wire.find(_target_node()).result()
    serving.publish(b, expected=a)

    def body(tx: Transaction) -> str:
        tx.wire.update(node, {"balance": "260.00"})
        return tx.edition

    assert db.transact(body) == "2026-09-b"
    assert _balance_of(profile_run) == Decimal("260.00")
