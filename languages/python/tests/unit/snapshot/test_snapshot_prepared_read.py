"""One compiled read bound once, and what its rows answer (m-snapshot-read).

The production seam a read lane crosses: a compiled read and a cataloged model
bind into a prepared read, and every row of that statement is converted through
``PreparedRead.convert_row`` and observed through it. What a row carries into
conversion — the concrete it resolved, the findings the transform raised, the
members it already classified — is the compiled read's own provenance, so every
case here drives a real ``compile_read`` rather than handing conversion a
provenance no statement produced.

The levels exist before the rows do: a read whose position is one concrete can
still answer a row of a sibling or of the family root. A tuple row and a
result-keyed row of one statement convert to the same state, whether the level
keeps its witness as its member row or reduces it. Identity, routing, and
temporal coordinates are ready when a row is claimed; the rest of the payload is
judged only when a Root View consumes it, and a correlation judged for routing is
never judged again. A classified member is translated rather than judged again,
in each of the states the transform can leave it in. And the observation reads one
row's physical columns under the same level, including the occurrences only the
position's OTHER concretes ever store at.

Where a guarantee is about when or how often a stored value is judged rather
than about what was published, the case records conversion's own decoding and
admission dependencies and counts what they reach.
"""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, cast

import pytest

from parallax.core import ONE_TO_MANY, Attr, DomainModel, Entity, Rel, ValueObject, attr, rel
from parallax.core import predicate as oa
from parallax.core.base import INFINITY, SQL_NULL, DocumentValue, PresentDocument
from parallax.core.db_port import Row
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import MISSING
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.temporal_read import Pin
from parallax.descriptor._records import (
    Attribute,
    DocumentLayout,
    Inheritance,
    NestedValueObject,
    ValueObjectAttribute,
)
from parallax.descriptor._records import (
    Entity as DescriptorEntity,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.descriptor._records import ValueObject as DescriptorValueObject
from parallax.snapshot.materialize import PageBuilder, RootView, _convert
from parallax.snapshot.materialize._page import ABSENT, StoredDataIssueInput, page_rows
from parallax.snapshot.materialize._prepared import PreparedRead, bind
from parallax.snapshot.materialize._publication import publication_issue
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import formed, target
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._document_layout_support import columns_model
from tests.unit._prepared_read_support import bound_read, compiled_read
from tests.unit._snapshot_materialization_support import (
    LAYOUTS,
    OWNERS,
    Layout,
    StressPort,
    batch,
    compiled_levels,
    metamodel,
    query,
    read_plan,
    rows_per_level,
)
from tests.unit.snapshot._snapshot_page_support import (
    physical_members,
    recorded_conversion_dependencies,
    rendered_members,
)

ANIMAL = corpus_model("animal")
SCALARS = corpus_model("scalars")


# --------------------------------------------------------------------------- #
# Models no corpus carries: a required document-resident member, a partially    #
# composed family, and a position whose concretes each own one occurrence.      #
# --------------------------------------------------------------------------- #
def _register_model() -> Metamodel:
    """One Relational Document Layout Entity whose document holds a REQUIRED
    member beside two nullable ones.

    Every document-resident member of a document-layout row arrives classified,
    so this is the shape that reaches each of the three states a classified
    member can be in — and the required member is what makes a stored null
    distinguishable from a nullable one's.
    """
    register = DescriptorEntity(
        name="Register",
        table="register",
        layout=DocumentLayout(column="payload"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="label", type="string", column="label"),
            Attribute(name="note", type="string", column="note", nullable=True),
            Attribute(name="stamp", type="date", column="stamp", nullable=True),
        ),
        value_objects=(
            DescriptorValueObject(
                name="marks",
                column="marks",
                multiplicity="many",
                attributes=(ValueObjectAttribute(name="tag", type="string"),),
                value_objects=(
                    NestedValueObject(
                        name="origin",
                        nullable=True,
                        attributes=(ValueObjectAttribute(name="port", type="string"),),
                    ),
                ),
            ),
        ),
    )
    return formed(DescriptorMetamodel(entities=(register,)))


