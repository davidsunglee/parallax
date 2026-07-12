# Parallax Python — operational guide

Operational reference for building and verifying the Parallax Python target
(`slice-snapshot-1`). Milestones, commands, database setup, status, blockers
only — design decisions live in `spec/python.md` and `docs/adr/`.

## Layout

```text
languages/python/
  pyproject.toml        uv workspace root (virtual): toolchain + tool config;
                        hosts the generated [tool.importlinter] complement
  pyrightconfig.json    Pyright strict configuration
  uv.lock               committed lockfile (one per workspace)
  tools/
    check_dag_sync.py   generates/checks the import-linter forbidden-edge
                        complement from core/spec/modules.md (§7)
  packages/
    parallax-core/        the class-free engine spine (production)
    parallax-snapshot/     snapshot lifecycle + handle (production)
    parallax-postgres/     concrete psycopg adapter (production)
    parallax-conformance/  corpus/case loading + describe/compile/run CLI (dev-only)
  tests/                unit / dialect / compile_sweep / conformance / provider /
                        adapter_smoke / api_conformance / artifact / clean_install /
                        api_surface lanes (pytest markers, §6/§10)
  docs/adr/             per-language ADRs
```

The four distributions share the PEP 420 `parallax.*` namespace: there is no
`parallax/__init__.py` at the namespace root, and each distribution ships
`py.typed` at its own package root.

## Dependency-respecting milestones

Built in dependency-graph order (`core/spec/modules.md`, `IMPLEMENTING.md`); a
dependency is always implemented before anything that names it. The nine COR-3
phases (structure outline
`.humanlayer/tasks/cor-3-build-python-slice/06-structure-outline-python-snapshot-target.md`):

1. Workspace, toolchain, and verification wiring. **(this milestone)**
2. Conformance spine — `m-core`, `m-case-format`, `describe` end-to-end.
3. Metamodel hub and Pydantic class frontend.
4. Core amendment bundle (compile-eligibility, write-instruction schema, coalescing).
5. SQL walking skeleton — tracer compiles and runs end-to-end.
6. Transactions and temporal backbone.
7. Snapshot branch.
8. Writes and correctness.
9. Claim closure.

## Commands

Run from the repo root (via `just`) or from `languages/python` (via `uv`).

| Purpose | Command |
|---|---|
| Install dev environment | `cd languages/python && uv sync` |
| All database-free gates (§10) | `just python-static` |
| Static + Docker database lanes | `just python-verify` |
| Unit tests | `cd languages/python && uv run pytest -m unit` |
| Regenerate import-linter complement | `cd languages/python && uv run python tools/check_dag_sync.py --write` |
| Verify the complement is in sync | `cd languages/python && uv run python tools/check_dag_sync.py` |

Pytest markers (§6): `unit`, `dialect`, `compile_sweep`, `adapter_smoke`,
`provider_contract`, `conformance`, `api_conformance`, `artifact`,
`clean_install`, `api_surface`.

## Database setup

Database-backed lanes (`conformance`/`pg-full`, `provider_contract`,
`adapter_smoke`) use testcontainers-python with a `self-managed` Postgres
container. **Docker must be running.** One container per test session; per-case
isolation is `DROP SCHEMA … CASCADE` → descriptor-derived DDL → fixtures. These
lanes come online in COR-3 Phase 5; a session summary will report every skipped
database-backed check, and CI fails on any silent skip.

## Current status

- **Phases 1–3 complete.** The uv workspace, the four distributions over the
  PEP 420 namespace, the generated import-linter enforcement, the full §10
  toolchain, `just python-static` / `just python-verify`, and the
  `python-static` / `python-database` CI lanes are stood up and green
  database-free.
- **Phase 2 (conformance spine):** `m-core` neutral types, `m-case-format`
  corpus loading with the §1 case-selection expression, the in-process adapter
  core, and the CLI — `describe` runs end-to-end from argv to schema-validated
  JSON and exit code. The API Conformance Suite framework, coverage partition,
  and generated Usage Guide run from day one (every active-slice case
  reasoned-skipped until its capability lands).
- **Phase 3 (metamodel hub + class frontend):** the `m-descriptor` records and
  serde, `m-pk-gen`, `m-inheritance`, and `m-value-object` models, plus the
  Pydantic class frontend (`Attr`/`Rel` typed descriptors, `Field` /
  `Relationship`, definition-time validation, `meta` introspection). The
  descriptor no-drift guard is live.
- **Phase 4 next:** the core amendment bundle (compile-eligibility declaration,
  write-instruction schema, same-transaction coalescing). Phases 5–9 not
  started; no read/write runtime path exists yet.

## Blockers

- None. Docker is required to run the database-backed lanes (Phase 5+); the
  database-free lane (`just python-static`) needs no Docker.
