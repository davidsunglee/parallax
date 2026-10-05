from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

import write_lowering_overhead as report
from durations import Spans
from interpreter_matrix import CURRENT_MINOR, IDENTITY_SCRIPT, supported_minors
from parallax.conformance import workloads
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import validate
from parallax.core.base import detach_json_container
from parallax.core.db_port import DocumentReadOrdinals, JsonDocument, Row
from parallax.core.unit_work import (
    BufferItem,
    MaterializedWriteGroup,
    PredecessorRows,
    UnitOfWork,
)
from tests.unit import _leaf_type_support as leaf_support
from tests.unit import _predicate_acquisition_support as acquisition_support
from tests.unit import _write_lowering_support as lowering_support
from tests.unit.tools._provenance_support import pin_dirty_tree

_CATEGORICAL_OPERATIONS = {
    "txtime": ("opening", "changed", "unchanged"),
    "plain": ("changed",),
    "bitemporal": ("interior",),
}


def _child_document(case: str, overrides: Mapping[str, object] | None = None) -> dict[str, object]:
    window = report.WINDOWS[case]
    document: dict[str, object] = {
        "case": case,
        "window": window,
        "units": 2,
        "samples": {
            "elapsedUs": [10.0, 12.0, 11.0] * 3,
            "transientBytes": [100.0] * report.MEASURED,
            "retainedBytes": [50.0],
        },
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
def test_the_matrix_names_every_keyed_acquisition_and_model_case_once() -> None:
    keyed = [case.name for case in lowering_support.CASES]
    leaf_keyed = [
        case.name for case in lowering_support.CASES if case.family == lowering_support.LEAF_FAMILY
    ]
    acquisition = [case.name for case in acquisition_support.CASES]
    leaf_acquisition = [case.name for case in acquisition_support.LEAF_CASES]
    response = [case.name for case in lowering_support.RESPONSE_CASES]
    assert (
        *keyed,
        *acquisition,
        *leaf_acquisition,
        *response,
        report.MODEL_CASE,
        report.MODEL_FAMILY_CASE,
    ) == report.CASE_NAMES
    assert len(set(report.CASE_NAMES)) == len(report.CASE_NAMES)
    assert (*response, report.MODEL_FAMILY_CASE) == report.CONTROL_CASE_NAMES
    assert (*leaf_keyed, *leaf_acquisition) == report.LEAF_TYPE_CASE_NAMES
    target = [case.name for case in lowering_support.CASES if case.addressed]
    assert tuple(target) == report.TARGET_CASE_NAMES
    before_targets = [name for name in keyed if name not in target]
    assert (
        *before_targets,
        *acquisition,
        *leaf_acquisition,
        *response,
        report.MODEL_CASE,
        report.MODEL_FAMILY_CASE,
    ) == report.BEFORE_TARGET_CASE_NAMES
    before_leaf_types = [name for name in before_targets if name not in leaf_keyed]
    assert (
        *before_leaf_types,
        *acquisition,
        *response,
        report.MODEL_CASE,
        report.MODEL_FAMILY_CASE,
    ) == report.BEFORE_LEAF_TYPE_CASE_NAMES
    assert (*before_leaf_types, *acquisition, report.MODEL_CASE) == report.LEGACY_CASE_NAMES
    assert report.CASE_COVERAGES == {
        "current": report.CASE_NAMES,
        "before target writes": report.BEFORE_TARGET_CASE_NAMES,
        "before leaf types": report.BEFORE_LEAF_TYPE_CASE_NAMES,
        "legacy": report.LEGACY_CASE_NAMES,
    }
    assert len(supported_minors()) == 2


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
    "plain": "plain.changed",
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
        writes = ["write"] * case.statements
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
        case.mutation == "update" and case.statements == 2 and case.stored is not None
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


def test_acquisition_cases_cover_every_row_level_under_both_layouts() -> None:
    assert {case.name for case in acquisition_support.CASES} == {
        f"acquisition.{level.id}.{layout}"
        for level in workloads.ACQUISITION_LEVELS
        for layout in workloads.STRUCTURAL_LAYOUTS
    }
    assert all(
        report.WINDOWS[case.name] == report.ACQUISITION_WINDOW for case in acquisition_support.CASES
    )
    assert report.WINDOWS[report.MODEL_CASE] == report.MODEL_WINDOW


def test_leaf_type_acquisition_covers_every_acquired_type_and_level_under_both_layouts() -> None:
    assert {case.name for case in acquisition_support.LEAF_CASES} == {
        f"leaf-acquisition.{type_id}.{level.id}.{layout}"
        for type_id in (workloads.LEAF_CONTROL_TYPE_ID, *workloads.LEAF_TYPE_IDS)
        for level in workloads.leaf_acquisition_levels()
        for layout in workloads.STRUCTURAL_LAYOUTS
    }
    assert all(
        report.WINDOWS[case.name] == report.ACQUISITION_WINDOW and case.model is leaf_support.MODEL
        for case in acquisition_support.LEAF_CASES
    )


# --------------------------------------------------------------------------- #
# The fixture: what each keyed case lowers to, and what the driver dumps.      #
# --------------------------------------------------------------------------- #
def _documents(statement_binds: Sequence[object]) -> list[object]:
    return [bind.value for bind in statement_binds if isinstance(bind, JsonDocument)]


def _stored_document(case: lowering_support.Case) -> Mapping[str, object]:
    """The Structured Column of the Relational Document row ``case`` revises."""
    assert case.layout == "document" and case.stored is not None
    return cast("Mapping[str, object]", case.stored["payload"])


@pytest.mark.parametrize("case", lowering_support.CASES, ids=lambda case: case.name)
def test_every_keyed_case_lowers_to_its_stated_statements_and_dumps_each_document(
    case: lowering_support.Case,
) -> None:
    lowered = lowering_support.lowered(case)
    assert len(lowered) == case.statements
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
        _close, head, middle, tail = lowering_support.lowered(case)
        titles = [
            next(bind for bind in statement.binds if isinstance(bind, str) and "title" in bind)
            if layout == "columns"
            else cast("Mapping[str, object]", _documents(statement.binds)[0])["title"]
            for statement in (head, middle, tail)
        ]
        assert titles == ["title-before", "title-middle", "title-before"]


def test_a_non_temporal_changed_update_revises_the_row_it_read_in_place() -> None:
    for layout in lowering_support.LAYOUTS:
        case = lowering_support.case_named(f"plain.changed.{layout}.typed")
        assert case.stored is not None
        (statement,) = lowering_support.lowered(case)
        assert statement.sql.startswith("update ")


class _CountingPort(acquisition_support.AcquisitionPort):
    reads = 0
    delivered = 0

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        rows = super().execute(sql, binds, document_reads)
        type(self).reads += 1
        type(self).delivered += len(rows)
        return rows


def test_acquisition_resolves_every_row_once_and_stops_before_any_flush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquisition_support, "AcquisitionPort", _CountingPort)
    buffered: list[MaterializedWriteGroup] = []
    buffer = UnitOfWork.buffer

    def recording_buffer(uow: UnitOfWork, instruction: BufferItem) -> None:
        if isinstance(instruction, MaterializedWriteGroup):
            buffered.append(instruction)
        buffer(uow, instruction)

    monkeypatch.setattr(UnitOfWork, "buffer", recording_buffer)
    for case in (*acquisition_support.CASES, *acquisition_support.LEAF_CASES):
        _CountingPort.reads = 0
        _CountingPort.delivered = 0
        buffered.clear()
        marks: list[str] = []
        with acquisition_support.database(case) as handle:
            acquisition_support.acquire(
                handle,
                case,
                opened=lambda marks=marks: marks.append("opened"),
                closed=lambda marks=marks: marks.append("closed"),
            )
        assert marks == ["opened", "closed"]
        assert _CountingPort.reads == 1
        assert _CountingPort.delivered == case.rows
        # What the window leaves buffered is one group retaining every
        # resolved row's judged positional state, and no per-row row view.
        (group,) = buffered
        evidence = group.evidence
        assert isinstance(evidence, PredecessorRows)
        assert len(evidence) == case.rows
        assert (evidence.documents is None) == (case.layout == "columns")
        assert all(type(row) is tuple for row in evidence.rows)
        ((assigned, value),) = case.changes.items()
        assert all(
            (row if case.layout == "columns" else cast("Mapping[str, object]", row["payload"]))[
                assigned
            ]
            != value
            for row in acquisition_support.AcquisitionPort(case.stored, case.rows).rows()
        )


