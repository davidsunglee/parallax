"""Deep-fetch pure planner unit tests (m-deep-fetch).

Exercises `parallax.core.deep_fetch.plan` independently of the Docker-gated
compile/run sweeps: shared-prefix dedup, broad-vs-narrowed distinct hops,
equivalent-narrowing convergence, the `1 + L` accounting, child-query
composition (`in` membership + propagated as-of + declared relationship
`orderBy`), narrowed view-key derivation, each level's correlation members
beside their correlation columns, and back-reference (ancestor-revisit) cycle
detection. The planner never compiles or executes anything — every assertion
here is over the returned `ObjectQueryPlan` / `FetchStep` shape alone.
"""

from __future__ import annotations

import dataclasses
from typing import cast

import pytest

from parallax.conformance import models
from parallax.core import deep_fetch, inheritance, relationship
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    RelationshipIdentity,
)
from parallax.core.object_query import (
    AsOf,
    IncludePath,
    IncludeSegment,
    TemporalDimension,
    TemporalSelection,
    canonical_includes,
    object_query,
    validate_object_query,
)
from parallax.core.object_query._validated import ValidatedOrderTerm
from parallax.core.predicate import (
    All,
    And,
    Comparison,
    Membership,
    ModelRejectedError,
    Narrow,
    PredicateNode,
)
from parallax.core.unit_work import PredicateSelection, PredicateWrite, WriteAssignment
from parallax.core.unit_work.instructions import PreparedPredicateWrite, prepare_typed_write
from tests.unit._corpus_model_support import model as accepted_model
from tests.unit._corpus_model_support import target as entity_of

ORDERS = accepted_model("orders")
ANIMAL = accepted_model("animal")
POLICY = accepted_model("policy")
RATE = accepted_model("rate")


def _seg(rel: str, narrow: tuple[str, ...] = ()) -> IncludeSegment:
    return IncludeSegment(rel=rel, narrow_to=narrow)


def _path(*segments: IncludeSegment, narrow: tuple[str, ...] | None = None) -> IncludePath:
    return IncludePath(segments=segments, applies_to=narrow)


def _guard(*to: str) -> tuple[str, ...]:
    return to


_BITEMPORAL_LATEST: dict[TemporalDimension, TemporalSelection] = {
    "transaction-time": AsOf("latest"),
    "valid-time": AsOf("latest"),
}


def _order_attr(term: object) -> str:
    member = cast("ValidatedOrderTerm", term).member
    return f"{member.identity.entity.canonical}.{member.identity.name}"


def _plan(
    model: Metamodel,
    target: str,
    paths: tuple[IncludePath, ...],
    temporal: dict[TemporalDimension, TemporalSelection] | None = None,
    predicate: PredicateNode | None = None,
    **clauses: object,
) -> deep_fetch.ObjectQueryPlan:
    entity = entity_of(model, target)
    query = object_query(
        entity.identity,
        predicate if predicate is not None else All(),
        temporal=temporal,
        includes=paths,
        **clauses,  # pyright: ignore[reportArgumentType] - the caller names real clauses
    )
    return deep_fetch.plan(
        validate_object_query(entity, query, model),
        model,
        projection=deep_fetch.ReadProjectionRequest("all", True),
    )


def _query_step(plan: deep_fetch.ObjectQueryPlan, index: int = 0) -> deep_fetch.QueryFetchStep:
    step = plan.fetch_steps[index]
    assert isinstance(step, deep_fetch.QueryFetchStep)
    return step


def _back_reference_step(
    plan: deep_fetch.ObjectQueryPlan, index: int
) -> deep_fetch.BackReferenceFetchStep:
    step = plan.fetch_steps[index]
    assert isinstance(step, deep_fetch.BackReferenceFetchStep)
    return step


def _position(
    plan: deep_fetch.ObjectQueryPlan, step: deep_fetch.FetchStep
) -> deep_fetch.IncludePosition:
    return plan.includes.position(step.position)


