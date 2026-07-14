"""Write no-drift guard (m-api-conformance, M4 increment 5).

Each idiomatic ``db.transact`` spelling the suite registers must produce exactly
the story its mirrored corpus case grades, driven through the **public**
developer surface against a recording fake port. Commit-path cases assert the
ordered driver DML (and participating reads) equal the case's golden statements
— the API spelling cannot drift from the graded wire protocol. Abort-path cases
assert the m-unit-work abort contract instead: the failure surfaces (the value
is withheld), the discarded buffer emits nothing, and the surrounding reads
still match their goldens — their rolled-back round trips are graded by the
conformance run lane, which executes-then-aborts; the developer surface discards
the buffer before it ever reaches the wire.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, cast

import pytest

from conftest import case_document
from parallax.conformance import case_format, engine, models
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.dialect import POSTGRES
from parallax.snapshot.handle import Database, Transaction

pytestmark = pytest.mark.api_conformance

_MODELS = models.load_models()
_CASES = {c.case_id: c for c in case_format.load_cases()}


class _RecordingPort:
    """An in-memory ``m-db-port`` recording every call in order (no Docker)."""

    def __init__(self, *, rows: Sequence[Row] = ()) -> None:
        self.ops: list[tuple[object, ...]] = []
        self.rows = list(rows)

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        self.ops.append(("read", sql, tuple(binds)))
        return [dict(row) for row in self.rows]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.ops.append(("write", sql, tuple(binds)))
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        self.ops.append(("begin",))
        try:
            result = body(self)
        except BaseException:
            self.ops.append(("rollback",))
            raise
        self.ops.append(("commit",))
        return result

    def statements(self) -> list[tuple[str, tuple[object, ...]]]:
        """The executed statements (reads and writes) in wire order."""
        return [
            (cast("str", op[1]), cast("tuple[object, ...]", op[2]))
            for op in self.ops
            if op[0] in ("read", "write")
        ]

    @property
    def wrote(self) -> bool:
        return any(op[0] == "write" for op in self.ops)


def _wire(binds: Sequence[object]) -> list[object]:
    # Reconcile authored YAML binds (a `date` object, ints) with the write-input
    # values the verbs carry verbatim — the same wire normalization the sweeps use.
    return [engine.wire_value(bind) for bind in binds]


def _driver_goldens(entries: list[dict[str, Any]]) -> list[tuple[str, list[object]]]:
    out: list[tuple[str, list[object]]] = []
    for entry in entries:
        sql: Any = entry["sql"]
        text = cast("dict[str, str]", sql)["postgres"] if isinstance(sql, dict) else sql
        out.append((POSTGRES.to_driver_sql(cast("str", text)), list(entry.get("binds", []))))
    return out


def _scenario_goldens(
    case_id: str, *, skip_rollback: bool = False
) -> list[tuple[str, list[object]]]:
    """The case's flattened per-step golden statements in driver form."""
    doc = case_document(_CASES[case_id])
    if _CASES[case_id].shape == "writeSequence":
        return _driver_goldens(cast("list[dict[str, Any]]", doc["then"]["statements"]))
    out: list[tuple[str, list[object]]] = []
    for step in cast("list[dict[str, Any]]", doc["when"]["scenario"]):
        if skip_rollback and step.get("rollback") is True:
            continue
        out.extend(_driver_goldens(cast("list[dict[str, Any]]", step["statements"])))
    return out


def _assert_statements(
    port: _RecordingPort, goldens: list[tuple[str, list[object]]], case_id: str
) -> None:
    observed = port.statements()
    assert len(observed) == len(goldens), (case_id, observed, goldens)
    for (sql, binds), (golden_sql, golden_binds) in zip(observed, goldens, strict=True):
        assert sql == golden_sql, (case_id, sql, golden_sql)
        assert _wire(binds) == _wire(golden_binds), (case_id, binds, golden_binds)


def _db(port: _RecordingPort, model: str) -> Database:
    return Database.connect(port, _MODELS[model])


# --------------------------------------------------------------------------- #
# Commit-path spellings: the emitted wire equals the golden, statement for      #
# statement. These are the `api_suite.EXAMPLES` write snippets' source of truth.#
# --------------------------------------------------------------------------- #
_NEW_ACCOUNT = {"id": 7, "owner": "Newton", "balance": 5.00, "version": 1}
_FIND_7 = {"eq": {"attr": "Account.id", "value": 7}}
_FIND_1 = {"eq": {"attr": "Account.id", "value": 1}}
_FIND_3 = {"eq": {"attr": "Account.id", "value": 3}}

_ORDER_100 = {
    "id": 100,
    "name": "Hopper",
    "sku": "X-1",
    "qty": 1,
    "price": 9.99,
    "active": True,
    "orderedOn": "2024-07-01",
}
_ITEM_200 = {"id": 200, "orderId": 100, "sku": "X-1", "quantity": 3}


def _read_your_own_writes(tx: Transaction) -> list[Row]:
    tx.insert("Account", _NEW_ACCOUNT)
    return tx.find("Account", _FIND_7)


def _update_then_observe(tx: Transaction) -> list[Row]:
    tx.update("Account", {"id": 1, "balance": 175.00, "version": 2})
    return tx.find("Account", _FIND_1)


def _delete_then_observe(tx: Transaction) -> list[Row]:
    tx.delete("Account", {"id": 3})
    return tx.find("Account", _FIND_3)


