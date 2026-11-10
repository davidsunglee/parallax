from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

import pytest

from parallax.conformance import case_format, workloads
from parallax.conformance.budget import BudgetContract
from parallax.conformance.story_models import ACCOUNT_MODEL, ORDERS_MODEL, Order
from parallax.conformance.workloads import (
    ANCESTOR_LEVEL_IDS,
    GEOMETRY_LEVELS,
    SCALAR_CONTROL_TYPE_ID,
    SCALAR_TYPE_IDS,
    SCALAR_TYPE_LEVEL_ID,
    SCALAR_TYPE_RUNTIMES,
    GeometryLevel,
    Workload,
    ancestor_levels,
    canonical_source,
    catalog,
    plan_levels,
    scalar_type_digest,
    scalar_type_level,
    scalar_type_runtimes,
    structural_digest,
    workload_digest,
)
from parallax.core import inheritance, read_planning
from parallax.core._execution._read_query import resolve_read_query
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.sql_gen._compile import compile_read, compile_template


def test_every_workload_loads_and_compiles_its_query_and_delivery_sizes() -> None:
    for workload in catalog().values():
        assert workload.model.entity(workload.query.target) is not None
        assert workload.page_sizes == tuple(sorted(set(workload.page_sizes)))
        validated = resolve_read_query(workload.query, model=workload.model)
        plan = read_planning.plan(
            validated,
            workload.model,
            projection=read_planning.ReadProjectionRequest("all", True),
        )
        compile_read(plan.root, workload.model, POSTGRES, result_form="instance")
        for step in plan.fetch_steps:
            if isinstance(step, read_planning.BackReferenceFetchStep):
                continue
            compile_template(step.query, workload.model, POSTGRES, result_form="instance").render(
                [0]
            )


def test_generated_workloads_preserve_the_fixture_scale_and_fanout() -> None:
    for workload in catalog().values():
        rows = workload.rows(workload.roots)
        assert rows.roots == workload.roots
        assert rows.fanout == workload.fanout
        assert len(rows.entity(rows.root_entity)) == workload.roots


class _MissingInheritance:
    def entity(self, identity: EntityIdentity) -> None:
        return None


def test_class_backed_consumer_must_match_the_complete_fixture_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workload = catalog()["conventional-fanout"]
    workload.validate_class_backed(ORDERS_MODEL, Order.where(Order.all).include(Order.items))
    with pytest.raises(ValueError, match="class-backed query differs"):
        workload.validate_class_backed(ORDERS_MODEL, Order.where(Order.active == True))  # noqa: E712
    with pytest.raises(ValueError, match="class-backed metadata differs"):
        workload.validate_class_backed(ACCOUNT_MODEL)
    descriptor_view = inheritance.inheritance_facet_of(workload.model)
    views = iter((_MissingInheritance(), descriptor_view))

    def next_view(_model: Metamodel) -> Any:
        return next(views)

    monkeypatch.setattr(inheritance, "inheritance_facet_of", next_view)
    with pytest.raises(ValueError, match="class-backed facets differ"):
        workload.validate_class_backed(ORDERS_MODEL)


def test_workload_digest_covers_the_catalog_inputs() -> None:
    digest = workload_digest()
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    assert workload_digest(catalog()) == digest


