"""Causal attribution over one rule (m-schema-delta), Docker-free.

An Evolution Operation is a cause of a physical operation exactly when a fact IT
moved is one of the facts the physical difference is made of. That is one rule
with two edges, and both are asserted here: a difference several operations were
each needed for names all of them, and an operation that moved only facts the
database does not hold — a write flag, a read-only marker — names nothing.

These read the plan directly because most of the attribution has no public
surface. Only `restate_column` and `create_index` can be refused, so
`UnsupportedSchemaOperation` exposes the causes of those two alone
(`test_schema_delta_errors.py`); a Column addition's causes are reachable
nowhere else.
"""

from __future__ import annotations

from _corpus_model_support import formed

from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.descriptor._records import (
    Attribute,
    Entity,
    Index,
    Inheritance,
    Metamodel,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.evolution.model_evolution import UnilateralEvolution, evolve
from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateIndex,
    PhysicalOperation,
    RestateColumnDomain,
)
from parallax.evolution.schema_delta._plan import plan


def _tpcs(*, sealed: bool, reparented: bool, own_lid: bool = False) -> AcceptedMetamodel:
    """A table-per-concrete-subtype family whose ancestry and members both vary.

    `Casket` hangs directly under the root or under `Warded`; `Other` is under
    `Warded` throughout, so one evolution moves a declaration into one concrete
    Table and leaves the other's arrival unconditional.
    """
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    warded = Entity(
        name="Warded",
        inheritance=Inheritance(role="abstract-subtype", parent="Root"),
        attributes=(
            (Attribute(name="seal", type="string", column="seal", max_length=16, nullable=True),)
            if sealed
            else ()
        ),
        indices=(Index(name="seal_ix", attributes=("seal",)),) if sealed else (),
    )
    casket = Entity(
        name="Casket",
        table="casket",
        inheritance=Inheritance(role="concrete-subtype", parent="Warded" if reparented else "Root"),
        attributes=(
            (Attribute(name="lid", type="int32", column="lid", nullable=True),) if own_lid else ()
        ),
    )
    other = Entity(
        name="Other",
        table="other",
        inheritance=Inheritance(role="concrete-subtype", parent="Warded"),
        attributes=(Attribute(name="z", type="int32", column="z"),),
    )
    return formed(Metamodel(entities=(root, warded, casket, other)))


