from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Generator, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType
from typing import Any, Final, cast

import pytest

import cost_report
import snapshot_delivery_overhead as snapshot_report
from cost_report import Collection, MemberResult
from durations import Spans
from interpreter_matrix import CURRENT_MINOR, RuntimeIdentity, RuntimeUnavailable, authority_minor
from parallax.conformance import cost_envelope, workloads
from parallax.conformance.budget import BudgetContract, MemoryGates, derive_memory_gates
from parallax.conformance.cost_envelope import Provenance, classify_authority
from parallax.conformance.workloads import workload_digest
from tests.unit._workload_digest_support import FEATURE_SOURCE, WRITE_SOURCES
from tests.unit.tools._cost_report_support import (
    canary_provenance,
    complete_instance_state,
    identities,
    member_envelopes,
)
from tests.unit.tools._redigest_support import assert_redigest_preserved, capture_files


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


_ORIGINS: Final = (
    (
        "parallax.core.internal.entity._row_fill",
        "packages/parallax-core/src/parallax/core/internal/entity/_row_fill.py",
    ),
)


def _preflight(monkeypatch: pytest.MonkeyPatch) -> tuple[BudgetContract, Provenance]:
    contract = BudgetContract.load()
    provenance = _on_authority_host(canary_provenance(contract), contract)
    monkeypatch.setattr(cost_report, "committed_contract", lambda: contract)

    def probe(_runtime: str, _namespace: str) -> RuntimeIdentity:
        return RuntimeIdentity("CPython", str(contract.authority["cpython"]), "/p", _ORIGINS)

    def capture(*_args: Any, **_kwargs: Any) -> Provenance:
        return provenance

    def import_child(
        _command: Sequence[str], _environment: Mapping[str, str]
    ) -> tuple[int, str, str]:
        return 0, "", ""

    monkeypatch.setattr(cost_report, "probe_runtime", probe)
    monkeypatch.setattr(cost_report, "run_probe", import_child)
    monkeypatch.setattr(cost_report, "stale_extensions", tuple)
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


def test_preflight_refuses_a_failed_other_minor_reading_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _preflight(monkeypatch)
    checked: list[tuple[str, str]] = []

    def import_child(
        command: Sequence[str], _environment: Mapping[str, str]
    ) -> tuple[int, str, str]:
        runtime = command[command.index("--python") + 1] if "--python" in command else CURRENT_MINOR
        namespace = (
            "write-lowering" if "write_lowering_reading" in command[-1] else "snapshot-delivery"
        )
        checked.append((runtime, namespace))
        if runtime == "3.14" and namespace == "write-lowering":
            return 1, "", "ModuleNotFoundError: No module named 'parallax'"
        return 0, "", ""

    monkeypatch.setattr(cost_report, "run_probe", import_child)
    with pytest.raises(ValueError, match=r"CPython 3\.14 write-lowering child import failed"):
        cost_report.preflight()
    assert len(checked) == 4


def test_shard_preflights_children_and_places_journal_inside_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = tmp_path / "reports"
    shard = cost_report.plan_ids("sharded")[0]
    events: list[str] = []

    def shard_request(*_args: object) -> cost_report.Request:
        return cast("cost_report.Request", object())

    def validate_plan(_plan: Sequence[cost_report.Shard]) -> None:
        pass

    monkeypatch.setattr(cost_report, "_shard_request", shard_request)
    monkeypatch.setattr(cost_report, "validate_plan", validate_plan)

    def preflight_children() -> list[str]:
        events.append("preflight")
        return []

    def run_shards(*_args: object) -> int:
        events.append("measure")
        assert os.environ["PARALLAX_CAPTURE_JOURNAL"] == str(out / "checkpoints")
        assert Path(os.environ["TMPDIR"]).is_dir()
        return 0

    monkeypatch.setattr(cost_report, "_child_import_mismatches", preflight_children)
    monkeypatch.setattr(cost_report, "run_shards", run_shards)
    assert cost_report.main(["--shard", shard, "--out", str(out)]) == 0
    assert events == ["preflight", "measure"]


