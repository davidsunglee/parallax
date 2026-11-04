from __future__ import annotations

import copy
import io
import json
import sys
import tarfile
import urllib.error
import zipfile
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

import release_artifacts as release
from wheel_build import matrix

type Document = dict[str, Any]


def _archive(path: Path, project: str, *, dependency: str | None = None) -> None:
    metadata = (
        f"Metadata-Version: 2.4\nName: {project}\nVersion: 0.1.0\n"
        "License-Expression: Apache-2.0\nLicense-File: LICENSE\nLicense-File: NOTICE\n"
    )
    if dependency:
        metadata += f"Requires-Dist: {dependency}\n"
    contents = {
        "LICENSE": (release.REPO / "LICENSE").read_bytes(),
        "NOTICE": b"Parallax\nCopyright 2026 David Lee\n",
    }
    if path.suffix == ".whl":
        prefix = f"{project.replace('-', '_')}-0.1.0.dist-info/"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(prefix + "METADATA", metadata)
            for name, body in contents.items():
                archive.writestr(prefix + "licenses/" + name, body)
    else:
        prefix = f"{project.replace('-', '_')}-0.1.0/"
        with tarfile.open(path, "w:gz") as archive:
            for name, body in {"PKG-INFO": metadata.encode(), **contents}.items():
                info = tarfile.TarInfo(prefix + name)
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))


@pytest.fixture
def handoff(tmp_path: Path) -> Path:
    root = tmp_path / "handoff"
    root.mkdir()
    for name in ("companions", "sdists"):
        (root / name).mkdir()
    projects = json.loads(release.CONFIG.read_text())["projects"]
    for project in projects:
        _archive(root / "sdists" / f"{project.replace('-', '_')}-0.1.0.tar.gz", project)
    companions: list[dict[str, str]] = []
    for project in [name for name in projects if name != "parallax-postgres"] + [
        "parallax-conformance"
    ]:
        path = root / "companions" / f"{project.replace('-', '_')}-0.1.0-py3-none-any.whl"
        _archive(
            path, project, dependency="parallax-core==0.1.0" if project != "parallax-core" else None
        )
        companions.append(release.identity(path))
    sdists = [release.identity(path) for path in sorted((root / "sdists").iterdir())]
    drivers = {
        name: {"status": "passed", "tests": {"passed": 10, "failed": 0, "errors": 0, "skipped": 0}}
        for name in ("binary", "c")
    }
    evidence: Document = {
        "schema_version": 1,
        "source_sha": "a" * 40,
        "run_id": "100",
        "run_attempt": 2,
        "status": "passed",
        "findings": [],
        "expected_targets": len(matrix()),
        "validated_targets": len(matrix()),
        "targets": [],
    }
    for number, target in enumerate(matrix()):
        tag = "cp" + target["python"].replace(".", "")
        path = root / f"parallax_postgres-0.1.0-{tag}-{tag}-{target['id'].replace('-', '_')}.whl"
        _archive(path, "parallax-postgres", dependency="parallax-core==0.1.0")
        evidence["targets"].append(
            {
                "source_sha": evidence["source_sha"],
                "run_id": "100",
                "run_attempt": 2,
                "target": target["id"],
                "python": target["python"],
                "status": "passed",
                "ci_job": {
                    "id": number,
                    "name": f"wheels / wheel ({target['id']}, {target['python']})",
                    "status": "completed",
                    "conclusion": "success",
                },
                "wheel": release.identity(path),
                "companions": copy.deepcopy(companions),
                "drivers": copy.deepcopy(drivers),
                "source_install": {
                    "status": "passed",
                    "sdists": sdists,
                    "wheel": release.identity(path),
                    "companions": companions,
                    "drivers": copy.deepcopy(drivers),
                },
            }
        )
    (root / "manifest.json").write_text(json.dumps(evidence))
    return root


@pytest.fixture
def bundle(handoff: Path, tmp_path: Path) -> Path:
    path = tmp_path / "bundle"
    release.freeze(handoff, path)
    return path


def _change(path: Path, mutation: Callable[[Document], None]) -> None:
    document = json.loads(path.read_text())
    mutation(document)
    path.write_text(json.dumps(document))


