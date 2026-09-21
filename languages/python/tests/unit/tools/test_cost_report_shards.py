from __future__ import annotations

import contextlib
import json
import subprocess
from collections.abc import Callable, Generator, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

import cost_report
from cost_report import (
    ALL_SHARDS,
    BASE,
    CAPTURE_FILE,
    DURATIONS_FILE,
    HEAD,
    MEMBERS,
    REQUEST_FILE,
    SELF_CAPTURE_FILE,
    SHARDS,
    UNAVAILABLE_FILE,
    BaseResult,
    Capture,
    Member,
    MemberResult,
    Request,
    Shard,
    ShardResult,
    collect_shard,
    local_request,
    measure_base,
    plan_ids,
    run_shards,
    shard_arguments,
    validate_plan,
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
from snapshot_delivery_overhead import (
    CONTROL_GROUP,
    GEOMETRY_GROUP,
    PLAN_GROUP,
    selected_addresses,
    workload_names,
    workload_selection,
)
from tests.unit.tools._cost_report_support import complete_snapshot, member_envelopes

SNAPSHOT = next(member for member in MEMBERS if member.subject == "snapshot-delivery")
OTHERS = tuple(member for member in MEMBERS if member is not SNAPSHOT)
SNAPSHOT_SHARDS = tuple(shard for shard in SHARDS if shard.member is SNAPSHOT)
OTHER_SHARDS = tuple(shard for shard in SHARDS if shard.member is not SNAPSHOT)
WHOLE_SNAPSHOT = Shard(SNAPSHOT.subject, SNAPSHOT)
LIFECYCLE = next(shard for shard in SHARDS if shard.member is MEMBERS[1])


@pytest.fixture(scope="module")
def contract() -> BudgetContract:
    return BudgetContract.load()


@pytest.fixture(scope="module")
def envelopes(contract: BudgetContract) -> dict[str, dict[str, Any]]:
    return member_envelopes(contract)


def _identities() -> dict[str, RuntimeStatus]:
    return {
        minor: RuntimeIdentity("CPython", f"{minor}.1", f"/interpreters/{minor}")
        for minor in supported_minors()
    }


def _split_plan(contract: BudgetContract) -> tuple[Shard, ...]:
    """A synthetic partition: one shard per Snapshot workload name, the other
    members whole."""
    return (
        *(
            Shard(f"snapshot-{name.lower()}", SNAPSHOT, frozenset({name}))
            for name in workload_names(contract)
        ),
        *(Shard(member.subject, member) for member in OTHERS),
    )


def _option(arguments: Sequence[str], option: str) -> list[str]:
    return [arguments[i + 1] for i, argument in enumerate(arguments) if argument == option]


def _member_runner(
    contract: BudgetContract,
    envelopes: dict[str, dict[str, Any]],
    *,
    metadata: bool = True,
    failing: Callable[[Member], tuple[int, str, str] | None] | None = None,
) -> tuple[cost_report.Runner, list[tuple[str, list[str]]]]:
    """A fake member that answers the shard it was asked for, with the
    sidecars a real member writes."""
    invoked: list[tuple[str, list[str]]] = []

    def run(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        invoked.append((member.subject, list(arguments)))
        (durations,) = _option(arguments, cost_report.DURATIONS_OPTION)
        (metadata_path,) = _option(arguments, cost_report.METADATA_OPTION)
        Spans().write(Path(durations))
        if metadata:
            write_metadata(Path(metadata_path), member.subject, _identities())
        if failing is not None and (answer := failing(member)) is not None:
            return answer
        workloads = _option(arguments, cost_report.WORKLOAD_OPTION)
        if member.subject == SNAPSHOT.subject and workloads:
            document = complete_snapshot(contract, workload_selection(workloads, contract))
        else:
            document = envelopes[member.subject]
        return (0, json.dumps(document), "")

    return run, invoked


# --------------------------------------------------------------------------- #
# The plan                                                                     #
# --------------------------------------------------------------------------- #
def test_the_plan_splits_snapshot_by_workload_heaviest_first_and_keeps_the_others_whole(
    contract: BudgetContract,
) -> None:
    validate_plan(SHARDS, contract)
    assert [(shard.id, shard.subject, shard.workloads) for shard in SHARDS] == [
        ("snapshot-duplicate-include", SNAPSHOT.subject, frozenset({"duplicate-include"})),
        ("snapshot-document-heavy", SNAPSHOT.subject, frozenset({"document-heavy"})),
        ("snapshot-conventional-fanout", SNAPSHOT.subject, frozenset({"conventional-fanout"})),
        ("snapshot-bitemporal-current", SNAPSHOT.subject, frozenset({"bitemporal-current"})),
        ("snapshot-versioned-document", SNAPSHOT.subject, frozenset({"versioned-document"})),
        ("snapshot-controls", SNAPSHOT.subject, frozenset({CONTROL_GROUP})),
        (
            "snapshot-geometry-plan-stress",
            SNAPSHOT.subject,
            frozenset({GEOMETRY_GROUP, PLAN_GROUP, "stress-columns", "stress-document"}),
        ),
        ("lifecycle-overhead", "lifecycle-overhead", None),
        ("instance-state", "instance-state", None),
        ("write-lowering", "write-lowering", None),
    ]
    assert [shard.member for shard in OTHER_SHARDS] == list(OTHERS)
    assert plan_ids("sharded") == [shard.id for shard in SHARDS]
    assert plan_ids("sequential") == [ALL_SHARDS]
    with pytest.raises(ValueError, match="layout"):
        plan_ids("parallel")


def test_the_plan_covers_every_snapshot_address_on_every_supported_minor_exactly_once(
    contract: BudgetContract,
) -> None:
    covered = [
        address
        for shard in SNAPSHOT_SHARDS
        for address in selected_addresses(contract, supported_minors(), shard.selection(contract))
    ]
    assert sorted(covered) == sorted(
        selected_addresses(contract, supported_minors(), cost_report.every_cell)
    )
    assert sorted(name for shard in SNAPSHOT_SHARDS for name in shard.workloads or ()) == sorted(
        workload_names(contract)
    )
    assert shard_arguments(SHARDS[0]) == [cost_report.WORKLOAD_OPTION, "duplicate-include"]
    assert shard_arguments(SHARDS[5]) == [cost_report.WORKLOAD_OPTION, CONTROL_GROUP]
    assert shard_arguments(SHARDS[6]) == [
        cost_report.WORKLOAD_OPTION,
        GEOMETRY_GROUP,
        cost_report.WORKLOAD_OPTION,
        PLAN_GROUP,
        cost_report.WORKLOAD_OPTION,
        "stress-columns",
        cost_report.WORKLOAD_OPTION,
        "stress-document",
    ]
    assert all(shard_arguments(shard) == [] for shard in OTHER_SHARDS)


def test_the_plan_is_printed_deterministically_for_either_layout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cost_report.main(["--plan"]) == 0
    assert json.loads(capsys.readouterr().out) == plan_ids("sharded")
    assert cost_report.main(["--plan", "--layout", "sharded"]) == 0
    assert json.loads(capsys.readouterr().out) == plan_ids("sharded")
    assert cost_report.main(["--plan", "--layout", "sequential"]) == 0
    assert json.loads(capsys.readouterr().out) == [ALL_SHARDS]


def test_a_workload_split_plan_covers_every_snapshot_address_exactly_once(
    contract: BudgetContract,
) -> None:
    plan = _split_plan(contract)
    validate_plan(plan, contract)
    assert shard_arguments(plan[0]) == [cost_report.WORKLOAD_OPTION, contract.workload_ids[0]]
    assert shard_arguments(plan[-1]) == []
    everything = selected_addresses(contract, supported_minors(), cost_report.every_cell)
    covered = [
        address
        for shard in plan
        if shard.subject == SNAPSHOT.subject
        for address in selected_addresses(contract, supported_minors(), shard.selection(contract))
    ]
    assert sorted(covered) == sorted(everything)


@pytest.mark.parametrize(
    ("plan", "message"),
    [
        ((Shard("all", SNAPSHOT), *OTHER_SHARDS), "reserved or unsafe"),
        ((Shard("Snapshot Delivery", SNAPSHOT), *OTHER_SHARDS), "reserved or unsafe"),
        ((Shard("x", SNAPSHOT), Shard("x", MEMBERS[1]), *OTHER_SHARDS[1:]), "not unique"),
        (
            (Shard("s", Member("python-report-other", "other.py", "other")), *SHARDS),
            "does not run",
        ),
        (
            (Shard("w", MEMBERS[1], frozenset({"a"})), WHOLE_SNAPSHOT, *OTHER_SHARDS[1:]),
            "has no workloads",
        ),
        ((Shard("w", SNAPSHOT, frozenset()), *OTHER_SHARDS), "selects no workload"),
        (OTHER_SHARDS, "snapshot-delivery must be one whole shard, found 0"),
        ((*SHARDS, Shard("again", MEMBERS[1])), "must be one whole shard, found 2"),
        ((WHOLE_SNAPSHOT, WHOLE_SNAPSHOT, *OTHER_SHARDS), "not unique"),
        ((Shard("half", SNAPSHOT, frozenset({GEOMETRY_GROUP})), *OTHER_SHARDS), "no shard covers"),
        (SHARDS[1:], "no shard covers"),
        (
            (
                Shard("half", SNAPSHOT, frozenset({GEOMETRY_GROUP})),
                WHOLE_SNAPSHOT,
                *OTHER_SHARDS,
            ),
            "mixes a whole-member shard",
        ),
        (
            (
                Shard("one", SNAPSHOT, frozenset({GEOMETRY_GROUP})),
                Shard("two", SNAPSHOT, frozenset({GEOMETRY_GROUP, PLAN_GROUP})),
                *OTHER_SHARDS,
            ),
            "covered by both 'one' and 'two'",
        ),
        ((*SHARDS, Shard("twice", SNAPSHOT, frozenset({PLAN_GROUP}))), "covered by both"),
        ((Shard("bad", SNAPSHOT, frozenset({"nope"})), *OTHER_SHARDS), "unknown workload nope"),
    ],
)
def test_an_incomplete_overlapping_or_unsafe_plan_is_refused(
    contract: BudgetContract, plan: tuple[Shard, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_plan(plan, contract)


# --------------------------------------------------------------------------- #
# One shard's collection                                                       #
# --------------------------------------------------------------------------- #
def test_a_shard_runs_its_member_once_over_its_workloads_with_both_sidecars(
    contract: BudgetContract, envelopes: dict[str, dict[str, Any]]
) -> None:
    run, invoked = _member_runner(contract, envelopes)
    shard = Shard("geometry", SNAPSHOT, frozenset({PLAN_GROUP, GEOMETRY_GROUP}))
    result = collect_shard(shard, run)
    assert [(subject, arguments[:4]) for subject, arguments in invoked] == [
        (SNAPSHOT.subject, ["--workload", GEOMETRY_GROUP, "--workload", PLAN_GROUP])
    ]
    assert _option(invoked[0][1], cost_report.DURATIONS_OPTION)
    assert _option(invoked[0][1], cost_report.METADATA_OPTION)
    assert result.result.envelope is not None
    readings = cast("list[dict[str, object]]", result.result.envelope["readings"])
    assert {(r["runtime"], r["workload"], r["cell"]) for r in readings} == set(
        selected_addresses(contract, supported_minors(), shard.selection(contract))
    )
    assert result.result.envelope["comparisons"] == []
    assert result.runtimes == _identities()
    assert not result.failed_required
    assert [(span.scope, span.name, dict(span.labels)) for span in result.durations.spans] == [
        ("member", SNAPSHOT.subject, {"member": SNAPSHOT.subject}),
        ("collection", "geometry", {"shard": "geometry"}),
    ]


def test_a_slice_answered_for_the_whole_matrix_is_not_that_slices_evidence(
    contract: BudgetContract, envelopes: dict[str, dict[str, Any]]
) -> None:
    def whole(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        del arguments
        return (0, json.dumps(envelopes[member.subject]), "")

    result = collect_shard(Shard("plan", SNAPSHOT, frozenset({PLAN_GROUP})), whole)
    assert result.result.envelope is None
    assert result.failed_required
    assert "Snapshot reading matrix is not exact: unexpected" in str(result.result.failure)


def test_missing_or_malformed_metadata_leaves_every_runtime_unavailable(
    contract: BudgetContract, envelopes: dict[str, dict[str, Any]]
) -> None:
    run, _invoked = _member_runner(contract, envelopes, metadata=False)
    absent = collect_shard(LIFECYCLE, run)
    assert absent.runtimes == dict.fromkeys(
        supported_minors(), RuntimeUnavailable("the member wrote no metadata sidecar")
    )

    def malformed(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        (metadata_path,) = _option(arguments, cost_report.METADATA_OPTION)
        Path(metadata_path).write_text('{"schemaVersion": 1, "runtimes": []}', encoding="utf-8")
        return (0, json.dumps(envelopes[member.subject]), "")

    broken = collect_shard(LIFECYCLE, malformed)
    assert all(isinstance(status, RuntimeUnavailable) for status in broken.runtimes.values())
    assert all(
        "runtimes is not an object" in cast("RuntimeUnavailable", status).reason
        for status in broken.runtimes.values()
    )

    def partial(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        (metadata_path,) = _option(arguments, cost_report.METADATA_OPTION)
        write_metadata(Path(metadata_path), member.subject, {"9.99": _identities()["3.14"]})
        return (0, json.dumps(envelopes[member.subject]), "")

    incomplete = collect_shard(LIFECYCLE, partial)
    assert incomplete.runtimes == dict.fromkeys(
        supported_minors(), RuntimeUnavailable("the member recorded no identity for this runtime")
    )
    assert incomplete.result.envelope is not None


# --------------------------------------------------------------------------- #
# Requests and captures                                                        #
# --------------------------------------------------------------------------- #
def test_a_local_request_names_the_checkout_and_a_fresh_id() -> None:
    head = cost_report.git_head()
    first = local_request("sharded")
    second = local_request("sequential", head)
    assert first.request_id != second.request_id
    assert first.request_id.startswith("local-")
    assert (first.event, first.requested_ref, first.head_commit, first.workflow_commit) == (
        "local",
        head,
        head,
        head,
    )
    assert first.base_commit is None and second.base_commit == head
    assert (first.run_id, first.run_attempt, first.pull_request) == (None, None, None)
    assert not first.is_pull_request
    assert Request.from_document(first.document()) == first
    assert first.document()["schemaVersion"] == cost_report.REQUEST_VERSION


def _request_document(**overrides: object) -> dict[str, object]:
    document = local_request("sharded").document()
    document.update(overrides)
    return document


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"schemaVersion": 2}, "schemaVersion 2"),
        ({"layout": "parallel"}, "layout 'parallel'"),
        ({"requestId": ""}, "requestId ''"),
        ({"headCommit": "abc"}, "headCommit 'abc' is not a full commit"),
        ({"baseCommit": 12}, "baseCommit 12"),
        ({"pullRequest": "7"}, "pullRequest '7'"),
        ({"runAttempt": True}, "runAttempt True"),
        ({"runId": 1.5}, "runId 1.5"),
    ],
)
def test_a_malformed_request_is_refused_by_field(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Request.from_document(_request_document(**overrides))
    with pytest.raises(ValueError, match="request is not an object"):
        Request.from_document([])


def test_a_hosted_request_keeps_its_run_and_attempt_beside_the_caller_supplied_id() -> None:
    head = cost_report.git_head()
    request = Request.from_document(
        _request_document(
            requestId="dispatch-42",
            event="pull_request",
            pullRequest=42,
            baseCommit=head,
            eventBaseCommit=head,
            runId=123456789,
            runAttempt=2,
        )
    )
    assert request.run == ("dispatch-42", "123456789", 2)
    assert request.is_pull_request
    nightly = Request.from_document(_request_document(event="schedule", requestId="night-1"))
    assert nightly.run == ("night-1", None, None)
    assert not nightly.is_pull_request


def _capture(request: Request, side: str = HEAD, pair: str = "pair") -> Capture:
    return Capture(
        request,
        SHARDS[0].id,
        SNAPSHOT.subject,
        tuple(sorted(SHARDS[0].workloads or ())),
        side,
        request.head_commit,
        pair,
        _identities(),
        {"image": "ubuntu24", "imageVersion": "20260901.1"},
    )


def test_a_capture_round_trips_and_refuses_malformed_fields() -> None:
    request = local_request("sharded")
    capture = _capture(request)
    document = capture.document()
    assert Capture.from_document(document) == capture
    assert document["shard"] == SHARDS[0].document()
    assert document["shard"] == {
        "id": SHARDS[0].id,
        "subject": SNAPSHOT.subject,
        "workloads": ["duplicate-include"],
    }
    whole = Capture.from_document(
        {
            **document,
            "shard": {**cast("dict[str, object]", document["shard"]), "workloads": None},
        }
    )
    assert whole.workloads is None
    forged: list[tuple[str, object, str]] = [
        ("schemaVersion", 3, "schemaVersion 3"),
        ("side", "middle", "side 'middle'"),
        ("commit", "short", "not a full commit"),
        ("pairId", "", "pairId ''"),
        ("runtimes", [], "runtimes is not an object"),
        ("runner", {"image": "x"}, "not an image and version"),
        ("shard", {"id": "s", "subject": "x", "workloads": "plan"}, "workloads 'plan'"),
        (
            "shard",
            {"id": "s", "subject": "x", "workloads": []},
            "workloads \\[\\] are not distinct",
        ),
        (
            "shard",
            {"id": "s", "subject": "x", "workloads": ["plan", "plan"]},
            "workloads \\['plan', 'plan'\\] are not distinct",
        ),
        ("request", {}, "schemaVersion None"),
    ]
    for field, value, message in forged:
        with pytest.raises(ValueError, match=message):
            Capture.from_document({**document, field: value})


def test_a_written_shard_is_a_legacy_portfolio_with_its_capture_beside_it(
    tmp_path: Path, contract: BudgetContract, envelopes: dict[str, dict[str, Any]]
) -> None:
    request = local_request("sharded")
    result = ShardResult(
        LIFECYCLE, MemberResult(MEMBERS[1], envelopes[MEMBERS[1].subject]), Spans(), _identities()
    )
    out = tmp_path / HEAD / LIFECYCLE.id
    write_shard(result, request, HEAD, request.head_commit, "pair-1", out)
    assert sorted(path.name for path in out.iterdir()) == sorted(
        ["portfolio.json", "summary.md", DURATIONS_FILE, CAPTURE_FILE, f"{MEMBERS[1].subject}.json"]
    )
    portfolio = json.loads((out / "portfolio.json").read_text(encoding="utf-8"))
    assert set(portfolio) == {"schemaVersion", "members", "failures"}
    assert len(portfolio["members"]) == 1
    capture = Capture.from_document(json.loads((out / CAPTURE_FILE).read_text(encoding="utf-8")))
    assert capture.request == request
    assert (capture.shard_id, capture.subject, capture.workloads, capture.side) == (
        LIFECYCLE.id,
        MEMBERS[1].subject,
        None,
        HEAD,
    )
    assert capture.commit == request.head_commit
    assert capture.pair_id == "pair-1"
    assert capture.runtimes == _identities()
    del contract


# --------------------------------------------------------------------------- #
# --shard: one shard, or every shard in order, on this runner                   #
# --------------------------------------------------------------------------- #
def test_sequential_all_and_independent_shards_write_identical_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    contract: BudgetContract,
    envelopes: dict[str, dict[str, Any]],
) -> None:
    plan = SHARDS
    run, invoked = _member_runner(contract, envelopes)
    monkeypatch.setattr(cost_report, "run_member", run)
    everything = tmp_path / "all"
    assert cost_report.main(["--shard", ALL_SHARDS, "--out", str(everything)]) == 0
    capsys.readouterr()
    sequential = [(subject, _option(arguments, "--workload")) for subject, arguments in invoked]
    assert [subject for subject, _ in sequential] == [shard.subject for shard in plan]
    assert sorted(name for _subject, names in sequential for name in names) == sorted(
        workload_names(contract)
    )
    assert sorted(path.name for path in (everything / HEAD).iterdir()) == sorted(
        shard.id for shard in plan
    )
    assert Request.load(everything / REQUEST_FILE).layout == "sequential"
    assert not (everything / BASE).exists()
    invoked.clear()
    separately = tmp_path / "separately"
    for shard in plan:
        assert cost_report.main(["--shard", shard.id, "--out", str(separately / shard.id)]) == 0
        capsys.readouterr()
    assert [(subject, _option(arguments, "--workload")) for subject, arguments in invoked] == (
        sequential
    )
    for shard in plan:
        one = json.loads(
            (separately / shard.id / HEAD / shard.id / "portfolio.json").read_text("utf-8")
        )
        whole = json.loads((everything / HEAD / shard.id / "portfolio.json").read_text("utf-8"))
        assert one == whole
        assert Request.load(separately / shard.id / REQUEST_FILE).layout == "sharded"
    readings = [
        (r["runtime"], r["workload"], r["cell"])
        for shard in plan
        if shard.subject == SNAPSHOT.subject
        for r in json.loads(
            (everything / HEAD / shard.id / f"{SNAPSHOT.subject}.json").read_text("utf-8")
        )["readings"]
    ]
    assert sorted(readings) == sorted(
        (r["runtime"], r["workload"], r["cell"]) for r in envelopes[SNAPSHOT.subject]["readings"]
    )
    assert len(readings) == len(set(readings))


def test_the_local_default_still_writes_the_complete_legacy_portfolio_over_whole_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    contract: BudgetContract,
    envelopes: dict[str, dict[str, Any]],
) -> None:
    run, invoked = _member_runner(contract, envelopes)
    monkeypatch.setattr(cost_report, "run_member", run)
    out = tmp_path / "reports"
    assert cost_report.main(["--out", str(out)]) == 0
    capsys.readouterr()
    assert [(subject, _option(arguments, "--workload")) for subject, arguments in invoked] == [
        (member.subject, []) for member in MEMBERS
    ]
    portfolio = json.loads((out / "portfolio.json").read_text(encoding="utf-8"))
    assert [member["subject"] for member in portfolio["members"]] == [m.subject for m in MEMBERS]
    assert portfolio["members"][0] == envelopes[SNAPSHOT.subject]
    assert portfolio["failures"] == []
    assert sorted(path.name for path in out.iterdir()) == sorted(
        [
            "portfolio.json",
            "summary.md",
            DURATIONS_FILE,
            cost_report.CONDITIONS_FILE,
            *(f"{m.subject}.json" for m in MEMBERS),
        ]
    )
    assert not (out / CAPTURE_FILE).exists() and not (out / HEAD).exists()


def test_a_failed_required_head_exits_non_zero_after_writing_every_shard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    contract: BudgetContract,
    envelopes: dict[str, dict[str, Any]],
) -> None:
    def failing(member: Member) -> tuple[int, str, str] | None:
        return (3, "", "the matrix is incomplete") if member.required else None

    run, invoked = _member_runner(contract, envelopes, failing=failing)
    monkeypatch.setattr(cost_report, "run_member", run)
    out = tmp_path / "reports"
    assert cost_report.main(["--shard", ALL_SHARDS, "--out", str(out)]) == 1
    capsys.readouterr()
    assert [subject for subject, _ in invoked] == [shard.subject for shard in SHARDS]
    for shard in SHARDS:
        directory = out / HEAD / shard.id
        assert (directory / CAPTURE_FILE).exists()
        portfolio = json.loads((directory / "portfolio.json").read_text(encoding="utf-8"))
        if shard.member.required:
            assert portfolio["members"] == []
            assert portfolio["failures"][0]["message"] == "exit 3: the matrix is incomplete"
        else:
            assert len(portfolio["members"]) == 1

    def optional_failure(member: Member) -> tuple[int, str, str] | None:
        return None if member.required else (9, "", "optional report unavailable")

    run, _invoked = _member_runner(contract, envelopes, failing=optional_failure)
    monkeypatch.setattr(cost_report, "run_member", run)
    assert cost_report.main(["--shard", ALL_SHARDS, "--out", str(tmp_path / "optional")]) == 0


def test_each_invocation_pairs_its_base_and_head_under_a_fresh_id(
    tmp_path: Path, contract: BudgetContract, envelopes: dict[str, dict[str, Any]]
) -> None:
    run, _invoked = _member_runner(contract, envelopes)
    head = cost_report.git_head()
    request = local_request("sharded", head)
    seen: list[str] = []

    def base_runner(workspace: Path, arguments: Sequence[str]) -> tuple[int, str, str]:
        del workspace
        if arguments[0] == "--plan":
            return (0, json.dumps([]), "")
        raise AssertionError("no shard is measured when the base plan lacks it")

    @contextlib.contextmanager
    def worktree(commit: str) -> Generator[Path]:
        seen.append(commit)
        yield tmp_path / "checkout"

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cost_report, "base_worktree", worktree)
        for attempt in ("first", "second"):
            assert (
                run_shards([LIFECYCLE.id], request, tmp_path / attempt, run, base_runner, SHARDS)
                == 0
            )
    assert seen == [head, head]
    pairs = {
        Capture.from_document(
            json.loads((tmp_path / attempt / HEAD / LIFECYCLE.id / CAPTURE_FILE).read_text("utf-8"))
        ).pair_id
        for attempt in ("first", "second")
    }
    assert len(pairs) == 2
    marker = json.loads(
        (tmp_path / "first" / BASE / LIFECYCLE.id / UNAVAILABLE_FILE).read_text("utf-8")
    )
    assert marker["reason"]["code"] == "missing-base-support"
    assert marker["baseCommit"] == head
    assert not (tmp_path / "first" / BASE / LIFECYCLE.id / CAPTURE_FILE).exists()