def test_complete_member_journal_tracks_actual_other_minor_and_support_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PARALLAX_CAPTURE_JOURNAL", str(tmp_path))
    patch = 10

    def probe(runtime: str, _namespace: str) -> RuntimeIdentity:
        return RuntimeIdentity("CPython", f"{runtime}.{patch}", "/temporary/python", _ORIGINS)

    monkeypatch.setattr(cost_report, "probe_runtime", probe)
    first = cost_report._member_journal()  # pyright: ignore[reportPrivateUsage] - journal seam
    first.store({"member": "instance-state"}, {"value": 1})
    document = json.loads(next(tmp_path.rglob("*.json")).read_bytes())
    assert "tests/_support/db_port.py" in document["identity"]["sources"]
    assert "tests/_support/document_reads.py" in document["identity"]["sources"]
    patch = 11
    second = cost_report._member_journal()  # pyright: ignore[reportPrivateUsage] - journal seam
    assert second.load({"member": "instance-state"}) is None


def test_import_preflight_executes_deferred_snapshot_workloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DeferredFailure(ModuleType):
        def __getattribute__(self, name: str) -> object:
            if name == "__dict__":
                raise ImportError("deferred model failed")
            return super().__getattribute__(name)

    for name in ("snapshot_delivery_reading", "write_lowering_reading"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    for name in (
        "_delivery_control_support",
        "_scalar_type_support",
        "_snapshot_materialization_support",
        "_structural_geometry_support",
    ):
        qualified = f"tests.unit.{name}"
        monkeypatch.setitem(sys.modules, qualified, DeferredFailure(qualified))

    def execute(command: Sequence[str], _environment: Mapping[str, str]) -> tuple[int, str, str]:
        try:
            exec(command[-1], {})
        except ImportError as error:
            return 1, "", str(error)
        return 0, "", ""

    monkeypatch.setattr(cost_report, "run_probe", execute)
    failures = cost_report._child_import_mismatches()  # pyright: ignore[reportPrivateUsage] - preflight seam
    assert len(failures) == 4
    assert all("deferred model failed" in failure for failure in failures)


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


def test_preflight_refuses_a_probe_that_records_no_production_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract, _provenance = _preflight(monkeypatch)

    def probe(_runtime: str, _namespace: str) -> RuntimeIdentity:
        return RuntimeIdentity("CPython", str(contract.authority["cpython"]), "/p")

    monkeypatch.setattr(cost_report, "probe_runtime", probe)
    with pytest.raises(ValueError, match="the probe recorded no production origins"):
        cost_report.preflight()


def test_preflight_refuses_a_stale_extension_beside_a_production_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _preflight(monkeypatch)
    stale = Path(
        "packages/parallax-core/src/parallax/core/internal/entity/_row_fill.cpython-314-darwin.so"
    )
    monkeypatch.setattr(cost_report, "stale_extensions", lambda: (stale,))
    with pytest.raises(ValueError, match=re.escape(f"stale extension: {stale}")):
        cost_report.preflight()


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
        current.authored.replace(
            str(current.authority["cpython"]).encode(),
            f"{authority_minor(current.authority)}.0".encode(),
            1,
        ),
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
        "minor": current.authored.replace(str(current.authority["cpython"]).encode(), b"9.99.1", 1),
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


PRODUCING_COMMIT: Final = "c" * 40
CODE_IDENTITY: Final = json.dumps([256, "1" * 64, "2" * 64, {"conventional-fanout@32": "3" * 64}])
PROOFS: Final = {proof.family: proof for proof in cost_report.DIGEST_PROOFS}
FAMILIES: Final = tuple(PROOFS)


class _WithoutProse(ast.NodeTransformer):
    def visit_Expr(self, node: ast.Expr) -> ast.AST | None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return self.generic_visit(node)


def _imports_retained(source: str, omitted: frozenset[str]) -> bytes:
    tree = ast.parse(source)
    tree.body = [
        node
        for node in tree.body
        if not (isinstance(node, ast.FunctionDef) and node.name in omitted)
    ]
    return ast.dump(_WithoutProse().visit(tree), include_attributes=False).encode("utf-8")


type SourceText = Callable[[Path], str]


def _producing_snapshot_digest(text: SourceText, monkeypatch: pytest.MonkeyPatch) -> str:
    """The shared digest as producing code that hashed the live-read source's
    whole syntax tree computed it."""

    def whole_tree(source: str) -> bytes:
        return ast.dump(ast.parse(source), include_attributes=False).encode("utf-8")

    with monkeypatch.context() as patched:
        patched.setattr(workloads, "canonical_source", whole_tree)
        return workload_digest(read=text)


def _producing_write_digest(text: SourceText, manifests: list[str], *, legacy: bool) -> str:
    """The write-lowering digest as producing code that kept import statements
    computed it, or under ``legacy`` hashed three sources' raw text."""
    sources = [text(cost_report.WORKSPACE / relative) for relative in WRITE_SOURCES]
    digest = hashlib.sha256()
    for index, source in enumerate(sources[:3] if legacy else sources):
        omitted = frozenset({"write_lowering_digest"}) if index == 0 else frozenset[str]()
        digest.update(source.encode("utf-8") if legacy else _imports_retained(source, omitted))
        digest.update(b"\0")
    for manifest in manifests:
        digest.update(manifest.encode("utf-8"))
    return digest.hexdigest()


def _producing_feature_digest(text: SourceText) -> str:
    """The feature-boundary digest as producing code that hashed its raw source computed it."""
    return hashlib.sha256(text(cost_report.WORKSPACE / FEATURE_SOURCE).encode("utf-8")).hexdigest()


def _moved_imports(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".py":
        return text
    return f'{text}\n"""Prose the producing commit carried."""\nimport os.path\n'


@dataclass(frozen=True, slots=True)
class _StaleCapture:
    portfolio: Path
    restated: dict[str, str]
    producing: dict[str, str]

    def files(self) -> dict[str, bytes]:
        return capture_files(self.portfolio.parent)


def _stale_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    stale: tuple[str, ...] = FAMILIES,
    text: SourceText = _moved_imports,
    legacy_write: bool = False,
) -> _StaleCapture:
    """A capture at :data:`PRODUCING_COMMIT` whose ``stale`` families record the
    digest their producing code gave the commit's sources, ``text``; the other
    families record HEAD's digest."""
    contract = BudgetContract.load()
    manifests = [workloads.structural_digest(), workloads.scalar_type_digest()]
    producing = {
        "Snapshot": _producing_snapshot_digest(text, monkeypatch),
        "write-lowering": _producing_write_digest(text, manifests, legacy=legacy_write),
        "feature-boundary": _producing_feature_digest(text),
    }
    envelopes = member_envelopes(contract)
    envelopes[cost_report.INSTANCE_STATE_SUBJECT] = complete_instance_state(contract)
    restated: dict[str, str] = {}
    for subject, envelope in envelopes.items():
        (proof,) = (proof for proof in cost_report.DIGEST_PROOFS if subject in proof.subjects)
        provenance = _on_authority_host(Provenance.from_document(envelope["provenance"]), contract)
        document = {**provenance.document(), "commit": PRODUCING_COMMIT}
        document["workloadDigest"] = proof.current()
        if proof.family in stale:
            restated[subject] = document["workloadDigest"]
            document["workloadDigest"] = producing[proof.family]
        envelope["provenance"] = document
        envelope["authority"] = classify_authority(Provenance.from_document(document), contract)
    collection = Collection(
        tuple(MemberResult(member, envelopes[member.subject]) for member in cost_report.MEMBERS),
        Spans(),
        {member.subject: identities() for member in cost_report.MEMBERS},
    )
    capture = tmp_path / "capture"
    cost_report.write_portfolio(collection, capture)
    _record_producing_sources(capture / cost_report.CONDITIONS_FILE, text)
    monkeypatch.setattr(cost_report, "committed_contract", lambda: contract)
    _produce_at_commit(tmp_path / "checkout", monkeypatch, text, producing, manifests)
    return _StaleCapture(capture / "portfolio.json", restated, producing)


def _record_producing_sources(path: Path, text: SourceText) -> None:
    conditions = json.loads(path.read_text())
    for subject, relatives in (
        (cost_report.WRITE_SUBJECT, WRITE_SOURCES),
        (cost_report.FEATURE_SUBJECT, (FEATURE_SOURCE,)),
    ):
        for relative in relatives:
            source = text(cost_report.WORKSPACE / relative).encode("utf-8")
            conditions["members"][subject]["sources"][relative] = hashlib.sha256(source).hexdigest()
    path.write_text(json.dumps(conditions))


def _produce_at_commit(
    checkout_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    text: SourceText,
    producing: Mapping[str, str],
    manifests: list[str],
) -> None:
    """Resolve :data:`PRODUCING_COMMIT` to sources ``text`` and a checkout whose
    digest code answers ``producing``, by family, and its frozen ``manifests``."""
    produced = {PROOFS[family].digest_program: digest for family, digest in producing.items()}

    def run(workspace: Path, program: str) -> tuple[int, str, str]:
        if program == cost_report.CODE_IDENTITY_PROGRAM:
            return 0, CODE_IDENTITY, ""
        assert workspace == checkout_root / "languages" / "python"
        if program == cost_report.FROZEN_MANIFESTS_PROGRAM:
            return 0, json.dumps(manifests), ""
        return 0, f"collected\n{json.dumps(produced[program])}\n", ""

    @contextlib.contextmanager
    def checkout(commit: str) -> Generator[Path]:
        assert commit == PRODUCING_COMMIT
        yield checkout_root

    def published(commit: str) -> bool:
        return commit == PRODUCING_COMMIT

    def text_at(_commit: str, path: Path) -> str:
        return text(path)

    monkeypatch.setattr(cost_report, "is_published", published)
    monkeypatch.setattr(cost_report, "text_at", text_at)
    monkeypatch.setattr(cost_report, "run_frozen_program", run)
    monkeypatch.setattr(cost_report, "base_worktree", checkout)


def _verified_after_restatement(
    capture: _StaleCapture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    after = json.loads(capture.portfolio.read_text())
    gates = MemoryGates.from_bytes(
        capture.portfolio.parent / "gates.yaml",
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
    assert cost_report.main(["--verify", str(capture.portfolio)]) == 0
    assert "workload digest re-stated" in capsys.readouterr().out


UNCHANGED_STATEMENT: Final = (
    "every reading, sample, comparison, and measurement condition; the producing "
    "commit's own digest code reproduces each recorded digest, and HEAD's digest "
    "code finds the producing commit's measured inputs equal to HEAD's"
)


@pytest.mark.usefixtures("capture_host")
def test_redigest_restates_every_stale_family_in_one_disclosed_adjustment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch)
    before = capture.files()
    assert cost_report.main(["--redigest", str(capture.portfolio)]) == 0
    assert sorted(capture.restated) == sorted(member.subject for member in cost_report.MEMBERS)
    assert_redigest_preserved(before, capture.portfolio.parent, capture.restated)
    adjustment = json.loads((capture.portfolio.parent / "conditions.json").read_text())[
        "adjustment"
    ]["redigested"]
    assert adjustment == {
        "workloadDigests": sorted(
            (
                {
                    "members": sorted(PROOFS[family].subjects),
                    "atCapture": capture.producing[family],
                    "redigestedUnder": PROOFS[family].current(),
                }
                for family in FAMILIES
            ),
            key=lambda change: (change["atCapture"], change["redigestedUnder"]),
        ),
        "producingCommit": PRODUCING_COMMIT,
        "members": sorted(capture.restated),
        "unchanged": UNCHANGED_STATEMENT,
    }
    _verified_after_restatement(capture, monkeypatch, capsys)


@pytest.mark.parametrize("family", FAMILIES)
def test_redigest_restates_only_the_stale_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, family: str
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch, stale=(family,))
    before = capture.files()
    assert cost_report.main(["--redigest", str(capture.portfolio)]) == 0
    assert set(capture.restated) == PROOFS[family].subjects
    assert_redigest_preserved(before, capture.portfolio.parent, capture.restated)
    adjustment = json.loads((capture.portfolio.parent / "conditions.json").read_text())[
        "adjustment"
    ]["redigested"]
    assert adjustment["workloadDigest"] == {
        "atCapture": capture.producing[family],
        "redigestedUnder": PROOFS[family].current(),
    }
    assert adjustment["producingCommit"] == PRODUCING_COMMIT


def test_redigest_trusts_the_producing_codes_own_legacy_write_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch, stale=("write-lowering",), legacy_write=True)
    before = capture.files()
    assert cost_report.main(["--redigest", str(capture.portfolio)]) == 0
    assert_redigest_preserved(before, capture.portfolio.parent, capture.restated)


