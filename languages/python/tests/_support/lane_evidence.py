"""Opt-in compatibility observations and a fixed-format cross-revision check."""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import subprocess
import traceback
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance import adapter, case_format, engine
from tests._support.corpus import (
    CollectionKinds,
    case_document,
    compare_binds,
    compare_graph,
    compare_rows,
    compare_rows_in_order,
    wire_value_deep,
)
from tests._support.repo import REPO_ROOT

DOCUMENT_CASES = frozenset({"m-temporal-write-011", "m-temporal-write-012", "m-storage-layout-024"})
_BASELINE_SUPPORT = (
    "languages/python/tests/_support/lane_evidence.py",
    "languages/python/tests/unit/test_lane_evidence.py",
    "languages/python/tests/compatibility/test_lane_evidence.py",
    "languages/python/tests/compatibility/test_compile_sweep.py",
    "languages/python/tests/compatibility/test_run_sweep.py",
)
_TRACKER_FRAGMENT = "out-of-band statements may have overtaken or stored"
_BASELINE_SHA = "f42129df6837f3dd01178a54ddae1ac4453dd55f"
_ORIGINAL_SEAL = "dcadfc565bebd8d9ff5019952423d6663008a2c875d310267c58fc2920b8a785"
_EXCEPTION_SKIP = "diagnostic-only: captured m-storage-layout-024 uncaught AssertionError"
_SCENARIO_PATH = "packages/parallax-conformance/src/parallax/conformance/_lanes/scenario.py"
_MODE_SKIP_NODE = "tests/api/test_to_one_traversal_performance.py::test_diagnostic_capture"
_MODE_SKIP_REASON = "diagnostic: set PARALLAX_TO_ONE_PERFORMANCE_MODE=compare to run"
_DOCUMENT_HASHES = {
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
_directory: Path | None = None
_metadata: dict[str, Any] = {}
_occurrences: Counter[tuple[str, str, str]] = Counter()
_provider: Counter[str] = Counter()


def _git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus_manifest(root: Path) -> dict[str, str]:
    paths = ("core/compatibility/", "core/schemas/")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "--", *paths)
    if untracked:
        raise ValueError(f"untracked corpus inputs: {untracked}")
    return {
        name: _digest(root / name)
        for name in sorted(_git(root, "ls-files", "--", *paths).splitlines())
    }


def baseline_identity(root: Path, sha: str) -> dict[str, Any]:
    if _git(root, "rev-parse", "HEAD") != sha:
        raise ValueError("baseline HEAD does not equal the required exact SHA")
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    # Preserve the two status columns, including the leading space on an unstaged edit.
    lines = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True
    ).splitlines()
    if any(line[3:] not in _BASELINE_SUPPORT or "R" in line[:2] for line in lines):
        raise ValueError(f"baseline contains changes outside test-only evidence support: {status}")
    return {
        "sha": sha,
        "status": status,
        "supportHashes": {name: _digest(root / name) for name in _BASELINE_SUPPORT},
        "supportPatch": _git(root, "diff", "HEAD", "--", *_BASELINE_SUPPORT),
    }


