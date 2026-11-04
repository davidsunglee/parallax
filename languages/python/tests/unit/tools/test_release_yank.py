from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import release_yank


@pytest.fixture
def release(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "source_sha": "a" * 40,
        "version": "0.1.0",
        "artifacts": [
            {"project": "parallax-core", "filename": "core.whl", "sha256": "abc"},
            {"project": "parallax-snapshot", "filename": "snapshot.whl", "sha256": "def"},
        ],
    }
    monkeypatch.setattr(release_yank, "verify", lambda _: manifest)
    return manifest


def test_plan_includes_published_and_unpublished_projects(
    release: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def listing(host: str, project: str, version: str) -> list[dict[str, Any]]:
        assert host == "https://pypi.org" and version == release["version"]
        return (
            [{"filename": "core.whl", "digests": {"sha256": "abc"}}]
            if project == "parallax-core"
            else []
        )

    monkeypatch.setattr(release_yank, "index_files", listing)
    result = release_yank.yank_plan(Path("candidate"), "Use 0.1.1: incorrect results")
    assert result["status"] == "approval-pending"
    assert result["projects"][0]["published_files"] == 1
    assert result["projects"][1]["action"] == "unpublished; no yank needed"
    assert "Dave" in result["approval_required"]


@pytest.mark.parametrize(
    "item",
    [
        {"filename": "other.whl", "digests": {"sha256": "abc"}},
        {"filename": "core.whl", "digests": {"sha256": "changed"}},
    ],
)
def test_plan_refuses_index_conflicts(
    release: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    item: dict[str, Any],
) -> None:
    monkeypatch.setattr(release_yank, "index_files", lambda *_: [item])
    with pytest.raises(ValueError, match="index differs"):
        release_yank.yank_plan(Path("candidate"), "Use 0.1.1")


@pytest.mark.parametrize(
    ("yanked", "reason", "passes"),
    [
        (False, None, False),
        (True, "other reason", False),
        (True, "Use 0.1.1", True),
    ],
)
def test_verify_requires_every_published_file_and_exact_reason(
    release: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    yanked: bool,
    reason: str | None,
    passes: bool,
) -> None:
    monkeypatch.setattr(
        release_yank,
        "index_files",
        lambda host, project, version: [
            {
                "filename": a["filename"],
                "digests": {"sha256": a["sha256"]},
                "yanked": yanked,
                "yanked_reason": reason,
            }
            for a in release["artifacts"]
            if a["project"] == project
        ],
    )
    if passes:
        assert (
            release_yank.yank_plan(Path("candidate"), "Use 0.1.1", check=True)["status"]
            == "verified"
        )
    else:
        with pytest.raises(ValueError, match="coordinated yank not complete"):
            release_yank.yank_plan(Path("candidate"), "Use 0.1.1", check=True)
