"""Run the m-perf-bench benchmark fixtures and emit a well-formed ``report.json``.

This is the executable half of `m-perf-bench` (performance & benchmark harness). Its job
is to prove the **methodology runs end-to-end** and produces a comparable,
machine-readable report — NOT to set numeric targets (those are per-language,
DQ10). For each benchmark fixture under ``core/compatibility/benchmarks/`` it:

1. provisions the fixture's model (derived DDL via the m-dialect seam);
2. loads a dataset — generated (a deterministic recipe + row count) or empty;
3. runs each workload's golden SQL ``iterations`` times against the real
   database, timing every run;
4. records wall-time ``p50``/``p95``, the database round trips actually issued
   (checked against ``expectRoundTrips`` when declared — the round-trip
   regression guard), and peak/steady process memory;
5. writes ``report.json`` (and prints a compact summary).

Run::

    uv run python -m reference_harness.benchmark ../core/compatibility/benchmarks

The numbers are REFERENCE figures. A language implementation runs the same
fixtures and grades its own numbers against its own targets.
"""

from __future__ import annotations

import json
import sys
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .case import Model, load_model
from .ddl_builder import ddl_for
from .providers import DatabaseProvider, available_dialects, provider_for


class BenchmarkError(Exception):
    """A benchmark fixture is malformed or a workload failed to run."""


# --- dataset generation ------------------------------------------------------


def _generate_accounts_sequential(rows: int) -> dict[str, list[dict[str, Any]]]:
    """``id = 1..rows``; ``owner = owner-<id>``; ``balance = id*100``; ``version = 1``."""
    return {
        "parallax.compatibility.Account": [
            {
                "id": i,
                "owner": f"owner-{i}",
                "balance": f"{i * 100}.00",
                "version": 1,
            }
            for i in range(1, rows + 1)
        ]
    }


def _generate_orders_tree(rows: int, fanout: int) -> dict[str, list[dict[str, Any]]]:
    """``rows`` orders, each with ``fanout`` items, each item with ``fanout`` statuses.

    Ids are global and sequential per entity so the deep-fetch IN-lists in the
    workloads (orders 1..N, items 1..N, statuses keyed by item) line up.
    """
    orders: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    item_id = 0
    status_id = 0
    for order_id in range(1, rows + 1):
        orders.append(
            {
                "id": order_id,
                "name": f"order-{order_id}",
                "sku": f"SKU-{order_id}",
                "qty": 1,
                "price": "10.00",
                "active": True,
                "orderedOn": "2024-01-01",
            }
        )
        for _ in range(fanout):
            item_id += 1
            items.append(
                {
                    "id": item_id,
                    "orderId": order_id,
                    "sku": f"SKU-{item_id}",
                    "quantity": 1,
                }
            )
            for _ in range(fanout):
                status_id += 1
                statuses.append(
                    {
                        "id": status_id,
                        "orderId": order_id,
                        "orderItemId": item_id,
                        "code": "OPEN",
                    }
                )
    return {
        "parallax.compatibility.Order": orders,
        "parallax.compatibility.OrderItem": items,
        "parallax.compatibility.OrderStatus": statuses,
    }


