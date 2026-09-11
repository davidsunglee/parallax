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
from parallax.evolution.model_evolution import (
    ConcreteSubtypeAdded,
    EntityAdded,
    EntityAltered,
    UnilateralEvolution,
    evolve,
)
from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateIndex,
    CreateTable,
    PhysicalOperation,
    RestateColumnDomain,
)
from parallax.evolution.schema_delta._plan import plan
from tests.unit._corpus_model_support import formed


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


def _tpcs_new_branch(*, reparented: bool, child: bool, stray: bool) -> AcceptedMetamodel:
    """A table-per-concrete-subtype family gaining whole Tables under two branches.

    `Warded` declares `seal` and `seal_ix` at both endpoints. `Branch` hangs
    directly under the root or under `Warded` and carries the concrete `Child`,
    while `Stray` arrives under `Warded` wherever `Branch` goes, so one created
    Table depends on the move and the other does not.
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
            Attribute(name="seal", type="string", column="seal", max_length=16, nullable=True),
        ),
        indices=(Index(name="seal_ix", attributes=("seal",)),),
    )
    branch = Entity(
        name="Branch",
        inheritance=Inheritance(role="abstract-subtype", parent="Warded" if reparented else "Root"),
    )
    other = Entity(
        name="Other",
        table="other",
        inheritance=Inheritance(role="concrete-subtype", parent="Warded"),
        attributes=(Attribute(name="z", type="int32", column="z"),),
    )
    arriving = tuple(
        entity
        for entity, present in (
            (
                Entity(
                    name="Child",
                    table="child",
                    inheritance=Inheritance(role="concrete-subtype", parent="Branch"),
                ),
                child,
            ),
            (
                Entity(
                    name="Stray",
                    table="stray",
                    inheritance=Inheritance(role="concrete-subtype", parent="Warded"),
                ),
                stray,
            ),
        )
        if present
    )
    return formed(Metamodel(entities=(root, warded, branch, other, *arriving)))


def _tpcs_within_owner(*, moved: bool, child: bool) -> AcceptedMetamodel:
    """A table-per-concrete-subtype family whose reparent stays under one declarer.

    `Warded` declares `seal` and `seal_ix` at both endpoints, and `Left` and
    `Right` are abstract positions directly beneath it declaring nothing, so
    `Branch` moving from one to the other stands under `Warded` throughout. The
    concrete `Child` arrives beneath `Branch` in the same evolution.
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
            Attribute(name="seal", type="string", column="seal", max_length=16, nullable=True),
        ),
        indices=(Index(name="seal_ix", attributes=("seal",)),),
    )
    left = Entity(name="Left", inheritance=Inheritance(role="abstract-subtype", parent="Warded"))
    right = Entity(name="Right", inheritance=Inheritance(role="abstract-subtype", parent="Warded"))
    branch = Entity(
        name="Branch",
        inheritance=Inheritance(role="abstract-subtype", parent="Right" if moved else "Left"),
    )
    other = Entity(
        name="Other",
        table="other",
        inheritance=Inheritance(role="concrete-subtype", parent="Warded"),
        attributes=(Attribute(name="z", type="int32", column="z"),),
    )
    arriving = (
        (
            Entity(
                name="Child",
                table="child",
                inheritance=Inheritance(role="concrete-subtype", parent="Branch"),
            ),
        )
        if child
        else ()
    )
    return formed(Metamodel(entities=(root, warded, left, right, branch, other, *arriving)))


