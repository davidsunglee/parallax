from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

import write_lowering_overhead as report
from interpreter_matrix import CURRENT_MINOR, supported_minors
from parallax.conformance import workloads
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import validate
from parallax.core.db_port import DocumentReadOrdinals, JsonDocument, Row
from parallax.core.entity import EntityRowCodec
from parallax.core.unit_work import TemporalObservation, WritePlanner
from parallax.snapshot.handle import build_write_planner
from tests.unit import _predicate_acquisition_support as acquisition_support
from tests.unit import _write_lowering_support as lowering_support

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


def _collaborators() -> tuple[EntityRowCodec, WritePlanner]:
    return EntityRowCodec(lowering_support.CATALOG), build_write_planner(
        lowering_support.CATALOG.meta
    )


# --------------------------------------------------------------------------- #
# The matrix: every case the protocol names, on every supported minor.         #
# --------------------------------------------------------------------------- #
def test_the_matrix_names_every_keyed_acquisition_and_model_case_once() -> None:
    keyed = [case.name for case in lowering_support.CASES]
    acquisition = [case.name for case in acquisition_support.CASES]
    assert (*keyed, *acquisition, report.MODEL_CASE) == report.CASE_NAMES
    assert len(set(report.CASE_NAMES)) == len(report.CASE_NAMES)
    assert len(supported_minors()) == 2


