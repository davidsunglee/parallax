"""Two editions serving one connection's reads, A then B, against real Postgres
(`spec/queries-and-results.md` and `spec/execution.md`, m-api-conformance).

The Docker-free suites grade adoption and the stamp over fake ports. What only a
real database shows is that a delivery keeps reading under the selection it
entered with while a publication lands between its pages, that a refusal a
result under A delays until an accessor inside a transaction under B keeps A
while the transaction reports B, that a result read under A licenses no source
write in a transaction under B yet still states the revision a target
write validated under B is checked against — Typed and Wire alike — and that
the committed row is what B's transaction wrote.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from parallax.conformance import case_format, engine
from parallax.conformance.boundary_runner import TARGET_ID
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.internal.base import UsageError
from parallax.core.internal.execution import (
    ServingModel,
    prepare_model,
)
from parallax.core.internal.read_delivery import InvalidDataError
from parallax.snapshot import TxnContext, connect
from tests._support.case_corpus import case as corpus_case
from tests._support.corpus import case_fixtures
from tests._support.errors import raises_code
from tests._support.root_ownership import own_root

_CASE_ID = "m-execution-lifecycle-004"
_ACCOUNT = "parallax.compatibility.Account"
_INVALID_CASE_ID = "m-value-object-017"
_CUSTOMER = "parallax.compatibility.Customer"


def _case(case_id: str) -> case_format.Case:
    return corpus_case(case_id)


def _seeded(profile_run: Any, case_id: str = _CASE_ID) -> Any:
    case = _case(case_id)
    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))
    return profile_run.port


def _editions() -> tuple[Any, Any, ServingModel]:
    a = prepare_model(MODELS["account"], edition="2026-09-a")
    b = prepare_model(MODELS["account"], edition="2026-09-b")
    return a, b, ServingModel(a)


def _target_node() -> dict[str, object]:
    return {
        "target": _ACCOUNT,
        "predicate": {"eq": {"path": f"{_ACCOUNT}.id", "value": TARGET_ID}},
    }


def _balance_of(profile_run: Any) -> Decimal:
    verify = own_root(connect(profile_run.port, MODELS["account"])).using_database_login()
    return verify.find(Account.where(Account.id == TARGET_ID)).result().balance


def test_a_publication_after_a_read_leaves_every_envelope_it_published_on_a(
    profile_run: Any,
) -> None:
    a, b, serving = _editions()
    db = own_root(connect(_seeded(profile_run), serving)).using_database_login()

    typed = db.find(Account.where(Account.id == TARGET_ID))
    wired = db.wire.find(_target_node())
    serving.publish(b, expected=a)

    assert (typed.edition, typed.checked().edition, wired.edition) == ("2026-09-a",) * 3
    assert typed.result().balance == Decimal("250.00")
    # The next operation on the same handle adopts what is serving by then.
    assert db.find(Account.where(Account.id == TARGET_ID)).edition == "2026-09-b"
    assert db.wire.find(_target_node()).edition == "2026-09-b"


def test_a_publication_during_a_stream_leaves_every_page_on_a(profile_run: Any) -> None:
    a, b, serving = _editions()
    db = own_root(connect(_seeded(profile_run), serving)).using_database_login()
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


def test_a_delayed_refusal_from_a_keeps_a_and_is_noted_with_the_transactions_b(
    profile_run: Any,
) -> None:
    # The Customer fixture holds stored states that contradict the model, so a
    # read over it publishes invalid roots its default accessor refuses later.
    # Reaching that accessor inside a transaction adopted under B starts no
    # execution and adopts nothing: the transaction's note names B, and the
    # refusal is still the one A's result settled, naming A.
    port = _seeded(profile_run, _INVALID_CASE_ID)
    a = prepare_model(MODELS["customer"], edition="2026-09-a")
    b = prepare_model(MODELS["customer"], edition="2026-09-b")
    serving = ServingModel(a)
    db = own_root(connect(port, serving)).using_database_login()

    snapshot = db.wire.find({"target": _CUSTOMER, "predicate": {"true": {}}})
    serving.publish(b, expected=a)

    with raises_code(InvalidDataError, "result-data-invalid") as failed:
        db.transact(lambda _tx: snapshot.results())

    assert failed.value.__notes__ == ["raised in a transaction under model edition '2026-09-b'"]
    assert failed.value.edition == "2026-09-a" == snapshot.edition
    assert failed.value.invalid_data


def test_a_typed_value_read_under_a_states_the_revision_a_write_under_b_is_checked_against(
    profile_run: Any,
) -> None:
    a, b, serving = _editions()
    db = own_root(connect(_seeded(profile_run), serving)).using_database_login()

    account = db.find(Account.where(Account.id == TARGET_ID)).result()
    serving.publish(b, expected=a)

    def body(tx: TxnContext) -> str:
        # No read of this attempt produced the value, so it licenses no source
        # write; the version it published is what the target write states.
        with raises_code(UsageError, "write-evidence-unavailable"):
            tx.amend(account.edit(balance=account.balance + Decimal("1.00")))
        tx.amend_if(
            Account,
            Account.balance.set(account.balance + Decimal("1.00")),
            key=account.id,
            version=account.version,
        )
        return tx.edition

    assert db.transact(body) == "2026-09-b"
    assert _balance_of(profile_run) == Decimal("251.00")


def test_a_wire_value_read_under_a_states_the_revision_a_write_under_b_is_checked_against(
    profile_run: Any,
) -> None:
    a, b, serving = _editions()
    db = own_root(connect(_seeded(profile_run), serving)).using_database_login()

    node = db.wire.find(_target_node()).result()
    serving.publish(b, expected=a)

    def body(tx: TxnContext) -> str:
        with raises_code(UsageError, "write-evidence-unavailable"):
            tx.wire.amend(node, {"balance": "260.00"})
        tx.wire.amend_if(
            _ACCOUNT,
            {"id": node["id"], "balance": "260.00"},
            version=cast("int", node["version"]),
        )
        return tx.edition

    assert db.transact(body) == "2026-09-b"
    assert _balance_of(profile_run) == Decimal("260.00")