def test_redigest_accepts_a_rebased_producer_for_source_families_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch, stale=("write-lowering", "feature-boundary"))
    monkeypatch.setattr(cost_report, "is_published", _unpublished)
    before = capture.files()
    assert cost_report.main(["--redigest", str(capture.portfolio)]) == 0
    assert_redigest_preserved(before, capture.portfolio.parent, capture.restated)


TREE_TWIN: Final = "d" * 40


def _tree_twin_of_producer(commit: str) -> str | None:
    assert commit == PRODUCING_COMMIT
    return TREE_TWIN


def _no_tree_twin(_commit: str) -> str | None:
    return None


def test_redigest_accepts_a_snapshot_producer_whose_tree_an_ancestor_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch)
    monkeypatch.setattr(cost_report, "is_published", _unpublished)
    monkeypatch.setattr(cost_report, "tree_twin", _tree_twin_of_producer)
    before = capture.files()
    assert cost_report.main(["--redigest", str(capture.portfolio)]) == 0
    assert_redigest_preserved(before, capture.portfolio.parent, capture.restated)
    adjustment = json.loads((capture.portfolio.parent / "conditions.json").read_text())[
        "adjustment"
    ]["redigested"]
    assert adjustment["producingCommit"] == PRODUCING_COMMIT
    assert adjustment["treeIdenticalAncestor"] == TREE_TWIN