def _partial_family() -> Metamodel:
    """A table-per-hierarchy family this model composed only part of, so the
    shared table can hand back a row tagged for a sibling it never declared."""
    root = DescriptorEntity(
        name="Beast",
        table="beast",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    wolf = DescriptorEntity(
        name="Wolf",
        inheritance=Inheritance(role="concrete-subtype", parent="Beast", tag_value="wolf"),
        attributes=(Attribute(name="howl", type="string", column="howl", nullable=True),),
    )
    return formed(DescriptorMetamodel(entities=(root, wolf)))


def _craft_family() -> Metamodel:
    """A table-per-hierarchy family whose two concretes each declare one
    occurrence, in the two multiplicities — the shape a polymorphic position
    observes its own concrete's occurrence and its siblings' alike."""
    root = DescriptorEntity(
        name="Craft",
        table="craft",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    tug = DescriptorEntity(
        name="Tug",
        inheritance=Inheritance(role="concrete-subtype", parent="Craft", tag_value="tug"),
        value_objects=(
            DescriptorValueObject(
                name="berth",
                column="berth",
                nullable=True,
                attributes=(ValueObjectAttribute(name="quay", type="string"),),
            ),
        ),
    )
    barge = DescriptorEntity(
        name="Barge",
        inheritance=Inheritance(role="concrete-subtype", parent="Craft", tag_value="barge"),
        value_objects=(
            DescriptorValueObject(
                name="decks",
                column="decks",
                multiplicity="many",
                attributes=(ValueObjectAttribute(name="label", type="string"),),
            ),
        ),
    )
    return formed(DescriptorMetamodel(entities=(root, tug, barge)))


def _encoded_identity_model() -> Metamodel:
    encoded = DescriptorEntity(
        name="EncodedIdentity",
        table="encoded_identity",
        attributes=(
            Attribute(name="id", type="bytes", column="id", primary_key=True),
            Attribute(name="token", type="bytes", column="token", nullable=True),
        ),
    )
    return formed(DescriptorMetamodel(entities=(encoded,)))


REGISTER = _register_model()
BEAST = _partial_family()
CRAFT = _craft_family()
ENCODED_IDENTITY = _encoded_identity_model()


# --------------------------------------------------------------------------- #
# Driving one prepared read.                                                   #
# --------------------------------------------------------------------------- #
def _compiled(model: Metamodel, name: str, *, narrow_to: tuple[str, ...] = ()) -> CompiledRead:
    """The instance-form read of ``name``, compiled as a find compiles it.

    ``narrow_to`` names the query-wide narrowing by bare Entity name, which is
    what resolves the read's position to fewer concretes than its family has.
    """
    return compile_read(
        oa.All(),
        model,
        POSTGRES,
        target(model, name),
        narrow_to=tuple(target(model, narrowed).identity for narrowed in narrow_to) or None,
        result_form="instance",
    )


def _prepared(model: Metamodel, name: str, *, narrow_to: tuple[str, ...] = ()) -> PreparedRead:
    """The read of ``name``, compiled and bound as a find binds it."""
    return bind(CatalogedModel(model), _compiled(model, name, narrow_to=narrow_to))


@dataclass(frozen=True, slots=True)
class _Converted:
    """One converted row: the concrete it laid out under, the members it carries
    by declared name, and what it classified.

    A member the row holds no value at is absent from ``members``, which is the
    positional row's ``ABSENT`` rendered — so what a state answers is read as the
    presence or absence of a name rather than as an index.
    """

    concrete: EntityIdentity
    members: Mapping[str, Any]
    issues: tuple[StoredDataIssueInput, ...]


def _converted(prepared: PreparedRead, stored: Mapping[str, object]) -> _Converted:
    """One stored row through the whole prepared seam: convert and seal."""
    builder = PageBuilder(ViewSchema.of())
    index, _resolved, _document, _variant = prepared.convert_row(stored, builder, source=ROOT_LEVEL)
    page = builder.finish((index,), Pin())
    rows = page_rows(page)
    layout = rows.layouts[index]
    root = RootView(page)
    values = rows.member_rows[index] if root.roots == (None,) else root.member_values(0)
    issues = root.invalid_roots[0].issues if root.roots == (None,) else root.issues(0)
    return _Converted(layout.concrete, rendered_members(layout, values), issues)


def _observed(prepared: PreparedRead, stored: Mapping[str, object]) -> dict[str, object]:
    """One stored row's shared Entity State viewed under physical storage keys."""
    builder = PageBuilder(ViewSchema.of())
    index, _resolved, _document, _variant = prepared.convert_row(stored, builder, source=ROOT_LEVEL)
    page = builder.finish((index,), Pin())
    rows = page_rows(page)
    root = RootView(page)
    return physical_members(rows.layouts[index], root.member_values(0))


def _stored_document(members: Mapping[str, object]) -> PresentDocument:
    """One Structured Column present in a row, carrying ``members`` in the
    portable spelling a document stores them in."""
    return PresentDocument(cast("DocumentValue", dict(members)))


_ONE_DECK: Final = "aft"


def _stored_decks() -> PresentDocument:
    """One stored ``decks`` array, the Many occurrence only `Barge` declares."""
    return PresentDocument(cast("DocumentValue", [{"label": _ONE_DECK}]))


# --------------------------------------------------------------------------- #
# Every Entity a read can resolve has its level before a row names it.         #
# --------------------------------------------------------------------------- #
def test_a_narrowed_read_converts_rows_of_every_entity_it_can_resolve() -> None:
    # A level belongs to the compiled read, so one exists for every Entity the
    # read can resolve before any row arrives. The narrowed family read is where
    # that is distinguishable — its position is one concrete while its rows can
    # resolve to the whole family — and a row of the position and a row outside
    # it each convert under their own concrete.
    compiled = _compiled(ANIMAL, "Animal", narrow_to=("Dog",))
    prepared = bind(CatalogedModel(ANIMAL), compiled)
    rex = _converted(
        prepared,
        {"id": 1, "kind": "dog", "name": "Rex", "owner_id": 10, "bark_volume": 3},
    )
    boar = _converted(
        prepared,
        {"id": 2, "kind": "boar", "name": "Bo", "owner_id": 10, "tusk_length": None},
    )
    assert {identity.name for identity in compiled.resolvable} >= {"Dog", "WildBoar"}
    assert (rex.concrete.name, boar.concrete.name) == ("Dog", "WildBoar")


def test_a_sibling_outside_the_narrowed_position_converts_under_its_own_concrete() -> None:
    # A narrowed read of an abstract target resolves a position of one concrete
    # and still projects the family's whole tag column, so the shared table can
    # hand back a row of a concrete the narrow excluded. That row converts under
    # `WildBoar`'s own member layout — bound with the read, before any row proved
    # the Entity was reachable — and each of its Attributes reads under its own
    # storage spelling, since the statement projected no contract for an Entity
    # outside its position.
    prepared = _prepared(ANIMAL, "Animal", narrow_to=("Dog",))
    boar = _converted(
        prepared,
        {
            "id": 2,
            "kind": "boar",
            "name": "Bo",
            "owner_id": 10,
            "tusk_length": decimal.Decimal("3.00"),
        },
    )
    assert boar.concrete.name == "WildBoar"
    assert boar.members["tuskLength"] == decimal.Decimal("3.00")
    assert boar.issues == ()


def test_an_unrecognized_family_tag_converts_under_the_family_root() -> None:
    # A model may compose a family's concretes partially, so a row tagged for one
    # it never declared resolves to the family ROOT — an Entity no position holds,
    # since the root is abstract and only concretes are projected. Its level is
    # bound anyway, and the row converts into the root's own members beside the
    # issue the unknown tag publishes.
    prepared = _prepared(BEAST, "Beast")
    unknown = _converted(prepared, {"id": 2, "kind": "bear", "howl": None})
    assert unknown.concrete.name == "Beast"
    assert unknown.members == {"id": 2}
    assert [issue.code for issue in unknown.issues] == ["stored-data-family-tag-unknown"]


def test_an_unknown_tag_is_host_checked_but_its_native_key_is_trusted() -> None:
    # The unconstrained family discriminator remains host-checked. The direct key
    # Column does not: its SQL type and primary-key constraint establish the value
    # space, so materialization trusts what the provider normalized there.
    prepared = _prepared(BEAST, "Beast")
    node = _converted(prepared, {"id": None, "kind": "bear", "howl": None})
    assert [issue.code for issue in node.issues] == ["stored-data-family-tag-unknown"]


# --------------------------------------------------------------------------- #
# A retained raw member is classified once, only after witness comparison.               #
# --------------------------------------------------------------------------- #
_ADA: Final[Mapping[str, object]] = {
    "label": "ada",
    "note": "north wing",
    "stamp": "2026-01-15",
    "marks": [{"tag": "founder", "origin": {"port": "Oslo"}}],
}


def _register(document: Mapping[str, object]) -> _Converted:
    return _converted(
        _prepared(REGISTER, "Register"), {"id": 1, "payload": _stored_document(document)}
    )


def test_raw_witness_distinguishes_sql_null_from_a_present_empty_document() -> None:
    # A shared Structured Column's SQL-null carrier and a present document that
    # omits the same member collapse to the same read value, but they are distinct
    # stored structure and must remain distinct before witness comparison.
    compiled = _compiled(REGISTER, "Register")
    identity = target(REGISTER, "Register").identity

    sql_null = compiled.raw_member_of({"id": 1, "payload": SQL_NULL}, identity, "label")
    missing = compiled.raw_member_of({"id": 1, "payload": PresentDocument({})}, identity, "label")

    assert sql_null is SQL_NULL
    assert missing is MISSING


def test_a_missing_shared_document_occurrence_is_classified_as_sql_null() -> None:
    node = _register({key: value for key, value in _ADA.items() if key != "marks"})

    assert node.members["marks"] == ()
    assert node.issues == ()


def test_a_direct_document_occurrence_is_classified_under_the_concrete_its_row_names() -> None:
    node = _converted(
        _prepared(CRAFT, "Craft"),
        {"id": 1, "kind": "tug", "berth": _stored_document({"quay": "7"})},
    )

    assert node.concrete == target(CRAFT, "Tug").identity
    assert node.members["berth"] == {"quay": "7"}
    assert node.issues == ()


def test_a_classified_member_is_carried_as_the_transform_classified_it() -> None:
    # Every member of a document-layout row but its key arrives already decoded
    # and already judged, as the MANAGED value its declared type spells.
    # Conversion carries each at its own position without asking the admission
    # rule again, which is what keeps a decoded value distinguishable from the
    # two states below.
    node = _register(_ADA)
    assert node.members["label"] == "ada"
    assert node.members["stamp"] == dt.date(2026, 1, 15)
    assert node.members["marks"] == ({"tag": "founder", "origin": {"port": "Oslo"}},)
    assert node.issues == ()


def test_a_classified_stored_null_reads_by_its_declared_nullability() -> None:
    # Stored null is the one classified state the member's own declaration
    # decides: a nullable member carries it as the value it is, and a required
    # one holds no value at all — the same two answers the admission rule gives,
    # reached without running it. The codec's own finding is what publishes the
    # required member's issue.
    nullable = _register({**_ADA, "note": None})
    assert nullable.members["note"] is None
    assert nullable.issues == ()

    required = _register({**_ADA, "label": None})
    assert "label" not in required.members
    assert [issue.code for issue in required.issues] == ["stored-data-attribute-null"]


def test_a_classified_member_the_transform_made_unavailable_is_absent() -> None:
    # `UNAVAILABLE` is the codec's own verdict that no conforming value could be
    # made available at that member, and it is not a value: the position reads
    # ABSENT even where a stored null at the SAME member reads `None`, which is
    # the distinction trusting the classification has to keep.
    node = _register({**_ADA, "label": 7})
    assert "label" not in node.members
    assert [issue.code for issue in node.issues] == ["stored-data-leaf-undecodable"]


def test_native_identity_and_document_members_need_no_scalar_admission() -> None:
    # A direct primary-key Column is established by its installed SQL type and
    # constraint, while document members arrive classified by the document codec.
    # Neither reaches the host scalar-admission rule.
    with recorded_conversion_dependencies() as calls:
        node = _register(_ADA)
    assert calls.admitted == []
    assert calls.decoded == []
    assert set(node.members) == {"id", "label", "note", "stamp", "marks"}


@pytest.mark.parametrize(
    ("raw", "key", "issue"),
    [
        pytest.param("0a1b", b"\x0a\x1b", None, id="canonical-wire"),
        pytest.param(None, None, "stored-data-primary-key-null", id="sql-null"),
        pytest.param(
            "not-hex",
            None,
            "stored-data-primary-key-undecodable",
            id="noncanonical-wire",
        ),
    ],
)
def test_encoded_identity_is_decoded_before_logical_key_formation(
    raw: object, key: object, issue: str | None
) -> None:
    builder = PageBuilder(ViewSchema.of())
    index, _resolved, _document, _variant = _prepared(
        ENCODED_IDENTITY, "EncodedIdentity"
    ).convert_row({"id_hex": raw, "token_hex": None}, builder, source=ROOT_LEVEL)
    claimed = builder.finish((index,), Pin())
    stored_key = page_rows(claimed).keys[index]
    root = RootView(claimed)
    issues = root.invalid_roots[0].issues if root.roots == (None,) else root.issues(0)

    assert (None if stored_key is None else stored_key.primary_key) == key
    assert [finding.code for finding in issues] == ([] if issue is None else [issue])


def _encoded_member(name: str) -> AttributeIdentity:
    return AttributeIdentity(target(ENCODED_IDENTITY, "EncodedIdentity").identity, name)


def test_identity_routing_skips_an_absent_non_identity_cell() -> None:
    token = _encoded_member("token")
    prepared = bound_read(ENCODED_IDENTITY, "EncodedIdentity", correlation_members=(token,))
    builder = PageBuilder(ViewSchema.of())
    index, *_ = prepared.convert_row({"id_hex": "0a1b"}, builder, source=ROOT_LEVEL)

    assert builder.member_value(index, _encoded_member("id")) == b"\x0a\x1b"
    assert builder.member_value(index, token) is ABSENT
    root = RootView(builder.finish((index,), Pin()))
    assert root.issues(0) == ()


def test_identity_routing_keeps_native_non_identity_cells_unchanged() -> None:
    identity = target(SCALARS, "ScalarThing").identity
    payload, f32 = AttributeIdentity(identity, "payload"), AttributeIdentity(identity, "f32")
    prepared = bound_read(SCALARS, "ScalarThing", correlation_members=(payload, f32))
    builder = PageBuilder(ViewSchema.of())
    index, *_ = prepared.convert_row(
        {"id": 1, "payload_hex": "0a1b", "f32": 1.5}, builder, source=ROOT_LEVEL
    )

    assert builder.member_value(index, payload) == b"\x0a\x1b"
    assert builder.member_value(index, f32) == 1.5


def test_sql_null_in_a_nullable_encoded_column_bypasses_wire_decoding() -> None:
    with recorded_conversion_dependencies() as calls:
        node = _converted(
            _prepared(ENCODED_IDENTITY, "EncodedIdentity"), {"id_hex": "0a1b", "token_hex": None}
        )

    assert node.members == {"id": b"\x0a\x1b", "token": None}
    assert node.issues == ()
    assert calls.decoded == ["0a1b"]
    assert calls.admitted == [b"\x0a\x1b", None]


# --------------------------------------------------------------------------- #
# The observation, taken under the same level the conversion read.             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "stored",
    [
        pytest.param({}, id="the-column-is-not-in-the-row"),
        pytest.param({"decks": None}, id="the-column-is-null-padding"),
        pytest.param({"decks": SQL_NULL}, id="the-column-is-a-sql-null-document"),
    ],
)
def test_a_sibling_occurrence_does_not_enter_the_concrete_entity_state(
    stored: dict[str, object],
) -> None:
    # A polymorphic statement may carry every concrete's occurrence column, but
    # the Page-owned Entity State is laid out by the row's resolved concrete.
    # Sibling-only storage therefore contributes no member, whether the driver
    # omitted it, null-padded it, or returned a SQL-null document marker.
    prepared = _prepared(CRAFT, "Craft")
    tug = _observed(
        prepared,
        {"id": 1, "kind": "tug", "berth": _stored_document({"quay": "7"}), **stored},
    )
    assert tug["berth"] == {"quay": "7"}
    assert "decks" not in tug
    barge = _observed(prepared, {"id": 2, "kind": "barge", "decks": _stored_decks()})
    decks = cast("tuple[Mapping[str, object], ...]", barge["decks"])
    assert tuple(map(dict, decks)) == ({"label": _ONE_DECK},)
    assert "berth" not in barge


def test_a_sibling_document_does_not_enter_the_concrete_entity_state() -> None:
    # Even an unexpectedly populated sibling column is outside the resolved
    # concrete's Entity State; the polymorphic statement shape cannot add a
    # member that concrete does not own.
    observed = _observed(
        _prepared(CRAFT, "Craft"),
        {"id": 1, "kind": "tug", "decks": _stored_decks()},
    )
    assert "decks" not in observed


def test_an_encoded_projection_is_observed_under_its_physical_column() -> None:
    # A Predecessor MappingRow is keyed by the column the value is STORED in, so the
    # alias an encoded cell arrives under is excluded from the passthrough and
    # the decoded value is answered under the Column's own name instead.
    observed = _observed(
        _prepared(SCALARS, "ScalarThing"),
        {
            "id": 1,
            "f32": 1.5,
            "f64": 2.5,
            "payload_hex": "0a1b",
            "local_time": None,
            "external_id": None,
        },
    )
    assert "payload_hex" not in observed
    assert observed["payload"] == b"\x0a\x1b"


def test_a_document_row_is_observed_with_its_members_under_their_own_columns() -> None:
    # The observation is physical under either Storage Layout: a document-layout
    # row's members were fanned out to the keys their Columns would carry, and
    # the observation answers those keys with the values the fan-out decoded —
    # each managed value as the classification left it, never decoded again.
    observed = _observed(
        _prepared(REGISTER, "Register"), {"id": 1, "payload": _stored_document(_ADA)}
    )
    assert observed["label"] == "ada"
    assert observed["stamp"] == dt.date(2026, 1, 15)
    marks = cast("tuple[Mapping[str, object], ...]", observed["marks"])
    assert tuple(map(dict, marks)) == ({"tag": "founder", "origin": {"port": "Oslo"}},)


def test_a_row_publisher_views_a_projected_occurrence_in_place() -> None:
    prepared = _prepared(REGISTER, "Register")
    builder = PageBuilder(ViewSchema.of())
    index, _resolved, _document, variant = prepared.convert_row(
        {"id": 1, "payload": _stored_document(_ADA)}, builder, source=ROOT_LEVEL
    )
    root = RootView(builder.finish((index,), Pin()))

    published = prepared.row_publisher().publish(
        root.layout(0).concrete, root.member_values(0), variant
    )

    assert list(published) == ["id", "label", "note", "stamp", "marks"]
    assert published["stamp"] == dt.date(2026, 1, 15)
    (mark,) = cast("tuple[Mapping[str, object], ...]", published["marks"])
    assert (mark["tag"], dict(cast("Mapping[str, object]", mark["origin"]))) == (
        "founder",
        {"port": "Oslo"},
    )


# --------------------------------------------------------------------------- #
# A positional row and a result-keyed row of one statement are one state.      #
# --------------------------------------------------------------------------- #
_OPENED: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_VALID_FROM: Final = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
POSITION = corpus_model("position")
BALANCE = corpus_model("balance")
ORDERS = corpus_model("orders")
TWIN_COLUMNS = columns_model()


def _shadowed_payload_model() -> Metamodel:
    """An encoded Attribute whose result key spells another Attribute's Column."""
    blob = DescriptorEntity(
        name="Blob",
        table="blob",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="payload", type="bytes", column="payload", nullable=True),
            Attribute(name="shadow", type="bytes", column="payload_hex", nullable=True),
        ),
    )
    return formed(DescriptorMetamodel(entities=(blob,)))