def _attach_key(plan: deep_fetch.ObjectQueryPlan, step: deep_fetch.FetchStep) -> str:
    view = _position(plan, step).view
    assert view is not None
    return view.narrowed_view or view.relationship.name


def test_include_tree_requires_a_root_and_refuses_an_unadmitted_render() -> None:
    identity = EntityIdentity("parallax.compatibility", "Order")
    with pytest.raises(ValueError, match="starts with its root"):
        deep_fetch.IncludeTree(identity, ())

    includes = _plan(ORDERS, "Order", ()).includes
    assert includes.render_token((includes.root,), EntityIdentity("elsewhere", "Order")) is None


def test_relationship_ordering_rejects_a_resolved_member_that_disappeared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direction = relationship.view(ORDERS).relationship(
        RelationshipIdentity(entity_of(ORDERS, "Order").identity, "itemsByShipDate")
    )
    assert direction is not None
    child = entity_of(ORDERS, "OrderItem")

    class MissingMemberView:
        @staticmethod
        def applicable_attribute(_name: str) -> None:
            return None

    monkeypatch.setattr(
        deep_fetch,
        "_entity_view",
        lambda *_args: MissingMemberView(),  # pyright: ignore[reportUnknownArgumentType,reportUnknownLambdaType]
    )

    with pytest.raises(deep_fetch.DeepFetchError, match=r"order member.*is absent"):
        deep_fetch._resolved_order_terms(  # pyright: ignore[reportPrivateUsage]
            direction, child, inheritance.view(ORDERS)
        )


def test_deep_fetch_rejects_a_validated_path_whose_relationship_disappeared() -> None:
    entity = entity_of(ORDERS, "Order")
    authored = object_query(
        entity.identity,
        All(),
        includes=(_path(_seg("Order.items")),),
    )
    validated = validate_object_query(entity, authored, ORDERS)
    path = validated.includes[0]
    segment = dataclasses.replace(
        path.segments[0],
        relationship=RelationshipIdentity(EntityIdentity(None, "Missing"), "items"),
    )
    malformed = dataclasses.replace(
        validated, includes=(dataclasses.replace(path, segments=(segment,)),)
    )

    with pytest.raises(deep_fetch.DeepFetchError, match=r"resolved relationship.*is absent"):
        deep_fetch.plan(
            malformed,
            ORDERS,
            projection=deep_fetch.ReadProjectionRequest("all", True),
        )


def test_mutation_read_unions_an_explicit_projection_with_assigned_value_objects() -> None:
    account = entity_of(ORDERS, "Order")
    prepared = prepare_typed_write(
        PredicateWrite(
            "update",
            PredicateSelection(account.identity.canonical, All()),
            (WriteAssignment(f"{account.identity.canonical}.name", "updated"),),
        ),
        ORDERS,
    )
    assert isinstance(prepared, PreparedPredicateWrite)

    query = deep_fetch.plan_mutation_read(
        prepared,
        model=ORDERS,
        temporal=(),
        projection=deep_fetch.ReadProjectionRequest(frozenset({"unavailable"}), False),
    )

    assert query.projection.value_objects == ()


# --------------------------------------------------------------------------- #
# Shared-prefix dedup + independent paths (m-deep-fetch dedup identity).       #
# --------------------------------------------------------------------------- #
def test_shared_prefix_dedups_to_one_level() -> None:
    plan = _plan(
        ORDERS,
        "Order",
        (_path(_seg("Order.items")), _path(_seg("Order.items"), _seg("OrderItem.statuses"))),
    )
    assert len(plan.fetch_steps) == 2
    items, statuses = plan.fetch_steps
    assert _attach_key(plan, items) == "items"
    assert isinstance(items.parent, deep_fetch.RootRef)
    assert _attach_key(plan, statuses) == "statuses"
    assert isinstance(statuses.parent, deep_fetch.LevelRef)
    assert statuses.parent.index == 0


