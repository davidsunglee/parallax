"""Unit tests for the M13 benchmark harness logic, DB-free.

The end-to-end benchmark run (provision, load a generated dataset, time workloads,
emit report.json) executes against a real database via
``python -m reference_harness.benchmark``. These tests cover the pure logic that
needs no database: the deterministic dataset generators, percentile aggregation,
the ``$i`` iteration substitution, and the shape of every shipped fixture.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from reference_harness.benchmark import (
    _binds_per_statement,
    _build_dataset,
    _dataset_row_count,
    _generate_accounts_sequential,
    _generate_orders_tree,
    _percentile,
    _statements,
    _substitute_iteration,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_ROOT = _REPO_ROOT / "core" / "compatibility" / "benchmarks"


# --- dataset generators ------------------------------------------------------


def test_accounts_sequential_is_deterministic_and_sized() -> None:
    rows = _generate_accounts_sequential(1000)
    accounts = rows["Account"]
    assert len(accounts) == 1000
    assert accounts[0] == {"id": 1, "owner": "owner-1", "balance": "100.00", "version": 1}
    assert accounts[-1]["id"] == 1000
    # Ids are unique and contiguous.
    assert {a["id"] for a in accounts} == set(range(1, 1001))


def test_orders_tree_fans_out() -> None:
    rows = _generate_orders_tree(rows=10, fanout=5)
    assert len(rows["Order"]) == 10
    assert len(rows["OrderItem"]) == 10 * 5
    assert len(rows["OrderStatus"]) == 10 * 5 * 5
    # The first five items belong to order 1 (so the deep-fetch IN-list lines up).
    first_order_items = [i for i in rows["OrderItem"] if i["orderId"] == 1]
    assert [i["id"] for i in first_order_items] == [1, 2, 3, 4, 5]


def test_build_dataset_dispatches_recipes() -> None:
    assert _dataset_row_count(_build_dataset({"dataset": {"empty": True}})) == 0
    accounts = _build_dataset(
        {"dataset": {"generate": {"recipe": "accounts-sequential", "rows": 5}}}
    )
    assert _dataset_row_count(accounts) == 5


# --- timing + binds ----------------------------------------------------------


def test_percentile_nearest_rank() -> None:
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(samples, 50) == 3.0
    assert _percentile(samples, 95) == 5.0
    assert _percentile([], 50) == 0.0


def test_iteration_substitution_replaces_sentinel() -> None:
    binds = ["$i", "ACCT-1", 100.00, "2024-01-01T00:00:00+00:00", "infinity"]
    assert _substitute_iteration(binds, 7)[0] == 7
    # Non-sentinel binds are untouched.
    assert _substitute_iteration(binds, 7)[1:] == binds[1:]


def test_binds_per_statement_pads_to_count() -> None:
    workload = {"binds": [[5], [1, 2, 3]]}
    per = _binds_per_statement(workload, 3)
    assert per == [[5], [1, 2, 3], []]
    # A flat list is the single statement's binds.
    assert _binds_per_statement({"binds": [5]}, 1) == [[5]]


def test_statements_single_and_list() -> None:
    assert _statements({"goldenSql": {"postgres": "select 1"}}, "postgres") == ["select 1"]
    multi = {"goldenSql": {"postgres": ["select 1", "select 2"]}}
    assert _statements(multi, "postgres") == ["select 1", "select 2"]


# --- the shipped fixtures ----------------------------------------------------


def _fixtures() -> list[Path]:
    return sorted(BENCHMARKS_ROOT.glob("*.yaml"))


def test_benchmark_fixtures_exist() -> None:
    names = {p.name for p in _fixtures()}
    assert {"read-mix.yaml", "deep-fetch.yaml", "milestone-write.yaml"} <= names


def test_every_workload_declares_iterations_and_golden() -> None:
    for fixture_path in _fixtures():
        fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
        assert "model" in fixture, fixture_path.name
        for workload in fixture["workloads"]:
            assert workload.get("iterations", 0) >= 1, (fixture_path.name, workload["name"])
            if workload.get("kind") == "cache-hit":
                # A cache-hit workload issues no SQL (0 round trips), so it lists
                # no golden SQL — the methodology witness for `expectRoundTrips: 0`.
                assert workload.get("expectRoundTrips") == 0, (
                    fixture_path.name,
                    workload["name"],
                )
                continue
            assert _statements(workload, "postgres"), (fixture_path.name, workload["name"])


def test_deep_fetch_round_trips_match_statement_count() -> None:
    # A multi-statement deep-fetch workload's expectRoundTrips MUST equal its
    # statement count — the round-trip regression guard the harness enforces.
    fixture = yaml.safe_load((BENCHMARKS_ROOT / "deep-fetch.yaml").read_text(encoding="utf-8"))
    for workload in fixture["workloads"]:
        statements = _statements(workload, "postgres")
        assert workload["expectRoundTrips"] == len(statements), workload["name"]