def _combined_flush(tx: Transaction) -> list[Row]:
    tx.insert("Account", {"id": 9, "owner": "Noether", "balance": 5.00, "version": 1})
    tx.update("Account", {"id": 1, "balance": 20.00, "version": 2})
    tx.delete("Account", {"id": 3})
    return tx.find("Account", {"lessThan": {"attr": "Account.balance", "value": 50.00}})


def _fk_ordered_inserts(tx: Transaction) -> None:
    tx.insert("Order", _ORDER_100)
    tx.insert("OrderItem", _ITEM_200)


def _fk_ordered_lifecycle(db: Database) -> None:
    # Two units of work: create the pair, then later delete it. Buffering all
    # four verbs in ONE transaction would coalesce each insert+delete to a
    # cancellation (the m-unit-work planner) — a different (also correct) story;
    # the case grades the cross-transaction lifecycle with its FK-ordered DML.
    db.transact(_fk_ordered_inserts)

    def teardown(tx: Transaction) -> None:
        tx.delete("OrderItem", {"id": 200})
        tx.delete("Order", {"id": 100})

    db.transact(teardown)


# case id -> (model stem, the idiomatic story driving the Database).
COMMIT_BUILDERS: dict[str, tuple[str, Callable[[Database], object]]] = {
    "m-unit-work-001": ("account", lambda db: db.transact(_read_your_own_writes)),
    "m-unit-work-005": ("account", lambda db: db.transact(_update_then_observe)),
    "m-unit-work-006": ("account", lambda db: db.transact(_delete_then_observe)),
    "m-unit-work-009": ("account", lambda db: db.transact(_combined_flush)),
    "m-unit-work-003": ("orders", lambda db: db.transact(_fk_ordered_inserts)),
    "m-unit-work-007": ("orders", _fk_ordered_lifecycle),
}


@pytest.mark.parametrize("case_id", sorted(COMMIT_BUILDERS), ids=sorted(COMMIT_BUILDERS))
def test_idiomatic_transact_emits_the_golden_dml(case_id: str) -> None:
    model, story = COMMIT_BUILDERS[case_id]
    port = _RecordingPort()
    story(_db(port, model))
    _assert_statements(port, _scenario_goldens(case_id), case_id)
    assert port.ops[0] == ("begin",)
    assert port.ops[-1] == ("commit",)
    assert ("rollback",) not in port.ops


# --------------------------------------------------------------------------- #
# Abort-path spellings: the failure surfaces, the discarded buffer emits        #
# nothing, and the surrounding reads still match their goldens.                 #
# --------------------------------------------------------------------------- #
class _Boom(RuntimeError):
    """The deliberate closure failure the abort spellings raise."""


def _aborted(db: Database, verb: Callable[[Transaction], None]) -> None:
    def fn(tx: Transaction) -> None:
        verb(tx)
        raise _Boom("abort after buffering")

    with pytest.raises(_Boom):
        db.transact(fn)


def _abort_update(db: Database) -> None:
    db.transact(lambda tx: tx.find("Account", _FIND_1))
    _aborted(db, lambda tx: tx.update("Account", {"id": 1, "balance": 999.00, "version": 2}))
    db.transact(lambda tx: tx.find("Account", _FIND_1))


def _abort_insert(db: Database) -> None:
    _aborted(db, lambda tx: tx.insert("Account", _NEW_ACCOUNT))
    db.transact(lambda tx: tx.find("Account", _FIND_7))


def _abort_delete(db: Database) -> None:
    _aborted(db, lambda tx: tx.delete("Account", {"id": 3}))
    db.transact(lambda tx: tx.find("Account", _FIND_3))


ABORT_BUILDERS: dict[str, Callable[[Database], None]] = {
    "m-unit-work-002": _abort_update,
    "m-unit-work-011": _abort_insert,
    "m-unit-work-012": _abort_delete,
}


@pytest.mark.parametrize("case_id", sorted(ABORT_BUILDERS), ids=sorted(ABORT_BUILDERS))
def test_idiomatic_abort_discards_the_buffer_and_keeps_the_reads_golden(case_id: str) -> None:
    # The rolled-back step's DML round trip is graded by the conformance run
    # lane (which executes then aborts); through the developer surface the
    # buffered write is discarded before it reaches the wire, so the guard here
    # is the abort CONTRACT: nothing written, failure surfaced, reads golden.
    port = _RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
    ABORT_BUILDERS[case_id](_db(port, "account"))
    assert not port.wrote, (case_id, port.ops)
    _assert_statements(port, _scenario_goldens(case_id, skip_rollback=True), case_id)
    assert ("rollback",) in port.ops


def test_boundary_callback_value_is_withheld_on_abort() -> None:
    # m-unit-work-004 (boundary, api-conformance lane): read -> buffered update
    # -> a dependent read force-flushes it inside the still-open scope -> the
    # closure throws. The abort discards even the force-flushed write (the
    # port rolls back) and `transact` raises instead of returning the value.
    port = _RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
    db = _db(port, "account")

    def fn(tx: Transaction) -> str:
        tx.find("Account", _FIND_1)
        tx.update("Account", {"id": 1, "balance": 175.00, "version": 2})
        tx.find("Account", _FIND_1)  # dependent read: forces the flush in-scope
        raise _Boom("abort after the dependent read")

    with pytest.raises(_Boom):
        db.transact(fn)
    kinds = [op[0] for op in port.ops]
    assert kinds == ["begin", "read", "write", "read", "rollback"], port.ops