def test_canonicalized_path_set_is_idempotent_and_plans_the_same_levels() -> None:
    authored = (
        _path(_seg("Order.items")),
        _path(_seg("Order.items"), _seg("OrderItem.statuses")),
        _path(_seg("Order.items")),
    )
    canonical = canonical_includes(authored)
    assert canonical == (_path(_seg("Order.items"), _seg("OrderItem.statuses")),)
    assert canonical_includes(canonical) == canonical
    assert (
        _plan(ORDERS, "Order", authored).fetch_steps
        == _plan(ORDERS, "Order", canonical).fetch_steps
    )


def test_two_independent_paths_off_root_are_two_levels_both_rooted() -> None:
    plan = _plan(
        ORDERS, "Order", (_path(_seg("Order.items")), _path(_seg("Order.itemsByShipDate")))
    )
    assert len(plan.fetch_steps) == 2
    assert all(isinstance(step.parent, deep_fetch.RootRef) for step in plan.fetch_steps)
    assert {_attach_key(plan, step) for step in plan.fetch_steps} == {
        "items",
        "itemsByShipDate",
    }


def test_multi_hop_path_chains_levels_in_declared_order() -> None:
    plan = _plan(
        POLICY,
        "Policy",
        (_path(_seg("Policy.coverages"), _seg("Coverage.claims")),),
        _BITEMPORAL_LATEST,
    )
    assert [_attach_key(plan, step) for step in plan.fetch_steps] == ["coverages", "claims"]
    coverages, claims = plan.fetch_steps
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
    assert len(plan.fetch_steps) == 2
    keys = {_attach_key(plan, step) for step in plan.fetch_steps}
    assert keys == {"pets", "pets[Dog]"}


def test_equivalent_narrowings_dedup_to_one_hop() -> None:
    # `to: [Pet]` (the abstract subtype) and `to: [Cat, Dog]` (its own concretes)
    # resolve to the SAME effective set {Cat, Dog} -> the same view key -> ONE level.
    plan = _plan(
        ANIMAL,
        "Person",
        (_path(_seg("Person.pets", ("Pet",))), _path(_seg("Person.pets", ("Cat", "Dog")))),
    )
    assert len(plan.fetch_steps) == 1
    assert _attach_key(plan, plan.fetch_steps[0]) == "pets[Cat,Dog]"


def test_broad_and_a_redundant_narrow_are_distinct_levels_filling_both_views() -> None:
    # `Person.pets` targets Pet, whose effective concrete set is exactly {Cat, Dog},
    # so `to: [Pet]` is REDUNDANT — it resolves to the very set the broad hop
    # already reaches, and both levels read the same rows. They are still TWO
    # levels: the view key is derived from whether a narrow was AUTHORED, so keying
    # identity on the resolved set alone would merge them and leave one view
    # unpopulated (m-deep-fetch, case m-inheritance-068).
    paths = (_path(_seg("Person.pets")), _path(_seg("Person.pets", ("Pet",))))
    plan = _plan(ANIMAL, "Person", paths)
    assert [_attach_key(plan, step) for step in plan.fetch_steps] == ["pets", "pets[Cat,Dog]"]
    assert {
        step.child_target
        for step in plan.fetch_steps
        if isinstance(step, deep_fetch.QueryFetchStep)
    } == {EntityIdentity("parallax.compatibility", "Pet")}
    # Canonical include order decides which view comes first, never how many hops.
    reversed_plan = _plan(ANIMAL, "Person", tuple(reversed(paths)))
    assert [_attach_key(reversed_plan, step) for step in reversed_plan.fetch_steps] == [
        "pets",
        "pets[Cat,Dog]",
    ]


def test_two_different_narrow_sets_are_distinct_levels() -> None:
    plan = _plan(
        ANIMAL,
        "Person",
        (_path(_seg("Person.pets", ("Dog",))), _path(_seg("Person.pets", ("Cat",)))),
    )
    assert len(plan.fetch_steps) == 2
    assert {_attach_key(plan, step) for step in plan.fetch_steps} == {"pets[Dog]", "pets[Cat]"}


