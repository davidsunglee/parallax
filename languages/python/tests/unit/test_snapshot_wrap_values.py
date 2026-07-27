"""Value-object and temporal node wrapping (spec
§3/§4): ``parallax.snapshot.handle._wrap.wrap_graph``'s value-object member
construction, whole-graph pin / per-node edge attachment, and ``Snapshot[T]``'s
arity accessors. The identity, projection and load-state half lives in
``test_snapshot_wrap_identity.py``.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from _snapshot_wrap_support import wrap

import snapshot_models as sm
from parallax.conformance.read_models import BALANCE_MODEL
from parallax.core import (
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Entity,
    MetamodelHub,
    ValueObject,
    attr,
)
from parallax.core.entity._hub import sealed_model
from parallax.core.temporal_read import Pin, edge_of, pin_of
from parallax.snapshot.handle import Execution, NoResultFound, Snapshot, TooManyResultsFound
from parallax.snapshot.materialize import Node

pytestmark = pytest.mark.unit

_ORDERS = sm.SNAP_ORDERS_MODEL


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
        },
        value_objects={
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
    (root,) = wrap((status,), "SnapOrderStatus", _ORDERS)
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
        },
        value_objects={
            "primary_tag": None,
            "tags": None,
        },
        pk_columns=("id",),
    )
    (root,) = wrap((empty_status,), "SnapOrderStatus", _ORDERS)
    assert isinstance(root, sm.SnapOrderStatus)
    assert root.tags == ()


# --------------------------------------------------------------------------- #
# A model / class disagreement about a member's SHAPE.                         #
#                                                                              #
# A class-backed hub compiles its model FROM the classes, so the two agree by  #
# construction there — but they are two independent sources in the conformance #
# lane, where the model is authored YAML and the class is a hand-written       #
# mirror. A model that calls a member a value object while the bound class     #
# maps it as a scalar has no ValueObject class to construct, and               #
# `_wrap_member` must say so rather than hand back the raw decoded dict typed  #
# as the declared VO (spec §3's instances-only contract).                      #
# --------------------------------------------------------------------------- #
class _WrapScalarProfile(Entity, table="wrap_scalar_profile", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    profile: Attr[str] = attr(max_length=32)


_SCALAR_PROFILE = MetamodelHub(_WrapScalarProfile)


# The SAME entity as the class above, except `profile` is declared a value
# object rather than the scalar attribute the class maps.
class _WrapDocumentProfile(ValueObject):
    note: Attr[str]


class _WrapVoProfile(
    Entity,
    table="wrap_scalar_profile",
    name="_WrapScalarProfile",
    namespace="parallax.compatibility",
):
    id: Attr[int] = attr(primary_key=True)
    profile: Attr[_WrapDocumentProfile]


_PROFILE_AS_VALUE_OBJECT = sealed_model(MetamodelHub(_WrapVoProfile)).model


def test_a_value_object_member_with_no_bound_class_is_refused() -> None:
    # The premise: the bound CLASS really does map `profile` as a scalar, so the
    # refusal below comes from the disagreement with the model above and not
    # from a malformed class declaration.
    assert [a.identity.name for a in _WrapScalarProfile.attributes] == ["id", "profile"]
    assert _WrapScalarProfile.value_objects == ()

    node = Node(
        fields={"id": 1},
        pk_columns=("id",),
        value_objects={"profile": {"note": "x"}},
    )
    match = r"_WrapScalarProfile\.profile: the bound Entity Class declares no"
    with pytest.raises(LookupError, match=match):
        wrap((node,), "_WrapScalarProfile", _SCALAR_PROFILE, model=_PROFILE_AS_VALUE_OBJECT)


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
    (root,) = wrap((row,), "Balance", BALANCE_MODEL, pin)
    assert pin_of(root) is pin
    assert edge_of(root).tx_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


# --------------------------------------------------------------------------- #
# Temporal inheritance: a table-per-concrete-subtype                           #
# family whose bitemporal axes are declared on the abstract ROOT and inherited #
# by every concrete descendant (m-inheritance "Inherited members") — the       #
# corpus's own Rate/DepositRate shape (`models/rate.yaml`), where the concrete #
# declares NO `asOfAttributes` locally. `_wrap._wrap` previously checked only  #
# the concrete descriptor's own (empty) `as_of_axes`, so a temporal            #
# inheritance node never got `pin_of`/`edge_of` attached at all.               #
# --------------------------------------------------------------------------- #
class _WrapTemporalRoot(
    Bitemporal,
    namespace="parallax.compatibility",
    inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE),
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=18, scale=2)


class _WrapTemporalLeaf(
    _WrapTemporalRoot,
    table="wrap_temporal_leaf",
    namespace="parallax.compatibility",
    inheritance=ConcreteSubtype,
):
    grade: Attr[str | None] = attr(max_length=8)


_TEMPORAL_TPCS = MetamodelHub(_WrapTemporalRoot, _WrapTemporalLeaf)


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
    (root,) = wrap((row,), "_WrapTemporalLeaf", _TEMPORAL_TPCS, pin)
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
