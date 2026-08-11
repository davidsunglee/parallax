"""Deep-fetch pure planner unit tests (m-deep-fetch).

Exercises `parallax.core.deep_fetch.plan` independently of the Docker-gated
compile/run sweeps: shared-prefix dedup, broad-vs-narrowed distinct hops,
equivalent-narrowing convergence, the `1 + L` accounting, child-operation
composition (`in` membership + propagated as-of + declared relationship
`orderBy`), narrowed view-key derivation, each level's correlation members
beside their correlation columns, and back-reference (ancestor-revisit) cycle
detection. The planner never compiles or executes anything — every assertion
here is over the returned `FetchPlan` / `FetchLevel` shape alone.
"""

from __future__ import annotations

import pytest
from _corpus_model_support import formed
from _corpus_model_support import model as accepted_model
from _corpus_model_support import target as entity_of

from parallax.core import deep_fetch
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    RelationshipIdentity,
)
from parallax.core.op_algebra import (
    All,
    And,
    AsOf,
    Comparison,
    DeepFetch,
    Membership,
    Narrow,
    NavigationPath,
    Operation,
    OrderBy,
    PathSegment,
)
from parallax.descriptor._serde import deserialize

ORDERS = accepted_model("orders")
ANIMAL = accepted_model("animal")
POLICY = accepted_model("policy")
RATE = accepted_model("rate")


def _seg(rel: str, narrow: tuple[str, ...] = ()) -> PathSegment:
    return PathSegment(rel=rel, narrow=narrow)


def _path(*segments: PathSegment, narrow: tuple[str, ...] | None = None) -> NavigationPath:
    return NavigationPath(segments=segments, narrow=narrow)


def _guard(*to: str) -> tuple[str, ...]:
    return to


def _plan(
    model: Metamodel,
    target: str,
    paths: tuple[NavigationPath, ...],
    operand: Operation | None = None,
) -> deep_fetch.FetchPlan:
    op = DeepFetch(operand=operand if operand is not None else All(), paths=paths)
    return deep_fetch.plan(entity_of(model, target), op, model)


# --------------------------------------------------------------------------- #
# Shared-prefix dedup + independent paths (m-deep-fetch dedup identity).       #
# --------------------------------------------------------------------------- #
def test_shared_prefix_dedups_to_one_level() -> None:
    plan = _plan(
        ORDERS,
        "Order",
        (_path(_seg("Order.items")), _path(_seg("Order.items"), _seg("OrderItem.statuses"))),
    )
    assert len(plan.levels) == 2
    items, statuses = plan.levels
    assert items.attach_key == "items"
    assert isinstance(items.parent, deep_fetch.RootRef)
    assert statuses.attach_key == "statuses"
    assert isinstance(statuses.parent, deep_fetch.LevelRef)
    assert statuses.parent.index == 0


def test_two_independent_paths_off_root_are_two_levels_both_rooted() -> None:
    plan = _plan(
        ORDERS, "Order", (_path(_seg("Order.items")), _path(_seg("Order.itemsByShipDate")))
    )
    assert len(plan.levels) == 2
    assert all(isinstance(level.parent, deep_fetch.RootRef) for level in plan.levels)
    assert {level.attach_key for level in plan.levels} == {"items", "itemsByShipDate"}


def test_multi_hop_path_chains_levels_in_declared_order() -> None:
    plan = _plan(POLICY, "Policy", (_path(_seg("Policy.coverages"), _seg("Coverage.claims")),))
    assert [level.attach_key for level in plan.levels] == ["coverages", "claims"]
    coverages, claims = plan.levels
    assert isinstance(coverages.parent, deep_fetch.RootRef)
    assert isinstance(claims.parent, deep_fetch.LevelRef)
    assert claims.parent.index == 0


# --------------------------------------------------------------------------- #
# Broad-vs-narrowed distinct hops; equivalent narrowings converge.             #
# --------------------------------------------------------------------------- #
def test_broad_and_narrowed_over_the_same_relationship_are_distinct_levels() -> None:
    plan = _plan(
        ANIMAL,
        "Person",
        (_path(_seg("Person.pets")), _path(_seg("Person.pets", ("Dog",)))),
    )
    assert len(plan.levels) == 2
    keys = {level.attach_key for level in plan.levels}
    assert keys == {"pets", "pets[Dog]"}