def test_freeze_preserves_exact_complete_set_without_publishing_conformance(
    handoff: Path, bundle: Path
) -> None:
    manifest = release.verify(bundle)
    assert len(manifest["artifacts"]) == 25
    assert len(list((bundle / "dist").iterdir())) == 25
    assert not any("conformance" in artifact["filename"] for artifact in manifest["artifacts"])
    assert (bundle / "wheel-manifest.json").read_bytes() == (handoff / "manifest.json").read_bytes()
    assert manifest["source_sha"] == "a" * 40
    assert manifest["validation_run_id"] == "100"
    assert manifest["validation_run_attempt"] == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_sha", "b" * 40),
        ("validation_run_id", "101"),
        ("validation_run_attempt", 3),
        ("schema_version", 2),
    ],
)
def test_verify_reconstructs_release_identity_from_retained_evidence(
    bundle: Path, field: str, value: object
) -> None:
    _change(bundle / "release-manifest.json", lambda document: document.update({field: value}))
    with pytest.raises(ValueError, match="retained validation evidence"):
        release.verify(bundle)


def test_verify_rejects_removal_even_when_release_manifest_is_changed_to_match(
    bundle: Path,
) -> None:
    document = json.loads((bundle / "release-manifest.json").read_text())
    removed = document["artifacts"].pop()
    (bundle / "dist" / removed["filename"]).unlink()
    (bundle / "release-manifest.json").write_text(json.dumps(document))
    with pytest.raises(ValueError, match="complete validated artifact set"):
        release.verify(bundle)


def test_verify_rejects_changed_bytes_even_when_release_hash_is_updated(bundle: Path) -> None:
    document = json.loads((bundle / "release-manifest.json").read_text())
    item = document["artifacts"][0]
    path = bundle / "dist" / item["filename"]
    with path.open("ab") as output:
        output.write(b"changed")
    item["sha256"] = release.identity(path)["sha256"]
    (bundle / "release-manifest.json").write_text(json.dumps(document))
    with pytest.raises(ValueError, match="not the validated bytes"):
        release.verify(bundle)


_INVALID_EVIDENCE: list[Callable[[Document], Any]] = [
    lambda document: document["targets"].pop(),
    lambda document: document["targets"][0].update(source_sha="b" * 40),
    lambda document: document["targets"][0].update(run_id="101"),
    lambda document: document["targets"][0].update(run_attempt=3),
    lambda document: document["targets"][0]["ci_job"].update(conclusion="failure"),
    lambda document: document["targets"][0]["drivers"]["c"]["tests"].update(skipped=1),
    lambda document: document["targets"][0]["source_install"]["drivers"].pop("binary"),
    lambda document: document["targets"][0]["source_install"]["drivers"]["binary"]["tests"].update(
        passed=0
    ),
    lambda document: document["targets"][0]["source_install"]["sdists"].pop(),
    lambda document: document["targets"][0]["companions"].pop(),
]


