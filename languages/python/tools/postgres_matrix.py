"""Select the PostgreSQL support floor and newest supported release for CI."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

from wheel_build import newest_postgres

_METADATA = Path(__file__).resolve().parents[1] / "packages/parallax-postgres/pyproject.toml"


def versions(latest: str) -> list[str]:
    with _METADATA.open("rb") as stream:
        supported = tomllib.load(stream)["tool"]["parallax"]["postgresql"]["supported"]
    bounds = re.fullmatch(r">=(18\.\d+),<19", supported)
    if bounds is None:
        raise ValueError(f"review PostgreSQL matrix selection for {supported!r}")
    floor = bounds.group(1)
    if not re.fullmatch(r"18\.\d+", latest) or int(latest.split(".")[1]) < int(floor.split(".")[1]):
        raise ValueError(f"PostgreSQL {latest!r} is outside {supported}")
    return sorted({floor, latest}, key=lambda version: int(version.split(".")[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    selected = versions(newest_postgres())
    if args.output is not None:
        source = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_METADATA.parents[4], text=True
        ).strip()
        args.output.write_text(
            json.dumps(
                {
                    "source_sha": source,
                    "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
                    "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
                    "postgres_versions": selected,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps(selected))


if __name__ == "__main__":
    main()
