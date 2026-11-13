"""DB-free tests for the shared-allocator oracle (m-pk-gen logical allocators)."""

from __future__ import annotations

from typing import Any

import pytest

from reference_harness.pk_gen import PK_GEN_SEQUENCE_CONFLICT, validate_shared_allocators
from reference_harness.value_object_resolve import RejectionError


def _keyed(name: str, generation: Any, key_type: str = "int64") -> dict[str, Any]:
    return {
        "name": name,
        "table": name.lower(),
        "attributes": [
            {"name": "id", "type": key_type, "primaryKey": True, "pkGeneration": generation}
        ],
    }


def _sequence(**settings: Any) -> dict[str, Any]:
    return {"strategy": "sequence", "name": "shared_seq", **settings}


def test_equal_keys_with_equal_settings_share_after_defaults_are_filled() -> None:
    validate_shared_allocators(
        [_keyed("Badge", _sequence()), _keyed("Ticket", _sequence(batchSize=1, initialValue=1))]
    )


def test_max_and_distinct_keys_are_never_compared() -> None:
    validate_shared_allocators(
        [
            _keyed("Badge", "max"),
            _keyed("Ticket", {"strategy": "sequence", "name": "a", "batchSize": 3}),
            _keyed("Voucher", {"strategy": "sequence", "name": "b"}, "int32"),
        ]
    )


@pytest.mark.parametrize(
    ("settings", "key_type"),
    [
        ({"batchSize": 2}, "int64"),
        ({"initialValue": 9}, "int64"),
        ({"incrementSize": 3}, "int64"),
        ({}, "int32"),
    ],
    ids=["batch-size", "initial-value", "increment-size", "key-type"],
)
def test_each_disagreeing_term_is_refused(settings: dict[str, Any], key_type: str) -> None:
    with pytest.raises(RejectionError) as raised:
        validate_shared_allocators(
            [_keyed("Badge", _sequence()), _keyed("Ticket", _sequence(**settings), key_type)]
        )
    assert raised.value.rule == PK_GEN_SEQUENCE_CONFLICT


def test_a_family_key_counts_once_on_its_declaring_root() -> None:
    root = {
        "name": "Vehicle",
        "inheritance": {"strategy": "table-per-concrete-subtype", "role": "root"},
        "attributes": [
            {"name": "id", "type": "int64", "primaryKey": True, "pkGeneration": _sequence()}
        ],
    }
    leaves = [
        {
            "name": name,
            "table": name.lower(),
            "inheritance": {"role": "concrete-subtype", "parent": "Vehicle"},
            "attributes": [{"name": "seats", "type": "int32"}],
        }
        for name in ("Car", "Truck")
    ]
    validate_shared_allocators([root, *leaves, _keyed("Fleet", _sequence())])
    with pytest.raises(RejectionError) as raised:
        validate_shared_allocators([root, *leaves, _keyed("Fleet", _sequence(batchSize=4))])
    assert "Vehicle.id" in raised.value.detail
