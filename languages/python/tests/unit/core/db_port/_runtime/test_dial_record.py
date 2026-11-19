"""The latest dial failure a pool met, kept until a connection becomes usable."""

from __future__ import annotations

import dataclasses
from typing import Any, cast

import pytest

from parallax.core.internal.db_port._runtime._dial_record import DialFailure, DialLedger


def test_a_new_ledger_holds_no_failure() -> None:
    assert DialLedger().latest_failure is None


def test_the_latest_failure_replaces_an_earlier_one() -> None:
    # A caller is told the last thing establishment met, not the first.
    ledger = DialLedger()
    earlier, later = ConnectionRefusedError("first"), PermissionError("second")

    ledger.report_failure("unavailable", earlier)
    ledger.report_failure("authentication_refused", later)

    assert ledger.latest_failure == DialFailure("authentication_refused", later)


def test_a_usable_connection_clears_the_failure_on_record() -> None:
    ledger = DialLedger()
    ledger.report_failure("credentials_refused", RuntimeError("no token"))

    ledger.report_usable()

    assert ledger.latest_failure is None


def test_a_handover_clears_the_failure_on_record_and_leaves_an_empty_ledger_empty() -> None:
    ledger = DialLedger()
    ledger.clear_on_handover()
    assert ledger.latest_failure is None

    ledger.report_failure("unavailable", ConnectionRefusedError("refused"))
    ledger.clear_on_handover()

    assert ledger.latest_failure is None


def test_a_recorded_failure_cannot_be_changed_through_the_value_read() -> None:
    ledger = DialLedger()
    ledger.report_failure("preparation_failed", RuntimeError("unusable"))
    failure = ledger.latest_failure
    assert failure is not None

    with pytest.raises(dataclasses.FrozenInstanceError):
        cast("Any", failure).reason = "unavailable"
