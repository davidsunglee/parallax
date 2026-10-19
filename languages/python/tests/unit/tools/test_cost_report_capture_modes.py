from __future__ import annotations

import contextlib
import hashlib
import json
import subprocess
from collections.abc import Callable, Generator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import cost_report
import snapshot_delivery_overhead as snapshot_report
from cost_report import Collection, MemberResult
from durations import Spans
from interpreter_matrix import RuntimeIdentity, RuntimeUnavailable, authority_minor
from parallax.conformance import cost_envelope, workloads
from parallax.conformance.budget import BudgetContract, MemoryGates, derive_memory_gates
from parallax.conformance.cost_envelope import Provenance, classify_authority
from parallax.conformance.workloads import workload_digest
from tests.unit.tools._cost_report_support import (
    canary_provenance,
    complete_instance_state,
    identities,
    member_envelopes,
)


@pytest.fixture(params=("native", "ci"))
def capture_host(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.param == "native":
        return
    fingerprint = {
        "hw.model": "x86_64",
        "machdep.cpu.brand_string": "x86_64",
        "hw.physicalcpu": "4",
        "hw.memsize": str(16 * 1024**3),
    }
    monkeypatch.setattr(cost_envelope, "_sysctl", fingerprint.get)


def _on_authority_host(provenance: Provenance, contract: BudgetContract) -> Provenance:
    return Provenance.from_document(
        {
            **provenance.document(),
            **contract.authority,
            "dirty": False,
            "postgres": provenance.postgres,
        }
    )


def _preflight(monkeypatch: pytest.MonkeyPatch) -> tuple[BudgetContract, Provenance]:
    contract = BudgetContract.load()
    provenance = _on_authority_host(canary_provenance(contract), contract)
    monkeypatch.setattr(cost_report, "committed_contract", lambda: contract)

    def probe(_runtime: str, _namespace: str) -> RuntimeIdentity:
        return RuntimeIdentity("CPython", str(contract.authority["cpython"]), "/p")

    def capture(*_args: Any, **_kwargs: Any) -> Provenance:
        return provenance

    monkeypatch.setattr(cost_report, "probe_runtime", probe)
    monkeypatch.setattr(Provenance, "capture", capture)
    return contract, provenance


@pytest.mark.parametrize(
    ("field", "value", "label"),
    [
        ("machine", "other", "machine"),
        ("cpu", "other", "cpu"),
        ("cores", 1, "cores"),
        ("ram_gib", 1, "ramGiB"),
        ("cpython", "3.14.0", "cpython"),
        ("dirty", True, "dirty"),
        ("commit", "", "commit"),
    ],
)
def test_canonical_refuses_before_any_member(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
    label: str,
) -> None:
    _contract, provenance = _preflight(monkeypatch)
    changed = replace(provenance, **{field: value})

    def capture(*_args: Any, **_kwargs: Any) -> Provenance:
        return changed

    def run_member(*_args: Any) -> Any:
        pytest.fail("member ran")

    monkeypatch.setattr(Provenance, "capture", capture)
    monkeypatch.setattr(cost_report, "run_member", run_member)
    out = tmp_path / "capture"
    assert cost_report.main(["--out", str(out)]) == 1
    message = capsys.readouterr().err
    assert label in message
    assert "authority block first" in message and "--diagnostic" in message
    assert not out.exists()


def test_preflight_checks_committed_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    contract, _provenance = _preflight(monkeypatch)
    monkeypatch.setattr(
        cost_report, "committed_contract", lambda: replace(contract, digest="0" * 64)
    )
    with pytest.raises(ValueError, match="budgetContractDigest"):
        cost_report.preflight()


@pytest.mark.parametrize(
    "identity",
    [
        RuntimeIdentity("CPython", "3.14.0", "/p"),
        RuntimeIdentity("PyPy", "3.14.8", "/p"),
        RuntimeUnavailable("missing"),
    ],
)
def test_preflight_probes_real_authority_child(
    monkeypatch: pytest.MonkeyPatch,
    identity: RuntimeIdentity | RuntimeUnavailable,
) -> None:
    contract, _provenance = _preflight(monkeypatch)
    calls: list[tuple[str, str]] = []

    def probe(runtime: str, namespace: str) -> RuntimeIdentity | RuntimeUnavailable:
        calls.append((runtime, namespace))
        return identity

    monkeypatch.setattr(cost_report, "probe_runtime", probe)
    with pytest.raises(ValueError, match="authority runtime CPython"):
        cost_report.preflight()
    assert calls == [(authority_minor(contract.authority), snapshot_report.ENVIRONMENT_NAMESPACE)]


@pytest.mark.usefixtures("capture_host")
def test_preflight_accepts_matching_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    _preflight(monkeypatch)
    cost_report.preflight()


def test_canonical_postgres_refusal_stops_other_members(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def runner(member: cost_report.Member, arguments: Any) -> tuple[int, str, str]:
        calls.append(member.subject)
        assert "--authority-preflight" in arguments
        return 1, "", "authority preflight refused: postgres"

    with pytest.raises(ValueError, match="postgres"):
        cost_report.collect(runner, canonical=True)
    assert calls == [cost_report.SNAPSHOT_SUBJECT]


def test_postgres_refusal_closes_before_workload(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class Port:
        def execute(self, _sql: str, _binds: Any) -> list[tuple[str]]:
            events.append("version")
            return [("other",)]

    class Provisioner:
        port = Port()

        def __init__(self) -> None:
            events.append("provision")

        def close(self) -> None:
            events.append("close")

    monkeypatch.setattr(snapshot_report, "Provisioner", Provisioner)

    def measure(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("workload ran")

    monkeypatch.setattr(snapshot_report, "measure", measure)
    with pytest.raises(ValueError, match="authority preflight refused: postgres"):
        snapshot_report._measured(  # pyright: ignore[reportPrivateUsage] - entrypoint seam
            BudgetContract.load(),
            None,
            None,
            authority_preflight=True,
        )
    assert events == ["provision", "version", "close"]


def _capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, BudgetContract]:
    current = BudgetContract.load()
    old = BudgetContract.from_bytes(
        current.path,
        current.authored.replace(str(current.authority["cpython"]).encode(), b"3.14.0", 1),
    )
    envelopes = member_envelopes(old)
    envelopes[cost_report.INSTANCE_STATE_SUBJECT] = complete_instance_state(old)
    for envelope in envelopes.values():
        provenance = _on_authority_host(Provenance.from_document(envelope["provenance"]), current)
        envelope["provenance"] = provenance.document()
        envelope["authority"] = classify_authority(provenance, old)
    collection = Collection(
        tuple(MemberResult(member, envelopes[member.subject]) for member in cost_report.MEMBERS),
        Spans(),
        {member.subject: identities() for member in cost_report.MEMBERS},
    )
    cost_report.write_portfolio(collection, tmp_path)
    monkeypatch.setattr(cost_report, "committed_contract", lambda: current)
    return tmp_path / "portfolio.json", current


def _files(root: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in root.iterdir()}


@pytest.mark.usefixtures("capture_host")
def test_reclassify_command_preserves_measurements_and_discloses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    portfolio, contract = _capture(tmp_path, monkeypatch)
    before = json.loads(portfolio.read_text())
    conditions = json.loads((tmp_path / "conditions.json").read_text())
    durations = (tmp_path / "durations.json").read_bytes()
    assert cost_report.main(["--reclassify", str(portfolio)]) == 0
    after = json.loads(portfolio.read_text())
    for old, new in zip(before["members"], after["members"], strict=True):
        assert old["readings"] == new["readings"]
        assert old["comparisons"] == new["comparisons"]
        provenance = dict(new["provenance"])
        assert provenance.pop("budgetContract") == contract.authored.decode()
        assert provenance.pop("budgetContractDigest") == contract.digest
        expected = dict(old["provenance"])
        expected.pop("budgetContract")
        expected.pop("budgetContractDigest")
        assert provenance == expected
        assert not (tmp_path / f"{new['subject']}.json").exists()
    assert after["members"][0]["authority"] == "authoritative"
    amended = json.loads((tmp_path / "conditions.json").read_text())
    assert (
        amended.pop("adjustment")["reclassified"]["contractDigest"]["reclassifiedUnder"]
        == contract.digest
    )
    assert amended == conditions
    assert (tmp_path / "durations.json").read_bytes() == durations
    assert (tmp_path / "summary.md").read_text() == cost_report._summary(  # pyright: ignore[reportPrivateUsage] - renderer seam
        after,
        Spans.load(tmp_path / "durations.json"),
    )
    gates = MemoryGates.from_bytes(
        tmp_path / "gates.yaml",
        json.dumps(
            {
                "schemaVersion": 1,
                "basis": {"portfolio": "portfolio.json", "headroom": 1.1},
                "advisory": {},
                "gates": derive_memory_gates(after, 1.1),
            }
        ).encode(),
    )
    monkeypatch.setattr(MemoryGates, "load", lambda: gates)
    capsys.readouterr()
    assert cost_report.main(["--verify", str(portfolio)]) == 0
    assert "envelopes re-classified" in capsys.readouterr().out
    assert cost_report.main(["--compare", str(portfolio), str(portfolio)]) == 0
    assert "envelopes re-classified" in capsys.readouterr().out


@pytest.mark.parametrize("change", ["unchanged", "sampling", "minor", "workload"])
def test_reclassify_refuses_contract_changes_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    portfolio, current = _capture(tmp_path, monkeypatch)
    old_text = json.loads(portfolio.read_text())["members"][0]["provenance"][
        "budgetContract"
    ].encode()
    authored = {
        "unchanged": old_text,
        "sampling": current.authored.replace(b"warmups: 3", b"warmups: 9", 1),
        "minor": current.authored.replace(str(current.authority["cpython"]).encode(), b"3.15.1", 1),
        "workload": current.authored + b"\nextra: changed\n",
    }[change]
    monkeypatch.setattr(
        cost_report, "committed_contract", lambda: BudgetContract.from_bytes(current.path, authored)
    )
    before = _files(tmp_path)
    assert cost_report.main(["--reclassify", str(portfolio)]) == 1
    assert _files(tmp_path) == before


@pytest.mark.parametrize(
    "damage",
    [
        "adjustment",
        "missing-conditions",
        "coverage",
        "digest",
        "contracts",
        "conditions",
        "durations",
        "reading",
        "comparison",
    ],
)
def test_reclassify_refuses_bad_inputs_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    portfolio, _current = _capture(tmp_path, monkeypatch)
    document = json.loads(portfolio.read_text())
    if damage == "adjustment":
        path = tmp_path / "conditions.json"
        conditions = json.loads(path.read_text())
        conditions["adjustment"] = {}
        path.write_text(json.dumps(conditions))
    elif damage == "missing-conditions":
        (tmp_path / "conditions.json").unlink()
    elif damage == "coverage":
        path = tmp_path / "conditions.json"
        conditions = json.loads(path.read_text())
        conditions["members"].pop(cost_report.WRITE_SUBJECT)
        path.write_text(json.dumps(conditions))
    elif damage in {"digest", "contracts", "reading", "comparison"}:
        member = document["members"][-1 if damage == "contracts" else 0]
        if damage == "contracts":
            provenance = Provenance.from_document(member["provenance"])
            changed = replace(provenance, budget_contract=provenance.budget_contract + "\n")
            changed = replace(
                changed,
                budget_contract_digest=hashlib.sha256(changed.budget_contract.encode()).hexdigest(),
            )
            member["provenance"] = changed.document()
        elif damage == "digest":
            member["provenance"]["budgetContractDigest"] = "0" * 64
        elif damage == "reading":
            member["readings"][0]["value"] += 1
        else:
            member["comparisons"][0]["limit"] += 1
        portfolio.write_text(json.dumps(document))
        (tmp_path / "summary.md").write_text(
            cost_report._summary(  # pyright: ignore[reportPrivateUsage] - renderer seam
                document,
                Spans.load(tmp_path / "durations.json"),
            )
        )
    else:
        (tmp_path / f"{damage}.json").write_text("{}")
    before = _files(tmp_path)
    assert cost_report.main(["--reclassify", str(portfolio)]) == 1
    assert _files(tmp_path) == before


@pytest.mark.parametrize("members", [None, {}, [], [{}], [None], "invalid"])
def test_reclassify_refuses_malformed_embedded_members_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    members: object,
) -> None:
    portfolio, _current = _capture(tmp_path, monkeypatch)
    document = json.loads(portfolio.read_text())
    document["members"] = members
    portfolio.write_text(json.dumps(document))
    before = _files(tmp_path)
    assert cost_report.main(["--reclassify", str(portfolio)]) == 1
    assert _files(tmp_path) == before


@pytest.mark.parametrize("damage", ["duplicate", "unknown"])
def test_reclassify_refuses_invalid_member_subjects_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    portfolio, _current = _capture(tmp_path, monkeypatch)
    document = json.loads(portfolio.read_text())
    if damage == "duplicate":
        document["members"].append(document["members"][0])
    else:
        document["members"][-1]["subject"] = "unknown"
    portfolio.write_text(json.dumps(document))
    before = _files(tmp_path)
    assert cost_report.main(["--reclassify", str(portfolio)]) == 1
    assert _files(tmp_path) == before


def test_reclassify_is_exclusive(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="2"):
        cost_report.main(["--reclassify", str(tmp_path), "--verify", str(tmp_path)])
    with pytest.raises(SystemExit, match="2"):
        cost_report.main(["--reclassify", str(tmp_path), "--out", str(tmp_path)])


def test_reclassify_preserves_optional_member_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio, _current = _capture(tmp_path, monkeypatch)
    document = json.loads(portfolio.read_text())
    omitted = "lifecycle-overhead"
    document["members"] = [member for member in document["members"] if member["subject"] != omitted]
    document["failures"] = [
        {
            "recipe": "python-report-lifecycle-overhead",
            "required": False,
            "message": "exit 1: unavailable",
        }
    ]
    portfolio.write_text(json.dumps(document))
    before_conditions = json.loads((tmp_path / "conditions.json").read_text())
    assert cost_report.main(["--reclassify", str(portfolio)]) == 0
    updated = json.loads(portfolio.read_text())
    assert updated["failures"] == document["failures"]
    assert [member["subject"] for member in updated["members"]] == [
        member["subject"] for member in document["members"]
    ]
    assert not (tmp_path / f"{omitted}.json").exists()
    conditions = json.loads((tmp_path / "conditions.json").read_text())
    conditions.pop("adjustment")
    assert conditions == before_conditions


RECORDED_DIGEST = "a" * 64
PRODUCING_COMMIT = "c" * 40
CODE_IDENTITY = json.dumps([256, "structural", "leaf-type"])


def _stale_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    contract = BudgetContract.load()
    current = workload_digest()
    envelopes = member_envelopes(contract)
    envelopes[cost_report.INSTANCE_STATE_SUBJECT] = complete_instance_state(contract)
    for envelope in envelopes.values():
        provenance = _on_authority_host(Provenance.from_document(envelope["provenance"]), contract)
        document = {**provenance.document(), "commit": PRODUCING_COMMIT}
        if document["workloadDigest"] == current:
            document["workloadDigest"] = RECORDED_DIGEST
        envelope["provenance"] = document
        envelope["authority"] = classify_authority(Provenance.from_document(document), contract)
    collection = Collection(
        tuple(MemberResult(member, envelopes[member.subject]) for member in cost_report.MEMBERS),
        Spans(),
        {member.subject: identities() for member in cost_report.MEMBERS},
    )
    capture = tmp_path / "capture"
    cost_report.write_portfolio(collection, capture)

    @contextlib.contextmanager
    def checkout(commit: str) -> Generator[Path]:
        assert commit == PRODUCING_COMMIT
        yield tmp_path / "checkout"

    def published(commit: str) -> bool:
        return commit == PRODUCING_COMMIT

    def unchanged_text(_commit: str, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def same_code(_workspace: Path) -> tuple[int, str, str]:
        return 0, CODE_IDENTITY, ""

    monkeypatch.setattr(cost_report, "committed_contract", lambda: contract)
    monkeypatch.setattr(cost_report, "is_published", published)
    monkeypatch.setattr(cost_report, "text_at", unchanged_text)
    monkeypatch.setattr(cost_report, "run_code_identity", same_code)
    monkeypatch.setattr(cost_report, "base_worktree", checkout)
    return capture / "portfolio.json"


@pytest.mark.usefixtures("capture_host")
def test_redigest_command_preserves_measurements_and_discloses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    portfolio = _stale_capture(tmp_path, monkeypatch)
    capture = portfolio.parent
    before = json.loads(portfolio.read_text())
    conditions = json.loads((capture / "conditions.json").read_text())
    durations = (capture / "durations.json").read_bytes()
    assert cost_report.main(["--redigest", str(portfolio)]) == 0
    after = json.loads(portfolio.read_text())
    current = workload_digest()
    amended: list[str] = []
    for old, new in zip(before["members"], after["members"], strict=True):
        if old["provenance"]["workloadDigest"] == RECORDED_DIGEST:
            amended.append(new["subject"])
            assert new["provenance"] == {**old["provenance"], "workloadDigest": current}
            assert new == {**old, "provenance": new["provenance"]}
        else:
            assert new == old
    assert sorted(amended) == [
        "instance-state",
        "lifecycle-overhead",
        cost_report.SNAPSHOT_SUBJECT,
    ]
    adjusted = json.loads((capture / "conditions.json").read_text())
    adjustment = adjusted.pop("adjustment")
    assert adjusted == conditions
    assert adjustment["schemaVersion"] == 1
    assert adjustment["redigested"] == {
        "workloadDigest": {"atCapture": RECORDED_DIGEST, "redigestedUnder": current},
        "producingCommit": PRODUCING_COMMIT,
        "members": sorted(amended),
        "unchanged": (
            "every reading, sample, comparison, and measurement condition; the measured "
            "workload inputs and code identity at the producing commit equal HEAD's"
        ),
    }
    assert (capture / "durations.json").read_bytes() == durations
    assert (capture / "summary.md").read_text() == cost_report._summary(  # pyright: ignore[reportPrivateUsage] - renderer seam
        after,
        Spans.load(capture / "durations.json"),
    )
    gates = MemoryGates.from_bytes(
        capture / "gates.yaml",
        json.dumps(
            {
                "schemaVersion": 1,
                "basis": {"portfolio": "portfolio.json", "headroom": 1.1},
                "advisory": {},
                "gates": derive_memory_gates(after, 1.1),
            }
        ).encode(),
    )
    monkeypatch.setattr(MemoryGates, "load", lambda: gates)
    capsys.readouterr()
    assert cost_report.main(["--verify", str(portfolio)]) == 0
    assert "workload digest re-stated" in capsys.readouterr().out


def _refused_without_writes(portfolio: Path) -> None:
    before = _files(portfolio.parent)
    assert cost_report.main(["--redigest", str(portfolio)]) == 1
    assert _files(portfolio.parent) == before


@pytest.mark.parametrize("damage", ["already-current", "adjustment", "commits"])
def test_redigest_refuses_inputs_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    portfolio = _stale_capture(tmp_path, monkeypatch)
    document = json.loads(portfolio.read_text())
    if damage == "already-current":
        for member in document["members"]:
            if member["provenance"]["workloadDigest"] == RECORDED_DIGEST:
                member["provenance"]["workloadDigest"] = workload_digest()
        portfolio.write_text(json.dumps(document))
    elif damage == "adjustment":
        path = portfolio.parent / "conditions.json"
        conditions = json.loads(path.read_text())
        conditions["adjustment"] = {}
        path.write_text(json.dumps(conditions))
    else:
        document["members"][-1]["provenance"]["commit"] = "d" * 40
        portfolio.write_text(json.dumps(document))
    _refused_without_writes(portfolio)


def _measured_change(_commit: str, path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("    rows: 200\n", "    rows: 201\n")


def _absent(commit: str, path: Path) -> str:
    raise ValueError(f"{path.name} does not exist at {commit[:12]}")


def _code_identity_at_commit(
    produced: tuple[int, str, str],
) -> Callable[[Path], tuple[int, str, str]]:
    def identity(workspace: Path) -> tuple[int, str, str]:
        return (0, CODE_IDENTITY, "") if workspace == cost_report.WORKSPACE else produced

    return identity


def _unavailable_checkout(_commit: str) -> contextlib.AbstractContextManager[Path]:
    raise subprocess.CalledProcessError(128, ["git", "worktree", "add"], stderr="bad revision")


def _changed_contract() -> BudgetContract:
    current = BudgetContract.load()
    return BudgetContract.from_bytes(current.path, current.authored + b"\nextra: changed\n")


def _unpublished(_commit: str) -> bool:
    return False


@pytest.mark.parametrize(
    ("seam", "fake"),
    [
        ("text_at", _measured_change),
        ("text_at", _absent),
        ("run_code_identity", _code_identity_at_commit((0, json.dumps([512, "s", "l"]), ""))),
        ("run_code_identity", _code_identity_at_commit((1, "", "no such module"))),
        ("base_worktree", _unavailable_checkout),
        ("committed_contract", _changed_contract),
        ("is_published", _unpublished),
    ],
    ids=[
        "measured-inputs",
        "absent-at-commit",
        "code-identity",
        "code-identity-fails",
        "checkout-fails",
        "contract",
        "unpublished",
    ],
)
def test_redigest_refuses_an_unproven_capture_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    seam: str,
    fake: object,
) -> None:
    portfolio = _stale_capture(tmp_path, monkeypatch)
    monkeypatch.setattr(cost_report, seam, fake)
    _refused_without_writes(portfolio)


def _code_identity_in_process(capsys: pytest.CaptureFixture[str]) -> object:
    capsys.readouterr()
    exec(cost_report.CODE_IDENTITY_PROGRAM, {})
    return json.loads(capsys.readouterr().out)


def test_the_code_identity_moves_with_a_generated_row(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    unchanged = _code_identity_in_process(capsys)
    original = workloads._orders_tree  # pyright: ignore[reportPrivateUsage] - recipe seam
    order = "parallax.compatibility.Order"

    def widened(roots: int, fanout: int) -> workloads.ScriptedRows:
        rows = original(roots, fanout)
        orders = tuple({**row, "name": f"{row['name']}0"} for row in rows.entity(order))
        return replace(rows, entities={**rows.entities, order: orders})

    monkeypatch.setattr(workloads, "_orders_tree", widened)
    assert _code_identity_in_process(capsys) != unchanged


def test_the_code_identity_moves_with_a_row_beyond_the_fixture_scale(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    unchanged = _code_identity_in_process(capsys)
    original = workloads._orders_tree  # pyright: ignore[reportPrivateUsage] - recipe seam
    order = "parallax.compatibility.Order"

    def renamed_from_root_1000(roots: int, fanout: int) -> workloads.ScriptedRows:
        rows = original(roots, fanout)
        orders = tuple(
            {**row, "name": "renamed"} if index >= 1_000 else row
            for index, row in enumerate(rows.entity(order))
        )
        return replace(rows, entities={**rows.entities, order: orders})

    monkeypatch.setattr(workloads, "_orders_tree", renamed_from_root_1000)
    assert _code_identity_in_process(capsys) != unchanged


def test_the_code_identity_moves_with_generated_fanout_metadata(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    unchanged = _code_identity_in_process(capsys)
    original = workloads._orders_tree  # pyright: ignore[reportPrivateUsage] - recipe seam

    def misreported(roots: int, fanout: int) -> workloads.ScriptedRows:
        return replace(original(roots, fanout), fanout=fanout + 1)

    monkeypatch.setattr(workloads, "_orders_tree", misreported)
    assert _code_identity_in_process(capsys) != unchanged


def test_redigest_is_exclusive(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="2"):
        cost_report.main(["--redigest", str(tmp_path), "--reclassify", str(tmp_path)])
    with pytest.raises(SystemExit, match="2"):
        cost_report.main(["--redigest", str(tmp_path), "--out", str(tmp_path)])


def test_a_source_absent_at_a_commit_has_no_text_there() -> None:
    head = cost_report.git_head()
    contract = cost_report.WORKSPACE / "spec" / "budget-contract.yaml"
    assert cost_report.text_at(head, contract) == cost_report.committed_contract().authored.decode()
    with pytest.raises(ValueError, match="does not exist at"):
        cost_report.text_at(head, cost_report.WORKSPACE / "spec" / "no-such-source.yaml")
