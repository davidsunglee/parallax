"""Freeze validated release bytes and reconcile indexes without replacing files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from email.message import Message
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from wheel_build import release_matrix

REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / ".github/release/configuration.json"
INDEXES = {"testpypi": "https://test.pypi.org", "pypi": "https://pypi.org"}
type Document = dict[str, Any]


def identity(path: Path) -> dict[str, str]:
    return {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _metadata(path: Path) -> Message:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            candidates = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            if len(candidates) != 1:
                raise ValueError(f"{path.name}: expected one METADATA")
            raw = archive.read(candidates[0])
            prefix = candidates[0].removesuffix("METADATA") + "licenses/"
            legal = {name: archive.read(prefix + name) for name in ("LICENSE", "NOTICE")}
    else:
        with tarfile.open(path) as archive:
            candidates = [
                n for n in archive.getnames() if n.count("/") == 1 and n.endswith("/PKG-INFO")
            ]
            if len(candidates) != 1:
                raise ValueError(f"{path.name}: expected one root PKG-INFO")
            prefix = candidates[0].removesuffix("PKG-INFO")
            contents: dict[str, bytes] = {}
            for name in ("PKG-INFO", "LICENSE", "NOTICE"):
                member = archive.getmember(prefix + name)
                if not member.isfile():
                    raise ValueError(f"{path.name}: {name} must be a regular file")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError(f"{path.name}: missing {name}")
                contents[name] = stream.read()
            raw = contents["PKG-INFO"]
            legal = {name: contents[name] for name in ("LICENSE", "NOTICE")}
    metadata = BytesParser().parsebytes(raw)
    if metadata["License-Expression"] != "Apache-2.0" or set(
        metadata.get_all("License-File", [])
    ) != {"LICENSE", "NOTICE"}:
        raise ValueError(f"{path.name}: expected Apache-2.0 licence and declared legal files")
    if (
        legal["LICENSE"].replace(b"\r\n", b"\n")
        != (REPO / "LICENSE").read_bytes().replace(b"\r\n", b"\n")
        or not legal["NOTICE"].strip()
    ):
        raise ValueError(f"{path.name}: invalid licence or empty notice")
    return metadata


def _artifact(path: Path, version: str, projects: set[str]) -> dict[str, str]:
    metadata = _metadata(path)
    name = metadata["Name"]
    if name not in projects or metadata["Version"] != version:
        raise ValueError(f"{path.name}: unexpected distribution/version")
    prefix = f"{name.replace('-', '_')}-{version}"
    suffix = path.name.removeprefix(prefix)
    if not path.name.startswith(prefix) or not (
        suffix == ".tar.gz" or (path.suffix == ".whl" and suffix.startswith("-"))
    ):
        raise ValueError(f"{path.name}: filename differs from distribution metadata")
    for requirement in metadata.get_all("Requires-Dist", []):
        match = re.fullmatch(r"\s*([\w.-]+)(?:\[[^]]+\])?\s*(.*)", requirement)
        if match is None:
            raise ValueError(f"{path.name}: malformed dependency {requirement!r}")
        dependency = _normalize(match[1])
        if dependency == "parallax-conformance":
            raise ValueError("production artifacts must not depend on conformance")
        if dependency in projects:
            constraint = match[2].split(";")[0].strip()
            if constraint.startswith("(") and constraint.endswith(")"):
                constraint = constraint[1:-1].strip()
            if constraint != f"=={version}":
                raise ValueError(f"{path.name}: first-party dependency must match exactly")
    return {
        **identity(path),
        "project": name,
        "version": version,
        "kind": "wheel" if path.suffix == ".whl" else "sdist",
    }


def _identities(items: Sequence[Document], projects: set[str], extension: str) -> dict[str, str]:
    result: dict[str, str] = {}
    names: list[str] = []
    for item in items:
        filename, digest = item["filename"], item["sha256"]
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or not filename.endswith(extension)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or filename in result
        ):
            raise ValueError("invalid or duplicate validated artifact identity")
        names.append(_normalize(filename.split("-", 1)[0]))
        result[filename] = digest
    if len(names) != len(projects) or set(names) != projects:
        raise ValueError("validated artifact identities differ from required distributions")
    return result


def _drivers(proof: Document) -> None:
    if set(proof["drivers"]) != {"binary", "c"}:
        raise ValueError("both driver proofs are required")
    for result in proof["drivers"].values():
        counts = result["tests"]
        if (
            result["status"] != "passed"
            or type(counts["passed"]) is not int
            or counts["passed"] <= 0
            or any(
                type(counts[k]) is not int or counts[k] != 0
                for k in ("failed", "errors", "skipped")
            )
        ):
            raise ValueError("both drivers must pass without skips")


def _evidence_header(evidence: Document) -> None:
    cells = evidence["targets"]
    if (
        evidence.get("schema_version") != 1
        or evidence.get("status") != "passed"
        or evidence.get("findings") != []
        or evidence.get("expected_targets") != len(cells)
        or evidence.get("validated_targets") != len(cells)
    ):
        raise ValueError("complete successful native wheel validation is required")
    if not re.fullmatch(r"[a-f0-9]{40}", evidence["source_sha"]):
        raise ValueError("validation must identify an exact source revision")
    if not str(evidence["run_id"]).isdigit() or int(evidence["run_id"]) <= 0:
        raise ValueError("validation must identify a CI run")
    if type(evidence["run_attempt"]) is not int or evidence["run_attempt"] <= 0:
        raise ValueError("validation must identify a CI attempt")


def _require_coverage(evidence: Document, version: str) -> int:
    """Coverage comes from the release's version, never from the evidence describing itself."""
    required = {(cell["id"], cell["python"]) for cell in release_matrix(version)}
    cells = evidence["targets"]
    if (
        len(cells) != len(required)
        or {(cell["target"], cell["python"]) for cell in cells} != required
    ):
        raise ValueError("complete successful native wheel validation is required")
    return len(required)


