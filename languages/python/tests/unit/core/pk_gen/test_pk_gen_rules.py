"""m-pk-gen: equal Sequence allocator keys share one allocator and must agree."""

from __future__ import annotations

import pytest

from parallax.core._formation_profile import form_metamodel
from parallax.core.internal.base import INT32, INT64
from parallax.core.internal.metamodel import (
    AbstractRoot,
    AttributeIdentity,
    AttributeLocation,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    MetamodelIssue,
    PrimaryKey,
    Sequence,
    Table,
    TablePerConcreteSubtype,
    UnresolvedEntityDeclaration,
)
from parallax.core.internal.model_formation import MetamodelValidationError
from parallax.core.internal.pk_gen._rules import SEQUENCE_CONFLICT
from tests.unit._metamodel_support import Declaration, attribute, identity, key, source

_BADGE = identity("Badge")
_TICKET = identity("Ticket")
_VOUCHER = identity("Voucher")


def _standalone(
    entity: EntityIdentity, sequence: Sequence, *, wide: bool = True
) -> UnresolvedEntityDeclaration:
    return Declaration(
        identity=entity,
        container=Table(entity.name.lower()),
        attributes=(
            attribute(
                entity, "id", type=INT64 if wide else INT32, primary_key=PrimaryKey(sequence)
            ),
        ),
    )


def _rejection(*declarations: UnresolvedEntityDeclaration) -> tuple[MetamodelIssue, ...]:
    with pytest.raises(MetamodelValidationError) as raised:
        form_metamodel(source(*declarations))
    return raised.value.issues


def _id(entity: EntityIdentity) -> AttributeLocation:
    return AttributeLocation(AttributeIdentity(entity, "id"))


def test_equal_keys_with_equal_settings_share_one_allocator() -> None:
    shared = Sequence("shared_seq", batch_size=5, initial_value=100, increment_size=2)
    formed = form_metamodel(source(_standalone(_BADGE, shared), _standalone(_TICKET, shared)))
    assert {entity.identity for entity in formed.entities} == {_BADGE, _TICKET}


def test_distinct_keys_never_compare_their_settings() -> None:
    form_metamodel(
        source(
            _standalone(_BADGE, Sequence("badge_seq", batch_size=1)),
            _standalone(_TICKET, Sequence("ticket_seq", batch_size=9), wide=False),
        )
    )


@pytest.mark.parametrize(
    ("later", "wide"),
    [
        (Sequence("shared_seq", batch_size=2), True),
        (Sequence("shared_seq", initial_value=50), True),
        (Sequence("shared_seq", increment_size=3), True),
        (Sequence("shared_seq"), False),
    ],
    ids=["batch-size", "initial-value", "increment-size", "key-type"],
)
def test_one_disagreeing_term_is_a_conflict_at_the_later_declaration(
    later: Sequence, wide: bool
) -> None:
    issues = _rejection(
        _standalone(_BADGE, Sequence("shared_seq")), _standalone(_TICKET, later, wide=wide)
    )
    assert issues == (MetamodelIssue(SEQUENCE_CONFLICT, _id(_TICKET), (_id(_BADGE),)),)


def test_every_disagreeing_declaration_is_related_to_the_first_canonical_one() -> None:
    # Frontend order differs from canonical order; the first canonical
    # declaration is the reference every other declaration is judged against.
    issues = _rejection(
        _standalone(_VOUCHER, Sequence("shared_seq", batch_size=3)),
        _standalone(_TICKET, Sequence("shared_seq", batch_size=2)),
        _standalone(_BADGE, Sequence("shared_seq")),
    )
    assert issues == (
        MetamodelIssue(SEQUENCE_CONFLICT, _id(_TICKET), (_id(_BADGE),)),
        MetamodelIssue(SEQUENCE_CONFLICT, _id(_VOUCHER), (_id(_BADGE),)),
    )


def _tpcs_family(sequence: Sequence) -> tuple[UnresolvedEntityDeclaration, ...]:
    root, car, truck = identity("Vehicle"), identity("Car"), identity("Truck")
    return (
        Declaration(
            identity=root,
            attributes=(key(root, generation=sequence),),
            inheritance=AbstractRoot(TablePerConcreteSubtype()),
        ),
        Declaration(
            identity=car,
            container=Table("car"),
            attributes=(attribute(car, "seats", type=INT32),),
            inheritance=ConcreteSubtype(ExactEntityReference(root)),
        ),
        Declaration(
            identity=truck,
            container=Table("truck"),
            attributes=(attribute(truck, "axles", type=INT32),),
            inheritance=ConcreteSubtype(ExactEntityReference(root)),
        ),
    )


def test_a_tableless_family_root_declaration_counts_once() -> None:
    # `Fleet` sorts before the family, so per-position counting would report
    # the root and both inheriting concrete subtypes.
    fleet = identity("Fleet")
    issues = _rejection(
        _standalone(fleet, Sequence("vehicle_seq")),
        *_tpcs_family(Sequence("vehicle_seq", batch_size=4)),
    )
    assert issues == (MetamodelIssue(SEQUENCE_CONFLICT, _id(identity("Vehicle")), (_id(fleet),)),)


def test_an_inherited_family_allocator_shares_with_an_agreeing_standalone() -> None:
    shared = Sequence("vehicle_seq", batch_size=4)
    form_metamodel(source(_standalone(identity("Fleet"), shared), *_tpcs_family(shared)))
