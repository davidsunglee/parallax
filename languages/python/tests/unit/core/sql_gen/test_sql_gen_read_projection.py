"""What a read fetches is its resolved projection, under every read shape.

Each case compiles one read under an explicit internal projection request in
both result forms and grades the statement, its binds and document ordinals,
the selected occurrences, the document mappings, and the flat-row publication
keys. The same reads then deliver stored rows, spelled by the names their
statements select, through binding, conversion, Page judgment, and flat-row
publication, graded by judged members, stored-data issues, the raw shared
document, and the published rows' values and iteration order.

The expectations are authored from the fixtures' declarations: a read selects
every applicable Attribute, the requested Value Objects of its position, and
the Structured Column wherever a fetched member resides in it or the read
observes it. Result form decides only sibling padding and the branch-owned
fields a flat row publishes.

Table-per-hierarchy ``Columns`` layout cannot give two sibling occurrences one
storage spelling, so its ``Right.home`` keeps the Column ``right_home``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, cast

import pytest

from parallax.core import predicate as oa
from parallax.core import storage_layout
from parallax.core.base import PresentDocument
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.sql_gen._inheritance import SingleTableReadPlan, TpcsUnionReadPlan
from tests._support.sql import compile_projected_read, compile_read
from tests.unit import _read_projection_support as support
from tests.unit.core.sql_gen._delivery_support import deliver
from tests.unit.core.sql_gen._plan_reuse_support import assert_planned_once, record_plan_reuse

type _Request = Literal["none", "all", "named"]
type _Form = Literal["row", "instance"]
type _Mapping = dict[str, tuple[list[str], tuple[str, ...]]]

_FORMS: tuple[_Form, ...] = ("row", "instance")
# Each wide field `facet_NN` declares the occurrence `facetNN`, which is also its
# storage spelling.
_FACETS = tuple(name.replace("_", "") for name in support.OCCURRENCES)
_NAMED_FACETS = (_FACETS[3], _FACETS[17])
_SIBLINGS = ("Left", "Right")
_WIDE_METAS = {layout: model_of(support.WIDE_MODELS[layout]) for layout in support.LAYOUTS}


@dataclass(frozen=True, slots=True)
class _Demand:
    request: _Request
    observe: bool

    @property
    def fetches(self) -> bool:
        return self.request != "none"


@dataclass(frozen=True, slots=True)
class _Shape:
    """One read shape: a matrix family read, or the standalone wide read where
    ``strategy`` is absent."""

    kind: Literal["standalone", "concrete", "abstract", "narrowed-one", "narrowed-two"]
    strategy: support.Strategy | None
    layout: support.Layout
    position: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "position",
            {
                "standalone": ("WideHolder",),
                "concrete": ("Left",),
                "abstract": ("Left", "Plain", "Right"),
                "narrowed-one": ("Left",),
                "narrowed-two": ("Left", "Right"),
            }[self.kind],
        )

    @property
    def target(self) -> str:
        if self.strategy is None:
            return "WideHolder"
        return "Left" if self.kind == "concrete" else "Root"

    @property
    def abstract_target(self) -> bool:
        return self.kind in ("abstract", "narrowed-one", "narrowed-two")

    @property
    def union(self) -> bool:
        return self.strategy == "tpcs" and len(self.position) > 1

    def meta(self) -> Metamodel:
        return support.MATRIX_META if self.strategy is not None else _WIDE_METAS[self.layout]

    def entity(self, name: str) -> EntityMetadata:
        if self.strategy is None:
            return next(item for item in self.meta().entities if item.identity.name == name)
        return support.matrix_entity(self.strategy, self.layout, name)

    def compile(self, demand: _Demand, form: _Form) -> CompiledRead:
        named = frozenset(_NAMED_FACETS if self.strategy is None else ("home",))
        narrow_to = (
            tuple(self.entity(name).identity for name in self.position)
            if self.kind.startswith("narrowed")
            else None
        )
        return compile_projected_read(
            oa.TrueNode(),
            self.meta(),
            POSTGRES,
            self.entity(self.target),
            value_objects=named if demand.request == "named" else demand.request,
            observe_structured_document=demand.observe,
            narrow_to=narrow_to,
            result_form=form,
        )


_SHAPES = (
    *(_Shape("standalone", None, layout) for layout in support.LAYOUTS),
    *(
        _Shape(kind, strategy, layout)
        for strategy in support.STRATEGIES
        for layout in support.LAYOUTS
        for kind in ("concrete", "abstract", "narrowed-one", "narrowed-two")
    ),
)
_DEMANDS = tuple(
    _Demand(request, observe) for request in ("none", "all", "named") for observe in (False, True)
)


class _SelectList:
    """One expected select list's cells and the document pairs among them."""

    def __init__(self) -> None:
        self.cells: list[str] = []
        self.document_reads: list[tuple[int, int]] = []

    def scalar(self, cell: str) -> None:
        self.cells.append(cell)

    def document(self, presence: str, value: str) -> None:
        self.document_reads.append((len(self.cells), len(self.cells) + 1))
        self.cells.extend((presence, value))

    def column_document(self, column: str, alias: str | None = None) -> None:
        self.document(
            f"not t0.{column} is null", f"t0.{column}" + ("" if alias is None else f" {alias}")
        )

    def sql(self) -> str:
        return ", ".join(self.cells)