def _validated_cell(
    cell: Document, evidence: Document, projects: set[str]
) -> tuple[dict[str, str], dict[str, str]]:
    for field in ("source_sha", "run_id", "run_attempt"):
        if str(cell[field]) != str(evidence[field]):
            raise ValueError(f"mixed validation {field}")
    expected_job = f"wheel ({cell['target']}, {cell['python']})"
    job = cell["ci_job"]
    if (
        cell["status"] != "passed"
        or (job["status"], job["conclusion"]) != ("completed", "success")
        or job["name"].split(" / ")[-1] != expected_job
    ):
        raise ValueError("native CI target did not succeed")
    source = cell["source_install"]
    if source["status"] != "passed":
        raise ValueError("source installation did not pass")
    _drivers(cell)
    _drivers(source)
    companion_projects = projects - {"parallax-postgres"} | {"parallax-conformance"}
    companions = _identities(cell["companions"], companion_projects, ".whl")
    _identities(source["companions"], companion_projects, ".whl")
    _identities([source["wheel"]], {"parallax-postgres"}, ".whl")
    sdists = _identities(source["sdists"], projects, ".tar.gz")
    return companions, sdists


def _validated(evidence: Document, projects: set[str]) -> dict[str, str]:
    _evidence_header(evidence)
    validated: dict[str, str] = {}
    shared = None
    for cell in evidence["targets"]:
        companions, sdists = _validated_cell(cell, evidence, projects)
        if shared is not None and shared != (companions, sdists):
            raise ValueError("targets validated different companion wheels or sdists")
        shared = (companions, sdists)
        artifacts = {**companions, **sdists}
        artifacts.update(_identities([cell["wheel"]], {"parallax-postgres"}, ".whl"))
        for filename, digest in artifacts.items():
            previous = validated.setdefault(filename, digest)
            if previous != digest:
                raise ValueError("validation used different bytes for the same filename")
    return {
        name: digest
        for name, digest in validated.items()
        if not name.startswith("parallax_conformance-")
    }


def _release_manifest(evidence_path: Path, paths: Sequence[Path]) -> Document:
    evidence = json.loads(evidence_path.read_text())
    projects = set(json.loads(CONFIG.read_text())["projects"])
    validated = _validated(evidence, projects)
    if len(paths) != len(validated) or {path.name for path in paths} != set(validated):
        raise ValueError("release files differ from the complete validated artifact set")
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise ValueError("release artifacts must be regular files")
    artifacts: list[dict[str, str]] = []
    version = _metadata(paths[0])["Version"]
    if not isinstance(version, str) or not re.fullmatch(r"0\.\d+\.\d+", version):
        raise ValueError("release requires a normal coordinated pre-1.0 version")
    adapter_wheels = _require_coverage(evidence, version)
    for path in sorted(paths, key=lambda candidate: candidate.name):
        if validated[path.name] != identity(path)["sha256"]:
            raise ValueError(f"{path.name}: not the validated bytes")
        artifacts.append(_artifact(path, version, projects))
    for name in projects:
        kinds = [artifact["kind"] for artifact in artifacts if artifact["project"] == name]
        expected_wheels = adapter_wheels if name == "parallax-postgres" else 1
        if kinds.count("sdist") != 1 or kinds.count("wheel") != expected_wheels:
            raise ValueError(f"{name}: incomplete release artifacts")
    return {
        "schema_version": 1,
        "version": version,
        "source_sha": evidence["source_sha"],
        "validation_run_id": evidence["run_id"],
        "validation_run_attempt": evidence["run_attempt"],
        "wheel_manifest": {
            "filename": "manifest.json",
            "sha256": identity(evidence_path)["sha256"],
        },
        "artifacts": artifacts,
    }


