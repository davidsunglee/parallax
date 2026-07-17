"""Unit pins for ``parallax.core.batch_write`` (m-batch-write's injected
collapse-eligibility vocabulary, COR-3 Phase 8 increment 5).

Direct, focused tests over the pure decision functions — independent of the
planner's own collapse-stage adjacency logic (pinned in ``test_planner.py``)
and the rendered SQL (pinned in ``test_write_lowering.py`` /
``test_engine.py``).
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import batch_write

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
ACCOUNT = _MODELS["account"]
WALLET = _MODELS["wallet"]
BALANCE = _MODELS["balance"]
POSITION = _MODELS["position"]


def test_insert_collapses_for_an_unversioned_non_pk_gen_entity() -> None:
    assert batch_write.insert_collapses(WALLET, "Wallet") is True


def test_insert_collapses_for_a_versioned_entity_too() -> None:
    # The initial version is a derived constant, never observed — a
    # versioned entity's insert collapses exactly like an unversioned one.
    assert batch_write.insert_collapses(ACCOUNT, "Account") is True


def test_insert_never_collapses_for_a_temporal_entity() -> None:
    assert batch_write.insert_collapses(BALANCE, "Balance") is False
    assert batch_write.insert_collapses(POSITION, "Position") is False


def test_update_collapses_when_uniform_and_unversioned() -> None:
    rows = [{"id": 1, "balance": 500.00}, {"id": 2, "balance": 500.00}]
    assert batch_write.update_collapses(WALLET, "Wallet", rows) is True


def test_update_does_not_collapse_when_non_uniform() -> None:
    rows = [{"id": 1, "balance": 111.00}, {"id": 2, "balance": 222.00}]
    assert batch_write.update_collapses(WALLET, "Wallet", rows) is False


def test_update_never_collapses_for_a_versioned_entity_even_when_uniform() -> None:
    rows = [{"id": 1, "balance": 0.00}, {"id": 2, "balance": 0.00}]
    assert batch_write.update_collapses(ACCOUNT, "Account", rows) is False


def test_update_never_collapses_for_a_temporal_entity() -> None:
    rows = [{"id": 1, "value": 1.00}, {"id": 2, "value": 1.00}]
    assert batch_write.update_collapses(BALANCE, "Balance", rows) is False


def test_update_does_not_collapse_when_a_row_carries_an_observation_key() -> None:
    # An explicit observedVersion/observedInZ control key is a per-row-
    # observation signal REGARDLESS of the target's own versioned-ness.
    rows = [
        {"id": 1, "balance": 500.00, "observedVersion": 1},
        {"id": 2, "balance": 500.00, "observedVersion": 1},
    ]
    assert batch_write.update_collapses(WALLET, "Wallet", rows) is False


def test_update_does_not_collapse_a_single_row() -> None:
    assert batch_write.update_collapses(WALLET, "Wallet", [{"id": 1, "balance": 1.00}]) is False


def test_delete_collapses_for_an_unversioned_entity() -> None:
    assert batch_write.delete_collapses(WALLET, "Wallet") is True


def test_delete_never_collapses_for_a_versioned_entity() -> None:
    assert batch_write.delete_collapses(ACCOUNT, "Account") is False


def test_delete_never_collapses_for_a_temporal_entity() -> None:
    assert batch_write.delete_collapses(BALANCE, "Balance") is False


def test_collapses_dispatches_by_mutation() -> None:
    rows = [{"id": 1, "balance": 5.00}, {"id": 2, "balance": 5.00}]
    assert batch_write.collapses(WALLET, "Wallet", "insert", rows) is True
    assert batch_write.collapses(WALLET, "Wallet", "update", rows) is True
    assert batch_write.collapses(WALLET, "Wallet", "delete", rows) is True
    assert batch_write.collapses(ACCOUNT, "Account", "delete", rows) is False