# --------------------------------------------------------------------------- #
# Independent expectations.                                                    #
# --------------------------------------------------------------------------- #
def _wide_fetched(demand: _Demand) -> tuple[str, ...]:
    return {"none": (), "all": _FACETS, "named": _NAMED_FACETS}[demand.request]


def _fetched(shape: _Shape, demand: _Demand) -> list[tuple[str, str]]:
    """The occurrences the read fetches, as (declaring Entity, name), in the
    position's own member order."""
    if shape.strategy is None:
        return [("WideHolder", name) for name in _wide_fetched(demand)]
    origin = [("Root", "origin")] if demand.request == "all" else []
    homes = [(name, "home") for name in _SIBLINGS if demand.fetches and name in shape.position]
    return origin + homes


def _fetched_by(shape: _Shape, demand: _Demand, concrete: str, *, column: bool) -> list[str]:
    """The fetched occurrences ``concrete`` carries by storage spelling; a
    ``column`` spelling distinguishes `Right.home`'s own Column under
    table-per-hierarchy ``Columns`` layout."""
    if shape.strategy is None:
        return list(_wide_fetched(demand))
    names = ["origin"] if demand.request == "all" else []
    if demand.fetches and concrete in _SIBLINGS:
        renamed = column and shape.strategy == "tph" and concrete == "Right"
        names.append("right_home" if renamed else "home")
    return names


def _projects_document(shape: _Shape, demand: _Demand) -> bool:
    """Whether a ``Document``-layout read projects its Structured Column."""
    resident_attribute = "Plain" in shape.position
    return bool(_fetched(shape, demand)) or demand.observe or resident_attribute


def _single_table(shape: _Shape, demand: _Demand) -> tuple[_SelectList, str, tuple[object, ...]]:
    select = _SelectList()
    select.scalar("t0.id")
    binds: tuple[object, ...] = ()
    if shape.strategy is None:
        table = f"wide_holder_{shape.layout}"
    else:
        if shape.strategy == "tph" and shape.abstract_target:
            select.scalar("t0.kind")
        select.scalar("t0.holder_id")
        if shape.layout == "columns":
            select.scalar("encode(t0.digest, ?) digest_hex")
            binds = ("hex",)
            if "Plain" in shape.position:
                select.scalar("t0.note")
                select.column_document("tags")
        table = (
            f"mx_tph_{shape.layout}" if shape.strategy == "tph" else f"mx_tpcs_{shape.layout}_left"
        )
    if shape.layout == "columns":
        columns = dict.fromkeys(
            name
            for concrete in shape.position
            for name in _fetched_by(shape, demand, concrete, column=True)
        )
        for column in columns:
            select.column_document(column)
    elif _projects_document(shape, demand):
        select.column_document("payload")
    guard = ""
    if shape.strategy == "tph" and shape.kind != "abstract":
        tags = tuple(name.lower() for name in shape.position)
        guard = " where t0.kind = ?" if len(tags) == 1 else " where t0.kind in (?, ?)"
        binds = (*binds, *tags)
    return select, f"select {select.sql()} from {table} t0{guard}", binds


