from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[5]


def test_verified_publication_announces_success_instead_of_preparation_status(
    tmp_path: Path,
) -> None:
    workflow: Any = yaml.safe_load((REPO / ".github/workflows/release.yml").read_text())
    announcement = workflow["jobs"]["announce"]
    assert "publish" in announcement["needs"]
    step = next(step for step in announcement["steps"] if "run" in step)
    for directory in ("candidate/dist", "production", "languages/python/docs", "bin"):
        (tmp_path / directory).mkdir(parents=True)
    for name in ("release-manifest.json", "wheel-manifest.json", "ci.json", "dist/candidate.whl"):
        (tmp_path / "candidate" / name).write_text("verified fixture\n")
    (tmp_path / "production/index.json").write_text('{"status":"passed"}\n')
    (tmp_path / "languages/python/docs/releases.md").write_text(
        "PREPARATION_ONLY: publication pending\n"
    )
    captured = tmp_path / "announcement.md"
    gh = tmp_path / "bin/gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "if sys.argv[1:3] == ['release', 'create']:\n"
        "    notes = Path(sys.argv[sys.argv.index('--notes-file') + 1])\n"
        "    Path(os.environ['CAPTURE']).write_text(notes.read_text())\n"
    )
    gh.chmod(0o755)
    source = "a" * 40
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{gh.parent}{os.pathsep}{os.environ['PATH']}",
            "CAPTURE": str(captured),
            "VERSION": "0.1.0",
            "SOURCE": source,
            "GITHUB_REPOSITORY": "owner/project",
            "GITHUB_RUN_ID": "21",
            "GITHUB_RUN_ATTEMPT": "1",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    published = captured.read_text()
    assert "Parallax 0.1.0 is published to PyPI" in published
    assert f"source `{source}`" in published
    assert (
        f"https://github.com/owner/project/blob/{source}/languages/python/docs/releases.md"
        in published
    )
    assert "PREPARATION_ONLY" not in published
