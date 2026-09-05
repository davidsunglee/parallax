# AGENTS.md — Parallax Python target

Directory-specific guidance for agents working under `languages/python/`. Repo
policy in the root `AGENTS.md` and `CLAUDE.md` still applies; this file only adds
what is specific to the Python target and does not restate it.

## Before writing runtime code

Read, in order: root `README.md`, `IMPLEMENTING.md`, `core/spec/00-overview.md`,
`core/spec/modules.md`, `core/spec/slices.md`,
`core/spec/m-conformance-adapter.md`, then this target's completed spec
`spec/python.md`, this file, and `TESTING.md`. The spec is the binding product
definition; nothing here overrides it.

## Binding constraint — no cross-implementation prior art

Other Parallax language implementations — sibling `languages/*` targets, their
justfile recipes, tests, adapters, and operational docs — are
**non-normative and MUST NOT** be used as prior art or design input. Derive
everything from `spec/python.md`, the core specs, `core/schemas/`, the
compatibility corpus, and the conformance-adapter contract. Resolve gaps in
those artifacts rather than consulting another implementation.

## Before adding, moving, or changing a test

Read `TESTING.md`. It is this target's authoritative testing map: which semantic
surface directory a test belongs in, what may live at the test root, where
cross-surface support goes, which fixture reaches a live database, and which
command owns which selection.

## Design decisions live in the spec

Do not record design decisions here or in `TESTING.md`. They belong in
`spec/python.md` and the ADRs under `docs/adr/`. Executable commands live in the
root `justfile`, whose recipe docs and `just show-gates <recipe>` are their own
reference; `TESTING.md` is limited to the test map.

## Deferred-work ledger

The deferred-work ledger at [`docs/deferred-ledger.md`](docs/deferred-ledger.md)
binds every session: read it at session start, add an entry in the same session
any deferral happens, and sweep it at claim closure. It carries **only open
entries** — closing or graduating one means removing it and leaving a forwarding
line, so the ledger stays a work list rather than an archive.

Entry numbering is continuous and never reused, so a D-number identifies one
item. The ledger's own History section names the per-ticket files holding the
full text of entries it no longer carries.

## Key commands

Every Python command is a `python-*` recipe in the root `justfile`; `just --list`
prints the catalog and `just show-gates python-check` prints what the merge gate
owns. Two steps have no recipe of their own:

- `cd languages/python && uv sync` — install the dev environment (all five
  workspace distributions editable, plus the toolchain).
- `cd languages/python && uv run python tools/check_dag_sync.py --write` —
  regenerate the import-linter forbidden-edge complement after a
  `core/spec/modules.md` change.
