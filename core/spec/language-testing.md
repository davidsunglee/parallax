# Language Testing Contract

This document is the normative cross-language contract for how an implementation
organizes its tests and exposes them as verification commands. It fixes the
vocabulary and the structural rules. It fixes no test framework, no runner
mechanism, and no command names.

Rationale for these rules lives here and only here, in
[Why this shape](#why-this-shape). A completed language spec records that
language's quality policy — thresholds, matrices, exclusions, and required proof.
An implementation's operational guide records that implementation's concrete
mapping — its directories, its classes, its commands, and its CI jobs. Neither
restates the rules below.

## 1. Command grammar

Every public verification command MUST read:

```text
<scope>-<operation>[-<qualifier>]
```

- **scope** — omitted for a repository-wide command; otherwise `core`, `harness`,
  or a language name.
- **operation** — exactly one entry from the closed vocabulary in [§2](#2-operation-vocabulary).
- **qualifier** — a scheduling class ([§5](#5-scheduling-classification)), a
  semantic surface ([§3](#3-primary-semantic-surfaces)), or the subject the
  operation validates.

A renamed command MUST NOT keep an alias under its former name. Two spellings of
one gate defeat the point of a scannable interface, and the stale one outlives
every document that would have explained it.

In this repository these commands are the root `justfile`'s public recipes.

## 2. Operation vocabulary

The vocabulary is closed. A command whose operation is not listed here has no
defined meaning and MUST NOT be introduced.

| Operation | Means |
|---|---|
| `check` | Non-mutating blocking validation, or an aggregate of blocking validation |
| `test` | Test-runner execution only |
| `coverage` | Coverage-policy evaluation over test output |
| `lint` | Lint rules only |
| `typecheck` | Static type analysis only |
| `format-check` | Non-mutating formatting validation |
| `format` | Formatting applied in place |
| `build` | Artifact production |
| `audit` | Dependency or artifact risk checks |
| `report` | Non-blocking diagnostic output |
| `show` | Resolved configuration or graph display |

`format` is the only operation that rewrites tracked sources; no other operation
may modify them. `build` and `test` additionally produce untracked output —
artifacts and coverage data. A command's effect therefore follows from its name,
which is what lets tooling and permission policy reason about safety
syntactically.

## 3. Primary semantic surfaces

A semantic surface is *what a test proves*. Its primary classification comes from
its directory, not from an annotation that restates the directory. Every language
implementation MUST provide these six surfaces under its test root:

| Surface | Directory | Focused command |
|---|---|---|
| Internal behavior | `unit/` | `<language>-test-unit` |
| Portable specification behavior | `compatibility/` | `<language>-test-compatibility` |
| Idiomatic public API | `api/` | `<language>-test-api` |
| Core `m-dialect` contract | `dialect/` | `<language>-test-dialect` |
| Provider integration contract | `provider_contract/` | `<language>-test-provider-contract` |
| Shipped and installed output | `distribution/` | `<language>-test-distribution` |

`dialect/` is mandatory for every implementation: `m-dialect` is an active core
module, not one language's local concern.

An additional surface is permitted only for a genuinely distinct contract, and
requires synchronized updates to the language spec, the implementation's
operational guide, its commands, its CI jobs, and its drift enforcement.

Focused surface commands exist for iteration. They MUST NOT be dependencies of
any aggregate. Surfaces cross-cut scheduling classes
([§5](#5-scheduling-classification)), so a gate composed out of them selects some
tests more than once.

## 4. Closed test-root structure

The test root is closed: every entry under it is one of the following, and
anything else MUST fail enforcement.

- Cross-surface helpers, models, and support code MUST live under `_support/`.
- Support code used by exactly one surface MUST stay inside that surface's
  directory.
- Only files the test runner requires at the root may live directly under the
  test root.
- `_support/` is not a semantic surface and gets no `test-*` command.

A test module MUST NOT import a sibling test module. Shared symbols belong in
`_support/`, where their audience is explicit and collection order is irrelevant.

## 5. Scheduling classification

A scheduling class is *when and where a test executes*. It is orthogonal to the
semantic surface: one surface may hold tests of several classes, and one class
spans several surfaces.

Each language implementation MUST:

- declare an exhaustive, mutually exclusive partition of scheduling classes;
- assign every collected test to exactly one class;
- fail mechanically when a test carries no class or more than one;
- define how a file whose items have differing requirements is handled —
  classified per item, or split so each file is uniform;
- keep the selections of its aggregates disjoint and collectively complete; and
- give every logical gate exactly one execution owner inside a complete
  aggregate.

"Mechanically" excludes review and prose: enforcement MUST live in collection or
in a blocking command. Deriving each test's class from the resources the test
itself requires satisfies this by construction, because neither zero nor two
classes is then representable. A class authored onto a test instead MUST be
checked against those requirements.

The resource that defines a class MUST be reachable only through the entry points
the implementation designates for it, and that restriction MUST itself be a
blocking check. Otherwise a test can acquire the resource by another route, and
its class silently understates what it needs.

## 6. Runtime classification

Runtime class is relative execution duration: `fast`, `medium`, or `slow`. It is
guidance rather than a timing budget, and it is orthogonal to both surface and
scheduling class — a class that needs no database is not necessarily fast.

- Every public execution command MUST declare exactly one runtime class.
- An aggregate's runtime class MUST be the slowest one in its transitive
  dependency closure, and MUST NOT understate it.
- The declaration MUST be structured data on the command itself, readable by
  machine from the orchestrator's own output rather than from a separate table.

Measured durations are supporting evidence, never an acceptance threshold.

## 7. Command roles and composition

Every public command is exactly one of two roles:

| Role | Rule |
|---|---|
| Execution | Has a command body and owns one coherent operation. It MAY depend on the commands producing its required inputs. It MUST NOT inline unrelated lint, typecheck, build, audit, or test work. |
| Aggregate | Has dependencies and no command body. |

No command may compose others while also carrying an unrelated body.

For each declared scheduling class `<class>`:

- `<language>-test-<class>` is the execution command owning exactly one
  test-runner invocation for that class;
- `<language>-check-<class>` is a dependency-only aggregate over that test
  command plus the quality execution commands assigned to the class; and
- `<language>-check` is a dependency-only aggregate over the scheduling-class
  aggregates.

An ordering constraint between two commands MUST be expressed as a dependency,
never as adjacency inside one body. A constraint that exists only as line order
is invisible to the graph and is not enforced when either command runs alone.

## 8. Graph inspection

The orchestrator's command graph is the single authoritative description of what
verification runs. A second gate manifest MUST NOT be introduced.

- Inspection MUST read the orchestrator's own structured output, so the
  description cannot disagree with what executes.
- The repository MUST provide a `show` command that displays the resolved
  graph: dependencies, execution owners, scheduling classes, prerequisites, and
  runtime classes.
- The repository MUST provide a blocking `check` command over that graph,
  failing on naming, ordering, role, scheduling-composition, declared-metadata,
  test-layout, runner-configuration, and CI drift. The repository's own check
  aggregate MUST depend on it.

## 9. Continuous integration contract

CI MUST use the same interface as local verification.

- A job's identifier matches the command it executes.
- The job's primary verification step invokes that command directly.
- A job MAY expand one command across a declared language-version or database
  matrix; the expansion MUST be recognizable as intentional rather than as
  duplicate ownership.
- A job MUST NOT embed a raw test, lint, build, coverage, or audit command when a
  canonical command owns that gate.
- Setup, dependency installation, secret scanning, and event-specific checks MAY
  remain native CI steps, because they are not repository verification gates.
- The union of jobs MUST cover the complete required repository check graph, even
  when CI parallelizes its dependencies instead of invoking the top aggregate.

## Why this shape

**Duplicate execution is a selection problem, not a text problem.** Two commands
with distinct text still run the same tests twice when their selections overlap,
and nothing in the output says so. A classification that is a cross-cutting
property rather than a partition is the usual cause: it becomes a superset of
selections that are also run separately, and the intersection executes once per
selection. Partitioning the scheduling classes and keeping the cross-cutting
surfaces out of the gate graph removes the overlap by construction instead of by
vigilance.

**What a test proves and when it can run are independent.** Collapsing them onto
one axis forces false choices — a surface that must be split because half of it
needs a database, or a class that must be widened because a surface straddles it.
Two orthogonal classifications, one from the directory and one from the
requirements, keep both questions answerable.

**Derived classification makes the bad state unrepresentable.** A class computed
from what a test requires cannot be absent, cannot be doubled, and cannot
disagree with the test. A class authored beside the test can do all three, which
is why authoring it obliges a separate check that it still matches.

**Roles exist so the graph can be reasoned about mechanically.** A body that
inlines unrelated operations hides its steps from the graph, so no tool can tell
which gates ran or find their owner. An aggregate that also carries a body cannot
be composed without re-running that body.

**One authoritative graph.** Any second description of the gates — a table, a
manifest, a job list — drifts from the graph it describes. Deriving inspection
from the orchestrator's own output makes drift between description and behavior
impossible, and reduces the remaining checks to comparing the other
representations against that one source.

**A grammar makes an unfamiliar command legible.** Scope, effect, and safety are
readable from the name, without opening the orchestrator's file, and a permission
policy can then be written against operations rather than against an enumerated
list that ages every time a command is added.