def _edited_digest(workload_id: str, source: str, edit: Callable[[str], str]) -> str:
    workload = catalog()[workload_id]
    edited = workload.fixture_path if source == "fixture" else workload.model_path

    def read(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        return edit(text) if path == edited else text

    return workload_digest(read=read)


def _commented(text: str) -> str:
    return f"# a comment no workload reads\n{text}"


def _replaced(old: str, new: str) -> Callable[[str], str]:
    def edit(text: str) -> str:
        assert old in text
        return text.replace(old, new, 1)

    return edit


@pytest.mark.parametrize(
    ("source", "edit"),
    [
        ("fixture", _commented),
        ("fixture", _replaced("tags: [m-perf-bench, stream]", "tags: [m-perf-bench]")),
        ("fixture", _replaced("tags:", "unmeasured: fixture metadata\ntags:")),
        ("fixture", _replaced('predicate: { "true": {} }', 'predicate: {"true": {}}')),
        ("model", _commented),
    ],
    ids=[
        "comment",
        "tags",
        "unmeasured-key",
        "format",
        "model-comment",
    ],
)
def test_workload_digest_ignores_what_no_workload_measures(
    source: str, edit: Callable[[str], str]
) -> None:
    assert _edited_digest("conventional-fanout", source, edit) == workload_digest()


@pytest.mark.parametrize(
    ("source", "edit"),
    [
        ("fixture", _replaced("    rows: 200", "    rows: 201")),
        ("fixture", _replaced("pageSizes: [1, 32, 128]", "pageSizes: [1, 32]")),
        ("fixture", _replaced("rel: parallax.compatibility.Order.items", "rel: other")),
        ("fixture", _replaced("model: models/orders.yaml", "model: models/account.yaml")),
        ("model", _replaced("  - name: OrderItem", "  - name: LineItem")),
    ],
    ids=["dataset", "delivery", "object-query", "model-reference", "model-content"],
)
def test_workload_digest_moves_with_every_measured_input(
    source: str, edit: Callable[[str], str]
) -> None:
    assert _edited_digest("conventional-fanout", source, edit) != workload_digest()


_ORDER_ID = "parallax.compatibility.Order.id"


@pytest.mark.parametrize(
    ("authored", "changed"),
    [("9007199254740992.0", "9007199254740993.0"), ("0", "1" * 5000)],
    ids=["beyond-float-precision", "beyond-int-digit-limit"],
)
def test_workload_digest_distinguishes_numbers_the_host_spells_alike(
    authored: str, changed: str
) -> None:
    def keyed(literal: str) -> str:
        return _edited_digest(
            "conventional-fanout",
            "fixture",
            _replaced(
                'predicate: { "true": {} }',
                f"predicate: {{ eq: {{ path: {_ORDER_ID}, value: {literal} }} }}",
            ),
        )

    assert keyed(authored) != keyed(changed)


def test_a_workload_holds_only_its_fixtures_measured_sections() -> None:
    for workload in catalog().values():
        authored = case_format.safe_load_yaml(workload.fixture_path.read_text(encoding="utf-8"))
        assert isinstance(authored, Mapping)
        assert "tags" in authored
        assert set(workload.document) == {"model", "objectQuery", "dataset", "delivery"}
    with pytest.raises(ValueError, match="tags are not measured sections"):
        _workload({"tags": []})


def test_workload_digest_changes_with_the_generated_key_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = workload_digest()
    monkeypatch.setattr(workloads, "_GENERATED_KEY_OFFSET", 512)
    assert workload_digest() != original


def test_structural_families_vary_one_dimension_from_a_shallow_baseline() -> None:
    baseline = GEOMETRY_LEVELS[0]
    assert (baseline.depth, baseline.many, baseline.width, baseline.populated) == (1, 2, 4, 4)
    assert len({level.id for level in GEOMETRY_LEVELS}) == len(GEOMETRY_LEVELS)
    for level in GEOMETRY_LEVELS[1:]:
        varied = {
            name
            for name in ("depth", "many", "width")
            if getattr(level, name) != getattr(baseline, name)
        }
        assert len(varied) <= 1, level
        assert level.populated == level.width or level.family == "sparsity", level
    assert {level.family for level in GEOMETRY_LEVELS} == {"depth", "many", "width", "sparsity"}


def test_structural_levels_refuse_impossible_geometry() -> None:
    with pytest.raises(ValueError, match="depth and width are positive"):
        GeometryLevel("bad", "depth", depth=0, many=0, width=1, populated=1)
    with pytest.raises(ValueError, match="cannot exceed the declared width"):
        GeometryLevel("bad", "width", depth=1, many=0, width=2, populated=3)


def test_the_changed_ancestor_levels_name_geometries_that_vary_only_in_width() -> None:
    levels = ancestor_levels()
    assert tuple(level.id for level in levels) == ANCESTOR_LEVEL_IDS
    assert {level.depth for level in levels} == {1}
    assert {level.width for level in levels} == {4, 16, 64}
    assert {level.width for level in levels if level.populated < level.width} == {64}


def test_the_workload_digest_covers_the_structural_families(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = workload_digest()
    structural = structural_digest()
    assert len(structural) == 64
    monkeypatch.setattr(workloads, "READ_GEOMETRY_ROOTS", workloads.READ_GEOMETRY_ROOTS + 1)
    assert structural_digest() != structural
    assert workload_digest() != original


def test_the_workload_digest_covers_the_changed_ancestor_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = workload_digest()
    monkeypatch.setattr(workloads, "ANCESTOR_LEVEL_IDS", ANCESTOR_LEVEL_IDS[:-1])
    assert workload_digest() != original


def test_the_scalar_types_are_measured_at_one_frozen_level_against_their_control() -> None:
    assert len(set(SCALAR_TYPE_IDS)) == len(SCALAR_TYPE_IDS)
    assert SCALAR_CONTROL_TYPE_ID not in SCALAR_TYPE_IDS
    level = scalar_type_level()
    assert level.id == SCALAR_TYPE_LEVEL_ID
    assert (level.depth, level.populated) == (1, level.width)


def test_the_scalar_types_are_measured_on_the_newest_supported_minor_alone() -> None:
    assert SCALAR_TYPE_RUNTIMES == 1
    assert scalar_type_runtimes(("3.13", "3.14")) == ("3.14",)
    assert scalar_type_runtimes(("3.14", "3.9", "3.13")) == ("3.14",)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SCALAR_TYPE_IDS", ("float64", "float32")),
        ("SCALAR_CONTROL_TYPE_ID", "bytes"),
        ("SCALAR_TYPE_LEVEL_ID", "width-16"),
        ("SCALAR_TYPE_RUNTIMES", 2),
    ],
)
def test_the_workload_digest_covers_the_scalar_type_manifest_apart_from_the_structural_one(
    monkeypatch: pytest.MonkeyPatch, name: str, value: object
) -> None:
    original = workload_digest()
    scalar_types = scalar_type_digest()
    structural = structural_digest()
    monkeypatch.setattr(workloads, name, value)
    assert scalar_type_digest() != scalar_types
    assert workload_digest() != original
    assert structural_digest() == structural


