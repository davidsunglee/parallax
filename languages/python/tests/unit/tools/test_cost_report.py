from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Sequence
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import cost_report
import instance_state_overhead as instance_report
import write_lowering_overhead as write_report
from cost_report import (
    COLLECTION_SPAN,
    DURATIONS_FILE,
    DURATIONS_OPTION,
    MEMBERS,
    METADATA_OPTION,
    Collection,
    Member,
    MemberResult,
    advisories,
    collect,
    compare,
    portfolio_document,
    report_recipes,
    validate_snapshot_matrix,
    validate_write_lowering_matrix,
    verify,
)
from durations import SCHEMA_VERSION, Spans
from interpreter_matrix import (
    RuntimeIdentity,
    RuntimeStatus,
    RuntimeUnavailable,
    authority_minor,
    supported_minors,
    write_metadata,
)
from parallax.conformance.budget import BudgetContract, MemoryGate, MemoryGates
from parallax.conformance.cost_envelope import CostReportEnvelope, validate
from snapshot_delivery_overhead import (
    ChildReading,
    addresses,
    build_envelope,
    canary,
    expanded_cells,
    expected_readings,
    is_memory_cell,
    unit,
)
from tests.unit.tools._cost_report_support import complete_instance_state


def _just_report_recipes() -> frozenset[str]:
    completed = subprocess.run(
        ["just", "--dump", "--dump-format", "json"],
        cwd=Path(__file__).resolve().parents[4],
        capture_output=True,
        text=True,
        check=True,
    )
    document = cast("dict[str, Any]", json.loads(completed.stdout))
    recipes = cast("dict[str, object]", document["recipes"])
    return frozenset(
        name
        for name in recipes
        if name.startswith("python-report-") and name != "python-report-cost"
    )


def _canary_provenance(contract: BudgetContract) -> Any:
    return canary(
        contract,
        lambda _request: ChildReading(1.0, "ms", (1.0,) * contract.timing_measured),
    ).provenance


def _complete_snapshot(contract: BudgetContract) -> dict[str, Any]:
    runtimes = supported_minors()
    limits = {(cell.workload, cell.path): float(cell.value) for cell in expanded_cells(contract)}
    results: dict[tuple[str, str, str], tuple[ChildReading, ...]] = {}
    for runtime, workload, path in addresses(contract, runtimes):
        count = expected_readings(contract, path)
        value = limits.get((workload, path), 1.0)
        samples = () if is_memory_cell(path) else (value,) * contract.timing_measured
        results[(runtime, workload, path)] = tuple(
            ChildReading(value, unit(path), samples) for _ in range(count)
        )
    return build_envelope(contract, _canary_provenance(contract), results, runtimes).document()


def _complete_write(contract: BudgetContract) -> dict[str, Any]:
    matrix: write_report.Matrix = {
        runtime: {
            case: write_report._canary_reading(case)  # pyright: ignore[reportPrivateUsage] - canary seam
            for case in write_report.CASE_NAMES
        }
        for runtime in supported_minors()
    }
    return write_report.build_envelope(
        contract,
        write_report._provenance(contract, matrix),  # pyright: ignore[reportPrivateUsage] - entrypoint seam
        matrix,
    ).document()


def _clean(document: dict[str, Any], contract: BudgetContract, *, authoritative: bool) -> None:
    provenance = cast("dict[str, Any]", document["provenance"])
    provenance["dirty"] = False
    if authoritative:
        provenance.update(dict(contract.authority))
        document["authority"] = "authoritative"


def _portfolio(*members: dict[str, Any]) -> dict[str, Any]:
    return {"schemaVersion": 1, "members": list(members), "failures": []}


def _verifiable(contract: BudgetContract) -> dict[str, Any]:
    snapshot = _complete_snapshot(contract)
    write = _complete_write(contract)
    _clean(snapshot, contract, authoritative=True)
    _clean(write, contract, authoritative=False)
    return _portfolio(snapshot, write)


def _optional_document(member: Member) -> dict[str, object]:
    contract = BudgetContract.load()
    return CostReportEnvelope(
        member.subject, _canary_provenance(contract), "non-authoritative"
    ).document()


def _clear_readings(document: dict[str, Any]) -> None:
    cast("list[object]", document["readings"]).clear()


def _clear_comparisons(document: dict[str, Any]) -> None:
    cast("list[object]", document["comparisons"]).clear()


def _duplicate_reading(document: dict[str, Any]) -> None:
    readings = cast("list[dict[str, object]]", document["readings"])
    readings.append(deepcopy(readings[0]))


def _wrong_reading_unit(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["readings"])[0]["unit"] = "wrong"


def _wrong_window(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["readings"])[0]["window"] = "elsewhere"


def _remove_samples(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["readings"])[0]["samples"] = []


def _forge_value(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["readings"])[0]["value"] = -1


def _forge_outcome(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["comparisons"])[0]["outcome"] = "outside"


def _add_comparison(document: dict[str, Any]) -> None:
    cast("list[object]", document["comparisons"]).append(
        {"workload": "w", "cell": "c", "operator": "at-most", "limit": 1, "unit": "us"}
    )


def _drop_a_runtime(document: dict[str, Any]) -> None:
    readings = cast("list[dict[str, object]]", document["readings"])
    readings[:] = [reading for reading in readings if reading["runtime"] == supported_minors()[0]]


def _published(_commit: str) -> bool:
    return True


def _unpublished(_commit: str) -> bool:
    return False


def _no_validation(_document: object) -> None:
    return None


def _no_matrix_validation(*_arguments: object, **_options: object) -> None:
    return None


def _snapshot_of(document: dict[str, Any]) -> dict[str, Any]:
    return next(m for m in document["members"] if m["subject"] == "snapshot-delivery")


def _write_of(document: dict[str, Any]) -> dict[str, Any]:
    return next(m for m in document["members"] if m["subject"] == write_report.SUBJECT)


def _first_comparison(document: dict[str, Any], *, timing: bool) -> dict[str, Any]:
    return next(
        comparison
        for comparison in document["comparisons"]
        if (comparison["unit"] in cost_report.TIMING_UNITS) == timing
    )


def _push_outside(snapshot: dict[str, Any], comparison: dict[str, Any]) -> None:
    compared = authority_minor(BudgetContract.load().authority)
    for reading in snapshot["readings"]:
        if (reading["runtime"], reading["workload"], reading["cell"]) == (
            compared,
            comparison["workload"],
            comparison["cell"],
        ):
            factor = 0.5 if comparison["operator"] == "at-least" else 2
            reading["value"] = comparison["limit"] * factor
            reading["samples"] = [reading["value"]] * len(reading["samples"])
    comparison["outcome"] = "outside"


# --------------------------------------------------------------------------- #
# Collection                                                                   #
# --------------------------------------------------------------------------- #
def test_collector_members_are_the_python_report_command_graph() -> None:
    assert report_recipes() == _just_report_recipes()
    assert {member.subject for member in MEMBERS if member.required} == {
        "snapshot-delivery",
        write_report.SUBJECT,
    }


def test_collection_attempts_every_member_and_fails_late_for_a_required_one() -> None:
    attempted: list[str] = []

    def failing(member: Member, _arguments: Sequence[str]) -> tuple[int, str, str]:
        attempted.append(member.recipe)
        return (7, "", f"{member.recipe} failed")

    collection = collect(failing)
    assert attempted == [member.recipe for member in MEMBERS]
    assert len(collection.results) == len(MEMBERS)
    assert collection.failed_required
    assert [span.name for span in collection.durations.spans] == [
        *(member.subject for member in MEMBERS),
        COLLECTION_SPAN,
    ]


def test_portfolio_document_preserves_optional_failures() -> None:
    optional = MEMBERS[1]
    document = portfolio_document((MemberResult(optional, None, "unavailable"),))
    assert document["failures"] == [
        {"recipe": optional.recipe, "required": False, "message": "unavailable"}
    ]


def test_outside_budget_outcomes_do_not_fail_collection() -> None:
    contract = BudgetContract.load()
    snapshot = _complete_snapshot(contract)
    _push_outside(snapshot, _first_comparison(snapshot, timing=False))
    write = _complete_write(contract)

    def run(member: Member, _arguments: Sequence[str]) -> tuple[int, str, str]:
        if member.subject == "snapshot-delivery":
            return (0, json.dumps(snapshot), "")
        if member.subject == write_report.SUBJECT:
            return (0, json.dumps(write), "")
        return (9, "", "optional report unavailable")

    collection = collect(run)
    assert not collection.failed_required
    assert collection.results[0].envelope is not None