def test_equivalent_narrowings_dedup_to_one_hop() -> None:
    # `to: [Pet]` (the abstract subtype) and `to: [Cat, Dog]` (its own concretes)
    # resolve to the SAME effective set {Cat, Dog} -> the same view key -> ONE level.
    plan = _plan(
        ANIMAL,
        "Person",
        (_path(_seg("Person.pets", ("Pet",))), _path(_seg("Person.pets", ("Cat", "Dog")))),
    )
    assert len(plan.levels) == 1
    assert plan.levels[0].attach_key == "pets[Cat,Dog]"


def test_broad_and_a_redundant_narrow_are_distinct_levels_filling_both_views() -> None:
    # `Person.pets` targets Pet, whose effective concrete set is exactly {Cat, Dog},
    # so `to: [Pet]` is REDUNDANT — it resolves to the very set the broad hop
    # already reaches, and both levels read the same rows. They are still TWO
    # levels: the view key is derived from whether a narrow was AUTHORED, so keying
    # identity on the resolved set alone would merge them and leave one view
    # unpopulated (m-deep-fetch, case m-inheritance-068).
    paths = (_path(_seg("Person.pets")), _path(_seg("Person.pets", ("Pet",))))
    plan = _plan(ANIMAL, "Person", paths)
    assert [level.attach_key for level in plan.levels] == ["pets", "pets[Cat,Dog]"]
    assert {level.child_target for level in plan.levels} == {"parallax.compatibility.Pet"}
    # Authoring order decides only which view comes first, never how many hops.
    reversed_plan = _plan(ANIMAL, "Person", tuple(reversed(paths)))
    assert [level.attach_key for level in reversed_plan.levels] == ["pets[Cat,Dog]", "pets"]


def test_two_different_narrow_sets_are_distinct_levels() -> None:
    plan = _plan(
        ANIMAL,
        "Person",
        (_path(_seg("Person.pets", ("Dog",))), _path(_seg("Person.pets", ("Cat",)))),
    )
    assert len(plan.levels) == 2
    assert {level.attach_key for level in plan.levels} == {"pets[Dog]", "pets[Cat]"}


def test_narrowed_view_key_is_alphabetical_no_spaces() -> None:
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets", ("Dog", "Cat"))),))
    assert plan.levels[0].attach_key == "pets[Cat,Dog]"


def test_a_narrow_naming_an_undeclared_subtype_is_rejected() -> None:
    # A narrow denotes ONE position, so a member the model does not declare (or
    # one belonging to another family) resolves to no position at all rather
    # than silently contributing nothing to the union.
    with pytest.raises(deep_fetch.DeepFetchError, match="does not declare"):
        _plan(ANIMAL, "Person", (_path(_seg("Person.pets", ("Ghost",))),))


# --------------------------------------------------------------------------- #
# `1 + L` accounting: L counts distinct (post-dedup) hops.                    #
# --------------------------------------------------------------------------- #
def test_l_counts_distinct_hops_after_dedup() -> None:
    # [items], [items, statuses], [itemsByShipDate] -> 3 distinct hops (items,
    # statuses under items, itemsByShipDate) despite 3 declared paths.
    plan = _plan(
        ORDERS,
        "Order",
        (
            _path(_seg("Order.items")),
            _path(_seg("Order.items"), _seg("OrderItem.statuses")),
            _path(_seg("Order.itemsByShipDate")),
        ),
    )
    assert len(plan.levels) == 3


def test_narrow_and_broad_both_count_toward_l() -> None:
    plan = _plan(
        ANIMAL, "Person", (_path(_seg("Person.animals")), _path(_seg("Person.pets", ("Dog",))))
    )
    assert len(plan.levels) == 2


# --------------------------------------------------------------------------- #
# Child-operation shape: IN membership + propagated as-of + declared orderBy. #
# --------------------------------------------------------------------------- #
def test_child_operation_is_a_plain_in_membership() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.statuses")),))
    target, op = plan.levels[0].child_operation([1, 2, 3])
    assert target == "parallax.compatibility.OrderStatus"
    assert isinstance(op, Membership)
    assert op.op == "in"
    assert op.attr == "parallax.compatibility.OrderStatus.orderId"
    assert op.values == (1, 2, 3)


