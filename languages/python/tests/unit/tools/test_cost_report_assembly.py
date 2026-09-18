from __future__ import annotations

import contextlib
import json
from collections.abc import Generator, Sequence
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import cost_report
from cost_report import (
    BASE,
    CAPTURE_FILE,
    DURATIONS_FILE,
    HEAD,
    MEMBERS,
    REQUEST_FILE,
    SHARDS,
    UNAVAILABLE_FILE,
    Assembly,
    History,
    MemberResult,
    Request,
    Shard,
    ShardResult,
    assemble,
    discover,
    local_request,
    write_assembly,
    write_shard,
)
from durations import Spans
from interpreter_matrix import (
    RuntimeIdentity,
    RuntimeStatus,
    RuntimeUnavailable,
    supported_minors,
    write_metadata,
)
from parallax.conformance.budget import BudgetContract
from snapshot_delivery_overhead import PLAN_GROUP, workload_selection
from tests.unit.tools._cost_report_support import clean, complete_snapshot, member_envelopes

type Document = dict[str, Any]

SNAPSHOT = next(shard for shard in SHARDS if shard.subject == "snapshot-delivery")
WRITE = next(shard for shard in SHARDS if shard.subject == "write-lowering")
LIFECYCLE = next(shard for shard in SHARDS if shard.subject == "lifecycle-overhead")


@pytest.fixture(scope="module")
def contract() -> BudgetContract:
    return BudgetContract.load()


@pytest.fixture(scope="module")
def head_commit() -> str:
    return cost_report.git_head()


@pytest.fixture(scope="module")
def envelopes(contract: BudgetContract) -> dict[str, Document]:
    return {
        subject: clean(document, contract)
        for subject, document in member_envelopes(contract).items()
    }


def _identities(**versions: str) -> dict[str, RuntimeStatus]:
    return {
        minor: RuntimeIdentity("CPython", versions.get(minor.replace(".", "_"), f"{minor}.1"), "/p")
        for minor in supported_minors()
    }


def _pr_request(head: str, *, request_id: str = "req-1", attempt: int = 1) -> Request:
    return Request.from_document(
        {
            **local_request("sharded", head).document(),
            "requestId": request_id,
            "event": "pull_request",
            "pullRequest": 7,
            "eventBaseCommit": head,
            "runId": "100",
            "runAttempt": attempt,
        }
    )


def _nightly_request(head: str, *, request_id: str) -> Request:
    return Request.from_document(
        {
            **local_request("sharded").document(),
            "requestId": request_id,
            "event": "schedule",
            "runId": request_id,
            "runAttempt": 1,
        }
    )


def _spans(shard_id: str, seconds: float) -> Spans:
    elapsed = [0.0]
    wall = datetime(2026, 9, 18, 6, 0, tzinfo=UTC)
    spans = Spans(clock=lambda: elapsed[0], now=lambda: wall + timedelta(seconds=elapsed[0]))
    with (
        spans.span("collection", shard_id, shard=shard_id),
        spans.span("member", "member", member="member"),
    ):
        elapsed[0] += seconds
    return spans


def _write(
    root: Path,
    artifact: str,
    shard: Shard,
    side: str,
    request: Request,
    envelope: Document | None,
    *,
    commit: str | None = None,
    pair: str = "pair",
    runtimes: dict[str, RuntimeStatus] | None = None,
    seconds: float = 10.0,
) -> Path:
    measured = commit or (request.head_commit if side == HEAD else request.base_commit)
    assert measured is not None
    result = ShardResult(
        shard,
        MemberResult(shard.member, envelope, None if envelope is not None else "exit 1: gone"),
        _spans(shard.id, seconds),
        runtimes if runtimes is not None else _identities(),
    )
    out = root / artifact / side / shard.id
    write_shard(result, request, side, measured, pair, out)
    return out


def _complete_pr(root: Path, request: Request, envelopes: dict[str, Document]) -> None:
    for index, shard in enumerate(SHARDS):
        for side in (BASE, HEAD):
            _write(
                root,
                f"artifact-{shard.id}",
                shard,
                side,
                request,
                envelopes[shard.subject],
                pair=f"pair-{shard.id}",
                seconds=10.0 * (index + 1),
            )


