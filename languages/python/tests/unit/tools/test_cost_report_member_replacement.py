from __future__ import annotations

import functools
import json
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, cast

import pytest

import cost_report
from cost_report import (
    DURATIONS_OPTION,
    METADATA_OPTION,
    REPLACEMENT_KEY,
    REPLACEMENT_SPAN,
    SNAPSHOT_SUBJECT,
    WRITE_SUBJECT,
    Member,
    MemberReplacement,
    verify,
)
from durations import Spans
from interpreter_matrix import RuntimeIdentity, RuntimeStatus, supported_minors, write_metadata
from parallax.conformance.budget import BudgetContract, MemoryGates
from parallax.conformance.cost_envelope import Provenance, classify_authority
from tests.unit.tools._cost_report_support import complete_instance_state, member_envelopes

type Document = dict[str, Any]

ORIGINAL: Final = "a" * 40
REPLACEMENT: Final = "b" * 40
FAILURE: Final = (
    "exit 3: the matrix is incomplete, so no envelope is reported:\n"
    "CPython 3.14, cross-object.txtime.changed-64.columns.typed: the child's reading did "
    "not decode: samples.work.largestOrderedInvocation samples must be positive"
)
REPLACED_OWN_SOURCES: Final = frozenset(
    {
        "languages/python/tools/write_lowering_overhead.py",
        "languages/python/tools/cost_report.py",
        "languages/python/tests/unit/tools/test_write_lowering_overhead.py",
        "languages/python/evidence/cost/README.md",
    }
)


def _at(envelope: Document, contract: BudgetContract, commit: str) -> Document:
    """``envelope`` as a clean capture at ``commit`` on the authority host."""
    provenance = Provenance.from_document(envelope["provenance"])
    placed = Provenance.from_document(
        {
            **provenance.document(),
            **contract.authority,
            "dirty": False,
            "commit": commit,
            "postgres": provenance.postgres,
        }
    )
    return {
        **deepcopy(envelope),
        "provenance": placed.document(),
        "authority": classify_authority(placed, contract),
    }


@functools.cache
def _complete_envelopes() -> str:
    contract = BudgetContract.load()
    envelopes = member_envelopes(contract)
    envelopes[cost_report.INSTANCE_STATE_SUBJECT] = complete_instance_state(contract)
    return json.dumps(envelopes)


def _envelopes(contract: BudgetContract, commit: str) -> dict[str, Document]:
    envelopes = cast("dict[str, Document]", json.loads(_complete_envelopes()))
    return {subject: _at(envelope, contract, commit) for subject, envelope in envelopes.items()}


def _identities(patch: int = 8) -> dict[str, RuntimeStatus]:
    return {
        minor: RuntimeIdentity("CPython", f"{minor}.{patch}", "/p") for minor in supported_minors()
    }