def test_redigest_refuses_a_snapshot_producer_no_ancestor_shares_a_tree_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch)
    monkeypatch.setattr(cost_report, "is_published", _unpublished)
    monkeypatch.setattr(cost_report, "tree_twin", _no_tree_twin)
    _refused_without_writes(
        capture,
        capsys,
        f"c{{12}} is not an ancestor of HEAD, and none of HEAD's nearest "
        f"{cost_report.TREE_SEARCH_DEPTH} ancestors has its tree",
    )


def _git(repo: Path, *arguments: str, stdin: str | None = None) -> str:
    environment = {
        "GIT_AUTHOR_NAME": "Parallax",
        "GIT_AUTHOR_EMAIL": "parallax@example.invalid",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
        "GIT_COMMITTER_NAME": "Parallax",
        "GIT_COMMITTER_EMAIL": "parallax@example.invalid",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "PATH": os.environ["PATH"],
    }
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        input=stdin,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, content: str, message: str) -> str:
    (repo / "measured.txt").write_text(content)
    _git(repo, "add", "measured.txt")
    _git(repo, "commit", "--quiet", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_a_tree_twin_is_the_newest_bounded_ancestor_holding_the_same_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet", "--initial-branch=main")
    first = _commit(repo, "measured\n", "first")
    reviewed = _commit(repo, "reviewed\n", "reviewed")
    _commit(repo, "later\n", "later")
    rebased = _git(repo, "commit-tree", f"{reviewed}^{{tree}}", "-p", first, "-m", "branch")
    unmerged_tree = _git(repo, "mktree", stdin="")
    unmerged = _git(repo, "commit-tree", unmerged_tree, "-p", first, "-m", "unmerged")
    monkeypatch.setattr(cost_report, "WORKSPACE", repo)
    assert cost_report.tree_twin(rebased) == reviewed
    assert cost_report.tree_twin(unmerged) is None
    assert cost_report.tree_twin("0" * 40) is None
    monkeypatch.setattr(cost_report, "TREE_SEARCH_DEPTH", 1)
    assert cost_report.tree_twin(rebased) is None


def _refused_without_writes(
    capture: _StaleCapture, capsys: pytest.CaptureFixture[str], reason: str
) -> None:
    before = _files(capture.portfolio.parent)
    capsys.readouterr()
    assert cost_report.main(["--redigest", str(capture.portfolio)]) == 1
    assert re.search(f"^redigest refused: .*{reason}", capsys.readouterr().err, re.MULTILINE)
    assert _files(capture.portfolio.parent) == before


def _rewrite_members(capture: _StaleCapture, edit: Callable[[dict[str, Any]], None]) -> None:
    document = json.loads(capture.portfolio.read_text())
    for member in document["members"]:
        edit(member)
    capture.portfolio.write_text(json.dumps(document))


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        ("already-current", "already HEAD's"),
        ("adjustment", "already records an adjustment"),
        ("commits", "different producing commits"),
        ("split-family", "Snapshot members record different workload digests"),
        ("no-snapshot", "no single snapshot-delivery member"),
    ],
)
def test_redigest_refuses_inputs_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    damage: str,
    reason: str,
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch)

    def current(member: dict[str, Any]) -> None:
        member["provenance"]["workloadDigest"] = capture.restated[member["subject"]]

    def split(member: dict[str, Any]) -> None:
        if member["subject"] == cost_report.LIFECYCLE_SUBJECT:
            member["provenance"]["workloadDigest"] = "e" * 64

    if damage == "already-current":
        _rewrite_members(capture, current)
    elif damage == "adjustment":
        path = capture.portfolio.parent / "conditions.json"
        conditions = json.loads(path.read_text())
        conditions["adjustment"] = {}
        path.write_text(json.dumps(conditions))
    elif damage == "commits":
        document = json.loads(capture.portfolio.read_text())
        document["members"][-1]["provenance"]["commit"] = "d" * 40
        capture.portfolio.write_text(json.dumps(document))
    elif damage == "split-family":
        _rewrite_members(capture, split)
    else:
        document = json.loads(capture.portfolio.read_text())
        document["members"] = [
            member
            for member in document["members"]
            if member["subject"] != cost_report.SNAPSHOT_SUBJECT
        ]
        capture.portfolio.write_text(json.dumps(document))
    _refused_without_writes(capture, capsys, reason)