def tracker_provenance(envelope: dict[str, Any]) -> str | None:
    if envelope.get("status") != "error":
        return None
    if any(
        item.get("code") == "run-failed" and _TRACKER_FRAGMENT in item.get("message", "")
        for item in envelope.get("diagnostics", [])
    ):
        return "tracked-document-milestone-refusal"
    return None


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def pytest_collection_finish(session: pytest.Session) -> None:
    global _directory, _metadata
    target = os.environ.get("PARALLAX_LANE_EVIDENCE_DIR")
    if target is None:
        return
    directory = Path(target)
    if not directory.is_dir():
        raise pytest.UsageError("create and verify the evidence directory before capture")
    if (directory / "metadata.json").exists():
        raise pytest.UsageError("evidence capture is immutable; use a fresh directory")
    sha = os.environ.get("PARALLAX_LANE_EVIDENCE_BASELINE_SHA")
    try:
        identity = (
            baseline_identity(REPO_ROOT, sha)
            if sha
            else {"sha": _git(REPO_ROOT, "rev-parse", "HEAD")}
        )
        manifest = corpus_manifest(REPO_ROOT)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc
    _directory = directory
    _metadata = {
        "format": 1,
        "identity": identity,
        "corpus": manifest,
        "selected": sorted(item.nodeid for item in session.items),
        "requiredProvider": os.environ.get("PARALLAX_REQUIRE_DB") == "1",
    }
    original = os.environ.get("PARALLAX_LANE_EVIDENCE_ORIGINAL")
    if original:
        if sha != _BASELINE_SHA or _digest(Path(original) / "seal.json") != _ORIGINAL_SEAL:
            raise pytest.UsageError("supplement requires the guarded original SHA and pinned seal")
        _metadata["originalSeal"] = _ORIGINAL_SEAL
    _write_json(_directory / "metadata.json", _metadata)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if (
        _directory is not None
        and "db" in report.keywords
        and (report.when == "call" or report.failed or report.skipped)
    ):
        outcome = "callSkipped" if report.when == "call" and report.skipped else report.outcome
        _provider[outcome] += 1


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _directory is not None:
        _metadata["exitstatus"] = int(exitstatus)
        _metadata["provider"] = dict(_provider)
        _write_json(_directory / "metadata.json", _metadata)
        _write_json(
            _directory / "seal.json",
            {
                name: _digest(_directory / name)
                for name in ("metadata.json", "observations.jsonl", "junit.xml")
                if (_directory / name).is_file()
            },
        )


