"""What publication attaches, through which door, and what a published node holds.

Entity Graph Construction no longer fills a Pydantic instance a member at a time.
It allocates a shell that holds nothing, assembles the whole row in local state,
and attaches it once — so a node either carries everything its read carried or
carries nothing at all, and the instance dictionary every Pydantic model is
assumed to have is never created for one.

Three claims live here that no other module states. **The door**: neither
constructor is entered, and the slot is written exactly once. **What is left
behind**: no storage, no name-keyed presence, no layout pointer, nothing per
instance that is a fact about the class. **What the model and the class have to
agree about**: a positional row is written against the model's member layout and
read back through the class's own publication plan, and the two are derived from
different material, so the pair is compared once and refused when it disagrees.

The correspondence refusals are reached by pairing one model's accepted metadata
with another's composed classes, which is a state only a test can build: a
composition root always takes both facts off one Domain Model. Each pair below is
two class declarations under one Entity Identity that disagree in exactly one
way.
"""

from __future__ import annotations

import gc
import weakref
from typing import Any, cast

import pytest
from _compact_support import carries_instance_storage, layout_slots, raw_row

from parallax.core.entity import (
    MANY_TO_ONE,
    UNLOADED,
    Attr,
    Entity,
    EntityGraphWriter,
    NodeHandle,
    Rel,
    ValueObject,
    attr,
    graph_construction_of,
    lifecycle_state_of,
    rel,
    relationship_value_of,
    row_codec_of,
    to_document,
)
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._errors import GraphConstructionError
from parallax.core.entity._graph_construction import (
    EntityGraphConstruction,
    _CallScope,  # pyright: ignore[reportPrivateUsage] - the scope the memo's life is a fact about
)
from parallax.core.entity._instance_state import COMPACT_STATE_SLOT, plan_of
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.entity._model import DomainModel, model_of
from parallax.core.metamodel import EntityIdentity, RelationshipIdentity, ValueObjectIdentity

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


def _one_parcel(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
    handle = writer.allocate(_PARCEL)
    writer.populate(handle, (1, "north", ABSENT, ABSENT, _TAG_ROW), (UNLOADED,))
    return (handle,)


def _published(build: Any = _one_parcel, *, state_factory: Any = None) -> Any:
    (root,) = graph_construction_of(PARCELS).construct(build, state_factory=state_factory)
    return root


# --------------------------------------------------------------------------- #
# The door publication takes.                                                  #
# --------------------------------------------------------------------------- #


def test_publication_enters_neither_constructor(monkeypatch: pytest.MonkeyPatch) -> None:
    # Deterministic rather than probabilistic: both doors are replaced with ones
    # that fail, so entering either is the test failing rather than a shape
    # someone has to notice. The Entity and its Value Object are both covered,
    # because an occurrence is published by the same door one level down.
    def refuse(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("publication entered a Pydantic constructor")

    for cls in (Parcel, Tag):
        monkeypatch.setattr(cls, "__init__", refuse)
        monkeypatch.setattr(cls, "model_construct", cast("Any", classmethod(refuse)))

    root = _published()
    assert (root.id, root.label) == (1, "north")
    assert root.tag.label == "red"


def test_a_published_node_s_row_is_attached_exactly_once() -> None:
    # A row is assembled in local state and attached at the end, so a populate
    # this collaboration refuses leaves its shell exactly as allocation left it —
    # unattached, and free to be populated again by a caller that corrects the
    # row. Nothing half-written survives the refusal.
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_PARCEL)
        with pytest.raises(GraphConstructionError) as refusal:
            writer.populate(handle, (1, "north", ABSENT, ABSENT, _TAG_ROW), ("not an arm",))
        assert refusal.value.code == "entity-graph-invalid-value"
        writer.populate(handle, (2, "south", ABSENT, ABSENT, ABSENT), (UNLOADED,))
        return (handle,)

    root = cast("Parcel", _published(build))
    assert raw_row(root) == (0b00011, 2, "south", None, None, None, UNLOADED)


def test_populating_a_node_twice_never_reaches_the_row_at_all() -> None:
    # The writer's own refusal stands in front of the row: the second call is
    # rejected on the node's populated state before any member is read, so
    # "attached exactly once" does not rest on the attachment noticing.
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_PARCEL)
        writer.populate(handle, (1, "north", ABSENT, ABSENT, ABSENT), (UNLOADED,))
        with pytest.raises(GraphConstructionError) as refusal:
            writer.populate(handle, (9, "z", ABSENT, ABSENT, ABSENT), (UNLOADED,))
        assert refusal.value.code == "entity-graph-node-already-populated"
        return (handle,)

    assert cast("Parcel", _published(build)).id == 1


# --------------------------------------------------------------------------- #
# What a published node holds, and what it does not.                           #
# --------------------------------------------------------------------------- #