def freeze(handoff: Path, output: Path) -> Document:
    paths = sorted(
        [
            *handoff.glob("*.whl"),
            *(handoff / "companions").glob("*.whl"),
            *(handoff / "sdists").glob("*.tar.gz"),
        ]
    )
    selected = [path for path in paths if not path.name.startswith("parallax_conformance-")]
    result = _release_manifest(handoff / "manifest.json", selected)
    output.mkdir(parents=True, exist_ok=False)
    dist = output / "dist"
    dist.mkdir()
    for path in selected:
        shutil.copy2(path, dist / path.name)
    shutil.copy2(handoff / "manifest.json", output / "wheel-manifest.json")
    (output / "release-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def verify(bundle: Path) -> Document:
    manifest = json.loads((bundle / "release-manifest.json").read_text())
    expected = _release_manifest(bundle / "wheel-manifest.json", list((bundle / "dist").iterdir()))
    if manifest != expected:
        raise ValueError("release manifest differs from retained validation evidence")
    return manifest


def index_files(host: str, project: str, version: str) -> list[Document]:
    try:
        with urllib.request.urlopen(
            f"{host}/pypi/{project}/{version}/json", timeout=60
        ) as response:
            return json.load(response)["urls"]
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return []
        raise


def _download(item: Document, expected: Mapping[str, Document], directory: Path) -> Document:
    filename = item["filename"]
    if item.get("yanked"):
        raise ValueError(f"{filename}: release is yanked; publish a new version")
    if item["digests"]["sha256"] != expected[filename]["sha256"]:
        raise ValueError(f"{filename}: index hash conflicts; never overwrite or skip")
    url = item["url"]
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("index artifact URL must use HTTPS")
    path = directory / filename
    with urllib.request.urlopen(url, timeout=60) as response:
        path.write_bytes(response.read())
    if identity(path)["sha256"] != expected[filename]["sha256"]:
        raise ValueError(f"{filename}: downloaded bytes conflict")
    return {"url": url, **identity(path)}


def reconcile(
    bundle: Path, index: str, output: Path, *, require_complete: bool = False
) -> Document:
    started = time.monotonic()
    manifest = verify(bundle)
    output.mkdir(parents=True, exist_ok=False)
    missing = output / "missing"
    downloaded = output / "downloaded"
    missing.mkdir()
    downloaded.mkdir()
    expected = {artifact["filename"]: artifact for artifact in manifest["artifacts"]}
    found: Document = {}
    for project in sorted({artifact["project"] for artifact in manifest["artifacts"]}):
        for item in index_files(INDEXES[index], project, manifest["version"]):
            filename = item["filename"]
            if filename not in expected or expected[filename]["project"] != project:
                raise ValueError(f"{index}: unexpected published file {filename}")
            if filename in found:
                raise ValueError(f"{index}: duplicate published file {filename}")
            found[filename] = _download(item, expected, downloaded)
    absent = sorted(expected.keys() - found.keys())
    for filename in absent:
        shutil.copy2(bundle / "dist" / filename, missing / filename)
    result: Document = {
        "index": index,
        "source_sha": manifest["source_sha"],
        "version": manifest["version"],
        "status": "incomplete" if absent else "passed",
        "missing": absent,
        "downloads": found,
        "elapsed_seconds": time.monotonic() - started,
    }
    (output / "index.json").write_text(json.dumps(result, indent=2) + "\n")
    if require_complete and absent:
        raise ValueError(f"{index}: missing {len(absent)} artifacts")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze_parser = commands.add_parser("freeze")
    freeze_parser.add_argument("--handoff", type=Path, required=True)
    freeze_parser.add_argument("--output", type=Path, required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--bundle", type=Path, required=True)
    reconcile_parser = commands.add_parser("reconcile")
    reconcile_parser.add_argument("--bundle", type=Path, required=True)
    reconcile_parser.add_argument("--index", choices=INDEXES, required=True)
    reconcile_parser.add_argument("--output", type=Path, required=True)
    reconcile_parser.add_argument("--require-complete", action="store_true")
    reconcile_parser.add_argument("--attempts", type=int, default=1)
    args = parser.parse_args()
    if args.command == "freeze":
        result = freeze(args.handoff, args.output)
    elif args.command == "verify":
        result = verify(args.bundle)
    else:
        if args.attempts < 1:
            parser.error("--attempts must be positive")
        for attempt in range(args.attempts):
            result = reconcile(args.bundle, args.index, args.output / str(attempt))
            if result["status"] == "passed" or not args.require_complete:
                break
            if attempt + 1 < args.attempts:
                time.sleep(15)
        else:
            raise ValueError(
                f"{args.index}: complete release not visible after {args.attempts} attempts"
            )
        if github_output := os.environ.get("GITHUB_OUTPUT"):
            destination = (args.output / str(attempt)).resolve()
            with Path(github_output).open("a", encoding="utf-8") as output:
                output.write(f"missing={destination / 'missing'}\n")
                output.write(f"downloaded={destination / 'downloaded'}\n")
                output.write(f"missing_count={len(result['missing'])}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