def _generate_document_milestones(rows: int) -> dict[str, list[dict[str, Any]]]:
    """``rows`` current ``Voyage`` milestones and ``rows`` current ``Charter`` rectangles.

    Ids run ``1..rows`` per entity, so a write workload's ``$i`` iteration index
    addresses a milestone of its own and each iteration closes a row no earlier
    iteration touched. Every row is opened at one instant and left open on
    Transaction Time, which is what makes each one a predecessor a close can
    address.

    Both entities are document-mapped, so each row's domain members compose into
    one Structured Column and its axis bounds keep Columns of their own.
    """
    return {
        "parallax.compatibility.Voyage": [
            {
                "id": index,
                "title": f"voyage-{index}",
                "crew": 4,
                "manifest": {"cargo": "timber"},
                "txStart": "2026-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            }
            for index in range(1, rows + 1)
        ],
        "parallax.compatibility.Charter": [
            {
                "id": index,
                "route": f"route-{index}",
                "terms": {"clause": "standard"},
                "validStart": "2026-01-01T00:00:00+00:00",
                "validEnd": "infinity",
                "txStart": "2026-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            }
            for index in range(1, rows + 1)
        ],
    }


def _build_dataset(fixture: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return the rows the benchmark loads, per its ``dataset``.

    Keys are canonical Entity spellings (m-perf-bench); the loader below still
    accepts an unambiguous bare key.
    """
    dataset = fixture.get("dataset", {})
    if dataset.get("empty"):
        return {}
    if "rows" in dataset and isinstance(dataset["rows"], dict):
        return dataset["rows"]
    generate = dataset.get("generate")
    if not generate:
        return {}
    recipe = generate.get("recipe")
    count = int(generate.get("rows", 0))
    if recipe == "accounts-sequential":
        return _generate_accounts_sequential(count)
    if recipe == "orders-tree":
        fanout = int(generate.get("fanout", 1))
        return _generate_orders_tree(count, fanout)
    if recipe == "document-milestones":
        return _generate_document_milestones(count)
    raise BenchmarkError(f"unknown dataset generator recipe {recipe!r}")


def _dataset_row_count(rows: dict[str, list[dict[str, Any]]]) -> int:
    return sum(len(v) for v in rows.values())


# --- provisioning + loading --------------------------------------------------


def _provision(model: Model, rows: dict[str, list[dict[str, Any]]], db: DatabaseProvider) -> None:
    """Reset, apply the model's DDL, and load the generated dataset."""
    db.reset()
    db.apply_ddl(ddl_for(model, db.dialect))
    # Build a Model whose fixtures are the generated rows, then load via the same
    # column-resolution path the compatibility loader uses.
    populated = Model(path=model.path, descriptor=model.descriptor, fixtures=rows)
    from .data_loader import load_model as load_rows

    load_rows(populated, db)


# --- workload execution + timing ---------------------------------------------


def _statement_entries(workload: dict[str, Any], dialect: str) -> list[dict[str, Any]]:
    """The workload's golden statement entries that declare *dialect*."""
    return [
        entry
        for entry in workload.get("statements", [])
        if isinstance(entry, dict)
        and isinstance(entry.get("sql"), dict)
        and dialect in entry["sql"]
    ]


def _statements(workload: dict[str, Any], dialect: str) -> list[str]:
    """The per-dialect golden SQL texts of a workload's ``{sql, binds}`` entries."""
    return [entry["sql"][dialect] for entry in _statement_entries(workload, dialect)]


def _binds_per_statement(workload: dict[str, Any], dialect: str) -> list[list[Any]]:
    """One authored bind list per statement entry, aligned with :func:`_statements`.

    Each statement's binds ride inline on its own entry (default ``[]``) — there is
    no positional pairing to interpret. A bind list follows the same
    flat-or-dialect-keyed polymorphism ``sql`` does (m-case-format): flat where the
    hole structure is shared, and keyed per dialect where it diverges — a document
    mutation's path bind is one Postgres text-array path and one MariaDB JSON-path
    string, so a workload over a Relational Document Layout cannot author one list.
    """
    return [_entry_binds(entry, dialect) for entry in _statement_entries(workload, dialect)]


def _entry_binds(entry: dict[str, Any], dialect: str) -> list[Any]:
    binds = entry.get("binds", [])
    if isinstance(binds, dict):
        return list(binds[dialect])
    return list(binds)


def _substitute_iteration(binds: list[Any], iteration: int) -> list[Any]:
    """Resolve the ``$i`` iteration sentinel against the 1-based iteration index.

    Lets a re-run ``write`` workload write something DISTINCT each iteration, so the
    timing loop stays idempotent and an engine that skips a physically unchanged row
    still does the work being measured.

    A bind that IS the sentinel becomes the index as a host integer — a milestone
    insert's own primary key. A bind that CONTAINS it is text, and the index's digits
    are interpolated into it: a document mutation's value hole takes JSON text
    (`m-case-format`), which no host integer can carry, so ``'"row-$i"'`` is how an
    iteration reaches one.
    """
    return [_iteration_bind(bind, iteration) for bind in binds]


def _iteration_bind(bind: Any, iteration: int) -> Any:
    if bind == "$i":
        return iteration
    if isinstance(bind, str) and "$i" in bind:
        return bind.replace("$i", str(iteration))
    return bind


def _percentile(samples: list[float], pct: float) -> float:
    """The ``pct`` percentile of *samples* (nearest-rank), in the samples' units."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return ordered[rank]


def _run_workload(workload: dict[str, Any], db: DatabaseProvider) -> dict[str, Any]:
    dialect = db.dialect
    is_cache_hit = workload.get("kind") == "cache-hit"
    is_write = workload.get("kind") == "write"
    if is_cache_hit:
        # A query-cache HIT issues NO database round trip: an implementation serves
        # the repeated find from its query cache. The reference harness has no
        # cache, so it executes nothing and records 0 round trips — the methodology
        # witness for `expectRoundTrips: 0`, a cache-hit regression guard for the
        # implementations that DO cache.
        statements: list[str] = []
    else:
        statements = _statements(workload, dialect)
        if not statements:
            raise BenchmarkError(
                f"workload {workload.get('name')!r} has no statements for {dialect}"
            )
    binds = _binds_per_statement(workload, dialect) if statements else []
    iterations = int(workload.get("iterations", 1))

    durations_ms: list[float] = []
    round_trips = 0
    for iteration in range(1, iterations + 1):
        start = time.perf_counter()
        trips = 0
        for index, statement in enumerate(statements):
            stmt_binds = _substitute_iteration(binds[index], iteration)
            if is_write:
                db.execute(statement, stmt_binds)
            else:
                db.query(statement, stmt_binds)
            trips += 1
        durations_ms.append((time.perf_counter() - start) * 1000.0)
        round_trips = trips  # constant across iterations; record the last

    result: dict[str, Any] = {
        "name": workload.get("name"),
        "iterations": iterations,
        "wallTimeMs": {
            "p50": round(_percentile(durations_ms, 50), 4),
            "p95": round(_percentile(durations_ms, 95), 4),
        },
        "roundTrips": round_trips,
    }
    expect = workload.get("expectRoundTrips")
    if expect is not None:
        result["expectRoundTrips"] = expect
        result["roundTripsOk"] = round_trips == expect
        if round_trips != expect:
            raise BenchmarkError(
                f"workload {workload.get('name')!r} issued {round_trips} round "
                f"trip(s) but expectRoundTrips is {expect} (a round-trip "
                f"regression — e.g. a deep fetch that fell back to N+1)."
            )
    return result


# --- top-level runner --------------------------------------------------------


def _discover_fixtures(benchmarks_root: Path) -> list[Path]:
    return sorted(benchmarks_root.glob("*.yaml")) + sorted(benchmarks_root.glob("*.yml"))


def run_benchmarks(benchmarks_root: Path, db: DatabaseProvider) -> dict[str, Any]:
    """Run every benchmark fixture against *db*; return the report structure."""
    benchmarks_root = benchmarks_root.resolve()
    compatibility_root = benchmarks_root.parent  # benchmarks/ -> compatibility/

    tracemalloc.start()
    benchmarks: list[dict[str, Any]] = []
    peak_bytes = 0
    for fixture_path in _discover_fixtures(benchmarks_root):
        with fixture_path.open("r", encoding="utf-8") as handle:
            fixture = yaml.safe_load(handle)
        if not isinstance(fixture, dict):
            continue

        model = load_model(compatibility_root, fixture["model"])
        rows = _build_dataset(fixture)
        _provision(model, rows, db)

        steady_before, _ = tracemalloc.get_traced_memory()
        workloads = [_run_workload(w, db) for w in fixture.get("workloads", [])]
        _, peak = tracemalloc.get_traced_memory()
        peak_bytes = max(peak_bytes, peak)

        benchmarks.append(
            {
                "fixture": fixture_path.name,
                "model": fixture["model"],
                "datasetRows": _dataset_row_count(rows),
                "workloads": workloads,
            }
        )

    steady_bytes, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "dialect": db.dialect,
        "benchmarks": benchmarks,
        "memory": {"peakBytes": peak_bytes, "steadyBytes": steady_bytes},
    }


def _print_summary(report: dict[str, Any]) -> None:
    print(f"benchmark report ({report['dialect']})")
    for benchmark in report["benchmarks"]:
        print(f"  {benchmark['fixture']} ({benchmark['datasetRows']} rows)")
        for workload in benchmark["workloads"]:
            wall = workload["wallTimeMs"]
            trips = workload["roundTrips"]
            expect = workload.get("expectRoundTrips")
            trip_note = f"  rt={trips}" + (f"/{expect}" if expect is not None else "")
            print(
                f"    {workload['name']:<22} "
                f"p50={wall['p50']:>8.3f}ms  p95={wall['p95']:>8.3f}ms{trip_note}"
            )
    mem = report["memory"]
    print(f"  memory: peak={mem['peakBytes']}B steady={mem['steadyBytes']}B")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.benchmark <core/compatibility/benchmarks>",
            file=sys.stderr,
        )
        return 2
    benchmarks_root = Path(argv[0])
    if not benchmarks_root.is_dir():
        print(f"not a directory: {benchmarks_root}", file=sys.stderr)
        return 2

    dialects = available_dialects()
    if not dialects:
        print("no database providers selected (set PARALLAX_DATABASES)", file=sys.stderr)
        return 1

    # Run against the first available dialect; the report records which.
    dialect = dialects[0]
    with provider_for(dialect) as db:
        report = run_benchmarks(benchmarks_root, db)

    Path("report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