SHADOWED = _shadowed_payload_model()

_ORDER: Final[Mapping[str, object]] = {
    "id": 1,
    "name": "Ada",
    "sku": None,
    "qty": 2,
    "price": decimal.Decimal("1.50"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 1),
}
_SCALAR_THING: Final[Mapping[str, object]] = {
    "id": 1,
    "f32": 1.5,
    "f64": 2.5,
    "payload_hex": "0a1b",
    "local_time": dt.time(9, 30),
    "external_id": None,
}


def _position(**cells: object) -> dict[str, object]:
    """One stored bitemporal `Position` row, current on both axes."""
    return {
        "pos_id": 1,
        "acct_num": "A-1",
        "val": decimal.Decimal("1.50"),
        "from_z": _VALID_FROM,
        "thru_z": INFINITY,
        "in_z": _OPENED,
        "out_z": INFINITY,
        **cells,
    }


def _positional(model: Metamodel, entity: str, cells: Mapping[str, object]) -> Row:
    """``cells`` laid out in the compiled read's own result order, as a port
    returns a provider row."""
    keys = compiled_read(model, entity).result_keys
    assert set(cells) == set(keys)
    return tuple(cells[key] for key in keys)


@dataclass(frozen=True, slots=True)
class _Delivered:
    """What one converted row answers: its logical key, its judged members by
    declared name, its issues, and the flat row it publishes."""

    key: object
    members: Mapping[str, Any]
    issues: tuple[StoredDataIssueInput, ...]
    flat: Mapping[str, object]