@pytest.mark.parametrize("roots", BudgetContract.load().memory_scaling_root_counts)
def test_generated_scaling_root_counts_use_uncached_keys_without_changing_row_payloads(
    roots: int,
) -> None:
    for workload in catalog().values():
        rows = workload.rows(roots)
        for entity_rows in rows.entities.values():
            for row in entity_rows:
                for name, value in row.items():
                    if name == "id" or name.endswith("Id"):
                        assert isinstance(value, int) and value > 256, (workload.id, name, value)
    orders = catalog()["conventional-fanout"].rows(roots)
    assert orders.entity("parallax.compatibility.Order")[0]["name"] == "order-000001"
    travelers = catalog()["document-heavy"].rows(roots)
    traveler_rows = travelers.entity("parallax.compatibility.Traveler")
    trips = travelers.entity("parallax.compatibility.Trip")
    assert traveler_rows[0]["score"] == 1
    assert trips[0]["travelerId"] == traveler_rows[0]["id"]
    assert trips[-1]["travelerId"] == traveler_rows[-1]["id"]


def test_orders_tree_rows_are_lazy_sequences_with_exact_relationship_keys() -> None:
    rows = catalog()["conventional-fanout"].rows(3)
    orders = rows.entity("parallax.compatibility.Order")
    items = rows.entity("parallax.compatibility.OrderItem")
    statuses = rows.entity("parallax.compatibility.OrderStatus")
    assert orders[-1]["id"] == 259
    assert [row["id"] for row in orders[1:3]] == [258, 259]
    assert items[5]["orderId"] == 258
    assert statuses[25]["orderId"] == 258
    assert statuses[25]["orderItemId"] == 262
    assert len(tuple(statuses)) == 75
    assert rows.entity("missing") == ()
    with pytest.raises(IndexError):
        _ = orders[3]


def _workload(document: Mapping[str, object]) -> Workload:
    fixture = (
        case_format.find_repo_root() / "core" / "compatibility" / "benchmarks" / "synthetic.yaml"
    )
    return Workload("synthetic", fixture, document)