def test_child_operation_wraps_declared_relationship_order_by() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items")),))
    target, op = plan.levels[0].child_operation([1])
    assert target == "parallax.compatibility.OrderItem"
    assert isinstance(op, OrderBy)
    assert op.keys[0].attr == "parallax.compatibility.OrderItem.id"
    assert op.keys[0].direction == "desc"
    assert isinstance(op.operand, Membership)


def test_child_operation_multi_key_order_by_preserves_declared_sequence() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.tags")),))
    _target, op = plan.levels[0].child_operation([1])
    assert isinstance(op, OrderBy)
    assert [(key.attr, key.direction) for key in op.keys] == [
        ("parallax.compatibility.OrderTag.priority", "desc"),
        ("parallax.compatibility.OrderTag.label", "asc"),
    ]


def test_child_operation_carries_the_declared_null_placement_of_each_key() -> None:
    # The declaration's placement rides the bare->dotted rewrite: `notesDescNullsFirst`
    # authors `first` while `items` leaves placement unauthored, which the accepted
    # model has already normalized to `last`.
    placed = _plan(ORDERS, "Order", (_path(_seg("Order.notesDescNullsFirst")),))
    _target, op = placed.levels[0].child_operation([1])
    assert isinstance(op, OrderBy)
    assert [(key.attr, key.direction, key.nulls) for key in op.keys] == [
        ("parallax.compatibility.OrderNote.resolvedOn", "desc", "first")
    ]
    defaulted = _plan(ORDERS, "Order", (_path(_seg("Order.items")),))
    _target, default_op = defaulted.levels[0].child_operation([1])
    assert isinstance(default_op, OrderBy)
    assert default_op.keys[0].nulls == "last"


def test_child_operation_has_no_order_by_when_relationship_declares_none() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.statuses")),))
    _target, op = plan.levels[0].child_operation([1])
    assert isinstance(op, Membership)  # no OrderBy wrapper at all


def test_child_operation_appends_propagated_as_of_after_the_in_membership() -> None:
    # every axis defaults to latest (the root operand pins none explicitly)
    op = DeepFetch(operand=All(), paths=(_path(_seg("Policy.coverages")),))
    plan = deep_fetch.plan(entity_of(POLICY, "Policy"), op, POLICY)
    _target, child_op = plan.levels[0].child_operation([1, 2])
    assert isinstance(child_op, And)
    membership, *as_of_terms = child_op.operands
    assert isinstance(membership, Membership)
    assert membership.values == (1, 2)
    assert len(as_of_terms) == 2  # Valid Time then Transaction Time (AXIS_ORDER)


def test_child_operation_raises_on_a_back_reference_level() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items"), _seg("OrderItem.order")),))
    back_reference = plan.levels[1]
    assert back_reference.is_back_reference
    with pytest.raises(deep_fetch.DeepFetchError):
        back_reference.child_operation([1])


# --------------------------------------------------------------------------- #
# Single-concrete narrow bypasses the Narrow node entirely (compile_read's own #
# concrete-target dispatch already yields the correct tag filter, no          #
# projection) — a 2+-concrete resolution DOES wrap Narrow.                    #
# --------------------------------------------------------------------------- #
def test_single_concrete_narrow_targets_the_concrete_directly_no_narrow_node() -> None:
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets", ("Dog",))),))
    level = plan.levels[0]
    assert level.child_target == "parallax.compatibility.Dog"
    assert level.narrow_to is None
    _target, op = level.child_operation([1])
    assert isinstance(op, Membership)
    assert op.attr == "parallax.compatibility.Dog.ownerId"


def test_multi_concrete_narrow_wraps_a_narrow_node() -> None:
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets", ("Cat", "Dog"))),))
    level = plan.levels[0]
    assert level.child_target == "parallax.compatibility.Pet"
    assert level.narrow_to == ("Cat", "Dog")
    _target, op = level.child_operation([1])
    assert isinstance(op, Narrow)
    assert op.to == ("Cat", "Dog")


