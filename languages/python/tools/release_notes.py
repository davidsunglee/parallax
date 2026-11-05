"""Render authored release notes with the exact published source and evidence."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_NOTES_PATH = "languages/python/docs/releases.md"
_LINK = re.compile(r"(\[[^\]\n]+\]\()([^\s()]+)(\))")
_REFERENCE = re.compile(r"^(\s*\[[^\]\n]+\]:\s*)([^\s]+)(.*)$", re.MULTILINE)


def _section(notes: str, version: str) -> str:
    sections: list[tuple[str, list[str]]] = []
    fence: str | None = None
    for line in notes.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        heading = re.fullmatch(r"##\s+(.+?)\s*", line) if fence is None else None
        if heading:
            sections.append((heading.group(1), []))
        elif sections:
            sections[-1][1].append(line)
    selected = ["\n".join(lines).strip() for name, lines in sections if name == version]
    if len(selected) != 1 or not selected[0]:
        raise ValueError(f"release notes require one nonempty section for {version}")
    return selected[0]


def _destination(target: str, repository: str, source: str) -> str:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return target
    path = (
        posixpath.normpath(
            posixpath.join(posixpath.dirname(_NOTES_PATH), parsed.path)
            if not parsed.path.startswith("/")
            else parsed.path.lstrip("/")
        )
        if parsed.path
        else _NOTES_PATH
    )
    if path == ".." or path.startswith("../"):
        raise ValueError("release note link escapes the repository")
    return urlunsplit(
        (
            "https",
            "github.com",
            f"/{repository}/blob/{source}/{path}",
            parsed.query,
            parsed.fragment,
        )
    )


def render_notes(
    notes: str,
    version: str,
    repository: str,
    source: str,
    ci_run_id: int,
    ci_attempt: int,
    publication_run_id: int,
    publication_attempt: int,
) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be an owner/name pair")
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("source must be a full commit SHA")
    if min(ci_run_id, ci_attempt, publication_run_id, publication_attempt) < 1:
        raise ValueError("evidence run IDs and attempts must be positive")
    section = _section(notes, version)
    section = _LINK.sub(
        lambda match: match[1] + _destination(match[2], repository, source) + match[3], section
    )
    section = _REFERENCE.sub(
        lambda match: match[1] + _destination(match[2], repository, source) + match[3], section
    )
    prefix = f"https://github.com/{repository}/actions/runs"
    return (
        f"Parallax {version} is published to PyPI.\n\n{section}\n\n"
        "### Validation and provenance\n\n"
        f"Published artifacts match the validated manifest for source `{source}`.\n\n"
        f"- [Successful source CI]({prefix}/{ci_run_id}/attempts/{ci_attempt})\n"
        "- [Production publication and verification]"
        f"({prefix}/{publication_run_id}/attempts/{publication_attempt})\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--publication-run-id", type=int, required=True)
    parser.add_argument("--publication-attempt", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.bundle / "release-manifest.json").read_text())
    ci = json.loads((args.bundle / "ci.json").read_text())
    source = manifest["source_sha"]
    run = ci["run"]
    if (
        ci["source_sha"] != source
        or ci["repository"] != args.repository
        or ci["status"] != "passed"
        or run["head_sha"] != source
        or run["status"] != "completed"
        or run["conclusion"] != "success"
    ):
        raise ValueError("release notes require successful CI for the artifact source")
    notes = subprocess.check_output(
        ["git", "show", f"{source}:{_NOTES_PATH}"], text=True, encoding="utf-8"
    )
    rendered = render_notes(
        notes,
        manifest["version"],
        args.repository,
        source,
        ci["run"]["id"],
        ci["run"]["run_attempt"],
        args.publication_run_id,
        args.publication_attempt,
    )
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
