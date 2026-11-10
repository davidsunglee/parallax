"""What publication attaches, through which door, and what a published node holds.

Entity Graph Construction no longer fills a Pydantic instance a member at a time.
It allocates a shell that holds nothing, assembles the whole row in local state,
and attaches it once — so a node either carries everything its read carried or
carries nothing at all, and the instance dictionary every Pydantic model is
assumed to have is never created for one.

Two claims live here that no other module states. **The door**: neither
constructor is entered, and the slot is written exactly once. **What the model
and the class have to agree about**: a positional row is written against the
model's member layout and read back through the class's own publication plan,
and the two are derived from different material, so the pair is compared once
and refused when it disagrees.

The correspondence refusals are reached through the constructor a composition
root uses, by binding one Domain Model's composed classes to another Domain
Model's cataloged metadata — the two halves a composition root always takes off
one model. Each pair below is two class declarations under one Entity Identity
that disagree in exactly one way.
"""

from __future__ import annotations

import gc
import sys
import weakref
from typing import Any, cast

import pytest

from parallax.core import InternalError
from parallax.core.internal.entity import (
    MANY_TO_ONE,
    UNLOADED,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    ConcreteSubtype,
    Entity,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    rel,
)
from parallax.core.internal.entity import _instance_state as instance_state
from parallax.core.internal.entity import _row_fill as row_fill
from parallax.core.internal.entity._construction_input import ABSENT
from parallax.core.internal.entity._graph_construction import EntityGraphConstruction
from parallax.core.internal.entity._instance_state import COMPACT_STATE_SLOT, plan_of
from parallax.core.internal.entity._layout import CatalogedModel
from parallax.core.internal.entity._model import DomainModel, class_index, model_of
from parallax.core.internal.metamodel import (
    EntityIdentity,
)
from tests._support.errors import raises_code
from tests._support.model_capabilities import graph_construction_for
from tests.unit._indexed_graph_support import Node, published_nodes
from tests.unit.memory_instruments import serve_one_measurement

_NS = "publication"


# --------------------------------------------------------------------------- #
# The shipping shapes.                                                         #
# --------------------------------------------------------------------------- #


class Tag(ValueObject):
    label: Attr[str]
    weight: Attr[int | None]


class Parcel(Entity, table="parcel", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None]
    tag: Attr[Tag | None]
    peer_id: Attr[int | None]
    peer: Rel[Parcel | None] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))


PARCELS = DomainModel(Parcel)
_PARCEL = Parcel.identity
_TAG_ROW: tuple[object, ...] = ("red", 2)


class _Pin(ValueObject):
    code: Attr[str]


class _Leg(ValueObject):
    distance: Attr[int]
    pin: Attr[_Pin | None]


class _Stop(ValueObject):
    name: Attr[str]
    pin: Attr[_Pin | None]


class _Route(ValueObject):
    label: Attr[str]
    leg: Attr[_Leg | None]
    stops: Attr[tuple[_Stop, ...]]


class Shipment(Entity, table="shipment", namespace=_NS):
    """Every containment shape ``_build_record`` recurses through, in one Entity.

    ``route`` is a top-level occurrence holding both a nested One (``leg``, whose
    own ``pin`` is a One at depth three) and a Many (``stops``) whose elements
    each hold a nested occurrence of their own.
    """

    id: Attr[int] = attr(primary_key=True)
    route: Attr[_Route | None]


SHIPMENTS = DomainModel(Shipment)
_SHIPMENT = Shipment.identity
_PIN_ROW: tuple[object, ...] = ("P1",)
_ROUTE_ROW: tuple[object, ...] = (
    "north",
    (12, _PIN_ROW),
    (("depot", _PIN_ROW), ("dock", ABSENT)),
)


def _published(node: Node) -> Any:
    return published_nodes(PARCELS, node)[0]


# --------------------------------------------------------------------------- #
# The door publication takes.                                                  #
# --------------------------------------------------------------------------- #