def test_collection_decodes_each_members_own_envelope() -> None:
    contract = BudgetContract.load()
    snapshot = _complete_snapshot(contract)
    write = _complete_write(contract)

    def run(member: Member, _arguments: Sequence[str]) -> tuple[int, str, str]:
        document = (
            snapshot
            if member.subject == "snapshot-delivery"
            else write
            if member.subject == write_report.SUBJECT
            else _optional_document(member)
        )
        return (0, json.dumps(document), "")

    collection = collect(run)
    assert not collection.failed_required
    assert [result.envelope["subject"] for result in collection.results if result.envelope] == [
        member.subject for member in MEMBERS
    ]
    summary = cost_report._summary(  # pyright: ignore[reportPrivateUsage] - rendered output under test
        portfolio_document(collection.results)
    )
    assert ", ".join(supported_minors()) in summary


# --------------------------------------------------------------------------- #
# Durations: telemetry beside the evidence, never part of it                  #
# --------------------------------------------------------------------------- #
class _Clocks:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.wall = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)

    def advance(self, seconds: float) -> None:
        self.elapsed += seconds
        self.wall += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self.elapsed

    def now(self) -> datetime:
        return self.wall


def _sidecar_path(arguments: Sequence[str]) -> Path:
    assert list(arguments[:1]) == [DURATIONS_OPTION]
    assert list(arguments[2:3]) == [METADATA_OPTION]
    assert len(arguments) == 4
    assert Path(arguments[3]).parent == Path(arguments[1]).parent
    return Path(arguments[1])


def _member_sidecar(*spans: dict[str, object]) -> str:
    return json.dumps({"schemaVersion": SCHEMA_VERSION, "spans": list(spans), "unavailable": []})