def _tpcs_two_reparents(*, branch_warded: bool, twig_far: bool, child: bool) -> AcceptedMetamodel:
    """A table-per-concrete-subtype family two inheritance alterations move at once.

    `Warded` declares `seal` and `seal_ix` at both endpoints. `Branch` hangs
    directly under the root or under `Warded`, and `Near` and its own child `Far`
    are declaration-free positions beneath `Branch`, so `Twig` moving from one to
    the other never leaves `Branch`'s subtree — yet `Warded` enters `Twig`'s
    ancestry across the same evolution, because `Branch` moved. The concrete
    `Child` beneath `Twig` puts a Table under both moves at once.
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
            Attribute(name="seal", type="string", column="seal", max_length=16, nullable=True),
        ),
        indices=(Index(name="seal_ix", attributes=("seal",)),),
    )
    branch = Entity(
        name="Branch",
        inheritance=Inheritance(
            role="abstract-subtype", parent="Warded" if branch_warded else "Root"
        ),
    )
    near = Entity(name="Near", inheritance=Inheritance(role="abstract-subtype", parent="Branch"))
    far = Entity(name="Far", inheritance=Inheritance(role="abstract-subtype", parent="Near"))
    twig = Entity(
        name="Twig",
        inheritance=Inheritance(role="abstract-subtype", parent="Far" if twig_far else "Near"),
    )
    other = Entity(
        name="Other",
        table="other",
        inheritance=Inheritance(role="concrete-subtype", parent="Warded"),
        attributes=(Attribute(name="z", type="int32", column="z"),),
    )
    arriving = (
        (
            Entity(
                name="Child",
                table="child",
                inheritance=Inheritance(role="concrete-subtype", parent="Twig"),
            ),
        )
        if child
        else ()
    )
    return formed(Metamodel(entities=(root, warded, branch, near, far, twig, other, *arriving)))


def _tpcs_vacated_owner(
    *, sealed: bool, old_warded: bool, branch_new: bool, child: bool
) -> AcceptedMetamodel:
    """A table-per-concrete-subtype family whose vacated position leaves the declarer.

    `Warded` declares `seal` and `seal_ix` once it is sealed, and `Old` and `New`
    are declaration-free positions beneath it. `Old` moves out to the root in the
    same evolution that moves `Branch` from `Old` to `New`, so `Branch` stands
    under `Warded` at both endpoints and yet takes the concrete `Child` arriving
    beneath it out of `Old`'s departure.
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
    old = Entity(
        name="Old",
        inheritance=Inheritance(role="abstract-subtype", parent="Warded" if old_warded else "Root"),
    )
    new = Entity(name="New", inheritance=Inheritance(role="abstract-subtype", parent="Warded"))
    branch = Entity(
        name="Branch",
        inheritance=Inheritance(role="abstract-subtype", parent="New" if branch_new else "Old"),
    )
    other = Entity(
        name="Other",
        table="other",
        inheritance=Inheritance(role="concrete-subtype", parent="Warded"),
        attributes=(Attribute(name="z", type="int32", column="z"),),
    )
    arriving = (
        (
            Entity(
                name="Child",
                table="child",
                inheritance=Inheritance(role="concrete-subtype", parent="Branch"),
            ),
        )
        if child
        else ()
    )
    return formed(Metamodel(entities=(root, warded, old, new, branch, other, *arriving)))


def _tpcs_rotation(*, rotated: bool, child: bool) -> AcceptedMetamodel:
    """A table-per-concrete-subtype family whose two alterations exchange one edge.

    `Owner` declares `seal` and `seal_ix` at both endpoints. Earlier `Pivot`
    hangs under the root with `Arm` beneath it; later `Arm` hangs under `Owner`
    with `Pivot` beneath it, so the two moves swap the edge between them and
    together put the concrete `Child` under `Owner`. Neither move alone does,
    and neither can be undone on its own: restoring one leaves the other
    pointing back at it.
    """
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    owner = Entity(
        name="Owner",
        inheritance=Inheritance(role="abstract-subtype", parent="Root"),
        attributes=(
            Attribute(name="seal", type="string", column="seal", max_length=16, nullable=True),
        ),
        indices=(Index(name="seal_ix", attributes=("seal",)),),
    )
    arm = Entity(
        name="Arm",
        inheritance=Inheritance(role="abstract-subtype", parent="Owner" if rotated else "Pivot"),
    )
    pivot = Entity(
        name="Pivot",
        inheritance=Inheritance(role="abstract-subtype", parent="Arm" if rotated else "Root"),
    )
    other = Entity(
        name="Other",
        table="other",
        inheritance=Inheritance(role="concrete-subtype", parent="Owner"),
        attributes=(Attribute(name="z", type="int32", column="z"),),
    )
    arriving = (
        (
            Entity(
                name="Child",
                table="child",
                inheritance=Inheritance(role="concrete-subtype", parent="Pivot"),
            ),
        )
        if child
        else ()
    )
    return formed(Metamodel(entities=(root, owner, arm, pivot, other, *arriving)))


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


