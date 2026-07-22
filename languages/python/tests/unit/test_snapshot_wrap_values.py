"""Value-object and temporal node wrapping (COR-3 Phase 7 increment 6a; spec
§3/§4): ``parallax.snapshot.handle._wrap.wrap_graph``'s value-object member
construction, whole-graph pin / per-node edge attachment, and ``Snapshot[T]``'s
arity accessors. The identity, projection and load-state half lives in
``test_snapshot_wrap_identity.py``.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

import snapshot_models as sm
from parallax.conformance import models
from parallax.core import Attr, Bitemporal, Entity, EntityConfig, Field, descriptor
from parallax.core.entity import metamodel
from parallax.core.entity.base import Concrete, FamilyRoot
from parallax.core.temporal_read import Pin, edge_of, pin_of
from parallax.snapshot.handle import Execution, NoResultFound, Snapshot, TooManyResultsFound
from parallax.snapshot.handle._wrap import wrap_graph
from parallax.snapshot.materialize import Node

pytestmark = pytest.mark.unit

_ORDERS = metamodel([sm.SnapOrder, sm.SnapOrderItem, sm.SnapOrderStatus])
_BALANCE = models.load_models()["balance"]


# --------------------------------------------------------------------------- #
# Entity-level value-object members (cardinality one and many).                #
# --------------------------------------------------------------------------- #
def test_entity_level_value_object_members_wrap_into_their_declared_classes() -> None:
    status = Node(
        fields={
            "id": 1,
            "order_id": 1,
            "order_item_id": None,
            "code": "shipped",
            "primary_tag": None,
            "tags": [
                {
                    "label": "a",
                    "detail": {"note": "x"},
                    "details": [{"note": "y"}, None],
                },
                {"label": "b"},
                None,
            ],
        },
        pk_columns=("id",),
    )
    (root,) = wrap_graph((status,), "SnapOrderStatus", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrderStatus)
    assert root.primary_tag is None
    assert len(root.tags) == 2
    first, second = root.tags
    assert isinstance(first, sm.Tag)
    assert first.label == "a"
    assert first.detail == sm.Detail(note="x")
    assert first.details == (sm.Detail(note="y"),)
    assert second.label == "b"
    assert second.detail is None
    assert second.details == ()


def test_a_null_cardinality_many_value_object_column_wraps_to_an_empty_tuple() -> None:
    empty_status = Node(
        fields={
            "id": 2,
            "order_id": 1,
            "order_item_id": None,
            "code": "empty",
            "primary_tag": None,
            "tags": None,
        },
        pk_columns=("id",),
    )
    (root,) = wrap_graph((empty_status,), "SnapOrderStatus", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrderStatus)
    assert root.tags == ()


# --------------------------------------------------------------------------- #
# A metamodel / registry disagreement about a member's SHAPE.                   #
#                                                                               #
# `metamodel([...])` compiles the descriptor FROM the classes, so the two agree #
# by construction there — but they are two independent sources in the           #
# conformance lane, where the descriptor is authored YAML and the class is a    #
# hand-written Python mirror. A descriptor that calls a member a value object   #
# while the registered class maps it as a scalar has no ValueObject class to    #
# construct, and `_wrap_member` must say so rather than hand back the raw       #
# decoded dict typed as the declared VO (spec §3's instances-only contract).    #
# --------------------------------------------------------------------------- #
class _WrapScalarProfile(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="wrap_scalar_profile",
        namespace="parallax.compatibility",
        mutability="transactional",
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    profile: Attr[str] = Field(type="string", max_length=32)


# The SAME entity as the class above, except `profile` is declared a value
# object rather than the scalar attribute the class registers.
_PROFILE_AS_VALUE_OBJECT = descriptor.Metamodel(
    entities=(
        descriptor.Entity(
            name="_WrapScalarProfile",
            table="wrap_scalar_profile",
            namespace="parallax.compatibility",
            mutability="transactional",
            attributes=(
                descriptor.Attribute(name="id", type="int64", column="id", primary_key=True),
            ),
            value_objects=(descriptor.ValueObject(name="profile", column="profile"),),
        ),
    )
)


def test_a_value_object_member_with_no_registered_class_is_refused() -> None:
    # The premise: the CLASS really does map `profile` as a scalar, so the
    # refusal below comes from the disagreement with the descriptor above and
    # not from a malformed class declaration.
    compiled = metamodel([_WrapScalarProfile]).entity("_WrapScalarProfile")
    assert [attr.name for attr in compiled.attributes] == ["id", "profile"]
    assert compiled.value_objects == ()

    node = Node(fields={"id": 1, "profile": {"note": "x"}}, pk_columns=("id",))
    match = r"_WrapScalarProfile\.profile: no registered ValueObject"
    with pytest.raises(LookupError, match=match):
        wrap_graph((node,), "_WrapScalarProfile", _PROFILE_AS_VALUE_OBJECT, Pin())


# --------------------------------------------------------------------------- #
# Whole-graph pin / per-node edge attachment (temporal_read.pin_of / edge_of). #
# --------------------------------------------------------------------------- #
def test_temporal_node_carries_the_whole_graph_pin_and_its_own_edge() -> None:
    row = Node(
        fields={
            "id": 1,
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("5.00"),
            "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        },
        pk_columns=("bal_id",),
    )
    pin = Pin(tx_time=dt.datetime(2024, 2, 1, tzinfo=dt.UTC))
    (root,) = wrap_graph((row,), "Balance", _BALANCE, pin)
    assert pin_of(root) is pin
    assert edge_of(root).tx_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


# --------------------------------------------------------------------------- #
# Temporal inheritance (review Spec-3 fix): a table-per-concrete-subtype       #
# family whose bitemporal axes are declared on the abstract ROOT and inherited #
# by every concrete descendant (m-inheritance "Inherited members") — the       #
# corpus's own Rate/DepositRate shape (`models/rate.yaml`), where the concrete #
# declares NO `asOfAttributes` locally. `_wrap._wrap` previously checked only  #
# the concrete descriptor's own (empty) `as_of_axes`, so a temporal            #
# inheritance node never got `pin_of`/`edge_of` attached at all.               #
# --------------------------------------------------------------------------- #
class _WrapTemporalRoot(Bitemporal, frozen=True):
    __parallax__ = EntityConfig(
        namespace="parallax.compatibility",
        mutability="transactional",
        inheritance=FamilyRoot(strategy="table-per-concrete-subtype"),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    amount: Attr[Decimal] = Field(type="decimal(18,2)")


class _WrapTemporalLeaf(_WrapTemporalRoot, frozen=True):
    __parallax__ = EntityConfig(
        table="wrap_temporal_leaf",
        namespace="parallax.compatibility",
        mutability="transactional",
        inheritance=Concrete(),
    )

    grade: Attr[str | None] = Field(type="string", max_length=8, nullable=True)


_TEMPORAL_TPCS = metamodel([_WrapTemporalRoot, _WrapTemporalLeaf])


def test_temporal_tpcs_concrete_node_carries_pin_and_edge() -> None:
    row = Node(
        fields={
            "id": 1,
            "amount": Decimal("2.50"),
            "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "thru_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            "grade": "A",
        },
        pk_columns=("id",),
    )
    pin = Pin(
        valid_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        tx_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    (root,) = wrap_graph((row,), "_WrapTemporalLeaf", _TEMPORAL_TPCS, pin)
    assert isinstance(root, _WrapTemporalLeaf)
    assert pin_of(root) is pin
    assert edge_of(root).valid_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert edge_of(root).tx_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


# --------------------------------------------------------------------------- #
# Snapshot[T] arity accessors.                                                 #
# --------------------------------------------------------------------------- #
def _snapshot(roots: tuple[object, ...]) -> Snapshot[object]:
    return Snapshot(roots, Pin(), Execution(()))


def test_result_raises_on_zero_and_on_more_than_one() -> None:
    with pytest.raises(NoResultFound):
        _snapshot(()).result()
    with pytest.raises(TooManyResultsFound):
        _snapshot((1, 2)).result()
    assert _snapshot((1,)).result() == 1


def test_result_or_none_returns_none_on_zero_and_raises_on_more_than_one() -> None:
    assert _snapshot(()).result_or_none() is None
    assert _snapshot((1,)).result_or_none() == 1
    with pytest.raises(TooManyResultsFound):
        _snapshot((1, 2)).result_or_none()


def test_results_returns_a_fresh_list_per_call() -> None:
    snapshot = _snapshot((1, 2))
    first = snapshot.results()
    second = snapshot.results()
    assert first == [1, 2]
    assert first is not second


def test_snapshot_has_no_iteration_len_or_indexing() -> None:
    snapshot = _snapshot((1, 2))
    assert not hasattr(snapshot, "__iter__")
    assert not hasattr(snapshot, "__len__")
    assert not hasattr(snapshot, "__getitem__")


def test_snapshot_pin_and_execution_and_repr() -> None:
    pin = Pin(tx_time=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
    snapshot = Snapshot((1,), pin, Execution(()))
    assert snapshot.pin is pin
    assert snapshot.execution.round_trips == 0
    assert "Snapshot(roots=1" in repr(snapshot)