def _capture(
    case: case_format.Case, lane: str, shape: str, actual: Any, profile: str | None
) -> None:
    if _directory is None:
        return
    node = os.environ["PYTEST_CURRENT_TEST"].rsplit(" (", 1)[0]
    path = case.path.resolve().relative_to(REPO_ROOT).as_posix()
    identity = (node, path, lane)
    ordinal = _occurrences[identity]
    _occurrences[identity] += 1
    record = {
        "node": node,
        "case": case.case_id,
        "path": path,
        "lane": lane,
        "ordinal": ordinal,
        "shape": shape,
        "profile": profile,
        "dialect": "postgres",
        "actual": actual,
    }
    if case.case_id in DOCUMENT_CASES and shape == "adapter":
        record["provenance"] = tracker_provenance(actual)
    with (_directory / "observations.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, default=_json_mapping) + "\n")


def _json_mapping(value: object) -> object:
    if isinstance(value, Mapping):
        return dict(cast("Mapping[str, object]", value))
    raise TypeError(f"not a JSON envelope value: {type(value).__name__}")


def capture_adapter(case: case_format.Case, lane: str, actual: dict[str, Any]) -> None:
    _capture(case, lane, "adapter", actual, actual.get("profile"))


def capture_document_exception(case: case_format.Case, exception: AssertionError) -> None:
    frames = traceback.extract_tb(exception.__traceback__)
    terminal = frames[-1]
    assert case.case_id == "m-storage-layout-024" and type(exception) is AssertionError
    assert str(exception) == "" and terminal.name == "_node_object_key"
    assert Path(terminal.filename).as_posix().endswith("/" + _SCENARIO_PATH)
    assert terminal.line is not None and terminal.line.startswith("assert authority is not None")
    _capture(
        case,
        "run",
        "uncaught-exception",
        {
            "type": "builtins.AssertionError",
            "message": str(exception),
            "terminal": {
                "path": _SCENARIO_PATH,
                "function": terminal.name,
                "source": terminal.line,
            },
            "traceback": "".join(traceback.format_exception(exception)),
        },
        "pg-full",
    )
    pytest.skip(_EXCEPTION_SKIP)


@pytest.fixture(autouse=True)
def capture_adapter_calls(request: Any) -> Iterator[None]:
    item = cast("pytest.Item", request.node)
    if (
        _directory is None
        or item.path.name not in {"test_compile_sweep.py", "test_run_sweep.py"}
        or "compatibility" not in item.path.parts
    ):
        yield
        return
    with pytest.MonkeyPatch.context() as patch:
        for name, lane in (("compile_case", "compile"), ("run_case", "run")):
            original = getattr(adapter, name)

            def observed(function: Any, entrypoint: str) -> Any:
                @functools.wraps(function)
                def call(path: Path, *args: Any, **kwargs: Any) -> dict[str, Any]:
                    result = function(path, *args, **kwargs)
                    capture_adapter(case_format.load_case(path), entrypoint, result)
                    return result

                return call

            patch.setattr(adapter, name, observed(original, lane))
        yield


def capture_scenario(case: case_format.Case, run: Any) -> None:
    if _directory is None:
        return
    actual = {
        "emissions": [emission.to_json() for emission in run.emissions],
        "observations": wire_value_deep(
            {
                "databaseCalls": run.database_calls,
                "errors": run.errors,
                "stepRows": run.step_rows,
                "stepGraphs": run.step_graphs,
                "units": run.units,
                "tableState": run.table_state,
                "stepAffectedRows": run.step_affected_rows,
            }
        ),
    }
    _capture(case, "interleaved", "scenario", actual, "pg-full")


def capture_rounds(case: case_format.Case, run: Any) -> None:
    if _directory is None:
        return
    actual = [
        {
            node: {
                "rows": wire_value_deep(list(outcome.rows)),
                "affected": list(outcome.affected),
                "error": None
                if outcome.error is None
                else {"category": outcome.error.category, "nativeCode": outcome.error.native_code},
                "waited": outcome.waited,
            }
            for node, outcome in round_outcomes.items()
        }
        for round_outcomes in run.rounds
    ]
    _capture(case, "concurrency", "rounds", actual, "pg-full")


def junit_verdicts(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in ET.parse(path).iter("testcase"):
        key = item.attrib["classname"] + "::" + item.attrib["name"]
        if key in result:
            raise ValueError(f"duplicate JUnit node: {key}")
        verdict = next(
            (tag for tag in ("failure", "error", "skipped") if item.find(tag) is not None), "passed"
        )
        child = item.find(verdict)
        result[key] = {
            "verdict": verdict,
            "reason": child.get("message") if child is not None else None,
        }
    if not result:
        raise ValueError("missing JUnit test verdicts")
    return result


def _observations(directory: Path) -> dict[tuple[Any, ...], dict[str, Any]]:
    result: dict[tuple[Any, ...], dict[str, Any]] = {}
    for line in (directory / "observations.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        key = tuple(record[name] for name in ("path", "lane", "node", "ordinal"))
        if key in result:
            raise ValueError(f"duplicate observation: {key}")
        result[key] = record
    if not result:
        raise ValueError("missing compatibility observations")
    return result


def compare_observations(
    left: dict[str, Any], right: dict[str, Any], case: case_format.Case
) -> None:
    assert left.keys() == right.keys(), "observation fields changed"
    model = engine.load_case_metamodel(case)
    for name, value in left.items():
        actual = right[name]
        if name == "rows":
            compare_rows(actual, value)
        elif name == "tableState" and value is not None:
            assert actual.keys() == value.keys()
            for table, rows in value.items():
                compare_rows(actual[table], rows)
        elif name in {"graph", "graphs", "stepGraphs"} and value is not None:
            _compare_graphs(name, value, actual, CollectionKinds(model))
        elif name == "stepRows" and value is not None:
            assert len(value) == len(actual)
            steps = case_document(case)["when"].get("scenario", [])
            for old, new in zip(value, actual, strict=True):
                assert old.keys() == new.keys() and old["at"] == new["at"]
                index = int(old["at"].rsplit("/", 1)[1])
                compare = compare_rows_in_order if "stream" in steps[index] else compare_rows
                compare(new["rows"], old["rows"])
        else:
            assert actual == value, f"{name}: {value!r} -> {actual!r}"


def _compare_graphs(name: str, left: Any, right: Any, kinds: CollectionKinds) -> None:
    if name == "graph":
        compare_graph(right, left, kinds)
        return
    assert len(left) == len(right)
    for old, new in zip(left, right, strict=True):
        assert old.keys() == new.keys()
        assert {key: value for key, value in old.items() if key != "graph"} == {
            key: value for key, value in new.items() if key != "graph"
        }
        compare_graph(new["graph"], old["graph"], kinds)


def _compare_rounds(left: Any, right: Any, case: case_format.Case) -> None:
    assert len(left) == len(right)
    if case.shape == "error":
        # The error grader constrains one victim, not which peer loses a deadlock.
        for actual in (left, right):
            errors = [
                outcome["error"]
                for round_ in actual
                for outcome in round_.values()
                if outcome["error"] is not None
            ]
            then = case_document(case)["then"]
            assert errors == [
                {"category": then["errorClass"], "nativeCode": then["nativeCode"]["postgres"]}
            ]
    for old_round, new_round in zip(left, right, strict=True):
        assert old_round.keys() == new_round.keys()
        for node, old in old_round.items():
            new = new_round[node]
            assert old["waited"] == new["waited"]
            if case.shape != "error":
                assert old["error"] == new["error"] and old["affected"] == new["affected"]
                compare_rows(new["rows"], old["rows"])


def compare_actual(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    assert {key: value for key, value in left.items() if key not in {"actual", "provenance"}} == {
        key: value for key, value in right.items() if key not in {"actual", "provenance"}
    }, "capture identity changed"
    case = case_format.load_case(REPO_ROOT / left["path"])
    old, new = left["actual"], right["actual"]
    if left["shape"] == "uncaught-exception":
        assert left["case"] == "m-storage-layout-024"
        assert {k: v for k, v in old.items() if k != "traceback"} == {
            k: v for k, v in new.items() if k != "traceback"
        }, "uncaught exception changed"
        return (
            []
            if old["traceback"] == new["traceback"]
            else [{"case": left["case"], "old": old["traceback"], "new": new["traceback"]}]
        )
    if left["shape"] == "rounds":
        _compare_rounds(old, new, case)
        return []
    assert old.keys() == new.keys(), "envelope fields changed"
    text_changes: list[dict[str, Any]] = []
    for name, value in old.items():
        actual = new[name]
        if name == "observations":
            compare_observations(value, actual, case)
        elif name == "emissions":
            assert len(value) == len(actual)
            from tests._support.bind_positions import statement_bind_positions

            model = engine.load_case_metamodel(case)
            for prior, current in zip(value, actual, strict=True):
                assert {k: v for k, v in prior.items() if k != "binds"} == {
                    k: v for k, v in current.items() if k != "binds"
                }
                compare_binds(
                    current["binds"],
                    prior["binds"],
                    statement_bind_positions(model, prior["sql"], prior["binds"]),
                )
        elif name == "diagnostics":
            assert len(value) == len(actual)
            for prior, current in zip(value, actual, strict=True):
                assert {k: v for k, v in prior.items() if k != "message"} == {
                    k: v for k, v in current.items() if k != "message"
                }
                if prior.get("message") != current.get("message"):
                    text_changes.append({"case": left["case"], "old": prior, "new": current})
        else:
            assert actual == value, f"{name} changed"
    return text_changes


def _sealed_capture(directory: Path) -> dict[str, Any]:
    seal = json.loads((directory / "seal.json").read_text())
    assert set(seal) == {"metadata.json", "observations.jsonl", "junit.xml"}, (
        "missing sealed evidence"
    )
    assert all(_digest(directory / name) == digest for name, digest in seal.items()), (
        "sealed evidence changed"
    )
    return cast("dict[str, Any]", json.loads((directory / "metadata.json").read_text()))


def _provider_passed(capture: dict[str, Any], verdicts: dict[str, Any]) -> None:
    assert capture["exitstatus"] == 0, "capture pytest did not pass"
    assert capture["requiredProvider"] and capture["provider"].get("passed", 0) > 0, (
        "required provider unavailable"
    )
    mode_skips = int(
        _MODE_SKIP_NODE in capture["selected"]
        and verdicts.get(_junit_node(_MODE_SKIP_NODE))
        == {"verdict": "skipped", "reason": _MODE_SKIP_REASON}
    )
    assert (
        not capture["provider"].get("failed", 0)
        and capture["provider"].get("skipped", 0) == mode_skips
    ), "required provider unavailable"
    assert not any(v["verdict"] in {"failure", "error"} for v in verdicts.values()), (
        "capture JUnit contains failures"
    )


def _diagnostic_node(case: str) -> str:
    return f"tests/compatibility/test_lane_evidence.py::test_document_run_diagnostic[{case}]"


def _junit_node(node: str) -> str:
    module, name = node.split("::", 1)
    return module.removesuffix(".py").replace("/", ".") + "::" + name


def _supplement_baseline(
    baseline: Path,
    supplement: Path,
    old: dict[str, Any],
    left: dict[tuple[Any, ...], dict[str, Any]],
    verdicts: dict[str, Any],
    report: dict[str, Any],
) -> None:
    assert _digest(baseline / "seal.json") == _ORIGINAL_SEAL, "not the authorized failed archive"
    assert old["identity"]["sha"] == _BASELINE_SHA and old["exitstatus"] == 1
    assert old["requiredProvider"] and old["provider"] == {
        "failed": 1,
        "passed": 2475,
        "skipped": 1,
    }
    storage_node = _junit_node(_diagnostic_node("m-storage-layout-024"))
    assert {k for k, v in verdicts.items() if v["verdict"] in {"failure", "error"}} == {
        storage_node
    }
    failure = next(
        t.find("failure")
        for t in ET.parse(baseline / "junit.xml").iter("testcase")
        if t.attrib["classname"] + "::" + t.attrib["name"] == storage_node
    )
    assert failure is not None and failure.get("message") == "AssertionError"
    trace = failure.text or ""
    assert "_node_object_key" in trace and "assert authority is not None" in trace
    assert verdicts[_junit_node(_MODE_SKIP_NODE)] == {
        "verdict": "skipped",
        "reason": _MODE_SKIP_REASON,
    }, "legacy provider skip is not the intentional diagnostic skip"
    extra = _sealed_capture(supplement)
    supplemental_verdicts = junit_verdicts(supplement / "junit.xml")
    _provider_passed(extra, supplemental_verdicts)
    assert extra["identity"]["sha"] == _BASELINE_SHA and "supportHashes" in extra["identity"]
    assert extra["originalSeal"] == _ORIGINAL_SEAL and extra["corpus"] == old["corpus"]
    assert extra["selected"] == sorted(_diagnostic_node(case) for case in DOCUMENT_CASES)
    supplemental = _observations(supplement)
    assert len(supplemental) == 3
    assert set(supplemental_verdicts) == {
        _junit_node(_diagnostic_node(case)) for case in DOCUMENT_CASES
    }
    for key, record in supplemental.items():
        case = record["case"]
        assert (
            case in DOCUMENT_CASES
            and record["lane"] == "run"
            and record["node"] == _diagnostic_node(case)
        )
        verdict = supplemental_verdicts[_junit_node(record["node"])]
        if case == "m-storage-layout-024":
            assert record["shape"] == "uncaught-exception" and record["ordinal"] == 0
            assert (
                record["actual"]["type"] == "builtins.AssertionError"
                and record["actual"]["message"] == ""
            )
            assert record["actual"]["terminal"]["function"] == "_node_object_key"
            assert record["actual"]["terminal"]["path"] == _SCENARIO_PATH
            assert record["actual"]["terminal"]["source"].startswith("assert authority is not None")
            assert verdict == {"verdict": "skipped", "reason": _EXCEPTION_SKIP}
            assert key not in left
            left[key] = record
            report["baselineFailure"] = {
                "node": storage_node,
                "verdict": verdicts[storage_node],
                "traceback": trace,
                "originalSeal": _ORIGINAL_SEAL,
            }
            report["explainedTransitions"].append(
                {
                    "node": storage_node,
                    "old": verdicts[storage_node],
                    "new": verdict,
                    "kind": "diagnostic-only-exception",
                }
            )
            verdicts[storage_node] = verdict
        else:
            assert (
                tracker_provenance(record["actual"])
                == record["provenance"]
                == "tracked-document-milestone-refusal"
            )
            assert (
                verdict
                == verdicts[_junit_node(record["node"])]
                == {"verdict": "passed", "reason": None}
            )
            compare_actual(left[key], record)


def _document_transitions(
    old: dict[str, Any],
    new: dict[str, Any],
    left: dict[tuple[Any, ...], dict[str, Any]],
    right: dict[tuple[Any, ...], dict[str, Any]],
    verdicts: tuple[dict[str, Any], dict[str, Any]],
    report: dict[str, Any],
) -> None:
    old_nodes = {_diagnostic_node(case) for case in DOCUMENT_CASES}
    new_nodes = {_full_grade_node(case) for case in DOCUMENT_CASES}
    assert set(old["selected"]) - set(new["selected"]) == old_nodes
    assert set(new["selected"]) - set(old["selected"]) == new_nodes
    for case in sorted(DOCUMENT_CASES):
        prior = [(key, r) for key, r in left.items() if r["case"] == case and r["lane"] == "run"]
        current = [(key, r) for key, r in right.items() if r["case"] == case and r["lane"] == "run"]
        assert len(prior) == len(current) == 1
        old_key, before = prior[0]
        new_key, after = current[0]
        assert before["node"] == _diagnostic_node(case)
        assert after["node"] == _full_grade_node(case) and after["shape"] == "adapter"
        assert after["actual"]["status"] == "ok" and before["path"] == after["path"]
        assert verdicts[1][_junit_node(after["node"])] == {"verdict": "passed", "reason": None}, (
            "full golden grade required"
        )
        if case == "m-storage-layout-024":
            assert before["shape"] == "uncaught-exception" and "baselineFailure" in report
        else:
            assert (
                before["provenance"]
                == tracker_provenance(before["actual"])
                == "tracked-document-milestone-refusal"
            )
        report["explainedTransitions"].append(
            {"case": case, "old": before, "new": after, "kind": "diagnostic-to-full-golden"}
        )
        del left[old_key], right[new_key]
        del verdicts[0][_junit_node(before["node"])], verdicts[1][_junit_node(after["node"])]


def _full_grade_node(case: str) -> str:
    sweep = (
        "test_write_run_sweep"
        if case == "m-storage-layout-024"
        else "test_run_only_write_sequence_run_sweep"
    )
    return f"tests/compatibility/test_run_sweep.py::{sweep}[{case}]"


def _document_corpus_transition(
    old: Mapping[str, str], new: Mapping[str, str], report: dict[str, Any]
) -> None:
    assert old.keys() == new.keys(), "changed corpus input selection"
    changed = {name for name in old if old[name] != new[name]}
    assert changed == _DOCUMENT_HASHES.keys(), "unauthorized corpus changes"
    for path, (before, after) in _DOCUMENT_HASHES.items():
        assert (old[path], new[path]) == (before, after), "unauthorized document hash pair"
        report["explainedTransitions"].append(
            {"path": path, "old": before, "new": after, "kind": "intentional-corpus-correction"}
        )


def _document_compile_transition(
    left: dict[tuple[Any, ...], dict[str, Any]],
    right: dict[tuple[Any, ...], dict[str, Any]],
    report: dict[str, Any],
) -> None:
    for case in sorted(DOCUMENT_CASES):
        prior = {key: r for key, r in left.items() if r["case"] == case and r["lane"] == "compile"}
        current = {
            key: r for key, r in right.items() if r["case"] == case and r["lane"] == "compile"
        }
        assert len(prior) == 2 and prior.keys() == current.keys(), (
            "missing document compile evidence"
        )
        for key, before in prior.items():
            after = current[key]
            assert before["actual"]["status"] == after["actual"]["status"] == "run-only"
            if case == "m-storage-layout-024":
                assert before["actual"]["caseShape"] == "writeSequence"
                assert after["actual"]["caseShape"] == "scenario"
                normalized = {**after, "actual": {**after["actual"], "caseShape": "writeSequence"}}
                assert before == normalized, "document compile envelope changed beyond case shape"
                report["explainedTransitions"].append(
                    {"case": case, "old": before, "new": after, "kind": "authored-case-shape"}
                )
            else:
                assert before == after, "document compile envelope changed"
            del left[key], right[key]


def compare_reports(
    baseline: Path,
    candidate: Path,
    root: Path = REPO_ROOT,
    *,
    supplement: Path | None = None,
    newly_graded_document_cases: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "classification": "unexplained",
        "differences": [],
        "diagnosticTextChanges": [],
        "explainedTransitions": [],
    }
    try:
        old, new = _sealed_capture(baseline), _sealed_capture(candidate)
        assert old["format"] == new["format"] == 1, "capture format changed"
        assert "supportHashes" in old["identity"], "baseline has no exact-SHA guard evidence"
        assert new["corpus"] == corpus_manifest(root), "candidate differs from current corpus"
        if newly_graded_document_cases:
            _document_corpus_transition(old["corpus"], new["corpus"], report)
        else:
            assert old["corpus"] == new["corpus"], "changed corpus inputs"
        verdicts = (junit_verdicts(baseline / "junit.xml"), junit_verdicts(candidate / "junit.xml"))
        _provider_passed(new, verdicts[1])
        left, right = _observations(baseline), _observations(candidate)
        if supplement is None:
            _provider_passed(old, verdicts[0])
        else:
            _supplement_baseline(baseline, supplement, old, left, verdicts[0], report)
        if newly_graded_document_cases:
            _document_transitions(old, new, left, right, verdicts, report)
            _document_compile_transition(left, right, report)
        else:
            assert old["selected"] == new["selected"], "unexpected test selection change"
        assert verdicts[0] == verdicts[1], "JUnit verdict or skip partition changed"
        assert left.keys() == right.keys(), (
            "missing observations or unexpected observation selection"
        )
        for key, record in left.items():
            try:
                report["diagnosticTextChanges"].extend(compare_actual(record, right[key]))
            except (AssertionError, KeyError, ValueError) as exc:
                report["differences"].append({"key": key, "reason": str(exc)})
        report["observations"] = len(left)
        report["nodes"] = len(verdicts[0])
    except (OSError, AssertionError, KeyError, ValueError, ET.ParseError) as exc:
        report["differences"].append({"reason": str(exc)})
    if not report["differences"]:
        report["classification"] = (
            "explained-corpus-operation-coverage-outcome-transition"
            if newly_graded_document_cases
            else "equivalent-with-diagnostic-baseline-failure"
            if supplement
            else "equivalent"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("compare",))
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--supplement", type=Path)
    parser.add_argument("--newly-graded-document-cases", action="store_true")
    arguments = parser.parse_args()
    report = compare_reports(
        arguments.baseline,
        arguments.candidate,
        supplement=arguments.supplement,
        newly_graded_document_cases=arguments.newly_graded_document_cases,
    )
    destination = arguments.candidate / "delta.json"
    _write_json(destination, report)
    print(
        f"{report['classification']}: {len(report['differences'])} unexplained differences; "
        f"{destination}"
    )
    return int(bool(report["differences"]))


if __name__ == "__main__":
    raise SystemExit(main())