def test_narrowed_view_key_is_alphabetical_no_spaces() -> None:
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets", ("Dog", "Cat"))),))
    assert _attach_key(plan, plan.fetch_steps[0]) == "pets[Cat,Dog]"


def test_a_narrow_naming_an_undeclared_subtype_is_rejected() -> None:
    # A narrow denotes ONE position, so a member the model does not declare (or
    # one belonging to another family) resolves to no position at all rather
    # than silently contributing nothing to the union.
    with pytest.raises(ModelRejectedError) as excinfo:
        _plan(ANIMAL, "Person", (_path(_seg("Person.pets", ("Ghost",))),))
    assert excinfo.value.rule == "narrow-empty-effective-set"


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
    assert len(plan.fetch_steps) == 3


def test_narrow_and_broad_both_count_toward_l() -> None:
    plan = _plan(
        ANIMAL, "Person", (_path(_seg("Person.animals")), _path(_seg("Person.pets", ("Dog",))))
    )
    assert len(plan.fetch_steps) == 2


# --------------------------------------------------------------------------- #
# Child-query shape: IN membership + propagated as-of + declared orderBy.     #
# --------------------------------------------------------------------------- #
def test_child_query_is_a_plain_in_membership() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.statuses")),))
    query = _query_step(plan).query_for([1, 2, 3])
    assert query.target == EntityIdentity("parallax.compatibility", "OrderStatus")
    assert isinstance(query.validated_predicate.authored, Membership)
    assert query.validated_predicate.authored.op == "in"
    assert query.validated_predicate.authored.attr == "parallax.compatibility.OrderStatus.orderId"
    assert query.validated_predicate.authored.values == (1, 2, 3)


def test_child_query_deduplicates_and_freezes_keys_in_encounter_order() -> None:
    level = _query_step(_plan(ORDERS, "Order", (_path(_seg("Order.statuses")),)))
    query = level.query_for([2, 1, 2, 3, 1])
    authored = query.validated_predicate.authored
    assert isinstance(authored, Membership)
    assert authored.values == (2, 1, 3)
    assert isinstance(authored.values, tuple)


def test_child_query_carries_declared_relationship_order_by() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items")),))
    query = _query_step(plan).query_for([1])
    assert query.target == EntityIdentity("parallax.compatibility", "OrderItem")
    assert _order_attr(query.order_by[0]) == "parallax.compatibility.OrderItem.id"
    assert query.order_by[0].direction == "desc"
    assert isinstance(query.validated_predicate.authored, Membership)


def test_child_query_multi_key_order_by_preserves_declared_sequence() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.tags")),))
    query = _query_step(plan).query_for([1])
    assert [(_order_attr(key), key.direction) for key in query.order_by] == [
        ("parallax.compatibility.OrderTag.priority", "desc"),
        ("parallax.compatibility.OrderTag.label", "asc"),
    ]


def test_child_query_carries_the_declared_null_placement_of_each_key() -> None:
    # The declaration's placement rides the bare->dotted rewrite: `notesDescNullsFirst`
    # authors `first` while `items` leaves placement unauthored, which the accepted
    # model has already normalized to `last`.
    placed = _plan(ORDERS, "Order", (_path(_seg("Order.notesDescNullsFirst")),))
    query = _query_step(placed).query_for([1])
    assert [(_order_attr(key), key.direction, key.nulls) for key in query.order_by] == [
        ("parallax.compatibility.OrderNote.resolvedOn", "desc", "first")
    ]
    defaulted = _plan(ORDERS, "Order", (_path(_seg("Order.items")),))
    default_query = _query_step(defaulted).query_for([1])
    assert default_query.order_by[0].nulls == "last"


def test_child_query_has_no_order_by_when_relationship_declares_none() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.statuses")),))
    query = _query_step(plan).query_for([1])
    assert query.order_by == ()
    assert isinstance(query.validated_predicate.authored, Membership)