def _measured_change(_commit: str, path: Path) -> str:
    return _moved_imports(path).replace("    rows: 200\n", "    rows: 201\n")


def _absent(commit: str, path: Path) -> str:
    raise ValueError(f"{path.name} does not exist at {commit[:12]}")


def _unavailable_checkout(_commit: str) -> contextlib.AbstractContextManager[Path]:
    raise subprocess.CalledProcessError(128, ["git", "worktree", "add"], stderr="bad revision")


def _changed_contract() -> BudgetContract:
    current = BudgetContract.load()
    return BudgetContract.from_bytes(current.path, current.authored + b"\nextra: changed\n")


def _unpublished(_commit: str) -> bool:
    return False


@pytest.mark.parametrize(
    ("seam", "fake", "reason"),
    [
        ("text_at", _measured_change, "Snapshot workload inputs at c{12} differ from HEAD's"),
        ("text_at", _absent, "does not exist at c{12}"),
        ("base_worktree", _unavailable_checkout, "git could not check out c{12}"),
        ("committed_contract", _changed_contract, "Budget Contract other than HEAD's"),
        ("is_published", _unpublished, "c{12} is not an ancestor of HEAD"),
    ],
    ids=["measured-inputs", "absent-at-commit", "checkout-fails", "contract", "unpublished"],
)
def test_redigest_refuses_an_unproven_capture_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    seam: str,
    fake: object,
    reason: str,
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch)
    monkeypatch.setattr(cost_report, seam, fake)
    _refused_without_writes(capture, capsys, reason)