def _delivered(model: Metamodel, entity: str, row: Row | Mapping[str, object]) -> _Delivered:
    prepared = bound_read(model, entity)
    builder = PageBuilder(ViewSchema.of())
    index, resolved, _document, variant = prepared.convert_row(row, builder, source=ROOT_LEVEL)
    page = builder.finish((index,), Pin())
    key = page_rows(page).keys[index]
    root = RootView(page)
    values = root.member_values(0)
    return _Delivered(
        key,
        rendered_members(root.layout(0), values),
        root.issues(0),
        prepared.row_publisher().publish(resolved, values, variant),
    )


@pytest.mark.parametrize(
    ("model", "entity", "cells", "member", "value"),
    [
        pytest.param(
            ORDERS, "Order", _ORDER, "orderedOn", dt.date(2024, 1, 1), id="native-columns"
        ),
        pytest.param(
            SCALARS, "ScalarThing", _SCALAR_THING, "payload", b"\x0a\x1b", id="encoded-column"
        ),
        pytest.param(POSITION, "Position", _position(), "validEnd", INFINITY, id="bitemporal"),
        pytest.param(
            REGISTER,
            "Register",
            {"id": 1, "payload": PresentDocument(cast("DocumentValue", dict(_ADA)))},
            "stamp",
            dt.date(2026, 1, 15),
            id="relational-document",
        ),
        pytest.param(TWIN_COLUMNS, "Marker", {"id": 5}, "id", 5, id="singleton-width"),
    ],
)
def test_a_positional_and_a_result_keyed_row_convert_and_publish_alike(
    model: Metamodel, entity: str, cells: Mapping[str, object], member: str, value: object
) -> None:
    # A port answers positional rows and a fake answers result-keyed ones, and
    # a level either keeps a row's witness as its member row or reduces it. None
    # of those choices is observable in the key, the judged members, the issues,
    # or the published flat row.
    positional = _delivered(model, entity, _positional(model, entity, cells))
    keyed = _delivered(model, entity, cells)
    assert positional == keyed
    assert positional.key is not None
    assert positional.members[member] == value
    assert positional.issues == ()