def test_child_query_appends_propagated_as_of_after_the_in_membership() -> None:
    plan = _plan(POLICY, "Policy", (_path(_seg("Policy.coverages")),), _BITEMPORAL_LATEST)
    child_query = _query_step(plan).query_for([1, 2])
    assert isinstance(child_query.validated_predicate.authored, And)
    membership, *as_of_terms = child_query.validated_predicate.authored.operands
    assert isinstance(membership, Membership)
    assert membership.values == (1, 2)
    assert len(as_of_terms) == 2  # Valid Time then Transaction Time (AXIS_ORDER)


def test_a_back_reference_step_exposes_no_query_construction() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items"), _seg("OrderItem.order")),))
    back_reference = _back_reference_step(plan, 1)
    assert not hasattr(back_reference, "query_for")
    assert not hasattr(back_reference, "query_template")


# --------------------------------------------------------------------------- #
# Single-concrete narrow bypasses query narrowing entirely (compile_read's own #
# concrete-target dispatch already yields the correct tag filter, no          #
# projection) — a 2+-concrete resolution DOES wrap Narrow.                    #
# --------------------------------------------------------------------------- #
def test_single_concrete_narrow_targets_the_concrete_directly_no_narrow_node() -> None:
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets", ("Dog",))),))
    level = _query_step(plan)
    assert level.child_target == EntityIdentity("parallax.compatibility", "Dog")
    assert level.narrow_to is None
    query = level.query_for([1])
    assert isinstance(query.validated_predicate.authored, Membership)
    assert query.validated_predicate.authored.attr == "parallax.compatibility.Dog.ownerId"


def test_multi_concrete_narrow_wraps_a_narrow_node() -> None:
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets", ("Cat", "Dog"))),))
    level = _query_step(plan)
    assert level.child_target == EntityIdentity("parallax.compatibility", "Pet")
    assert level.narrow_to == (
        EntityIdentity("parallax.compatibility", "Cat"),
        EntityIdentity("parallax.compatibility", "Dog"),
    )
    query = level.query_for([1])
    assert query.narrow_to == level.narrow_to
    assert isinstance(query.validated_predicate.authored, Membership)


def test_broad_polymorphic_hop_targets_the_relationship_position_no_narrow() -> None:
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.animals")),))
    level = _query_step(plan)
    assert level.child_target == EntityIdentity("parallax.compatibility", "Animal")
    assert level.narrow_to is None


