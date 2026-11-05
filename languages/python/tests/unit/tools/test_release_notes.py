from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import release_notes as release

_SOURCE = "a" * 40
_REPOSITORY = "example/parallax"


def _render(notes: str) -> str:
    return release.render_notes(notes, "0.1.0", _REPOSITORY, _SOURCE, 123, 456)


def test_selects_only_requested_release_and_preserves_nested_headings_and_code() -> None:
    notes = """# Release notes

## 0.2.0
Future changes.

## 0.1.0
Published features.

### Installation
```text
## 0.9.0
literal example
```

## Older changes
Earlier features.
"""
    rendered = _render(notes)
    assert "Published features." in rendered
    assert "### Installation\n```text\n## 0.9.0\nliteral example\n```" in rendered
    assert "Future changes." not in rendered
    assert "Earlier features." not in rendered
    assert f"source `{_SOURCE}`" in rendered
    assert f"https://github.com/{_REPOSITORY}/actions/runs/123" in rendered
    assert f"https://github.com/{_REPOSITORY}/actions/runs/456" in rendered


@pytest.mark.parametrize(
    "notes",
    [
        "# Release notes\n\n## 0.2.0\nOther release.\n",
        "## 0.1.0\n\n## 0.2.0\nOther release.\n",
        "## 0.1.0\nOne.\n## 0.1.0\nTwo.\n",
        "## [0.1.0]\nMalformed version heading.\n",
    ],
)
def test_refuses_missing_empty_duplicate_or_malformed_requested_section(notes: str) -> None:
    with pytest.raises(ValueError, match=r"one nonempty section for 0\.1\.0"):
        _render(notes)


def test_relative_links_are_pinned_to_original_source_in_release_body() -> None:
    notes = """## 0.1.0
[Guide](guide/01-getting-started.md#install)
[Licence](../../../LICENSE)
[Root](/README.md)
[Same file](#details)
[External](https://example.com/path?q=1#section)
[Mail](mailto:hello@example.com)
[Policy][policy]

[policy]: releasing.md#compatibility-and-maintenance
"""
    rendered = _render(notes)
    base = f"https://github.com/{_REPOSITORY}/blob/{_SOURCE}"
    assert f"[Guide]({base}/languages/python/docs/guide/01-getting-started.md#install)" in rendered
    assert f"[Licence]({base}/LICENSE)" in rendered
    assert f"[Root]({base}/README.md)" in rendered
    assert f"[Same file]({base}/languages/python/docs/releases.md#details)" in rendered
    assert "[External](https://example.com/path?q=1#section)" in rendered
    assert "[Mail](mailto:hello@example.com)" in rendered
    assert (
        f"[policy]: {base}/languages/python/docs/releasing.md#compatibility-and-maintenance"
        in rendered
    )


def test_refuses_relative_links_escaping_the_repository() -> None:
    with pytest.raises(ValueError, match="escapes the repository"):
        _render("## 0.1.0\n[Escape](../../../../outside.md)\n")


@pytest.mark.parametrize(
    ("repository", "source", "ci_run", "publication_run"),
    [("invalid", _SOURCE, 1, 2), (_REPOSITORY, "HEAD", 1, 2), (_REPOSITORY, _SOURCE, 0, 2)],
)
def test_refuses_ambiguous_source_and_evidence_identity(
    repository: str, source: str, ci_run: int, publication_run: int
) -> None:
    with pytest.raises(ValueError):
        release.render_notes(
            "## 0.1.0\nFeatures.\n", "0.1.0", repository, source, ci_run, publication_run
        )


def _git(directory: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(directory), *arguments], text=True).strip()


def test_cli_reads_artifact_source_notes_instead_of_checkout_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Release test")
    _git(tmp_path, "config", "user.email", "release@example.com")
    notes = tmp_path / "languages/python/docs/releases.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("## 0.1.0\nOriginal authored features.\n")
    _git(tmp_path, "add", str(notes.relative_to(tmp_path)))
    _git(tmp_path, "commit", "-qm", "docs: author release notes")
    source = _git(tmp_path, "rev-parse", "HEAD")
    notes.write_text("## 0.1.0\nUnvalidated checkout features.\n")
    bundle = tmp_path / "candidate"
    bundle.mkdir()
    (bundle / "release-manifest.json").write_text(
        json.dumps({"source_sha": source, "version": "0.1.0"})
    )
    ci: dict[str, Any] = {
        "source_sha": source,
        "repository": _REPOSITORY,
        "status": "passed",
        "run": {"id": 123, "head_sha": source, "status": "completed", "conclusion": "success"},
    }
    (bundle / "ci.json").write_text(json.dumps(ci))
    output = tmp_path / "published.md"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "release_notes.py",
            "--bundle",
            str(bundle),
            "--repository",
            _REPOSITORY,
            "--publication-run-id",
            "456",
            "--output",
            str(output),
        ],
    )
    release.main()
    rendered = output.read_text()
    assert "Original authored features." in rendered
    assert "Unvalidated checkout features." not in rendered
    assert f"source `{source}`" in rendered
    ci["run"]["head_sha"] = "b" * 40
    (bundle / "ci.json").write_text(json.dumps(ci))
    output.unlink()
    with pytest.raises(ValueError, match="successful CI for the artifact source"):
        release.main()
    assert not output.exists()