def test_collection_asks_each_member_for_a_sidecar_and_folds_only_what_decodes() -> None:
    contract = BudgetContract.load()
    snapshot = _complete_snapshot(contract)
    write = _complete_write(contract)
    clocks = _Clocks()
    asked: dict[str, Path] = {}

    def run(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        sidecar = _sidecar_path(arguments)
        asked[member.subject] = sidecar
        clocks.advance(10.0)
        if member.subject == "snapshot-delivery":
            sidecar.write_text(
                _member_sidecar(
                    {
                        "scope": "workload",
                        "name": "conventional-fanout",
                        "labels": {"runtime": "3.13"},
                        "startedAt": "2026-09-18T12:00:01+00:00",
                        "seconds": 4.0,
                    }
                ),
                encoding="utf-8",
            )
            return (0, json.dumps(snapshot), "")
        if member.subject == "lifecycle-overhead":
            sidecar.write_text(_member_sidecar(), encoding="utf-8")
            return (0, json.dumps(_optional_document(member)), "")
        if member.subject == "instance-state":
            sidecar.write_text('{"schemaVersion": 1, "spans": "none"}', encoding="utf-8")
            return (4, "", "the matrix is incomplete")
        return (0, json.dumps(write), "")

    collection = collect(run, Spans(clock=clocks.monotonic, now=clocks.now))
    assert not collection.failed_required
    assert set(asked) == {member.subject for member in MEMBERS}
    assert {path.name for path in asked.values()} == {f"{subject}.json" for subject in asked}
    assert len({path.parent for path in asked.values()}) == 1
    assert not any(path.parent.exists() for path in asked.values())
    recorded = [
        (span.scope, span.name, dict(span.labels), span.seconds)
        for span in collection.durations.spans
    ]
    assert recorded == [
        ("member", "snapshot-delivery", {"member": "snapshot-delivery"}, 10.0),
        (
            "workload",
            "conventional-fanout",
            {"member": "snapshot-delivery", "runtime": "3.13"},
            4.0,
        ),
        ("member", "lifecycle-overhead", {"member": "lifecycle-overhead"}, 10.0),
        ("member", "instance-state", {"member": "instance-state"}, 10.0),
        ("member", write_report.SUBJECT, {"member": write_report.SUBJECT}, 10.0),
        ("collection", COLLECTION_SPAN, {}, 40.0),
    ]
    assert [(entry.name, entry.reason) for entry in collection.durations.unavailable] == [
        (
            "instance-state",
            "the member's durations sidecar does not decode: "
            f"{asked['instance-state']} spans is not a list",
        ),
        (write_report.SUBJECT, "the member wrote no durations sidecar"),
    ]
    assert collection.results[2].failure == "exit 4: the matrix is incomplete"


def test_written_output_keeps_the_legacy_portfolio_beside_the_durations_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = BudgetContract.load()
    snapshot = _complete_snapshot(contract)
    write = _complete_write(contract)

    def run(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        _sidecar_path(arguments).write_text(_member_sidecar(), encoding="utf-8")
        document = (
            snapshot
            if member.subject == "snapshot-delivery"
            else write
            if member.subject == write_report.SUBJECT
            else _optional_document(member)
        )
        return (0, json.dumps(document), "")

    monkeypatch.setattr(cost_report, "run_member", run)
    out = tmp_path / "reports"
    assert cost_report.main(["--out", str(out)]) == 0
    assert sorted(path.name for path in out.iterdir()) == sorted(
        [
            "portfolio.json",
            "summary.md",
            DURATIONS_FILE,
            cost_report.CONDITIONS_FILE,
            *(f"{m.subject}.json" for m in MEMBERS),
        ]
    )
    portfolio = cast("dict[str, Any]", json.loads((out / "portfolio.json").read_text("utf-8")))
    assert set(portfolio) == {"schemaVersion", "members", "failures"}
    assert portfolio["schemaVersion"] == 1
    assert [member["subject"] for member in portfolio["members"]] == [m.subject for m in MEMBERS]
    assert portfolio["failures"] == []
    durations = Spans.load(out / DURATIONS_FILE)
    assert [span.name for span in durations.spans] == [
        *(member.subject for member in MEMBERS),
        COLLECTION_SPAN,
    ]
    assert durations.unavailable == ()
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert summary.startswith("# Python cost report\n")
    assert "## Durations" in summary
    assert f"the `{COLLECTION_SPAN}` collection span" in summary
    assert capsys.readouterr().out == summary


def test_a_failed_required_member_still_leaves_every_output_and_its_attribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(member: Member, _arguments: Sequence[str]) -> tuple[int, str, str]:
        if member.subject == "snapshot-delivery":
            return (1, "", "no database")
        return (0, json.dumps(_optional_document(member)), "")

    monkeypatch.setattr(cost_report, "run_member", run)
    out = tmp_path / "reports"
    assert cost_report.main(["--out", str(out)]) == 1
    durations = Spans.load(out / DURATIONS_FILE)
    assert [span.name for span in durations.spans] == [
        *(member.subject for member in MEMBERS),
        COLLECTION_SPAN,
    ]
    assert [entry.name for entry in durations.unavailable] == [m.subject for m in MEMBERS]
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "`python-report-snapshot-delivery` (required): exit 1: no database" in summary
    assert "Durations unavailable:" in summary
    assert not (out / "snapshot-delivery.json").exists()


def test_portfolio_document_carries_no_telemetry() -> None:
    collection = Collection((), Spans())
    assert portfolio_document(collection.results) == {
        "schemaVersion": 1,
        "members": [],
        "failures": [],
    }


# --------------------------------------------------------------------------- #
# Matrix validation                                                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_clear_readings, "reading matrix is not exact"),
        (_clear_comparisons, "comparison matrix is not exact"),
        (_duplicate_reading, "duplicate Snapshot reading"),
        (_wrong_reading_unit, "reading unit"),
        (_wrong_window, "reading window is not"),
        (_remove_samples, "samples, expected"),
        (_forge_value, "disagrees with sample median"),
        (_forge_outcome, "comparison outcome"),
        (_drop_a_runtime, "reading matrix is not exact: missing CPython"),
    ],
)
def test_snapshot_matrix_validation_rejects_semantic_forgeries(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    contract = BudgetContract.load()
    document = _complete_snapshot(contract)
    mutate(document)
    with pytest.raises(ValueError, match=message):
        validate_snapshot_matrix(document, contract)


def test_snapshot_matrix_validation_requires_every_scaling_arm() -> None:
    contract = BudgetContract.load()
    document = _complete_snapshot(contract)
    reading = next(
        reading
        for reading in cast("list[dict[str, object]]", document["readings"])
        if str(reading["cell"]).startswith("streamedMemory.")
    )
    samples = cast("list[float]", reading["samples"])
    del samples[-contract.memory_children :]
    with pytest.raises(ValueError, match="samples, expected"):
        validate_snapshot_matrix(document, contract)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_clear_readings, "reading matrix is not exact"),
        (_duplicate_reading, "duplicate write-lowering reading"),
        (_wrong_reading_unit, "reading unit"),
        (_wrong_window, "reading window is not"),
        (_remove_samples, "has 0 samples, expected"),
        (_forge_value, "disagrees with its sample median"),
        (
            _drop_a_runtime,
            "reading matrix is not exact under any one case coverage and counter vocabulary; "
            "against the current cases and current counters: missing CPython",
        ),
        (_add_comparison, "declares no comparisons"),
    ],
)
def test_write_lowering_matrix_validation_rejects_semantic_forgeries(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    document = _complete_write(BudgetContract.load())
    mutate(document)
    with pytest.raises(ValueError, match=message):
        validate_write_lowering_matrix(document)


_RENAMED_COUNTERS = {
    "calls.encodeDocument": "calls.encodeManagedDocument",
    "calls.encodeMany": "calls.encodeManagedMany",
}


def _historical(name: str, member: str) -> dict[str, Any]:
    path = cost_report.EVIDENCE_DIRECTORY / name / f"{member}.json"
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _counter_readings(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        reading
        for reading in cast("list[dict[str, Any]]", document["readings"])
        if str(reading["cell"]).startswith("calls.")
    ]


def _rename_counters(
    document: dict[str, Any],
    names: dict[str, str],
    *,
    runtime: str | None = None,
    workload: str | None = None,
) -> None:
    for reading in _counter_readings(document):
        if runtime is not None and reading["runtime"] != runtime:
            continue
        if workload is not None and reading["workload"] != workload:
            continue
        reading["cell"] = names.get(str(reading["cell"]), reading["cell"])


def _to_legacy(document: dict[str, Any]) -> None:
    _rename_counters(document, {new: old for old, new in _RENAMED_COUNTERS.items()})


# The two retained captures carry the legacy counter vocabulary on every keyed
# case and both runtimes. Their original workload digests remain untouched when
# the source defining a workload later changes without a recapture, and
# verification names that mismatch rather than presenting the old readings as
# current evidence.
@pytest.mark.parametrize("name", ["before", "after"])
def test_each_retained_historical_portfolio_preserves_its_original_provenance(
    name: str,
) -> None:
    write = _historical(name, write_report.SUBJECT)
    validate_write_lowering_matrix(write)
    counters = {str(reading["cell"]) for reading in _counter_readings(write)}
    assert counters == {f"calls.{name}" for name in write_report.LEGACY_CALL_NAMES}
    portfolio = cast(
        "dict[str, Any]",
        json.loads(
            (cost_report.EVIDENCE_DIRECTORY / name / "portfolio.json").read_text(encoding="utf-8")
        ),
    )
    assert verify(portfolio) == ["the write-lowering envelope's workload digest is stale"]


def test_a_complete_matrix_verifies_under_either_whole_vocabulary_and_no_mixture() -> None:
    contract = BudgetContract.load()
    current = _complete_write(contract)
    validate_write_lowering_matrix(current)
    assert {str(reading["cell"]) for reading in _counter_readings(current)} == {
        f"calls.{name}" for name in write_report.CALL_NAMES
    }
    legacy = deepcopy(current)
    _to_legacy(legacy)
    validate_write_lowering_matrix(legacy)
    runtimes = supported_minors()
    keyed = next(case for case, window in write_report.WINDOWS.items() if window == "keyed-write")
    refused = "not exact under any one case coverage and counter vocabulary"

    one_case_legacy = deepcopy(current)
    _rename_counters(
        one_case_legacy, {new: old for old, new in _RENAMED_COUNTERS.items()}, workload=keyed
    )
    with pytest.raises(
        ValueError, match=f"{refused}; against the current cases and current counters"
    ):
        validate_write_lowering_matrix(one_case_legacy)

    one_runtime_legacy = deepcopy(current)
    _rename_counters(
        one_runtime_legacy,
        {new: old for old, new in _RENAMED_COUNTERS.items()},
        runtime=runtimes[0],
    )
    with pytest.raises(ValueError, match=refused):
        validate_write_lowering_matrix(one_runtime_legacy)

    union = deepcopy(current)
    readings = cast("list[dict[str, Any]]", union["readings"])
    for reading in _counter_readings(current):
        if reading["cell"] in _RENAMED_COUNTERS.values():
            legacy_name = next(
                old for old, new in _RENAMED_COUNTERS.items() if new == reading["cell"]
            )
            readings.append({**deepcopy(reading), "cell": legacy_name})
    with pytest.raises(ValueError, match=f"{refused}.*unexpected .*calls.encodeDocument"):
        validate_write_lowering_matrix(union)

    one_counter_short = deepcopy(current)
    readings = cast("list[dict[str, Any]]", one_counter_short["readings"])
    readings[:] = [
        reading
        for reading in readings
        if (reading["runtime"], reading["workload"], reading["cell"])
        != (runtimes[0], keyed, "calls.encodeManagedMany")
    ]
    with pytest.raises(
        ValueError,
        match=f"{refused}; against the current cases and current counters: "
        f"missing CPython {runtimes[0]} {keyed}.calls.encodeManagedMany$",
    ):
        validate_write_lowering_matrix(one_counter_short)

    unknown_counter = deepcopy(current)
    cast("list[dict[str, Any]]", unknown_counter["readings"]).append(
        {**deepcopy(_counter_readings(current)[0]), "cell": "calls.encodeCandidate"}
    )
    with pytest.raises(ValueError, match=f"{refused}.*unexpected .*calls.encodeCandidate"):
        validate_write_lowering_matrix(unknown_counter)


def test_compare_pairs_every_unchanged_address_across_the_counter_rename() -> None:
    after = _historical("after", "portfolio")
    base = _portfolio(_snapshot_of(after), _write_of(after))
    write = deepcopy(_write_of(after))
    _rename_counters(write, _RENAMED_COUNTERS)
    validate_write_lowering_matrix(write)
    rendered = compare(base, _portfolio(_snapshot_of(after), write))
    lines = rendered.splitlines()
    keyed_cases = [case for case, window in write_report.WINDOWS.items() if window == "keyed-write"]
    unmatched = len(keyed_cases) * len(supported_minors())
    missing_on_head = [line for line in lines if line.endswith("| missing on head |")]
    missing_on_base = [line for line in lines if line.endswith("| missing on base |")]
    assert len(missing_on_head) == 2 * unmatched
    assert len(missing_on_base) == 2 * unmatched
    assert all(
        "| calls.encodeDocument |" in line or "| calls.encodeMany |" in line
        for line in missing_on_head
    )
    assert all(
        "| calls.encodeManagedDocument |" in line or "| calls.encodeManagedMany |" in line
        for line in missing_on_base
    )
    paired = [line for line in lines if line.startswith("| 3.1") and "missing on" not in line]
    write_readings = cast("list[dict[str, Any]]", _write_of(after)["readings"])
    unchanged = [r for r in write_readings if str(r["cell"]) not in _RENAMED_COUNTERS]
    snapshot_readings = cast("list[dict[str, Any]]", _snapshot_of(after)["readings"])
    assert len(paired) == len(unchanged) + len(snapshot_readings)
    assert all(line.endswith(("| within noise |", "| exact |")) for line in paired)
    assert "incomparable" not in rendered


# --------------------------------------------------------------------------- #
# Verification: invalid evidence fails, adverse timing is advisory.            #
# --------------------------------------------------------------------------- #
def test_verify_refuses_a_missing_required_envelope() -> None:
    assert verify({"schemaVersion": 1, "members": [], "failures": []}) == [
        "the portfolio has no required snapshot-delivery envelope"
    ]
    contract = BudgetContract.load()
    snapshot = _complete_snapshot(contract)
    _clean(snapshot, contract, authoritative=True)
    assert verify(_portfolio(snapshot)) == ["the portfolio has no required write-lowering envelope"]


def test_a_clean_published_complete_portfolio_verifies_with_no_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    document = _verifiable(BudgetContract.load())
    lock = tmp_path / "uv.lock"
    lock.write_bytes((cost_report.WORKSPACE / "uv.lock").read_bytes())
    monkeypatch.setattr(cost_report, "WORKSPACE", tmp_path)
    monkeypatch.setattr(cost_report, "is_published", _published)
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps(document), encoding="utf-8")
    assert verify(document) == []
    assert advisories(document) == []
    assert cost_report.main(["--verify", str(portfolio)]) == 0
    captured = capsys.readouterr()
    assert "lock freshness matches" in captured.out
    assert captured.err == ""


