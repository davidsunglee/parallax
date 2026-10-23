from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal
from unittest.mock import Mock

import pytest

from tests._support import lane_evidence as evidence
from tests._support.case_corpus import reachable_cases

_SHA = "f42129df6837f3dd01178a54ddae1ac4453dd55f"
_SCENARIO = "packages/parallax-conformance/src/parallax/conformance/_lanes/scenario.py"
_SKIP = "diagnostic-only: captured m-storage-layout-024 uncaught AssertionError"
_MODE_NODE = "tests/api/test_to_one_traversal_performance.py::test_diagnostic_capture"
_MODE_REASON = "diagnostic: set PARALLAX_TO_ONE_PERFORMANCE_MODE=compare to run"


_CORPUS_HASHES = {
    "core/compatibility/cases/m-storage-layout-024-document-layout-occurrence-parent-states.yaml": (
        "b2ce228b2e19aefb6bb503e71353e7ff52d784b523a2eb53e847b2ad2b8bbae1",
        "f8bc1908468082c9a544fb381d6d65f0368b94ec2aab276eb2a1a7bc555b7074",
    ),
    "core/compatibility/cases/m-temporal-write-011-document-layout-unknown-key-preserved.yaml": (
        "c3dc2e4a156fce873f87b815d5fd3bba9709603dacacf52d49c00e8d4df2d290",
        "9c85c310198651a3f7ed9b7c952268af18977d1f87be4a6b9b242c8ad9573f00",
    ),
    (
        "core/compatibility/cases/"
        "m-temporal-write-012-document-layout-assigned-occurrence-replacement.yaml"
    ): (
        "150444875f23dc41c5fdb1a5b3130a354bd74f3415de8022e021ba92889469b2",
        "fca6869541245e6d03920ae676affa0ee58bebe13fd3bdcce923975291906ee1",
    ),
}


def _grade_node(case: str) -> str:
    sweep = (
        "test_write_run_sweep"
        if case == "m-storage-layout-024"
        else "test_run_only_write_sequence_run_sweep"
    )
    return f"tests/compatibility/test_run_sweep.py::{sweep}[{case}]"


def _probe_node(case: str) -> str:
    return f"tests/compatibility/test_lane_evidence.py::test_document_run_diagnostic[{case}]"


def _verdict_node(node: str) -> str:
    module, name = node.split("::")
    return module.removesuffix(".py").replace("/", ".") + "::" + name


def _record() -> dict[str, Any]:
    case = next(case for case in reachable_cases() if case.case_id == "m-pk-gen-001")
    return {
        "node": "tests/compatibility/test_compile_sweep.py::test_compile_sweep[m-pk-gen-001]",
        "case": case.case_id,
        "path": case.path.relative_to(evidence.REPO_ROOT).as_posix(),
        "lane": "compile",
        "ordinal": 0,
        "shape": "adapter",
        "profile": None,
        "dialect": "postgres",
        "actual": {"status": "ok", "databaseCalls": 1, "emissions": []},
    }


def _seal(directory: Path) -> None:
    _write_json(
        directory / "seal.json",
        {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("metadata.json", "observations.jsonl", "junit.xml")
        },
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value))


def _reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setattr(evidence, "corpus_manifest", Mock(return_value={"case": "hash"}))
    directories = tmp_path / "baseline", tmp_path / "candidate"
    for directory in directories:
        directory.mkdir()
        _write_json(
            directory / "metadata.json",
            {
                "format": 1,
                "identity": {"sha": "exact-sha", "supportHashes": {"support": "hash"}},
                "corpus": {"case": "hash"},
                "selected": ["test-node"],
                "requiredProvider": True,
                "provider": {"passed": 1},
                "exitstatus": 0,
            },
        )
        (directory / "observations.jsonl").write_text(json.dumps(_record()) + "\n")
        (directory / "junit.xml").write_text(
            '<testsuites><testsuite><testcase classname="tests.compatibility.test_compile_sweep" '
            'name="test_compile_sweep[m-pk-gen-001]"/></testsuite></testsuites>'
        )
        _seal(directory)
    return directories