_ROW_FORMS: Final = pytest.mark.parametrize(
    "positional", [False, True], ids=["result-keyed", "positional"]
)


@_ROW_FORMS
def test_a_member_stored_at_another_members_result_key_reads_its_own_cell(
    positional: bool,
) -> None:
    # `payload` arrives under its encoded alias `payload_hex`, which is the Column
    # `shadow` is stored in, so `shadow`'s own cell arrives aliased once more.
    # Each Attribute reads the cell its own result key names, and the flat row
    # publishes both renamed members after the one it keeps.
    cells = {"id": 1, "payload_hex": "00ff", "payload_hex_hex": "0102"}
    delivered = _delivered(
        SHADOWED, "Blob", _positional(SHADOWED, "Blob", cells) if positional else cells
    )
    assert (delivered.members["payload"], delivered.members["shadow"]) == (
        b"\x00\xff",
        b"\x01\x02",
    )
    assert list(delivered.flat.items()) == [
        ("id", 1),
        ("payload_hex", "00ff"),
        ("payload_hex_hex", "0102"),
    ]


def test_a_result_keyed_row_without_a_column_carries_no_value_for_it() -> None:
    # Only a result-keyed row can omit a column. An omitted Attribute holds no
    # value rather than a null, while an omitted occurrence reads as one stored
    # without a document: no value for a One and nothing for a Many.
    delivered = _delivered(TWIN_COLUMNS, "Person", {"id": 1, "display_name": "Ada"})
    assert delivered.members == {"id": 1, "displayName": "Ada", "address": None, "tags": ()}
    assert delivered.issues == ()


