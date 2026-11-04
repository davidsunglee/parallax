"""Prepare coordinated owner-approved yanking and verify the index result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from release_artifacts import INDEXES, index_files, verify


def yank_plan(bundle: Path, reason: str, *, check: bool = False) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("a clear coordinated yank reason is required")
    manifest = verify(bundle)
    projects = sorted({a["project"] for a in manifest["artifacts"]})
    expected = {a["filename"]: a for a in manifest["artifacts"]}
    result: dict[str, Any] = {
        "source_sha": manifest["source_sha"],
        "version": manifest["version"],
        "reason": reason,
        "approval_required": "Dave must explicitly approve before any yank action.",
        "projects": [],
    }
    for project in projects:
        files = index_files(INDEXES["pypi"], project, manifest["version"])
        for item in files:
            entry = expected.get(item["filename"])
            if (
                entry is None
                or entry["project"] != project
                or entry["sha256"] != item["digests"]["sha256"]
            ):
                raise ValueError(
                    "index differs from the retained release; investigate before yanking"
                )
            if check and (not item.get("yanked") or item.get("yanked_reason") != reason):
                raise ValueError(f"{project}/{item['filename']}: coordinated yank not complete")
        result["projects"].append(
            {
                "project": project,
                "published_files": len(files),
                "action": "yank" if files else "unpublished; no yank needed",
                "owner_url": f"https://pypi.org/manage/project/{project}/release/{manifest['version']}/",
            }
        )
    result["status"] = "verified" if check else "approval-pending"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = yank_plan(args.bundle, args.reason, check=args.verify)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