def test_equivalent_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline, candidate = _reports(tmp_path, monkeypatch)
    result = evidence.compare_reports(baseline, candidate)
    assert result["classification"] == "equivalent"
    assert result["observations"] == result["nodes"] == 1


def _test_report(
    when: Literal["setup", "call", "teardown"], outcome: Literal["passed", "failed", "skipped"]
) -> pytest.TestReport:
    return pytest.TestReport(
        nodeid="tests/api/probe.py::test_probe",
        location=("tests/api/probe.py", 0, "test_probe"),
        keywords={"db": True},
        outcome=outcome,
        longrepr=("tests/api/probe.py", 0, "Skipped: diagnostic mode not selected")
        if outcome == "skipped"
        else None,
        when=when,
    )


@pytest.mark.parametrize(
    ("when", "outcome", "counts"),
    [
        ("setup", "passed", {}),
        ("teardown", "passed", {}),
        ("call", "passed", {"passed": 1}),
        ("setup", "failed", {"failed": 1}),
        ("call", "failed", {"failed": 1}),
        ("teardown", "failed", {"failed": 1}),
        ("setup", "skipped", {"skipped": 1}),
        ("call", "skipped", {"callSkipped": 1}),
        ("teardown", "skipped", {"skipped": 1}),
    ],
)
def test_provider_accounting_distinguishes_report_phases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    when: Literal["setup", "call", "teardown"],
    outcome: Literal["passed", "failed", "skipped"],
    counts: dict[str, int],
) -> None:
    monkeypatch.setattr(evidence, "_directory", tmp_path)
    provider: Counter[str] = Counter()
    monkeypatch.setattr(evidence, "_provider", provider)
    evidence.pytest_runtest_logreport(_test_report(when, outcome))
    assert provider == counts


@pytest.mark.parametrize("disabled", [True, False])
def test_provider_accounting_ignores_disabled_capture_or_dbfree_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, disabled: bool
) -> None:
    monkeypatch.setattr(evidence, "_directory", None if disabled else tmp_path)
    provider: Counter[str] = Counter()
    monkeypatch.setattr(evidence, "_provider", provider)
    report = _test_report("call", "passed")
    if not disabled:
        report.keywords = {}
    evidence.pytest_runtest_logreport(report)
    assert provider == {}


def test_diagnostic_skip_is_not_a_pass_or_provider_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, candidate = _reports(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence, "_directory", tmp_path)
    provider: Counter[str] = Counter()
    monkeypatch.setattr(evidence, "_provider", provider)
    evidence.pytest_runtest_logreport(_test_report("call", "passed"))
    evidence.pytest_runtest_logreport(_test_report("call", "skipped"))
    assert provider == {"passed": 1, "callSkipped": 1}
    for directory in (baseline, candidate):
        metadata_path = directory / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["provider"] = dict(provider)
        metadata["selected"].append("diagnostic-node")
        _write_json(metadata_path, metadata)
        (directory / "junit.xml").write_text(
            '<testsuites><testsuite><testcase classname="tests.compatibility.test_compile_sweep" '
            'name="test_compile_sweep[m-pk-gen-001]"/>'
            '<testcase classname="tests.api.probe" name="test_diagnostic">'
            '<skipped message="diagnostic mode not selected"/>'
            "</testcase></testsuite></testsuites>"
        )
        _seal(directory)
    assert evidence.compare_reports(baseline, candidate)["classification"] == "equivalent"
    junit = candidate / "junit.xml"
    junit.write_text(
        junit.read_text().replace('<skipped message="diagnostic mode not selected"/>', "")
    )
    _seal(candidate)
    result = evidence.compare_reports(baseline, candidate)
    assert result["classification"] == "unexplained"
    assert [item["reason"].splitlines()[0] for item in result["differences"]] == [
        "JUnit verdict or skip partition changed"
    ]