def test_adverse_timing_and_memory_outcomes_are_advisory_and_never_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    document = _verifiable(contract)
    snapshot = _snapshot_of(document)
    timing = _first_comparison(snapshot, timing=True)
    _push_outside(snapshot, timing)
    assert verify(document) == []
    assert advisories(document) == [
        f"advisory: {timing['workload']}.{timing['cell']} is outside its timing ceiling"
    ]
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps(document), encoding="utf-8")
    assert cost_report.main(["--verify", str(portfolio)]) == 0
    printed = capsys.readouterr()
    assert (
        f"advisory: {timing['workload']}.{timing['cell']} is outside its timing ceiling"
        in printed.out
    )
    assert printed.err == ""
    memory = _first_comparison(snapshot, timing=False)
    _push_outside(snapshot, memory)
    assert verify(document) == []
    assert advisories(document)[-1] == (
        f"advisory: {memory['workload']}.{memory['cell']} is outside its memory ceiling"
    )
    portfolio.write_text(json.dumps(document), encoding="utf-8")
    assert cost_report.main(["--verify", str(portfolio)]) == 0
    printed = capsys.readouterr()
    assert (
        f"advisory: {memory['workload']}.{memory['cell']} is outside its memory ceiling"
        in printed.out
    )
    assert printed.err == ""


def test_an_unpublished_producing_commit_is_advisory_and_a_dirty_or_stale_one_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _unpublished)
    document = _verifiable(contract)
    assert verify(document) == []
    assert advisories(document) == [
        "advisory: the snapshot-delivery envelope's producing commit "
        f"{_snapshot_of(document)['provenance']['commit'][:12]} is not an ancestor of the "
        "inspected head",
        "advisory: the write-lowering envelope's producing commit "
        f"{_write_of(document)['provenance']['commit'][:12]} is not an ancestor of the "
        "inspected head",
    ]
    monkeypatch.setattr(cost_report, "is_published", _published)
    write = _write_of(document)
    write["provenance"]["dirty"] = True
    write["provenance"]["workloadDigest"] = "0" * 64
    write["provenance"]["commit"] = "f" * 40
    monkeypatch.setattr(cost_report, "validate", _no_validation)
    assert verify(document) == [
        "the write-lowering envelope was not produced from a clean tree",
        "the write-lowering envelope's workload digest is stale",
        "the snapshot-delivery and write-lowering envelopes name different commits",
    ]


def _reading_at(member: dict[str, Any], runtime: str, workload: str, cell: str) -> dict[str, Any]:
    return next(
        reading
        for reading in member["readings"]
        if (reading.get("runtime"), reading["workload"], reading["cell"])
        == (runtime, workload, cell)
    )


def _push_past_gate(reading: dict[str, Any], gate: MemoryGate) -> None:
    value = gate.max_bytes / (1_024 if gate.unit == "KiB" else 1) + 1
    reading["value"] = value
    reading["samples"] = [value] * len(reading["samples"])


# The memory gate blocks in the cost class, where the same window is read again
# in an interpreter of its own; the verifier states a reading past it beside
# the other advisories and never fails for it, on whichever runtime read it.
def test_a_reading_past_its_memory_gate_is_advisory_and_never_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    contract = BudgetContract.load()
    gates = MemoryGates.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    document = _verifiable(contract)
    assert verify(document) == []
    assert advisories(document) == []
    write_gate = gates.gate("write-lowering", "txtime.opening.columns.typed", "retainedBytes")
    read_gate = gates.gate("snapshot-delivery", "read-depth-1", "document.retainedKiB")
    other_runtime = next(
        minor for minor in supported_minors() if minor != authority_minor(contract.authority)
    )
    _push_past_gate(
        _reading_at(_write_of(document), other_runtime, write_gate.workload, write_gate.cell),
        write_gate,
    )
    _push_past_gate(
        _reading_at(_snapshot_of(document), other_runtime, read_gate.workload, read_gate.cell),
        read_gate,
    )
    assert verify(document) == []
    assert advisories(document) == [
        f"advisory: snapshot-delivery CPython {other_runtime} read-depth-1.document.retainedKiB "
        f"is outside its memory gate ({read_gate.max_bytes + 1024} B over {read_gate.max_bytes} B; "
        "the cost class gates it)",
        f"advisory: write-lowering CPython {other_runtime} "
        "txtime.opening.columns.typed.retainedBytes is outside its memory gate "
        f"({write_gate.max_bytes + 1} B over {write_gate.max_bytes} B; the cost class gates it)",
    ]
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps(document), encoding="utf-8")
    assert cost_report.main(["--verify", str(portfolio)]) == 0
    printed = capsys.readouterr()
    assert "is outside its memory gate" in printed.out
    assert printed.err == ""
    mismatched = _reading_at(_write_of(document), other_runtime, "model.prepared", "retainedBytes")
    mismatched["unit"] = "KiB"
    monkeypatch.setattr(cost_report, "validate_write_lowering_matrix", _no_validation)
    assert advisories(document)[-1] == (
        f"advisory: write-lowering CPython {other_runtime} model.prepared.retainedBytes is read "
        "in KiB and gated in B"
    )


def test_is_published_asks_git_whether_the_commit_is_an_ancestor_of_head() -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cost_report.WORKSPACE,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert cost_report.is_published(head)
    assert not cost_report.is_published("f" * 40)


def test_verify_rejects_a_semantically_incomplete_snapshot_matrix() -> None:
    document = _complete_snapshot(BudgetContract.load())
    cast("list[object]", document["comparisons"]).clear()
    failures = verify(_portfolio(document))
    assert len(failures) == 1
    assert "comparison matrix is not exact" in failures[0]


def test_verify_rejects_an_invalid_write_lowering_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cost_report, "is_published", _published)
    document = _verifiable(BudgetContract.load())
    _clear_readings(_write_of(document))
    failures = verify(document)
    assert len(failures) == 1
    assert failures[0].startswith("the write-lowering envelope is invalid: ")


def test_collection_attempts_later_members_after_an_invalid_required_matrix() -> None:
    attempted: list[str] = []
    contract = BudgetContract.load()
    snapshot = _complete_snapshot(contract)
    write = _complete_write(contract)
    cast("list[object]", snapshot["readings"]).clear()

    def run(member: Member, _arguments: Sequence[str]) -> tuple[int, str, str]:
        attempted.append(member.recipe)
        document = (
            snapshot
            if member.subject == "snapshot-delivery"
            else write
            if member.subject == write_report.SUBJECT
            else _optional_document(member)
        )
        return (0, json.dumps(document), "")

    collection = collect(run)
    assert attempted == [member.recipe for member in MEMBERS]
    assert collection.failed_required
    assert collection.results[0].envelope is None
    assert all(result.envelope is not None for result in collection.results[1:])


def test_a_moved_checkout_lock_is_advisory_and_never_changes_authority_or_the_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = _verifiable(BudgetContract.load())
    snapshot = _snapshot_of(document)
    original_lock = (cost_report.WORKSPACE / "uv.lock").read_bytes()
    lock = tmp_path / "uv.lock"
    lock.write_bytes(original_lock)
    monkeypatch.setattr(cost_report, "WORKSPACE", tmp_path)
    monkeypatch.setattr(cost_report, "is_published", _published)
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps(document), encoding="utf-8")

    assert verify(document) == []
    assert cost_report.main(["--verify", str(portfolio)]) == 0
    matching = capsys.readouterr()
    assert "lock freshness matches" in matching.out
    assert matching.err == ""

    lock.write_bytes(original_lock + b"\n")
    expected = (
        "advisory: stale snapshot-delivery evidence: "
        f"recorded lockDigest={hashlib.sha256(original_lock).hexdigest()}; "
        f"inspected lockDigest={hashlib.sha256(lock.read_bytes()).hexdigest()} ({lock})"
    )
    assert verify(document) == []
    assert advisories(document) == [expected]
    assert cost_report.main(["--verify", str(portfolio)]) == 0
    moved = capsys.readouterr()
    assert moved.out == expected + "\n"
    assert moved.err == ""
    validate(snapshot)
    assert snapshot["authority"] == "authoritative"


