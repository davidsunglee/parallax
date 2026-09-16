---
date: 2026-09-15
git_commit: 681ce91fa06f185ee57ebe8889ccd4445d4c86cc
topic: "Eager and streamed delivery benchmarks: Parallax against SQLAlchemy"
type: research
tags: [research, benchmark, performance, memory, streaming, sqlalchemy, parallax]
status: living
---

# Delivery Benchmarks

This directory keeps a dated history of end-to-end delivery measurements for
Parallax and the comparable SQLAlchemy shapes, so later changes can be graded
against earlier runs on the same workloads. Each run has a note, a raw data
file, and the script revision that produced it.

These are calibration figures, not acceptance gates. The gated cost envelopes
live under `languages/python/docs/` and are owned by CI. Nothing here is read
by a check.

## Runs

| Date | Note | Data | Subject |
|---|---|---|---|
| 2026-09-11 | [2026-09-15 note](2026-09-15-parallax-vs-sqlalchemy.md), baseline columns | [parallax](data/2026-09-11-parallax.json), [sqlalchemy](data/2026-09-11-sqlalchemy-2.0.52.json) | Original Parallax baseline and SQLAlchemy 2.0.52 comparison, transcribed from the COR-146 and COR-147 task reports |
| 2026-09-15 | [Parallax vs SQLAlchemy](2026-09-15-parallax-vs-sqlalchemy.md) | [parallax](data/2026-09-15-parallax-681ce91f.json) | Parallax rerun at `681ce91f` against the unchanged SQLAlchemy figures |

## Layout

- `data/` holds one JSON file per measured system per run, named
  `<date>-<system>[-<commit>].json`. Files emitted directly by a script are
  raw; files rebuilt from a report carry a `provenance.source` saying so.
- `scripts/` holds the measurement scripts. `measure_parallax_delivery.py`
  drives Parallax through the provider-free port and live PostgreSQL;
  `measure_sqlalchemy_delivery.py` drives SQLAlchemy through the same DDL and
  fixtures, and imports the Parallax script for them.

## Adding a run

1. Run the script from `languages/python` as the note's reproduction section
   describes, redirecting stdout to `data/<date>-parallax-<short-sha>.json`.
2. Rerun the SQLAlchemy script only when the SQLAlchemy release, driver, or
   PostgreSQL version changes, or when the workload shapes change. Otherwise
   reuse the most recent SQLAlchemy data file and say so in the note.
3. Write a dated note with the primary comparison, the page-size curve, and
   memory at page 32, and add a row to the table above.
4. If the script had to change to run, record what changed and why in the
   note. Repairs that only touch the provider-free fake port do not affect the
   live PostgreSQL cells.