@_ROW_FORMS
@pytest.mark.parametrize(
    ("model", "entity", "cells", "starts"),
    [
        pytest.param(ORDERS, "Order", _ORDER, (), id="no-axis-unreduced"),
        pytest.param(SCALARS, "ScalarThing", _SCALAR_THING, (), id="no-axis-reduced"),
        pytest.param(
            BALANCE,
            "Balance",
            {
                "bal_id": 1,
                "acct_num": "A-1",
                "val": decimal.Decimal("1.50"),
                "in_z": _OPENED,
                "out_z": INFINITY,
            },
            (_OPENED,),
            id="transaction-time",
        ),
        pytest.param(POSITION, "Position", _position(), (_VALID_FROM, _OPENED), id="bitemporal"),
    ],
)
def test_a_row_keys_by_its_axis_starts_in_layout_order(
    model: Metamodel,
    entity: str,
    cells: Mapping[str, object],
    starts: tuple[object, ...],
    positional: bool,
) -> None:
    row = _positional(model, entity, cells) if positional else cells
    key = _delivered(model, entity, row).key
    assert key == (target(model, entity).identity, 1, starts)


# --------------------------------------------------------------------------- #
# Temporal identity: the axis starts key a row, and its ends are host-checked.  #
# --------------------------------------------------------------------------- #
def test_a_bitemporal_row_keys_by_its_axis_starts_and_admits_its_open_ends() -> None:
    delivered = _delivered(POSITION, "Position", _positional(POSITION, "Position", _position()))
    family = target(POSITION, "Position").identity
    assert delivered.key == (family, 1, (_VALID_FROM, _OPENED))
    assert (delivered.members["validEnd"], delivered.members["txEnd"]) == (INFINITY, INFINITY)
    assert delivered.issues == ()


@pytest.mark.parametrize(
    ("column", "stored", "member", "code"),
    [
        pytest.param(
            "thru_z", "not-an-instant", "validEnd", "stored-data-leaf-undecodable", id="malformed"
        ),
        pytest.param("out_z", None, "txEnd", "stored-data-attribute-null", id="null"),
    ],
)
def test_a_rejected_temporal_end_is_diagnosed_once_its_state_is_judged(
    column: str, stored: object, member: str, code: str
) -> None:
    builder = PageBuilder(ViewSchema.of())
    index, *_ = bound_read(POSITION, "Position").convert_row(
        _position(**{column: stored}), builder, source=ROOT_LEVEL
    )
    page = builder.finish((index,), Pin())
    assert page_rows(page).keys[index] == (
        target(POSITION, "Position").identity,
        1,
        (_VALID_FROM, _OPENED),
    )
    root = RootView(page)
    entity = target(POSITION, "Position").identity
    assert [(issue.code, issue.member, issue.stored_value) for issue in root.issues(0)] == [
        (code, AttributeIdentity(entity, member), stored)
    ]
    assert member not in rendered_members(root.layout(0), root.member_values(0))


def test_rows_share_a_logical_node_only_where_key_and_axis_starts_agree() -> None:
    prepared = bound_read(POSITION, "Position")
    builder = PageBuilder(ViewSchema.of())
    refs = tuple(
        prepared.convert_row(row, builder, source=ROOT_LEVEL)[0]
        for row in (
            _position(),
            _position(),
            _position(in_z=_OPENED + dt.timedelta(days=1)),
            _position(pos_id=2),
        )
    )
    rows = page_rows(builder.finish(refs, Pin()))
    assert list(rows.logical_ids) == [0, 0, 1, 2]


# --------------------------------------------------------------------------- #
# Correlations: judged once when the row is claimed, reused by its payload.    #
# --------------------------------------------------------------------------- #
_NAMESPACE = "parallax.compatibility"


class CorrelatedTerms(ValueObject):
    label: Attr[str]


class CorrelatedHolder(Entity, table="correlated_holder", namespace=_NAMESPACE):
    id: Attr[bytes] = attr(primary_key=True)
    holdings: Rel[tuple[CorrelatedHolding, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "holder_id")
    )