class _Provisioner:
    def __init__(self) -> None:
        self.rows: Mapping[str, object] | None = None

    def reset(self, model: Metamodel, fixtures: Mapping[str, object]) -> None:
        assert any(
            entity.identity.canonical == "parallax.compatibility.Order" for entity in model.entities
        )
        self.rows = fixtures


def test_inline_rows_can_be_scaled_down_and_provisioned() -> None:
    workload = _workload(
        {
            "model": "models/orders.yaml",
            "dataset": {"rows": {"parallax.compatibility.Order": [{"id": 1}]}},
            "objectQuery": {"target": "parallax.compatibility.Order", "predicate": {"true": {}}},
            "delivery": {"pageSizes": [1]},
        }
    )
    rows = workload.rows(1)
    assert rows.entity(rows.root_entity) == ({"id": 1},)
    provisioner = _Provisioner()
    workload.provision(provisioner, 1)
    assert provisioner.rows is not None
    with pytest.raises(ValueError, match="inline dataset has only 1 roots"):
        workload.rows(2)


def test_workload_reports_malformed_fixture_members() -> None:
    with pytest.raises(ValueError, match="positive built-in int"):
        catalog()["conventional-fanout"].rows(0)
    with pytest.raises(ValueError, match="pageSizes is not an array"):
        _ = _workload({"delivery": "bad"}).page_sizes
    with pytest.raises(ValueError, match="positive integers"):
        _ = _workload({"delivery": {"pageSizes": [0]}}).page_sizes
    with pytest.raises(ValueError, match="model is not a string"):
        _ = _workload({}).model_path
    with pytest.raises(ValueError, match="objectQuery is not a mapping"):
        _ = _workload({}).query
    with pytest.raises(ValueError, match="dataset is not a mapping"):
        _workload({}).rows(1)
    with pytest.raises(ValueError, match="dataset is not a mapping"):
        _ = _workload({}).roots
    with pytest.raises(ValueError, match="malformed generated dataset"):
        _workload({"dataset": {"generate": {}}}).rows(1)
    with pytest.raises(ValueError, match=r"dataset\.generate is not a mapping"):
        _ = _workload({"dataset": {}}).roots
    with pytest.raises(ValueError, match=r"generate\.rows must be positive"):
        _ = _workload({"dataset": {"generate": {"rows": 0}}}).roots
    with pytest.raises(ValueError, match=r"generate\.fanout must be positive"):
        _ = _workload({"dataset": {"generate": {"fanout": 0}}}).fanout
    with pytest.raises(ValueError, match="dataset has no rows or generator"):
        _workload({"dataset": {}}).rows(1)
    with pytest.raises(ValueError, match="unknown benchmark dataset recipe"):
        _workload({"dataset": {"generate": {"recipe": "unknown"}}}).rows(1)


def test_catalog_rejects_a_fixture_that_is_not_a_mapping(tmp_path: Path) -> None:
    contract_path = tmp_path / "a" / "b" / "c" / "contract.yaml"
    fixture = tmp_path / "core" / "compatibility" / "bad.yaml"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("[]", encoding="utf-8")
    contract = BudgetContract(
        contract_path,
        1,
        {},
        {},
        {"bad": {"fixture": "bad.yaml"}},
        "a",
        b"authored",
    )
    with pytest.raises(ValueError, match="benchmark fixture is not a mapping"):
        catalog(contract)


def test_catalog_rejects_duplicate_fixture_ownership(tmp_path: Path) -> None:
    contract_path = tmp_path / "a" / "b" / "c" / "contract.yaml"
    fixture = tmp_path / "core" / "compatibility" / "shared.yaml"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}", encoding="utf-8")
    contract = BudgetContract(
        contract_path,
        1,
        {},
        {},
        {
            "first": {"fixture": "shared.yaml"},
            "second": {"fixture": "shared.yaml"},
        },
        "a",
        b"authored",
    )
    with pytest.raises(
        ValueError,
        match="workloads 'first' and 'second' both own",
    ):
        catalog(contract)


def test_the_plan_levels_are_a_frozen_structural_selection_in_the_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    levels = plan_levels()
    assert [level.id for level in levels] == list(workloads.PLAN_LEVEL_IDS)
    assert all(level in GEOMETRY_LEVELS for level in levels)
    assert {level.family for level in levels} == {"depth", "width"}
    original = structural_digest()
    monkeypatch.setattr(workloads, "PLAN_LEVEL_IDS", ("depth-1",))
    assert structural_digest() != original
    assert [level.id for level in plan_levels()] == ["depth-1"]