@pytest.mark.parametrize(
    "provider",
    [
        {},
        {"callSkipped": 1},
        {"passed": 1, "skipped": 1},
        {"passed": 1, "failed": 1},
    ],
)
def test_required_provider_evidence_stays_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: dict[str, int]
) -> None:
    baseline, candidate = _reports(tmp_path, monkeypatch)
    path = candidate / "metadata.json"
    metadata = json.loads(path.read_text())
    metadata["provider"] = provider
    _write_json(path, metadata)
    _seal(candidate)
    result = evidence.compare_reports(baseline, candidate)
    assert result["classification"] == "unexplained"
    assert [item["reason"].splitlines()[0] for item in result["differences"]] == [
        "required provider unavailable"
    ]


def _mode_skip_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    directories = _reports(tmp_path, monkeypatch)
    for directory in directories:
        path = directory / "metadata.json"
        metadata = json.loads(path.read_text())
        metadata["selected"].append(_MODE_NODE)
        metadata["provider"]["skipped"] = 1
        _write_json(path, metadata)
        tree = ET.parse(directory / "junit.xml")
        module, name = _verdict_node(_MODE_NODE).split("::")
        test = ET.SubElement(next(tree.iter("testsuite")), "testcase", classname=module, name=name)
        ET.SubElement(test, "skipped", message=_MODE_REASON)
        tree.write(directory / "junit.xml")
        _seal(directory)
    return directories


def test_sealed_existing_mode_skip_preserves_provider_and_verdicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, candidate = _mode_skip_reports(tmp_path, monkeypatch)
    result = evidence.compare_reports(baseline, candidate)
    assert result["classification"] == "equivalent"
    assert result["nodes"] == 2
    assert evidence.junit_verdicts(candidate / "junit.xml")[_verdict_node(_MODE_NODE)] == {
        "verdict": "skipped",
        "reason": _MODE_REASON,
    }


@pytest.mark.parametrize("outcome", ["skipped", "failure", "error"])
def test_known_mode_skip_cannot_hide_unrelated_provider_skip_or_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    baseline, candidate = _mode_skip_reports(tmp_path, monkeypatch)
    path = candidate / "metadata.json"
    metadata = json.loads(path.read_text())
    key = "skipped" if outcome == "skipped" else "failed"
    metadata["provider"][key] = metadata["provider"].get(key, 0) + 1
    _write_json(path, metadata)
    tree = ET.parse(candidate / "junit.xml")
    test = ET.SubElement(
        next(tree.iter("testsuite")), "testcase", classname="tests.api.probe", name="test_provider"
    )
    ET.SubElement(test, outcome, message="provider unavailable")
    tree.write(candidate / "junit.xml")
    _seal(candidate)
    assert evidence.compare_reports(baseline, candidate)["classification"] == "unexplained"


@pytest.mark.parametrize("change", ["provider", "passes", "required"])
def test_known_mode_skip_still_requires_positive_required_provider_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    baseline, candidate = _mode_skip_reports(tmp_path, monkeypatch)
    path = candidate / "metadata.json"
    metadata = json.loads(path.read_text())
    if change == "provider":
        del metadata["provider"]
    elif change == "passes":
        del metadata["provider"]["passed"]
    else:
        metadata["requiredProvider"] = False
    _write_json(path, metadata)
    _seal(candidate)
    assert evidence.compare_reports(baseline, candidate)["classification"] == "unexplained"


@pytest.mark.parametrize("change", ["reason", "verdict", "node", "missing", "unsealed"])
def test_mode_skip_admission_requires_exact_sealed_junit_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    baseline, candidate = _mode_skip_reports(tmp_path, monkeypatch)
    tree = ET.parse(candidate / "junit.xml")
    test = next(t for t in tree.iter("testcase") if t.get("name") == "test_diagnostic_capture")
    skipped = test.find("skipped")
    assert skipped is not None
    if change in {"reason", "unsealed"}:
        skipped.set("message", "provider unavailable")
    elif change == "node":
        test.set("classname", "tests.api.unrelated")
    elif change == "missing":
        next(tree.iter("testsuite")).remove(test)
    else:
        test.remove(skipped)
    tree.write(candidate / "junit.xml")
    if change != "unsealed":
        _seal(candidate)
    assert evidence.compare_reports(baseline, candidate)["classification"] == "unexplained"