def test_broad_polymorphic_hop_targets_the_relationship_position_no_narrow() -> None:
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.animals")),))
    level = plan.levels[0]
    assert level.child_target == "parallax.compatibility.Animal"
    assert level.narrow_to is None


def test_non_polymorphic_child_target_is_the_related_entity_itself() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items")),))
    assert plan.levels[0].child_target == "parallax.compatibility.OrderItem"


# --------------------------------------------------------------------------- #
# Path-ROOT guards (m-deep-fetch "Path-root guards"): identity keys on the     #
# RESOLVED SOURCE SET, the deliberate opposite of the segment rule above.      #
# --------------------------------------------------------------------------- #
def test_equivalent_root_guards_dedup_to_one_hop() -> None:
    # `to: [Pet]` and `to: [Cat, Dog]` resolve to the same source set, and a guard
    # creates no view to tell them apart, so they are ONE hop — unlike the two
    # equivalent SEGMENT spellings, which also dedup, and unlike a broad segment
    # beside a redundant narrow, which does not.
    plan = _plan(
        ANIMAL,
        "Animal",
        (
            _path(_seg("Animal.owner"), narrow=_guard("Pet")),
            _path(_seg("Animal.owner"), narrow=_guard("Cat", "Dog")),
        ),
    )
    assert len(plan.levels) == 1
    assert plan.levels[0].attach_key == "owner"
    assert plan.levels[0].source_position == (
        EntityIdentity("parallax.compatibility", "Cat"),
        EntityIdentity("parallax.compatibility", "Dog"),
    )


def test_a_root_guard_admitting_every_queried_object_is_the_broad_path() -> None:
    # The degenerate guard: it resolves to the whole queried position, so nothing
    # observable separates it from the unguarded path and it must not emit a
    # second, identical statement filling one view twice.
    plan = _plan(
        ANIMAL,
        "Animal",
        (_path(_seg("Animal.owner")), _path(_seg("Animal.owner"), narrow=_guard("Animal"))),
    )
    assert len(plan.levels) == 1
    assert plan.levels[0].source_position is None


def test_disjoint_overlapping_and_contained_root_guards_stay_distinct_hops() -> None:
    # Every relation other than equality yields distinct hops, each costing its own
    # statement, and every one of them fills the SAME ordinary view key.
    for guards in (
        (_guard("Dog"), _guard("Cat")),  # disjoint
        (_guard("Dog", "WildBoar"), _guard("Cat", "Dog")),  # overlapping (neither nests)
        (_guard("Dog"), _guard("Cat", "Dog")),  # containment (a guard inside a guard)
        (None, _guard("Dog")),  # containment (a guard inside broad)
    ):
        plan = _plan(
            ANIMAL,
            "Animal",
            tuple(_path(_seg("Animal.owner"), narrow=guard) for guard in guards),
        )
        assert len(plan.levels) == 2
        assert {level.attach_key for level in plan.levels} == {"owner"}


def test_a_root_guard_naming_an_undeclared_subtype_is_rejected() -> None:
    # A guard denotes ONE position, exactly as a segment narrow does, so a member
    # the model does not declare resolves to no position rather than silently
    # contributing nothing to the union.
    with pytest.raises(deep_fetch.DeepFetchError, match="does not declare"):
        _plan(ANIMAL, "Animal", (_path(_seg("Animal.owner"), narrow=_guard("Ghost")),))


def test_a_root_guard_qualifies_only_the_first_level_of_its_path() -> None:
    # A guard restricts which ROOT objects a path starts from; a deeper level
    # descends from the already-guarded parents, so it carries no guard of its own
    # and the two narrow positions keep their own keys.
    plan = _plan(
        ANIMAL,
        "Animal",
        (
            _path(
                _seg("Animal.owner"),
                _seg("Person.pets", ("Dog",)),
                narrow=_guard("Pet"),
            ),
        ),
    )
    owner, pets = plan.levels
    assert (owner.attach_key, pets.attach_key) == ("owner", "pets[Dog]")
    assert owner.source_position is not None
    assert pets.source_position is None