def test_invalid_evidence_fails_while_every_drift_is_reported_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    document = _verifiable(contract)
    snapshot = _snapshot_of(document)
    memory = _first_comparison(snapshot, timing=False)
    _push_outside(snapshot, memory)
    compared = authority_minor(contract.authority)
    scaling = next(
        item
        for item in snapshot["readings"]
        if item["cell"].startswith("streamedMemory.") and item["runtime"] == compared
    )
    scaling["samples"][contract.memory_children :] = [scaling["value"] + 100] * (
        contract.memory_children * (len(contract.memory_scaling_arms) - 1)
    )
    scaling_comparison = next(
        item
        for item in snapshot["comparisons"]
        if (item["workload"], item["cell"]) == (scaling["workload"], scaling["cell"])
    )
    scaling_comparison["outcome"] = "outside"
    snapshot["provenance"]["dirty"] = True
    snapshot["authority"] = "non-authoritative"
    snapshot["incomplete"] = [{"code": "unavailable", "message": "incomplete observation"}]
    snapshot["errors"] = [{"code": "error", "message": "observation error"}]
    expected = verify(document)
    assert expected == [
        "the snapshot-delivery envelope is not authoritative",
        "the snapshot-delivery envelope is incomplete",
        "the snapshot-delivery envelope contains errors",
        "the snapshot-delivery envelope was not produced from a clean tree",
    ]
    assert advisories(document) == [
        f"advisory: {memory['workload']}.{memory['cell']} is outside its memory ceiling",
        f"advisory: {scaling['workload']}.{scaling['cell']} is outside its memory ceiling",
        f"advisory: {scaling['workload']}.{scaling['cell']} grows 100.000 KiB between memory arms",
    ]
    (tmp_path / "uv.lock").write_bytes(b"updated dependencies")
    monkeypatch.setattr(cost_report, "WORKSPACE", tmp_path)
    assert verify(document) == expected
    reported = advisories(document)
    assert reported[0].startswith("advisory: stale snapshot-delivery evidence:")
    assert len(reported) == 4
    snapshot["comparisons"].clear()
    failures = verify(document)
    assert len(failures) == 1
    assert "comparison matrix is not exact" in failures[0]


def test_freshness_only_compares_an_explicit_lock_without_revalidating_historical_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    merge_lock = tmp_path / "merge.lock"
    merge_lock.write_bytes(b"event merge dependencies")
    snapshot = {
        "subject": "snapshot-delivery",
        "provenance": {"lockDigest": hashlib.sha256(merge_lock.read_bytes()).hexdigest()},
    }
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps({"members": [snapshot]}), encoding="utf-8")
    args = ["--freshness-only", str(portfolio), "--lock-file", str(merge_lock)]
    assert cost_report.main(args) == 0
    assert "lock freshness matches" in capsys.readouterr().out
    merge_lock.write_bytes(b"later dependencies")
    assert cost_report.main(args) == 0
    assert "advisory: stale snapshot-delivery evidence:" in capsys.readouterr().out


@pytest.mark.parametrize(
    "members",
    [
        [],
        [{"subject": "snapshot-delivery", "provenance": None}],
        [{"subject": "snapshot-delivery", "provenance": {}}],
        [{"subject": "snapshot-delivery", "provenance": {"lockDigest": "0" * 63}}],
        [{"subject": "snapshot-delivery", "provenance": {"lockDigest": 0}}],
    ],
)
def test_freshness_reports_unavailable_evidence_without_losing_validation_diagnostics(
    tmp_path: Path, members: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps({"members": members}), encoding="utf-8")
    assert cost_report.main(["--freshness-only", str(portfolio)]) == 1
    assert "lock freshness unavailable:" in capsys.readouterr().out
    assert cost_report.main(["--verify", str(portfolio)]) == 1
    diagnostic = capsys.readouterr().err
    assert "invalid:" in diagnostic if members else "no required" in diagnostic


def test_explicit_lock_cannot_silently_override_strict_checkout_verification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        cost_report.main(["--verify", "portfolio.json", "--lock-file", str(tmp_path / "uv.lock")])
    assert error.value.code == 2
    assert "--lock-file requires --freshness-only" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Comparison: identity-preserving, explicit about noise, missing, incomparable #
# --------------------------------------------------------------------------- #
def _reading(
    workload: str, cell: str, value: float, unit: str, *, runtime: str = "3.14", window: str = "w"
) -> dict[str, object]:
    return {
        "workload": workload,
        "cell": cell,
        "value": value,
        "unit": unit,
        "samples": [value] * 3,
        "runtime": runtime,
        "window": window,
    }


def _member(subject: str, *readings: dict[str, object]) -> dict[str, object]:
    return {"subject": subject, "readings": list(readings), "comparisons": []}


def test_compare_pairs_identical_addresses_and_names_every_other_cell() -> None:
    base = _portfolio(
        _member(
            "write-lowering",
            _reading("case", "elapsedUs", 100.0, "us/row"),
            _reading("case", "elapsedUs", 100.0, "us/row", runtime="3.13"),
            _reading("case", "retainedBytes", 1000.0, "B/row"),
            _reading("case", "transientBytes", 10.0, "B/row"),
            _reading("case", "calls.encodeMany", 1.0, "calls/row"),
            _reading("case", "peak", 1000.0, "B/row"),
            _reading("only-base", "elapsedUs", 1.0, "us/row"),
            _reading("case", "elapsedUs", 5.0, "us/row", window="other"),
        ),
        _member("snapshot-delivery", _reading("w", "live.eager.maxMs", 10.0, "ms")),
    )
    head = _portfolio(
        _member(
            "write-lowering",
            _reading("case", "elapsedUs", 103.0, "us/row"),
            _reading("case", "elapsedUs", 120.0, "us/row", runtime="3.13"),
            _reading("case", "retainedBytes", 900.0, "B/row"),
            _reading("case", "transientBytes", 10.0, "B"),
            _reading("case", "calls.encodeMany", 2.0, "calls/row"),
            _reading("case", "peak", 1020.0, "B/row"),
            _reading("only-head", "elapsedUs", 1.0, "us/row"),
        ),
    )
    rendered = compare(base, head)
    assert f"{cost_report.TIMING_NOISE_ALLOWANCE:.0%}" in rendered
    assert f"{cost_report.MEMORY_NOISE_ALLOWANCE:.0%}" in rendered
    lines = rendered.splitlines()

    def row(prefix: str) -> str:
        return next(line for line in lines if line.startswith(prefix))

    assert row("| 3.14 | w | case | elapsedUs |").endswith(
        "| 100.000 | 103.000 | +3.000 us/row (+3.00%) | 3 | within noise |"
    )
    assert row("| 3.13 | w | case | elapsedUs |").endswith(
        "| 100.000 | 120.000 | +20.000 us/row (+20.00%) | 3 | slower |"
    )
    assert row("| 3.14 | w | case | retainedBytes |").endswith(
        "| 1000.000 | 900.000 | -100.000 B/row (-10.00%) | 3 | smaller |"
    )
    assert row("| 3.14 | w | case | calls.encodeMany |").endswith("| 3 | changed |")
    assert row("| 3.14 | w | case | peak |").endswith("| 3 | within noise |")
    assert (
        "| 3.14 | w | case | transientBytes | | | | | incomparable: B/row against B |" in rendered
    )
    assert "| 3.14 | w | only-base | elapsedUs | | | | | missing on head |" in rendered
    assert "| 3.14 | w | only-head | elapsedUs | | | | | missing on base |" in rendered
    assert "| 3.14 | other | case | elapsedUs | | | | | missing on head |" in rendered
    assert "## snapshot-delivery" in rendered
    assert "The snapshot-delivery envelope is unavailable on one side." in rendered


def test_compare_reads_throughput_deltas_in_their_own_direction() -> None:
    base = _portfolio(
        _member(
            "snapshot-delivery",
            _reading("w", "live.eager.minRootsPerSecond", 1000.0, "roots/s"),
            _reading("w", "stress.peakFor64KiB", 400.0, "KiB"),
            _reading("w", "calls", 4.0, "calls/row"),
            _reading("w", "zero", 0.0, "ms"),
        )
    )
    head = _portfolio(
        _member(
            "snapshot-delivery",
            _reading("w", "live.eager.minRootsPerSecond", 1200.0, "roots/s"),
            _reading("w", "stress.peakFor64KiB", 440.0, "KiB"),
            _reading("w", "calls", 4.0, "calls/row"),
            _reading("w", "zero", 1.0, "ms"),
        )
    )
    rendered = compare(base, head)
    assert "| faster |" in rendered
    assert "| larger |" in rendered
    assert "| exact |" in rendered
    assert "| incomparable |" in rendered