def test_the_workload_digest_covers_every_defining_source(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = lowering_support.write_lowering_digest()
    assert len(digest) == 64
    with monkeypatch.context() as patched:
        patched.setattr(workloads, "READ_GEOMETRY_ROOTS", workloads.READ_GEOMETRY_ROOTS + 1)
        assert lowering_support.write_lowering_digest() != digest
    monkeypatch.setattr(workloads, "LEAF_TYPE_RUNTIMES", 2)
    assert lowering_support.write_lowering_digest() != digest


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
    for case in (acquisition_support.CASES[0].name, report.MODEL_CASE):
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
        report.ACQUISITION_WINDOW,
        report.RESPONSE_WINDOW,
        report.MODEL_WINDOW,
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
    assert report.selected_cases(["acquisition.rows-8.*"]) == (
        "acquisition.rows-8.columns",
        "acquisition.rows-8.document",
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


def test_the_control_cases_are_the_difference_between_the_two_earlier_case_coverages() -> None:
    before_leaf_types = report.expected_addresses(
        ("3.14",), report.CALL_NAMES, report.BEFORE_LEAF_TYPE_CASE_NAMES
    )
    legacy = report.expected_addresses(("3.14",), report.CALL_NAMES, report.LEGACY_CASE_NAMES)
    assert legacy < before_leaf_types
    assert before_leaf_types - legacy == {
        ("3.14", case, metric) for case in report.CONTROL_CASE_NAMES for metric in report.METRICS
    }
    assert all(not address[2].startswith("calls.") for address in before_leaf_types - legacy)


def test_the_leaf_type_cases_are_the_difference_the_leaf_type_coverage_tier_adds() -> None:
    before_targets = report.expected_addresses(
        ("3.14",), report.CALL_NAMES, report.BEFORE_TARGET_CASE_NAMES
    )
    before_leaf_types = report.expected_addresses(
        ("3.14",), report.CALL_NAMES, report.BEFORE_LEAF_TYPE_CASE_NAMES
    )
    assert before_leaf_types < before_targets
    assert {case for _runtime, case, _cell in before_targets - before_leaf_types} == set(
        report.LEAF_TYPE_CASE_NAMES
    )


def test_the_target_cases_are_the_difference_between_the_two_latest_case_coverages() -> None:
    runtimes = supported_minors()
    current = report.expected_addresses(runtimes)
    before_targets = report.expected_addresses(
        runtimes, report.CALL_NAMES, report.BEFORE_TARGET_CASE_NAMES
    )
    assert before_targets < current
    assert current - before_targets == {
        (runtime, case, cell)
        for runtime in runtimes
        for case in report.TARGET_CASE_NAMES
        for cell in (*report.METRICS, *(f"calls.{name}" for name in report.CALL_NAMES))
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
