"""Unit pins for ``parallax.core.batch_write`` (m-batch-write's injected
collapse-eligibility vocabulary) and for the composition layer's own batch
grouping.

Direct, focused tests over the pure decision functions — independent of the
Write Planner's own batching-stage adjacency logic (pinned in
``test_write_planner.py``) and the rendered SQL (pinned in
``test_write_lowering.py`` / ``test_engine.py``). The final section composes
the two: it plans through the SAME production wiring
(``parallax.snapshot.handle.build_write_planner``) and lowers the resulting
plan, pinning that a run only ever collapses rows whose filtered Table Layout
slot selections match (`m-sql` "Physical DML ordering").
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from _support.clock_probes import inert_instant
from _support.planner_probes import TEST_SUBJECT_IDENTITY, observed_buffer
from parallax.conformance import models
from parallax.core import batch_write
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import BufferItem, KeyedWrite, PlanningRequest, WriteRejectedError
from parallax.snapshot.handle import build_write_planner, stream_lowered
from parallax.snapshot.handle._keyed_sql import collapse_group_key

_MODELS = models.load_models()


def _target(stem: str, name: str) -> tuple[Metamodel, EntityMetadata]:
    """One corpus model and one of its Entities, both accepted."""
    model = _MODELS[stem]
    entity = model.entity(EntityIdentity("parallax.compatibility", name))
    assert entity is not None
    return model, entity


ACCOUNT = _target("account", "Account")
WALLET = _target("wallet", "Wallet")
BALANCE = _target("balance", "Balance")
POSITION = _target("position", "Position")


def _flush_and_lower(
    buffer: list[BufferItem | KeyedWrite], model: Metamodel
) -> list[LoweredStatement]:
    """Plan ``buffer`` with the production wiring, then lower the plan."""
    instant = inert_instant()
    plan = build_write_planner(model).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=instant,
            concurrency="locking",
            buffered_writes=observed_buffer(buffer, model, None),
        )
    )
    return [statement for _step, statement in stream_lowered(plan, model, POSTGRES)]


def test_insert_collapses_for_an_unversioned_non_pk_gen_entity() -> None:
    assert batch_write.insert_collapses(*WALLET) is True


def test_insert_collapses_for_a_versioned_entity_too() -> None:
    # The initial version is a derived constant, never observed — a
    # versioned entity's insert collapses exactly like an unversioned one.
    assert batch_write.insert_collapses(*ACCOUNT) is True


def test_insert_never_collapses_for_a_temporal_entity() -> None:
    assert batch_write.insert_collapses(*BALANCE) is False
    assert batch_write.insert_collapses(*POSITION) is False


def test_update_collapses_when_uniform_and_unversioned() -> None:
    rows = [{"id": 1, "balance": Decimal("500.00")}, {"id": 2, "balance": Decimal("500.00")}]
    assert batch_write.update_collapses(*WALLET, rows) is True


def test_update_does_not_collapse_when_non_uniform() -> None:
    rows = [{"id": 1, "balance": Decimal("111.00")}, {"id": 2, "balance": Decimal("222.00")}]
    assert batch_write.update_collapses(*WALLET, rows) is False


def test_update_never_collapses_for_a_versioned_entity_even_when_uniform() -> None:
    rows = [{"id": 1, "balance": Decimal("0.00")}, {"id": 2, "balance": Decimal("0.00")}]
    assert batch_write.update_collapses(*ACCOUNT, rows) is False


def test_update_never_collapses_for_a_temporal_entity() -> None:
    rows = [{"id": 1, "value": Decimal("1.00")}, {"id": 2, "value": Decimal("1.00")}]
    assert batch_write.update_collapses(*BALANCE, rows) is False


def test_update_does_not_collapse_when_a_row_carries_an_observation_key() -> None:
    # An explicit observedVersion control key is a per-row-observation signal
    # REGARDLESS of the target's own versioned-ness.
    rows = [
        {"id": 1, "balance": Decimal("500.00"), "observedVersion": 1},
        {"id": 2, "balance": Decimal("500.00"), "observedVersion": 1},
    ]
    assert batch_write.update_collapses(*WALLET, rows) is False


def test_update_does_not_collapse_a_single_row() -> None:
    assert batch_write.update_collapses(*WALLET, [{"id": 1, "balance": Decimal("1.00")}]) is False


def test_delete_collapses_for_an_unversioned_entity() -> None:
    assert batch_write.delete_collapses(*WALLET) is True


def test_delete_never_collapses_for_a_versioned_entity() -> None:
    assert batch_write.delete_collapses(*ACCOUNT) is False


def test_delete_never_collapses_for_a_temporal_entity() -> None:
    assert batch_write.delete_collapses(*BALANCE) is False


def test_collapses_dispatches_by_mutation() -> None:
    rows = [{"id": 1, "balance": Decimal("5.00")}, {"id": 2, "balance": Decimal("5.00")}]
    assert batch_write.collapses(*WALLET, "insert", rows) is True
    assert batch_write.collapses(*WALLET, "update", rows) is True
    assert batch_write.collapses(*WALLET, "delete", rows) is True
    assert batch_write.collapses(*ACCOUNT, "delete", rows) is False


# --------------------------------------------------------------------------- #
# Batch grouping (m-sql "Physical DML ordering"): the planner's collapse stage  #
# composed with the write lowering it feeds, under the composition layer's own  #
# injected vocabulary.                                                          #
# --------------------------------------------------------------------------- #
def test_same_shape_insert_run_collapses_into_one_multi_row_statement() -> None:
    model, _ = WALLET
    buffer: list[BufferItem | KeyedWrite] = [
        KeyedWrite(
            "insert", "Wallet", ({"id": 10, "owner": "Mira", "balance": Decimal("100.00")},)
        ),
        KeyedWrite("insert", "Wallet", ({"id": 11, "owner": "Omar", "balance": Decimal("20.00")},)),
    ]
    assert [statement.sql for statement in _flush_and_lower(buffer, model)] == [
        "insert into wallet(id, owner, balance) values (?, ?, ?), (?, ?, ?)"
    ]


def test_insert_preparation_refuses_a_missing_required_slot_before_grouping() -> None:
    model, _ = WALLET
    buffer: list[BufferItem | KeyedWrite] = [
        KeyedWrite(
            "insert", "Wallet", ({"id": 10, "owner": "Mira", "balance": Decimal("100.00")},)
        ),
        KeyedWrite("insert", "Wallet", ({"id": 11, "owner": "Omar"},)),
    ]
    with pytest.raises(WriteRejectedError, match=r"Wallet\.balance: required attribute"):
        _flush_and_lower(buffer, model)


def test_one_invalid_insert_refuses_the_whole_candidate_run_before_grouping() -> None:
    model, _ = WALLET
    buffer: list[BufferItem | KeyedWrite] = [
        KeyedWrite(
            "insert", "Wallet", ({"id": 10, "owner": "Mira", "balance": Decimal("100.00")},)
        ),
        KeyedWrite("insert", "Wallet", ({"id": 11, "owner": "Nils", "balance": Decimal("30.00")},)),
        KeyedWrite("insert", "Wallet", ({"id": 12, "owner": "Omar"},)),
    ]
    with pytest.raises(WriteRejectedError, match=r"Wallet\.balance: required attribute"):
        _flush_and_lower(buffer, model)


def test_grouping_an_unmappable_row_answers_one_undifferentiated_group() -> None:
    # The grouping key is asked of every collapse candidate, before any lowering
    # decides the row is renderable — so it stays TOTAL where a physical shape
    # does not exist: an abstract family position owns no table, and a control
    # key (`m-opt-lock`'s observation signal) names no slot of the view. Both
    # answer the same absent key, leaving the loud refusal to the builder.
    payment_model, payment = _target("payment", "Payment")
    assert collapse_group_key(payment_model, payment, "insert", {"id": 1}) is None
    wallet_model, wallet = WALLET
    row = {"id": 1, "balance": Decimal("5.00"), "observedVersion": 1}
    assert collapse_group_key(wallet_model, wallet, "update", row) is None


def test_delete_grouping_ignores_members_the_statement_never_uses() -> None:
    # A DELETE's emitted statement selects the key columns alone, so two rows
    # carrying different non-key payload members are the SAME physical shape and
    # must reach one `IN`-list statement.
    model, _ = WALLET
    buffer: list[BufferItem | KeyedWrite] = [
        KeyedWrite(
            "delete", "Wallet", ({"id": 10, "owner": "Mira", "balance": Decimal("100.00")},)
        ),
        KeyedWrite("delete", "Wallet", ({"id": 11},)),
    ]
    statements = _flush_and_lower(buffer, model)
    assert [statement.sql for statement in statements] == ["delete from wallet where id in (?, ?)"]
    assert [statement.binds for statement in statements] == [(10, 11)]


def test_update_grouping_still_splits_on_a_differing_set_clause() -> None:
    # An UPDATE's emitted statement DOES select the assignable members (its `set`
    # clause), so a differing assignable selection stays a differing group —
    # each side then collapses on its own uniform values.
    model, _ = WALLET
    buffer: list[BufferItem | KeyedWrite] = [
        KeyedWrite("update", "Wallet", ({"id": 10, "balance": Decimal("5.00")},)),
        KeyedWrite("update", "Wallet", ({"id": 11, "balance": Decimal("5.00")},)),
        KeyedWrite("update", "Wallet", ({"id": 12, "owner": "Omar"},)),
        KeyedWrite("update", "Wallet", ({"id": 13, "owner": "Omar"},)),
    ]
    statements = _flush_and_lower(buffer, model)
    assert [statement.sql for statement in statements] == [
        "update wallet set balance = ? where id in (?, ?)",
        "update wallet set owner = ? where id in (?, ?)",
    ]
    assert [statement.binds for statement in statements] == [
        (Decimal("5.00"), 10, 11),
        ("Omar", 12, 13),
    ]


def test_row_member_order_alone_never_splits_a_batch_group() -> None:
    # The grouping key is the TABLE-ordered slot selection, so two rows naming
    # the same members in different payload order stay one group.
    model, _ = WALLET
    buffer: list[BufferItem | KeyedWrite] = [
        KeyedWrite(
            "insert", "Wallet", ({"id": 10, "owner": "Mira", "balance": Decimal("100.00")},)
        ),
        KeyedWrite("insert", "Wallet", ({"balance": Decimal("20.00"), "id": 11, "owner": "Omar"},)),
    ]
    assert [statement.sql for statement in _flush_and_lower(buffer, model)] == [
        "insert into wallet(id, owner, balance) values (?, ?, ?), (?, ?, ?)"
    ]
