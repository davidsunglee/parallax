"""`TxnOptions` (`execution.md`): the built-in record, the field rules
construction is held to — the same rules an explicit `db.transact` keyword
meets — the immutability of what a root is connected with, and the private
marker an omitted transaction keyword defaults to.
"""

from __future__ import annotations

import dataclasses

import pytest

from parallax.core._execution._options import (
    OMITTED,
    Omitted,
)
from parallax.core.execution import AdaptiveBackoff, RetryPolicy, TxnOptions


def test_the_built_in_record_is_ten_optimistic_and_read_committed() -> None:
    options = TxnOptions()
    assert options.retry == RetryPolicy()
    assert options.concurrency == "optimistic"
    assert options.isolation == "read_committed"


def test_the_record_is_frozen_and_slotted() -> None:
    options = TxnOptions()
    with pytest.raises(dataclasses.FrozenInstanceError):
        options.retry = RetryPolicy(max_retries=3)  # pyright: ignore[reportAttributeAccessIssue] - the refusal is what this proves
    assert not hasattr(options, "__dict__")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("retry", 10, "retry must be a RetryPolicy"),
        ("retry", True, "retry must be a RetryPolicy"),
        ("retry", AdaptiveBackoff(), "retry must be a RetryPolicy"),
        ("retry", None, "retry must be a RetryPolicy"),
        ("concurrency", "pessimistic", r"concurrency must be one of \['locking', 'optimistic'\]"),
        ("concurrency", None, "concurrency must be one of"),
        ("isolation", "read uncommitted", "isolation must be one of"),
        ("isolation", "repeatable read", "isolation must be one of"),
        ("isolation", None, "isolation must be one of"),
    ],
)
def test_construction_refuses_a_value_outside_its_fields_contract(
    field: str, value: object, message: str
) -> None:
    # `None` is invalid for every field: the record holds concrete values only,
    # and omission is a keyword a caller leaves out rather than a value.
    with pytest.raises(ValueError, match=message):
        TxnOptions(**{field: value})  # pyright: ignore[reportArgumentType] - the runtime refusal of an untyped caller is what this proves


def test_an_accepted_vocabulary_value_is_stored_as_its_canonical_spelling() -> None:
    class Spelled(str):
        __hash__ = None  # type: ignore[assignment]

    options = TxnOptions(
        concurrency=Spelled("locking"),  # pyright: ignore[reportArgumentType]
        isolation=Spelled("serializable"),  # pyright: ignore[reportArgumentType]
    )
    assert type(options.concurrency) is str
    assert type(options.isolation) is str
    assert {options.concurrency: 1, options.isolation: 2}


def test_the_omission_marker_is_one_slotted_value_that_names_itself() -> None:
    # `help(db.transact)` renders each keyword's default through this `repr`,
    # so it reads as omission rather than as an object address.
    assert isinstance(OMITTED, Omitted)
    assert not hasattr(OMITTED, "__dict__")
    assert repr(OMITTED) == "OMITTED"