def _union(shape: _Shape, demand: _Demand) -> tuple[_SelectList, str, tuple[object, ...]]:
    branches: list[str] = []
    first: _SelectList | None = None
    for concrete in shape.position:
        select = _SelectList()
        select.scalar("t0.id")
        select.scalar("t0.holder_id")
        if shape.layout == "columns":
            # Every branch owns the inherited Bytes Column, so each renders its
            # encoding under the raw spelling the union allocates.
            select.scalar("encode(t0.digest, ?) digest")
            if "Plain" in shape.position:
                select.scalar("t0.note" if concrete == "Plain" else "cast(null as text) note")
                if concrete == "Plain":
                    select.column_document("tags")
                else:
                    select.document("false", "cast(null as jsonb) tags")
            if demand.request == "all":
                select.column_document("origin")
            if demand.fetches:
                for owner, alias in zip(
                    _SIBLINGS, ("parallax_attr_0", "parallax_attr_1"), strict=True
                ):
                    if owner == concrete:
                        select.column_document("home", alias)
                    else:
                        select.document("false", f"cast(null as jsonb) {alias}")
        elif _projects_document(shape, demand):
            select.column_document("payload")
        select.scalar(f"'{concrete}' family_variant")
        branches.append(f"select {select.sql()} from mx_tpcs_{shape.layout}_{concrete.lower()} t0")
        first = first or select
    assert first is not None
    binds = ("hex",) * len(shape.position) if shape.layout == "columns" else ()
    return first, " union all ".join(branches), binds


def _shared(shape: _Shape, demand: _Demand, form: _Form) -> _Mapping | None:
    if shape.layout == "columns" or not _projects_document(shape, demand):
        return None
    members = {
        concrete: (["note", "tags"] if concrete == "Plain" else [])
        + _fetched_by(shape, demand, concrete, column=False)
        for concrete in shape.position
    }
    pads = form == "row" and ((shape.strategy == "tph" and shape.abstract_target) or shape.union)
    padding = tuple(dict.fromkeys(key for keys in members.values() for key in keys)) if pads else ()
    return {concrete: (keys, padding) for concrete, keys in members.items()}


def _direct(shape: _Shape, demand: _Demand) -> dict[str, list[str]] | None:
    if shape.layout == "document":
        return None
    direct = {
        concrete: (["tags"] if concrete == "Plain" else [])
        + _fetched_by(shape, demand, concrete, column=True)
        for concrete in shape.position
    }
    return direct if any(direct.values()) else None