def _tph_ancestor(*, sealed: bool, reparented: bool) -> AcceptedMetamodel:
    """A table-per-hierarchy family whose new ancestor already reaches the Table.

    `Warded` declares the members that arrive, and `Other` stands under it at
    both endpoints, so the family's one Table already materializes `Warded`
    wherever `Casket` hangs.
    """
    root = Entity(
        name="Root",
        table="vault",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
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
        inheritance=Inheritance(
            role="concrete-subtype",
            parent="Warded" if reparented else "Root",
            tag_value="casket",
        ),
    )
    other = Entity(
        name="Other",
        inheritance=Inheritance(role="concrete-subtype", parent="Warded", tag_value="other"),
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


def _entity_causes(operation: PhysicalOperation) -> list[str]:
    """Every cause, naming its Entity where it has one, to tell two alterations apart."""
    return [
        f"{type(cause).__name__}({cause.entity.name})"
        if isinstance(cause, (ConcreteSubtypeAdded, EntityAdded, EntityAltered))
        else type(cause).__name__
        for cause in operation.caused_by
    ]


def _added(operations: tuple[PhysicalOperation, ...], table: str) -> AddColumn:
    (added,) = [
        operation
        for operation in operations
        if isinstance(operation, AddColumn) and operation.table.name == table
    ]
    return added


def _creates(operations: tuple[PhysicalOperation, ...], table: str) -> CreateTable:
    (created,) = [
        operation
        for operation in operations
        if isinstance(operation, CreateTable) and operation.table.name == table
    ]
    return created


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
    # `casket` already materialized `Casket`'s own position, so moving `Casket`
    # in the ancestry is not why one of its declarations landed there: `lid`
    # lands on the strength of its own addition however `Casket` is parented.
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


def test_a_reparent_under_an_ancestor_the_Table_already_holds_names_the_addition_alone() -> None:
    # `Warded` gains `seal` while `Casket` moves under it, but `Other` stood
    # under `Warded` in the same Table all along, so that Table materializes the
    # arriving declarations whatever `Casket` does. Asking whether the
    # REPARENTED Entity gained the declaring owner would name the alteration
    # here; the question belongs to the Table.
    operations = _operations(
        _tph_ancestor(sealed=False, reparented=False),
        _tph_ancestor(sealed=True, reparented=True),
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


def test_a_created_Table_names_the_reparent_that_carried_a_declaration_into_it() -> None:
    # `child` holds `seal` only because BOTH `Branch` moved under `Warded` and
    # `Child` arrived beneath `Branch`: without the move the new Table repeats no
    # `Warded` member, and without the addition there is no Table. A created
    # Table is all of its Columns at once, so it answers to the rule an added
    # Column answers to, and the Index created with it carries the same causes.
    operations = _operations(
        _tpcs_new_branch(reparented=False, child=False, stray=False),
        _tpcs_new_branch(reparented=True, child=True, stray=True),
    )
    assert _causes(_creates(operations, "child")) == ["EntityAltered", "ConcreteSubtypeAdded"]
    assert _causes(_created(operations, "child")) == ["EntityAltered", "ConcreteSubtypeAdded"]


def test_a_created_Table_the_reparent_did_not_reach_names_its_addition_alone() -> None:
    # `Stray` arrived under `Warded`, which it stood beneath however `Branch`
    # moved, so the same evolution's reparent carried nothing into `stray`.
    operations = _operations(
        _tpcs_new_branch(reparented=False, child=False, stray=False),
        _tpcs_new_branch(reparented=True, child=True, stray=True),
    )
    assert _causes(_creates(operations, "stray")) == ["ConcreteSubtypeAdded"]
    assert _causes(_created(operations, "stray")) == ["ConcreteSubtypeAdded"]


def test_a_created_Table_names_no_reparent_that_stayed_under_the_same_declarer() -> None:
    # `Branch` moves between two abstract positions that both hang under
    # `Warded`, so `child` stands under `Warded` — the only declarer it holds a
    # Column from — however the move went. A created Table held nothing earlier,
    # so the surviving Table's "did it already materialize this position" clause
    # is vacuous here and would name the move; the baseline is the position
    # `Branch` left, which still hangs under `Warded` in the later model.
    operations = _operations(
        _tpcs_within_owner(moved=False, child=False),
        _tpcs_within_owner(moved=True, child=True),
    )
    assert _causes(_creates(operations, "child")) == ["ConcreteSubtypeAdded"]
    assert _causes(_created(operations, "child")) == ["ConcreteSubtypeAdded"]


def test_a_created_Table_names_only_the_reparent_that_carried_the_declarer() -> None:
    # `Branch` moving under `Warded` is why `child` repeats `Warded`'s members;
    # `Twig` moving between two positions inside `Branch` carried nothing, and
    # gained `Warded` in its ancestry only because `Branch` moved. Reading that
    # gain off the two endpoints' ancestries names both alterations for one
    # move, so each alteration answers for the edge IT changed: `Twig` left a
    # position that stands under `Warded` in the later model, and `Branch` did
    # not.
    operations = _operations(
        _tpcs_two_reparents(branch_warded=False, twig_far=False, child=False),
        _tpcs_two_reparents(branch_warded=True, twig_far=True, child=True),
    )
    expected = ["EntityAltered(Branch)", "ConcreteSubtypeAdded(Child)"]
    assert _entity_causes(_creates(operations, "child")) == expected
    assert _entity_causes(_created(operations, "child")) == expected


def test_a_created_Table_names_the_reparent_whose_vacated_position_left_the_declarer() -> None:
    # `Branch` stood under `Warded` before it moved and stands under `Warded`
    # after, yet its move is why `child` repeats `Warded`'s members: `Old`, the
    # position `Branch` left, moved out to the root in the same evolution, so
    # staying there would have put `Child` outside `Warded` altogether. Where the
    # Entity stood before therefore decides nothing — the counterfactual is the
    # position it left, read from the LATER model — and `Old`'s own move, which
    # left `Warded` itself, carried nothing anywhere.
    operations = _operations(
        _tpcs_vacated_owner(sealed=False, old_warded=True, branch_new=False, child=False),
        _tpcs_vacated_owner(sealed=True, old_warded=False, branch_new=True, child=True),
    )
    expected = ["EntityAltered(Branch)", "ConcreteSubtypeAdded(Child)"]
    assert _entity_causes(_creates(operations, "child")) == expected
    assert _entity_causes(_created(operations, "child")) == expected


def test_a_surviving_Table_names_only_the_reparent_that_carried_the_declarer() -> None:
    # The same two moves over a `child` both endpoints hold: the Table gains
    # `seal` and `seal_ix` because `Branch` came under `Warded`, and `Twig`'s
    # move within `Branch` is no more a cause here than it is of a Table created
    # in the same evolution. The Table's own history cannot rule it out — `child`
    # held no `Warded` position earlier either.
    operations = _operations(
        _tpcs_two_reparents(branch_warded=False, twig_far=False, child=True),
        _tpcs_two_reparents(branch_warded=True, twig_far=True, child=True),
    )
    assert _entity_causes(_added(operations, "child")) == ["EntityAltered(Branch)"]
    assert _entity_causes(_created(operations, "child")) == ["EntityAltered(Branch)"]


def test_a_surviving_Table_names_both_halves_of_an_edge_rotation() -> None:
    # `Arm` moves under `Owner` and `Pivot` moves under `Arm` in one evolution,
    # so the later path `Owner -> Arm -> Pivot -> Child` is why `child` gains
    # `seal`, and each move alone leaves `Child` outside `Owner`. Reading the
    # vacated position's later ancestry as a set answers neither: `Arm` left
    # `Pivot`, and `Pivot` stands under `Owner` later only through the very edge
    # `Arm`'s counterfactual removes. The world where `Arm` stayed is not a
    # model at all, and an alteration the later model cannot be well-founded
    # without is a cause of everything its move carried.
    operations = _operations(
        _tpcs_rotation(rotated=False, child=True), _tpcs_rotation(rotated=True, child=True)
    )
    expected = ["EntityAltered(Arm)", "EntityAltered(Pivot)"]
    assert _entity_causes(_added(operations, "child")) == expected
    assert _entity_causes(_created(operations, "child")) == expected


def test_a_created_Table_names_both_halves_of_an_edge_rotation() -> None:
    # The same rotation with `Child` arriving in the same evolution: `child` is
    # created holding `seal`, and the addition that brought it names both moves
    # beside it for the same reason the surviving Table does.
    operations = _operations(
        _tpcs_rotation(rotated=False, child=False), _tpcs_rotation(rotated=True, child=True)
    )
    expected = ["EntityAltered(Arm)", "ConcreteSubtypeAdded(Child)", "EntityAltered(Pivot)"]
    assert _entity_causes(_creates(operations, "child")) == expected
    assert _entity_causes(_created(operations, "child")) == expected
