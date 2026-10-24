from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pytest

import write_lowering_overhead as report
from durations import Spans
from interpreter_matrix import CURRENT_MINOR, IDENTITY_SCRIPT, supported_minors
from parallax.conformance import workloads
from parallax.conformance.budget import BudgetContract, derive_memory_gates
from parallax.conformance.cost_envelope import validate
from parallax.core._execution._unit_work.ranges import RangeBindings
from parallax.core._execution._unit_work.source_authority import SourceAuthority
from parallax.core._execution._unit_work.write_planner import WritePlanner
from parallax.core._execution._write_step_executor import WriteStepExecutor
from parallax.core.base import INFINITY, detach_json_container
from parallax.core.db_port import (
    CanonicalWriteStatement,
    DocumentReadOrdinals,
    JsonDocument,
    OrderedWriteResult,
    OrderedWriteResultComplete,
    Row,
)
from tests.unit import _leaf_type_support as leaf_support
from tests.unit import _write_lowering_support as lowering_support
from tests.unit.tools._provenance_support import pin_dirty_tree

_CATEGORICAL_OPERATIONS = {
    "txtime": ("opening", "changed", "unchanged"),
    "plain": ("changed",),
    "bitemporal": ("interior",),
}


def _samples(metric: str) -> list[float]:
    if metric.endswith("elapsedUs"):
        return [10.0, 12.0, 11.0] * 3
    return [100.0] * report.MEASURED if report.samples_expected(metric) > 1 else [50.0]


def _child_document(case: str, overrides: Mapping[str, object] | None = None) -> dict[str, object]:
    window = report.WINDOWS[case]
    document: dict[str, object] = {
        "case": case,
        "window": window,
        "units": report.CROSS_OBJECT_OBJECTS.get(case, 2),
        "samples": {metric: _samples(metric) for metric in report.metrics_of(window, case)},
        "calls": dict.fromkeys(report.CALL_NAMES, 1.0) if window == report.KEYED_WINDOW else {},
        "warmups": report.WARMUPS,
        "measured": report.MEASURED,
        "retainedWarmups": 200,
    }
    document.update(overrides or {})
    return document


def _reading(case: str) -> report.ChildReading:
    decoded = report._decoded(  # pyright: ignore[reportPrivateUsage] - child protocol under test
        json.dumps(_child_document(case)), case
    )
    assert isinstance(decoded, report.ChildReading)
    return decoded


def _matrix(*runtimes: str) -> report.Matrix:
    return {runtime: {case: _reading(case) for case in report.CASE_NAMES} for runtime in runtimes}


# --------------------------------------------------------------------------- #
# The matrix: every case the protocol names, on every supported minor.         #
# --------------------------------------------------------------------------- #
def test_the_matrix_names_every_keyed_response_and_model_case_once() -> None:
    keyed = [case.name for case in lowering_support.CASES]
    leaf_keyed = [
        case.name for case in lowering_support.CASES if case.family == lowering_support.LEAF_FAMILY
    ]
    target = [case.name for case in lowering_support.CASES if case.addressed]
    response = [case.name for case in lowering_support.RESPONSE_CASES]
    cross_object = [case.name for case in lowering_support.CROSS_OBJECT_CASES]
    assert (
        *keyed,
        *response,
        report.MODEL_CASE,
        report.MODEL_FAMILY_CASE,
        *cross_object,
    ) == report.CASE_NAMES
    assert len(set(report.CASE_NAMES)) == len(report.CASE_NAMES)
    assert (*response, report.MODEL_FAMILY_CASE) == report.CONTROL_CASE_NAMES
    assert tuple(leaf_keyed) == report.LEAF_TYPE_CASE_NAMES
    assert tuple(target) == report.TARGET_CASE_NAMES
    assert tuple(cross_object) == report.CROSS_OBJECT_CASE_NAMES
    legacy_keyed = [name for name in keyed if name not in target and name not in leaf_keyed]
    assert (*legacy_keyed, *report.RETIRED_WINDOWS, report.MODEL_CASE) == report.LEGACY_CASE_NAMES
    assert report.CASE_COVERAGES == {
        "current": report.CASE_NAMES,
        "legacy": report.LEGACY_CASE_NAMES,
    }
    assert len(supported_minors()) == 2


def test_a_retired_case_is_carried_by_an_envelope_but_read_by_no_child() -> None:
    assert not set(report.RETIRED_WINDOWS) & set(report.WINDOWS)
    assert not set(report.RETIRED_WINDOWS.values()) & set(report.WINDOW_DESCRIPTIONS)
    assert report.ENVELOPE_WINDOWS == {**report.WINDOWS, **report.RETIRED_WINDOWS}
    for case in report.RETIRED_WINDOWS:
        assert report.selected_cases([case]) == ()
        assert all(
            report.unit_of(report.ENVELOPE_WINDOWS[case], metric).endswith("/row")
            for metric in report.METRICS
        )


def test_twenty_categorical_cases_cross_every_layout_and_ingress() -> None:
    categorical = [
        case
        for case in lowering_support.CASES
        if case.family in _CATEGORICAL_OPERATIONS and not case.addressed
    ]
    assert len(categorical) == 20
    expected = {
        f"{family}.{operation}.{layout}.{ingress}"
        for family, operations in _CATEGORICAL_OPERATIONS.items()
        for operation in operations
        for layout in lowering_support.LAYOUTS
        for ingress in lowering_support.INGRESSES
    }
    assert {case.name for case in categorical} == expected
    assert all(report.WINDOWS[name] == report.KEYED_WINDOW for name in expected)


_TARGET_TWINS = {
    "txtime": "txtime.changed",
    "bitemporal": "bitemporal.interior",
}


def test_target_writes_cross_every_categorical_family_and_layout_without_a_typed_patch() -> None:
    targets = [case for case in lowering_support.CASES if case.addressed]
    assert {case.name for case in targets} == {
        *(
            f"{family}.target-patch.{layout}.wire"
            for family in _TARGET_TWINS
            for layout in lowering_support.LAYOUTS
        ),
        *(
            f"{family}.target-replace.{layout}.{ingress}"
            for family in _TARGET_TWINS
            for layout in lowering_support.LAYOUTS
            for ingress in lowering_support.INGRESSES
        ),
    }
    assert all(
        case.stored is not None
        and case.bounded == (case.family == "bitemporal")
        and (case.instance is not None) == (case.ingress == "typed")
        and report.WINDOWS[case.name] == report.KEYED_WINDOW
        for case in targets
    )


def test_a_target_write_lowers_to_the_statements_its_observed_twin_lowers_to() -> None:
    for case in lowering_support.CASES:
        if not case.addressed:
            continue
        twin = lowering_support.case_named(f"{_TARGET_TWINS[case.family]}.{case.layout}.wire")
        target = lowering_support.lowered(case)
        observed = lowering_support.lowered(twin)
        assert [statement.sql for statement in target] == [s.sql for s in observed], case.name
        assert [statement.binds for statement in target] == [s.binds for s in observed], case.name