# --------------------------------------------------------------------------- #
# Correlation members beside correlation columns (m-deep-fetch "A level names  #
# its correlation members, not only their columns").                          #
# --------------------------------------------------------------------------- #
def test_a_queried_level_carries_both_correlation_members_beside_their_columns() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items")),))
    items = plan.levels[0]
    assert items.owner.column == "id"
    assert items.owner.identity == AttributeIdentity(
        EntityIdentity("parallax.compatibility", "Order"), "id"
    )
    assert items.related is not None
    assert items.related.column == "order_id"
    assert items.related.identity == AttributeIdentity(
        EntityIdentity("parallax.compatibility", "OrderItem"), "orderId"
    )


def test_a_back_reference_level_carries_the_owner_side_member_and_no_child_side_one() -> None:
    # A back-reference gathers the ancestor's key off the parent row exactly as a
    # queried level does — it just resolves that key in memory — so the owner-side
    # member is carried while the child side, which only a child query would need,
    # stays absent entirely.
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items"), _seg("OrderItem.order")),))
    order = plan.levels[1]
    assert order.is_back_reference
    assert order.owner.column == "order_id"
    assert order.owner.identity == AttributeIdentity(
        EntityIdentity("parallax.compatibility", "OrderItem"), "orderId"
    )
    assert order.related is None


def test_a_correlation_member_is_addressed_at_the_position_the_join_names_it_at() -> None:
    # `Person.pets` joins to `{ entity: Pet, attribute: ownerId }`, and `ownerId` is
    # declared on the family ROOT `Animal`. The Identity keeps the position the join
    # wrote while the column comes from the declaration that position inherits, so
    # an inherited member is reached without the join naming its declarer.
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets")),))
    pets = plan.levels[0]
    assert pets.related is not None
    assert pets.related.column == "owner_id"
    assert pets.related.identity == AttributeIdentity(
        EntityIdentity("parallax.compatibility", "Pet"), "ownerId"
    )


# A table-per-concrete-subtype family whose two DISJOINT concrete branches reuse one
# member name over different Columns, which m-inheritance expressly permits
# ("Members do not shadow across ancestry ... Disjoint sibling branches may reuse a
# name"). No corpus model carries that shape at a join endpoint, so this is a
# synthetic descriptor: `Aviary` sorts before `Kennel`, so a family-wide search for
# `keeperId` finds the sibling's Column first.
_SHELTER_MODEL = {
    "entities": [
        {
            "name": "Keeper",
            "table": "keeper",
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "column": "id",
                    "primaryKey": True,
                    "pkGeneration": "application-assigned",
                }
            ],
            "relationships": [
                {
                    "name": "kennels",
                    "cardinality": "one-to-many",
                    "join": {
                        "source": "id",
                        "target": {"entity": "Kennel", "attribute": "keeperId"},
                    },
                }
            ],
        },
        {
            "name": "Shelter",
            "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "column": "id",
                    "primaryKey": True,
                    "pkGeneration": "application-assigned",
                }
            ],
        },
        {
            "name": "Aviary",
            "table": "aviary",
            "inheritance": {"role": "concrete-subtype", "parent": "Shelter"},
            "attributes": [
                {
                    "name": "keeperId",
                    "type": "int64",
                    "column": "aviary_keeper_id",
                    "nullable": True,
                }
            ],
        },
        {
            "name": "Kennel",
            "table": "kennel",
            "inheritance": {"role": "concrete-subtype", "parent": "Shelter"},
            "attributes": [
                {
                    "name": "keeperId",
                    "type": "int64",
                    "column": "kennel_keeper_id",
                    "nullable": True,
                }
            ],
            "relationships": [{"name": "keeper", "reverseOf": "Keeper.kennels"}],
        },
    ]
}
_SHELTER = formed(deserialize(_SHELTER_MODEL))


def test_a_child_side_correlation_column_is_resolved_at_the_addressed_position() -> None:
    plan = _plan(_SHELTER, "Keeper", (_path(_seg("Keeper.kennels")),))
    kennels = plan.levels[0]
    assert kennels.related is not None
    assert kennels.related.identity == AttributeIdentity(EntityIdentity(None, "Kennel"), "keeperId")
    assert kennels.related.column == "kennel_keeper_id"