@pytest.mark.parametrize("mutation", _INVALID_EVIDENCE)
def test_freeze_refuses_incomplete_or_unrelated_validation(
    handoff: Path, tmp_path: Path, mutation: Callable[[Document], None]
) -> None:
    _change(handoff / "manifest.json", mutation)
    with pytest.raises(ValueError):
        release.freeze(handoff, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize(
    "dependency",
    [
        "parallax-core",
        "parallax_core>=0.1.0",
        "Parallax.Core==0.2.0; extra == 'x'",
        "parallax-conformance==0.1.0",
    ],
)
def test_artifact_rejects_unpinned_mixed_or_conformance_dependency(
    handoff: Path, tmp_path: Path, dependency: str
) -> None:
    path = handoff / "companions/parallax_snapshot-0.1.0-py3-none-any.whl"
    _archive(path, "parallax-snapshot", dependency=dependency)
    evidence = json.loads((handoff / "manifest.json").read_text())
    for cell in evidence["targets"]:
        for item in cell["companions"]:
            if item["filename"] == path.name:
                item.update(release.identity(path))
    (handoff / "manifest.json").write_text(json.dumps(evidence))
    with pytest.raises(ValueError):
        release.freeze(handoff, tmp_path / "bad-dependency")


def _index(monkeypatch: pytest.MonkeyPatch, bundle: Path, count: int) -> dict[str, list[Document]]:
    manifest = release.verify(bundle)
    entries: dict[str, list[Document]] = {}
    for artifact in manifest["artifacts"][:count]:
        entries.setdefault(artifact["project"], []).append(
            {
                "filename": artifact["filename"],
                "digests": {"sha256": artifact["sha256"]},
                "yanked": False,
                "url": f"https://files.example/{artifact['filename']}",
            }
        )

    def files(_host: str, project: str, _version: str) -> list[Document]:
        return entries.get(project, [])

    def download(url: str, **_kwargs: object) -> io.BytesIO:
        return io.BytesIO((bundle / "dist" / url.rsplit("/", 1)[1]).read_bytes())

    monkeypatch.setattr(release, "index_files", files)
    monkeypatch.setattr(release.urllib.request, "urlopen", download)
    return entries


def test_reconcile_downloads_present_bytes_and_uploads_only_missing(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _index(monkeypatch, bundle, 2)
    output = tmp_path / "reconciled"
    result = release.reconcile(bundle, "testpypi", output)
    assert result["status"] == "incomplete"
    assert len(result["downloads"]) == 2
    assert len(result["missing"]) == 23
    assert {path.name for path in (output / "missing").iterdir()} == set(result["missing"])
    for path in (output / "missing").iterdir():
        assert path.read_bytes() == (bundle / "dist" / path.name).read_bytes()


def test_reconcile_requires_all_files_before_reporting_success(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _index(monkeypatch, bundle, 24)
    with pytest.raises(ValueError, match="missing 1 artifacts"):
        release.reconcile(bundle, "pypi", tmp_path / "incomplete", require_complete=True)
    assert json.loads((tmp_path / "incomplete/index.json").read_text())["status"] == "incomplete"
    _index(monkeypatch, bundle, 25)
    result = release.reconcile(bundle, "pypi", tmp_path / "complete", require_complete=True)
    assert result["status"] == "passed"
    assert result["missing"] == []
    assert len(result["downloads"]) == 25


@pytest.mark.parametrize(
    "change,error",
    [
        ({"yanked": True}, "release is yanked"),
        ({"digests": {"sha256": "0" * 64}}, "index hash conflicts"),
        ({"filename": "unexpected.whl"}, "unexpected published file"),
        ({"url": "http://files.example/package.whl"}, "must use HTTPS"),
    ],
)
def test_reconcile_rejects_conflicts_and_yanked_or_extra_files(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: Document, error: str
) -> None:
    entries = _index(monkeypatch, bundle, 1)
    next(iter(entries.values()))[0].update(change)
    with pytest.raises(ValueError, match=error):
        release.reconcile(bundle, "pypi", tmp_path / "conflict")


def test_reconcile_rejects_downloaded_bytes_that_disagree_with_index_digest(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _index(monkeypatch, bundle, 1)

    def wrong_bytes(*_args: object, **_kwargs: object) -> io.BytesIO:
        return io.BytesIO(b"wrong")

    monkeypatch.setattr(release.urllib.request, "urlopen", wrong_bytes)
    with pytest.raises(ValueError, match="downloaded bytes conflict"):
        release.reconcile(bundle, "testpypi", tmp_path / "bad-download")


def test_index_absence_is_missing_but_access_failure_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> Any:
        raise urllib.error.HTTPError("https://example", 404, "Not Found", Message(), None)

    monkeypatch.setattr(release.urllib.request, "urlopen", fail)
    assert release.index_files("https://test.pypi.org", "parallax-core", "0.1.0") == []

    def denied(*_args: object, **_kwargs: object) -> Any:
        raise urllib.error.HTTPError("https://example", 403, "Forbidden", Message(), None)

    monkeypatch.setattr(release.urllib.request, "urlopen", denied)
    with pytest.raises(urllib.error.HTTPError):
        release.index_files("https://test.pypi.org", "parallax-core", "0.1.0")


def test_reconcile_cli_retries_incomplete_sets_and_reports_actual_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def reconcile(_bundle: Path, _index: str, output: Path) -> Document:
        calls.append(output)
        return {"status": "passed" if len(calls) == 2 else "incomplete", "missing": []}

    def wait(seconds: float) -> None:
        assert seconds == 15

    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(release, "reconcile", reconcile)
    monkeypatch.setattr(release.time, "sleep", wait)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_artifacts.py",
            "reconcile",
            "--bundle",
            str(tmp_path / "bundle"),
            "--index",
            "testpypi",
            "--output",
            str(tmp_path / "checks"),
            "--attempts",
            "2",
            "--require-complete",
        ],
    )
    release.main()
    assert calls == [tmp_path / "checks/0", tmp_path / "checks/1"]
    assert output.read_text().splitlines() == [
        f"missing={tmp_path / 'checks/1/missing'}",
        f"downloaded={tmp_path / 'checks/1/downloaded'}",
        "missing_count=0",
    ]


def test_reconcile_cli_exhaustion_never_emits_success_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def incomplete(_bundle: Path, _index: str, _output: Path) -> Document:
        return {"status": "incomplete", "missing": ["missing.whl"]}

    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(release, "reconcile", incomplete)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_artifacts.py",
            "reconcile",
            "--bundle",
            str(tmp_path / "bundle"),
            "--index",
            "testpypi",
            "--output",
            str(tmp_path / "checks"),
            "--require-complete",
        ],
    )
    with pytest.raises(ValueError, match="complete release not visible"):
        release.main()
    assert not output.exists()