def _answering(
    monkeypatch: pytest.MonkeyPatch, program: str, answer: tuple[int, str, str], *, head: bool
) -> None:
    """Replace what ``program`` answers in the producing checkout, and at HEAD
    too under ``head``."""
    produced = cost_report.run_frozen_program

    def run(workspace: Path, ran: str) -> tuple[int, str, str]:
        if ran == program and (head or workspace != cost_report.WORKSPACE):
            return answer
        return produced(workspace, ran)

    monkeypatch.setattr(cost_report, "run_frozen_program", run)


@pytest.mark.parametrize("family", FAMILIES)
def test_redigest_refuses_producing_code_that_does_not_reproduce_the_recorded_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], family: str
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch)
    _answering(
        monkeypatch, PROOFS[family].digest_program, (0, json.dumps("f" * 64), ""), head=False
    )
    _refused_without_writes(
        capture, capsys, f"{family} digest code at c{{12}} does not reproduce the recorded digest"
    )


def test_redigest_refuses_workload_code_whose_identity_differs_from_heads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch)
    changed = json.dumps([512, "1" * 64, "2" * 64, {"conventional-fanout@32": "3" * 64}])
    _answering(monkeypatch, cost_report.CODE_IDENTITY_PROGRAM, (0, changed, ""), head=False)
    _refused_without_writes(capture, capsys, "workload code at the producing commit differs")


_MALFORMED_OUTPUTS: Final = (
    (1, "", "no such module"),
    (0, "", ""),
    (0, "not JSON", ""),
    (0, "null", ""),
    (0, "17", ""),
    (0, json.dumps({"digest": "a" * 64}), ""),
    (0, json.dumps("A" * 64), ""),
    (0, json.dumps("a" * 63), ""),
    (0, json.dumps(["a" * 64]), ""),
    (0, json.dumps([256, "1" * 64, "2" * 64]), ""),
    (0, json.dumps([True, "1" * 64, "2" * 64, {}]), ""),
    (0, json.dumps([256, "1" * 64, "2" * 64, {"workload@1": "short"}]), ""),
    (0, json.dumps(["1" * 64, "2" * 64, "3" * 64]), ""),
    (0, json.dumps(["1" * 64, 2]), ""),
)