def _published(shape: _Shape, demand: _Demand, concrete: str, form: _Form) -> tuple[str, ...]:
    keys = ["id"]
    if shape.strategy is None:
        if shape.layout == "columns":
            keys.extend(_fetched_by(shape, demand, concrete, column=True))
        return tuple(keys)
    keys.append("holder_id")
    shared = _shared(shape, demand, form)
    if shape.layout == "document":
        if shared is not None:
            keys.extend(shared[concrete][1])
        return tuple(keys)
    if shape.union:
        # A row-form union keeps every alias that spells its own key where the
        # union result placed it, and appends the keys its resolved branch
        # renames to; an instance-form union keeps only that branch's own
        # fields, in result order.
        plain = "Plain" in shape.position and (form == "row" or concrete == "Plain")
        if form == "instance":
            keys.append("digest_hex")
        if plain:
            keys.extend(("note", "tags"))
        fetched = _fetched_by(shape, demand, concrete, column=True)
        keys.extend(name for name in fetched if name != "home")
        if form == "row":
            keys.append("digest_hex")
        keys.extend(name for name in fetched if name == "home")
        return tuple(keys)
    keys.append("digest_hex")
    if "Plain" in shape.position:
        keys.extend(("note", "tags"))
    keys.extend(
        dict.fromkeys(
            name
            for member in shape.position
            for name in _fetched_by(shape, demand, member, column=True)
        )
    )
    return tuple(keys)


# --------------------------------------------------------------------------- #
# Observations.                                                                #
# --------------------------------------------------------------------------- #
def _selected(compiled: CompiledRead) -> list[tuple[str, str]]:
    return [
        (member.identity.entity.name, member.identity.path[-1])
        for member in compiled.projection.value_objects
    ]


def _shared_mapping(compiled: CompiledRead) -> _Mapping | None:
    shared = compiled.result_contract.shared_document
    if shared is None:
        return None
    assert shared.column == "payload"
    return {
        identity.name: ([key for key, _path in fan_out.members], fan_out.padding)
        for identity, fan_out in shared.per_entity
    }


def _direct_mapping(compiled: CompiledRead) -> dict[str, list[str]] | None:
    direct = compiled.result_contract.direct_documents
    if direct is None:
        return None
    return {
        identity.name: [member.storage.name for member in members]
        for identity, members in direct.per_entity
    }


@pytest.mark.parametrize(
    "demand", _DEMANDS, ids=[f"{demand.request}-observe={demand.observe}" for demand in _DEMANDS]
)
@pytest.mark.parametrize(
    "shape",
    _SHAPES,
    ids=[f"{shape.strategy or 'standalone'}-{shape.layout}-{shape.kind}" for shape in _SHAPES],
)
def test_a_read_fetches_its_resolved_demand_whatever_its_result_form(
    shape: _Shape, demand: _Demand
) -> None:
    row, instance = (shape.compile(demand, form) for form in _FORMS)

    assert instance.statement == row.statement
    assert instance.document_reads == row.document_reads
    assert instance.projection == row.projection

    if shape.union:
        select, sql, binds = _union(shape, demand)
    else:
        select, sql, binds = _single_table(shape, demand)
    assert row.statement.sql == sql
    assert row.statement.binds == binds
    assert row.document_reads == tuple(select.document_reads)
    assert _selected(row) == _fetched(shape, demand)
    assert row.projection.observe_structured_document is demand.observe
    assert tuple(identity.name for identity in row.resolved_position) == shape.position

    for form, compiled in zip(_FORMS, (row, instance), strict=True):
        assert _shared_mapping(compiled) == _shared(shape, demand, form)
        assert _direct_mapping(compiled) == _direct(shape, demand)