def test_twenty_categorical_cases_cross_every_layout_and_ingress() -> None:
    categorical = [
        case for case in lowering_support.CASES if case.family in _CATEGORICAL_OPERATIONS
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


def test_geometry_cases_cover_every_level_under_both_layouts_through_typed_inserts() -> None:
    geometry = [case for case in lowering_support.CASES if case.family.startswith("geometry-")]
    assert {case.name for case in geometry} == {
        f"geometry.{level.id}.{layout}.typed"
        for level in workloads.GEOMETRY_LEVELS
        for layout in workloads.STRUCTURAL_LAYOUTS
    }
    assert all(case.mutation == "insert" and case.observation is None for case in geometry)


def test_changed_ancestor_cases_succeed_a_milestone_at_every_manifest_width() -> None:
    ancestors = [case for case in lowering_support.CASES if case.family.startswith("ancestor-")]
    assert {case.name for case in ancestors} == {
        f"ancestor.{level_id}.{layout}.typed"
        for level_id in workloads.ANCESTOR_LEVEL_IDS
        for layout in workloads.STRUCTURAL_LAYOUTS
    }
    assert {level.width for level in workloads.ancestor_levels()} == {4, 16, 64}
    assert all(
        case.mutation == "update"
        and case.statements == 2
        and isinstance(case.observation, TemporalObservation)
        for case in ancestors
    )
    assert all(report.WINDOWS[case.name] == report.KEYED_WINDOW for case in ancestors)


def test_a_changed_ancestor_patches_one_root_leaf_and_carries_every_other_member() -> None:
    codec, planner = _collaborators()
    for level_id in workloads.ANCESTOR_LEVEL_IDS:
        case = lowering_support.case_named(f"ancestor.{level_id}.document.typed")
        observation = case.observation
        assert isinstance(observation, TemporalObservation)
        predecessor = cast("Mapping[str, object]", observation.predecessor.document)
        (_close, _), (insert, _) = lowering_support.lowered(case, codec, planner)
        (successor,) = _documents(insert.binds)
        root = cast("Mapping[str, object]", cast("Mapping[str, object]", successor)["body"])
        before = cast("Mapping[str, object]", predecessor["body"])
        assert root["f0"] != before["f0"]
        assert {name: root[name] for name in before if name != "f0"} == {
            name: before[name] for name in before if name != "f0"
        }
        assert cast("Mapping[str, object]", successor)["items"] == predecessor["items"]


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


# --------------------------------------------------------------------------- #
# The fixture: what each keyed case lowers to, and what the driver dumps.      #
# --------------------------------------------------------------------------- #
def _documents(statement_binds: Sequence[object]) -> list[object]:
    return [bind.value for bind in statement_binds if isinstance(bind, JsonDocument)]


@pytest.mark.parametrize("case", lowering_support.CASES, ids=lambda case: case.name)
def test_every_keyed_case_lowers_to_its_stated_statements_and_dumps_each_document(
    case: lowering_support.Case,
) -> None:
    codec, planner = _collaborators()
    lowered = lowering_support.lowered(case, codec, planner)
    assert len(lowered) == case.statements
    for statement, dumped in lowered:
        assert len(dumped) == len(statement.binds)
        for bind, buffer in zip(statement.binds, dumped, strict=True):
            if isinstance(bind, JsonDocument):
                assert bytes(buffer or b"") == json.dumps(bind.value).encode()


def test_typed_and_wire_ingress_lower_to_the_same_statements() -> None:
    codec, planner = _collaborators()
    by_name = {case.name: case for case in lowering_support.CASES}
    for case in lowering_support.CASES:
        if case.ingress != "typed" or case.family.startswith(("geometry-", "ancestor-")):
            continue
        twin = by_name[case.name.removesuffix(".typed") + ".wire"]
        typed = lowering_support.lowered(case, codec, planner)
        wire = lowering_support.lowered(twin, codec, planner)
        assert [statement.sql for statement, _ in typed] == [statement.sql for statement, _ in wire]
        assert [statement.binds for statement, _ in typed] == [
            statement.binds for statement, _ in wire
        ]


def test_an_unchanged_successor_carries_its_predecessor_and_a_changed_one_replaces_it() -> None:
    codec, planner = _collaborators()
    unchanged = lowering_support.case_named("txtime.unchanged.document.typed")
    changed = lowering_support.case_named("txtime.changed.document.typed")
    for case in (unchanged, changed):
        observation = case.observation
        assert isinstance(observation, TemporalObservation)
        predecessor = observation.predecessor.document
        (_close, _), (insert, _) = lowering_support.lowered(case, codec, planner)
        (successor,) = _documents(insert.binds)
        if case is unchanged:
            assert successor == predecessor
        else:
            assert successor != predecessor
            assert cast("Mapping[str, object]", successor)["title"] == "title-after"


def test_a_bitemporal_interior_update_carries_head_and_tail_and_changes_the_middle() -> None:
    codec, planner = _collaborators()
    for layout in lowering_support.LAYOUTS:
        case = lowering_support.case_named(f"bitemporal.interior.{layout}.typed")
        _close, head, middle, tail = lowering_support.lowered(case, codec, planner)
        titles = [
            next(bind for bind in statement.binds if isinstance(bind, str) and "title" in bind)
            if layout == "columns"
            else cast("Mapping[str, object]", _documents(statement.binds)[0])["title"]
            for statement, _ in (head, middle, tail)
        ]
        assert titles == ["title-before", "title-middle", "title-before"]


def test_a_non_temporal_changed_update_revises_in_place_without_a_predecessor() -> None:
    codec, planner = _collaborators()
    for layout in lowering_support.LAYOUTS:
        case = lowering_support.case_named(f"plain.changed.{layout}.typed")
        assert case.observation is None
        ((statement, _),) = lowering_support.lowered(case, codec, planner)
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
    for case in acquisition_support.CASES:
        _CountingPort.reads = 0
        _CountingPort.delivered = 0
        marks: list[str] = []
        handle = acquisition_support.database(case)
        try:
            acquisition_support.acquire(
                handle,
                case,
                opened=lambda marks=marks: marks.append("opened"),
                closed=lambda marks=marks: marks.append("closed"),
            )
        finally:
            handle.close()
        assert marks == ["opened", "closed"]
        assert _CountingPort.reads == 1
        assert _CountingPort.delivered == case.rows
        assert all(
            row["title"] != acquisition_support.ASSIGNED_TITLE
            if case.layout == "columns"
            else cast("Mapping[str, object]", row["payload"])["title"]
            != acquisition_support.ASSIGNED_TITLE
            for row in acquisition_support.AcquisitionPort(case.layout, case.rows).rows()
        )


def test_the_workload_digest_covers_every_defining_source(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = lowering_support.write_lowering_digest()
    assert len(digest) == 64
    monkeypatch.setattr(workloads, "READ_GEOMETRY_ROOTS", workloads.READ_GEOMETRY_ROOTS + 1)
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
    assert envelope.provenance.workload_digest == report.evidence_digest()
    assert envelope.provenance.sampling["retainedWarmups"] == 200
    assert set(cast("Mapping[str, str]", envelope.provenance.sampling["windows"])) == {
        report.KEYED_WINDOW,
        report.ACQUISITION_WINDOW,
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


# Review Cadence requires a fresh capture whenever an instrument changes, so the
# digest a capture records has to move when one does.
def test_the_evidence_digest_covers_the_instruments_that_took_the_readings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instrument = tmp_path / "write_lowering_reading.py"
    instrument.write_text("# an instrument\n", encoding="utf-8")
    monkeypatch.setattr(report, "INSTRUMENTS", (instrument,))
    original = report.evidence_digest()
    instrument.write_text("# an edited instrument\n", encoding="utf-8")
    assert report.evidence_digest() != original
    assert report.evidence_digest() != lowering_support.write_lowering_digest()


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
    assert document["unavailable"] == ["CPython 3.14, model.prepared: model.prepared refused"]
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
