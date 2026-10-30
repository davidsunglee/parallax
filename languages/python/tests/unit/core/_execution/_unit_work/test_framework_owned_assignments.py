from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Final, cast

import pytest

from parallax.core._execution._unit_work import instructions as wi
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import INT32, STRING, TIMESTAMP
from parallax.core.metamodel import (
    AbstractRoot,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    Table,
    TablePerHierarchy,
    TemporalDimension,
)
from parallax.core.write_plan.managed_row import named_members
from tests._support.write_preparation import write_preparation_of
from tests.unit._metamodel_support import Declaration, attribute, identity, key, source

_PLAIN = identity("Plain")
_VERSIONED = identity("Counted")
_TEMPORAL = identity("Recorded")
_ROOT = identity("Root")
_CHILD = identity("Child")
_OWNED: Final = ("entered", "departed", "effective", "expired")
_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_END: Final = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_RULE: Final = "framework-owned-member-assigned"

_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_PLAIN,
            container=Table("plain"),
            attributes=(key(_PLAIN), attribute(_PLAIN, "label", type=STRING)),
        ),
        Declaration(
            identity=_VERSIONED,
            container=Table("counted"),
            attributes=(
                key(_VERSIONED),
                attribute(_VERSIONED, "label", type=STRING),
                AttributeMetadata(
                    identity=AttributeIdentity(_VERSIONED, "revisionCounter"),
                    type=INT32,
                    storage=Column("lock_number"),
                    optimistic_locking=True,
                ),
            ),
        ),
        Declaration(
            identity=_TEMPORAL,
            container=Table("recorded"),
            attributes=(
                key(_TEMPORAL),
                attribute(_TEMPORAL, "label", type=STRING),
                *(
                    attribute(_TEMPORAL, name, type=TIMESTAMP, column=f"bound_{i}")
                    for i, name in enumerate(_OWNED)
                ),
            ),
            as_of_axes=(
                AsOfAxisMetadata(
                    dimension=TemporalDimension.TRANSACTION_TIME,
                    start_attribute=AttributeIdentity(_TEMPORAL, "entered"),
                    end_attribute=AttributeIdentity(_TEMPORAL, "departed"),
                ),
                AsOfAxisMetadata(
                    dimension=TemporalDimension.VALID_TIME,
                    start_attribute=AttributeIdentity(_TEMPORAL, "effective"),
                    end_attribute=AttributeIdentity(_TEMPORAL, "expired"),
                ),
            ),
        ),
        Declaration(
            identity=_ROOT,
            container=Table("root"),
            attributes=(
                key(_ROOT),
                AttributeMetadata(
                    identity=AttributeIdentity(_ROOT, "revisionCounter"),
                    type=INT32,
                    storage=Column("lock_number"),
                    optimistic_locking=True,
                ),
            ),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=_CHILD,
            attributes=(attribute(_CHILD, "label", type=STRING),),
            inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), "child"),
        ),
    )
)
_PREPARATION = write_preparation_of(_MODEL)
_LANES: Final = pytest.mark.parametrize("prepare", [wi.prepare_typed_write, wi.prepare_wire_write])
type _Prepare = Callable[..., Any]


@_LANES
@pytest.mark.parametrize("value", [1, None, {"increment": 1}, {"computed": "maxPlusOne"}])
def test_a_version_assignment_is_refused_by_role_before_any_value(
    prepare: _Prepare, value: object
) -> None:
    instruction = wi.KeyedWriteInstruction(
        "amend", _VERSIONED.canonical, ({"id": "bad-key", "label": 7, "revisionCounter": value},)
    )
    with pytest.raises(wi.InstructionRejectedError, match=r"Counted\.revisionCounter") as refused:
        prepare(instruction, _PREPARATION)
    assert refused.value.rule == _RULE


@_LANES
@pytest.mark.parametrize("member", _OWNED)
@pytest.mark.parametrize("mutation", ["amend", "amendUntil", "replace", "replaceUntil"])
def test_temporal_assignment_roles_are_refused_in_bounded_and_unbounded_writes(
    prepare: _Prepare, member: str, mutation: wi.KeyedMutation
) -> None:
    instruction = wi.KeyedWriteInstruction(
        mutation,
        _TEMPORAL.canonical,
        ({"id": 1, "label": 7, member: {"computed": "txInstant"}},),
        valid_from=_START,
        until=_END if mutation.endswith("Until") else None,
    )
    with pytest.raises(wi.InstructionRejectedError, match=rf"Recorded\.{member}") as refused:
        prepare(instruction, _PREPARATION)
    assert refused.value.rule == _RULE


