from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[5]


def test_verified_publication_announces_source_notes_with_exact_evidence_attempts(
    tmp_path: Path,
) -> None:
    workflow: Any = yaml.safe_load((REPO / ".github/workflows/release.yml").read_text())
    announcement = workflow["jobs"]["announce"]
    assert "publish" in announcement["needs"]
    step = next(step for step in announcement["steps"] if "run" in step)
    for directory in ("candidate/dist", "production", "languages/python/docs", "bin"):
        (tmp_path / directory).mkdir(parents=True)
    authored_notes = tmp_path / "languages/python/docs/releases.md"
    authored_notes.write_text(
        "# Release notes\n\n## 0.2.0\nFuture features.\n\n"
        "## 0.1.0\nPublished features and [guide](guide/01-getting-started.md#install).\n"
    )
    origin = tmp_path / "origin.git"
    commands = [
        ["git", "init", "--bare", str(origin)],
        ["git", "init", str(tmp_path)],
        ["git", "config", "user.name", "Release test"],
        ["git", "config", "user.email", "release@example.com"],
        ["git", "add", str(authored_notes.relative_to(tmp_path))],
        ["git", "commit", "-m", "docs: author release notes"],
        ["git", "remote", "add", "origin", str(origin)],
        ["git", "push", "origin", "HEAD:main"],
    ]
    for command in commands:
        subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    authored_notes.write_text("PREPARATION_ONLY: unvalidated checkout notes\n")
    renderer = tmp_path / "languages/python/tools/release_notes.py"
    renderer.parent.mkdir()
    shutil.copyfile(REPO / "languages/python/tools/release_notes.py", renderer)
    (tmp_path / "candidate/release-manifest.json").write_text(
        json.dumps({"source_sha": source, "version": "0.1.0"})
    )
    (tmp_path / "candidate/ci.json").write_text(
        json.dumps(
            {
                "source_sha": source,
                "repository": "owner/project",
                "status": "passed",
                "run": {
                    "id": 17,
                    "run_attempt": 2,
                    "head_sha": source,
                    "status": "completed",
                    "conclusion": "success",
                },
            }
        )
    )
    for name in ("wheel-manifest.json", "dist/candidate.whl"):
        (tmp_path / "candidate" / name).write_text("verified fixture\n")
    (tmp_path / "production/index.json").write_text('{"status":"passed"}\n')
    captured = tmp_path / "announcement.md"
    captured_target = tmp_path / "target.txt"
    gh = tmp_path / "bin/gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "if sys.argv[1:3] == ['release', 'create']:\n"
        "    notes = Path(sys.argv[sys.argv.index('--notes-file') + 1])\n"
        "    Path(os.environ['CAPTURE']).write_text(notes.read_text())\n"
        "    Path(os.environ['CAPTURE_TARGET']).write_text(\n"
        "        sys.argv[sys.argv.index('--target') + 1])\n"
    )
    gh.chmod(0o755)
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{gh.parent}{os.pathsep}{os.environ['PATH']}",
            "CAPTURE": str(captured),
            "CAPTURE_TARGET": str(captured_target),
            "VERSION": "0.1.0",
            "SOURCE": source,
            "GITHUB_REPOSITORY": "owner/project",
            "GITHUB_RUN_ID": "21",
            "GITHUB_RUN_ATTEMPT": "3",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    published = captured.read_text()
    assert "Parallax 0.1.0 is published to PyPI" in published
    assert "Published features" in published
    assert f"source `{source}`" in published
    assert (
        f"https://github.com/owner/project/blob/{source}/languages/python/docs/guide/"
        "01-getting-started.md#install" in published
    )
    assert "https://github.com/owner/project/actions/runs/17/attempts/2" in published
    assert "https://github.com/owner/project/actions/runs/21/attempts/3" in published
    assert "Future features" not in published
    assert "PREPARATION_ONLY" not in published
    assert captured_target.read_text() == source
