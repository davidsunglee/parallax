"""Static SQL lint: every golden / reference SQL parses, golden SQL is canonical.

Run as a module against the compatibility tree::

    uv run python -m reference_harness.sql_lint ../core/compatibility

For every case this checks, without touching a database:

* each ``goldenSql[dialect]`` parses under that dialect (sqlglot);
* each ``goldenSql[dialect]`` is already a **fixed point** of M3 normalization
  (``normalize(goldenSql) == goldenSql``) — the M12 layer-3 property, enforced
  statically so non-canonical golden SQL fails before any database run;
* ``referenceSql`` (when present) parses (it is naive by design, so it is NOT
  required to be canonical).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import sqlglot
import yaml

from .sql_normalize import normalize


class SqlLintFailure(Exception):
    pass


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def lint_tree(compatibility_root: Path) -> list[str]:
    compatibility_root = compatibility_root.resolve()
    errors: list[str] = []
    cases_dir = compatibility_root / "cases"

    for case_path in sorted(cases_dir.glob("**/*.y*ml")):
        case = _load_yaml(case_path)
        if not isinstance(case, dict):
            continue
        name = case_path.name

        _lint_golden(case.get("goldenSql", {}), "goldenSql", name, errors)
        # A scenario case carries its golden SQL per step; lint each step's.
        scenario = case.get("scenario")
        if isinstance(scenario, list):
            for index, step in enumerate(scenario):
                if isinstance(step, dict):
                    _lint_golden(
                        step.get("goldenSql", {}),
                        f"scenario[{index}].goldenSql",
                        name,
                        errors,
                    )

        reference = case.get("referenceSql")
        if isinstance(reference, str):
            # referenceSql is dialect-neutral naive SQL; parse with the first
            # declared golden dialect (or postgres) just to confirm it is valid.
            golden = case.get("goldenSql", {})
            dialect = next(iter(golden), "postgres") if isinstance(golden, dict) else "postgres"
            try:
                sqlglot.parse_one(reference, read=dialect)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"case {name}: referenceSql does not parse: {exc}")

    return errors


def _lint_golden(golden: Any, where: str, name: str, errors: list[str]) -> None:
    """Parse + canonical-check every golden SQL statement under *golden*.

    *golden* is a ``goldenSql`` mapping (dialect -> statement | [statements]),
    used both for a case's top-level golden SQL and for a scenario step's. Each
    statement must parse under its dialect and be a fixed point of M3
    normalization; *where* labels the source (``goldenSql`` or
    ``scenario[i].goldenSql``).
    """
    if not isinstance(golden, dict):
        return
    for dialect, value in golden.items():
        # A dialect's golden SQL is a single statement or an ordered list of
        # statements (one per deep-fetch level / DML step); lint each statement.
        statements = [value] if isinstance(value, str) else list(value)
        for index, sql in enumerate(statements):
            label = f"{where}.{dialect}"
            if len(statements) > 1:
                label += f"[{index}]"
            try:
                sqlglot.parse_one(sql, read=dialect)
            except Exception as exc:  # noqa: BLE001 - report parse errors as lint
                errors.append(f"case {name}: {label} does not parse: {exc}")
                continue
            try:
                canonical = normalize(sql, dialect)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"case {name}: {label} could not be normalized: {exc}")
                continue
            if canonical != sql:
                errors.append(
                    f"case {name}: {label} is not canonical.\n"
                    f"      stored:     {sql!r}\n"
                    f"      normalized: {canonical!r}"
                )


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.sql_lint <core/compatibility>",
            file=sys.stderr,
        )
        return 2
    compatibility_root = Path(argv[0])
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2

    errors = lint_tree(compatibility_root)
    if errors:
        print(f"sql lint FAILED ({len(errors)} problem(s)):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("sql lint OK: all golden SQL is canonical and all SQL parses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