@_LANES
@pytest.mark.parametrize("bad_row", [0, 1, 2])
def test_each_amendment_row_is_judged(prepare: _Prepare, bad_row: int) -> None:
    rows: list[dict[str, object]] = [{"id": i, "label": "accepted"} for i in range(3)]
    rows[bad_row]["revisionCounter"] = 2
    with pytest.raises(wi.InstructionRejectedError) as refused:
        prepare(wi.KeyedWriteInstruction("amend", _VERSIONED.canonical, tuple(rows)), _PREPARATION)
    assert refused.value.rule == _RULE


@_LANES
def test_an_earlier_rows_value_is_judged_before_a_later_rows_owned_name(prepare: _Prepare) -> None:
    instruction = wi.KeyedWriteInstruction(
        "amend",
        _VERSIONED.canonical,
        ({"id": 1, "label": 7}, {"id": 2, "revisionCounter": 2}),
    )
    with pytest.raises(ValueError, match=r"Counted\.label") as refused:
        prepare(instruction, _PREPARATION)
    assert getattr(refused.value, "rule", None) != _RULE


@_LANES
def test_subtype_metadata_is_judged_before_an_inherited_owned_name(prepare: _Prepare) -> None:
    instruction = wi.KeyedWriteInstruction(
        "amend", _CHILD.canonical, ({"id": 1, "revisionCounter": 2, "tagValue": "child"},)
    )
    with pytest.raises(wi.WriteRejectedError) as refused:
        prepare(instruction, _PREPARATION)
    assert refused.value.rule == "subtype-write-metadata-field"


@_LANES
def test_target_and_operation_applicability_precede_assignment_names(prepare: _Prepare) -> None:
    instruction = wi.KeyedWriteInstruction(
        "amendUntil",
        _VERSIONED.canonical,
        ({"id": 1, "revisionCounter": 2},),
        valid_from=_START,
        until=_END,
    )
    with pytest.raises(wi.WriteInstructionError) as refused:
        prepare(instruction, _PREPARATION)
    assert not isinstance(refused.value, wi.InstructionRejectedError)
    assert "Non-Temporal" in str(refused.value) or "non-temporal" in str(refused.value)


@pytest.mark.parametrize("explicit_members", [False, True])
@pytest.mark.parametrize("member", ["revisionCounter", *_OWNED])
def test_optimized_typed_preparation_refuses_framework_owned_assignments(
    explicit_members: bool, member: str
) -> None:
    entity = _VERSIONED if member == "revisionCounter" else _TEMPORAL
    target = _MODEL.entity(entity)
    assert target is not None
    entry = _PREPARATION.entity(entity)
    position = entry.selection.members.shape.position(member)
    assert position is not None
    with pytest.raises(wi.InstructionRejectedError) as refused:
        wi.prepare_typed_keyed_write(
            _PREPARATION,
            "amend",
            target,
            pairs=((entry.key, 1),) if explicit_members else ((entry.key, 1), (position, None)),
            members=(lambda: {member: None}) if explicit_members else None,
            valid_from=None if entity == _VERSIONED else _START,
            until=None,
        )
    assert refused.value.rule == _RULE


@_LANES
def test_temporal_arguments_and_target_revision_are_not_row_assignments(prepare: _Prepare) -> None:
    for instruction in (
        wi.KeyedWriteInstruction(
            "amendUntil",
            _TEMPORAL.canonical,
            ({"id": 1, "label": "accepted"},),
            valid_from=_START,
            until=_END,
        ),
        wi.TargetWriteInstruction(
            "amendUntil",
            _TEMPORAL.canonical,
            {"id": 1, "label": "accepted"},
            valid_from=_START,
            until=_END,
            if_tx_start=_START,
        ),
        wi.TargetWriteInstruction(
            "amend",
            _VERSIONED.canonical,
            {"id": 1, "label": "accepted"},
            if_version=3,
        ),
    ):
        prepared = prepare(instruction, _PREPARATION)
        assert prepared is not None


@pytest.mark.parametrize("mutation", ["replace", "replaceUntil"])
def test_typed_full_state_replacement_omits_carried_temporal_endpoints(
    mutation: wi.KeyedMutation,
) -> None:
    target = _MODEL.entity(_TEMPORAL)
    assert target is not None
    entry = _PREPARATION.entity(_TEMPORAL)
    values = entry.plan.authored_values({"id": 1, "label": "accepted", **dict.fromkeys(_OWNED, 7)})
    prepared = wi.prepare_typed_keyed_write(
        _PREPARATION,
        mutation,
        target,
        values=values,
        valid_from=_START,
        until=_END if mutation.endswith("Until") else None,
    )
    assert named_members(prepared.rows[0]) == {"id": 1, "label": "accepted"}


@_LANES
def test_neutral_insert_projection_omits_carried_framework_owned_state(prepare: _Prepare) -> None:
    instruction = wi.KeyedWriteInstruction(
        "insert",
        _TEMPORAL.canonical,
        ({"id": 1, "label": "accepted", **dict.fromkeys(_OWNED, 7)},),
        valid_from=_START,
    )
    prepared = cast("wi.PreparedKeyedInstruction", prepare(instruction, _PREPARATION))
    assert named_members(prepared.rows[0]) == {"id": 1, "label": "accepted"}


