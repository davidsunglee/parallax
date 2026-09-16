from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

import cost_report
import write_lowering_overhead as write_report
from cost_report import (
    MEMBERS,
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
from interpreter_matrix import authority_minor, supported_minors
from parallax.conformance.budget import BudgetContract
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

    def failing(member: Member) -> tuple[int, str, str]:
        attempted.append(member.recipe)
        return (7, "", f"{member.recipe} failed")

    results, failed_required = collect(failing)
    assert attempted == [member.recipe for member in MEMBERS]
    assert len(results) == len(MEMBERS)
    assert failed_required


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

    def run(member: Member) -> tuple[int, str, str]:
        if member.subject == "snapshot-delivery":
            return (0, json.dumps(snapshot), "")
        if member.subject == write_report.SUBJECT:
            return (0, json.dumps(write), "")
        return (9, "", "optional report unavailable")

    results, failed_required = collect(run)
    assert not failed_required
    assert results[0].envelope is not None


def test_collection_decodes_each_members_own_envelope() -> None:
    contract = BudgetContract.load()
    snapshot = _complete_snapshot(contract)
    write = _complete_write(contract)

    def run(member: Member) -> tuple[int, str, str]:
        document = (
            snapshot
            if member.subject == "snapshot-delivery"
            else write
            if member.subject == write_report.SUBJECT
            else _optional_document(member)
        )
        return (0, json.dumps(document), "")

    results, failed_required = collect(run)
    assert not failed_required
    assert [result.envelope["subject"] for result in results if result.envelope] == [
        member.subject for member in MEMBERS
    ]
    summary = cost_report._summary(  # pyright: ignore[reportPrivateUsage] - rendered output under test
        portfolio_document(results)
    )
    assert ", ".join(supported_minors()) in summary


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
        (_drop_a_runtime, "reading matrix is not exact: missing CPython"),
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


def test_an_adverse_timing_outcome_is_advisory_and_a_memory_outcome_fails(
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
    assert "advisory:" in capsys.readouterr().out
    memory = _first_comparison(snapshot, timing=False)
    _push_outside(snapshot, memory)
    assert verify(document) == [f"{memory['workload']}.{memory['cell']} is outside"]


def test_verification_requires_clean_published_and_fresh_producing_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(cost_report, "is_published", _unpublished)
    document = _verifiable(contract)
    failures = verify(document)
    assert failures == [
        "the snapshot-delivery envelope's producing commit "
        f"{_snapshot_of(document)['provenance']['commit'][:12]} is not an ancestor of the "
        "inspected head",
        "the write-lowering envelope's producing commit "
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

    def run(member: Member) -> tuple[int, str, str]:
        attempted.append(member.recipe)
        document = (
            snapshot
            if member.subject == "snapshot-delivery"
            else write
            if member.subject == write_report.SUBJECT
            else _optional_document(member)
        )
        return (0, json.dumps(document), "")

    results, failed_required = collect(run)
    assert attempted == [member.recipe for member in MEMBERS]
    assert failed_required
    assert results[0].envelope is None
    assert all(result.envelope is not None for result in results[1:])


def test_strict_verification_detects_changed_checkout_lock_without_changing_authority(
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
        "stale snapshot-delivery evidence: "
        f"recorded lockDigest={hashlib.sha256(original_lock).hexdigest()}; "
        f"inspected lockDigest={hashlib.sha256(lock.read_bytes()).hexdigest()} ({lock})"
    )
    assert verify(document) == [expected]
    assert cost_report.main(["--verify", str(portfolio)]) == 1
    assert capsys.readouterr().err == expected + "\n"
    validate(snapshot)
    assert snapshot["authority"] == "authoritative"


def test_staleness_preserves_other_verification_failures(
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
        f"{memory['workload']}.{memory['cell']} is outside",
        f"{scaling['workload']}.{scaling['cell']} is outside",
        f"{scaling['workload']}.{scaling['cell']} grows 100.000 KiB between memory arms",
    ]
    (tmp_path / "uv.lock").write_bytes(b"updated dependencies")
    monkeypatch.setattr(cost_report, "WORKSPACE", tmp_path)
    failures = verify(document)
    assert failures[0].startswith("stale snapshot-delivery evidence:")
    assert failures[1:] == expected
    snapshot["comparisons"].clear()
    failures = verify(document)
    assert failures[0].startswith("stale snapshot-delivery evidence:")
    assert "comparison matrix is not exact" in failures[1]


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
    assert cost_report.main(args) == 1
    assert "stale snapshot-delivery evidence:" in capsys.readouterr().out


@pytest.mark.parametrize("members", [[], [{"subject": "snapshot-delivery", "provenance": None}]])
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