@pytest.mark.parametrize(
    "demand", _DEMANDS, ids=[f"{demand.request}-observe={demand.observe}" for demand in _DEMANDS]
)
@pytest.mark.parametrize(
    "shape",
    _SHAPES,
    ids=[f"{shape.strategy or 'standalone'}-{shape.layout}-{shape.kind}" for shape in _SHAPES],
)
def test_every_read_shape_is_planned_once_over_its_one_position_layout(
    shape: _Shape, demand: _Demand, monkeypatch: pytest.MonkeyPatch
) -> None:
    reuse = record_plan_reuse(monkeypatch)
    shape.compile(demand, "row")

    planned = assert_planned_once(reuse)
    assert tuple(identity.name for identity in planned.concrete_types) == shape.position
    assert tuple(planned.layout.concrete_entities) == tuple(planned.concrete_types)
    if shape.union:
        assert isinstance(planned, TpcsUnionReadPlan)
        assert [branch.identity for branch in planned.branches] == list(planned.concrete_types)
        assert all(len(branch.columns) == len(planned.columns) for branch in planned.branches)
    else:
        assert isinstance(planned, SingleTableReadPlan)
        guarded = shape.strategy == "tph" and shape.kind != "abstract"
        assert (planned.tag_guard is not None) is guarded
    shared = planned.shared_document
    if shared is not None:
        # Every concrete is keyed by the storage owner's complete resident
        # shape, whatever subset of it the read fetches.
        storage = storage_layout.view(shape.meta())
        assert [identity for identity, _fan_out in shared.per_entity] == list(
            planned.concrete_types
        )
        for identity, fan_out in shared.per_entity:
            physical = storage.entity(identity)
            assert physical is not None
            residents = physical.document_residents
            assert residents is not None
            assert fan_out.shape is residents.shape


@pytest.mark.parametrize("layout", support.LAYOUTS)
def test_an_abstract_target_narrowed_to_one_concrete_still_projects_its_discriminator(
    layout: support.Layout,
) -> None:
    root, left = (support.matrix_entity("tph", layout, name) for name in ("Root", "Left"))
    narrowed = compile_read(
        oa.TrueNode(), support.MATRIX_META, POSTGRES, root, narrow_to=(left.identity,)
    )
    concrete = compile_read(oa.TrueNode(), support.MATRIX_META, POSTGRES, left)

    digest = ", encode(t0.digest, ?) digest_hex" if layout == "columns" else ""
    assert narrowed.statement.sql == (
        f"select t0.id, t0.kind, t0.holder_id{digest} from mx_tph_{layout} t0 where t0.kind = ?"
    )
    assert concrete.statement.sql == (
        f"select t0.id, t0.holder_id{digest} from mx_tph_{layout} t0 where t0.kind = ?"
    )
    binds = ("hex", "left") if layout == "columns" else ("left",)
    assert narrowed.statement.binds == concrete.statement.binds == binds
    assert narrowed.resolved_position == concrete.resolved_position == (left.identity,)


# --------------------------------------------------------------------------- #
# Delivery: the same reads, their rows converted, judged, and published.       #
# --------------------------------------------------------------------------- #
# What each concrete's one stored row holds, by declared member. An occurrence
# is a present object, `None` for SQL NULL in its own Column or a key missing
# from the Structured Column, or `_JSON_NULL` for a present JSON null. The
# `Root` row carries a tag no composed concrete claims.
_JSON_NULL = PresentDocument(None)
_STORED: dict[str, dict[str, object]] = {
    "Left": {
        "id": 1,
        "holder_id": 10,
        "digest": b"\x0a\x0b",
        "origin": {"city": "Rome"},
        "home": None,
    },
    "Plain": {
        "id": 2,
        "holder_id": None,
        "digest": None,
        "note": "memo",
        "tags": ("a", "b"),
        "origin": {"city": "Bern"},
    },
    "Right": {
        "id": 3,
        "holder_id": 30,
        "digest": b"\xff",
        "origin": _JSON_NULL,
        "home": {"city": "Oslo"},
    },
    "Root": {"id": 4, "holder_id": 40, "digest": b"\x00", "origin": None},
}
_UNKNOWN_TAG = "ghost"


def _wide_stored(index: int) -> object:
    """``facetNN``'s stored value in the first wide row; the second stores none."""
    return ({"label": f"f{index}", "rank": index}, None, _JSON_NULL)[index % 3]


def _decoded(stored: object) -> object:
    return None if stored is _JSON_NULL else stored


def _hex(stored: object) -> str | None:
    return None if stored is None else cast("bytes", stored).hex()