@_LANES
def test_owned_names_are_refused_before_undeclared_names(prepare: _Prepare) -> None:
    instruction = wi.KeyedWriteInstruction(
        "amend",
        _VERSIONED.canonical,
        ({"id": 1, "undeclared": 7, "revisionCounter": 2},),
    )
    with pytest.raises(wi.InstructionRejectedError) as refused:
        prepare(instruction, _PREPARATION)
    assert refused.value.rule == _RULE


@_LANES
def test_a_target_missing_its_revision_is_refused_before_payload_ownership(
    prepare: _Prepare,
) -> None:
    instruction = wi.TargetWriteInstruction(
        "amend",
        _VERSIONED.canonical,
        {"id": 1, "revisionCounter": 2},
    )
    with pytest.raises(wi.WriteInstructionError, match="requires version"):
        prepare(instruction, _PREPARATION)


@pytest.mark.parametrize("member", _OWNED)
def test_an_explicit_wire_insert_still_refuses_owned_payload_members(member: str) -> None:
    target = _MODEL.entity(_TEMPORAL)
    assert target is not None
    with pytest.raises(wi.WriteInstructionError, match="framework-owned"):
        wi.prepare_wire_insert(
            _PREPARATION,
            "insert",
            target,
            {"id": 1, "label": "accepted", member: None},
            valid_from=_START,
            until=None,
        )


def test_typed_insert_projection_omits_carried_temporal_state() -> None:
    target = _MODEL.entity(_TEMPORAL)
    assert target is not None
    entry = _PREPARATION.entity(_TEMPORAL)
    values = entry.plan.authored_values({"id": 1, "label": "accepted", **dict.fromkeys(_OWNED, 7)})
    prepared = wi.prepare_typed_insert(
        _PREPARATION,
        "insert",
        target,
        values=values,
        valid_from=_START,
        until=None,
    )
    assert named_members(prepared.rows[0]) == {"id": 1, "label": "accepted"}


def test_typed_replacement_projection_omits_carried_version_state() -> None:
    target = _MODEL.entity(_VERSIONED)
    assert target is not None
    entry = _PREPARATION.entity(_VERSIONED)
    values = entry.plan.authored_values({"id": 1, "label": "accepted", "revisionCounter": 7})
    prepared = wi.prepare_typed_keyed_write(
        _PREPARATION,
        "replace",
        target,
        values=values,
        valid_from=None,
        until=None,
    )
    assert named_members(prepared.rows[0]) == {"id": 1, "label": "accepted"}


@pytest.fixture
def ownership_scans(monkeypatch: pytest.MonkeyPatch) -> list[None]:
    scans: list[None] = []
    original = wi._refuse_owned_names

    def counted(*args: Any, **kwargs: Any) -> None:
        scans.append(None)
        original(*args, **kwargs)

    monkeypatch.setattr(wi, "_refuse_owned_names", counted)
    return scans


@_LANES
@pytest.mark.parametrize("entity", [_PLAIN, _VERSIONED])
@pytest.mark.parametrize("authorship", ["neutral", "authored", "members"])
def test_keyed_amendment_ownership_is_scanned_once_only_when_needed(
    ownership_scans: list[None], prepare: _Prepare, entity: EntityIdentity, authorship: str
) -> None:
    row = {"id": 1, "label": "accepted"}
    instruction = wi.KeyedWriteInstruction("amend", entity.canonical, (row,))
    if authorship == "members":
        prepare(instruction, _PREPARATION, members=lambda: {"label": "accepted"})
    else:
        prepare(
            instruction,
            _PREPARATION,
            authored_members=row.keys() if authorship == "authored" else None,
        )

    assert len(ownership_scans) == (1 if entity == _VERSIONED else 0)


@pytest.mark.parametrize("entity", [_PLAIN, _VERSIONED])
@pytest.mark.parametrize("explicit_members", [False, True])
def test_optimized_typed_ownership_is_scanned_once_only_when_needed(
    ownership_scans: list[None], entity: EntityIdentity, explicit_members: bool
) -> None:
    target = _MODEL.entity(entity)
    assert target is not None
    entry = _PREPARATION.entity(entity)
    label = entry.selection.members.shape.position("label")
    assert label is not None
    wi.prepare_typed_keyed_write(
        _PREPARATION,
        "amend",
        target,
        pairs=((entry.key, 1),) if explicit_members else ((entry.key, 1), (label, "accepted")),
        members=(lambda: {"label": "accepted"}) if explicit_members else None,
        valid_from=None,
        until=None,
    )

    assert len(ownership_scans) == (1 if entity == _VERSIONED else 0)