class CorrelatedCustodian(Entity, table="correlated_custodian", namespace=_NAMESPACE):
    id: Attr[bytes] = attr(primary_key=True)
    holdings: Rel[tuple[CorrelatedHolding, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "custodian_id")
    )


class CorrelatedHolding(Entity, table="correlated_holding", namespace=_NAMESPACE):
    """Joined to two owners through non-key Bytes Columns, with an unrelated
    encoded payload Column between them and a document Column after them."""

    id: Attr[int] = attr(primary_key=True)
    holder_id: Attr[bytes | None]
    digest: Attr[bytes | None]
    custodian_id: Attr[bytes | None]
    terms: Attr[CorrelatedTerms | None]
    holder: Rel[CorrelatedHolder | None] = rel(reverse_of="holdings")
    custodian: Rel[CorrelatedCustodian | None] = rel(reverse_of="holdings")


HOLDINGS = model_of(DomainModel(CorrelatedHolder, CorrelatedCustodian, CorrelatedHolding))
_HOLDING = EntityIdentity(_NAMESPACE, "CorrelatedHolding")
_HOLDER = AttributeIdentity(_HOLDING, "holderId")
_DIGEST = AttributeIdentity(_HOLDING, "digest")
_CUSTODIAN = AttributeIdentity(_HOLDING, "custodianId")
_TERMS_LABEL = ValueObjectAttributeIdentity(ValueObjectIdentity(_HOLDING, ("terms",)), "label")


def _holdings() -> PreparedRead:
    """The holding level bound with its correlations named in reverse attribute
    order, as a plan may select them."""
    return bound_read(HOLDINGS, "CorrelatedHolding", correlation_members=(_CUSTODIAN, _HOLDER))


def _holding(**cells: object) -> dict[str, object]:
    return {
        "id": 1,
        "holder_id_hex": "a101",
        "digest_hex": "d101",
        "custodian_id_hex": "c101",
        "terms": SQL_NULL,
        **cells,
    }


def _consumed(row: Mapping[str, object]) -> RootView:
    builder = PageBuilder(ViewSchema.of())
    index, *_ = _holdings().convert_row(row, builder, source=ROOT_LEVEL)
    return RootView(builder.finish((index,), Pin()))


def test_a_correlation_is_judged_once_for_routing_and_reused_by_its_payload() -> None:
    with recorded_conversion_dependencies() as calls:
        builder = PageBuilder(ViewSchema.of())
        index, *_ = _holdings().convert_row(_holding(), builder, source=ROOT_LEVEL)
        assert builder.member_value(index, _HOLDER) == b"\xa1\x01"
        assert builder.member_value(index, _CUSTODIAN) == b"\xc1\x01"
        assert sorted(cast("list[str]", calls.decoded)) == ["a101", "c101"]
        assert sorted(cast("list[bytes]", calls.admitted)) == [b"\xa1\x01", b"\xc1\x01"]

        root = RootView(builder.finish((index,), Pin()))
        members = rendered_members(root.layout(0), root.member_values(0))

    assert sorted(cast("list[str]", calls.decoded)) == ["a101", "c101", "d101"]
    assert sorted(cast("list[bytes]", calls.admitted)) == [
        b"\xa1\x01",
        b"\xc1\x01",
        b"\xd1\x01",
    ]
    assert (members["holderId"], members["digest"], members["custodianId"]) == (
        b"\xa1\x01",
        b"\xd1\x01",
        b"\xc1\x01",
    )
    assert root.issues(0) == ()


@pytest.mark.parametrize(
    ("stored", "routed", "issues"),
    [
        pytest.param("a101", b"\xa1\x01", [], id="accepted"),
        pytest.param(None, None, [], id="null"),
        pytest.param(ABSENT, ABSENT, [], id="absent"),
        pytest.param("zz", ABSENT, [("stored-data-leaf-undecodable", "zz")], id="rejected"),
    ],
)
def test_a_routed_correlation_is_visible_before_consumption_and_diagnosed_after(
    stored: object, routed: object, issues: list[tuple[str, object]]
) -> None:
    # A rejected correlation routes as no value, exactly as an absent one does,
    # yet only the rejection publishes a finding once the payload is consumed.
    row = _holding(holder_id_hex=stored)
    if stored is ABSENT:
        del row["holder_id_hex"]
    builder = PageBuilder(ViewSchema.of())
    index, *_ = _holdings().convert_row(row, builder, source=ROOT_LEVEL)
    assert builder.member_value(index, _HOLDER) is routed or (
        builder.member_value(index, _HOLDER) == routed
    )

    root = RootView(builder.finish((index,), Pin()))
    assert root.member_values(0)[root.layout(0).index_of[_HOLDER]] == routed
    assert [
        (issue.code, issue.stored_value) for issue in root.issues(0) if issue.member == _HOLDER
    ] == issues


def _diagnoses(root: RootView) -> list[tuple[object, ...]]:
    return [(issue.code, issue.member, issue.path, issue.stored_value) for issue in root.issues(0)]


def test_captured_correlation_findings_keep_their_attribute_positions_in_the_payload() -> None:
    # Both correlations are judged when the row is claimed, the unrelated `digest`
    # between them only when its state is consumed. Publication still lists every
    # finding in its documented order — the document codec's first, then each
    # Attribute at its own position — and the first of them is what refuses.
    failing = _holding(
        holder_id_hex="zz",
        digest_hex="yy",
        custodian_id_hex="xx",
        terms=PresentDocument({"label": 7}),
    )
    root = _consumed(failing)
    undecodable = "stored-data-leaf-undecodable"
    assert _diagnoses(root) == [
        (undecodable, _TERMS_LABEL, ("terms", "label"), 7),
        (undecodable, _HOLDER, (), "zz"),
        (undecodable, _DIGEST, (), "yy"),
        (undecodable, _CUSTODIAN, (), "xx"),
    ]
    assert publication_issue(root) is root.issues(0)[0]

    without_document = _consumed({**failing, "terms": SQL_NULL})
    assert [member for _code, member, _path, _value in _diagnoses(without_document)] == [
        _HOLDER,
        _DIGEST,
        _CUSTODIAN,
    ]
    refusal = publication_issue(without_document)
    assert refusal is not None
    assert refusal.member == _HOLDER