# Every capture is compared under the frozen protocol the evidence README publishes.
# Changing an allowance or the write sampling makes already-committed captures
# incomparable, so each value is pinned here as a reviewed diff line.
def test_the_frozen_allowances_and_write_sampling_match_the_published_protocol() -> None:
    assert cost_report.TIMING_NOISE_ALLOWANCE == 0.05
    assert cost_report.MEMORY_NOISE_ALLOWANCE == 0.03
    assert (write_report.WARMUPS, write_report.MEASURED) == (3, 9)
    assert write_report.samples_expected("elapsedUs") == 9
    assert write_report.samples_expected("retainedBytes") == 1
    assert write_report.samples_expected("calls.encodeMany") == 1
    readme = (
        cost_report.WORKSPACE / "docs" / "structural-metadata-envelope" / "README.md"
    ).read_text(encoding="utf-8")
    assert "three warm-ups and nine measured samples" in readme
    assert "**5%**" in readme
    assert "**3%**" in readme


def test_a_diagnostic_reading_set_is_never_verifiable_evidence(tmp_path: Path) -> None:
    diagnostic: dict[str, Any] = {"diagnostic": True, "subject": "write-lowering", "readings": []}
    assert verify(diagnostic) == ["a diagnostic reading set is not evidence and cannot be verified"]
    portfolio = _verifiable(BudgetContract.load())
    cast("list[dict[str, Any]]", portfolio["members"]).append(diagnostic)
    assert verify(portfolio) == ["a diagnostic reading set is not evidence and cannot be verified"]
    path = tmp_path / "diagnostic.json"
    path.write_text(json.dumps(diagnostic), encoding="utf-8")
    assert cost_report.main(["--verify", str(path)]) == 1