@pytest.mark.parametrize("change", ["reason", "verdict"])
def test_changed_known_skip_partition_fails_even_with_otherwise_admissible_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    baseline, candidate = _mode_skip_reports(tmp_path, monkeypatch)
    path = candidate / "metadata.json"
    metadata = json.loads(path.read_text())
    metadata["provider"] = {"passed": 2, "callSkipped": 1}
    _write_json(path, metadata)
    tree = ET.parse(candidate / "junit.xml")
    skipped = tree.find(".//testcase/skipped")
    assert skipped is not None
    if change == "reason":
        skipped.set("message", "different diagnostic mode")
    else:
        test = next(t for t in tree.iter("testcase") if t.find("skipped") is skipped)
        test.remove(skipped)
    tree.write(candidate / "junit.xml")
    _seal(candidate)
    assert evidence.compare_reports(baseline, candidate)["classification"] == "unexplained"


@pytest.mark.parametrize("change", ["selection", "corpus", "provider", "exit", "identity"])
def test_changed_metadata_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    baseline, candidate = _reports(tmp_path, monkeypatch)
    path = candidate / "metadata.json"
    metadata = json.loads(path.read_text())
    if change == "selection":
        metadata["selected"] = []
    elif change == "corpus":
        metadata["corpus"] = {"case": "changed"}
    elif change == "provider":
        metadata["provider"] = {"skipped": 1}
    elif change == "exit":
        metadata["exitstatus"] = 1
    else:
        path = baseline / "metadata.json"
        metadata["identity"] = {"sha": "unverified"}
    _write_json(path, metadata)
    _seal(path.parent)
    assert evidence.compare_reports(baseline, candidate)["classification"] == "unexplained"


@pytest.mark.parametrize("change", ["missing", "actual", "verdict", "tampered"])
def test_missing_or_changed_answers_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    baseline, candidate = _reports(tmp_path, monkeypatch)
    if change == "verdict":
        (candidate / "junit.xml").write_text(
            '<testsuites><testsuite><testcase classname="tests.compatibility.test_compile_sweep" '
            'name="test_compile_sweep[m-pk-gen-001]"><skipped message="unavailable"/>'
            "</testcase></testsuite></testsuites>"
        )
    else:
        record = _record()
        record["actual"]["databaseCalls"] = 2
        (candidate / "observations.jsonl").write_text(
            "" if change == "missing" else json.dumps(record) + "\n"
        )
    if change != "tampered":
        _seal(candidate)
    assert evidence.compare_reports(baseline, candidate)["classification"] == "unexplained"


def test_only_measured_tracker_diagnostic_has_local_provenance() -> None:
    unrelated: dict[str, Any] = {
        "status": "error",
        "diagnostics": [{"code": "run-failed", "message": "connection lost"}],
    }
    assert evidence.tracker_provenance(unrelated) is None
    tracked = deepcopy(unrelated)
    tracked["diagnostics"][0]["message"] = "out-of-band statements may have overtaken or stored"
    assert evidence.tracker_provenance(tracked) == "tracked-document-milestone-refusal"
    tracked["diagnostics"][0]["code"] = "other-code"
    assert evidence.tracker_provenance(tracked) is None


def test_rows_compare_as_multisets_but_streams_stay_ordered() -> None:
    case = next(case for case in reachable_cases() if case.case_id == "m-unit-work-030")
    left: dict[str, Any] = {"stepRows": [{"at": "/scenario/0", "rows": [{"id": 1}, {"id": 2}]}]}
    right = deepcopy(left)
    right["stepRows"][0]["rows"].reverse()
    with pytest.raises(AssertionError):
        evidence.compare_observations(left, right, case)
    evidence.compare_observations(
        {"rows": [{"id": 1}, {"id": 2}]}, {"rows": [{"id": 2}, {"id": 1}]}, case
    )


def test_baseline_guard_refuses_wrong_sha(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(evidence, "_git", Mock(return_value="other-sha"))
    with pytest.raises(ValueError, match="exact SHA"):
        evidence.baseline_identity(tmp_path, "expected-sha")


@pytest.mark.parametrize(
    "status", [" M runner.py\n", "?? new_source.py\n", "M  core/schemas/case.json\n"]
)
def test_baseline_guard_refuses_other_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: str
) -> None:
    monkeypatch.setattr(evidence, "_git", Mock(return_value="expected-sha"))
    monkeypatch.setattr(evidence.subprocess, "check_output", Mock(return_value=status))
    with pytest.raises(ValueError, match="outside test-only"):
        evidence.baseline_identity(tmp_path, "expected-sha")