def _tph_siblings(*, sealed: bool, reparented: bool) -> AcceptedMetamodel:
    """A table-per-hierarchy family whose siblings share one Table.

    `Casket` hangs directly under the root or under `Warded`, and `Other` — a
    sibling `Casket` never inherits from — declares the members that arrive. One
    Table therefore holds a declaration the reparent did not carry anywhere.
    """
    root = Entity(
        name="Root",
        table="vault",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    warded = Entity(name="Warded", inheritance=Inheritance(role="abstract-subtype", parent="Root"))
    casket = Entity(
        name="Casket",
        inheritance=Inheritance(
            role="concrete-subtype",
            parent="Warded" if reparented else "Root",
            tag_value="casket",
        ),
    )
    other = Entity(
        name="Other",
        inheritance=Inheritance(role="concrete-subtype", parent="Warded", tag_value="other"),
        attributes=(
            (Attribute(name="seal", type="string", column="seal", max_length=16, nullable=True),)
            if sealed
            else ()
        ),
        indices=(Index(name="seal_ix", attributes=("seal",)),) if sealed else (),
    )
    return formed(Metamodel(entities=(root, warded, casket, other)))


def _tph_position_role(*, note_concrete: bool, coupon_read_only: bool) -> AcceptedMetamodel:
    """A table-per-hierarchy family whose stored shapes and a write flag both vary.

    `Bond.coupon` is required of the only stored shape while `Note` is abstract,
    so admitting `Note` as a concrete one relaxes a Column a DIFFERENT Entity
    declares — beside a `readOnly` change that moves no physical fact at all.
    """
    instrument = Entity(
        name="Instrument",
        table="instrument",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    note = Entity(
        name="Note",
        inheritance=Inheritance(
            role="concrete-subtype" if note_concrete else "abstract-subtype",
            parent="Instrument",
            tag_value="note" if note_concrete else None,
        ),
    )
    bond = Entity(
        name="Bond",
        inheritance=Inheritance(role="concrete-subtype", parent="Instrument", tag_value="bond"),
        attributes=(
            Attribute(name="coupon", type="int32", column="coupon", read_only=coupon_read_only),
        ),
    )
    return formed(Metamodel(entities=(instrument, note, bond)))


def _parcel(*, origin_nullable: bool) -> AcceptedMetamodel:
    """One Entity whose top-level Value Object occurrence may or may not be absent."""
    return formed(
        Metamodel(
            entities=(
                Entity(
                    name="Parcel",
                    table="parcel",
                    attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
                    value_objects=(
                        ValueObject(
                            name="origin",
                            nullable=origin_nullable,
                            attributes=(ValueObjectAttribute(name="city", type="string"),),
                        ),
                    ),
                ),
            )
        )
    )


def _operations(
    earlier: AcceptedMetamodel, later: AcceptedMetamodel
) -> tuple[PhysicalOperation, ...]:
    evolution = evolve(earlier, later)
    assert isinstance(evolution, UnilateralEvolution)
    return plan(evolution, POSTGRES).operations


def _causes(operation: PhysicalOperation) -> list[str]:
    return [type(cause).__name__ for cause in operation.caused_by]


def _added(operations: tuple[PhysicalOperation, ...], table: str) -> AddColumn:
    (added,) = [
        operation
        for operation in operations
        if isinstance(operation, AddColumn) and operation.table.name == table
    ]
    return added


def _created(operations: tuple[PhysicalOperation, ...], table: str) -> CreateIndex:
    (created,) = [
        operation
        for operation in operations
        if isinstance(operation, CreateIndex) and operation.definition.table.name == table
    ]
    return created


def test_an_addition_and_the_reparent_that_carried_it_here_are_both_causes() -> None:
    # Neither operation alone put `seal` in `casket`: without the addition there
    # is no declaration, and without the reparent the declaration reaches a
    # family branch `casket` is not in. The causes are in canonical operation
    # order, which puts the Entity alteration before the member addition.
    operations = _operations(
        _tpcs(sealed=False, reparented=False), _tpcs(sealed=True, reparented=True)
    )
    assert _causes(_added(operations, "casket")) == ["EntityAltered", "AttributeAdded"]
    assert _causes(_created(operations, "casket")) == ["EntityAltered", "IndexAdded"]


def test_a_table_the_reparent_did_not_touch_names_the_addition_alone() -> None:
    # `Other` was under `Warded` at both endpoints, so its copy of the same
    # declaration arrived because the declaration arrived and for no other
    # reason. Naming the reparent here would be the over-attribution a union
    # invites.
    operations = _operations(
        _tpcs(sealed=False, reparented=False), _tpcs(sealed=True, reparented=True)
    )
    assert _causes(_added(operations, "other")) == ["AttributeAdded"]
    assert _causes(_created(operations, "other")) == ["IndexAdded"]


def test_a_reparent_is_no_cause_of_a_column_the_reparented_entity_declares() -> None:
    # An Entity always held its own declarations, so moving it in the ancestry
    # is not why one of them materialized: `lid` lands in `casket` on the
    # strength of its own addition however `Casket` is parented.
    operations = _operations(
        _tpcs(sealed=False, reparented=False),
        _tpcs(sealed=False, reparented=True, own_lid=True),
    )
    assert _causes(_added(operations, "casket")) == ["AttributeAdded"]


def test_a_reparent_is_no_cause_of_a_sibling_declaration_sharing_the_Table() -> None:
    # `Casket` moving under `Warded` and `Other` gaining `seal` land in one
    # table-per-hierarchy Table, but `Casket` never inherits from `Other`, so the
    # reparent carried this declaration to no rows at all. Asking only whether
    # the owner was absent EARLIER would name it: every sibling's owner is.
    operations = _operations(
        _tph_siblings(sealed=False, reparented=False),
        _tph_siblings(sealed=True, reparented=True),
    )
    assert _causes(_added(operations, "vault")) == ["AttributeAdded"]
    assert _causes(_created(operations, "vault")) == ["IndexAdded"]


def test_an_alteration_moving_no_physical_fact_causes_nothing() -> None:
    # `Bond.coupon` becoming writable and `Note` becoming concrete are both
    # unilateral, and only the second one widened anything: a write flag is not a
    # fact the database holds, so the relaxed Column answers to the arriving
    # shape alone.
    operations = _operations(
        _tph_position_role(note_concrete=False, coupon_read_only=True),
        _tph_position_role(note_concrete=True, coupon_read_only=False),
    )
    (widened,) = [
        operation for operation in operations if isinstance(operation, RestateColumnDomain)
    ]
    assert widened.later.column.name == "coupon"
    assert _causes(widened) == ["EntityAltered"]


def test_a_relaxed_value_object_occurrence_names_its_own_alteration() -> None:
    # A Structured Column's stored domain is its occurrence's nullability, so the
    # occurrence alteration is the operation that widened it. Asking only about
    # Attribute alterations would leave this widening caused by nothing.
    operations = _operations(_parcel(origin_nullable=False), _parcel(origin_nullable=True))
    (widened,) = [
        operation for operation in operations if isinstance(operation, RestateColumnDomain)
    ]
    assert widened.later.column.name == "origin"
    assert _causes(widened) == ["ValueObjectOccurrenceAltered"]