def test_a_rejected_correlation_freezes_its_evidence_when_it_is_judged() -> None:
    # The rejected value is captured at the routing verdict. A provider carrier
    # mutated after the row was claimed cannot rewrite what the payload publishes.
    rejected: list[object] = ["0a", {"k": "1b"}]
    builder = PageBuilder(ViewSchema.of())
    index, *_ = _holdings().convert_row(
        _holding(holder_id_hex=rejected), builder, source=ROOT_LEVEL
    )
    cast("dict[str, object]", rejected[1])["k"] = "changed"
    rejected.append("more")

    root = RootView(builder.finish((index,), Pin()))
    (issue,) = root.issues(0)
    evidence = cast("tuple[object, ...]", issue.stored_value)
    assert issue.member == _HOLDER
    assert evidence == ("0a", {"k": "1b"})
    assert isinstance(evidence[1], MappingProxyType)


# --------------------------------------------------------------------------- #
# What still happens per row on the conforming path.                           #
# --------------------------------------------------------------------------- #
_DECLARATION_FIXED: Final = (
    "occurrence_shape",
    "decode_occurrence_classified",
)
"""The codec entries conversion reaches only for a document its compiled read did
not already classify. Each one's work is fixed by the occurrence's declaration,
so reaching any of them once per row is declaration-fixed work scaling with
rows."""

_COUNTED: Final = (*_DECLARATION_FIXED, "admits_stored_scalar")


def _conversion_calls(layout: Layout, owners: int) -> dict[str, int]:
    """How often one whole batch over ``owners`` roots reaches each counted site
    from inside conversion.

    Patched by name on the conversion module alone, so what is counted is the
    calls this seam makes and not the ones the compiled transform makes for
    itself on the way in.
    """
    calls: dict[str, int] = dict.fromkeys(_COUNTED, 0)
    model, reads, rows = _workload(layout, owners)
    validated = query(layout, model.meta)
    plan = read_plan(model, validated)
    with pytest.MonkeyPatch.context() as patched:
        for name in _COUNTED:
            patched.setattr(_convert, name, _counting(name, getattr(_convert, name), calls))
        page = batch(model, validated, plan, StressPort(reads, rows)).page
        for position in range(page.root_count):
            RootView(page, position)
    return calls


def _counting(name: str, site: Any, calls: dict[str, int]) -> Any:
    def counted(*args: object, **kwargs: object) -> object:
        calls[name] += 1
        return site(*args, **kwargs)

    return counted


def _workload(
    layout: Layout, owners: int
) -> tuple[
    CatalogedModel,
    tuple[CompiledRead | None, ...],
    tuple[tuple[Row, ...], ...],
]:
    model = CatalogedModel(metamodel(layout))
    plan = read_plan(model, query(layout, model.meta))
    reads = compiled_levels(layout, plan)
    return model, reads, rows_per_level(layout, model, plan, reads, owners)


def _host_checked_payload_cells(layout: Layout, owners: int) -> int:
    """Non-identity Attribute cells whose storage contract needs a host check."""
    model, reads, rows = _workload(layout, owners)
    total = 0
    seen: set[object] = set()
    for compiled, level_rows in zip(reads, rows, strict=True):
        if compiled is None:
            continue
        for driver in level_rows:
            resolved, _variant, _unknown, _document = compiled.row_identity(driver)
            entity_layout = model.layouts.entity(resolved)
            identity_positions = frozenset(
                (*entity_layout.primary_key, *entity_layout.temporal_starts)
            )
            contracts = compiled.attribute_reads(resolved)
            keys: Sequence[str] = [contract.result_key for contract in contracts]
            occurrence: object = (
                resolved,
                tuple(
                    driver[compiled.result_keys.index(keys[position])]
                    for position in identity_positions
                ),
            )
            if not identity_positions:
                occurrence = id(driver)
            if occurrence in seen:
                continue
            seen.add(occurrence)
            total += sum(
                1
                for position, contract in enumerate(contracts)
                if position not in identity_positions
                and (contract.encoded or contract.temporal_end)
            )
    return total


@pytest.mark.parametrize("layout", LAYOUTS)
def test_the_conforming_path_checks_only_host_checked_payload_positions(
    layout: Layout,
) -> None:
    # Work fixed by a layout, a member declaration, or a Neutral Type does not
    # scale with rows, measured over the report's own workload. Every
    # document a conforming row carries is classified only if its deferred state
    # is reached. The admissions that remain are exactly encoded Columns and
    # temporal ends, so doubling the rows doubles them and nothing else moves.
    one = _conversion_calls(layout, OWNERS)
    twice = _conversion_calls(layout, OWNERS * 2)
    assert [one[site] for site in _DECLARATION_FIXED] == [0, 0]
    assert [twice[site] for site in _DECLARATION_FIXED] == [0, 0]
    assert one["admits_stored_scalar"] == _host_checked_payload_cells(layout, OWNERS)
    assert twice["admits_stored_scalar"] == _host_checked_payload_cells(layout, OWNERS * 2)