@pytest.mark.parametrize("output", _MALFORMED_OUTPUTS)
@pytest.mark.parametrize(
    "program",
    [
        *FAMILIES,
        "code identity",
        "frozen manifests",
    ],
)
def test_redigest_refuses_malformed_program_output_even_where_both_sides_agree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    program: str,
    output: tuple[int, str, str],
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch)
    source, reason = {
        "code identity": (cost_report.CODE_IDENTITY_PROGRAM, "the code identity at"),
        "frozen manifests": (
            cost_report.FROZEN_MANIFESTS_PROGRAM,
            "the write-lowering frozen manifests",
        ),
    }.get(program) or (PROOFS[program].digest_program, f"the {program} digest code at")
    _answering(monkeypatch, source, output, head=True)
    _refused_without_writes(capture, capsys, reason)


def _edited(path_name: str, old: str, new: str) -> SourceText:
    def text(path: Path) -> str:
        source = _moved_imports(path)
        if path.name != path_name:
            return source
        assert old in source
        return source.replace(old, new, 1)

    return text


@pytest.mark.parametrize(
    ("family", "text"),
    [
        (
            "Snapshot",
            _edited("live_read_workloads.py", "dt.datetime(2024, 5, 1", "dt.datetime(2024, 8, 1"),
        ),
        ("write-lowering", _edited("_workload_spelling_support.py", '"read-"', '"changed-"')),
        (
            "write-lowering",
            _edited(
                "_write_lowering_support.py", "_NULL_EVERY: Final = 4", "_NULL_EVERY: Final = 5"
            ),
        ),
        (
            "feature-boundary",
            _edited(
                "_feature_boundary_support.py", '"workload_digest"]', '"feature_boundary_digest"]'
            ),
        ),
        ("feature-boundary", _edited("_feature_boundary_support.py", "(0, 8, 128)", "(0, 8, 64)")),
    ],
    ids=[
        "live-read-coordinate",
        "write-literal",
        "write-constant",
        "feature-export",
        "feature-size",
    ],
)
def test_redigest_refuses_a_producing_commit_whose_retained_syntax_differs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    family: str,
    text: SourceText,
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch, stale=(family,), text=text)
    _refused_without_writes(capture, capsys, f"{family} workload inputs at c{{12}} differ")


@pytest.mark.parametrize(
    ("family", "subject", "relative"),
    [
        ("write-lowering", "write-lowering", WRITE_SOURCES[3]),
        ("feature-boundary", "feature-boundary", FEATURE_SOURCE),
    ],
)
@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        ("differs", "captured .+ source .+ differs at c{12}"),
        ("missing", "captured .+ source .+ differs at c{12}"),
        ("dirty", "capture names a dirty producing tree"),
    ],
)
def test_redigest_refuses_source_family_provenance_it_cannot_prove_from(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    family: str,
    subject: str,
    relative: str,
    damage: str,
    reason: str,
) -> None:
    capture = _stale_capture(tmp_path, monkeypatch, stale=(family,))
    if damage == "dirty":

        def dirty(member: dict[str, Any]) -> None:
            if member["subject"] == subject:
                member["provenance"]["dirty"] = True

        _rewrite_members(capture, dirty)
    else:
        path = capture.portfolio.parent / "conditions.json"
        conditions = json.loads(path.read_text())
        sources = conditions["members"][subject]["sources"]
        if damage == "differs":
            sources[relative] = "0" * 64
        else:
            sources.pop(relative)
        path.write_text(json.dumps(conditions))
    _refused_without_writes(capture, capsys, reason)


@pytest.mark.parametrize("family", FAMILIES)
def test_each_digest_program_answers_its_checkouts_own_digest(
    family: str, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    exec(PROOFS[family].digest_program, {})
    assert json.loads(capsys.readouterr().out) == PROOFS[family].current()


def test_the_frozen_manifests_program_answers_its_checkouts_manifests(
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsys.readouterr()
    exec(cost_report.FROZEN_MANIFESTS_PROGRAM, {})
    assert json.loads(capsys.readouterr().out) == [
        workloads.structural_digest(),
        workloads.scalar_type_digest(),
    ]


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