class _ChronologyPort(lowering_support.AcceptingPort):
    __slots__ = ("events",)
    events: list[str]

    def __init__(self, stored: Sequence[Mapping[str, object]]) -> None:
        super().__init__(stored)
        self.events = []

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        self.events.append("read")
        return super().execute(sql, binds, document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.events.append("write")
        return super().execute_write(sql, binds)


def test_a_target_reads_nothing_before_its_verb_and_its_one_read_inside_the_window() -> None:
    # An unversioned Non-Temporal target acquires its row at the call under
    # either strategy; a temporal target reads its coverage at flush.
    for case in lowering_support.CASES:
        if not case.addressed:
            continue
        assert case.stored is not None
        port = _ChronologyPort((case.stored,))
        with lowering_support.database(case, port) as handle:
            lowering_support.write(
                handle,
                case,
                opened=lambda port=port: port.events.append("opened"),
                buffered=lambda port=port: port.events.append("buffered"),
            )
        writes = ["write"] * len(lowering_support.lowered(case))
        if case.family == "plain":
            assert port.events == ["opened", "read", "buffered", *writes], case.name
        else:
            assert port.events == ["opened", "buffered", "read", *writes], case.name


def test_geometry_cases_cover_every_level_under_both_layouts_through_typed_inserts() -> None:
    geometry = [case for case in lowering_support.CASES if case.family.startswith("geometry-")]
    assert {case.name for case in geometry} == {
        f"geometry.{level.id}.{layout}.typed"
        for level in workloads.GEOMETRY_LEVELS
        for layout in workloads.STRUCTURAL_LAYOUTS
    }
    assert all(case.mutation == "insert" and case.stored is None for case in geometry)


def test_changed_ancestor_cases_succeed_a_milestone_at_every_manifest_width() -> None:
    ancestors = [case for case in lowering_support.CASES if case.family.startswith("ancestor-")]
    assert {case.name for case in ancestors} == {
        f"ancestor.{level_id}.{layout}.typed"
        for level_id in workloads.ANCESTOR_LEVEL_IDS
        for layout in workloads.STRUCTURAL_LAYOUTS
    }
    assert {level.width for level in workloads.ancestor_levels()} == {4, 16, 64}
    assert all(
        case.mutation == "amend" and case.statements == 2 and case.stored is not None
        for case in ancestors
    )
    assert all(report.WINDOWS[case.name] == report.KEYED_WINDOW for case in ancestors)


def test_a_changed_ancestor_patches_one_root_leaf_and_carries_every_other_member() -> None:
    for level_id in workloads.ANCESTOR_LEVEL_IDS:
        case = lowering_support.case_named(f"ancestor.{level_id}.document.typed")
        predecessor = _stored_document(case)
        _close, insert = lowering_support.lowered(case)
        (successor,) = _documents(insert.binds)
        root = cast("Mapping[str, object]", cast("Mapping[str, object]", successor)["body"])
        before = cast("Mapping[str, object]", predecessor["body"])
        assert root["f0"] != before["f0"]
        assert {name: root[name] for name in before if name != "f0"} == {
            name: before[name] for name in before if name != "f0"
        }
        assert (
            detach_json_container(cast("Mapping[str, object]", successor)["items"])
            == predecessor["items"]
        )


def test_the_counter_vocabularies_differ_only_in_the_retired_and_renamed_counters() -> None:
    assert report.CALL_VOCABULARIES == {
        "current": report.CALL_NAMES,
        "managed": report.MANAGED_CALL_NAMES,
        "legacy": report.LEGACY_CALL_NAMES,
    }
    assert len(report.CALL_NAMES) == len(set(report.CALL_NAMES)) == 5
    assert len(report.MANAGED_CALL_NAMES) == len(set(report.MANAGED_CALL_NAMES)) == 7
    assert len(report.LEGACY_CALL_NAMES) == len(set(report.LEGACY_CALL_NAMES)) == 7
    assert set(report.MANAGED_CALL_NAMES) - set(report.CALL_NAMES) == {
        "shapeOfDeclaration",
        "entityShape",
    }
    assert set(report.CALL_NAMES) <= set(report.MANAGED_CALL_NAMES)
    assert set(report.MANAGED_CALL_NAMES) - set(report.LEGACY_CALL_NAMES) == {
        "encodeManagedDocument",
        "encodeManagedMany",
    }
    assert set(report.LEGACY_CALL_NAMES) - set(report.MANAGED_CALL_NAMES) == {
        "encodeDocument",
        "encodeMany",
    }
    keyed = [case.name for case in lowering_support.CASES]
    current = report.expected_addresses(("3.14",))
    managed = report.expected_addresses(("3.14",), report.MANAGED_CALL_NAMES)
    legacy = report.expected_addresses(("3.14",), report.LEGACY_CALL_NAMES)
    assert current == report.expected_addresses(("3.14",), report.CALL_NAMES)
    uncounted = {address for address in current if not address[2].startswith("calls.")}
    assert uncounted == {address for address in managed if not address[2].startswith("calls.")}
    assert uncounted == {address for address in legacy if not address[2].startswith("calls.")}
    assert managed - current == {
        ("3.14", case, f"calls.{name}")
        for case in keyed
        for name in ("shapeOfDeclaration", "entityShape")
    }
    assert current < managed
    assert managed - legacy == {
        ("3.14", case, f"calls.{name}")
        for case in keyed
        for name in ("encodeManagedDocument", "encodeManagedMany")
    }
    assert legacy - managed == {
        ("3.14", case, f"calls.{name}")
        for case in keyed
        for name in ("encodeDocument", "encodeMany")
    }


def test_leaf_type_inserts_cross_every_measured_type_layout_and_ingress_beside_a_wire_control() -> (
    None
):
    leaf = [case for case in lowering_support.CASES if case.family == lowering_support.LEAF_FAMILY]
    assert {case.name for case in leaf} == {
        *(
            f"leaf.{type_id}.{layout}.{ingress}"
            for type_id in workloads.LEAF_TYPE_IDS
            for layout in workloads.STRUCTURAL_LAYOUTS
            for ingress in lowering_support.INGRESSES
        ),
        *(
            f"leaf.{workloads.LEAF_CONTROL_TYPE_ID}.{layout}.wire"
            for layout in workloads.STRUCTURAL_LAYOUTS
        ),
    }
    assert all(
        case.mutation == "insert"
        and case.stored is None
        and case.model is leaf_support.MODEL
        and report.WINDOWS[case.name] == report.KEYED_WINDOW
        for case in leaf
    )
    level = workloads.leaf_type_level()
    string_control = lowering_support.case_named(f"geometry.{level.id}.columns.typed")
    assert string_control.model is lowering_support.MODEL


def test_a_leaf_type_insert_writes_every_leaf_in_its_canonical_wire_spelling() -> None:
    for case in lowering_support.CASES:
        if case.family != lowering_support.LEAF_FAMILY:
            continue
        leaf = leaf_support.leaf_type_named(case.name.split(".")[1])
        (insert,) = lowering_support.lowered(case)
        documents = [detach_json_container(document) for document in _documents(insert.binds)]
        if case.layout == "document":
            (payload,) = documents
            documents = [cast("Mapping[str, object]", payload)[name] for name in ("body", "items")]
        expected = leaf_support.wire_row(leaf, lowering_support.LEAF_KEY)
        assert documents == [expected["body"], expected["items"]], case.name


# --------------------------------------------------------------------------- #
# The fixture: what each keyed case lowers to, and what the driver dumps.      #
# --------------------------------------------------------------------------- #
def _documents(statement_binds: Sequence[object]) -> list[object]:
    return [bind.value for bind in statement_binds if isinstance(bind, JsonDocument)]


def _rows(statement: lowering_support.Executed) -> list[tuple[object, ...]]:
    """The binds of each value tuple ``statement`` renders: one per Planned
    Step, since contiguous compatible single-entry inserts share one grouped
    insert (`m-execution` *Flush execution*); any other statement is one."""
    tuples = statement.sql.count("), (") + 1 if statement.sql.startswith("insert") else 1
    width = len(statement.binds) // tuples
    return [statement.binds[index * width : (index + 1) * width] for index in range(tuples)]


def _physical(case: lowering_support.Case) -> list[tuple[str, int]]:
    """The statements ``case``'s flush executes, each with the value tuples it
    renders: a temporal change closes its predecessor, then opens every
    successor in one insert."""
    if case.mutation == "insert":
        return [("insert", 1)]
    if case.family == "plain":
        return [("update", 1)]
    if case.statements == 0:
        return []
    return [("update", 1), ("insert", case.statements - 1)]


def _stored_document(case: lowering_support.Case) -> Mapping[str, object]:
    """The Structured Column of the Relational Document row ``case`` revises."""
    assert case.layout == "document" and case.stored is not None
    return cast("Mapping[str, object]", case.stored["payload"])


@pytest.mark.parametrize("case", lowering_support.CASES, ids=lambda case: case.name)
def test_every_keyed_case_lowers_its_stated_writes_and_dumps_each_document(
    case: lowering_support.Case,
) -> None:
    lowered = lowering_support.lowered(case)
    assert sum(len(_rows(statement)) for statement in lowered) == case.statements
    assert [
        (statement.sql.split(" ", 1)[0], len(_rows(statement))) for statement in lowered
    ] == _physical(case)
    for statement in lowered:
        assert len(statement.dumped) == len(statement.binds)
        for bind, buffer in zip(statement.binds, statement.dumped, strict=True):
            if isinstance(bind, JsonDocument):
                assert (
                    bytes(buffer or b"") == json.dumps(detach_json_container(bind.value)).encode()
                )


def test_typed_and_wire_ingress_lower_to_the_same_statements() -> None:
    by_name = {case.name: case for case in lowering_support.CASES}
    for case in lowering_support.CASES:
        if case.ingress != "typed" or case.family.startswith(("geometry-", "ancestor-")):
            continue
        twin = by_name[case.name.removesuffix(".typed") + ".wire"]
        typed = lowering_support.lowered(case)
        wire = lowering_support.lowered(twin)
        assert [statement.sql for statement in typed] == [statement.sql for statement in wire]
        assert [statement.binds for statement in typed] == [statement.binds for statement in wire]


def test_an_unchanged_successor_writes_nothing_and_a_changed_one_replaces_it() -> None:
    for ingress in lowering_support.INGRESSES:
        unchanged = lowering_support.case_named(f"txtime.unchanged.document.{ingress}")
        assert lowering_support.lowered(unchanged) == ()
        changed = lowering_support.case_named(f"txtime.changed.document.{ingress}")
        _close, insert = lowering_support.lowered(changed)
        (successor,) = _documents(insert.binds)
        assert successor != _stored_document(changed)
        assert cast("Mapping[str, object]", successor)["title"] == "title-after"


def test_a_bitemporal_interior_update_carries_head_and_tail_and_changes_the_middle() -> None:
    for layout in lowering_support.LAYOUTS:
        case = lowering_support.case_named(f"bitemporal.interior.{layout}.typed")
        _close, opened = lowering_support.lowered(case)
        titles = [
            next(bind for bind in row if isinstance(bind, str) and "title" in bind)
            if layout == "columns"
            else cast("Mapping[str, object]", _documents(row)[0])["title"]
            for row in _rows(opened)
        ]
        assert titles == ["title-before", "title-middle", "title-before"]


def test_a_non_temporal_changed_update_revises_the_row_it_read_in_place() -> None:
    for layout in lowering_support.LAYOUTS:
        case = lowering_support.case_named(f"plain.changed.{layout}.typed")
        assert case.stored is not None
        (statement,) = lowering_support.lowered(case)
        assert statement.sql.startswith("update ")


def test_the_workload_digest_covers_every_defining_source(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = lowering_support.write_lowering_digest()
    assert len(digest) == 64
    with monkeypatch.context() as patched:
        patched.setattr(workloads, "READ_GEOMETRY_ROOTS", workloads.READ_GEOMETRY_ROOTS + 1)
        assert lowering_support.write_lowering_digest() != digest
    monkeypatch.setattr(workloads, "LEAF_TYPE_RUNTIMES", 2)
    assert lowering_support.write_lowering_digest() != digest


@pytest.mark.parametrize("prose", ["# Revised comment\n", '"""Revised module prose."""\n'])
def test_workload_identity_ignores_prose(prose: str) -> None:
    from tests.unit._workload_digest_support import canonical_source

    before = '"Original prose."\nVALUE = "operational"\n"Attribute prose."\n'
    after = prose + 'VALUE = "operational"\n"New attribute prose."\n'
    assert canonical_source(before) == canonical_source(after)
    assert canonical_source(before) != canonical_source(after.replace('"operational"', '"changed"'))


@pytest.mark.parametrize(
    "relative",
    [
        "tests/unit/_write_lowering_support.py",
        "tests/unit/_structural_geometry_support.py",
        "tests/unit/_leaf_type_support.py",
        "tests/unit/_workload_spelling_support.py",
    ],
)
def test_the_write_digest_ignores_prose_and_tracks_operational_code(
    monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    baseline = lowering_support.write_lowering_digest()
    source_path = Path(lowering_support.__file__).parents[2] / relative
    read_text = Path.read_text

    def prose(path: Path, *args: Any, **kwargs: Any) -> str:
        source = read_text(path, *args, **kwargs)
        return (
            source.replace('"""', '"""Revised documentation.\n', 1)
            if path == source_path
            else source
        )

    monkeypatch.setattr(Path, "read_text", prose)
    assert lowering_support.write_lowering_digest() == baseline

    def operational(path: Path, *args: Any, **kwargs: Any) -> str:
        source = read_text(path, *args, **kwargs)
        return source + '\nWORKLOAD_INPUT = "changed"\n' if path == source_path else source

    monkeypatch.setattr(Path, "read_text", operational)
    assert lowering_support.write_lowering_digest() != baseline


# --------------------------------------------------------------------------- #
# The child protocol and the envelope.                                         #
# --------------------------------------------------------------------------- #
def test_child_output_decodes_from_its_final_line() -> None:
    case = report.CASE_NAMES[0]
    decoded = report._decoded(  # pyright: ignore[reportPrivateUsage] - child protocol under test
        f"ignored diagnostic\n{json.dumps(_child_document(case))}\n", case
    )
    assert isinstance(decoded, report.ChildReading)
    assert decoded.units == 2
    assert decoded.samples["elapsedUs"] == (10.0, 12.0, 11.0) * 3
    assert decoded.retained_warmups == 200
    assert set(decoded.calls) == set(report.CALL_NAMES)


@pytest.mark.parametrize(
    "overrides",
    [
        {"case": "other"},
        {"window": report.MODEL_WINDOW},
        {"units": 0},
        {"samples": {"elapsedUs": [1.0]}},
        {"samples": {"elapsedUs": [0.0], "transientBytes": [1.0], "retainedBytes": [1.0]}},
        {"samples": {"elapsedUs": [1.0], "transientBytes": [-1.0], "retainedBytes": [1.0]}},
        {"calls": {}},
        {"calls": {**dict.fromkeys(report.CALL_NAMES, 1.0), "extra": 1.0}},
        {"calls": dict.fromkeys(report.LEGACY_CALL_NAMES, 1.0)},
        {"calls": dict.fromkeys(report.MANAGED_CALL_NAMES, 1.0)},
        {"calls": dict.fromkeys((*report.CALL_NAMES, *report.LEGACY_CALL_NAMES), 1.0)},
        {"calls": {name: 1.0 for name in report.CALL_NAMES if name != "encodeManagedMany"}},
        {"warmups": report.WARMUPS + 1},
        {"retainedWarmups": 0},
        {"unexpected": True},
    ],
)
def test_a_malformed_keyed_child_reading_is_an_unavailable_cell(
    overrides: dict[str, object],
) -> None:
    case = lowering_support.CASES[0].name
    assert isinstance(
        report._decoded(  # pyright: ignore[reportPrivateUsage] - child protocol under test
            json.dumps(_child_document(case, overrides)), case
        ),
        str,
    )


@pytest.mark.parametrize("output", ["", "not-json"])
def test_empty_or_unparsable_child_output_is_an_unavailable_cell(output: str) -> None:
    assert isinstance(
        report._decoded(  # pyright: ignore[reportPrivateUsage] - child protocol under test
            output, report.CASE_NAMES[0]
        ),
        str,
    )


def test_a_non_keyed_case_reports_no_pass_observations() -> None:
    for case in (lowering_support.RESPONSE_CASES[0].name, report.MODEL_CASE):
        assert isinstance(_reading(case), report.ChildReading)
        assert isinstance(
            report._decoded(  # pyright: ignore[reportPrivateUsage] - child protocol under test
                json.dumps(_child_document(case, {"calls": {"encodeMany": 1.0}})), case
            ),
            str,
        )


def test_envelope_carries_every_address_with_its_window_runtime_and_unit() -> None:
    matrix = _matrix("3.13", "3.14")
    contract = BudgetContract.load()
    envelope = report.build_envelope(
        contract,
        report._provenance(contract, matrix),  # pyright: ignore[reportPrivateUsage] - entrypoint seam
        matrix,
    )
    validate(envelope)
    assert envelope.subject == report.SUBJECT
    assert envelope.comparisons == () and envelope.incomplete == () and envelope.errors == ()
    assert envelope.provenance.workload_digest == lowering_support.write_lowering_digest()
    assert envelope.provenance.sampling["retainedWarmups"] == 200
    assert set(cast("Mapping[str, str]", envelope.provenance.sampling["windows"])) == {
        report.KEYED_WINDOW,
        report.RESPONSE_WINDOW,
        report.MODEL_WINDOW,
        report.FLUSH_WINDOW,
    }
    addresses = {(reading.runtime, reading.workload, reading.cell) for reading in envelope.readings}
    assert addresses == report.expected_addresses(("3.13", "3.14"))
    for reading in envelope.readings:
        assert reading.window == report.WINDOWS[reading.workload]
        assert reading.window is not None
        if reading.cell.startswith("calls."):
            assert reading.unit == "calls/row"
        else:
            assert reading.unit == report.unit_of(reading.window, reading.cell)
            assert reading.value == 11.0 or reading.cell != "elapsedUs"
    model = next(r for r in envelope.readings if r.workload == report.MODEL_CASE)
    assert model.unit in {"us", "B"}


def test_children_must_agree_on_the_retained_warmup_count() -> None:
    matrix = _matrix("3.14")
    matrix["3.14"][report.MODEL_CASE] = report.ChildReading(
        report.MODEL_CASE, report.MODEL_WINDOW, 1, {m: (1.0,) for m in report.METRICS}, {}, 3, 9, 7
    )
    with pytest.raises(ValueError, match="disagree on the retained warm-up count"):
        report.retained_warmups(matrix)


def test_canary_is_a_schema_valid_complete_envelope() -> None:
    envelope = report.canary(BudgetContract.load())
    validate(envelope)
    assert envelope.subject == report.SUBJECT
    assert {(r.runtime, r.workload, r.cell) for r in envelope.readings} == (
        report.expected_addresses((CURRENT_MINOR,))
    )


def test_successful_entrypoint_stdout_is_only_the_owned_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix = _matrix("3.14")
    monkeypatch.setattr(report, "supported_minors", lambda: ("3.14",))

    def child(runtime: str, case: str) -> report.Cell:
        return matrix[runtime][case]

    monkeypatch.setattr(report, "in_a_child", child)
    assert report.main([]) == 0
    captured = capsys.readouterr()
    document = cast("Mapping[str, object]", json.loads(captured.out))
    assert captured.err == ""
    assert document["subject"] == report.SUBJECT
    validate(document)


def test_entrypoint_refuses_arguments_and_an_incomplete_matrix(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert report.main(["unexpected"]) == 2
    assert "usage:" in capsys.readouterr().err
    monkeypatch.setattr(report, "supported_minors", lambda: ("3.14",))

    def failing_child(_runtime: str, case: str) -> report.Cell:
        return f"{case} failed"

    monkeypatch.setattr(report, "in_a_child", failing_child)
    assert report.main([]) == 3
    diagnostic = capsys.readouterr().err
    assert "the matrix is incomplete" in diagnostic
    assert all(case in diagnostic for case in report.CASE_NAMES)


def test_missing_cells_and_envelope_refuse_an_incomplete_matrix() -> None:
    assert report.missing_cells({}, ("3.14",), report.CASE_NAMES) == [
        f"CPython 3.14, {case}: no child was run" for case in report.CASE_NAMES
    ]
    contract = BudgetContract.load()
    with pytest.raises(ValueError, match="matrix is incomplete"):
        report.build_envelope(
            contract,
            report._provenance(contract, _matrix("3.14")),  # pyright: ignore[reportPrivateUsage] - entrypoint seam
            {"3.14": {}},
        )


def test_a_diagnostic_run_answers_the_chosen_cases_and_is_no_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix = _matrix("3.14")

    def child(runtime: str, case: str) -> report.Cell:
        return matrix[runtime][case] if case.startswith("plain.") else f"{case} refused"

    monkeypatch.setattr(report, "in_a_child", child)
    assert (
        report.main(["--diagnostic", "--case", "plain.*", "--case", "model.*", "--runtime", "3.14"])
        == 0
    )
    document = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    assert document["diagnostic"] is True
    assert document["subject"] == report.SUBJECT
    assert document["runtimes"] == ["3.14"]
    readings = cast("list[dict[str, object]]", document["readings"])
    assert {r["workload"] for r in readings} == set(report.selected_cases(["plain.*"]))
    assert document["unavailable"] == [
        f"CPython 3.14, {case}: {case} refused"
        for case in report.CASE_NAMES
        if case.startswith("model.")
    ]
    assert "provenance" not in document
    with pytest.raises(Exception):  # noqa: B017 - any schema or semantic refusal proves it is no envelope
        validate(document)


def test_diagnostic_options_are_refused_outside_diagnostic_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert report.main(["--case", "plain.*"]) == 2
    assert "usage:" in capsys.readouterr().err
    assert report.main(["--diagnostic", "--case", "nothing-matches"]) == 2
    assert "no case matches" in capsys.readouterr().err
    assert report.selected_cases(["txtime.unchanged.*.wire"]) == (
        "txtime.unchanged.columns.wire",
        "txtime.unchanged.document.wire",
    )


def test_durations_time_every_child_without_changing_the_matrix_or_the_stdout_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pin_dirty_tree(monkeypatch)
    matrix = _matrix("3.13", "3.14")
    monkeypatch.setattr(report, "supported_minors", lambda: ("3.13", "3.14"))
    asked: list[tuple[str, str]] = []

    def child(runtime: str, case: str) -> report.Cell:
        asked.append((runtime, case))
        return matrix[runtime][case]

    monkeypatch.setattr(report, "in_a_child", child)
    assert report.main([]) == 0
    plain = capsys.readouterr()
    plain_order = list(asked)
    assert {runtime for runtime, case in plain_order if case in report.LEAF_TYPE_CASE_NAMES} == {
        "3.14"
    }
    asked.clear()
    sidecar = tmp_path / "durations.json"
    assert report.main(["--durations", str(sidecar)]) == 0
    timed = capsys.readouterr()
    assert asked == plain_order
    assert timed.out == plain.out
    assert timed.err == ""
    validate(cast("Mapping[str, object]", json.loads(timed.out)))
    spans = Spans.load(sidecar)
    assert [(span.labels["runtime"], span.name) for span in spans.spans] == plain_order
    assert {span.scope for span in spans.spans} == {"case"}
    assert all(
        span.labels
        == {"member": report.SUBJECT, "runtime": runtime, "window": report.WINDOWS[case]}
        for span, (runtime, case) in zip(spans.spans, plain_order, strict=True)
    )
    assert spans.unavailable == ()


def test_an_incomplete_matrix_still_leaves_its_durations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(report, "supported_minors", lambda: ("3.14",))

    def failing_child(_runtime: str, case: str) -> report.Cell:
        return f"{case} failed"

    monkeypatch.setattr(report, "in_a_child", failing_child)
    sidecar = tmp_path / "durations.json"
    assert report.main(["--durations", str(sidecar)]) == 3
    assert "the matrix is incomplete" in capsys.readouterr().err
    assert [span.name for span in Spans.load(sidecar).spans] == list(report.CASE_NAMES)


def test_an_unwritable_sidecar_changes_neither_the_envelope_nor_the_exit_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pin_dirty_tree(monkeypatch)
    matrix = _matrix("3.14")
    monkeypatch.setattr(report, "supported_minors", lambda: ("3.14",))
    identity = json.dumps({"implementation": "CPython", "version": "3.14.7", "executable": "/p"})

    def probe(_command: Sequence[str], _environment: Mapping[str, str]) -> tuple[int, str, str]:
        return (0, identity, "")

    def child(runtime: str, case: str) -> report.Cell:
        return matrix[runtime][case]

    monkeypatch.setattr(report, "run_probe", probe)
    monkeypatch.setattr(report, "in_a_child", child)
    assert report.main([]) == 0
    plain = capsys.readouterr()
    durations = tmp_path / "durations.json"
    metadata = tmp_path / "metadata.json"
    durations.mkdir()
    metadata.mkdir()
    assert report.main(["--durations", str(durations), "--metadata", str(metadata)]) == 0
    captured = capsys.readouterr()
    assert captured.out == plain.out
    assert captured.err.splitlines() == [
        f"telemetry sidecar {metadata} was not written: [Errno 21] Is a directory: '{metadata}'",
        f"telemetry sidecar {durations} was not written: [Errno 21] Is a directory: '{durations}'",
    ]


def test_durations_are_refused_beside_a_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sidecar = tmp_path / "durations.json"
    assert report.main(["--diagnostic", "--durations", str(sidecar)]) == 2
    assert "usage:" in capsys.readouterr().err
    assert report.main(["--durations"]) == 2
    assert "usage:" in capsys.readouterr().err
    assert not sidecar.exists()


def test_metadata_probes_each_runtime_through_the_childs_resolution_before_any_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    matrix = _matrix("3.13", "3.14")
    monkeypatch.setattr(report, "supported_minors", lambda: ("3.13", "3.14"))
    events: list[str] = []
    probed: list[tuple[list[str], dict[str, str]]] = []
    versions = {
        tuple(report.child_command(runtime, IDENTITY_SCRIPT, ())): version
        for runtime, version in (("3.13", "3.13.15"), ("3.14", "3.14.7"))
    }

    def probe(command: Sequence[str], environment: Mapping[str, str]) -> tuple[int, str, str]:
        probed.append((list(command), dict(environment)))
        events.append("probe")
        identity = {
            "implementation": "CPython",
            "version": versions[tuple(command)],
            "executable": "/p",
        }
        return (0, json.dumps(identity), "")

    def child(runtime: str, case: str) -> report.Cell:
        events.append("child")
        return matrix[runtime][case]

    monkeypatch.setattr(report, "run_probe", probe)
    monkeypatch.setattr(report, "in_a_child", child)
    metadata = tmp_path / "metadata.json"
    assert report.main(["--metadata", str(metadata)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    validate(cast("Mapping[str, object]", json.loads(captured.out)))
    assert events[:2] == ["probe", "probe"] and "probe" not in events[2:]
    assert [command for command, _environment in probed] == [
        report.child_command(runtime, IDENTITY_SCRIPT, ()) for runtime in ("3.13", "3.14")
    ]
    assert [environment for _command, environment in probed] == [
        report.child_environment(runtime, report.ENVIRONMENT_NAMESPACE)
        for runtime in ("3.13", "3.14")
    ]
    recorded = json.loads(metadata.read_text(encoding="utf-8"))
    assert recorded["subject"] == report.SUBJECT
    assert {r: s["version"] for r, s in recorded["runtimes"].items()} == {
        "3.13": "3.13.15",
        "3.14": "3.14.7",
    }


def test_metadata_is_refused_beside_a_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = tmp_path / "metadata.json"
    assert report.main(["--diagnostic", "--metadata", str(metadata)]) == 2
    assert "usage:" in capsys.readouterr().err
    assert not metadata.exists()


# --------------------------------------------------------------------------- #
# The controls beside the lowering matrix: the public insert and the family.   #
# --------------------------------------------------------------------------- #
def test_the_public_insert_answers_its_nested_polymorphic_node_inside_the_window() -> None:
    (case,) = lowering_support.RESPONSE_CASES
    assert case.entity is lowering_support.Dog
    assert report.WINDOWS[case.name] == report.RESPONSE_WINDOW
    assert report.unit_of(report.RESPONSE_WINDOW, "elapsedUs") == "us/row"
    assert report.unit_of(report.RESPONSE_WINDOW, "retainedBytes") == "B/row"
    marks: list[str] = []
    with lowering_support.response_database(case) as handle:
        node = lowering_support.insert_response(
            handle,
            case,
            opened=lambda: marks.append("opened"),
            closed=lambda: marks.append("closed"),
        )
        again = lowering_support.insert_response(handle, case)
    assert marks == ["opened", "closed"]
    assert dict(node) == dict(again)
    assert node["familyVariant"] == "Dog"
    address = cast("Mapping[str, Any]", node["address"])
    assert cast("Mapping[str, Any]", address["geo"])["country"] == "country-response"
    assert [
        cast("Mapping[str, Any]", tag)["label"] for tag in cast("list[object]", node["tags"])
    ] == [
        "tag-response-a",
        "tag-response-b",
    ]
    assert node["barkVolume"] == 3
    assert lowering_support.response_case_named(case.name) is case
    with pytest.raises(KeyError):
        lowering_support.response_case_named("response.insert.plain.wire")


def test_the_family_model_is_its_own_preparation_beside_the_structural_model() -> None:
    assert report.WINDOWS[report.MODEL_FAMILY_CASE] == report.MODEL_WINDOW
    assert not set(lowering_support.FAMILY_ENTITY_CLASSES) & set(lowering_support.ENTITY_CLASSES)
    assert {cls.__name__ for cls in lowering_support.FAMILY_ENTITY_CLASSES} == {"Pet", "Dog", "Cat"}


def test_the_legacy_coverage_drops_the_later_cases_and_carries_the_retired_ones() -> None:
    runtimes = supported_minors()
    current = report.expected_addresses(runtimes)
    legacy = report.expected_addresses(runtimes, report.CALL_NAMES, report.LEGACY_CASE_NAMES)
    assert {case for _runtime, case, _cell in current - legacy} == {
        *report.CONTROL_CASE_NAMES,
        *report.LEAF_TYPE_CASE_NAMES,
        *report.TARGET_CASE_NAMES,
        *report.CROSS_OBJECT_CASE_NAMES,
    }
    assert legacy - current == {
        (runtime, case, metric)
        for runtime in runtimes
        for case in report.RETIRED_WINDOWS
        for metric in report.METRICS
    }


def test_the_leaf_type_cases_are_read_on_the_newest_supported_minor_alone() -> None:
    oldest, newest = supported_minors()
    assert report.runtime_cases(newest) == report.CASE_NAMES
    assert report.runtime_cases(oldest) == tuple(
        name for name in report.CASE_NAMES if name not in report.LEAF_TYPE_CASE_NAMES
    )
    assert {
        runtime
        for runtime, case, _cell in report.expected_addresses((oldest, newest))
        if case in report.LEAF_TYPE_CASE_NAMES
    } == {newest}


# --------------------------------------------------------------------------- #
# The cross-object flushes: keyed loops whose one flush executes Write Groups. #
# --------------------------------------------------------------------------- #
def test_the_cross_object_family_is_keyed_loops_and_deferred_spans_read_on_every_minor() -> None:
    family = {
        case.name: (case.entity, case.ingress, case.layout, case.objects, case.groups)
        for case in lowering_support.CROSS_OBJECT_CASES
    }
    assert family == {
        "cross-object.txtime.changed-64.columns.typed": (
            lowering_support.TxColumns,
            "typed",
            "columns",
            64,
            (64,),
        ),
        "cross-object.txtime.changed-130.columns.typed": (
            lowering_support.TxColumns,
            "typed",
            "columns",
            130,
            (64, 64, 2),
        ),
        "cross-object.bitemporal.interior-64.document.wire": (
            lowering_support.BiDocument,
            "wire",
            "document",
            64,
            (64,),
        ),
        "cross-object.bitemporal.deferred-32x4.columns.typed": (
            lowering_support.BiColumns,
            "typed",
            "columns",
            32,
            (32,),
        ),
        "cross-object.bitemporal.deferred-32x12.document.wire": (
            lowering_support.BiDocument,
            "wire",
            "document",
            32,
            (32,),
        ),
        "cross-object.bitemporal.requesting-32x12.document.wire": (
            lowering_support.BiDocument,
            "wire",
            "document",
            32,
            (32,),
        ),
        "cross-object.bitemporal.deferred-32x32.columns.typed": (
            lowering_support.BiColumns,
            "typed",
            "columns",
            32,
            (32,),
        ),
        "cross-object.bitemporal.partial-3x66.columns.typed": (
            lowering_support.BiColumns,
            "typed",
            "columns",
            3,
            (1, 2),
        ),
    }
    assert report.selected_cases([f"{lowering_support.CROSS_OBJECT_PREFIX}*"]) == tuple(family)
    assert all(report.WINDOWS[name] == report.FLUSH_WINDOW for name in family)
    assert (
        tuple(case.name for case in lowering_support.DEFERRED_CASES)
        == report.DEFERRED_CROSS_OBJECT_CASE_NAMES
    )
    assert lowering_support.CROSS_OBJECT_CASES[3:] == lowering_support.DEFERRED_CASES
    for case in lowering_support.CROSS_OBJECT_CASES:
        keys = [row["id"] for row in case.stored]
        assert len(set(keys)) == case.objects == sum(case.groups)
        assert set(case.changes) == set(keys)
        assert all("id" not in changes for changes in case.changes.values())
        assert case.deferred == (case.name in report.DEFERRED_CROSS_OBJECT_CASE_NAMES)
        assert {row["id"] for row in case.acquired} <= set(keys)
    runtimes = supported_minors()
    combinations = {
        (runtime, case)
        for runtime, case, _cell in report.expected_addresses(runtimes)
        if case in family
    }
    assert combinations == {(runtime, case) for runtime in runtimes for case in family}
    assert len(combinations) == 16


def _flush_cells(case: str) -> tuple[str, ...]:
    deferred = case in report.DEFERRED_CROSS_OBJECT_CASE_NAMES
    return (*report.FLUSH_METRICS, *(report.DEFERRED_FLUSH_METRICS if deferred else ()))


def test_a_cross_object_flush_answers_per_flush_and_per_object_bytes_at_distinct_addresses() -> (
    None
):
    units = {**report.FLUSH_UNITS, **report.DEFERRED_FLUSH_UNITS}
    for metric in (*report.FLUSH_METRICS, *report.DEFERRED_FLUSH_METRICS):
        assert report.unit_of(report.FLUSH_WINDOW, metric) == units[metric]
    per_flush = {m for m, unit in report.FLUSH_UNITS.items() if unit == "B"}
    per_object = {m for m, unit in report.FLUSH_UNITS.items() if unit == "B/row"}
    assert per_flush == {"plan.retainedBytes", "execution.transientBytes"}
    assert per_object == {f"{metric}PerObject" for metric in per_flush}
    assert {m for m, unit in report.DEFERRED_FLUSH_UNITS.items() if unit in {"B", "B/row"}} == {
        "binding.transientBytes",
        "binding.transientBytesPerObject",
    }
    for _runtime, case, cell in report.expected_addresses(("3.14",)):
        if case in report.CROSS_OBJECT_CASE_NAMES:
            assert cell in _flush_cells(case), (case, cell)
    matrix = _matrix("3.13", "3.14")
    contract = BudgetContract.load()
    envelope = report.build_envelope(
        contract,
        report._provenance(contract, matrix),  # pyright: ignore[reportPrivateUsage] - entrypoint seam
        matrix,
    )
    flushes = [r for r in envelope.readings if r.workload in report.CROSS_OBJECT_CASE_NAMES]
    assert {(r.runtime, r.workload, r.cell) for r in flushes} == {
        (runtime, case, metric)
        for runtime in ("3.13", "3.14")
        for case in report.CROSS_OBJECT_CASE_NAMES
        for metric in _flush_cells(case)
    }
    assert all(r.window == report.FLUSH_WINDOW for r in flushes)
    gates = derive_memory_gates({"members": [envelope.document()]}, 1.10)
    flush_gates = {
        "plan.retainedBytes": "B",
        "plan.retainedBytesPerObject": "B/row",
        "execution.transientBytes": "B",
        "execution.transientBytesPerObject": "B/row",
    }
    binding_gates = {"binding.transientBytes": "B", "binding.transientBytesPerObject": "B/row"}
    assert {
        workload: {cell: gate["unit"] for cell, gate in cells.items()}
        for workload, cells in gates[report.SUBJECT].items()
        if workload in report.CROSS_OBJECT_CASE_NAMES
    } == {
        case: flush_gates
        | (binding_gates if case in report.DEFERRED_CROSS_OBJECT_CASE_NAMES else {})
        for case in report.CROSS_OBJECT_CASE_NAMES
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"units": 1},
        {"samples": {"elapsedUs": [1.0] * 9, "transientBytes": [1.0] * 9, "retainedBytes": [1.0]}},
        {"samples": {metric: _samples(metric) for metric in report.FLUSH_METRICS[:-1]}},
        {
            "samples": {
                **{metric: _samples(metric) for metric in report.FLUSH_METRICS},
                "work.statements": [0.0],
            }
        },
        {"calls": dict.fromkeys(report.CALL_NAMES, 1.0)},
    ],
)
def test_a_malformed_cross_object_child_reading_is_an_unavailable_cell(
    overrides: dict[str, object],
) -> None:
    (case, *_others) = report.CROSS_OBJECT_CASE_NAMES
    assert isinstance(_reading(case), report.ChildReading)
    assert isinstance(
        report._decoded(  # pyright: ignore[reportPrivateUsage] - child protocol under test
            json.dumps(_child_document(case, overrides)), case
        ),
        str,
    )


def test_the_single_write_port_offers_no_ordered_transport_and_the_flush_port_one_stable_one() -> (
    None
):
    assert lowering_support.AcceptingPort().ordered_write_transport is None
    port = lowering_support.OrderedAcceptingPort()
    transport = port.ordered_write_transport
    assert transport is not None
    assert port.ordered_write_transport is transport


_DAY = dt.timedelta(days=1)
_START = lowering_support.VALID_START


def test_the_span_port_answers_each_read_with_the_milestones_it_names_once() -> None:
    port = lowering_support.SpanAcceptingPort(
        [{"id": 1, "from_z": _START, "thru_z": _START + _DAY}],
        [
            *(
                {"id": 1, "from_z": _START + _DAY * day, "thru_z": _START + _DAY * (day + 1)}
                for day in range(1, 4)
            ),
            {"id": 2, "from_z": _START, "thru_z": INFINITY},
        ],
    )
    coverage = (
        "select t0.id, t0.from_z from t t0 where ((t0.id = %s and ((t0.thru_z > %s and "
        "t0.from_z < %s) or (t0.thru_z > %s and t0.from_z < %s))) or (t0.id = %s and "
        "t0.thru_z > %s and t0.from_z < %s)) and t0.out_z = %s"
    )
    # The milestone of day 2 reaches into both of key 1's windows: it is one row.
    windows = [1, _START + _DAY, _START + _DAY * 2.5, _START + _DAY * 2, _START + _DAY * 3]
    answered = port.execute(coverage, [*windows, 2, _START, _START + _DAY, INFINITY])
    assert answered == [(1, _START + _DAY), (1, _START + _DAY * 2), (2, _START)]
    as_of = (
        "select t0.id, t0.from_z from t t0 where t0.id between %s and %s and "
        "t0.from_z <= %s and t0.thru_z > %s and t0.out_z = %s"
    )
    middle = _START + _DAY / 2
    assert port.execute(as_of, [1, 9, middle, middle, INFINITY]) == [(1, _START)]
    assert port.coverage_reads == 1
    port.reset()
    assert (port.coverage_reads, port.work()) == (0, lowering_support.FlushWork(0, 0, 0, 0))


@dataclass(frozen=True, slots=True)
class _Statement:
    sql: str
    binds: Sequence[object]


def test_the_flush_port_serializes_every_statement_and_counts_one_flush_in_constant_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serialized: list[int] = []

    def counting(binds: Sequence[object]) -> Any:
        serialized.append(len(binds))
        return []

    monkeypatch.setattr(lowering_support, "serialize", counting)
    port = lowering_support.OrderedAcceptingPort()
    transport = port.ordered_write_transport
    assert transport is not None
    assert port.work() == lowering_support.FlushWork(0, 0, 0, 0)
    assert port.execute_write("insert into t(a, b) values (%s, %s), (%s, %s), (%s, %s)", [1] * 6)
    assert port.execute_write("update t set a = %s where b = %s", [1, 2])
    result = transport(
        [_Statement("update t set a = ? where b = ?", (1, 2)) for _ in range(3)]
        + [_Statement("delete from t where b = ?", (JsonDocument({"b": 1}),))]
    )
    assert result == OrderedWriteResultComplete((1, 1, 1, 1))
    assert serialized == [6, 2, 2, 2, 2, 1]
    assert port.work() == lowering_support.FlushWork(
        statements=6, invocations=3, largest_ordered_invocation=4, largest_grouped_insert=3
    )
    port.reset()
    assert port.work() == lowering_support.FlushWork(0, 0, 0, 0)


def _observed_flush(
    case: lowering_support.CrossObjectCase, monkeypatch: pytest.MonkeyPatch
) -> tuple[lowering_support.OrderedAcceptingPort, list[str]]:
    """``case``'s flush through its own port, recording each read, statement,
    ordered invocation, mark, and completion as it happens."""
    events: list[str] = []
    port_type = type(lowering_support.flush_port(case))
    execute = port_type.execute
    execute_write = port_type.execute_write
    ordered_writes = port_type._ordered_writes  # pyright: ignore[reportPrivateUsage] - observing the transport
    complete = SourceAuthority.complete_write

    def reading(
        port: lowering_support.OrderedAcceptingPort,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        events.append("read")
        return execute(port, sql, binds, document_reads)

    def writing(
        port: lowering_support.OrderedAcceptingPort, sql: str, binds: Sequence[object]
    ) -> int:
        events.append("statement")
        return execute_write(port, sql, binds)

    def ordering(
        port: lowering_support.OrderedAcceptingPort, statements: Sequence[CanonicalWriteStatement]
    ) -> OrderedWriteResult:
        events.append("ordered")
        return ordered_writes(port, statements)

    def completing(owner: SourceAuthority, *args: Any, **kwargs: Any) -> None:
        events.append("complete")
        complete(owner, *args, **kwargs)

    monkeypatch.setattr(port_type, "execute", reading)
    monkeypatch.setattr(port_type, "execute_write", writing)
    monkeypatch.setattr(port_type, "_ordered_writes", ordering)
    monkeypatch.setattr(SourceAuthority, "complete_write", completing)
    port = lowering_support.flush_port(case)
    regions = lowering_support.FlushRegions(
        planning=lambda: events.append("planning"),
        planned=lambda: events.append("planned"),
        binding=lambda: events.append("binding"),
        bound=lambda: events.append("bound"),
        executing=lambda: events.append("executing"),
        executed=lambda: events.append("executed"),
    )
    with (
        lowering_support.flush_database(case, port) as handle,
        lowering_support.marked_flushes(regions),
    ):
        lowering_support.flush_objects(handle, case)
    return port, events


def _presented(invocations: int, inserts: int) -> list[str]:
    return ["ordered"] * invocations + ["statement"] * inserts


_GROUP_CALLS: Final[dict[str, list[list[str]]]] = {
    "cross-object.txtime.changed-64.columns.typed": [["ordered", "statement"]],
    "cross-object.txtime.changed-130.columns.typed": [["ordered", "statement"]] * 3,
    "cross-object.bitemporal.interior-64.document.wire": [
        ["ordered", "statement", "statement", "statement"]
    ],
    "cross-object.bitemporal.deferred-32x4.columns.typed": [_presented(2, 3)],
    "cross-object.bitemporal.deferred-32x12.document.wire": [_presented(6, 7)],
    "cross-object.bitemporal.requesting-32x12.document.wire": [_presented(6, 7)],
    "cross-object.bitemporal.deferred-32x32.columns.typed": [_presented(16, 17)],
    "cross-object.bitemporal.partial-3x66.columns.typed": [_presented(2, 2), _presented(2, 2)],
}
"""What each Write Group presents: its closes' ordered invocations, then its
openings' inserts."""


@pytest.mark.parametrize("case", lowering_support.CROSS_OBJECT_CASES, ids=lambda case: case.name)
def test_a_cross_object_flush_executes_its_groups_between_completions_outside_every_region(
    case: lowering_support.CrossObjectCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, events = _observed_flush(case, monkeypatch)
    calls = _GROUP_CALLS[case.name]
    # A deferred span reads coverage inside the advance binding the group the
    # read makes ready, one read before each group here, and a last advance
    # ends the span; a requesting flush precedes the read that causes it.
    advance = ["binding", "read", "bound"] if case.deferred else []
    assert events == [
        *(["read"] * max(len(case.reads), 1)),
        "planning",
        "planned",
        *(
            event
            for size, presented in zip(case.groups, calls, strict=True)
            for event in (*advance, "executing", *presented, "executed", *(["complete"] * size))
        ),
        *(["binding", "bound"] if case.deferred else []),
        *(["read"] if case.requesting else []),
    ]
    assert port.work() == case.work


_DEFERRED_GEOMETRY: Final[
    dict[str, tuple[tuple[tuple[int, int], ...], tuple[tuple[int, ...], ...]]]
] = {
    "cross-object.bitemporal.deferred-32x4.columns.typed": (((4, 6),) * 32, (tuple(range(32)),)),
    "cross-object.bitemporal.deferred-32x12.document.wire": (
        ((12, 14),) * 32,
        (tuple(range(32)),),
    ),
    "cross-object.bitemporal.requesting-32x12.document.wire": (
        ((12, 14),) * 32,
        (tuple(range(32)),),
    ),
    "cross-object.bitemporal.deferred-32x32.columns.typed": (
        ((32, 34),) * 32,
        (tuple(range(32)),),
    ),
    "cross-object.bitemporal.partial-3x66.columns.typed": (
        ((66, 67), (66, 67), (2, 2)),
        ((0,), (1, 2)),
    ),
}
"""Each deferred case's objects as (closes, openings) — a close per milestone
its window reaches, and an opening for its head, each amended milestone, and
its tail, where the window leaves them — and the objects each ready group
holds."""


def _calculated_work(name: str) -> lowering_support.FlushWork:
    """A deferred case's work under the realization contract: each group's
    closes in ordered invocations of at most 64, a lone remainder alone, and
    its openings in inserts of at most 64."""
    objects, groups = _DEFERRED_GEOMETRY[name]
    statements = invocations = 0
    for group in groups:
        closes = sum(objects[index][0] for index in group)
        inserts = -(-sum(objects[index][1] for index in group) // 64)
        full, rest = divmod(closes, 64)
        statements += closes + inserts
        invocations += full + (1 if rest else 0) + inserts
    return lowering_support.FlushWork(statements, invocations, 64, 64)


def test_each_cross_object_flush_writes_every_object_through_its_capped_call_shapes() -> None:
    for case in lowering_support.CROSS_OBJECT_CASES:
        port = lowering_support.flush_port(case)
        with (
            lowering_support.flush_database(case, port) as handle,
            lowering_support.marked_flushes(lowering_support.FlushRegions()),
        ):
            lowering_support.flush_objects(handle, case)
            first = port.work()
            port.reset()
            lowering_support.flush_objects(handle, case)
        assert first == port.work() == case.work, case.name
        if case.deferred:
            assert case.work == _calculated_work(case.name), case.name
            assert isinstance(port, lowering_support.SpanAcceptingPort)
            assert port.coverage_reads == case.coverage_reads == len(case.groups)
            continue
        successors = 3 if case.bounded else 1
        largest = case.work.largest_grouped_insert
        assert case.work.largest_ordered_invocation == largest == 64
        inserts = sum(-(-size * successors // largest) for size in case.groups)
        assert case.work.statements == case.objects + inserts
        assert case.work.invocations == len(case.groups) + inserts


def test_a_requesting_deferred_flush_hands_each_write_the_rows_its_source_continues() -> None:
    # Each source read one whole milestone, which its amendment leaves as a
    # head before the read instant and an amended piece after it: the two
    # rows a later submission of the source may continue from. A concluding
    # pre-commit flush demands and captures none.
    complete = SourceAuthority.complete_write
    handed: list[int] = []

    def completing(
        owner: SourceAuthority, effects: Any, allocated: Any, *, captured: Any = ()
    ) -> None:
        handed.append(len(captured))
        complete(owner, effects, allocated, captured=captured)

    captured: dict[str, int] = {}
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(SourceAuthority, "complete_write", completing)
        for case in lowering_support.DEFERRED_CASES:
            handed.clear()
            with lowering_support.flush_database(case) as handle:
                lowering_support.flush_objects(handle, case)
            captured[case.name] = sum(handed)
    assert captured == {
        case.name: 2 * case.objects if case.requesting else 0
        for case in lowering_support.DEFERRED_CASES
    }


def test_marked_flushes_restore_production_on_every_exit() -> None:
    finalize = WritePlanner.finalize
    advance = RangeBindings.__next__
    execute = WriteStepExecutor.execute
    with lowering_support.marked_flushes(lowering_support.FlushRegions()):
        assert WritePlanner.finalize is not finalize
        assert RangeBindings.__next__ is not advance
        assert WriteStepExecutor.execute is not execute
    assert WritePlanner.finalize is finalize
    assert RangeBindings.__next__ is advance
    assert WriteStepExecutor.execute is execute
    with (
        pytest.raises(RuntimeError, match="left"),
        lowering_support.marked_flushes(lowering_support.FlushRegions()),
    ):
        raise RuntimeError("left")
    assert WritePlanner.finalize is finalize
    assert RangeBindings.__next__ is advance
    assert WriteStepExecutor.execute is execute