def test_corpus_manifest_refuses_new_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(evidence, "_git", Mock(return_value="core/compatibility/new.yaml"))
    with pytest.raises(ValueError, match="untracked corpus inputs"):
        evidence.corpus_manifest(tmp_path)


def test_capture_retains_nested_immutable_json_mappings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(evidence, "_directory", tmp_path)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/compatibility/probe.py::test_probe (call)")
    case = next(case for case in reachable_cases() if case.case_id == "m-pk-gen-001")
    envelope: dict[str, Any] = {
        "status": "ok",
        "observations": {"rows": [{"tag": MappingProxyType({"label": "b"})}]},
    }
    evidence.capture_adapter(case, "run", envelope)
    recorded = json.loads((tmp_path / "observations.jsonl").read_text())
    assert recorded["actual"] == envelope
    assert isinstance(envelope["observations"]["rows"][0]["tag"], MappingProxyType)


def _document_record(case_id: str) -> dict[str, Any]:
    case = next(case for case in reachable_cases() if case.case_id == case_id)
    record = _record()
    record.update(
        case=case_id,
        path=case.path.relative_to(evidence.REPO_ROOT).as_posix(),
        node=_probe_node(case_id),
        lane="run",
    )
    if case_id == "m-storage-layout-024":
        record.update(
            shape="uncaught-exception",
            profile="pg-full",
            actual={
                "type": "builtins.AssertionError",
                "message": "",
                "terminal": {
                    "path": _SCENARIO,
                    "function": "_node_object_key",
                    "source": "assert authority is not None",
                },
                "traceback": "raw traceback",
            },
        )
    else:
        record.update(
            provenance="tracked-document-milestone-refusal",
            actual={
                "status": "error",
                "diagnostics": [
                    {
                        "code": "run-failed",
                        "message": "out-of-band statements may have overtaken or stored",
                    }
                ],
            },
        )
    return record


def _failed_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    baseline, candidate = _reports(tmp_path, monkeypatch)
    supplement = tmp_path / "supplement"
    supplement.mkdir()
    records = [_document_record(case) for case in sorted(evidence.DOCUMENT_CASES)]
    for directory in (baseline, candidate, supplement):
        metadata = json.loads((baseline / "metadata.json").read_text())
        metadata["identity"]["sha"] = _SHA
        metadata["selected"] = sorted(r["node"] for r in records)
        if directory != supplement:
            metadata["selected"] = sorted([*metadata["selected"], _MODE_NODE])
        if directory == baseline:
            metadata.update(exitstatus=1, provider={"failed": 1, "passed": 2475, "skipped": 1})
        else:
            metadata.update(exitstatus=0, provider={"passed": 2, "callSkipped": 1})
            if directory == candidate:
                metadata["provider"]["skipped"] = 1
        _write_json(directory / "metadata.json", metadata)
        (directory / "observations.jsonl").write_text(
            "".join(
                json.dumps(r) + "\n"
                for r in records
                if directory != baseline or r["shape"] != "uncaught-exception"
            )
        )
        suite = ET.Element("testsuite")
        for record in records:
            module, name = _verdict_node(record["node"]).split("::")
            test = ET.SubElement(suite, "testcase", classname=module, name=name)
            if record["shape"] == "uncaught-exception":
                if directory == baseline:
                    ET.SubElement(
                        test, "failure", message="AssertionError"
                    ).text = "_node_object_key: assert authority is not None"
                else:
                    ET.SubElement(test, "skipped", message=_SKIP)
        if directory != supplement:
            test = ET.SubElement(
                suite,
                "testcase",
                classname="tests.api.test_to_one_traversal_performance",
                name="test_diagnostic_capture",
            )
            ET.SubElement(
                test,
                "skipped",
                message=_MODE_REASON,
            )
        ET.ElementTree(suite).write(directory / "junit.xml")
        _seal(directory)
    seal = hashlib.sha256((baseline / "seal.json").read_bytes()).hexdigest()
    monkeypatch.setattr(evidence, "_ORIGINAL_SEAL", seal)
    metadata = json.loads((supplement / "metadata.json").read_text())
    metadata["originalSeal"] = seal
    _write_json(supplement / "metadata.json", metadata)
    _seal(supplement)
    return baseline, candidate, supplement