def test_a_published_node_holds_one_row_and_no_state_keyed_by_a_name() -> None:
    root = _published()
    row = raw_row(root)
    assert row == (0b10011, 1, "north", None, None, root.tag, UNLOADED)
    assert root.model_fields_set == {"id", "label", "tag"}
    assert not carries_instance_storage(root)
    assert not carries_instance_storage(root.tag)
    for held in gc.get_referents(root):
        assert not isinstance(held, dict | set)


def test_a_published_node_carries_no_fact_that_belongs_to_its_class() -> None:
    # No layout pointer, no Adapter, no wrapper: the only class fact a published
    # node reaches is the one every instance of that class reaches, through its
    # own type. So two nodes of one class refer to nothing in common but the
    # class, and the plan they resolve their ordinals from is that class's.
    first, second = _published(), _published()
    plan = plan_of(Parcel)
    for node in (first, second):
        assert plan not in gc.get_referents(node)
        assert plan_of(cast("type[Any]", type(node))) is plan
    assert {id(held) for held in gc.get_referents(first)} & {
        id(held) for held in gc.get_referents(second)
    } == {id(Parcel), id(None)}


def test_a_published_node_s_object_layout_is_the_framework_roots_own() -> None:
    # The slots a published node has are the ones the framework lays out and
    # nothing else: the row, the auxiliary slot a `cached_property` would warm,
    # Pydantic's two containers and its two presented names, and — on an Entity
    # alone — the lifecycle slot.
    assert set(layout_slots(Parcel)) == {
        COMPACT_STATE_SLOT,
        "__parallax_auxiliary__",
        "__parallax_lifecycle__",
        "__pydantic_extra__",
        "__pydantic_fields_set__",
        "__pydantic_private__",
    }
    assert "__parallax_lifecycle__" not in layout_slots(Tag)


def test_no_framework_read_of_a_published_graph_creates_its_storage() -> None:
    # The residual `object.__setattr__` leaves open is that a caller holding a
    # value can write its storage; the framework's own obligation is to make no
    # such write, and this is where every first-party read of a published node is
    # driven at one and the storage asked for afterwards — by identity, and
    # without asking the value for a mapping, since asking is what would create
    # one.
    state = object()

    def factory(_view: object, _handle: object) -> object:
        return state

    root = _published(state_factory=factory)
    codec = row_codec_of(PARCELS)

    assert codec.full_row(root)
    assert to_document(root.tag)
    assert root.model_dump() == {
        "id": 1,
        "label": "north",
        "note": None,
        "tag": {"label": "red", "weight": 2},
        "peer_id": None,
    }
    assert repr(root)
    assert root == _published()
    assert dict(root)
    assert relationship_value_of(root, RelationshipIdentity(_PARCEL, "peer")) is UNLOADED
    assert lifecycle_state_of(root) is state

    assert not carries_instance_storage(root)
    assert not carries_instance_storage(root.tag)


# --------------------------------------------------------------------------- #
# What one construction retains, and what it does not.                         #
# --------------------------------------------------------------------------- #


def test_class_metadata_count_is_independent_of_published_instance_count() -> None:
    # The whole point of resolving an ordinal from the class: publishing more
    # nodes derives no more metadata. The per-Entity facts and the member layout
    # are each derived once per model and answered from thereafter, whether one
    # node or a hundred are published against them.
    construction = graph_construction_of(PARCELS)
    facts = construction.facts_for(_PARCEL)

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handles = [writer.allocate(_PARCEL) for _ in range(100)]
        for handle in handles:
            writer.populate(handle, (1, "north", ABSENT, ABSENT, ABSENT), (UNLOADED,))
        return tuple(handles)

    roots = construction.construct(build)
    assert len(roots) == 100
    assert construction.facts_for(_PARCEL) is facts
    assert plan_of(Parcel) is plan_of(Parcel)


def test_a_cyclic_published_graph_is_collected_whole() -> None:
    # Two nodes referring to each other through their rows, which is a reference
    # cycle the collector has to break: nothing outside the graph names either
    # node, and no cache, layout, or presence memo holds one after the roots go.
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        left = writer.allocate(_PARCEL)
        right = writer.allocate(_PARCEL)
        writer.populate(left, (1, "l", ABSENT, 2, ABSENT), (right,))
        writer.populate(right, (2, "r", ABSENT, 1, ABSENT), (left,))
        return (left, right)

    roots = graph_construction_of(PARCELS).construct(build)
    alive = [weakref.ref(cast("Any", node)) for node in roots]
    assert cast("Any", roots[0]).peer is roots[1]

    del roots
    gc.collect()
    assert [reference() for reference in alive] == [None, None]


