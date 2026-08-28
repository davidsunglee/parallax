# Testing Parallax

The operational map for verifying this repository: which command owns which
gate, and how to get from iterating on a change to a merge-ready run.

Everything here is about *this* repository. The rules a language implementation
must satisfy, and the reasoning behind them, belong to
[`core/spec/language-testing.md`](core/spec/language-testing.md). Python's test
layout, fixtures, and scheduling labels belong to
[`languages/python/TESTING.md`](languages/python/TESTING.md), and its quality
policy — thresholds, matrices, exclusions, and required proof — to
[`languages/python/spec/python.md`](languages/python/spec/python.md) §10.
Verification behavior specific to agents belongs to [`AGENTS.md`](AGENTS.md).
None of them is restated here.

## The workflow

1. **While iterating**, run the narrowest command covering what you changed —
   a focused test selector, or the one execution command that owns the gate you
   are working against.
2. **After the last relevant change**, run `just check` once. It is the merge
   gate, and it ends with a single stable line naming its verdict.
3. **After a failure**, run the focused command that owns the failing gate to get
   a short diagnostic loop, and fix the cause there. Do not repeat the aggregate
   until something relevant has changed.

`just check` is the merge gate, not the complete one. It omits the `cost` class —
the memory measurements, which read a whole interpreter each and are the slowest
thing here by a wide margin. `just check-all` adds them, and CI runs them on
every change, so nothing that `just check` skips goes ungated. `check-all` and
`check-cost` are CI's, not a local step. While you are changing what that class
grades — the memory instruments themselves, or a suite that reads a whole
interpreter — `just python-check-cost` is the one command that owns the gate, and
running it is focused iteration rather than a second aggregate.

Rerun a command that already passed only when it did not run to completion, when
relevant repository state changed afterwards, or when you are explicitly asked
to. The aggregate is slow because it is broad; running it twice on one tree
proves nothing the first run did not.

## Reading a command name

Every public recipe reads `<scope>-<operation>[-<qualifier>]` over the closed
operation vocabulary in
[`core/spec/language-testing.md`](core/spec/language-testing.md) §2, so what
running one does — and whether it touches your working tree — is readable
without opening anything. The scopes here are `core`, the core specification and
compatibility corpus; `harness`, the reference harness's own health; and
`python`. A command with no scope is repository-wide.

`just --list` prints the whole catalog with a one-line description each.

## Repository aggregates

| Command | Runs |
|---|---|
| `just check` | The merge gate: every blocking check a merge waits on |
| `just check-all` | The complete gate: `check` plus the `cost` class CI also runs |
| `just check-dbfree` | Every blocking check that needs no live database |
| `just check-db` | Every blocking check that needs a live database (Docker) |
| `just check-cost` | Every blocking check needing an interpreter no other test shares |
| `just check-gates` | This repository's command graph against the testing contract |
| `just lint-markdown` | Markdown lint across `core/spec`, `languages/**/spec`, and the root |

## Scope aggregates

| Command | Runs |
|---|---|
| `just core-check` | The module graph, slice profiles, schemas, language-contract diagnostics, cross-layout and batch-size twin parity, and every completed language spec |
| `just harness-check-dbfree` | The harness's format, lint, typecheck, database-access guard, and database-free tests |
| `just harness-check-db` | The compatibility corpus against every selected provider |
| `just python-check-dbfree` | Every Python gate that needs no database, including coverage and diff coverage |
| `just python-check-db` | Every Python gate that needs one |
| `just python-check-cost` | The memory measurements, and the guard confining them |
| `just python-check` | All three Python class aggregates |

Everything in both tables above is covered by `just check-all`, and everything
but the `cost` entries by `just check`, so naming one of them beside its
aggregate adds no coverage. `just show-gates check` and `just show-gates
check-all` resolve exactly what each run contains.

## Focused iteration