def test_failed_archive_requires_separate_guarded_supplement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, candidate, supplement = _failed_reports(tmp_path, monkeypatch)
    assert evidence.compare_reports(baseline, candidate)["classification"] == "unexplained"
    result = evidence.compare_reports(baseline, candidate, supplement=supplement)
    assert result["classification"] == "equivalent-with-diagnostic-baseline-failure"
    assert result["baselineFailure"]["verdict"]["verdict"] == "failure"
    assert result["explainedTransitions"][0]["new"]["verdict"] == "skipped"
    assert json.loads((baseline / "metadata.json").read_text())["exitstatus"] == 1


@pytest.mark.parametrize(
    "change",
    ["seal", "guard", "provider", "selection", "exception", "refusal", "verdict", "missing"],
)
def test_failed_archive_supplement_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    baseline, candidate, supplement = _failed_reports(tmp_path, monkeypatch)
    path = supplement / "metadata.json"
    metadata = json.loads(path.read_text())
    if change == "seal":
        metadata["originalSeal"] = "unrelated"
    elif change == "guard":
        metadata["identity"]["sha"] = "wrong-sha"
    elif change == "provider":
        metadata["provider"]["skipped"] = 1
    elif change == "selection":
        metadata["selected"].pop()
    elif change in {"exception", "refusal", "missing"}:
        records = [
            json.loads(line)
            for line in (supplement / "observations.jsonl").read_text().splitlines()
        ]
        if change == "missing":
            records.pop()
        elif change == "exception":
            records[0]["actual"]["terminal"]["function"] = "unrelated"
        else:
            records[-1]["actual"]["diagnostics"][0]["message"] = "connection lost"
        (supplement / "observations.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in records)
        )
    else:
        junit = supplement / "junit.xml"
        tree = ET.parse(junit)
        for test in tree.iter("testcase"):
            for skipped in list(test):
                test.remove(skipped)
        tree.write(junit)
    _write_json(path, metadata)
    _seal(supplement)
    assert (
        evidence.compare_reports(baseline, candidate, supplement=supplement)["classification"]
        == "unexplained"
    )


