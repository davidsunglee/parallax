"""One compiled read bound once, and what its rows answer (m-snapshot-read).

The production seam a read lane crosses: a compiled read and a cataloged model
bind into a prepared read, and every row of that statement is materialized,
converted, and observed through it. What a row carries into conversion — the
concrete it resolved, the findings the transform raised, the members it already
classified — is the compiled read's own provenance, so every case here drives a
real ``compile_read`` rather than handing conversion a provenance no statement
produced.

Three properties divide the suite. The levels exist before the rows do: a read
whose position is one concrete can still answer a row of a sibling or of the
family root, and the level that row converts under was derived at bind — one per
Entity the read can resolve, all of them before the first row arrives. A
classified member is translated rather than judged again, in each of the states
the transform can leave it in. And the observation reads one row's physical
columns under the same level, including the occurrences only the position's OTHER
concretes ever store at.

Beside them, one cadence claim: over the report's own workload, the work fixed by
a layout, a member declaration, or a Neutral Type no longer happens per row at
all, and what scales with rows is the admission each unclassified stored cell
owes. A cadence cannot be read off a result, so it and the bind-time claim above
are the two here that patch a name inside the seam and count what it reaches,
rather than grading what the seam published.

Conversion itself is graded in `test_snapshot_conversion.py`, which drives
``convert_row`` directly: the positional layout, the absent/null/empty
vocabulary, every leaf type, and the issue each codec finding publishes are
properties of that seam and are stated there.
"""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import pytest