def _concretes(shape: _Shape) -> tuple[str, ...]:
    """The concretes whose rows the statement can return: its position, plus an
    unclaimed tag wherever an abstract read carries no tag guard."""
    unguarded = shape.strategy == "tph" and shape.kind == "abstract"
    return (*shape.position, "Root") if unguarded else shape.position


def _occurrence_column(shape: _Shape, concrete: str, name: str) -> str:
    """Where a union or single-table statement selects ``concrete``'s ``name``."""
    if name == "home" and shape.union:
        return {"Left": "parallax_attr_0", "Right": "parallax_attr_1"}[concrete]
    renamed = shape.layout == "columns" and shape.strategy == "tph" and concrete == "Right"
    return "right_home" if name == "home" and renamed else name


def _cells(shape: _Shape, demand: _Demand, concrete: str) -> dict[str, object]:
    """``concrete``'s stored row spelled by the names the statement selects."""
    stored = _STORED[concrete]
    cells: dict[str, object] = {"id": stored["id"], "holder_id": stored["holder_id"]}
    if shape.union:
        cells["family_variant"] = concrete
    elif shape.strategy == "tph" and shape.abstract_target:
        cells["kind"] = _UNKNOWN_TAG if concrete == "Root" else concrete.lower()
    fetched = {name for owner, name in _fetched(shape, demand) if owner in (concrete, "Root")}
    if shape.layout == "columns":
        cells["digest" if shape.union else "digest_hex"] = _hex(stored["digest"])
        if concrete == "Plain":
            cells["note"] = stored["note"]
            cells["tags"] = [*cast("tuple[str, ...]", stored["tags"])]
        for name in sorted(fetched):
            if name in stored:
                cells[_occurrence_column(shape, concrete, name)] = stored[name]
        return cells
    if _projects_document(shape, demand):
        cells["payload"] = _payload(concrete)
    return cells


def _payload(concrete: str) -> dict[str, object]:
    """``concrete``'s stored Structured Column; a member stored as SQL NULL is a
    missing key, and a sibling's unfetched occurrence is stored all the same."""
    stored = _STORED[concrete]
    payload: dict[str, object] = {}
    for name in ("note", "tags", "origin", "home"):
        if name not in stored or stored[name] is None:
            continue
        value = stored[name]
        if isinstance(value, tuple):
            value = [*cast("tuple[str, ...]", value)]
        payload[name] = None if value is _JSON_NULL else value
    return payload


def _wide_cells(shape: _Shape, demand: _Demand, row: int) -> dict[str, object]:
    cells: dict[str, object] = {"id": row + 1}
    fetched = _wide_fetched(demand)
    if shape.layout == "columns":
        for name in fetched:
            cells[name] = _wide_stored(_FACETS.index(name)) if row == 0 else None
        return cells
    if _projects_document(shape, demand):
        cells["payload"] = _wide_payload() if row == 0 else None
    return cells


def _wide_payload() -> dict[str, object]:
    payload: dict[str, object] = {}
    for index, name in enumerate(_FACETS):
        stored = _wide_stored(index)
        if stored is not None:
            payload[name] = None if stored is _JSON_NULL else stored
    return payload


def _delivered_variant(shape: _Shape, concrete: str) -> str | None:
    tagged = shape.strategy == "tph" and shape.abstract_target
    return concrete if concrete != "Root" and (shape.union or tagged) else None


def _members(shape: _Shape, demand: _Demand, concrete: str) -> dict[str, object]:
    """The judged member row by declared name, its absent members omitted."""
    stored = _STORED[concrete]
    members: dict[str, object] = {"id": stored["id"], "holderId": stored["holder_id"]}
    # A row an unclaimed tag resolves to the family root reads each Attribute
    # by its own storage spelling, so the encoded Bytes Column stays absent.
    if shape.layout == "columns" and concrete != "Root":
        members["digest"] = stored["digest"]
    if concrete == "Plain":
        members["note"] = stored["note"]
        members["tags"] = stored["tags"]
    for owner, name in _fetched(shape, demand):
        if owner in (concrete, "Root"):
            members[name] = _decoded(stored.get(name))
    return members