def test_an_owner_side_correlation_column_is_resolved_at_the_addressed_position() -> None:
    plan = _plan(_SHELTER, "Keeper", (_path(_seg("Keeper.kennels"), _seg("Kennel.keeper")),))
    keeper = plan.levels[1]
    assert keeper.is_back_reference
    assert keeper.owner.identity == AttributeIdentity(EntityIdentity(None, "Kennel"), "keeperId")
    assert keeper.owner.column == "kennel_keeper_id"


def test_a_level_names_the_direction_it_attaches_under_beside_its_attach_key() -> None:
    # A narrowed hop's attach key is a DERIVED spelling of the resolved concrete
    # set, so matching it back against the owner's relationship names is exactly
    # the inversion the identity removes: the identity names the declaring
    # position and the declared direction, whatever the key spells.
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets", ("Dog",))),))
    pets = plan.levels[0]
    assert pets.attach_key == "pets[Dog]"
    assert pets.relationship == RelationshipIdentity(
        EntityIdentity("parallax.compatibility", "Person"), "pets"
    )


def test_a_back_reference_level_names_its_direction_too() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items"), _seg("OrderItem.order")),))
    order = plan.levels[1]
    assert order.is_back_reference
    assert order.relationship == RelationshipIdentity(
        EntityIdentity("parallax.compatibility", "OrderItem"), "order"
    )


# --------------------------------------------------------------------------- #
# Back-reference (ancestor-revisit) cycle detection.                          #
# --------------------------------------------------------------------------- #
def test_back_reference_hop_is_detected() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items"), _seg("OrderItem.order")),))
    items, order = plan.levels
    assert not items.is_back_reference
    assert order.is_back_reference
    assert order.back_reference_family == EntityIdentity("parallax.compatibility", "Order")
    assert order.owner.column == "order_id"


def test_the_inverse_edge_is_recognized_below_the_first_level_too() -> None:
    # `OrderStatus.orderItem` reverses the very hop the path arrived on
    # (`OrderItem.statuses`), so it lands on that level's own parent row.
    plan = _plan(
        ORDERS,
        "Order",
        (_path(_seg("Order.items"), _seg("OrderItem.statuses"), _seg("OrderStatus.orderItem")),),
    )
    items, statuses, order_item = plan.levels
    assert not items.is_back_reference
    assert not statuses.is_back_reference
    assert order_item.is_back_reference
    assert order_item.back_reference_family == EntityIdentity("parallax.compatibility", "OrderItem")


def test_a_to_one_revisit_over_another_association_is_an_ordinary_queried_level() -> None:
    # `OrderStatus.order` is to-one and reaches the Order family the path is rooted
    # at, but it reverses `Order.statuses` — NOT `OrderItem.statuses`, the hop the
    # path arrived on. It therefore correlates on `order_status.order_id` while the
    # path descended through `order_status.order_item_id`, so nothing ties the row
    # it selects to the root order: resolving it from the graph-local identity map
    # would attach an unmaterialized (or simply different) Order. It is queried.
    plan = _plan(
        ORDERS,
        "Order",
        (_path(_seg("Order.items"), _seg("OrderItem.statuses"), _seg("OrderStatus.order")),),
    )
    assert not any(level.is_back_reference for level in plan.levels)
    order = plan.levels[2]
    assert order.child_target == "parallax.compatibility.Order"
    assert order.related is not None
    assert order.related.reference == "parallax.compatibility.Order.id"


def test_ordinary_deeper_level_is_not_flagged_a_back_reference() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items"), _seg("OrderItem.statuses")),))
    assert not any(level.is_back_reference for level in plan.levels)


def test_a_to_many_hop_revisiting_a_family_is_an_ordinary_queried_level() -> None:
    # `Animal.owner` then `Person.pets` returns to the Animal family, but the pets
    # are selected by their OWN foreign key to that owner — they are whatever the
    # owner owns, not the animal the path arrived from — so the level is queried
    # rather than resolved from the graph-local identity map.
    plan = _plan(ANIMAL, "Animal", (_path(_seg("Animal.owner"), _seg("Person.pets")),))
    owner, pets = plan.levels
    assert not owner.is_back_reference
    assert not pets.is_back_reference
    assert pets.child_target == "parallax.compatibility.Pet"