def test_diagnose_writes_only_diagnostic_documents_and_never_a_portfolio(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invoked: list[tuple[str, list[str]]] = []

    def runner(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        invoked.append((member.subject, list(arguments)))
        document: dict[str, Any] = {"diagnostic": True, "subject": member.subject, "readings": []}
        return (0, json.dumps(document), "")

    assert (
        cost_report.diagnose(
            ["write-lowering", "snapshot-delivery"], ["plan-*"], ["3.14"], tmp_path, runner
        )
        == 0
    )
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "diagnostic-snapshot-delivery.json",
        "diagnostic-write-lowering.json",
    ]
    assert invoked == [
        ("snapshot-delivery", ["--diagnostic", "--select", "plan-*", "--runtime", "3.14"]),
        ("write-lowering", ["--diagnostic", "--case", "plan-*", "--runtime", "3.14"]),
    ]
    assert cost_report.diagnose(["unknown"], [], [], None, runner) == 2
    assert cost_report.diagnose(["write-lowering"], [], [], None, lambda m, a: (3, "", "boom")) == 1
    assert "boom" in capsys.readouterr().err
    assert (
        cost_report.diagnose(
            ["write-lowering"], [], [], None, lambda m, a: (0, json.dumps({"subject": "x"}), "")
        )
        == 1
    )


def test_a_diagnostic_run_never_writes_into_the_committed_evidence_directory(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def runner(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        raise AssertionError(f"{member.subject} {list(arguments)} must never be run")

    for out in (cost_report.EVIDENCE_DIRECTORY, cost_report.EVIDENCE_DIRECTORY / "scratch"):
        assert cost_report.diagnose(["write-lowering"], [], [], out, runner) == 2
    assert "writes nothing into" in capsys.readouterr().err


def test_diagnostic_options_are_fenced_from_verification_and_collection(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for arguments in (
        ["--select", "x"],
        ["--diagnostic", "--verify", "portfolio.json"],
        ["--diagnostic", "--compare", "a.json", "b.json"],
    ):
        with pytest.raises(SystemExit) as error:
            cost_report.main(arguments)
        assert error.value.code == 2
    assert "diagnostic" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Required members: a member held to the exact matrix its owner declares      #
# --------------------------------------------------------------------------- #
def _without_controls(snapshot: dict[str, Any]) -> None:
    readings = cast("list[dict[str, Any]]", snapshot["readings"])
    readings[:] = [r for r in readings if not str(r["workload"]).startswith("control-")]


def _without_control_cases(write: dict[str, Any]) -> None:
    readings = cast("list[dict[str, Any]]", write["readings"])
    readings[:] = [r for r in readings if r["workload"] not in write_report.CONTROL_CASE_NAMES]


def _with_instance_state(document: dict[str, Any], contract: BudgetContract) -> dict[str, Any]:
    member = complete_instance_state(contract)
    _clean(member, contract, authoritative=False)
    member["provenance"]["commit"] = _snapshot_of(document)["provenance"]["commit"]
    cast("list[dict[str, Any]]", document["members"]).append(member)
    return member


def _instance_of(document: dict[str, Any]) -> dict[str, Any]:
    return next(
        m for m in document["members"] if m["subject"] == cost_report.INSTANCE_STATE_SUBJECT
    )


def _without_instance_head_only(document: dict[str, Any]) -> None:
    readings = cast("list[dict[str, Any]]", _instance_of(document)["readings"])
    readings[:] = [
        reading
        for reading in readings
        if cast("str", reading["cell"]) not in cost_report.HEAD_ONLY["instance-state"]
    ]


def test_a_capture_without_the_control_group_verifies_but_cannot_be_required_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    document = _verifiable(contract)
    assert verify(document, required=["snapshot-delivery", write_report.SUBJECT]) == []
    _without_controls(_snapshot_of(document))
    _without_control_cases(_write_of(document))
    assert verify(document) == []
    (snapshot_failure,) = verify(document, required=["snapshot-delivery"])
    assert snapshot_failure.startswith(
        "the snapshot-delivery envelope is invalid: Snapshot reading matrix is not exact: "
        "missing CPython"
    )
    assert "control-" in snapshot_failure
    (write_failure,) = verify(document, required=[write_report.SUBJECT])
    assert write_failure.startswith(
        "the write-lowering envelope is invalid: write-lowering reading matrix is not exact "
        "under any one case coverage and counter vocabulary; against the current cases and "
        "current counters: missing CPython"
    )
    assert write_report.MODEL_FAMILY_CASE in write_failure


def test_requiring_instance_state_holds_it_to_its_owners_complete_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    document = _verifiable(contract)
    assert verify(document) == []
    assert verify(document, required=["instance-state"]) == [
        "the portfolio has no required instance-state envelope"
    ]
    member = _with_instance_state(document, contract)
    assert verify(document, required=["instance-state"]) == []
    assert verify(document) == []

    member["provenance"]["dirty"] = True
    member["provenance"]["workloadDigest"] = "0" * 64
    monkeypatch.setattr(cost_report, "validate", _no_validation)
    assert verify(document, required=["instance-state"]) == [
        "the instance-state envelope was not produced from a clean tree",
        "the instance-state envelope's workload digest is stale",
    ]
    member["provenance"]["dirty"] = False
    member["provenance"]["workloadDigest"] = _snapshot_of(document)["provenance"]["workloadDigest"]
    member["provenance"]["commit"] = "f" * 40
    member["incomplete"] = [{"code": "unavailable", "message": "one scenario"}]
    assert verify(document, required=["instance-state"]) == [
        "the instance-state envelope is incomplete",
        "the instance-state envelope names a different commit from the required members",
    ]
    del cast("list[object]", member["readings"])[0]
    (failure,) = verify(document, required=["instance-state"])
    assert failure.startswith("the instance-state envelope is invalid: instance-state reading")
    with pytest.raises(ValueError, match="requirable members are"):
        verify(document, required=["lifecycle-overhead"])


def _instance_add_window(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["readings"])[0]["window"] = "elsewhere"


def _instance_add_samples(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["readings"])[0]["samples"] = [1.0]


def _instance_drop_runtime(document: dict[str, Any]) -> None:
    readings = cast("list[dict[str, object]]", document["readings"])
    readings[:] = [r for r in readings if not str(r["workload"]).startswith("cpython-3.13")]


def _instance_add_reading(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["readings"]).append(
        {
            "workload": "cpython-3.14/shallow",
            "cell": "compact.unknownProjectionNs",
            "value": 1,
            "unit": "ns",
            "samples": [],
        }
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_clear_readings, "instance-state reading matrix is not exact"),
        (_clear_comparisons, "instance-state comparison matrix is not exact"),
        (_duplicate_reading, "duplicate instance-state reading"),
        (_wrong_reading_unit, "reading unit"),
        (_instance_add_window, "names a window"),
        (_instance_add_samples, "carries samples"),
        (_forge_outcome, "comparison outcome"),
        (_instance_drop_runtime, "reading matrix is not exact: missing cpython-3.13"),
        (_instance_add_reading, "unexpected cpython-3.14/shallow.compact.unknownProjectionNs"),
    ],
)
def test_instance_state_matrix_validation_rejects_semantic_forgeries(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    document = complete_instance_state(BudgetContract.load())
    cost_report.validate_instance_state_matrix(document)
    mutate(document)
    with pytest.raises(ValueError, match=message):
        cost_report.validate_instance_state_matrix(document)


def test_require_member_is_a_verify_or_compare_option_over_requirable_subjects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for arguments in (
        ["--require-member", "instance-state"],
        ["--verify", "portfolio.json", "--require-member", "lifecycle-overhead"],
        ["--require-compatible"],
        ["--verify", "portfolio.json", "--require-compatible"],
    ):
        with pytest.raises(SystemExit) as error:
            cost_report.main(arguments)
        assert error.value.code == 2
        assert "require" in capsys.readouterr().err
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    document = _verifiable(contract)
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps(document), encoding="utf-8")
    assert cost_report.main(["--verify", str(portfolio), "--require-member", "instance-state"]) == 1
    assert "no required instance-state envelope" in capsys.readouterr().err
    _with_instance_state(document, contract)
    portfolio.write_text(json.dumps(document), encoding="utf-8")
    assert cost_report.main(["--verify", str(portfolio), "--require-member", "instance-state"]) == 0
    assert capsys.readouterr().err == ""


# --------------------------------------------------------------------------- #
# Conditions: what the envelopes cannot carry, written beside them            #
# --------------------------------------------------------------------------- #
def _identities(version: str = "3.14.7") -> dict[str, dict[str, RuntimeStatus]]:
    return {
        member.subject: {
            minor: RuntimeIdentity("CPython", f"{minor}.1" if minor != "3.14" else version, "/p")
            for minor in supported_minors()
        }
        for member in MEMBERS
    }


def test_conditions_record_every_members_sources_and_runtimes_and_round_trip(
    tmp_path: Path,
) -> None:
    document = cost_report.conditions_document(_identities())
    assert document["schemaVersion"] == cost_report.CONDITIONS_VERSION
    members = cast("dict[str, dict[str, Any]]", document["members"])
    assert list(members) == [member.subject for member in MEMBERS]
    for subject, recorded in members.items():
        sources = cost_report.MEMBER_SOURCES[subject]
        assert set(recorded["sources"]) == set(sources.instruments) | set(sources.controls)
        assert all(
            hashlib.sha256((cost_report.WORKSPACE / path).read_bytes()).hexdigest() == digest
            for path, digest in recorded["sources"].items()
        )
        assert set(recorded["runtimes"]) == set(supported_minors())
    assert "tests/unit/_delivery_control_support.py" in members["snapshot-delivery"]["sources"]
    assert "tests/unit/_write_lowering_support.py" in members[write_report.SUBJECT]["sources"]
    path = tmp_path / cost_report.CONDITIONS_FILE
    path.write_text(json.dumps(document), encoding="utf-8")
    loaded = cost_report.load_conditions(path)
    assert set(loaded) == set(members)
    assert loaded["snapshot-delivery"].sources == members["snapshot-delivery"]["sources"]
    assert loaded["snapshot-delivery"].runtimes["3.14"] == RuntimeIdentity(
        "CPython", "3.14.7", "/p"
    )
    members["snapshot-delivery"]["sources"]["tools/snapshot_delivery_reading.py"] = "not a digest"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="not all digests"):
        cost_report.load_conditions(path)
    path.write_text(json.dumps({"schemaVersion": 2, "members": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="schemaVersion"):
        cost_report.load_conditions(path)


def test_collection_writes_the_conditions_it_recorded_beside_the_portfolio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = BudgetContract.load()
    snapshot = _complete_snapshot(contract)
    write = _complete_write(contract)

    def run(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        sidecar = _sidecar_path(arguments)
        sidecar.write_text(_member_sidecar(), encoding="utf-8")
        if member.subject == "snapshot-delivery":
            write_metadata(
                Path(arguments[3]),
                member.subject,
                {
                    minor: RuntimeIdentity("CPython", f"{minor}.9", "/p")
                    for minor in supported_minors()
                },
            )
        document = (
            snapshot
            if member.subject == "snapshot-delivery"
            else write
            if member.subject == write_report.SUBJECT
            else _optional_document(member)
        )
        return (0, json.dumps(document), "")

    monkeypatch.setattr(cost_report, "run_member", run)
    out = tmp_path / "reports"
    assert cost_report.main(["--out", str(out)]) == 0
    capsys.readouterr()
    loaded = cost_report.load_conditions(out / cost_report.CONDITIONS_FILE)
    assert set(loaded) == {member.subject for member in MEMBERS}
    assert loaded["snapshot-delivery"].runtimes == {
        minor: RuntimeIdentity("CPython", f"{minor}.9", "/p") for minor in supported_minors()
    }
    assert all(
        isinstance(status, RuntimeUnavailable)
        for status in loaded[write_report.SUBJECT].runtimes.values()
    )


# --------------------------------------------------------------------------- #
# Required compatibility: no arithmetic until the two captures are matched    #
# --------------------------------------------------------------------------- #
def _capture(
    root: Path,
    name: str,
    document: dict[str, Any],
    conditions: dict[str, object] | None,
) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    portfolio = directory / "portfolio.json"
    portfolio.write_text(json.dumps(document), encoding="utf-8")
    if conditions is not None:
        (directory / cost_report.CONDITIONS_FILE).write_text(
            json.dumps(conditions), encoding="utf-8"
        )
    return portfolio


def _pair(
    tmp_path: Path, contract: BudgetContract, *, with_instance_state: bool = False
) -> tuple[Path, Path, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = _verifiable(contract)
    head = deepcopy(base)
    if with_instance_state:
        _with_instance_state(base, contract)
        _with_instance_state(head, contract)
        _without_instance_head_only(base)
    base_conditions = cost_report.conditions_document(_identities())
    head_conditions = deepcopy(base_conditions)
    return (
        _capture(tmp_path, "before", base, base_conditions),
        _capture(tmp_path, "after", head, head_conditions),
        base,
        head,
        base_conditions,
        head_conditions,
    )


def _rewrite(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def test_a_matched_pair_is_compared_with_its_compatibility_stated_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    base, head, *_rest = _pair(tmp_path, contract, with_instance_state=True)
    assert (
        cost_report.main(
            [
                "--compare",
                str(base),
                str(head),
                "--require-compatible",
                "--require-member",
                "instance-state",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.startswith("# Python cost report comparison\n")
    assert (
        "Compatibility established over snapshot-delivery, write-lowering, instance-state: "
        in captured.out
    )
    assert "## snapshot-delivery" in captured.out and "## instance-state" in captured.out
    assert "incomparable:" not in captured.out
    assert captured.out.count("missing on base") == (
        len(supported_minors())
        * len(instance_report.SCENARIOS)
        * len(cost_report.HEAD_ONLY["instance-state"])
    )
    assert cost_report.main(["--compare", str(base), str(head)]) == 0
    assert "Compatibility established" not in capsys.readouterr().out


def test_an_amended_capture_is_stated_by_verification_and_by_every_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    base, head, *_rest, head_conditions = _pair(tmp_path, contract)
    assert cost_report.amendment_beside(head) is None

    head_conditions[cost_report.ADJUSTMENT_FIELD] = {
        "remeasured": {"count": 470},
        "derived": {"count": 8},
    }
    _rewrite(head.parent / cost_report.CONDITIONS_FILE, head_conditions)
    amendment = (
        "470 re-measured and 8 derived readings changed after the run its provenance names, "
        f"recorded in the {cost_report.ADJUSTMENT_FIELD} of {cost_report.CONDITIONS_FILE}"
    )

    assert cost_report.main(["--verify", str(head)]) == 0
    assert f"the capture is amended: {amendment}" in capsys.readouterr().out
    assert cost_report.main(["--compare", str(base), str(head)]) == 0
    assert f"- The head capture is amended: {amendment}." in capsys.readouterr().out
    assert cost_report.main(["--compare", str(base), str(head), "--require-compatible"]) == 0
    stated = capsys.readouterr().out
    assert "Compatibility established over " in stated
    assert f"- The head capture is amended: {amendment}." in stated


def test_an_unmatched_pair_is_refused_before_any_arithmetic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    base, head, base_document, head_document, base_conditions, head_conditions = _pair(
        tmp_path, contract
    )

    def refused(*extra: str) -> list[str]:
        assert (
            cost_report.main(["--compare", str(base), str(head), "--require-compatible", *extra])
            == 1
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        lines = captured.err.splitlines()
        assert lines[0].startswith("the captures are not comparable over ")
        return lines[1:]

    members = cast("dict[str, dict[str, Any]]", head_conditions["members"])
    members["snapshot-delivery"]["sources"]["tests/unit/_delivery_control_support.py"] = "0" * 64
    members[write_report.SUBJECT]["sources"]["tools/write_lowering_reading.py"] = "0" * 64
    members[write_report.SUBJECT]["runtimes"]["3.14"] = {
        "status": "available",
        "implementation": "CPython",
        "version": "3.14.8",
        "executable": "/p",
    }
    members["snapshot-delivery"]["runtimes"]["3.13"] = {
        "status": "unavailable",
        "reason": "the identity probe exited 1",
    }
    _rewrite(head.parent / cost_report.CONDITIONS_FILE, head_conditions)
    assert refused() == [
        "the snapshot-delivery control source tests/unit/_delivery_control_support.py differs "
        "between the captures",
        "snapshot-delivery CPython 3.13 identity is unknown on head (the identity probe exited 1)",
        "the write-lowering instrument tools/write_lowering_reading.py differs between the "
        "captures",
        "write-lowering CPython 3.14 is CPython 3.14.7 on base and CPython 3.14.8 on head",
    ]

    _rewrite(head.parent / cost_report.CONDITIONS_FILE, base_conditions)
    snapshot = _snapshot_of(head_document)
    write = _write_of(head_document)
    dropped = cast("list[dict[str, Any]]", snapshot["readings"]).pop()
    cast("list[dict[str, Any]]", write["readings"]).append(
        {**deepcopy(cast("list[dict[str, Any]]", write["readings"])[0]), "cell": "projectionUs"}
    )
    changed = cast("list[dict[str, Any]]", write["readings"])[1]
    original_unit = changed["unit"]
    changed["unit"] = "ms/row"
    shortened = next(
        r for r in cast("list[dict[str, Any]]", write["readings"]) if len(r["samples"]) > 1
    )
    original_samples = len(shortened["samples"])
    shortened["samples"] = shortened["samples"][:-1]
    write["provenance"]["dirty"] = True
    write["provenance"]["lockDigest"] = "1" * 64
    monkeypatch.setattr(cost_report, "validate", _no_validation)
    monkeypatch.setattr(cost_report, "validate_matrix", _no_matrix_validation)
    _rewrite(head, head_document)
    failures = refused()
    assert any(
        f"snapshot-delivery {dropped['runtime']}" in line
        and dropped["cell"] in line
        and "missing on head" in line
        for line in failures
    )
    assert "head: the write-lowering envelope was not produced from a clean tree" in failures
    assert any(
        line.startswith("the write-lowering envelopes disagree on lockDigest") for line in failures
    )
    assert any(
        "projectionUs is present on head alone and not declared head-only" in line
        for line in failures
    )
    assert any(
        f"is read in {original_unit} on base and ms/row on head" in line for line in failures
    )
    assert any(
        f"carries {original_samples} samples on base and {original_samples - 1} on head" in line
        for line in failures
    )

    (head.parent / cost_report.CONDITIONS_FILE).unlink()
    failures = refused()
    assert failures[:1] == [
        "head: no recorded conditions for snapshot-delivery, so its sources and interpreter "
        "identities are unknown"
    ]
    _rewrite(head, base_document)
    assert refused("--require-member", "instance-state")[-1] == (
        "head: expected one instance-state envelope, found 0"
    )


def test_only_the_exact_head_only_source_transitions_are_noted_rather_than_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    base, head, _base_document, head_document, base_conditions, head_conditions = _pair(
        tmp_path, contract, with_instance_state=True
    )
    members = cast("dict[str, dict[str, Any]]", head_conditions["members"])
    base_members = cast("dict[str, dict[str, Any]]", base_conditions["members"])
    transitions = cost_report.HEAD_ONLY_SOURCE_TRANSITIONS["instance-state"]
    for path, (before, after) in transitions.items():
        base_members["instance-state"]["sources"][path] = before
        members["instance-state"]["sources"][path] = after
    _rewrite(base.parent / cost_report.CONDITIONS_FILE, base_conditions)
    _rewrite(head, head_document)
    _rewrite(head.parent / cost_report.CONDITIONS_FILE, head_conditions)
    monkeypatch.setattr(cost_report, "validate", _no_validation)
    declared = cost_report.HEAD_ONLY["instance-state"]
    monkeypatch.setitem(cost_report.HEAD_ONLY, "instance-state", frozenset())
    monkeypatch.setitem(cost_report.HEAD_ONLY_SOURCE_TRANSITIONS, "instance-state", {})
    arguments = [
        "--compare",
        str(base),
        str(head),
        "--require-compatible",
        "--require-member",
        "instance-state",
    ]
    assert cost_report.main(arguments) == 1
    refused = capsys.readouterr().err.splitlines()
    assert set(refused[1:3]) == {
        "the instance-state instrument tools/instance_state_overhead.py differs between the "
        "captures",
        "the instance-state instrument tools/instance_state_reading.py differs between the "
        "captures",
    }
    undeclared = refused[3:]
    assert len(undeclared) == len(supported_minors()) * len(instance_report.SCENARIOS) * len(
        declared
    )
    assert all("is present on head alone and not declared head-only" in line for line in undeclared)
    assert any("compact.projectionNs" in line for line in undeclared)
    monkeypatch.setitem(cost_report.HEAD_ONLY, "instance-state", declared)
    monkeypatch.setitem(cost_report.HEAD_ONLY_SOURCE_TRANSITIONS, "instance-state", transitions)
    assert cost_report.main(arguments) == 0
    printed = capsys.readouterr()
    assert printed.err == ""
    assert (
        "- the instance-state instrument tools/instance_state_reading.py differs between the "
        "captures; permitted because this exact source transition introduces its declared "
        "head-only cells" in printed.out
    )
    assert (
        "- instance-state - | - | cpython-3.14/wide | compact.projectionTransientBytes is head-only"
        in printed.out
    )
    members["instance-state"]["sources"]["tests/unit/_instance_state_support.py"] = "0" * 64
    _rewrite(head.parent / cost_report.CONDITIONS_FILE, head_conditions)
    assert cost_report.main(arguments) == 1
    assert (
        "the instance-state control source tests/unit/_instance_state_support.py differs"
        in capsys.readouterr().err
    )
    members["instance-state"]["sources"]["tests/unit/_instance_state_support.py"] = base_members[
        "instance-state"
    ]["sources"]["tests/unit/_instance_state_support.py"]
    members["instance-state"]["sources"]["tests/unit/memory_instruments.py"] = "0" * 64
    _rewrite(head.parent / cost_report.CONDITIONS_FILE, head_conditions)
    assert cost_report.main(arguments) == 1
    assert (
        "the instance-state instrument tests/unit/memory_instruments.py differs"
        in capsys.readouterr().err
    )
    members["instance-state"]["sources"]["tests/unit/memory_instruments.py"] = base_members[
        "instance-state"
    ]["sources"]["tests/unit/memory_instruments.py"]
    members["instance-state"]["sources"]["tools/instance_state_reading.py"] = "f" * 64
    _rewrite(head.parent / cost_report.CONDITIONS_FILE, head_conditions)
    assert cost_report.main(arguments) == 1
    assert (
        "the instance-state instrument tools/instance_state_reading.py differs"
        in capsys.readouterr().err
    )


def test_a_malformed_conditions_sidecar_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _published)
    base, head, *_rest = _pair(tmp_path, contract)
    (head.parent / cost_report.CONDITIONS_FILE).write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        cost_report.main(["--compare", str(base), str(head), "--require-compatible"])
    assert error.value.code == 2
    assert "does not decode" in capsys.readouterr().err