def _published_row(
    shape: _Shape, demand: _Demand, concrete: str, form: _Form
) -> tuple[tuple[str, object], ...]:
    """The flat row a delivered row publishes, in iteration order: its own
    unencoded Attributes and carried occurrences in member order, then its
    encoded Attributes under their encoded keys, then the read's remaining
    publication keys as null padding, then its `familyVariant`."""
    members = _members(shape, demand, concrete)
    published: dict[str, object] = {"id": members["id"], "holder_id": members["holderId"]}
    if concrete == "Plain":
        published["note"] = members["note"]
        published["tags"] = members["tags"]
    for name in ("origin", "home"):
        if name in members:
            spelled = _occurrence_column(shape, concrete, name)
            published[name if spelled.startswith("parallax_attr_") else spelled] = members[name]
    if "digest" in members:
        published["digest_hex"] = _hex(members["digest"])
    # An unclaimed tag's family root has no document fan-out of its own, while
    # a shared table's columns pad it as they pad every concrete.
    padding: tuple[str, ...] = ()
    if concrete != "Root":
        padding = _published(shape, demand, concrete, form)
    elif shape.layout == "columns":
        padding = _published(shape, demand, shape.position[0], form)
    for key in padding:
        published.setdefault(key, None)
    variant = _delivered_variant(shape, concrete)
    if variant is not None:
        published["familyVariant"] = variant
    return tuple(published.items())


def _wide_members(demand: _Demand, row: int) -> dict[str, object]:
    members: dict[str, object] = {"id": row + 1}
    for name in _wide_fetched(demand):
        members[name] = _decoded(_wide_stored(_FACETS.index(name))) if row == 0 else None
    return members


type _Delivered = tuple[
    str, str | None, dict[str, object], tuple[tuple[str, object], ...], object, object
]


def _expected_delivery(shape: _Shape, demand: _Demand, form: _Form) -> list[_Delivered]:
    """Every delivered row as (Entity, variant, members, issues, published items,
    raw shared document)."""
    if shape.strategy is None:
        expected: list[_Delivered] = []
        for row in (0, 1):
            members = _wide_members(demand, row)
            document = (
                (_wide_payload() if row == 0 else None)
                if shape.layout == "document" and _projects_document(shape, demand)
                else None
            )
            expected.append(("WideHolder", None, members, (), tuple(members.items()), document))
        return expected
    return [
        (
            concrete,
            _delivered_variant(shape, concrete),
            _members(shape, demand, concrete),
            (("stored-data-family-tag-unknown", _UNKNOWN_TAG),) if concrete == "Root" else (),
            _published_row(shape, demand, concrete, form),
            _payload(concrete)
            if shape.layout == "document" and _projects_document(shape, demand)
            else None,
        )
        for concrete in _concretes(shape)
    ]


@pytest.mark.parametrize(
    "demand", _DEMANDS, ids=[f"{demand.request}-observe={demand.observe}" for demand in _DEMANDS]
)
@pytest.mark.parametrize(
    "shape",
    _SHAPES,
    ids=[f"{shape.strategy or 'standalone'}-{shape.layout}-{shape.kind}" for shape in _SHAPES],
)
def test_a_read_delivers_its_rows_judged_and_published_in_member_order(
    shape: _Shape, demand: _Demand
) -> None:
    rows = (
        [_wide_cells(shape, demand, row) for row in (0, 1)]
        if shape.strategy is None
        else [_cells(shape, demand, concrete) for concrete in _concretes(shape)]
    )
    for form in _FORMS:
        delivered = deliver(shape.meta(), shape.compile(demand, form), rows)

        assert [
            (row.entity, row.variant, row.members, row.issues, row.published, row.document)
            for row in delivered
        ] == _expected_delivery(shape, demand, form)
