"""The layered assertion engine (M12 runner sub-part).

Per case, against a freshly-provisioned database selected via the provider seam:

1. **Schema conformance** — descriptor / operation / case validate (done
   statically by :mod:`schema_validate`; re-asserted here for the loaded case).
2. **Triple equivalence** — ``exec(goldenSql[dialect]) == exec(referenceSql) ==
   expectedRows`` (the ``referenceSql`` term only when present).
3. **Normalization determinism** — ``normalize(goldenSql[dialect]) ==
   goldenSql[dialect]``.
4. **Serde round-trip** — ``serialize(deserialize(x)) == x`` for BOTH the
   operation encoding AND the model descriptor, in BOTH JSON and YAML.

It deliberately **never compiles the operation to SQL** — that is the job of a
real implementation, graded against the golden SQL.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from . import serde
from .case import Case
from .data_loader import load_model
from .ddl_builder import ddl_for
from .providers import DatabaseProvider
from .sql_normalize import normalize


class CaseFailure(AssertionError):
    """A compatibility-case assertion failed."""


def _coerce_scalar(value: Any) -> Any:
    """Coerce a DB / expected scalar to a comparable canonical form.

    Postgres returns ``Decimal`` for numeric and exact ints for integers; YAML
    authors write plain ints/floats/strings. We compare numerically where both
    sides are numbers so authoring an ``int`` against a ``bigint`` column matches.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        # Preserve exactness but allow comparison with int/float expected values.
        return float(value) if value % 1 else int(value)
    return value


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _coerce_scalar(value) for key, value in row.items()}


def _rows_equal(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    """Order-insensitive multiset comparison of result rows."""
    def key(rows: list[dict[str, Any]]) -> list[tuple[tuple[str, Any], ...]]:
        return sorted(
            tuple(sorted(_normalize_row(r).items())) for r in rows
        )

    return key(left) == key(right)


def _assert_schema(case: Case) -> None:
    # Layer 1 is enforced statically across the whole tree by schema_validate.
    # Here we assert the minimal structural invariants the runner relies on so a
    # malformed case fails loudly rather than deep in execution.
    if "operation" not in case.raw:
        raise CaseFailure(f"{case.path.name}: missing operation")
    if not case.model.class_name:
        raise CaseFailure(f"{case.path.name}: model has no class name")


def _assert_normalization(case: Case, dialect: str) -> None:
    golden = case.golden_sql[dialect]
    canonical = normalize(golden, dialect)
    if canonical != golden:
        raise CaseFailure(
            f"{case.path.name}: goldenSql.{dialect} is not canonical.\n"
            f"  stored:     {golden!r}\n"
            f"  normalized: {canonical!r}"
        )


def _assert_serde(case: Case) -> None:
    # Layer 4a: operation serde. Layer 4b: metamodel (descriptor) serde.
    serde.assert_roundtrip(case.operation)
    serde.assert_roundtrip(case.model.descriptor)


def _assert_triple_equivalence(case: Case, db: DatabaseProvider) -> None:
    dialect = db.dialect
    golden = case.golden_sql[dialect]

    db.reset()
    db.apply_ddl(ddl_for(case.model, dialect))
    load_model(case.model, db)

    golden_rows = db.query(golden, case.binds)
    expected = case.expected_rows

    if not _rows_equal(golden_rows, expected):
        raise CaseFailure(
            f"{case.path.name}: goldenSql.{dialect} rows != expectedRows.\n"
            f"  golden:   {golden_rows!r}\n"
            f"  expected: {expected!r}"
        )

    if case.reference_sql is not None:
        reference_rows = db.query(case.reference_sql)
        if not _rows_equal(reference_rows, expected):
            raise CaseFailure(
                f"{case.path.name}: referenceSql rows != expectedRows.\n"
                f"  reference: {reference_rows!r}\n"
                f"  expected:  {expected!r}"
            )


def run_case(case: Case, db: DatabaseProvider) -> None:
    """Run all available assertion layers for *case* against *db*."""
    dialect = db.dialect
    if dialect not in case.golden_sql:
        # No golden SQL for this dialect: nothing to execute against it. The
        # serde + (dialect-agnostic) checks still run so coverage is not skipped.
        _assert_schema(case)
        _assert_serde(case)
        return

    _assert_schema(case)
    _assert_normalization(case, dialect)  # layer 3
    _assert_serde(case)  # layer 4
    _assert_triple_equivalence(case, db)  # layer 2
