"""`DatabaseOptions` (spec §5): the built-in record, the field rules
construction is held to — the same rules an explicit `db.transact` keyword
meets — the immutability of what a root is connected with, and the private
marker an omitted transaction keyword defaults to.
"""

from __future__ import annotations

import dataclasses

import pytest

from parallax.snapshot import DatabaseOptions
from parallax.snapshot.handle._options import OMITTED, Omitted


def test_the_built_in_record_is_ten_optimistic_off_and_read_committed() -> None:
    options = DatabaseOptions()
    assert options.max_retries == 10
    assert options.concurrency == "optimistic"
    assert options.retry_optimistic_conflicts is False
    assert options.isolation == "read_committed"


def test_the_record_is_frozen_and_slotted() -> None:
    options = DatabaseOptions()
    with pytest.raises(dataclasses.FrozenInstanceError):
        options.max_retries = 3  # pyright: ignore[reportAttributeAccessIssue] - the refusal is what this proves
    assert not hasattr(options, "__dict__")


def test_every_field_is_configurable_and_compares_by_value() -> None:
    configured = DatabaseOptions(
        max_retries=0,
        concurrency="locking",
        retry_optimistic_conflicts=True,
        isolation="serializable",
    )
    assert configured == DatabaseOptions(
        max_retries=0,
        concurrency="locking",
        retry_optimistic_conflicts=True,
        isolation="serializable",
    )
    assert configured != DatabaseOptions()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("max_retries", -1, "max_retries must be >= 0"),
        ("max_retries", True, "max_retries must be a nonnegative int"),
        ("max_retries", 1.0, "max_retries must be a nonnegative int"),
        ("max_retries", "10", "max_retries must be a nonnegative int"),
        ("max_retries", None, "max_retries must be a nonnegative int"),
        ("concurrency", "pessimistic", r"concurrency must be one of \['locking', 'optimistic'\]"),
        ("concurrency", None, "concurrency must be one of"),
        ("retry_optimistic_conflicts", 1, "retry_optimistic_conflicts must be a bool"),
        ("retry_optimistic_conflicts", "true", "retry_optimistic_conflicts must be a bool"),
        ("retry_optimistic_conflicts", None, "retry_optimistic_conflicts must be a bool"),
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
        DatabaseOptions(**{field: value})  # pyright: ignore[reportArgumentType] - the runtime refusal of an untyped caller is what this proves


def test_an_accepted_vocabulary_value_is_stored_as_its_canonical_spelling() -> None:
    class Spelled(str):
        __hash__ = None  # type: ignore[assignment]

    options = DatabaseOptions(
        concurrency=Spelled("locking"),  # pyright: ignore[reportArgumentType]
        isolation=Spelled("serializable"),  # pyright: ignore[reportArgumentType]
    )
    assert type(options.concurrency) is str
    assert type(options.isolation) is str
    assert {options.concurrency: 1, options.isolation: 2}


def test_zero_retries_is_a_value_rather_than_an_omission() -> None:
    assert DatabaseOptions(max_retries=0).max_retries == 0
    assert DatabaseOptions(retry_optimistic_conflicts=False).retry_optimistic_conflicts is False


def test_the_omission_marker_is_one_slotted_value_that_names_itself() -> None:
    # `help(db.transact)` renders each keyword's default through this `repr`,
    # so it reads as omission rather than as an object address.
    assert isinstance(OMITTED, Omitted)
    assert not hasattr(OMITTED, "__dict__")
    assert repr(OMITTED) == "OMITTED"