from parallax.core import predicate as oa
from parallax.core.base import (
    SQL_NULL,
    Admission,
    DocumentValue,
    NeutralType,
    PresentDocument,
    admits_stored_scalar,
)
from parallax.core.db_port import MappingRow
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import UNAVAILABLE
from parallax.core.entity._layout import CatalogedModel, LayoutCatalog
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.sql_gen._compile import CompiledRead, MaterializedReadRow
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import EntityStateRow
from parallax.descriptor._records import (
    Attribute,
    DocumentLayout,
    Entity,
    Inheritance,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.snapshot.materialize import (
    PageBuilder,
    RootView,
    StoredDataIssueInput,
    _convert,
    _identity,
)
from parallax.snapshot.materialize._identity import claim_identity
from parallax.snapshot.materialize._page import ABSENT, page_rows
from parallax.snapshot.materialize._prepared import PreparedRead, bind
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import formed, target
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._snapshot_materialization_support import (
    LAYOUTS,
    OWNERS,
    Layout,
    batch,
    compiled_levels,
    fetch_plan,
    metamodel,
    prepared_levels,
    query,
    rows_per_level,
)
from tests.unit.snapshot._snapshot_graph_support import rendered_members

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
    register = Entity(
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
            ValueObject(
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
    root = Entity(
        name="Beast",
        table="beast",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    wolf = Entity(
        name="Wolf",
        inheritance=Inheritance(role="concrete-subtype", parent="Beast", tag_value="wolf"),
        attributes=(Attribute(name="howl", type="string", column="howl", nullable=True),),
    )
    return formed(DescriptorMetamodel(entities=(root, wolf)))


def _craft_family() -> Metamodel:
    """A table-per-hierarchy family whose two concretes each declare one
    occurrence, in the two multiplicities — the shape a polymorphic position
    observes its own concrete's occurrence and its siblings' alike."""
    root = Entity(
        name="Craft",
        table="craft",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    tug = Entity(
        name="Tug",
        inheritance=Inheritance(role="concrete-subtype", parent="Craft", tag_value="tug"),
        value_objects=(
            ValueObject(
                name="berth",
                column="berth",
                nullable=True,
                attributes=(ValueObjectAttribute(name="quay", type="string"),),
            ),
        ),
    )
    barge = Entity(
        name="Barge",
        inheritance=Inheritance(role="concrete-subtype", parent="Craft", tag_value="barge"),
        value_objects=(
            ValueObject(
                name="decks",
                column="decks",
                multiplicity="many",
                attributes=(ValueObjectAttribute(name="label", type="string"),),
            ),
        ),
    )
    return formed(DescriptorMetamodel(entities=(root, tug, barge)))


def _encoded_identity_model() -> Metamodel:
    encoded = Entity(
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


def _prepared(
    model: Metamodel, name: str, *, narrow_to: tuple[str, ...] = ()
) -> PreparedRead[MaterializedReadRow]:
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


def _converted(
    prepared: PreparedRead[MaterializedReadRow], stored: Mapping[str, object]
) -> _Converted:
    """One stored row through the whole prepared seam: materialize, convert, seal."""
    row = prepared.materialize(stored)
    builder = PageBuilder(ViewSchema.of())
    index = prepared.convert(row, builder, source=ROOT_LEVEL)
    page = builder.finish((index,), Pin())
    rows = page_rows(page)
    layout = rows.layouts[index]
    root = RootView(page)
    values = rows.member_rows[index] if root.roots == (None,) else root.member_values(0)
    issues = root.invalid_roots[0].issues if root.roots == (None,) else root.issues(0)
    return _Converted(layout.concrete, rendered_members(layout, values), issues)


def _observed(
    prepared: PreparedRead[MaterializedReadRow], stored: Mapping[str, object]
) -> dict[str, object]:
    """One stored row's shared Entity State viewed under physical storage keys."""
    materialized = prepared.materialize(stored)
    builder = PageBuilder(ViewSchema.of())
    index = prepared.convert(materialized, builder, source=ROOT_LEVEL)
    page = builder.finish((index,), Pin())
    rows = page_rows(page)
    root = RootView(page)
    return dict(
        EntityStateRow.over_members(rows.layouts[index], root.member_values(0), absent=ABSENT)
    )


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
def _recording_levels(patched: pytest.MonkeyPatch, derived: list[EntityIdentity]) -> None:
    """Record the exact Entity of every level the prepared seam builds, in build
    order.

    Patched on the name :func:`bind` and the per-row path both read, so a level
    built anywhere in that seam is recorded — including one built on the row that
    first reached an Entity.
    """
    level_context = _convert.LevelContext

    def recording(*args: Any, **kwargs: Any) -> Any:
        level = level_context(*args, **kwargs)
        derived.append(level.concrete_entity)
        return level

    patched.setattr("parallax.snapshot.materialize._prepared.LevelContext", recording)


def test_binding_derives_every_resolvable_level_and_no_row_derives_another() -> None:
    # A level belongs to the compiled read, so all of them exist the moment bind
    # returns: one per Entity the read can resolve, and none built afterwards.
    # The narrowed family read is where the two halves are distinguishable — its
    # position is one concrete while its rows can resolve to the whole family —
    # and converting a row of the position and a row outside it adds nothing,
    # which a level derived on first reach could not do.
    compiled = _compiled(ANIMAL, "Animal", narrow_to=("Dog",))
    derived: list[EntityIdentity] = []
    with pytest.MonkeyPatch.context() as patched:
        _recording_levels(patched, derived)
        prepared = bind(CatalogedModel(ANIMAL), compiled)
        at_bind = tuple(derived)
        rex = _converted(
            prepared,
            {"id": 1, "kind": "dog", "name": "Rex", "owner_id": 10, "bark_volume": 3},
        )
        boar = _converted(
            prepared,
            {"id": 2, "kind": "boar", "name": "Bo", "owner_id": 10, "tusk_length": None},
        )
    assert set(at_bind) == set(compiled.resolvable)
    assert len(at_bind) == len(set(compiled.resolvable))
    assert {identity.name for identity in at_bind} >= {"Dog", "WildBoar"}
    assert (rex.concrete.name, boar.concrete.name) == ("Dog", "WildBoar")
    assert tuple(derived) == at_bind


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


def test_an_unknown_tag_and_a_null_key_both_reach_the_projection() -> None:
    # The tag verdict the transform handed over and the judgment conversion makes
    # itself are two issues on one projection, the transform's first: a row whose
    # tag named no composed concrete AND whose key column is null publishes both.
    prepared = _prepared(BEAST, "Beast")
    node = _converted(prepared, {"id": None, "kind": "bear", "howl": None})
    assert [issue.code for issue in node.issues] == [
        "stored-data-family-tag-unknown",
        "stored-data-primary-key-null",
    ]


# --------------------------------------------------------------------------- #
# A classified member is translated, never judged a second time.               #
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


def test_identity_cells_are_admitted_once_before_payload_judgment() -> None:
    # The count is the claim, and no result can carry it: a re-admission agreeing
    # with the classification is invisible in the converted row. So the rule is
    # replaced for this conversion and its arguments recorded — a document-layout
    # row must reach it for its direct key Column and for nothing else, however
    # many members the document carried.
    identity_admitted: list[object] = []
    payload_admitted: list[object] = []

    def _record(
        value: object, declared: NeutralType, *, nullable: bool, temporal_end: bool
    ) -> Admission:
        identity_admitted.append(value)
        return admits_stored_scalar(value, declared, nullable=nullable, temporal_end=temporal_end)

    def _payload_record(
        value: object, declared: NeutralType, *, nullable: bool, temporal_end: bool
    ) -> Admission:
        payload_admitted.append(value)
        return admits_stored_scalar(value, declared, nullable=nullable, temporal_end=temporal_end)

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(_identity, "admits_stored_scalar", _record)
        patched.setattr(_convert, "admits_stored_scalar", _payload_record)
        node = _register(_ADA)
    assert identity_admitted == [1]
    assert payload_admitted == []
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
    compiled = _compiled(ENCODED_IDENTITY, "EncodedIdentity")
    identity = target(ENCODED_IDENTITY, "EncodedIdentity").identity
    layout = LayoutCatalog(ENCODED_IDENTITY).entity(identity)
    contracts = compiled.attribute_reads(identity)
    level = _convert.LevelContext(layout, attribute_reads=contracts)
    claim = claim_identity({contracts[0].result_key: raw}, level)

    assert (None if claim.key is None else claim.key.primary_key) == key
    assert [finding.code for finding in claim.findings] == ([] if issue is None else [issue])


def test_a_classified_unavailable_identity_never_forms_a_logical_key() -> None:
    compiled = _compiled(ENCODED_IDENTITY, "EncodedIdentity")
    identity = target(ENCODED_IDENTITY, "EncodedIdentity").identity
    layout = LayoutCatalog(ENCODED_IDENTITY).entity(identity)
    contracts = compiled.attribute_reads(identity)
    key = contracts[0].result_key

    claim = claim_identity(
        {key: UNAVAILABLE},
        _convert.LevelContext(layout, attribute_reads=contracts),
        classified_members=frozenset({key}),
    )

    assert claim.key is None
    assert [finding.code for finding in claim.findings] == ["stored-data-primary-key-undecodable"]


def test_sql_null_in_a_nullable_encoded_column_bypasses_wire_decoding() -> None:
    compiled = _compiled(ENCODED_IDENTITY, "EncodedIdentity")
    identity = target(ENCODED_IDENTITY, "EncodedIdentity").identity
    contracts = compiled.attribute_reads(identity)
    stored = {
        contract.result_key: "0a1b" if contract.attribute.identity.name == "id" else None
        for contract in contracts
    }
    node = _converted(bind(CatalogedModel(ENCODED_IDENTITY), compiled), stored)

    assert node.members == {"id": b"\x0a\x1b", "token": None}
    assert node.issues == ()


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


# --------------------------------------------------------------------------- #
# What still happens per row on the conforming path.                           #
# --------------------------------------------------------------------------- #
_DECLARATION_FIXED: Final = (
    "occurrence_shape",
    "decode_occurrence_classified",
    "reduce_declared_members_classified",
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
    model, plan, reads, rows = _workload(layout, owners)
    with pytest.MonkeyPatch.context() as patched:
        for name in _COUNTED:
            patched.setattr(_convert, name, _counting(name, getattr(_convert, name), calls))
        page = batch(model, plan, prepared_levels(model, reads), rows)
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
    Any,
    tuple[CompiledRead | None, ...],
    tuple[tuple[MappingRow, ...], ...],
]:
    meta = metamodel(layout)
    model = CatalogedModel(meta)
    plan = fetch_plan(query(layout, meta), meta)
    reads = compiled_levels(layout, plan, meta)
    return model, plan, reads, rows_per_level(layout, model, plan, reads, owners)


def _payload_cells_judged(layout: Layout, owners: int) -> int:
    """Non-identity Attribute cells the batch carries without prior classification.

    Identity positions are admitted while claims are formed; every remaining
    unclassified cell is admitted exactly once when its Entity State is judged.
    """
    model, _plan, reads, rows = _workload(layout, owners)
    prepared = prepared_levels(model, reads)
    total = 0
    seen: set[object] = set()
    for prepared_read, level_rows in zip(prepared, rows, strict=True):
        if prepared_read is None:
            continue
        for driver in level_rows:
            row = prepared_read.materialize(driver)
            level = prepared_read._level(row)  # pyright: ignore[reportPrivateUsage] - derives the prepared seam's own cadence contract
            claim = claim_identity(
                row.values,
                level,
                unknown_family_tag=row.unknown_family_tag,
                classified_members=row.classified_members,
            )
            occurrence = claim.key if claim.key is not None else (id(row),)
            if occurrence in seen:
                continue
            seen.add(occurrence)
            entity_layout = level.layout
            identity_positions = frozenset(
                (*entity_layout.primary_key, *entity_layout.temporal_starts)
            )
            contracts = level.attribute_reads
            keys: Sequence[str] = (
                [contract.result_key for contract in contracts]
                if contracts
                else [
                    attribute.storage.name
                    for attribute in model.layouts.entity(row.resolved_entity).attributes
                ]
            )
            total += sum(
                1
                for position, key in enumerate(keys)
                if position not in identity_positions
                and key in row.values
                and key not in row.classified_members
            )
    return total


@pytest.mark.parametrize("layout", LAYOUTS)
def test_the_conforming_path_decodes_no_declaration_and_admits_nothing_twice(
    layout: Layout,
) -> None:
    # Work fixed by a layout, a member declaration, or a Neutral Type does not
    # scale with rows, measured over the report's own workload. Every
    # document a conforming row carries reaches conversion already classified, so
    # conversion asks the codec for none of them at either batch size — and the
    # admissions that remain are exactly the stored cells no transform classified,
    # so doubling the rows doubles them and nothing else moves.
    one = _conversion_calls(layout, OWNERS)
    twice = _conversion_calls(layout, OWNERS * 2)
    assert [one[site] for site in _DECLARATION_FIXED] == [0, 0, 0]
    assert [twice[site] for site in _DECLARATION_FIXED] == [0, 0, 0]
    assert one["admits_stored_scalar"] == _payload_cells_judged(layout, OWNERS)
    assert twice["admits_stored_scalar"] == _payload_cells_judged(layout, OWNERS * 2)