def _refuse_both_constructors(monkeypatch: pytest.MonkeyPatch, *classes: type) -> None:
    """Replace both Pydantic doors on each class with one that fails.

    Patched on each concrete declared class rather than on ``BaseModel``, because
    Pydantic resolves ``model_construct`` as a classmethod through the MRO and a
    patch on the root would also fire for every framework-internal model a call
    happens to build. Both doors are covered on every class the recursion can
    reach, so entering either is this test failing rather than a shape someone
    has to notice in output.
    """

    def refuse(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("publication entered a Pydantic constructor")

    for cls in classes:
        monkeypatch.setattr(cls, "__init__", refuse)
        monkeypatch.setattr(cls, "model_construct", cast("Any", classmethod(refuse)))


def test_publication_enters_neither_constructor_at_any_containment_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Value Object filling recurses, so a patch that only observes the root and its one
    # top-level occurrence proves less than this test's name claims. Every class
    # the recursion reaches is patched: the Entity shell, a top-level Value
    # Object, a nested One at depth two, an element of a Many, and the nested
    # occurrence inside that element.
    _refuse_both_constructors(monkeypatch, Shipment, _Route, _Leg, _Stop, _Pin)

    (root,) = published_nodes(SHIPMENTS, (_SHIPMENT, (1, _ROUTE_ROW), ()))
    shipment = cast("Shipment", root)
    route = cast("_Route", shipment.route)
    assert route.leg is not None
    assert (route.leg.distance, cast("_Pin", route.leg.pin).code) == (12, "P1")
    assert tuple(stop.name for stop in route.stops) == ("depot", "dock")
    assert cast("_Pin", route.stops[0].pin).code == "P1"
    assert route.stops[1].pin is None


def test_the_constructor_proof_would_fire_if_a_constructor_were_entered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The negative control the proof above rests on. A patch that silently
    # failed to bind — a name Pydantic resolves elsewhere, a classmethod wrapper
    # the metaclass replaces — would leave that test passing on a tree that
    # still called a constructor. So each door is entered here the way a caller
    # enters it, on every class the recursion reaches, and each one has to raise.
    _refuse_both_constructors(monkeypatch, Shipment, _Route, _Leg, _Stop, _Pin)
    for cls in (Shipment, _Route, _Leg, _Stop, _Pin):
        with pytest.raises(AssertionError, match="entered a Pydantic constructor"):
            cast("Any", cls)()
        with pytest.raises(AssertionError, match="entered a Pydantic constructor"):
            cast("Any", cls).model_construct()


def _allocated(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Every instance publication allocates from here on, as it allocates it."""
    allocated: list[object] = []
    allocate = instance_state.allocate

    def recorded(cls: type[Any]) -> Any:
        allocated.append(allocate(cls))
        return allocated[-1]

    monkeypatch.setattr(row_fill, "allocate", recorded)
    return allocated


def test_a_refused_relationship_value_leaves_the_shell_unattached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A row is assembled in local state and attached at the end, so a node whose
    # relationship row is refused after its Value Object was built holds nothing.
    allocated = _allocated(monkeypatch)
    with raises_code(InternalError, "entity-graph-invalid-value"):
        _published((_PARCEL, (1, "north", ABSENT, ABSENT, _TAG_ROW), ("not a node",)))
    shell, tag = allocated
    assert not hasattr(shell, COMPACT_STATE_SLOT)
    assert cast("Any", tag).label == "red"


def test_a_value_object_refused_mid_row_leaves_the_shell_unattached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The occurrence converts after every Attribute position is read, and its
    # refusal still precedes the one attachment.
    allocated = _allocated(monkeypatch)
    with raises_code(InternalError, "entity-graph-invalid-value"):
        _published((_PARCEL, (1, "north", ABSENT, ABSENT, ("red",)), (UNLOADED,)))
    assert [hasattr(shell, COMPACT_STATE_SLOT) for shell in allocated] == [False, False]


# --------------------------------------------------------------------------- #
# What one construction retains, and what it does not.                         #
# --------------------------------------------------------------------------- #


def test_class_metadata_count_is_independent_of_published_instance_count() -> None:
    # The whole point of resolving an ordinal from the class: publishing more
    # nodes derives no more metadata. The per-Entity facts and the member layout
    # are each derived once per model and answered from thereafter, whether one
    # node or a hundred are published against them.
    construction = graph_construction_for(PARCELS)
    facts = construction.facts_for(_PARCEL)
    nodes = published_nodes(
        construction, *[(_PARCEL, (1, "north", ABSENT, ABSENT, ABSENT), (UNLOADED,))] * 100
    )
    assert len(nodes) == 100
    assert construction.facts_for(_PARCEL) is facts
    assert plan_of(Parcel) is plan_of(Parcel)


def test_a_cyclic_published_graph_is_collected_whole() -> None:
    # Two nodes referring to each other through their rows, which is a reference
    # cycle the collector has to break: nothing outside the graph names either
    # node, and no cache, layout, or presence memo holds one after the roots go.
    roots = published_nodes(
        PARCELS,
        (_PARCEL, (1, "l", ABSENT, 2, ABSENT), (1,)),
        (_PARCEL, (2, "r", ABSENT, 1, ABSENT), (0,)),
    )
    alive = [weakref.ref(cast("Any", node)) for node in roots]
    assert cast("Any", roots[0]).peer is roots[1]

    del roots
    gc.collect()
    assert [reference() for reference in alive] == [None, None]


# --------------------------------------------------------------------------- #
# The pairs that disagree, and the one refusal each earns.                     #
# --------------------------------------------------------------------------- #


class _Note(ValueObject):
    body: Attr[str]


class _Doc(ValueObject):
    first: Attr[str]
    second: Attr[str]


class _SwappedDoc(ValueObject):
    second: Attr[str]
    first: Attr[str]


class CorrPeer(Entity, table="corr_peer", namespace=_NS):
    """The shared target every variant's directions name."""

    id: Attr[int] = attr(primary_key=True)


class _Composed(Entity, table="corr", name="Corr", namespace=_NS):
    """The class every construction below resolves, and the one the plans are
    built from."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None]
    doc: Attr[_Doc | None]
    left_id: Attr[int | None]
    right_id: Attr[int | None]
    left: Rel[CorrPeer | None] = rel(cardinality=MANY_TO_ONE, join=("left_id", "id"))
    right: Rel[CorrPeer | None] = rel(cardinality=MANY_TO_ONE, join=("right_id", "id"))


class _ReorderedMembers(Entity, table="corr", name="Corr", namespace=_NS):
    """The same Entity with two Attributes declared the other way round."""

    id: Attr[int] = attr(primary_key=True)
    note: Attr[str | None]
    label: Attr[str] = attr(max_length=16)
    doc: Attr[_Doc | None]
    left_id: Attr[int | None]
    right_id: Attr[int | None]
    left: Rel[CorrPeer | None] = rel(cardinality=MANY_TO_ONE, join=("left_id", "id"))
    right: Rel[CorrPeer | None] = rel(cardinality=MANY_TO_ONE, join=("right_id", "id"))


class _ScalarNote(Entity, table="corr_note", name="CorrNote", namespace=_NS):
    """An Entity mapping its last member as a scalar."""

    id: Attr[int] = attr(primary_key=True)
    note: Attr[str | None]


class _OccurrenceNote(Entity, table="corr_note", name="CorrNote", namespace=_NS):
    """The same Entity calling that member a Value Object occurrence.

    The one pair whose member ROW matches: a scalar declared last sits at the same
    position an occurrence declared first does, because both runs are laid out
    attributes-then-occurrences. So what is left to disagree about is the kind.
    """

    id: Attr[int] = attr(primary_key=True)
    note: Attr[_Note | None]


class _ReorderedRelationships(Entity, table="corr", name="Corr", namespace=_NS):
    """The same Entity with its two directions declared the other way round."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None]
    doc: Attr[_Doc | None]
    left_id: Attr[int | None]
    right_id: Attr[int | None]
    right: Rel[CorrPeer | None] = rel(cardinality=MANY_TO_ONE, join=("right_id", "id"))
    left: Rel[CorrPeer | None] = rel(cardinality=MANY_TO_ONE, join=("left_id", "id"))


class _SwappedDocMembers(Entity, table="corr", name="Corr", namespace=_NS):
    """The same Entity whose occurrence lays its own members out the other way
    round — one containment path, two orders."""

    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None]
    doc: Attr[_SwappedDoc | None]
    left_id: Attr[int | None]
    right_id: Attr[int | None]
    left: Rel[CorrPeer | None] = rel(cardinality=MANY_TO_ONE, join=("left_id", "id"))
    right: Rel[CorrPeer | None] = rel(cardinality=MANY_TO_ONE, join=("right_id", "id"))


class _Inner(ValueObject):
    tip: Attr[str]


class _OuterScalar(ValueObject):
    head: Attr[str]
    inner: Attr[str]


class _OuterNested(ValueObject):
    head: Attr[str]
    inner: Attr[_Inner | None]


class _DeepScalar(Entity, table="corr_deep", name="CorrDeep", namespace=_NS):
    """An Entity whose occurrence maps its own last member as a scalar."""

    id: Attr[int] = attr(primary_key=True)
    doc: Attr[_OuterScalar | None]


class _DeepNested(Entity, table="corr_deep", name="CorrDeep", namespace=_NS):
    """The same Entity whose occurrence calls that member a nested occurrence."""

    id: Attr[int] = attr(primary_key=True)
    doc: Attr[_OuterNested | None]


_CORR: EntityIdentity = _Composed.identity


def _disagreeing(composed: type[Entity], variant: type[Entity]) -> InternalError:
    """The refusal one construction earns when the model it lays its rows out
    against is ``variant``'s and the class it publishes is ``composed``'s.

    Only a test hands a construction that pair: a composition root takes the
    cataloged metadata and the composed classes off one Domain Model, so the two
    halves are handed in disagreeing here, through the constructor a composition
    root itself calls — which derives every Entity's facts as it is built and
    refuses there.
    """
    classes = class_index(DomainModel(composed, CorrPeer))
    assert classes is not None
    with raises_code(InternalError, "entity-graph-layout-mismatch") as refusal:
        EntityGraphConstruction(CatalogedModel(model_of(DomainModel(variant, CorrPeer))), classes)
    return refusal.value


def test_the_pair_that_agrees_is_not_refused() -> None:
    # The control: `_Composed` against its own model is the shape every other
    # case is one deviation from, so a refusal below is that deviation rather
    # than the check refusing everything. Read back through a published node,
    # since what the correspondence buys is that each of the model's row
    # positions lands on the member the class carries at it.
    (published,) = published_nodes(
        DomainModel(_Composed, CorrPeer),
        (_CORR, (1, "north", None, 2, 3, ("head", "tail")), (UNLOADED, UNLOADED)),
    )
    corr = cast("_Composed", published)
    assert (corr.id, corr.label, corr.note, corr.left_id, corr.right_id) == (1, "north", None, 2, 3)
    assert (cast("_Doc", corr.doc).first, cast("_Doc", corr.doc).second) == ("head", "tail")


def test_a_construction_proves_only_the_class_it_composed_for_an_entity() -> None:
    construction = graph_construction_for(DomainModel(_Composed, CorrPeer))

    assert construction.proves(_Composed, _CORR)
    assert not construction.proves(_ReorderedMembers, _CORR)
    assert not construction.proves(_Composed, CorrPeer.identity)
    assert not construction.proves(_ScalarNote, _ScalarNote.identity)


def test_a_member_row_the_class_lays_out_differently_is_refused() -> None:
    refusal = _disagreeing(_Composed, _ReorderedMembers)
    assert "'id', 'note', 'label'" in refusal.args[1]
    assert "'id', 'label', 'note'" in refusal.args[1]


def test_a_member_the_model_calls_a_value_object_and_the_class_maps_as_a_scalar_is_refused() -> (
    None
):
    # The rejection a positional row cannot make and an identity-keyed carrier
    # could: the two sides agree about which members exist and disagree about
    # what KIND position 2 is, which a row of the right width says nothing about
    # because width is a count. Without this the disagreement reaches the
    # declared type's own check further down and is refused as a value outside a
    # `str`'s value space — true, and an accident of what `note` happens to be
    # declared as.
    refusal = _disagreeing(_ScalarNote, _OccurrenceNote)
    assert "the model calls member 1 ('note') a Value Object occurrence" in refusal.args[1]
    assert "the class holds None at that position" in refusal.args[1]


def test_a_relationship_tail_the_class_lays_out_differently_is_refused() -> None:
    # A tail position carries no name and no presence bit once a row is written,
    # so a direction installed at another direction's position would answer for
    # the wrong relationship silently, for the life of the graph.
    refusal = _disagreeing(_Composed, _ReorderedRelationships)
    assert "'right', 'left'" in refusal.args[1]
    assert "'left', 'right'" in refusal.args[1]


def test_a_nested_occurrence_the_class_maps_as_a_leaf_is_refused() -> None:
    # The same kind disagreement one containment level down. A nested occurrence
    # is a member row of its own where a leaf is one value, so a class binding no
    # Value Object Class at that position would take the row as the leaf's value.
    refusal = _disagreeing(_DeepScalar, _DeepNested)
    assert "calls member 1 ('inner') a nested occurrence" in refusal.args[1]
    assert "_OuterScalar holds None there" in refusal.args[1]


def test_a_value_object_path_layout_the_class_lays_out_differently_is_refused() -> None:
    # A Value Object layout is keyed to a containment PATH and a publication plan
    # to a CLASS, so the correspondence descends into the occurrence rather than
    # stopping at the position that holds it.
    refusal = _disagreeing(_Composed, _SwappedDocMembers)
    assert f"{_CORR.canonical}.doc lays out members ('second', 'first')" in refusal.args[1]
    assert "_Doc is laid out as ('first', 'second')" in refusal.args[1]


class _AlphaRoot(
    Entity,
    table="fam_alpha",
    name="Alpha",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    """One of two families whose members are spelled identically and declared
    differently, so a name says which member only once an ancestry is fixed."""

    id: Attr[int] = attr(primary_key=True)
    payload: Attr[str] = attr(max_length=16)


class _BetaRoot(
    Entity,
    table="fam_beta",
    name="Beta",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    payload: Attr[int]


class _KinOfAlpha(
    _AlphaRoot, name="Kin", namespace=_NS, inheritance=ConcreteSubtype(tag_value="k")
):
    pass


class _KinOfBeta(_BetaRoot, name="Kin", namespace=_NS, inheritance=ConcreteSubtype(tag_value="k")):
    pass


class _NextOfBeta(
    _BetaRoot, name="Next", namespace=_NS, inheritance=ConcreteSubtype(tag_value="n")
):
    pass


class _NextOfAlpha(
    _AlphaRoot, name="Next", namespace=_NS, inheritance=ConcreteSubtype(tag_value="n")
):
    pass


_ANCESTRIES = (
    DomainModel(_AlphaRoot, _BetaRoot, _KinOfAlpha, _NextOfBeta),
    DomainModel(_AlphaRoot, _BetaRoot, _KinOfBeta, _NextOfAlpha),
)


class _TieRoot(
    Entity,
    table="tie",
    name="TieRoot",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    """The family whose root owns ``peer``, against a twin whose middle does."""

    id: Attr[int] = attr(primary_key=True)
    peer_id: Attr[int | None]
    peer: Rel[CorrPeer | None] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))


class _TieRootSilent(
    Entity,
    table="tie",
    name="TieRoot",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    peer_id: Attr[int | None]


class _TieMid(_TieRoot, name="TieMid", namespace=_NS, inheritance=AbstractSubtype):
    pass


class _TieMidNavigating(_TieRootSilent, name="TieMid", namespace=_NS, inheritance=AbstractSubtype):
    peer: Rel[CorrPeer | None] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))


class _Anchor(_TieMid, name="Anchor", namespace=_NS, inheritance=ConcreteSubtype(tag_value="a")):
    pass


class _AnchorNavigating(
    _TieMidNavigating, name="Anchor", namespace=_NS, inheritance=ConcreteSubtype(tag_value="a")
):
    pass


_DECLARING_LEVELS = (
    DomainModel(_TieRoot, _TieMid, _Anchor, CorrPeer),
    DomainModel(_TieRootSilent, _TieMidNavigating, _AnchorNavigating, CorrPeer),
)


def _refusal_across(cataloged: DomainModel, composed: DomainModel) -> InternalError:
    """The refusal a construction earns when it lays its rows out against
    ``cataloged`` and publishes ``composed``'s classes."""
    classes = class_index(composed)
    assert classes is not None
    with raises_code(InternalError, "entity-graph-layout-mismatch") as refusal:
        EntityGraphConstruction(CatalogedModel(model_of(cataloged)), classes)
    return refusal.value


def test_a_member_row_two_ancestries_spell_the_same_way_is_refused() -> None:
    # A member's local name is unique down ONE ancestry, so an equal-looking row
    # is not an equal row across two. Both models declare the same four Entity
    # Identities and assign `Kin` to opposite parents, so every identity has a
    # class and the two `Kin` rows spell ('id', 'payload') on both sides — while
    # the model means Beta's members and the class carries Alpha's. Without this
    # the pair passes and a `(1, 7)` row publishes the integer 7 into a member
    # declared `str`, because the value is checked against the layout's declared
    # type and written at the class's own position.
    refusal = _refusal_across(_ANCESTRIES[1], _ANCESTRIES[0])
    assert "the model declares member 0 ('id')" in refusal.args[1]
    assert "name='Beta'" in refusal.args[1]
    assert "name='Alpha'" in refusal.args[1]


def test_a_relationship_two_ancestries_declare_at_different_levels_is_refused() -> None:
    # The tail analogue, and the one a local name cannot express: both families
    # navigate one `peer`, one declaring it at the root and one at the middle, so
    # `Anchor`'s tail is spelled ('peer',) on both sides and names two different
    # relationships — whose targets and cardinalities the check may not assume
    # agree. `Anchor` is refused rather than an ancestor because Entity
    # enumeration is canonical Identity order and the refusal names the Entity
    # whose own row the disagreement would misdirect.
    refusal = _refusal_across(_DECLARING_LEVELS[0], _DECLARING_LEVELS[1])
    assert "the model lays out relationship 0 ('peer')" in refusal.args[1]


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