@dataclass
class _Members:
    """A fake member runner: each member answers its envelope and both
    sidecars, the ``failing`` one its recorded failure instead."""

    envelopes: dict[str, Document]
    failing: str | None = None
    identities: dict[str, RuntimeStatus] = field(default_factory=_identities)
    calls: list[tuple[str, tuple[str, ...]]] = field(
        default_factory=list[tuple[str, tuple[str, ...]]]
    )

    def __call__(self, member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        self.calls.append((member.subject, tuple(arguments)))
        spans = Spans()
        with spans.span("case", "measured", runtime="3.14"):
            pass
        spans.write(Path(arguments[arguments.index(DURATIONS_OPTION) + 1]))
        write_metadata(
            Path(arguments[arguments.index(METADATA_OPTION) + 1]), member.subject, self.identities
        )
        if member.subject == self.failing:
            return 3, "", FAILURE.removeprefix("exit 3: ")
        return 0, json.dumps(self.envelopes[member.subject]), ""


@dataclass
class _Replacement:
    run_dir: Path
    out: Path
    contract: BudgetContract
    members: _Members
    events: list[str]

    @property
    def portfolio(self) -> Path:
        return self.run_dir / "portfolio.json"

    def files(self) -> dict[str, bytes]:
        return {path.name: path.read_bytes() for path in self.run_dir.iterdir()}

    def run(self, subject: str = WRITE_SUBJECT) -> int:
        return cost_report.main(
            [
                "--replace-member",
                subject,
                "--from",
                str(self.run_dir),
                "--out",
                str(self.out),
            ]
        )

    def rewrite(self, name: str, edit: Callable[[Document], None]) -> None:
        path = self.run_dir / name
        document = cast("Document", json.loads(path.read_text()))
        edit(document)
        path.write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Replacement:
    """A canonical capture at ``ORIGINAL`` whose write-lowering member failed,
    and a clean checkout at ``REPLACEMENT`` descending from it that changed only
    that member's own instrument, the collector, a test, and prose."""
    contract = BudgetContract.load()
    original = _Members(_envelopes(contract, ORIGINAL), failing=WRITE_SUBJECT)
    run_dir = tmp_path / "attempt-1"
    cost_report.write_portfolio(cost_report.collect(original, canonical=True), run_dir)
    events: list[str] = []
    members = _Members(_envelopes(contract, REPLACEMENT))

    def measured(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
        events.append(f"measure {member.subject}")
        return members(member, arguments)

    def preflight() -> None:
        events.append("preflight")

    def changed(commit: str) -> frozenset[str]:
        assert commit == ORIGINAL
        return REPLACED_OWN_SOURCES

    def descends(commit: str) -> bool:
        return commit == ORIGINAL

    monkeypatch.setattr(cost_report, "run_member", measured)
    monkeypatch.setattr(cost_report, "preflight", preflight)
    monkeypatch.setattr(cost_report, "committed_contract", lambda: contract)
    monkeypatch.setattr(cost_report, "checkout_is_clean", lambda: True)
    monkeypatch.setattr(cost_report, "git_head", lambda: REPLACEMENT)
    monkeypatch.setattr(cost_report, "is_published", descends)
    monkeypatch.setattr(cost_report, "changed_since", changed)
    return _Replacement(run_dir, tmp_path / "completed", contract, members, events)


def _unread_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    gates = MemoryGates.from_bytes(
        Path("memory-gates.yaml"),
        b"schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\n"
        b"gates: {unread: {w: {c: {unit: B, maxBytes: 1}}}}\n",
    )

    def load(path: Path | None = None) -> MemoryGates:
        return gates

    monkeypatch.setattr(MemoryGates, "load", staticmethod(load))


STATED: Final = (
    f"the {WRITE_SUBJECT} member, which the run at {ORIGINAL[:12]} failed to produce, "
    f"re-measured alone at {REPLACEMENT[:12]} after the run its provenance names, recorded "
    f"in the {cost_report.ADJUSTMENT_FIELD} of {cost_report.CONDITIONS_FILE}"
)


def test_a_failed_member_is_re_measured_alone_into_a_new_complete_capture(
    replacement: _Replacement,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = replacement.files()
    original = json.loads(replacement.portfolio.read_text())
    original_conditions = json.loads((replacement.run_dir / "conditions.json").read_text())
    original_spans = Spans.load(replacement.run_dir / "durations.json").spans
    assert [failure["recipe"] for failure in original["failures"]] == [
        "python-report-write-lowering"
    ]

    assert replacement.run() == 0
    assert replacement.files() == before
    assert replacement.events == ["preflight", f"measure {WRITE_SUBJECT}"]
    ((subject, arguments),) = replacement.members.calls
    assert subject == WRITE_SUBJECT
    assert "--authority-preflight" not in arguments

    completed = json.loads((replacement.out / "portfolio.json").read_text())
    assert [member["subject"] for member in completed["members"]] == [
        member.subject for member in cost_report.MEMBERS
    ]
    kept = [m for m in completed["members"] if m["subject"] != WRITE_SUBJECT]
    assert kept == original["members"]
    (write,) = (m for m in completed["members"] if m["subject"] == WRITE_SUBJECT)
    assert write == replacement.members.envelopes[WRITE_SUBJECT]
    assert completed["failures"] == []

    conditions = json.loads((replacement.out / "conditions.json").read_text())
    adjustment = conditions.pop(cost_report.ADJUSTMENT_FIELD)
    assert conditions == {
        **original_conditions,
        "members": {
            **original_conditions["members"],
            WRITE_SUBJECT: {
                "sources": cost_report.source_digests(cost_report.MEMBER_SOURCES[WRITE_SUBJECT]),
                "runtimes": {
                    runtime: status.document()
                    for runtime, status in sorted(replacement.members.identities.items())
                },
            },
        },
    }
    assert adjustment["schemaVersion"] == 1
    recorded = adjustment[REPLACEMENT_KEY]
    assert {
        key: recorded[key]
        for key in ("member", "recipe", "originalCommit", "replacementCommit", "replacedFailure")
    } == {
        "member": WRITE_SUBJECT,
        "recipe": "python-report-write-lowering",
        "originalCommit": ORIGINAL,
        "replacementCommit": REPLACEMENT,
        "replacedFailure": FAILURE,
    }
    assert set(recorded["originalCollection"]) == {"startedAt", "finishedAt"}
    assert recorded["replacement"]["startedAt"] >= recorded["originalCollection"]["finishedAt"]

    spans = Spans.load(replacement.out / "durations.json")
    assert spans.spans[: len(original_spans)] == original_spans
    added = spans.spans[len(original_spans) :]
    assert {(span.scope, span.name) for span in added} >= {
        ("collection", REPLACEMENT_SPAN),
        ("member", WRITE_SUBJECT),
    }
    assert (replacement.out / "summary.md").read_text() == cost_report._summary(  # pyright: ignore[reportPrivateUsage] - renderer seam
        completed, spans
    )

    _unread_gates(monkeypatch)
    capsys.readouterr()
    assert cost_report.main(["--verify", str(replacement.out / "portfolio.json")]) == 0
    verified = capsys.readouterr()
    assert f"the capture is amended: {STATED}" in verified.out
    assert verified.err == ""
    assert (
        cost_report.main(
            ["--compare", str(replacement.portfolio), str(replacement.out / "portfolio.json")]
        )
        == 0
    )
    assert f"- The head capture is amended: {STATED}." in capsys.readouterr().out


def _without_write_failure(document: Document) -> None:
    document["failures"] = []


def _two_commits(document: Document) -> None:
    document["members"][-1]["provenance"]["commit"] = "c" * 40


def _dirty_kept(document: Document) -> None:
    document["members"][-1]["provenance"]["dirty"] = True


def _stale_workload(document: Document) -> None:
    document["members"][0]["provenance"]["workloadDigest"] = "0" * 64


def _two_failures(document: Document) -> None:
    document["failures"].append(deepcopy(document["failures"][0]))


@pytest.mark.parametrize(
    ("subject", "edit", "refusal"),
    [
        (SNAPSHOT_SUBJECT, None, "the capture produced the snapshot-delivery member"),
        ("unknown", None, "'unknown' is not a collected member"),
        (WRITE_SUBJECT, _without_write_failure, "records 0 collection failures"),
        (WRITE_SUBJECT, _two_failures, "records 2 collection failures"),
        (WRITE_SUBJECT, _two_commits, "the kept members name different producing commits"),
        (WRITE_SUBJECT, _dirty_kept, "a kept member was not produced from a clean tree"),
        (WRITE_SUBJECT, _stale_workload, "workload digest differs from HEAD's"),
    ],
)
def test_only_a_member_the_capture_failed_to_produce_is_replaced(
    replacement: _Replacement,
    capsys: pytest.CaptureFixture[str],
    subject: str,
    edit: Callable[[Document], None] | None,
    refusal: str,
) -> None:
    if edit is not None:
        replacement.rewrite("portfolio.json", edit)
    _refused_before_measuring(replacement, capsys, refusal, subject)


def _refused_before_measuring(
    replacement: _Replacement,
    capsys: pytest.CaptureFixture[str],
    refusal: str,
    subject: str = WRITE_SUBJECT,
) -> None:
    before = replacement.files()
    capsys.readouterr()
    assert replacement.run(subject) == 1
    assert refusal in capsys.readouterr().err
    assert replacement.members.calls == []
    assert not replacement.out.exists()
    assert replacement.files() == before


def _adjusted(document: Document) -> None:
    document[cost_report.ADJUSTMENT_FIELD] = {"reclassified": {}}


def _changed_kept_source(document: Document) -> None:
    document["members"][SNAPSHOT_SUBJECT]["sources"]["tests/unit/memory_instruments.py"] = "0" * 64


def test_an_adjusted_capture_is_never_replaced_into(
    replacement: _Replacement, capsys: pytest.CaptureFixture[str]
) -> None:
    replacement.rewrite("conditions.json", _adjusted)
    _refused_before_measuring(replacement, capsys, "already records an adjustment")


def test_a_kept_member_whose_recorded_sources_differ_from_heads_is_refused(
    replacement: _Replacement, capsys: pytest.CaptureFixture[str]
) -> None:
    replacement.rewrite("conditions.json", _changed_kept_source)
    _refused_before_measuring(
        replacement,
        capsys,
        "the kept snapshot-delivery member's recorded sources differ from HEAD's: "
        "tests/unit/memory_instruments.py",
    )


def test_a_capture_without_durations_is_refused(
    replacement: _Replacement, capsys: pytest.CaptureFixture[str]
) -> None:
    (replacement.run_dir / "durations.json").unlink()
    _refused_before_measuring(replacement, capsys, "records no durations.json")


def test_an_existing_output_directory_is_refused(
    replacement: _Replacement, capsys: pytest.CaptureFixture[str]
) -> None:
    replacement.out.mkdir()
    before = replacement.files()
    assert replacement.run() == 1
    assert "exists; the replacement writes a new capture directory" in capsys.readouterr().err
    assert replacement.members.calls == []
    assert list(replacement.out.iterdir()) == []
    assert replacement.files() == before


def _descends(_commit: str) -> bool:
    return True


def _unrelated(_commit: str) -> bool:
    return False


def _dirty() -> bool:
    return False


def _changed_contract() -> BudgetContract:
    current = BudgetContract.load()
    return BudgetContract.from_bytes(current.path, current.authored + b"\nextra: changed\n")


@pytest.mark.parametrize(
    ("seam", "fake", "refusal"),
    [
        ("checkout_is_clean", _dirty, "the checkout is not clean"),
        (
            "is_published",
            _unrelated,
            f"does not descend from the capture's {ORIGINAL[:12]}",
        ),
        (
            "committed_contract",
            _changed_contract,
            "embeds a Budget Contract other than HEAD's",
        ),
    ],
    ids=["dirty", "not-a-descendant", "contract"],
)
def test_a_checkout_that_cannot_complete_the_capture_is_refused(
    replacement: _Replacement,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    seam: str,
    fake: object,
    refusal: str,
) -> None:
    monkeypatch.setattr(cost_report, seam, fake)
    _refused_before_measuring(replacement, capsys, refusal)


@pytest.mark.parametrize(
    "path",
    [
        "languages/python/packages/parallax-core/src/parallax/core/sql_gen/_write.py",
        "languages/python/uv.lock",
        "languages/python/tools/interpreter_matrix.py",
        "languages/python/tools/snapshot_delivery_overhead.py",
        "languages/python/tools/lifecycle_overhead.py",
    ],
)
def test_a_change_to_what_a_kept_member_measured_through_is_refused(
    replacement: _Replacement,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    path: str,
) -> None:
    def changed(_commit: str) -> frozenset[str]:
        return REPLACED_OWN_SOURCES | {path}

    monkeypatch.setattr(cost_report, "changed_since", changed)
    _refused_before_measuring(
        replacement, capsys, f"HEAD changes what the kept members measured through: {path}"
    )


def test_a_refused_authority_preflight_measures_nothing(
    replacement: _Replacement,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def refused() -> None:
        raise ValueError("authority preflight refused:\n- cpython: observed '3.14.0'")

    monkeypatch.setattr(cost_report, "preflight", refused)
    _refused_before_measuring(replacement, capsys, "authority preflight refused")


def _refused_after_measuring(
    replacement: _Replacement, capsys: pytest.CaptureFixture[str], refusal: str
) -> None:
    before = replacement.files()
    capsys.readouterr()
    assert replacement.run() == 1
    assert refusal in capsys.readouterr().err
    assert [subject for subject, _arguments in replacement.members.calls] == [WRITE_SUBJECT]
    assert not replacement.out.exists()
    assert replacement.files() == before


def test_a_member_failing_again_writes_nothing(
    replacement: _Replacement, capsys: pytest.CaptureFixture[str]
) -> None:
    replacement.members.failing = WRITE_SUBJECT
    _refused_after_measuring(replacement, capsys, f"the {WRITE_SUBJECT} member failed again")


@pytest.mark.parametrize(("commit", "dirty"), [(ORIGINAL, False), (REPLACEMENT, True)])
def test_a_member_not_measured_on_a_clean_head_writes_nothing(
    replacement: _Replacement, capsys: pytest.CaptureFixture[str], commit: str, dirty: bool
) -> None:
    envelope = replacement.members.envelopes[WRITE_SUBJECT]
    envelope["provenance"] = {**envelope["provenance"], "commit": commit, "dirty": dirty}
    _refused_after_measuring(replacement, capsys, f"was not measured on a clean {REPLACEMENT[:12]}")


def test_a_member_measured_on_another_interpreter_writes_nothing(
    replacement: _Replacement, capsys: pytest.CaptureFixture[str]
) -> None:
    replacement.members.identities = _identities(patch=9)
    _refused_after_measuring(replacement, capsys, "the interpreters differ from the kept members'")


@pytest.mark.parametrize(
    "arguments",
    [
        ["--replace-member", WRITE_SUBJECT, "--out", "out"],
        ["--replace-member", WRITE_SUBJECT, "--from", "run"],
        ["--from", "run", "--out", "out"],
        ["--replace-member", WRITE_SUBJECT, "--from", "run", "--out", "out", "--verify", "p"],
        ["--replace-member", WRITE_SUBJECT, "--from", "run", "--out", "o", "--redigest", "p"],
    ],
)
def test_member_replacement_is_a_separate_mode_needing_its_capture_and_destination(
    arguments: list[str],
) -> None:
    with pytest.raises(SystemExit, match="2"):
        cost_report.main(arguments)


# --------------------------------------------------------------------------- #
# Verification accepts the commit difference only as a replacement states it. #
# --------------------------------------------------------------------------- #
def _verifiable(
    snapshot_commit: str, write_commit: str, *, instance: str | None = None
) -> Document:
    contract = BudgetContract.load()
    envelopes = _envelopes(contract, snapshot_commit)
    members = [
        envelopes[SNAPSHOT_SUBJECT],
        _at(envelopes[WRITE_SUBJECT], contract, write_commit),
    ]
    if instance is not None:
        members.append(_at(envelopes[cost_report.INSTANCE_STATE_SUBJECT], contract, instance))
    return {"schemaVersion": 1, "members": members, "failures": []}


WRITE_REPLACED: Final = MemberReplacement(WRITE_SUBJECT, ORIGINAL, REPLACEMENT)
DIFFERENT_COMMITS: Final = (
    "the snapshot-delivery and write-lowering envelopes name different commits"
)


def test_envelopes_naming_different_commits_verify_only_under_the_recorded_replacement() -> None:
    document = _verifiable(ORIGINAL, REPLACEMENT)
    assert verify(document) == [DIFFERENT_COMMITS]
    assert verify(document, replacement=WRITE_REPLACED) == []


@pytest.mark.parametrize(
    ("recorded", "refusals"),
    [
        (
            MemberReplacement(SNAPSHOT_SUBJECT, ORIGINAL, REPLACEMENT),
            [
                f"the snapshot-delivery envelope names commit {ORIGINAL[:12]}, but the recorded "
                f"replacement of the snapshot-delivery member requires the replacement commit "
                f"{REPLACEMENT[:12]}",
                f"the write-lowering envelope names commit {REPLACEMENT[:12]}, but the recorded "
                f"replacement of the snapshot-delivery member requires the original commit "
                f"{ORIGINAL[:12]}",
            ],
        ),
        (
            MemberReplacement("feature-boundary", ORIGINAL, REPLACEMENT),
            [
                f"the write-lowering envelope names commit {REPLACEMENT[:12]}, but the recorded "
                f"replacement of the feature-boundary member requires the original commit "
                f"{ORIGINAL[:12]}"
            ],
        ),
        (
            MemberReplacement(WRITE_SUBJECT, "c" * 40, REPLACEMENT),
            [
                f"the snapshot-delivery envelope names commit {ORIGINAL[:12]}, but the recorded "
                f"replacement of the write-lowering member requires the original commit "
                f"{'c' * 12}"
            ],
        ),
        (
            MemberReplacement(WRITE_SUBJECT, ORIGINAL, "c" * 40),
            [
                f"the write-lowering envelope names commit {REPLACEMENT[:12]}, but the recorded "
                f"replacement of the write-lowering member requires the replacement commit "
                f"{'c' * 12}"
            ],
        ),
    ],
    ids=["snapshot-named", "other-member-named", "original-commit", "replacement-commit"],
)
def test_a_replacement_naming_another_member_or_commit_is_refused(
    recorded: MemberReplacement, refusals: list[str]
) -> None:
    assert verify(_verifiable(ORIGINAL, REPLACEMENT), replacement=recorded) == refusals


def test_a_recorded_replacement_also_binds_a_capture_at_one_commit() -> None:
    assert verify(_verifiable(ORIGINAL, ORIGINAL)) == []
    assert verify(_verifiable(ORIGINAL, ORIGINAL), replacement=WRITE_REPLACED) == [
        f"the write-lowering envelope names commit {ORIGINAL[:12]}, but the recorded replacement "
        f"of the write-lowering member requires the replacement commit {REPLACEMENT[:12]}"
    ]


def test_a_required_kept_member_must_name_the_original_commit() -> None:
    required = [cost_report.INSTANCE_STATE_SUBJECT]
    kept = _verifiable(ORIGINAL, REPLACEMENT, instance=ORIGINAL)
    assert verify(kept, required=required, replacement=WRITE_REPLACED) == []
    moved = _verifiable(ORIGINAL, REPLACEMENT, instance=REPLACEMENT)
    assert verify(moved, required=required, replacement=WRITE_REPLACED) == [
        f"the instance-state envelope names commit {REPLACEMENT[:12]}, but the recorded "
        f"replacement of the write-lowering member requires the original commit {ORIGINAL[:12]}"
    ]
    assert verify(kept, required=required) == [
        DIFFERENT_COMMITS,
        "the instance-state envelope names a different commit from the required members",
    ]


def _beside(tmp_path: Path, document: Document, adjustment: object) -> Path:
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps(document), encoding="utf-8")
    conditions: Document = {"schemaVersion": 1, "members": {}}
    if adjustment is not None:
        conditions[cost_report.ADJUSTMENT_FIELD] = adjustment
    (tmp_path / "conditions.json").write_text(json.dumps(conditions), encoding="utf-8")
    return portfolio


def _recorded(**fields: object) -> dict[str, object]:
    return {
        REPLACEMENT_KEY: {
            "member": WRITE_SUBJECT,
            "originalCommit": ORIGINAL,
            "replacementCommit": REPLACEMENT,
            **fields,
        }
    }


@pytest.mark.parametrize(
    ("adjustment", "status", "stderr"),
    [
        (None, 1, DIFFERENT_COMMITS),
        ({"redigested": {}}, 1, DIFFERENT_COMMITS),
        (_recorded(), 0, ""),
        (_recorded(member="unknown"), 1, "is not a collected member"),
        (_recorded(originalCommit="a" * 12), 1, "is not a full commit hash"),
        (_recorded(replacementCommit=None), 1, "is not a non-empty string"),
    ],
    ids=["none", "other-adjustment", "recorded", "unknown-member", "short-commit", "absent"],
)
def test_verification_reads_the_replacement_recorded_beside_the_portfolio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    adjustment: object,
    status: int,
    stderr: str,
) -> None:
    _unread_gates(monkeypatch)
    monkeypatch.setattr(cost_report, "is_published", _descends)
    portfolio = _beside(tmp_path, _verifiable(ORIGINAL, REPLACEMENT), adjustment)
    assert cost_report.main(["--verify", str(portfolio)]) == status
    captured = capsys.readouterr()
    assert stderr in captured.err
    if not stderr:
        assert captured.err == ""
        assert f"the capture is amended: {STATED}" in captured.out


def test_a_replacement_is_stated_beside_other_adjustments(tmp_path: Path) -> None:
    portfolio = _beside(tmp_path, _verifiable(ORIGINAL, REPLACEMENT), _recorded())
    assert cost_report.amendment_beside(portfolio) == STATED
    _beside(tmp_path, _verifiable(ORIGINAL, REPLACEMENT), {**_recorded(), "reclassified": {}})
    assert cost_report.amendment_beside(portfolio) == (
        f"envelopes re-classified under a later Budget Contract and {STATED}"
    )
    assert cost_report.replacement_beside(portfolio) == WRITE_REPLACED
    _beside(tmp_path, _verifiable(ORIGINAL, REPLACEMENT), {"reclassified": {}})
    assert cost_report.replacement_beside(portfolio) is None
