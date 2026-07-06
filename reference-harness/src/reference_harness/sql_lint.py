"""Static SQL lint: every golden / reference SQL parses, golden SQL is canonical.

Run as a module against the compatibility tree::

    uv run python -m reference_harness.sql_lint ../core/compatibility

For every case this checks, without touching a database, over every ``{sql, binds}``
statement entry (``then.statements``, each per-step ``statements`` list under
``when`` — scenario / coherence / attempts / concurrency rounds — and each
``given.apply`` naive entry):

* each golden entry's per-dialect ``sql`` parses under that dialect (sqlglot);
* each golden entry's per-dialect ``sql`` is already a **fixed point** of m-sql
  normalization (``normalize(sql) == sql``) — the m-case-format layer-3 property,
  enforced statically so non-canonical golden SQL fails before any database run;
* each entry's ``?`` placeholder count equals its ``binds`` count — the most common
  authoring mistake, which the Docker-backed suite would otherwise only surface as
  a driver exception;
* a ``given.apply`` entry's plain-string ``sql`` and ``then.referenceSql`` (when
  present) parse (both are naive by design, so NOT required to be canonical).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import sqlglot
import yaml

from .sql_normalize import normalize, sqlglot_dialect


class SqlLintFailure(Exception):
    pass


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _lint_benchmarks(compatibility_root: Path, errors: list[str]) -> None:
    """Lint every benchmark workload's golden statement entries (m-perf-bench).

    Benchmark fixtures live under ``benchmarks/`` (not ``cases/``) and carry their
    golden SQL per workload as ``{sql, binds}`` statement entries (dialect-keyed map
    form), like a case's ``then.statements``. Each statement must parse and be a fixed
    point of m-sql normalization — so a non-canonical benchmark query fails statically
    rather than only at run time. A cache-hit workload lists no ``statements``.
    """
    benchmarks_dir = compatibility_root / "benchmarks"
    if not benchmarks_dir.is_dir():
        return
    for fixture_path in sorted(benchmarks_dir.glob("*.y*ml")):
        fixture = _load_yaml(fixture_path)
        if not isinstance(fixture, dict):
            continue
        for index, workload in enumerate(fixture.get("workloads", [])):
            if isinstance(workload, dict):
                _lint_golden(
                    workload.get("statements"),
                    f"workloads[{index}].statements",
                    fixture_path.name,
                    errors,
                )


def lint_tree(compatibility_root: Path) -> list[str]:
    compatibility_root = compatibility_root.resolve()
    errors: list[str] = []
    cases_dir = compatibility_root / "cases"
    _lint_benchmarks(compatibility_root, errors)

    for case_path in sorted(cases_dir.glob("**/*.y*ml")):
        case = _load_yaml(case_path)
        if not isinstance(case, dict):
            continue
        name = case_path.name
        raw_given = case.get("given")
        given = raw_given if isinstance(raw_given, dict) else {}
        raw_when = case.get("when")
        when = raw_when if isinstance(raw_when, dict) else {}
        raw_then = case.get("then")
        then = raw_then if isinstance(raw_then, dict) else {}

        # The golden SQL an implementation is expected to emit.
        _lint_golden(then.get("statements"), "then.statements", name, errors)

        # A conflict case's out-of-band setup: dialect-agnostic naive statement
        # entries (plain-string sql). Like referenceSql they are NOT required to be
        # canonical, but each must parse — and its ? count must match its binds.
        _lint_golden(given.get("apply"), "given.apply", name, errors)

        # The per-step golden SQL of a scenario / coherence / conflict-retry case.
        for step_key in ("scenario", "coherence", "attempts"):
            steps = when.get(step_key)
            if isinstance(steps, list):
                for index, step in enumerate(steps):
                    if isinstance(step, dict):
                        _lint_golden(
                            step.get("statements"),
                            f"when.{step_key}[{index}].statements",
                            name,
                            errors,
                        )

        # An error case (m-db-error) or read-lock case may carry its golden SQL inside
        # a two-connection `concurrency` choreography; lint each node step's.
        concurrency = when.get("concurrency")
        if isinstance(concurrency, dict):
            for r_index, rnd in enumerate(concurrency.get("rounds", [])):
                if not isinstance(rnd, dict):
                    continue
                for node in ("A", "B"):
                    step = rnd.get(node)
                    if isinstance(step, dict):
                        _lint_golden(
                            step.get("statements"),
                            f"when.concurrency.rounds[{r_index}].{node}.statements",
                            name,
                            errors,
                        )

        reference = then.get("referenceSql")
        if isinstance(reference, str):
            # referenceSql is dialect-neutral naive SQL; parse with the first
            # declared golden dialect (or postgres) just to confirm it is valid.
            dialect = _first_golden_dialect(then.get("statements"))
            try:
                sqlglot.parse_one(reference, read=sqlglot_dialect(dialect))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"case {name}: referenceSql does not parse: {exc}")

    return errors


def _first_golden_dialect(entries: Any) -> str:
    """The first dialect declared in *entries*' golden ``sql`` maps (or postgres)."""
    if isinstance(entries, list):
        for entry in entries:
            sql = entry.get("sql") if isinstance(entry, dict) else None
            if isinstance(sql, dict) and sql:
                return next(iter(sql))
    return "postgres"


def _lint_golden(entries: Any, where: str, name: str, errors: list[str]) -> None:
    """Parse + canonical-check + bind-count-check every statement entry in *entries*.

    *entries* is a list of ``{sql, binds}`` statement entries — a case's
    ``then.statements``, a per-step ``statements`` list, a ``given.apply`` list, or a
    benchmark workload's ``statements``. A GOLDEN entry's ``sql`` is a dialect-keyed
    map (``postgres`` / ``mariadb``) whose every dialect text must parse AND be a fixed
    point of m-sql normalization; a NAIVE ``given.apply`` entry's ``sql`` is a plain
    string that must parse (naive by design, so NOT required to be canonical). Either
    way each entry's ``?`` placeholder count MUST equal its bind count. *where* labels
    the source (``then.statements``, ``when.scenario[i].statements``, ...).
    """
    if not isinstance(entries, list):
        return
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        sql = entry.get("sql")
        binds = entry.get("binds", [])
        bind_count = len(binds) if isinstance(binds, list) else 0
        # A naive entry's sql is a plain string (parse-only); a golden entry's is a
        # dialect-keyed map, each text of which must be canonical.
        if isinstance(sql, str):
            texts: list[tuple[str, str, bool]] = [("postgres", sql, False)]
        elif isinstance(sql, dict):
            texts = [(d, t, True) for d, t in sql.items() if isinstance(t, str)]
        else:
            continue
        for dialect, text, canonical_required in texts:
            label = f"{where}[{index}]"
            if canonical_required:
                label += f".{dialect}"
            try:
                sqlglot.parse_one(text, read=sqlglot_dialect(dialect))
            except Exception as exc:  # noqa: BLE001 - report parse errors as lint
                errors.append(f"case {name}: {label} does not parse: {exc}")
                continue
            if canonical_required:
                try:
                    canonical = normalize(text, dialect)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"case {name}: {label} could not be normalized: {exc}")
                    continue
                if canonical != text:
                    errors.append(
                        f"case {name}: {label} is not canonical.\n"
                        f"      stored:     {text!r}\n"
                        f"      normalized: {canonical!r}"
                    )
            placeholders = text.count("?")
            if placeholders != bind_count:
                errors.append(
                    f"case {name}: {label} has {placeholders} ? placeholder(s) "
                    f"but {bind_count} bind(s)"
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
