"""Emit the compatibility-matrix report (implementations x databases).

The only "implementation" is the reference suite itself (the golden SQL); the
databases are Postgres and MariaDB (Phase 10 added MariaDB as the second dialect
behind the m-db-port provider seam). The report shape was built in from day one so the
matrix grows without a redesign: adding a dialect adds a column; adding a language
implementation adds a row.

Run::

    uv run python -m reference_harness.matrix ../core/compatibility

Writes ``matrix.json`` and prints a compact grid to stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .case import discover_cases
from .case_runner import run_case
from .providers import available_dialects, provider_for


def build_matrix(compatibility_root: Path) -> dict[str, Any]:
    compatibility_root = compatibility_root.resolve()
    cases = discover_cases(compatibility_root)
    dialects = available_dialects()

    # reference x {dialects}: pass/fail counts per dialect.
    results: dict[str, dict[str, Any]] = {}
    for dialect in dialects:
        passed = 0
        failures: list[str] = []
        with provider_for(dialect) as db:
            for case in cases:
                try:
                    run_case(case, db)
                    passed += 1
                except AssertionError as exc:  # noqa: PERF203 - per-case reporting
                    failures.append(f"{case.path.name}: {exc}")
        results[dialect] = {
            "total": len(cases),
            "passed": passed,
            "failed": len(failures),
            "failures": failures,
            "green": not failures,
        }

    return {
        "implementations": ["reference"],
        "databases": dialects,
        "cases": len(cases),
        "results": {"reference": results},
    }


def _print_grid(matrix: dict[str, Any]) -> None:
    databases = matrix["databases"]
    print(f"compatibility matrix ({matrix['cases']} cases)")
    header = "  implementation   " + "  ".join(f"{db:>10}" for db in databases)
    print(header)
    for impl in matrix["implementations"]:
        cells = []
        for db in databases:
            result = matrix["results"][impl][db]
            mark = "OK" if result["green"] else f"FAIL({result['failed']})"
            cells.append(f"{mark:>10}")
        print(f"  {impl:<15}  " + "  ".join(cells))


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m reference_harness.matrix <core/compatibility>", file=sys.stderr)
        return 2
    compatibility_root = Path(argv[0])
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2

    matrix = build_matrix(compatibility_root)
    Path("matrix.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    _print_grid(matrix)

    all_green = all(
        result["green"] for impl in matrix["results"].values() for result in impl.values()
    )
    if not matrix["databases"]:
        print("no database providers selected (set PARALLAX_DATABASES)", file=sys.stderr)
        return 1
    return 0 if all_green else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
