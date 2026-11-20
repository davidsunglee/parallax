from __future__ import annotations

import datetime as dt
from typing import Final

import pytest

from parallax.core._execution._unit_work import instructions as wi
from parallax.core._execution._unit_work.preparation import (
    TYPED,
    WIRE,
    PartialPayload,
    WriteRepresentation,
)
from parallax.core._formation_profile import form_metamodel
from parallax.core.internal.base import INT32, STRING, TIMESTAMP, UsageError
from parallax.core.internal.metamodel import (
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
from parallax.core.internal.planned_step.managed_row import named_members
from tests._support.errors import raises_code
from tests._support.write_preparation import (
    REPRESENTATIONS,
    prepare_instruction,
    write_preparation_of,
)
from tests.unit._metamodel_support import Declaration, attribute, identity, key, source

_PLAIN = identity("Plain")
_VERSIONED = identity("Counted")
_TEMPORAL = identity("Recorded")
_ROOT = identity("Root")
_CHILD = identity("Child")
_OWNED: Final = ("txStart", "txEnd", "validStart", "validEnd")
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
                    attribute(_TEMPORAL, name, type=TIMESTAMP, column=column)
                    for name, column in zip(
                        _OWNED, ("in_z", "out_z", "from_z", "thru_z"), strict=True
                    )
                ),
            ),
            as_of_axes=(
                AsOfAxisMetadata(
                    dimension=TemporalDimension.TRANSACTION_TIME,
                    start_attribute=AttributeIdentity(_TEMPORAL, "txStart"),
                    end_attribute=AttributeIdentity(_TEMPORAL, "txEnd"),
                ),
                AsOfAxisMetadata(
                    dimension=TemporalDimension.VALID_TIME,
                    start_attribute=AttributeIdentity(_TEMPORAL, "validStart"),
                    end_attribute=AttributeIdentity(_TEMPORAL, "validEnd"),
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


@REPRESENTATIONS
@pytest.mark.parametrize("value", [1, None, {"increment": 1}, {"computed": "maxPlusOne"}])
def test_a_version_assignment_is_refused_by_role_before_any_value(
    representation: WriteRepresentation, value: object
) -> None:
    instruction = wi.KeyedWriteInstruction(
        "amend", _VERSIONED.canonical, {"id": "bad-key", "label": 7, "revisionCounter": value}
    )
    with raises_code(UsageError, _RULE, match=r"Counted\.revisionCounter"):
        prepare_instruction(instruction, _PREPARATION, representation)


@pytest.mark.parametrize("member", _OWNED)
@pytest.mark.parametrize(
    ("representation", "mutation"),
    [
        (TYPED, "amend"),
        (TYPED, "amendUntil"),
        (WIRE, "amend"),
        (WIRE, "amendUntil"),
        (WIRE, "replace"),
        (WIRE, "replaceUntil"),
    ],
)
def test_temporal_assignment_roles_are_refused_in_bounded_and_unbounded_writes(
    representation: WriteRepresentation, member: str, mutation: wi.KeyedMutation
) -> None:
    instruction = wi.KeyedWriteInstruction(
        mutation,
        _TEMPORAL.canonical,
        {"id": 1, "label": 7, member: {"computed": "txInstant"}},
        valid_from=_START,
        until=_END if mutation.endswith("Until") else None,
    )
    with raises_code(UsageError, _RULE, match=rf"Recorded\.{member}"):
        prepare_instruction(instruction, _PREPARATION, representation)


@REPRESENTATIONS
def test_subtype_metadata_is_judged_before_an_inherited_owned_name(
    representation: WriteRepresentation,
) -> None:
    instruction = wi.KeyedWriteInstruction(
        "amend", _CHILD.canonical, {"id": 1, "revisionCounter": 2, "tagValue": "child"}
    )
    with raises_code(UsageError, "subtype-write-metadata-field"):
        prepare_instruction(instruction, _PREPARATION, representation)


@REPRESENTATIONS
def test_target_and_operation_applicability_precede_assignment_names(
    representation: WriteRepresentation,
) -> None:
    instruction = wi.KeyedWriteInstruction(
        "amendUntil",
        _VERSIONED.canonical,
        {"id": 1, "revisionCounter": 2},
        valid_from=_START,
        until=_END,
    )
    with raises_code(UsageError, "write-instruction-invalid") as refused:
        prepare_instruction(instruction, _PREPARATION, representation)
    assert "Non-Temporal" in str(refused.value) or "non-temporal" in str(refused.value)


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("member", ["revisionCounter", *_OWNED])
def test_typed_partial_payloads_refuse_framework_owned_assignments(
    explicit: bool, member: str
) -> None:
    entity = _VERSIONED if member == "revisionCounter" else _TEMPORAL
    target = _MODEL.entity(entity)
    assert target is not None
    entry = _PREPARATION.entity(entity)
    position = entry.selection.members.shape.position(member)
    assert position is not None
    identity_pair = (entry.key_position, 1)
    with raises_code(UsageError, _RULE):
        wi.prepare_keyed_write(
            _PREPARATION,
            TYPED,
            "amend",
            target,
            PartialPayload((identity_pair,) if explicit else (identity_pair, (position, None))),
            assignments=(wi.WriteAssignment(f"{entity.canonical}.{member}", None),)
            if explicit
            else (),
            valid_from=None if entity == _VERSIONED else _START,
            until=None,
        )


@pytest.mark.parametrize("mutation", ["insert", "replace", "replaceUntil"])
def test_a_typed_complete_payload_omits_carried_temporal_endpoints(
    mutation: wi.KeyedMutation,
) -> None:
    instruction = wi.KeyedWriteInstruction(
        mutation,
        _TEMPORAL.canonical,
        {"id": 1, "label": "accepted", **dict.fromkeys(_OWNED, 7)},
        valid_from=_START,
        until=_END if mutation.endswith("Until") else None,
    )
    prepared = prepare_instruction(instruction, _PREPARATION, TYPED)
    assert named_members(prepared.rows[0]) == {"id": 1, "label": "accepted"}


@REPRESENTATIONS
def test_a_target_missing_its_revision_is_refused_before_payload_ownership(
    representation: WriteRepresentation,
) -> None:
    instruction = wi.TargetWriteInstruction(
        "amend",
        _VERSIONED.canonical,
        {"id": 1, "revisionCounter": 2},
    )
    with raises_code(UsageError, "write-instruction-invalid", match="requires version"):
        prepare_instruction(instruction, _PREPARATION, representation)


@pytest.mark.parametrize("member", _OWNED)
def test_a_wire_insert_refuses_owned_payload_members(member: str) -> None:
    instruction = wi.KeyedWriteInstruction(
        "insert",
        _TEMPORAL.canonical,
        {"id": 1, "label": "accepted", member: None},
        valid_from=_START,
    )
    with raises_code(UsageError, "framework-owned-member-assigned", match="framework-owned"):
        prepare_instruction(instruction, _PREPARATION, WIRE)


@REPRESENTATIONS
@pytest.mark.parametrize(
    ("entity", "member", "mutation"),
    [
        (_VERSIONED, "revisionCounter", "amend"),
        (_TEMPORAL, "txStart", "amend"),
        (_TEMPORAL, "validEnd", "amendUntil"),
    ],
)
def test_authored_ownership_refusal_precedes_undeclared_members(
    representation: WriteRepresentation,
    entity: EntityIdentity,
    member: str,
    mutation: wi.KeyedMutation,
) -> None:
    instruction = wi.KeyedWriteInstruction(
        mutation,
        entity.canonical,
        {"id": 1, "undeclared": 7, member: 2},
        valid_from=_START if entity == _TEMPORAL else None,
        until=_END if mutation == "amendUntil" else None,
    )
    with raises_code(UsageError, _RULE):
        prepare_instruction(instruction, _PREPARATION, representation)