def test_a_to_one_revisit_of_a_one_way_arrival_is_an_ordinary_queried_level() -> None:
    # `Person.pets` is one-way — no declaration reverses it — so `Animal.owner`,
    # which reverses `Person.animals`, is a different association reaching the same
    # family. Nothing in the model pins its row to the person the path arrived from,
    # so the level is queried rather than shortcut.
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets"), _seg("Animal.owner")),))
    pets, owner = plan.levels
    assert not pets.is_back_reference
    assert not owner.is_back_reference


def test_a_path_cannot_continue_past_a_back_reference_level() -> None:
    with pytest.raises(deep_fetch.DeepFetchError):
        _plan(
            ORDERS,
            "Order",
            (_path(_seg("Order.items"), _seg("OrderItem.order"), _seg("Order.items")),),
        )


# --------------------------------------------------------------------------- #
# The planner is pure: no paths means no levels; the root operation is        #
# canonicalized (as-of injected, navigation composed) but nothing executes.   #
# --------------------------------------------------------------------------- #
def test_zero_paths_plans_zero_levels() -> None:
    plan = _plan(ORDERS, "Order", ())
    assert plan.levels == ()


def test_root_operation_is_canonicalized_even_with_zero_paths() -> None:
    literal = Comparison(op="eq", attr="Order.id", value=1)
    op = DeepFetch(operand=literal, paths=())
    plan = deep_fetch.plan(entity_of(ORDERS, "Order"), op, ORDERS)
    assert plan.root_operation == literal


def test_plan_accepts_a_non_deep_fetch_operation_with_zero_levels() -> None:
    # A bare read (no DeepFetch wrapper at all) plans as a zero-level fetch —
    # the degenerate "materialize with no relationships" shape a plain snapshot
    # find or a scenario's own `find` step needs.
    literal = Comparison(op="eq", attr="Order.id", value=1)
    plan = deep_fetch.plan(entity_of(ORDERS, "Order"), literal, ORDERS)
    assert plan.levels == ()
    assert plan.root_operation == literal


# --------------------------------------------------------------------------- #
# Root as-of injection over a CONCRETE inheritance target whose family's axes #
# are declared on the ROOT alone. `plan()` must inject the default-latest or  #
# pinned as-of predicate even though `DepositRate` carries no local axes. The #
# injected term names its DECLARING Entity by exact identity, so it stays     #
# addressed at one Entity in a model two namespaces could share a name in.    #
# --------------------------------------------------------------------------- #
def test_concrete_target_root_operation_defaults_every_axis_to_latest() -> None:
    plan = deep_fetch.plan(entity_of(RATE, "DepositRate"), All(), RATE)
    # Valid-Time-first (m-temporal-read), both defaulted to the current
    # milestone since neither axis is pinned: `thru_z = infinity`, `out_z = infinity`.
    assert plan.root_operation == And(
        operands=(
            Comparison(op="eq", attr="parallax.compatibility.Rate.validEnd", value="infinity"),
            Comparison(op="eq", attr="parallax.compatibility.Rate.txEnd", value="infinity"),
        )
    )


def test_concrete_target_root_operation_injects_a_pinned_axis() -> None:
    op = AsOf(operand=All(), dimension="transaction-time", coordinate="2024-01-15T00:00:00+00:00")
    plan = deep_fetch.plan(entity_of(RATE, "DepositRate"), op, RATE)
    assert plan.root_operation == And(
        operands=(
            # Valid Time defaults to latest (never pinned by this operation)
            Comparison(op="eq", attr="parallax.compatibility.Rate.validEnd", value="infinity"),
            # Transaction Time is pinned to the past instant (containment)
            Comparison(
                op="lessThanEquals",
                attr="parallax.compatibility.Rate.txStart",
                value="2024-01-15T00:00:00+00:00",
            ),
            Comparison(
                op="greaterThan",
                attr="parallax.compatibility.Rate.txEnd",
                value="2024-01-15T00:00:00+00:00",
            ),
        )
    )