def _entry(assembly: Assembly, shard: Shard) -> cost_report.ShardAssembly:
    return next(entry for entry in assembly.shards if entry.shard is shard)


def _codes(entry: cost_report.ShardAssembly) -> list[tuple[str, str | None]]:
    return [(reason.code, reason.side) for reason in entry.reasons]


def _rows(entry: cost_report.ShardAssembly, marker: str) -> list[str]:
    return [line for line in entry.comparison if marker in line]


# --------------------------------------------------------------------------- #
# A complete same-runner pull-request assembly                                #
# --------------------------------------------------------------------------- #
def test_a_complete_pull_request_assembly_pairs_every_shard_on_its_own_runner(
    tmp_path: Path,
    head_commit: str,
    envelopes: dict[str, Document],
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _pr_request(head_commit)
    root = tmp_path / "inputs"
    _complete_pr(root, request, envelopes)
    request.write(root / REQUEST_FILE)
    captures = discover(root)
    assert [capture.source for capture in captures] == sorted(
        f"artifact-{shard.id}/{side}/{shard.id}" for shard in SHARDS for side in (BASE, HEAD)
    )
    assembly = assemble(captures, SHARDS, request)
    assert assembly.failures == ()
    assert [entry.shard.id for entry in assembly.shards] == [shard.id for shard in SHARDS]
    for entry in assembly.shards:
        assert entry.pairing == "same-runner"
        assert entry.reasons == ()
        assert entry.head is not None and entry.base is not None
        assert entry.sources == (
            f"artifact-{entry.shard.id}/base/{entry.shard.id}",
            f"artifact-{entry.shard.id}/head/{entry.shard.id}",
        )
        assert entry.comparison[:2] == cost_report.COMPARISON_HEADER
        assert not _rows(entry, "unavailable") and not _rows(entry, "missing on")
    write_rows = _rows(_entry(assembly, WRITE), "| within noise |") + _rows(
        _entry(assembly, WRITE), "| exact |"
    )
    assert len(write_rows) == len(envelopes[WRITE.subject]["readings"])
    document = assembly.document()
    assert document["schemaVersion"] == 2
    assert document["request"] == request.document()
    assert document["plan"] == [shard.document() for shard in SHARDS]
    first = cast("dict[str, Any]", cast("list[Any]", document["shards"])[0])
    assert set(first) == {"id", "base", "head", "pairing", "reasons", "sources"}
    assert first["head"]["capture"]["side"] == HEAD and first["base"]["capture"]["side"] == BASE
    assert first["head"]["portfolio"]["members"] == [envelopes[SNAPSHOT.subject]]
    labelled = {
        (span.labels["shard"], span.labels["side"])
        for span in assembly.durations.spans
        if span.scope == "collection"
    }
    assert labelled == {(shard.id, side) for shard in SHARDS for side in (BASE, HEAD)}
    assert assembly.durations.unavailable == ()
    summary = assembly.summary()
    assert f"Critical path: 80.000 s on shard `{SHARDS[-1].id}`" in summary
    assert "| Shard | Subject | Workloads | Head | Base | Pairing | Reasons |" in summary
    assert f"Planned {len(SHARDS)} shard(s); {len(SHARDS)} with a valid head capture" in summary
    assert "same-runner" in summary and "cross-runner" not in summary
    assert "workload digest" in summary and "lock digest" in summary
    out = tmp_path / "assembled"
    assert cost_report.main(["--assemble", str(root), "--out", str(out)]) == 0
    assert capsys.readouterr().out == summary
    _assert_round_trip(assembly, root, captures, out)


def _assert_round_trip(
    assembly: Assembly, root: Path, captures: list[cost_report.ShardCapture], out: Path
) -> None:
    assert sorted(path.name for path in out.iterdir()) == [
        DURATIONS_FILE,
        "portfolio.json",
        "raw",
        "summary.md",
    ]
    reloaded = json.loads((out / "portfolio.json").read_text(encoding="utf-8"))
    assert reloaded == json.loads(json.dumps(assembly.document()))
    assert (out / "summary.md").read_text(encoding="utf-8") == assembly.summary()
    merged = Spans.load(out / DURATIONS_FILE)
    assert [span.document() for span in merged.spans] == [
        span.document() for span in assembly.durations.spans
    ]
    for capture in captures:
        raw = out / "raw" / capture.source
        original = root / capture.source
        assert sorted(p.name for p in raw.iterdir()) == sorted(p.name for p in original.iterdir())
        for path in original.iterdir():
            assert (raw / path.name).read_bytes() == path.read_bytes()


# --------------------------------------------------------------------------- #
# Missing, duplicate, unexpected, and malformed inputs                        #
# --------------------------------------------------------------------------- #
def test_zero_arriving_captures_assemble_into_an_honest_all_missing_result(
    tmp_path: Path, head_commit: str, capsys: pytest.CaptureFixture[str]
) -> None:
    request = _pr_request(head_commit)
    assembly = assemble([], SHARDS, request)
    assert assembly.failures == ()
    for entry in assembly.shards:
        assert _codes(entry) == [("head-missing", HEAD), ("base-missing", BASE)]
        assert entry.pairing == "unavailable" and entry.head is None and entry.base is None
        assert entry.comparison == ("No head envelope is available; nothing was compared.",)
    assert "Critical path: unavailable" in assembly.summary()
    request_path = tmp_path / REQUEST_FILE
    request.write(request_path)
    out = tmp_path / "assembled"
    assert (
        cost_report.main(
            [
                "--assemble",
                str(tmp_path / "never-downloaded"),
                "--request",
                str(request_path),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    capsys.readouterr()
    reloaded = json.loads((out / "portfolio.json").read_text(encoding="utf-8"))
    assert [entry["id"] for entry in reloaded["shards"]] == [shard.id for shard in SHARDS]
    assert all(entry["head"] is None for entry in reloaded["shards"])
    assert not (out / "raw").exists()


def test_duplicate_unexpected_and_malformed_inputs_are_failures_that_lose_nothing(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _pr_request(head_commit)
    root = tmp_path / "inputs"
    _write(root, "first", LIFECYCLE, HEAD, request, envelopes[LIFECYCLE.subject])
    _write(root, "second", LIFECYCLE, HEAD, request, envelopes[LIFECYCLE.subject])
    _write(root, "first", LIFECYCLE, BASE, request, envelopes[LIFECYCLE.subject])
    rogue = Shard("rogue", MEMBERS[2])
    _write(root, "first", rogue, HEAD, request, envelopes[rogue.subject])
    broken = _write(root, "first", WRITE, HEAD, request, envelopes[WRITE.subject])
    (broken / CAPTURE_FILE).write_text("{", encoding="utf-8")
    stranger = _write(
        root,
        "first",
        SNAPSHOT,
        HEAD,
        _pr_request(head_commit, request_id="other"),
        envelopes[SNAPSHOT.subject],
    )
    captures = discover(root)
    assembly = assemble(captures, SHARDS, request)
    assert sorted((f.code, f.shard, f.side, f.source) for f in assembly.failures) == sorted(
        [
            ("duplicate-capture", LIFECYCLE.id, HEAD, f"first/head/{LIFECYCLE.id}"),
            ("duplicate-capture", LIFECYCLE.id, HEAD, f"second/head/{LIFECYCLE.id}"),
            ("unexpected-shard", "rogue", HEAD, "first/head/rogue"),
            ("input-malformed", None, None, f"first/head/{WRITE.id}"),
            ("request-mismatch", SNAPSHOT.id, HEAD, f"first/head/{SNAPSHOT.id}"),
        ]
    )
    lifecycle = _entry(assembly, LIFECYCLE)
    assert _codes(lifecycle) == [("head-duplicate", HEAD)]
    assert lifecycle.head is None and lifecycle.base is not None
    assert lifecycle.pairing == "unavailable"
    assert sorted(lifecycle.sources) == sorted(
        [f"first/base/{LIFECYCLE.id}", f"first/head/{LIFECYCLE.id}", f"second/head/{LIFECYCLE.id}"]
    )
    assert _codes(_entry(assembly, WRITE)) == [("head-missing", HEAD), ("base-missing", BASE)]
    assert _codes(_entry(assembly, SNAPSHOT)) == [("head-missing", HEAD), ("base-missing", BASE)]
    out = tmp_path / "assembled"
    write_assembly(assembly, root, captures, out)
    assert (out / "raw" / "first" / "head" / "rogue" / CAPTURE_FILE).exists()
    assert (out / "raw" / "second" / "head" / LIFECYCLE.id / CAPTURE_FILE).exists()
    assert (out / "raw" / "first" / "head" / WRITE.id / CAPTURE_FILE).read_text("utf-8") == "{"
    assert (out / "raw" / stranger.relative_to(root) / CAPTURE_FILE).exists()
    assert "## Collection failures" in assembly.summary()


def test_a_corrupt_durations_sidecar_leaves_the_evidence_compared_and_the_timing_unavailable(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _pr_request(head_commit)
    root = tmp_path / "inputs"
    head = _write(root, "a", LIFECYCLE, HEAD, request, envelopes[LIFECYCLE.subject])
    base = _write(root, "a", LIFECYCLE, BASE, request, envelopes[LIFECYCLE.subject])
    (head / DURATIONS_FILE).write_text("[]", encoding="utf-8")
    (base / DURATIONS_FILE).unlink()
    assembly = assemble(discover(root), SHARDS, request)
    entry = _entry(assembly, LIFECYCLE)
    assert entry.reasons == () and entry.pairing == "same-runner"
    assert _rows(entry, "| within noise |")
    assert [(item.name, item.reason) for item in assembly.durations.unavailable] == [
        (f"{LIFECYCLE.id}/base", "no durations sidecar arrived"),
        (
            f"{LIFECYCLE.id}/head",
            f"the durations sidecar does not decode: {head / DURATIONS_FILE} does not hold a "
            "durations document",
        ),
    ]
    assert assembly.durations.spans == ()
    assert "Durations unavailable:" in assembly.summary()


# --------------------------------------------------------------------------- #
# Invalid sides                                                               #
# --------------------------------------------------------------------------- #
def test_invalid_provenance_a_diagnostic_and_a_missing_envelope_are_collection_failures(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _pr_request(head_commit)
    root = tmp_path / "inputs"
    dirty = deepcopy(envelopes[WRITE.subject])
    dirty["provenance"]["dirty"] = True
    dirty["authority"] = "non-authoritative"
    _write(root, "a", WRITE, HEAD, request, dirty)
    _write(root, "a", WRITE, BASE, request, envelopes[WRITE.subject])
    _write(root, "a", LIFECYCLE, HEAD, request, envelopes[LIFECYCLE.subject], commit="e" * 40)
    _write(root, "a", LIFECYCLE, BASE, request, envelopes[LIFECYCLE.subject])
    diagnostic: Document = {"diagnostic": True, "subject": SNAPSHOT.subject, "readings": []}
    _write(root, "a", SNAPSHOT, HEAD, request, diagnostic)
    _write(root, "a", SNAPSHOT, BASE, request, None)
    assembly = assemble(discover(root), SHARDS, request)
    write = _entry(assembly, WRITE)
    assert _codes(write) == [("provenance-dirty", HEAD)]
    assert write.head is None and write.base is not None and write.pairing == "unavailable"
    assert write.comparison == ("No head envelope is available; nothing was compared.",)
    lifecycle = _entry(assembly, LIFECYCLE)
    assert _codes(lifecycle) == [("commit-mismatch", HEAD), ("provenance-commit-mismatch", HEAD)]
    assert f"measured {'e' * 40}, expected {head_commit}" in lifecycle.reasons[0].message
    assert f"produced at {head_commit}, the capture says {'e' * 40}" in lifecycle.reasons[1].message
    snapshot = _entry(assembly, SNAPSHOT)
    assert _codes(snapshot) == [("diagnostic", HEAD), ("envelope-missing", BASE)]
    assert "exit 1: gone" in snapshot.reasons[1].message
    assert sorted((f.code, f.shard, f.side) for f in assembly.failures) == sorted(
        [
            ("provenance-dirty", WRITE.id, HEAD),
            ("commit-mismatch", LIFECYCLE.id, HEAD),
            ("provenance-commit-mismatch", LIFECYCLE.id, HEAD),
            ("diagnostic", SNAPSHOT.id, HEAD),
            ("envelope-missing", SNAPSHOT.id, BASE),
        ]
    )


def test_each_side_is_validated_against_its_own_recorded_selection(
    tmp_path: Path, head_commit: str, contract: BudgetContract, envelopes: dict[str, Document]
) -> None:
    request = _pr_request(head_commit)
    root = tmp_path / "inputs"
    plan_only = Shard(SNAPSHOT.id, SNAPSHOT.member, frozenset({PLAN_GROUP}))
    sliced = clean(
        complete_snapshot(contract, workload_selection([PLAN_GROUP], contract)), contract
    )
    _write(root, "a", plan_only, BASE, request, sliced)
    claimed = _write(root, "a", plan_only, HEAD, request, envelopes[SNAPSHOT.subject])
    assembly = assemble(discover(root), SHARDS, request)
    entry = _entry(assembly, SNAPSHOT)
    assert _codes(entry) == [("envelope-invalid", HEAD)]
    assert "Snapshot reading matrix is not exact: unexpected" in entry.reasons[0].message
    assert entry.base is not None
    for path in claimed.iterdir():
        path.unlink()
    claimed.rmdir()
    _write(root, "b", SNAPSHOT, HEAD, request, envelopes[SNAPSHOT.subject])
    assembly = assemble(discover(root), SHARDS, request)
    entry = _entry(assembly, SNAPSHOT)
    assert _codes(entry) == [("selection-mismatch", BASE)]
    assert entry.pairing == "same-runner" and entry.base is not None
    assert len(_rows(entry, "unavailable: incompatible (selection-mismatch")) == len(
        envelopes[SNAPSHOT.subject]["readings"]
    )
    assert assembly.failures == ()


# --------------------------------------------------------------------------- #
# Incompatible and unpaired sides                                             #
# --------------------------------------------------------------------------- #
def test_only_cells_on_runtimes_with_the_same_full_interpreter_are_compared(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _pr_request(head_commit)
    root = tmp_path / "inputs"
    older, newer = supported_minors()
    _write(
        root,
        "a",
        WRITE,
        HEAD,
        request,
        envelopes[WRITE.subject],
        runtimes=_identities(**{older.replace(".", "_"): f"{older}.99"}),
    )
    _write(root, "a", WRITE, BASE, request, envelopes[WRITE.subject])
    unknown = _identities()
    unknown[newer] = RuntimeUnavailable("the identity probe printed nothing")
    _write(root, "a", SNAPSHOT, HEAD, request, envelopes[SNAPSHOT.subject], runtimes=unknown)
    _write(root, "a", SNAPSHOT, BASE, request, envelopes[SNAPSHOT.subject])
    assembly = assemble(discover(root), SHARDS, request)
    write = _entry(assembly, WRITE)
    assert _codes(write) == [("runtime-mismatch", BASE)]
    assert write.pairing == "same-runner"
    write_readings = envelopes[WRITE.subject]["readings"]
    per_runtime = {
        minor: sum(1 for r in write_readings if r["runtime"] == minor) for minor in (older, newer)
    }
    assert len(_rows(write, f"| {older} |")) == per_runtime[older]
    assert all(
        f"unavailable: runtime-mismatch: CPython {older} is CPython {older}.1 on base and "
        f"CPython {older}.99 on head" in row
        for row in _rows(write, f"| {older} |")
    )
    assert len(_rows(write, f"| {newer} |")) == per_runtime[newer]
    assert all(
        row.endswith(("| within noise |", "| exact |")) for row in _rows(write, f"| {newer} |")
    )
    snapshot = _entry(assembly, SNAPSHOT)
    assert _codes(snapshot) == [("runtime-unavailable", BASE)]
    assert all(
        f"unavailable: runtime-unavailable: CPython {newer} identity is unknown on head "
        "(the identity probe printed nothing)" in row
        for row in _rows(snapshot, f"| {newer} |")
    )
    assert _rows(snapshot, f"| {older} |") and not _rows(snapshot, f"| {older} |")[0].endswith(
        "|  |"
    )
    assert assembly.failures == ()


def test_a_changed_workload_or_protocol_makes_the_whole_shard_incomparable(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _pr_request(head_commit)
    root = tmp_path / "inputs"
    other_workloads = deepcopy(envelopes[LIFECYCLE.subject])
    other_workloads["provenance"]["workloadDigest"] = "0" * 64
    _write(root, "a", LIFECYCLE, BASE, request, other_workloads)
    _write(root, "a", LIFECYCLE, HEAD, request, envelopes[LIFECYCLE.subject])
    other_protocol = deepcopy(envelopes[WRITE.subject])
    other_protocol["provenance"]["sampling"] = {
        **other_protocol["provenance"]["sampling"],
        "measured": 5,
    }
    _write(root, "a", WRITE, BASE, request, other_protocol)
    _write(root, "a", WRITE, HEAD, request, envelopes[WRITE.subject])
    assembly = assemble(discover(root), SHARDS, request)
    lifecycle = _entry(assembly, LIFECYCLE)
    assert _codes(lifecycle) == [("workload-digest-mismatch", BASE)]
    assert len(_rows(lifecycle, "unavailable: incompatible (workload-digest-mismatch")) == len(
        envelopes[LIFECYCLE.subject]["readings"]
    )
    write = _entry(assembly, WRITE)
    assert _codes(write) == [("sampling-mismatch", BASE)]
    assert not _rows(write, "within noise")
    assert assembly.failures == ()


def test_a_base_from_another_invocation_is_never_paired_with_the_head(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _pr_request(head_commit)
    root = tmp_path / "inputs"
    _write(root, "a", LIFECYCLE, HEAD, request, envelopes[LIFECYCLE.subject], pair="attempt-2")
    _write(root, "a", LIFECYCLE, BASE, request, envelopes[LIFECYCLE.subject], pair="attempt-1")
    assembly = assemble(discover(root), SHARDS, request)
    entry = _entry(assembly, LIFECYCLE)
    assert _codes(entry) == [("pair-mismatch", BASE)]
    assert entry.pairing == "unavailable"
    assert entry.base is not None and entry.head is not None
    assert len(_rows(entry, "unavailable: base unavailable (pair-mismatch")) == len(
        envelopes[LIFECYCLE.subject]["readings"]
    )
    assert assembly.failures == ()


def test_every_head_cell_is_named_when_the_base_is_unavailable_by_marker(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _pr_request(head_commit)
    root = tmp_path / "inputs"
    _write(root, "a", WRITE, HEAD, request, envelopes[WRITE.subject])
    marker = root / "a" / BASE / WRITE.id / UNAVAILABLE_FILE
    marker.parent.mkdir(parents=True)
    marker.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "shard": WRITE.id,
                "side": BASE,
                "baseCommit": head_commit,
                "reason": {"code": "missing-base-support", "message": "the base's plan lacks it"},
            }
        ),
        encoding="utf-8",
    )
    _write(root, "a", LIFECYCLE, HEAD, request, envelopes[LIFECYCLE.subject])
    assembly = assemble(discover(root), SHARDS, request)
    write = _entry(assembly, WRITE)
    assert _codes(write) == [("missing-base-support", BASE)]
    assert write.base is None and write.head is not None
    rows = _rows(
        write, "unavailable: base unavailable (missing-base-support: the base's plan lacks it)"
    )
    assert len(rows) == len(envelopes[WRITE.subject]["readings"])
    assert write.sources == (f"a/base/{WRITE.id}", f"a/head/{WRITE.id}")
    lifecycle = _entry(assembly, LIFECYCLE)
    assert _codes(lifecycle) == [("base-missing", BASE)]
    assert len(_rows(lifecycle, "unavailable: base unavailable (base-missing")) == len(
        envelopes[LIFECYCLE.subject]["readings"]
    )
    assert assembly.failures == ()
    (marker.parent / "portfolio.json").write_text("{}", encoding="utf-8")
    marker.write_text('{"schemaVersion": 1}', encoding="utf-8")
    assembly = assemble(discover(root), SHARDS, request)
    assert [(f.code, f.source) for f in assembly.failures] == [
        ("input-malformed", f"a/base/{WRITE.id}")
    ]
    assert _codes(_entry(assembly, WRITE)) == [("base-missing", BASE)]


# --------------------------------------------------------------------------- #
# Nightlies: the previous assembly's head, cross-runner                        #
# --------------------------------------------------------------------------- #
def _nightly(
    root: Path, request: Request, envelopes: dict[str, Document]
) -> list[cost_report.ShardCapture]:
    for shard in SHARDS:
        _write(
            root,
            "night",
            shard,
            HEAD,
            request,
            envelopes[shard.subject],
            pair=f"{request.request_id}-{shard.id}",
        )
    request.write(root / REQUEST_FILE)
    return discover(root)


def test_a_nightly_pairs_each_head_with_the_previous_nightlys_head_cross_runner(
    tmp_path: Path,
    head_commit: str,
    envelopes: dict[str, Document],
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = _nightly_request(head_commit, request_id="night-1")
    first_root = tmp_path / "first"
    first_assembly = assemble(_nightly(first_root, first, envelopes), SHARDS, first)
    assert all(_codes(entry) == [("base-not-requested", BASE)] for entry in first_assembly.shards)
    previous = tmp_path / "previous"
    write_assembly(first_assembly, first_root, discover(first_root), previous)
    second = _nightly_request(head_commit, request_id="night-2")
    second_root = tmp_path / "second"
    captures = _nightly(second_root, second, envelopes)
    assembly = assemble(captures, SHARDS, second, History.load(previous))
    assert assembly.failures == ()
    for entry in assembly.shards:
        assert entry.reasons == ()
        assert entry.pairing == "cross-runner"
        assert entry.base is not None and entry.base.source == f"against/{entry.shard.id}"
        assert entry.base.capture is not None
        assert entry.base.capture.request.request_id == "night-1"
        assert entry.comparison[0].startswith("Cross-runner comparison:")
        assert "calibrated on same-runner pairs" in entry.comparison[0]
        if envelopes[entry.shard.subject]["readings"]:
            assert _rows(entry, "| within noise |") or _rows(entry, "| exact |")
    assert "cross-runner" in assembly.summary()
    document = assembly.document()
    assert (
        cast("list[Any]", document["shards"])[0]["base"]["capture"]["request"]["requestId"]
        == "night-1"
    )
    labelled = {
        (span.labels["shard"], span.labels["side"], span.labels["request"])
        for span in assembly.durations.spans
        if span.scope == "collection"
    }
    assert labelled == {(shard.id, HEAD, "night-2") for shard in SHARDS}
    assert [item.name for item in assembly.durations.unavailable] == [
        f"{shard.id}/head" for shard in SHARDS
    ]
    out = tmp_path / "assembled"
    assert (
        cost_report.main(
            ["--assemble", str(second_root), "--against", str(previous), "--out", str(out)]
        )
        == 0
    )
    capsys.readouterr()
    assert json.loads((out / "portfolio.json").read_text("utf-8")) == json.loads(
        json.dumps(document)
    )


def test_missing_or_unsupported_history_is_unavailable_and_never_a_failure(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _nightly_request(head_commit, request_id="night-2")
    root = tmp_path / "inputs"
    captures = _nightly(root, request, envelopes)
    absent = assemble(captures, SHARDS, request, History.load(tmp_path / "expired"))
    assert absent.failures == ()
    assert all(_codes(entry) == [("history-unavailable", BASE)] for entry in absent.shards)
    assert "no previous assembly" in absent.shards[0].reasons[0].message
    assert "Previous nightly: unavailable" in absent.summary()
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "portfolio.json").write_text('{"schemaVersion": 1, "members": []}', encoding="utf-8")
    unsupported = assemble(captures, SHARDS, request, History.load(legacy))
    assert "schemaVersion 1" in unsupported.shards[0].reasons[0].message
    (legacy / "portfolio.json").write_text("[", encoding="utf-8")
    assert History.load(legacy).reason is not None
    (legacy / "portfolio.json").write_text("[]", encoding="utf-8")
    assert History.load(legacy).reason == "the previous assembly is not an object"
    previous = tmp_path / "previous"
    first = _nightly_request(head_commit, request_id="night-1")
    first_root = tmp_path / "first"
    first_assembly = assemble(_nightly(first_root, first, envelopes), SHARDS, first)
    write_assembly(first_assembly, first_root, discover(first_root), previous)
    document = json.loads((previous / "portfolio.json").read_text("utf-8"))
    document["shards"] = [
        {**entry, "head": {"portfolio": {}, "capture": {}}} if entry["id"] == WRITE.id else entry
        for entry in document["shards"]
        if entry["id"] != LIFECYCLE.id
    ]
    (previous / "portfolio.json").write_text(json.dumps(document), encoding="utf-8")
    renamed = assemble(captures, SHARDS, request, History.load(previous))
    assert _codes(_entry(renamed, LIFECYCLE)) == [("history-missing-shard", BASE)]
    assert _codes(_entry(renamed, WRITE)) == [("history-invalid", BASE)]
    assert _codes(_entry(renamed, SNAPSHOT)) == []
    assert _entry(renamed, SNAPSHOT).pairing == "cross-runner"
    assert renamed.failures == ()


def test_history_is_refused_for_a_pull_request_and_a_stray_base_is_a_failure(
    tmp_path: Path,
    head_commit: str,
    envelopes: dict[str, Document],
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _pr_request(head_commit)
    root = tmp_path / "inputs"
    request.write(root / REQUEST_FILE)
    with pytest.raises(SystemExit) as error:
        cost_report.main(
            ["--assemble", str(root), "--against", str(tmp_path), "--out", str(tmp_path / "out")]
        )
    assert error.value.code == 2
    assert "never a pull request" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
    nightly = _nightly_request(head_commit, request_id="night-3")
    captures = _nightly(root, nightly, envelopes)
    _write(
        root, "stray", LIFECYCLE, BASE, nightly, envelopes[LIFECYCLE.subject], commit=head_commit
    )
    assembly = assemble(discover(root), SHARDS, nightly)
    assert [(f.code, f.shard, f.source) for f in assembly.failures] == [
        ("unexpected-base", LIFECYCLE.id, f"stray/base/{LIFECYCLE.id}")
    ]
    assert _codes(_entry(assembly, LIFECYCLE)) == [("base-not-requested", BASE)]
    del captures
    missing = tmp_path / "no-request"
    missing.mkdir()
    with pytest.raises(SystemExit) as error:
        cost_report.main(["--assemble", str(missing), "--out", str(tmp_path / "out")])
    assert error.value.code == 2
    assert "does not hold the request" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# From a shard run to its assembly                                            #
# --------------------------------------------------------------------------- #
def test_a_shard_run_with_a_self_measured_base_assembles_into_same_runner_pairs(
    tmp_path: Path,
    head_commit: str,
    envelopes: dict[str, Document],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _pr_request(head_commit)

    def member(shard_member: cost_report.Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        metadata = Path(arguments[arguments.index(cost_report.METADATA_OPTION) + 1])
        write_metadata(metadata, shard_member.subject, _identities())
        return (0, json.dumps(envelopes[shard_member.subject]), "")

    def base_tool(workspace: Path, arguments: Sequence[str]) -> tuple[int, str, str]:
        del workspace
        if arguments[0] == "--plan":
            return (0, json.dumps([shard.id for shard in SHARDS]), "")
        shard = next(shard for shard in SHARDS if shard.id == arguments[1])
        staging = Path(arguments[3])
        base_local = local_request("sharded")
        result = ShardResult(
            shard,
            MemberResult(shard.member, envelopes[shard.subject]),
            _spans(shard.id, 5.0),
            _identities(),
        )
        write_shard(
            result, base_local, HEAD, head_commit, "the-base-own-pair", staging / HEAD / shard.id
        )
        return (0, "", "")

    @contextlib.contextmanager
    def checkout(commit: str) -> Generator[Path]:
        assert commit == head_commit
        yield tmp_path / "checkout"

    monkeypatch.setattr(cost_report, "base_worktree", checkout)
    out = tmp_path / "reports"
    assert (
        cost_report.run_shards([shard.id for shard in SHARDS], request, out, member, base_tool) == 0
    )
    captures = discover(out)
    assert [capture.source for capture in captures] == sorted(
        f"{side}/{shard.id}" for shard in SHARDS for side in (BASE, HEAD)
    )
    assembly = assemble(captures, SHARDS, Request.load(out / REQUEST_FILE))
    assert assembly.failures == ()
    for entry in assembly.shards:
        assert entry.reasons == ()
        assert entry.pairing == "same-runner"
        assert entry.base is not None and entry.base.capture is not None
        assert entry.head is not None and entry.head.capture is not None
        assert entry.base.capture.pair_id == entry.head.capture.pair_id
        assert entry.base.capture.pair_id != "the-base-own-pair"
        assert entry.base.capture.request == request
        assert (out / BASE / entry.shard.id / "self-capture.json").exists()
    assert {
        (span.labels["shard"], span.labels["side"])
        for span in assembly.durations.spans
        if span.scope == "collection"
    } == {(shard.id, side) for shard in SHARDS for side in (BASE, HEAD)}
