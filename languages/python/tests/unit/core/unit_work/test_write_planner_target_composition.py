"""How caller-conditioned writes join an object's pending writes, driven at the
composition seam without a database."""

from __future__ import annotations

from decimal import Decimal

import pytest

from parallax.core import inheritance
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import KeyedWrite, RetainedObservation, TargetWrite, buffered_write
from parallax.core.unit_work.instructions import (
    ExpectedVersion,
    PreparedKeyedWrite,
    prepare_wire_write,
)
from parallax.core.unit_work.materialized import TargetKeyedWrite, target_write
from parallax.core.unit_work.write_planner import PendingWrites
from parallax.core.write_plan import ObjectKey, VersionObservation
from parallax.core.write_plan.keys import VersionedStateKey
from tests.unit._corpus_model_support import corpus_records, formed

_ACCOUNT = formed(corpus_records()["account"])
_FAMILIES = inheritance.view(_ACCOUNT)
_OBJECT = ObjectKey(EntityIdentity("parallax.compatibility", "Account"), (("id", 1),))


def _target(version: int, **members: object) -> TargetKeyedWrite:
    return target_write(
        prepare_wire_write(
            TargetWrite("amend", "Account", {"id": 1, **members}, if_version=version), _ACCOUNT
        ),
        _FAMILIES,
    )


def _update(**members: object) -> PreparedKeyedWrite:
    prepared = prepare_wire_write(KeyedWrite("amend", "Account", ({"id": 1, **members},)), _ACCOUNT)
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _retained(version: int) -> RetainedObservation:
    return RetainedObservation(
        VersionedStateKey(_OBJECT, version), VersionObservation(version), None
    )


def test_a_target_write_meets_the_writes_of_its_own_stated_state() -> None:
    pending = PendingWrites(_ACCOUNT)
    observed = _retained(3)
    pending.add(buffered_write(_update(owner="Bo"), observed), _OBJECT)
    target = _target(3, balance="1.00")
    assert pending.admits_target(target, _OBJECT)
    pending.add(target, _OBJECT)
    assert pending.target_scope(_OBJECT) == VersionedStateKey(_OBJECT, 3)
    (merged,) = pending.writes()
    assert isinstance(merged, TargetKeyedWrite)
    assert merged.claims == (observed,)
    assert dict(merged.instruction.rows[0]) == {
        "id": 1,
        "owner": "Bo",
        "balance": Decimal("1.00"),
    }


def test_a_target_write_beside_writes_of_other_states_of_its_object_is_refused() -> None:
    held = PendingWrites(_ACCOUNT)
    held.add(buffered_write(_update(owner="Bo"), VersionObservation(3)), _OBJECT)
    assert not held.admits_target(_target(3, balance="1.00"), _OBJECT)
    several = PendingWrites(_ACCOUNT)
    several.add(buffered_write(_update(owner="Bo"), _retained(2)), _OBJECT)
    several.add(buffered_write(_update(owner="Cy"), _retained(3)), _OBJECT)
    assert not several.admits_target(_target(3, balance="1.00"), _OBJECT)
    other = PendingWrites(_ACCOUNT)
    other.add(_target(3, balance="1.00"), _OBJECT)
    other.add(buffered_write(_update(owner="Bo"), _retained(4)), _OBJECT)
    assert not other.admits_target(_target(4, owner="Di"), _OBJECT)


def test_a_target_carrier_refuses_an_insert_and_a_write_of_several_objects() -> None:
    insert = prepare_wire_write(
        KeyedWrite("insert", "Account", ({"id": 1, "owner": "Ada", "balance": "1.00"},)), _ACCOUNT
    )
    several = prepare_wire_write(
        KeyedWrite("amend", "Account", ({"id": 1, "owner": "Bo"}, {"id": 2, "owner": "Cy"})),
        _ACCOUNT,
    )
    for instruction in (insert, several):
        assert isinstance(instruction, PreparedKeyedWrite)
        with pytest.raises(ValueError, match="addresses one existing object"):
            TargetKeyedWrite(instruction, ExpectedVersion(3), VersionedStateKey(_OBJECT, 3))