| Purpose | Command |
|---|---|
| One Python semantic surface | `just python-test-<surface>`, one per surface — `just python-test-unit` and its five siblings |
| The Pydantic parity corpus on the declared floor | `just python-test-pydantic-floor` |
| The language-contract diagnostics | `just harness-test-contract-tools` |
| One canonical slice's capabilities and cases | `just core-show-slice slice-snapshot-1` |
| One language spec, drafted or complete | `just core-show-language-spec languages/python/spec/python.md` |
| The compatibility-matrix report | `just report-matrix` |
| The execution lifecycle's dispatch and overhead baseline | `just python-report-lifecycle-overhead` |
| The Snapshot graph's retained and build overhead baseline | `just python-report-snapshot-graph-overhead` |
| The published instance-state three-arm retained and timing matrix | `just python-report-instance-state` |
| Formatting, applied in place | `just harness-format`, `just python-format` |

No focused selector is part of `just check`, so a green focused run is never
evidence that the gate covering it would pass. Iterate here; finish there.

`python-test-pydantic-floor` is the one whose subject no aggregate covers at
all: it re-resolves the parity corpus against the oldest Pydantic release
`parallax-core` declares, while every aggregate grades the locked one. CI owns
that end of the supported range in a job of its own, so it is gated on every
change without `just check` growing a second dependency resolution.

## Inspecting the graph

```sh
just show-gates
just show-gates check
```

`just show-gates` renders the root [`justfile`](justfile) as resolved — roles,
execution owners, prerequisites, scheduling classes, and runtime classes — and
naming a command narrows it to that command's closure. It is how to resolve what
an aggregate already contains before listing or running commands beside it.
`just check-gates` is the blocking half: it fails when the graph, the test
layout, the runner configuration, these maps, or the CI job list drift apart.

## Continuous integration

`.github/workflows/ci.yml` runs the same commands, so its job identifiers are
recipe names. The union of the jobs covers the whole `check-all` graph —
including the `cost` class that `just check` omits, which is what makes omitting
it locally safe.

| Job | Matrix | Runs |
|---|---|---|
| `check-gates` | — | `just check-gates` |
| `core-check` | — | `just core-check` |
| `lint-markdown` | — | `just lint-markdown` |
| `harness-check-dbfree` | — | `just harness-check-dbfree` |
| `harness-check-db` | `postgres`, `mariadb` | `just harness-check-db` |
| `python-check-dbfree` | CPython 3.13 / 3.14 | 3.14: `just python-check-dbfree`; 3.13: `just python-test-dbfree` with coverage disabled |
| `python-check-db` | — | `just python-check-db` |
| `python-check-cost` | — | `just python-check-cost` |
| `python-test-pydantic-floor` | — | `just python-test-pydantic-floor` |

Every job but the last runs a command `check-all` contains.
`python-test-pydantic-floor` runs a focused selector, which
[`core/spec/language-testing.md`](core/spec/language-testing.md) §3 keeps out of
every aggregate, so it is the one gate here that no local aggregate reaches and
CI alone owns — the same division as the 3.13 `python-check-dbfree` leg, where
CI owns the far end of a supported range and the local gate owns what the lock
pins.

`secrets` and `commitlint` are event checks rather than repository verification
gates, and stay native CI steps. The monthly `python-deps-refresh` workflow
uses CPython 3.14 to open a lockfile-upgrade pull request that the jobs above
then gate. The 3.13 `python-check-dbfree` leg proves runtime compatibility only;
the 3.14 leg owns the full database-free gate and its coverage verdicts.
Every other uv-backed CI job is also pinned to CPython 3.14.

## Databases

Database-backed commands need a reachable Docker daemon. The one-time
`~/.testcontainers.properties` setup for runtimes other than Docker Desktop is
in [`README.md`](README.md).

## Command permissions

`.claude/settings.json` allowlists the non-mutating operations by class, so an
ordinary gate run prompts for nothing and the mutating ones still ask.

One residual is outside the repository's reach. An untracked
`.claude/settings.local.json` may sit beside it, and nothing prunes an allowlist
when a recipe is renamed or removed — a local file can still grant commands that
no longer exist. Because it is untracked, no gate can see it and no change here
can fix it; those entries are deleted by hand.
