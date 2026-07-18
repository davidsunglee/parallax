"""Copy-to-row no-drift guard (m-api-conformance, `python.md` "API Conformance
Suite and Usage Guide" — the fourth no-drift guard).

The other guards prove: an idiomatic statement's serialization equals the
corpus operation (`test_operation_no_drift.py`); an idiomatic class descriptor
equals its corpus model (`test_descriptor_no_drift.py`); a registered write
story's wire DML equals its corpus golden byte-exact
(`test_write_no_drift.py`). None of them isolates the ONE seam every keyed
UPDATE driven by an edited copy shares regardless of which story exercises
it: ``model_copy``'s Change Record feeds `parallax.core.entity.
effective_change_set`, which `Transaction.update` narrows to a sparse
(non-temporal) or observation-merged (temporal) row — and the row's own
version/processing-axis columns are ALWAYS framework-owned, never the copy's
own carried value (`m-opt-lock`; ADR 0003/0013).

This guard drives that seam directly, Docker-free, at the unit lane, scoped to
the write shapes that actually pass through edited-copy lowering: a keyed
non-temporal (versioned) update and a keyed temporal (audit-only) update. It
builds a fixture instance, edits a copy through ``model_copy``, derives the
row through the SAME helpers ``Transaction.update`` calls
(``primary_key_row`` / ``canonical_row`` / ``effective_change_set``), and
lowers it through ``lower_write`` with a SYNTHETIC observation — proving the
lowered statement binds exactly that observation's value, and a companion
assertion with a DIFFERENT observation proves the bound value tracks the
observation every time, never a value the copy itself happens to carry
(inserts, deletes/terminates, and set-based materialize paths never touch
``model_copy`` lowering at all, so they carry no analogous risk here). A
third assertion proves the version guard itself: ``model_copy`` refuses a
``version`` reassignment at the entity frontend, before any row is ever
derived — the copy-to-row seam never even reaches
``reject_caller_authored_version``'s own row-level backstop (pinned
separately, on the raw-document route, by
``test_write_lowering.test_versioned_update_carrying_a_literal_version_is_
refused``).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

import mirrored_models as mm
from parallax.conformance import models
from parallax.core.dialect import POSTGRES
from parallax.core.entity import (
    ModelCopyError,
    canonical_row,
    effective_change_set,
    primary_key_row,
)
from parallax.core.unit_work import KeyedWrite, Observation, PlannedWrite
from parallax.snapshot.handle import lower_write

pytestmark = [pytest.mark.unit, pytest.mark.api_conformance]

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
_BALANCE = _MODELS["balance"]


def _edited_account_row(*, version: int = 1) -> dict[str, object]:
    fetched = mm.Account(id=1, owner="Ada", balance=Decimal("100.00"), version=version)
    copy = fetched.model_copy(update={"balance": Decimal("175.00")})
    row = primary_key_row(copy)
    row.update(canonical_row(copy, effective_change_set(copy)))
    return row


def test_copy_to_row_non_temporal_update_binds_the_observed_version() -> None:
    instruction = KeyedWrite("update", "Account", (_edited_account_row(),))
    statement = lower_write(
        PlannedWrite(instruction=instruction, observation=Observation(version=7)),
        _ACCOUNT,
        POSTGRES,
        "locking",
    )[0].statement
    assert statement.sql == "update account set balance = ?, version = ? where id = ?"
    # 8 = the OBSERVED version (7) + 1 -- never the copy's own carried version
    # (1) + 1 = 2, even though the copy itself still holds `version=1`.
    assert statement.binds == (175.00, 8, 1)


def test_copy_to_row_non_temporal_update_tracks_a_different_observation() -> None:
    # The companion pin: a DIFFERENT observation drives a DIFFERENT advance, off
    # the SAME edited copy (still carrying its own untouched `version=1`) --
    # proving the bound value tracks the observation, never anything the copy
    # itself carries.
    instruction = KeyedWrite("update", "Account", (_edited_account_row(),))
    statement = lower_write(
        PlannedWrite(instruction=instruction, observation=Observation(version=41)),
        _ACCOUNT,
        POSTGRES,
        "locking",
    )[0].statement
    assert statement.binds == (175.00, 42, 1)


def test_copy_to_row_never_reaches_a_caller_authored_version() -> None:
    # `reject_caller_authored_version` (`~parallax.core.opt_lock`) is a
    # row-level backstop for a version-carrying row reaching `lower_write`
    # directly (the raw-document/rejected-write route, pinned by
    # `test_write_lowering.test_versioned_update_carrying_a_literal_version_
    # is_refused`) -- but the copy-to-row seam THIS guard exercises cannot
    # itself reach that backstop: `model_copy` refuses a `version` key
    # earlier, at the entity frontend, before any row is ever derived (spec
    # §3's own frontend guard, ADR 0013). Proving that here keeps the two
    # defenses distinct and both accounted for, rather than assuming the
    # copy-to-row path free-rides on the row-level one.
    fetched = mm.Account(id=1, owner="Ada", balance=Decimal("100.00"), version=1)
    with pytest.raises(ModelCopyError, match="framework-owned"):
        fetched.model_copy(update={"balance": Decimal("175.00"), "version": 99})


def _edited_balance_row() -> dict[str, object]:
    # processing_from/processing_to are framework/clock-derived on any temporal
    # write, never caller-authored (`m-unit-work`'s own axis-column exclusion)
    # -- these two are placeholders Pydantic's constructor requires but the
    # lowering seam never reads for an UPDATE's close (only `observed.in_z`
    # drives its gate, below).
    fetched = mm.Balance(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        processing_from=dt.datetime(1970, 1, 1, tzinfo=dt.UTC),
        processing_to=dt.datetime(1970, 1, 1, tzinfo=dt.UTC),
    )
    copy = fetched.model_copy(update={"value": Decimal("150.00")})
    row = primary_key_row(copy)
    row.update(canonical_row(copy, effective_change_set(copy)))
    return row


def test_copy_to_row_temporal_update_gates_the_close_on_the_observed_in_z() -> None:
    # The close (the milestone plan's FIRST statement, `audit_write.plan`)
    # binds the OBSERVATION's own `in_z` as its optimistic gate -- never a
    # value the edited copy carries (a temporal keyed write's row never even
    # HAS a processing-axis column to carry one, `m-unit-work` axis-column
    # exclusion). Optimistic concurrency renders the gate at all
    # (`~parallax.core.opt_lock.gates`); locking mode never does.
    instruction = KeyedWrite("update", "Balance", (_edited_balance_row(),))
    observed = Observation(in_z="2024-01-01T00:00:00+00:00")
    close = lower_write(
        PlannedWrite(instruction=instruction, observation=observed),
        _BALANCE,
        POSTGRES,
        "optimistic",
        "2024-09-01T00:00:00+00:00",
    )[0].statement
    assert close.sql == "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    assert close.binds == (
        "2024-09-01T00:00:00+00:00",
        1,
        "infinity",
        "2024-01-01T00:00:00+00:00",
    )


def test_copy_to_row_temporal_update_tracks_a_different_observed_in_z() -> None:
    # The companion pin: off the SAME edited copy, a DIFFERENT observed `in_z`
    # binds a DIFFERENT gate value -- the bound value tracks the observation,
    # never anything the copy or its row carries.
    instruction = KeyedWrite("update", "Balance", (_edited_balance_row(),))
    observed = Observation(in_z="2024-06-01T00:00:00+00:00")
    close = lower_write(
        PlannedWrite(instruction=instruction, observation=observed),
        _BALANCE,
        POSTGRES,
        "optimistic",
        "2024-09-01T00:00:00+00:00",
    )[0].statement
    assert close.binds == (
        "2024-09-01T00:00:00+00:00",
        1,
        "infinity",
        "2024-06-01T00:00:00+00:00",
    )