def test_no_call_scope_outlives_the_construction_that_made_it() -> None:
    # The presence-bitmap memo lives on the call scope, so what keeps it from
    # being a process-wide cache is that the scope itself is unreachable once
    # `construct` returns. Read off the heap rather than argued, because a memo
    # promoted to module scope would still pass every behavioral assertion here.
    _published()
    gc.collect()
    assert [held for held in gc.get_objects() if type(held) is _CallScope] == []


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


def _disagreeing(composed: type[Entity], variant: type[Entity]) -> GraphConstructionError:
    """The refusal one construction earns when the model it derives its layout
    from is ``variant``'s and the class it publishes is ``composed``'s.

    Only a test can hold a construction in that state: a composition root always
    takes the accepted metadata and the composed classes off one Domain Model, so
    the two halves are substituted here the way the graph suites substitute a
    merge's model.
    """
    construction = EntityGraphConstruction(DomainModel(composed, CorrPeer))
    meta = model_of(DomainModel(variant, CorrPeer))
    construction._model = meta  # pyright: ignore[reportPrivateUsage] - the disagreeing pair a root cannot build
    construction._layouts = LayoutCatalog(meta)  # pyright: ignore[reportPrivateUsage] - same
    with pytest.raises(GraphConstructionError) as refusal:
        construction.facts_for(cast("EntityIdentity", cast("Any", composed).identity))
    assert refusal.value.code == "entity-graph-layout-mismatch"
    return refusal.value


def test_the_pair_that_agrees_is_not_refused() -> None:
    # The control: `_Composed` against its own model is the shape every other
    # case is one deviation from, so a refusal below is that deviation rather
    # than the check refusing everything.
    facts = EntityGraphConstruction(DomainModel(_Composed, CorrPeer)).facts_for(_CORR)
    assert tuple(attribute.py_name for attribute in facts.attributes) == (
        "id",
        "label",
        "note",
        "left_id",
        "right_id",
    )


def test_a_member_row_the_class_lays_out_differently_is_refused() -> None:
    refusal = _disagreeing(_Composed, _ReorderedMembers)
    assert "'id', 'note', 'label'" in refusal.message
    assert "'id', 'label', 'note'" in refusal.message
    assert refusal.identity == _CORR


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
    assert "the model calls member 1 ('note') a Value Object occurrence" in refusal.message
    assert "the class holds None at that position" in refusal.message
    assert refusal.identity == ValueObjectIdentity(_OccurrenceNote.identity, ("note",))


def test_a_relationship_tail_the_class_lays_out_differently_is_refused() -> None:
    # A tail position carries no name and no presence bit once a row is written,
    # so a direction installed at another direction's position would answer for
    # the wrong relationship silently, for the life of the graph.
    refusal = _disagreeing(_Composed, _ReorderedRelationships)
    assert "'right', 'left'" in refusal.message
    assert "'left', 'right'" in refusal.message


def test_a_nested_occurrence_the_class_maps_as_a_leaf_is_refused() -> None:
    # The same kind disagreement one containment level down. A nested occurrence
    # is a member row of its own where a leaf is one value, so a class binding no
    # Value Object Class at that position would take the row as the leaf's value.
    refusal = _disagreeing(_DeepScalar, _DeepNested)
    assert "calls member 1 ('inner') a nested occurrence" in refusal.message
    assert "_OuterScalar holds None there" in refusal.message


def test_a_row_laid_out_against_another_models_layout_is_refused() -> None:
    # The other half of the correspondence, and the one that does not involve a
    # class at all: the member layout a row is written against and the runs this
    # collaboration reads it back with are two derivations of the model's own
    # order, neither derived from the other. A row laid out against a different
    # model's layout is what a disagreement between them would install, member by
    # member, with nothing left to notice it.
    construction = EntityGraphConstruction(DomainModel(_Composed, CorrPeer))
    foreign = model_of(DomainModel(_ReorderedMembers, CorrPeer))
    construction._layouts = LayoutCatalog(foreign)  # pyright: ignore[reportPrivateUsage] - a pair a root cannot build
    with pytest.raises(GraphConstructionError) as refusal:
        construction.facts_for(_CORR)
    assert refusal.value.code == "entity-graph-layout-mismatch"
    assert "the member layout lays out" in refusal.value.message
    assert "this collaboration reads" in refusal.value.message


def test_a_value_object_path_layout_the_class_lays_out_differently_is_refused() -> None:
    # A Value Object layout is keyed to a containment PATH and a publication plan
    # to a CLASS, so the correspondence descends into the occurrence rather than
    # stopping at the position that holds it.
    refusal = _disagreeing(_Composed, _SwappedDocMembers)
    assert f"{_CORR.canonical}.doc lays out members ('second', 'first')" in refusal.message
    assert "_Doc is laid out as ('first', 'second')" in refusal.message