def test_live_history_and_query_coordinates_belong_to_the_workload_digest() -> None:
    def read(path: Path) -> str:
        text = path.read_text()
        return (
            text.replace("dt.datetime(2024, 5, 1", "dt.datetime(2024, 8, 1")
            if path.name == "live_read_workloads.py"
            else text
        )

    assert workload_digest(read=read) != workload_digest()


def _live_source_edited(edit: Callable[[str], str]) -> str:
    def read(path: Path) -> str:
        text = path.read_text()
        return edit(text) if path.name == "live_read_workloads.py" else text

    return workload_digest(read=read)


def _appended(addition: str) -> Callable[[str], str]:
    def edit(text: str) -> str:
        return text + addition

    return edit


@pytest.mark.parametrize(
    "edit",
    [
        _appended("\nimport os.path\nfrom collections import abc\n"),
        _replaced("import datetime as dt\n", "import datetime as dt  # time\n\n"),
        _appended('\n"""Revised trailing prose."""\n'),
    ],
    ids=["imports", "formatting", "prose"],
)
def test_the_live_read_source_enters_the_workload_digest_as_executable_syntax(
    edit: Callable[[str], str],
) -> None:
    assert _live_source_edited(edit) == workload_digest()


_EXECUTABLE: Final = """\
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["VALUE", "measured"]

VALUE = "operational"


def measured(values: Sequence[int]) -> int:
    \"\"\"Measured prose.\"\"\"
    from math import fsum

    return int(fsum(values))


def digest() -> str:
    return hashlib.sha256(VALUE.encode()).hexdigest()
"""


@pytest.mark.parametrize(
    "edited",
    [
        _EXECUTABLE.replace("import hashlib\n", "import hashlib as hashing\nimport json\n"),
        _EXECUTABLE.replace("    from math import fsum\n", "    from math import fsum, prod\n"),
        _EXECUTABLE.replace("    from collections.abc import Sequence\n", "    import typing\n"),
        _EXECUTABLE.replace('"""Measured prose."""', '"""Revised prose."""'),
        _EXECUTABLE.replace(
            'VALUE = "operational"\n', '"Prose."\nVALUE = (\n    "operational"\n)\n'
        ),
        "# A comment.\n" + _EXECUTABLE.replace("\n\n\n", "\n\n"),
    ],
    ids=["moved-import", "local-import", "type-only-import", "docstring", "layout", "comments"],
)
def test_canonical_source_ignores_imports_prose_and_positions(edited: str) -> None:
    assert canonical_source(edited) == canonical_source(_EXECUTABLE)


@pytest.mark.parametrize(
    "edited",
    [
        _EXECUTABLE.replace('VALUE = "operational"', 'VALUE = "changed"'),
        _EXECUTABLE.replace('"measured"]', '"renamed"]'),
        _EXECUTABLE.replace("int(fsum(values))", "round(fsum(values))"),
        _EXECUTABLE.replace("def measured(values", "def renamed(values"),
        _EXECUTABLE + "\nTRAILING = 1\n",
    ],
    ids=["literal", "export-string", "call", "name", "statement"],
)
def test_canonical_source_retains_every_executable_statement(edited: str) -> None:
    assert canonical_source(edited) != canonical_source(_EXECUTABLE)


def test_canonical_source_omits_only_the_named_top_level_functions() -> None:
    omitted = frozenset({"digest"})
    revised = _EXECUTABLE.replace("VALUE.encode()", "b'other'")
    assert canonical_source(revised, omit_functions=omitted) == canonical_source(
        _EXECUTABLE, omit_functions=omitted
    )
    assert canonical_source(revised) != canonical_source(_EXECUTABLE)
    nested = _EXECUTABLE.replace("    from math import fsum\n", "    def digest() -> None: ...\n")
    revised_nested = nested.replace("def digest() -> None: ...", "def digest() -> int: ...")
    assert canonical_source(revised_nested, omit_functions=omitted) != canonical_source(
        nested, omit_functions=omitted
    )
