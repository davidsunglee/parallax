"""Build retained production sdists and validate their installed native wheels."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from validate_wheel import digest, run_logged

CONFIG = Path(__file__).resolve().parents[3] / ".github/release/configuration.json"
PRODUCTION = frozenset(
    name.replace("-", "_") for name in json.loads(CONFIG.read_text())["projects"]
)


def identities(paths: list[Path]) -> list[dict[str, str]]:
    return [{"filename": path.name, "sha256": digest(path)} for path in sorted(paths)]


def production_paths(directory: Path, pattern: str) -> list[Path]:
    paths = sorted(directory.glob(pattern))
    names = [path.name.split("-", 1)[0] for path in paths]
    if len(names) != len(PRODUCTION) or set(names) != set(PRODUCTION):
        raise ValueError("expected exactly the six production source distributions")
    return paths


def build_and_validate(sdists: Path, companions: Path, output: Path, postgres_version: str) -> None:
    output.mkdir(parents=True, exist_ok=False)
    record: dict[str, Any] = {"status": "failed"}
    started = time.monotonic()
    try:
        sources = production_paths(sdists, "*.tar.gz")
        record["sdists"] = identities(sources)
        wheelhouse = output / "built"
        wheelhouse.mkdir()
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
        }
        record["build_seconds"] = run_logged(
            [
                sys.executable,
                "-I",
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-cache-dir",
                "--wheel-dir",
                str(wheelhouse),
                *(str(path) for path in sources),
            ],
            output / "build.log",
            environment,
        )
        built = production_paths(wheelhouse, "*.whl")
        record["wheels"] = identities(built)
        (output / "wheelhouse").mkdir()
        (output / "companions").mkdir()
        for wheel in built:
            destination = (
                "wheelhouse" if wheel.name.startswith("parallax_postgres-") else "companions"
            )
            shutil.move(wheel, output / destination / wheel.name)
        (conformance,) = companions.glob("parallax_conformance-*.whl")
        shutil.copy2(conformance, output / "companions" / conformance.name)
        (adapter,) = (output / "wheelhouse").glob("*.whl")
        run_logged(
            [
                sys.executable,
                "-I",
                str(Path(__file__).with_name("validate_wheel.py")),
                "--wheel",
                str(adapter),
                "--companions",
                str(output / "companions"),
                "--output",
                str(output / "validation"),
                "--postgres-version",
                postgres_version,
            ],
            output / "validate.log",
            environment,
        )
        record["status"] = "passed"
    except BaseException as error:
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        record["elapsed_seconds"] = time.monotonic() - started
        (output / "source.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdists", required=True, type=Path)
    parser.add_argument("--companions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--postgres-version", required=True)
    args = parser.parse_args()
    build_and_validate(
        args.sdists.resolve(strict=True),
        args.companions.resolve(strict=True),
        args.output.resolve(),
        args.postgres_version,
    )


if __name__ == "__main__":
    main()
