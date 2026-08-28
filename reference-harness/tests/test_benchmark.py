"""Unit tests for the m-perf-bench benchmark harness logic, DB-free.

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
    _generate_document_milestones,
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
    accounts = rows["parallax.compatibility.Account"]
    assert len(accounts) == 1000
    assert accounts[0] == {"id": 1, "owner": "owner-1", "balance": "100.00", "version": 1}
    assert accounts[-1]["id"] == 1000
    # Ids are unique and contiguous.
    assert {a["id"] for a in accounts} == set(range(1, 1001))


def test_orders_tree_fans_out() -> None:
    rows = _generate_orders_tree(rows=10, fanout=5)
    assert len(rows["parallax.compatibility.Order"]) == 10
    assert len(rows["parallax.compatibility.OrderItem"]) == 10 * 5
    assert len(rows["parallax.compatibility.OrderStatus"]) == 10 * 5 * 5
    # The first five items belong to order 1 (so the deep-fetch IN-list lines up).
    first_order_items = [i for i in rows["parallax.compatibility.OrderItem"] if i["orderId"] == 1]
    assert [i["id"] for i in first_order_items] == [1, 2, 3, 4, 5]


def test_document_milestones_opens_one_current_row_per_id() -> None:
    # Each write iteration addresses the milestone whose primary key is its own
    # `$i` index, so ids must be contiguous per entity and every row must be left
    # open on Transaction Time for a close to address it.
    rows = _generate_document_milestones(50)
    voyages = rows["parallax.compatibility.Voyage"]
    charters = rows["parallax.compatibility.Charter"]
    assert {v["id"] for v in voyages} == set(range(1, 51))
    assert {c["id"] for c in charters} == set(range(1, 51))
    assert all(v["txEnd"] == "infinity" for v in voyages)
    assert all(c["txEnd"] == "infinity" and c["validEnd"] == "infinity" for c in charters)
    # Both are document-mapped, so each row carries an occurrence the Structured
    # Column composes rather than a column of its own.
    assert voyages[0]["manifest"] == {"cargo": "timber"}
    assert charters[0]["terms"] == {"clause": "standard"}


def test_build_dataset_dispatches_recipes() -> None:
    assert _dataset_row_count(_build_dataset({"dataset": {"empty": True}})) == 0
    accounts = _build_dataset(
        {"dataset": {"generate": {"recipe": "accounts-sequential", "rows": 5}}}
    )
    assert _dataset_row_count(accounts) == 5
    milestones = _build_dataset(
        {"dataset": {"generate": {"recipe": "document-milestones", "rows": 5}}}
    )
    assert _dataset_row_count(milestones) == 10  # one Voyage and one Charter per id


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


def test_a_sentinel_inside_text_interpolates_rather_than_replacing_the_bind() -> None:
    # A document mutation's value hole takes JSON TEXT (m-case-format), which no
    # host integer can carry: Postgres resolves a bare parameter there to
    # `jsonb_set`'s declared `jsonb` and refuses an integer outright. Interpolating
    # the index into the text is how an iteration reaches such a hole, and it leaves
    # the bare-sentinel form (a milestone insert's own primary key) alone.
    assert _substitute_iteration(['"Ada-$i"', "{score}", "$i"], 3) == ['"Ada-3"', "{score}", 3]


def test_binds_per_statement_reads_each_entry() -> None:
    # Each statement entry carries its own binds inline (default []); the reader
    # returns one list per entry, aligned with `_statements`.
    workload = {
        "statements": [
            {"sql": {"postgres": "select 1"}, "binds": [5]},
            {"sql": {"postgres": "select 2"}, "binds": [1, 2, 3]},
            {"sql": {"postgres": "select 3"}},
        ]
    }
    assert _binds_per_statement(workload, "postgres") == [[5], [1, 2, 3], []]
    single = {"statements": [{"sql": {"postgres": "select 1"}, "binds": [5]}]}
    assert _binds_per_statement(single, "postgres") == [[5]]


def test_binds_may_be_keyed_per_dialect_where_the_hole_structure_diverges() -> None:
    # A document mutation's path bind is one Postgres text-array path and one
    # MariaDB JSON-path string, so the two dialects cannot share one authored list.
    workload = {
        "statements": [
            {
                "sql": {"postgres": "update t set p = ?", "mariadb": "update t set p = ?"},
                "binds": {"postgres": ["{score}"], "mariadb": ["$.score"]},
            }
        ]
    }
    assert _binds_per_statement(workload, "postgres") == [["{score}"]]
    assert _binds_per_statement(workload, "mariadb") == [["$.score"]]


def test_statements_single_and_list() -> None:
    single = {"statements": [{"sql": {"postgres": "select 1"}}]}
    assert _statements(single, "postgres") == ["select 1"]
    multi = {"statements": [{"sql": {"postgres": "select 1"}}, {"sql": {"postgres": "select 2"}}]}
    assert _statements(multi, "postgres") == ["select 1", "select 2"]


# --- the shipped fixtures ----------------------------------------------------


def _fixtures() -> list[Path]:
    return sorted(BENCHMARKS_ROOT.glob("*.yaml"))


def test_benchmark_fixtures_exist() -> None:
    names = {p.name for p in _fixtures()}
    assert {
        "read-mix.yaml",
        "deep-fetch.yaml",
        "milestone-write.yaml",
        "document-layout.yaml",
        "document-layout-temporal.yaml",
        "stream.yaml",
    } <= names


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


def test_stream_round_trips_are_the_page_arithmetic_of_one_result() -> None:
    # A delivery of N roots at page size B over L levels costs `floor(N/B) + 1`
    # root statements and `ceil(N/B) * L` child ones (m-perf-bench, streamed
    # delivery), so each workload's declared count is derivable from its own page
    # size rather than merely equal to how many statements someone authored. The
    # three workloads are ONE result at three page sizes, which is what makes the
    # count the trade rather than a setting: 20 roots cost 9, 6, and 3 round trips.
    fixture = yaml.safe_load((BENCHMARKS_ROOT / "stream.yaml").read_text(encoding="utf-8"))
    roots, levels = 20, 1
    for workload, page in zip(fixture["workloads"], (5, 7, 20), strict=True):
        pages = -(-roots // page)
        declared = roots // page + 1 + pages * levels
        for dialect in ("postgres", "mariadb"):
            assert workload["expectRoundTrips"] == len(_statements(workload, dialect)), (
                workload["name"],
                dialect,
            )
        assert workload["expectRoundTrips"] == declared, workload["name"]
    assert [w["expectRoundTrips"] for w in fixture["workloads"]] == [9, 6, 3]


def test_stream_pages_seek_from_the_root_the_previous_page_delivered_last() -> None:
    # The keyset seek, read off the binds rather than off the SQL: every root
    # statement after the first carries one more bind than the first, and that bind
    # is the primary key of the root its predecessor page ended on. A workload
    # authored with a fixed cursor — or with none — re-delivers or skips rows, and
    # would still spell exactly the right number of statements.
    fixture = yaml.safe_load((BENCHMARKS_ROOT / "stream.yaml").read_text(encoding="utf-8"))
    for workload, page in zip(fixture["workloads"], (5, 7, 20), strict=True):
        roots = [
            entry for entry in workload["statements"] if "from orders" in entry["sql"]["postgres"]
        ]
        assert [entry["binds"][-1] for entry in roots] == [page] * len(roots), workload["name"]
        cursors = [entry["binds"][1] for entry in roots[1:]]
        assert cursors == [min(page * (n + 1), 20) for n in range(len(cursors))], workload["name"]


def test_temporal_document_layout_declares_the_milestone_write_shapes() -> None:
    # A temporal successor binds ONE complete document, so the statement count is a
    # property of the milestone topology rather than of the member count: a chain
    # closes and inserts once, a rectangle split closes and inserts three times.
    fixture = yaml.safe_load(
        (BENCHMARKS_ROOT / "document-layout-temporal.yaml").read_text(encoding="utf-8")
    )
    by_name = {w["name"]: w for w in fixture["workloads"]}
    for dialect in ("postgres", "mariadb"):
        assert by_name["predecessor-resolve"]["expectRoundTrips"] == len(
            _statements(by_name["predecessor-resolve"], dialect)
        )
        assert by_name["milestone-chain"]["expectRoundTrips"] == len(
            _statements(by_name["milestone-chain"], dialect)
        )
        assert by_name["rectangle-split"]["expectRoundTrips"] == len(
            _statements(by_name["rectangle-split"], dialect)
        )
    assert by_name["milestone-chain"]["expectRoundTrips"] == 2
    assert by_name["rectangle-split"]["expectRoundTrips"] == 4
    # Every write iteration addresses its own seeded milestone, so the dataset must
    # carry at least one row per iteration.
    seeded = fixture["dataset"]["generate"]["rows"]
    assert by_name["milestone-chain"]["iterations"] <= seeded
    assert by_name["rectangle-split"]["iterations"] <= seeded
    assert by_name["predecessor-resolve"]["iterations"] <= seeded