@pytest.mark.parametrize(
    "source", ["assert authority is not None", "assert False", 'raise AssertionError("different")']
)
def test_exception_capture_is_site_and_message_specific(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    monkeypatch.setattr(evidence, "_directory", tmp_path)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", _probe_node("m-storage-layout-024") + " (call)")
    path = tmp_path / _SCENARIO
    path.parent.mkdir(parents=True)
    path.write_text("def _node_object_key():\n    authority = None\n    " + source + "\n")
    namespace: dict[str, Any] = {}
    exec(compile(path.read_text(), str(path), "exec"), namespace)
    case = next(case for case in reachable_cases() if case.case_id == "m-storage-layout-024")
    with pytest.raises(AssertionError) as raised:
        namespace["_node_object_key"]()
    if source == "assert authority is not None":
        with pytest.raises(pytest.skip.Exception, match="diagnostic-only"):
            evidence.capture_document_exception(case, raised.value)
        record = json.loads((tmp_path / "observations.jsonl").read_text())
        assert record["shape"] == "uncaught-exception" and "status" not in record["actual"]
    else:
        with pytest.raises(AssertionError):
            evidence.capture_document_exception(case, raised.value)
        assert not (tmp_path / "observations.jsonl").exists()


def _add_compile_transition_evidence(
    directory: Path,
    candidate: Path,
    metadata: dict[str, Any],
    records: list[dict[str, Any]],
    suite: ET.Element,
) -> None:
    for case in sorted(evidence.DOCUMENT_CASES):
        original = _document_record(case)
        for name in (
            f"test_compile_sweep[{case}]",
            "test_run_only_cases_are_never_compiled",
        ):
            record = {
                **original,
                "lane": "compile",
                "shape": "adapter",
                "profile": None,
                "provenance": None,
            }
            record["node"] = f"tests/compatibility/test_compile_sweep.py::{name}"
            record["actual"] = {
                "status": "run-only",
                "caseShape": "scenario"
                if case == "m-storage-layout-024" and directory == candidate
                else "writeSequence",
            }
            records.append(record)
            module, test_name = _verdict_node(record["node"]).split("::")
            if not any(t.attrib.get("name") == test_name for t in suite):
                test = ET.SubElement(suite, "testcase", classname=module, name=test_name)
                ET.SubElement(test, "skipped", message="run-only")
            metadata["selected"].append(record["node"])
    metadata["selected"] = sorted(set(metadata["selected"]))


def _transition_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    baseline, candidate, supplement = _failed_reports(tmp_path, monkeypatch)
    hashes = _CORPUS_HASHES
    old_corpus = {path: pair[0] for path, pair in hashes.items()}
    new_corpus = {path: pair[1] for path, pair in hashes.items()}
    old_corpus["core/schemas/case.schema.json"] = "unchanged"
    new_corpus["core/schemas/case.schema.json"] = "unchanged"
    monkeypatch.setattr(evidence, "corpus_manifest", Mock(return_value=new_corpus))
    for directory in (baseline, candidate, supplement):
        metadata = json.loads((directory / "metadata.json").read_text())
        metadata["corpus"] = new_corpus if directory == candidate else old_corpus
        records = [
            json.loads(line) for line in (directory / "observations.jsonl").read_text().splitlines()
        ]
        tree = ET.parse(directory / "junit.xml")
        suite = next(tree.iter("testsuite"))
        if directory == candidate:
            for record in records:
                record.update(
                    node=_grade_node(record["case"]),
                    shape="adapter",
                    actual={"status": "ok", "emissions": [], "observations": {}},
                )
            for test in list(suite):
                if test.attrib["classname"].endswith("test_lane_evidence"):
                    suite.remove(test)
            for record in records:
                module, name = _verdict_node(record["node"]).split("::")
                ET.SubElement(suite, "testcase", classname=module, name=name)
            metadata["selected"] = sorted([*(r["node"] for r in records), _MODE_NODE])
            metadata["provider"] = {"passed": 3, "skipped": 1}
        if directory != supplement:
            _add_compile_transition_evidence(directory, candidate, metadata, records, suite)
        _write_json(directory / "metadata.json", metadata)
        (directory / "observations.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in records)
        )
        tree.write(directory / "junit.xml")
        _seal(directory)
    seal = hashlib.sha256((baseline / "seal.json").read_bytes()).hexdigest()
    monkeypatch.setattr(evidence, "_ORIGINAL_SEAL", seal)
    path = supplement / "metadata.json"
    metadata = json.loads(path.read_text())
    metadata["originalSeal"] = seal
    _write_json(path, metadata)
    _seal(supplement)
    return baseline, candidate, supplement


def test_document_transition_requires_exact_hashes_selection_and_full_grades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, candidate, supplement = _transition_reports(tmp_path, monkeypatch)
    assert (
        evidence.compare_reports(baseline, candidate, supplement=supplement)["classification"]
        == "unexplained"
    )
    result = evidence.compare_reports(
        baseline, candidate, supplement=supplement, newly_graded_document_cases=True
    )
    assert result["classification"] == "explained-corpus-operation-coverage-outcome-transition", (
        result
    )
    assert len(result["explainedTransitions"]) == 9
    assert result["baselineFailure"]["verdict"]["verdict"] == "failure"
    assert {
        item["path"]
        for item in result["explainedTransitions"]
        if item["kind"] == "intentional-corpus-correction"
    } == _CORPUS_HASHES.keys()


def _change_compile(records: list[dict[str, Any]], change: str) -> None:
    index = next(i for i, r in enumerate(records) if r["lane"] == "compile")
    if change == "missing-compile":
        records.pop(index)
    elif change == "compile-status":
        records[index]["actual"]["status"] = "ok"
    elif change == "compile-shape":
        records[index]["actual"]["caseShape"] = "writeSequence"
    else:
        records[index]["actual"]["diagnostics"] = []


def _change_corpus(
    change: str,
    baseline: Path,
    candidate: Path,
    metadata: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, dict[str, Any]]:
    path = candidate / "metadata.json"
    corpus_path = next(iter(_CORPUS_HASHES))
    if change == "old-hash":
        path = baseline / "metadata.json"
        metadata = json.loads(path.read_text())
        metadata["corpus"][corpus_path] = "unapproved-old"
    elif change in {"new-hash", "unchanged-case", "schema", "extra-corpus", "missing-corpus"}:
        if change == "new-hash":
            metadata["corpus"][corpus_path] = "unapproved-new"
        elif change == "unchanged-case":
            metadata["corpus"][corpus_path] = _CORPUS_HASHES[corpus_path][0]
        elif change == "schema":
            metadata["corpus"]["core/schemas/case.schema.json"] = "changed"
        elif change == "missing-corpus":
            del metadata["corpus"][corpus_path]
        else:
            metadata["corpus"]["core/compatibility/cases/unrelated.yaml"] = "added"
        monkeypatch.setattr(evidence, "corpus_manifest", Mock(return_value=metadata["corpus"]))
    elif change == "current-corpus":
        monkeypatch.setattr(evidence, "corpus_manifest", Mock(return_value={}))
    return path, metadata


@pytest.mark.parametrize(
    "change",
    [
        "old-hash",
        "new-hash",
        "extra-corpus",
        "schema",
        "missing-corpus",
        "unchanged-case",
        "current-corpus",
        "wrong-sweep",
        "extra-selection",
        "missing-selection",
        "skipped-grade",
        "failed-grade",
        "error-envelope",
        "refusal",
        "missing-compile",
        "compile-status",
        "compile-envelope",
        "compile-shape",
        "missing-run",
    ],
)
def test_document_authorization_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    baseline, candidate, supplement = _transition_reports(tmp_path, monkeypatch)
    path = candidate / "metadata.json"
    metadata = json.loads(path.read_text())
    records = [
        json.loads(line) for line in (candidate / "observations.jsonl").read_text().splitlines()
    ]
    tree = ET.parse(candidate / "junit.xml")
    if change in {
        "old-hash",
        "new-hash",
        "unchanged-case",
        "schema",
        "extra-corpus",
        "missing-corpus",
        "current-corpus",
    }:
        path, metadata = _change_corpus(change, baseline, candidate, metadata, monkeypatch)
    elif change == "extra-selection":
        metadata["selected"].append("tests/unrelated.py::test_extra")
    elif change == "missing-selection":
        metadata["selected"].remove(records[0]["node"])
    elif change == "wrong-sweep":
        old_node = records[0]["node"]
        records[0]["node"] = old_node.replace(
            "test_write_run_sweep", "test_run_only_write_sequence_run_sweep"
        )
        metadata["selected"].remove(old_node)
        metadata["selected"].append(records[0]["node"])
    elif change in {"skipped-grade", "failed-grade"}:
        target = next(
            t for t in tree.iter("testcase") if t.attrib["name"].startswith("test_write_run_sweep")
        )
        ET.SubElement(
            target, "skipped" if change == "skipped-grade" else "failure", message="not graded"
        )
    elif change == "error-envelope":
        records[0]["actual"]["status"] = "error"
    elif change == "refusal":
        source = supplement / "observations.jsonl"
        items = [json.loads(line) for line in source.read_text().splitlines()]
        items[-1]["actual"]["diagnostics"][0]["message"] = "connection lost"
        source.write_text("".join(json.dumps(r) + "\n" for r in items))
        _seal(supplement)
    elif change == "missing-run":
        records.pop(0)
    else:
        _change_compile(records, change)
    _write_json(path, metadata)
    (candidate / "observations.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    tree.write(candidate / "junit.xml")
    _seal(path.parent)
    _seal(candidate)
    result = evidence.compare_reports(
        baseline, candidate, supplement=supplement, newly_graded_document_cases=True
    )
    assert result["classification"] == "unexplained", result
