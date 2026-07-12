# AGENTS.md — Parallax Python target

Directory-specific guidance for agents working under `languages/python/`. Repo
policy in the root `AGENTS.md` and `CLAUDE.md` still applies; this file only adds
what is specific to the Python target and does not restate it.

## Before writing runtime code

Read, in order: root `README.md`, `IMPLEMENTING.md`, `core/spec/00-overview.md`,
`core/spec/modules.md`, `core/spec/slices.md`,
`core/spec/m-conformance-adapter.md`, then this target's completed spec
`spec/python.md`, this file, and the operational guide `GUIDE.md`. The spec is
the binding product definition; nothing here overrides it.

## Binding constraint — no cross-implementation prior art

Other Parallax language implementations (e.g. `languages/typescript/`, its
`ts-*` justfile recipes, tests, adapters, and operational docs) are
**non-normative and MUST NOT** be used as prior art or design input. Derive
everything from `spec/python.md`, the core specs, `core/schemas/`, the
compatibility corpus, and the conformance-adapter contract. Resolve gaps in
those artifacts rather than consulting another implementation.

## Design decisions live in the spec

Do not record design decisions here or in `GUIDE.md`. They belong in
`spec/python.md` and the ADRs under `docs/adr/`. Per-language operational docs
are limited to milestones, executable commands, database setup, current status,
and blockers.

## COR-3 deferred-work ledger

While the initial build (`slice-snapshot-1`) is in flight, the deferred-work
ledger at `.humanlayer/tasks/cor-3-build-python-slice/05-deferred-ledger.md`
binds every session: read it at session start, add an entry in the same session
any deferral happens, and sweep it at claim closure.

## Key commands

All commands run against the uv workspace rooted at this directory.

- `uv sync` — install the dev environment (all four workspace distributions
  editable, plus the toolchain).
- `just python-static` — every database-free gate (§10).
- `just python-verify` — static plus the Docker-backed database lanes.
- `uv run python tools/check_dag_sync.py --write` — regenerate the import-linter
  forbidden-edge complement after a `core/spec/modules.md` change.

See `GUIDE.md` for the full milestone/command/status detail.