# --------------------------------------------------------------------------- #
# The CLI fences                                                               #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "arguments",
    [
        ["--layout", "sharded"],
        ["--base-commit", "abc"],
        ["--against", "previous"],
        ["--request", "request.json"],
        ["--shard", "nope", "--out", "reports"],
        ["--shard", SHARDS[0].id],
        ["--shard", "snapshot-delivery", "--out", "reports"],
        ["--assemble", "reports"],
        ["--plan", "--shard", "all", "--out", "reports"],
        ["--shard", "all", "--assemble", "reports", "--out", "assembled"],
        ["--plan", "--verify", "portfolio.json"],
        ["--diagnostic", "--plan"],
        ["--plan", "--layout", "parallel"],
    ],
)
def test_shard_options_are_fenced_from_one_another_and_from_every_other_mode(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        cost_report.main(arguments)
    assert error.value.code == 2
    assert capsys.readouterr().err


def test_a_request_must_agree_with_the_checkout_layout_and_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    head = cost_report.git_head()
    request = tmp_path / REQUEST_FILE
    local_request("sharded", head).write(request)
    for arguments, message in (
        (["--shard", ALL_SHARDS, "--request", str(request)], "sequential layout"),
        (
            ["--shard", LIFECYCLE.id, "--request", str(request), "--base-commit", "HEAD~1"],
            "disagrees with the request",
        ),
        (["--shard", LIFECYCLE.id, "--base-commit", "not-a-ref"], "is not a commit"),
    ):
        with pytest.raises(SystemExit) as error:
            cost_report.main([*arguments, "--out", str(tmp_path / "out")])
        assert error.value.code == 2
        assert message in capsys.readouterr().err
    moved = Request.from_document({**local_request("sharded").document(), "headCommit": "f" * 40})
    moved.write(request)
    with pytest.raises(SystemExit) as error:
        cost_report.main(
            ["--shard", LIFECYCLE.id, "--request", str(request), "--out", str(tmp_path)]
        )
    assert error.value.code == 2
    assert "is not the checkout's" in capsys.readouterr().err
    request.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        cost_report.main(
            ["--shard", LIFECYCLE.id, "--request", str(request), "--out", str(tmp_path)]
        )
    assert error.value.code == 2
    assert "does not hold a request" in capsys.readouterr().err
    assert not (tmp_path / HEAD).exists()


# --------------------------------------------------------------------------- #
# Base self-measurement                                                        #
# --------------------------------------------------------------------------- #
def _git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "cost@example.invalid")
    _git(repo, "config", "user.name", "Cost Report")
    workspace = repo / "languages" / "python" / "tools"
    workspace.mkdir(parents=True)
    (workspace / "cost_report.py").write_text("print('base')\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


class _BaseTool:
    """A fake base checkout's collector: it answers a plan and stages a shard
    exactly where the head asked, recording where it was invoked."""

    def __init__(
        self,
        commit: str,
        envelope: dict[str, Any],
        plan: list[str] | None = None,
        *,
        plan_answer: tuple[int, str, str] | None = None,
        staged_commit: str | None = None,
        stage: bool = True,
        malformed: bool = False,
    ) -> None:
        self.commit = commit
        self.envelope = envelope
        self.plan = plan if plan is not None else [shard.id for shard in SHARDS]
        self.plan_answer = plan_answer
        self.staged_commit = staged_commit or commit
        self.stage = stage
        self.malformed = malformed
        self.calls: list[tuple[Path, list[str]]] = []
        self.checkouts: list[Path] = []

    def __call__(self, workspace: Path, arguments: Sequence[str]) -> tuple[int, str, str]:
        self.calls.append((workspace, list(arguments)))
        checkout = workspace.parents[1]
        self.checkouts.append(checkout)
        assert workspace == checkout / "languages" / "python"
        assert (workspace / "tools" / "cost_report.py").read_text(
            encoding="utf-8"
        ) == "print('base')\n"
        assert _git(checkout, "rev-parse", "HEAD") == self.commit
        assert (
            subprocess.run(
                ["git", "symbolic-ref", "-q", "HEAD"],
                cwd=checkout,
                capture_output=True,
                check=False,
            ).returncode
            != 0
        )
        if arguments[0] == "--plan":
            assert arguments == ["--plan", "--layout", "sharded"]
            return self.plan_answer or (0, json.dumps(self.plan) + "\n", "")
        assert arguments[:3] == ["--shard", arguments[1], "--out"]
        staging = Path(arguments[3])
        assert staging.is_absolute()
        if not self.stage:
            return (1, "", "the base could not measure")
        shard = next(shard for shard in SHARDS if shard.id == arguments[1])
        base_local = Request.from_document(
            {
                **local_request("sharded").document(),
                "headCommit": self.staged_commit,
                "workflowCommit": self.staged_commit,
                "requestedRef": self.staged_commit,
            }
        )
        result = ShardResult(
            shard, MemberResult(shard.member, self.envelope), Spans(), _identities()
        )
        write_shard(
            result, base_local, HEAD, self.staged_commit, "base-own-pair", staging / HEAD / shard.id
        )
        if self.malformed:
            (staging / HEAD / shard.id / CAPTURE_FILE).write_text("{", encoding="utf-8")
        return (0, "", "")


def _no_worktrees_left(repo: Path) -> bool:
    listed = _git(repo, "worktree", "list", "--porcelain")
    return listed.count("worktree ") == 1


def test_the_base_measures_itself_in_a_detached_worktree_that_is_removed_afterwards(
    tmp_path: Path, repository: tuple[Path, str], envelopes: dict[str, dict[str, Any]]
) -> None:
    repo, commit = repository
    tool = _BaseTool(commit, envelopes[MEMBERS[1].subject])
    request = Request.from_document({**local_request("sharded").document(), "baseCommit": commit})
    out = tmp_path / "reports" / BASE
    result = measure_base(
        commit,
        LIFECYCLE.id,
        out,
        request,
        "shared-pair",
        tool,
        lambda commit: cost_report.base_worktree(commit, repo),
    )
    assert result == BaseResult(LIFECYCLE.id, commit, None, result.capture)
    assert result.measured
    assert [arguments for _workspace, arguments in tool.calls] == [
        ["--plan", "--layout", "sharded"],
        ["--shard", LIFECYCLE.id, "--out", tool.calls[1][1][3]],
    ]
    assert tool.checkouts[0] == tool.checkouts[1]
    assert not tool.checkouts[0].exists()
    assert _no_worktrees_left(repo)
    imported = out / LIFECYCLE.id
    assert sorted(path.name for path in imported.iterdir()) == sorted(
        [
            "portfolio.json",
            "summary.md",
            DURATIONS_FILE,
            CAPTURE_FILE,
            SELF_CAPTURE_FILE,
            f"{MEMBERS[1].subject}.json",
        ]
    )
    wrapped = Capture.from_document(json.loads((imported / CAPTURE_FILE).read_text("utf-8")))
    assert wrapped == result.capture
    assert wrapped.request == request
    assert (wrapped.side, wrapped.commit, wrapped.pair_id) == (BASE, commit, "shared-pair")
    assert wrapped.runtimes == _identities()
    original = Capture.from_document(json.loads((imported / SELF_CAPTURE_FILE).read_text("utf-8")))
    assert (original.side, original.pair_id, original.commit) == (HEAD, "base-own-pair", commit)
    assert original.request.request_id != request.request_id
    assert original.request.base_commit is None
    portfolio = json.loads((imported / "portfolio.json").read_text(encoding="utf-8"))
    assert portfolio["members"] == [envelopes[MEMBERS[1].subject]]
    assert not (imported / UNAVAILABLE_FILE).exists()


@pytest.mark.parametrize(
    ("options", "code", "message"),
    [
        (
            {"plan_answer": (2, "", "unrecognized arguments: --plan")},
            "base-plan-failed",
            "exited 2: unrecognized arguments",
        ),
        ({"plan_answer": (0, "not json", "")}, "base-plan-failed", "not JSON"),
        ({"plan_answer": (0, '{"a": 1}', "")}, "base-plan-failed", "not a list of ids"),
        ({"plan": ["elsewhere"]}, "missing-base-support", "has no shard"),
        (
            {"stage": False},
            "base-collection-failed",
            "exited 1 and wrote no capture: the base could not measure",
        ),
        ({"malformed": True}, "base-output-malformed", "does not decode"),
        (
            {"staged_commit": "e" * 40},
            "base-commit-mismatch",
            f"measured {'e' * 40}, not the requested",
        ),
    ],
)
def test_an_unavailable_base_records_its_distinct_reason_and_leaves_no_worktree(
    tmp_path: Path,
    repository: tuple[Path, str],
    envelopes: dict[str, dict[str, Any]],
    options: dict[str, Any],
    code: str,
    message: str,
) -> None:
    repo, commit = repository
    runner = _BaseTool(commit, envelopes[MEMBERS[1].subject], **options)
    request = Request.from_document({**local_request("sharded").document(), "baseCommit": commit})
    out = tmp_path / BASE
    result = measure_base(
        commit,
        LIFECYCLE.id,
        out,
        request,
        "pair",
        runner,
        lambda c: cost_report.base_worktree(c, repo),
    )
    assert result.reason is not None
    assert result.reason.code == code
    assert message in result.reason.message
    assert not result.measured and result.capture is None
    assert _no_worktrees_left(repo)
    assert all(not checkout.exists() for checkout in runner.checkouts)
    marker = json.loads((out / LIFECYCLE.id / UNAVAILABLE_FILE).read_text(encoding="utf-8"))
    assert marker == {
        "schemaVersion": 1,
        "shard": LIFECYCLE.id,
        "side": BASE,
        "baseCommit": commit,
        "reason": {"code": code, "message": result.reason.message},
    }
    assert sorted(path.name for path in (out / LIFECYCLE.id).iterdir()) == [UNAVAILABLE_FILE]


def test_a_commit_git_cannot_check_out_is_an_unavailable_base(
    tmp_path: Path, repository: tuple[Path, str]
) -> None:
    repo, _commit = repository
    request = local_request("sharded")

    def never(workspace: Path, arguments: Sequence[str]) -> tuple[int, str, str]:
        raise AssertionError(f"{workspace} {arguments} must never run")

    result = measure_base(
        "f" * 40,
        LIFECYCLE.id,
        tmp_path / BASE,
        request,
        "pair",
        never,
        lambda c: cost_report.base_worktree(c, repo),
    )
    assert result.reason is not None
    assert result.reason.code == "base-checkout-failed"
    assert _no_worktrees_left(repo)


def test_the_base_collector_runs_through_its_own_frozen_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []

    class _Completed:
        returncode = 0
        stdout = "[]\n"
        stderr = ""

    def run(command: list[str], **options: Any) -> _Completed:
        calls.append({"command": command, **options})
        return _Completed()

    monkeypatch.setattr(cost_report.subprocess, "run", run)
    monkeypatch.setenv("VIRTUAL_ENV", "/head/.venv")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/head/env")
    monkeypatch.setenv("PYTHONPATH", "/head")
    monkeypatch.setenv("UV_FROZEN", "1")
    assert cost_report.run_base(tmp_path, ["--plan", "--layout", "sharded"]) == (0, "[]\n", "")
    (call,) = calls
    assert call["command"] == [
        "uv",
        "run",
        "--frozen",
        "python",
        "tools/cost_report.py",
        "--plan",
        "--layout",
        "sharded",
    ]
    assert call["cwd"] == tmp_path
    assert not {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH"} & call["env"].keys()
    assert call["env"]["UV_FROZEN"] == "1"

    def missing(command: list[str], **options: Any) -> _Completed:
        raise OSError("uv is not installed")

    monkeypatch.setattr(cost_report.subprocess, "run", missing)
    assert cost_report.run_base(tmp_path, ["--plan"]) == (127, "", "uv is not installed")