def test_non_polymorphic_child_target_is_the_related_entity_itself() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items")),))
    assert _query_step(plan).child_target == EntityIdentity("parallax.compatibility", "OrderItem")


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
    assert len(plan.fetch_steps) == 1
    step = plan.fetch_steps[0]
    assert _attach_key(plan, step) == "owner"
    assert _position(plan, step).source == (
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
    assert len(plan.fetch_steps) == 1
    step = plan.fetch_steps[0]
    assert _position(plan, step).source == plan.includes.position(plan.includes.root).target


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
        assert len(plan.fetch_steps) == 2
        assert {_attach_key(plan, step) for step in plan.fetch_steps} == {"owner"}


def test_overlapping_guarded_positions_preserve_all_applicable_continuations() -> None:
    plan = _plan(
        ANIMAL,
        "Animal",
        (
            _path(
                _seg("Animal.owner"),
                _seg("Person.pets", ("Dog",)),
                narrow=_guard("Dog", "WildBoar"),
            ),
            _path(
                _seg("Animal.owner"),
                _seg("Person.pets", ("Cat",)),
                narrow=_guard("Cat", "Dog"),
            ),
        ),
    )
    root = plan.includes.position(plan.includes.root)
    owner_view, owner_positions = next(iter(root.children.items()))
    assert owner_view.relationship.name == "owner"
    assert len(owner_positions) == 2

    dog = EntityIdentity("parallax.compatibility", "Dog")
    cat = EntityIdentity("parallax.compatibility", "Cat")
    person = EntityIdentity("parallax.compatibility", "Person")
    dog_positions = plan.includes.admitted_children(owner_positions, dog)
    cat_positions = plan.includes.admitted_children(owner_positions, cat)

    assert len(dog_positions) == 2
    assert len(cat_positions) == 1
    token = plan.includes.render_token(dog_positions, person)
    assert isinstance(token, tuple)
    assert {
        view.narrowed_view or view.relationship.name for view in plan.includes.child_groups(token)
    } == {"pets[Cat]", "pets[Dog]"}


def test_a_root_guard_naming_an_undeclared_subtype_is_rejected() -> None:
    # A guard denotes ONE position, exactly as a segment narrow does, so a member
    # the model does not declare resolves to no position rather than silently
    # contributing nothing to the union.
    with pytest.raises(ModelRejectedError) as excinfo:
        _plan(ANIMAL, "Animal", (_path(_seg("Animal.owner"), narrow=_guard("Ghost")),))
    assert excinfo.value.rule == "narrow-empty-effective-set"


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
    owner, pets = plan.fetch_steps
    assert (_attach_key(plan, owner), _attach_key(plan, pets)) == ("owner", "pets[Dog]")
    assert _position(plan, owner).source != plan.includes.position(plan.includes.root).target
    owner_position = _position(plan, owner)
    assert owner_position.parent is not None
    assert _position(plan, pets).source == owner_position.target


# --------------------------------------------------------------------------- #
# Correlation members beside correlation columns (m-deep-fetch "A level names  #
# its correlation members, not only their columns").                          #
# --------------------------------------------------------------------------- #
def test_a_queried_level_carries_both_correlation_members_beside_their_columns() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items")),))
    items = _query_step(plan)
    assert items.owner.column == "id"
    assert items.owner.identity == AttributeIdentity(
        EntityIdentity("parallax.compatibility", "Order"), "id"
    )
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
    order = _back_reference_step(plan, 1)
    assert order.owner.column == "order_id"
    assert order.owner.identity == AttributeIdentity(
        EntityIdentity("parallax.compatibility", "OrderItem"), "orderId"
    )
    assert not hasattr(order, "related")


def test_a_correlation_member_is_addressed_at_the_position_the_join_names_it_at() -> None:
    # `Person.pets` joins to `{ entity: Pet, attribute: ownerId }`, and `ownerId` is
    # declared on the family ROOT `Animal`. The Identity keeps the position the join
    # wrote while the column comes from the declaration that position inherits, so
    # an inherited member is reached without the join naming its declarer.
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets")),))
    pets = _query_step(plan)
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
_SHELTER = models.accepted_model(_SHELTER_MODEL)


def test_a_child_side_correlation_column_is_resolved_at_the_addressed_position() -> None:
    plan = _plan(_SHELTER, "Keeper", (_path(_seg("Keeper.kennels")),))
    kennels = _query_step(plan)
    assert kennels.related.identity == AttributeIdentity(EntityIdentity(None, "Kennel"), "keeperId")
    assert kennels.related.column == "kennel_keeper_id"


def test_an_owner_side_correlation_column_is_resolved_at_the_addressed_position() -> None:
    plan = _plan(_SHELTER, "Keeper", (_path(_seg("Keeper.kennels"), _seg("Kennel.keeper")),))
    keeper = _back_reference_step(plan, 1)
    assert keeper.owner.identity == AttributeIdentity(EntityIdentity(None, "Kennel"), "keeperId")
    assert keeper.owner.column == "kennel_keeper_id"


def test_a_level_names_the_direction_it_attaches_under_beside_its_attach_key() -> None:
    # A narrowed hop's attach key is a DERIVED spelling of the resolved concrete
    # set, so matching it back against the owner's relationship names is exactly
    # the inversion the identity removes: the identity names the declaring
    # position and the declared direction, whatever the key spells.
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets", ("Dog",))),))
    pets = plan.fetch_steps[0]
    position = _position(plan, pets)
    assert _attach_key(plan, pets) == "pets[Dog]"
    assert position.view is not None
    assert position.view.relationship == RelationshipIdentity(
        EntityIdentity("parallax.compatibility", "Person"), "pets"
    )


def test_a_back_reference_level_names_its_direction_too() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items"), _seg("OrderItem.order")),))
    order = _back_reference_step(plan, 1)
    position = _position(plan, order)
    assert position.view is not None
    assert position.view.relationship == RelationshipIdentity(
        EntityIdentity("parallax.compatibility", "OrderItem"), "order"
    )


# --------------------------------------------------------------------------- #
# Back-reference (ancestor-revisit) cycle detection.                          #
# --------------------------------------------------------------------------- #
def test_back_reference_hop_is_detected() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items"), _seg("OrderItem.order")),))
    items, order = plan.fetch_steps
    assert isinstance(items, deep_fetch.QueryFetchStep)
    assert isinstance(order, deep_fetch.BackReferenceFetchStep)
    assert order.family == EntityIdentity("parallax.compatibility", "Order")
    assert order.owner.column == "order_id"


def test_the_inverse_edge_is_recognized_below_the_first_level_too() -> None:
    # `OrderStatus.orderItem` reverses the very hop the path arrived on
    # (`OrderItem.statuses`), so it lands on that level's own parent row.
    plan = _plan(
        ORDERS,
        "Order",
        (_path(_seg("Order.items"), _seg("OrderItem.statuses"), _seg("OrderStatus.orderItem")),),
    )
    items, statuses, order_item = plan.fetch_steps
    assert isinstance(items, deep_fetch.QueryFetchStep)
    assert isinstance(statuses, deep_fetch.QueryFetchStep)
    assert isinstance(order_item, deep_fetch.BackReferenceFetchStep)
    assert order_item.family == EntityIdentity("parallax.compatibility", "OrderItem")


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
    assert all(isinstance(step, deep_fetch.QueryFetchStep) for step in plan.fetch_steps)
    order = _query_step(plan, 2)
    assert order.child_target == EntityIdentity("parallax.compatibility", "Order")
    assert order.related.reference == "parallax.compatibility.Order.id"


def test_ordinary_deeper_level_is_not_flagged_a_back_reference() -> None:
    plan = _plan(ORDERS, "Order", (_path(_seg("Order.items"), _seg("OrderItem.statuses")),))
    assert all(isinstance(step, deep_fetch.QueryFetchStep) for step in plan.fetch_steps)


def test_a_to_many_hop_revisiting_a_family_is_an_ordinary_queried_level() -> None:
    # `Animal.owner` then `Person.pets` returns to the Animal family, but the pets
    # are selected by their OWN foreign key to that owner — they are whatever the
    # owner owns, not the animal the path arrived from — so the level is queried
    # rather than resolved from the graph-local identity map.
    plan = _plan(ANIMAL, "Animal", (_path(_seg("Animal.owner"), _seg("Person.pets")),))
    owner, pets = plan.fetch_steps
    assert isinstance(owner, deep_fetch.QueryFetchStep)
    assert isinstance(pets, deep_fetch.QueryFetchStep)
    assert pets.child_target == EntityIdentity("parallax.compatibility", "Pet")


def test_a_to_one_revisit_of_a_one_way_arrival_is_an_ordinary_queried_level() -> None:
    # `Person.pets` is one-way — no declaration reverses it — so `Animal.owner`,
    # which reverses `Person.animals`, is a different association reaching the same
    # family. Nothing in the model pins its row to the person the path arrived from,
    # so the level is queried rather than shortcut.
    plan = _plan(ANIMAL, "Person", (_path(_seg("Person.pets"), _seg("Animal.owner")),))
    pets, owner = plan.fetch_steps
    assert isinstance(pets, deep_fetch.QueryFetchStep)
    assert isinstance(owner, deep_fetch.QueryFetchStep)


def test_a_path_cannot_continue_past_a_back_reference_level() -> None:
    with pytest.raises(deep_fetch.DeepFetchError):
        _plan(
            ORDERS,
            "Order",
            (_path(_seg("Order.items"), _seg("OrderItem.order"), _seg("Order.items")),),
        )


# --------------------------------------------------------------------------- #
# The planner is pure: no paths means no levels; the root query is           #
# canonicalized (as-of injected, navigation composed) but nothing executes.   #
# --------------------------------------------------------------------------- #
def test_zero_paths_plans_zero_levels() -> None:
    plan = _plan(ORDERS, "Order", ())
    assert plan.fetch_steps == ()
    assert len(plan.includes.positions) == 1


def test_a_query_with_no_includes_plans_zero_levels_and_keeps_its_predicate() -> None:
    # The degenerate "materialize with no relationships" shape a plain snapshot
    # find or a scenario's own read step needs.
    literal = Comparison(op="eq", attr="Order.id", value=1)
    plan = _plan(ORDERS, "Order", (), predicate=literal)
    assert plan.fetch_steps == ()
    assert plan.root.validated_predicate.authored == literal


def test_plan_resolves_result_narrowing_and_leaves_a_predicate_narrow_alone() -> None:
    plan = _plan(
        ORDERS,
        "Order",
        (),
        predicate=Narrow(to=("Order",), operand=All()),
        narrow_to=("Order",),
    )
    assert plan.root.narrow_to == (entity_of(ORDERS, "Order").identity,)
    assert plan.root.validated_predicate.authored == Narrow(to=("Order",), operand=All())


def test_plan_rejects_an_unknown_result_narrowing_target() -> None:
    with pytest.raises(ModelRejectedError) as excinfo:
        _plan(ORDERS, "Order", (), narrow_to=("Ghost",))
    assert excinfo.value.rule == "narrow-empty-effective-set"


# --------------------------------------------------------------------------- #
# Root as-of injection over a CONCRETE inheritance target whose family's axes #
# are declared on the ROOT alone. `plan()` must inject the default-latest or  #
# pinned as-of predicate even though `DepositRate` carries no local axes. The #
# injected term names its DECLARING Entity by exact identity, so it stays     #
# addressed at one Entity in a model two namespaces could share a name in.    #
# --------------------------------------------------------------------------- #
def test_concrete_target_root_query_injects_explicit_latest_on_every_axis() -> None:
    plan = _plan(RATE, "DepositRate", (), _BITEMPORAL_LATEST)
    # Valid-Time-first (m-temporal-read), both explicitly select the current
    # milestone: `thru_z = infinity`, `out_z = infinity`.
    assert plan.root.validated_predicate.authored == And(
        operands=(
            Comparison(op="eq", attr="parallax.compatibility.Rate.validEnd", value="infinity"),
            Comparison(op="eq", attr="parallax.compatibility.Rate.txEnd", value="infinity"),
        )
    )


def test_concrete_target_root_query_injects_a_pinned_axis() -> None:
    pinned: dict[TemporalDimension, TemporalSelection] = {
        "transaction-time": AsOf("2024-01-15T00:00:00.000000Z"),
        "valid-time": AsOf("latest"),
    }
    plan = _plan(RATE, "DepositRate", (), pinned)
    assert plan.root.validated_predicate.authored == And(
        operands=(
            # Valid Time explicitly selects latest.
            Comparison(op="eq", attr="parallax.compatibility.Rate.validEnd", value="infinity"),
            # Transaction Time is pinned to the past instant (containment)
            Comparison(
                op="lessThanEquals",
                attr="parallax.compatibility.Rate.txStart",
                value="2024-01-15T00:00:00.000000Z",
            ),
            Comparison(
                op="greaterThan",
                attr="parallax.compatibility.Rate.txEnd",
                value="2024-01-15T00:00:00.000000Z",
            ),
        )
    )
