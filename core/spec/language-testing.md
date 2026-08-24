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
  operation acts on.

A scope is either a **language scope** — one language implementation, which
ships a test suite under a published contract — or a **tooling scope**, which
validates a shared artifact or maintains the repository's own tooling. `core`
and `harness` are tooling scopes. The unscoped repository-wide commands compose
both kinds and are themselves governed by
[§7](#7-command-roles-and-composition). Every rule below binds every scope
unless it names a kind.

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

An operation is **blocking** when its purpose is a verdict: `check`, `test`,
`coverage`, `lint`, `typecheck`, `format-check`, `build`, and `audit` each fail
when what they examine is wrong. `format`, `report`, and `show` are
**non-blocking**: they rewrite, describe, or display, and pass no judgement.
Only blocking commands are gates. An aggregate's verdict is its blocking
dependencies', so it may depend on a non-blocking command for that command's
output without acquiring a second verdict.

## 3. Primary semantic surfaces

A semantic surface is *what a test proves*. Its primary classification comes from
its directory, not from an annotation that restates the directory. Every language
scope MUST provide these six surfaces under its test root:

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

A tooling scope declares no semantic surface. It proves one subject rather than
a portfolio of contracts, so the six-way split has nothing to classify, and the
`test-<surface>` commands do not apply to it.

Focused test commands exist for iteration — a surface command in a language
scope, or any command selecting part of a tooling scope's suite. They MUST NOT
be dependencies of any aggregate. Such selections cross-cut scheduling classes
([§5](#5-scheduling-classification)), so a gate composed out of them selects some
tests more than once.

## 4. Test-root structure

A language scope's test root is closed: every entry under it is a semantic
surface directory, `_support/`, or a file the test runner requires at the root.
Anything else MUST fail enforcement.

- Cross-surface helpers, models, and support code MUST live under `_support/`.
- Support code used by exactly one surface MUST stay inside that surface's
  directory.
- `_support/` is not a semantic surface and gets no `test-*` command.

A tooling scope has no canonical surface set, so it has no closed entry list to
enforce. Its test root MAY stay flat, and it MAY group a coherent subject into
its own directory when that directory is exactly what one focused test command
selects. Which directories exist is its operational guide's fact to record, not
this contract's to fix.

In every test root, a test module MUST NOT import a sibling test module. Shared
symbols belong in a module that exists to be imported — `_support/` where a
language scope has one — so their audience is explicit and collection order is
irrelevant.

## 5. Scheduling classification

A scheduling class is *when and where a test executes*. It is orthogonal to the
semantic surface: one surface may hold tests of several classes, and one class
spans several surfaces.

Every scope that runs tests MUST declare a partition, tooling scopes included: a
repository class aggregate that omits one scope's tests does not gate what its
name claims. A scope that runs no tests declares no class.

Each scope that declares a partition MUST:

- declare an exhaustive, mutually exclusive partition of scheduling classes;
- assign every collected test to exactly one class;
- fail mechanically when a test carries no class or more than one;
- define how a file whose items have differing requirements is handled —
  classified per item, or split so each file is uniform;
- keep the selections of its aggregates disjoint and collectively complete; and
- give every logical gate exactly one execution owner inside the complete
  aggregate ([§7](#7-command-roles-and-composition)).

"Mechanically" excludes review and prose: enforcement MUST live in collection or
in a blocking command. Deriving each test's class from the resources the test
itself requires satisfies this by construction, because neither zero nor two
classes is then representable. A class authored onto a test instead MUST be
checked against those requirements.

A command that owns a scheduling class's execution MUST declare that class as
structured data on itself, in the carrier [§6](#6-runtime-classification) fixes
for the runtime class. The declaration, not the name, is what separates the two
kinds of test command: a scheduling command and a focused one
([§3](#3-primary-semantic-surfaces)) are the same shape, and only the first
declares a class. Graph inspection therefore decides which test commands
[§7](#7-command-roles-and-composition) requires an aggregate to compose, and
which [§3](#3-primary-semantic-surfaces) forbids it from composing, without
reading names.

The resource that defines a class MUST be reachable only through the entry points
the scope designates for it, and that restriction MUST itself be a blocking
check. Otherwise a test can acquire the resource by another route, and its class
silently understates what it needs.

### The classes

The scheduling classes are `dbfree`, `db`, and `cost`. The vocabulary is closed
the way [§2](#2-operation-vocabulary)'s is: a class named anywhere else has no
defined meaning and MUST NOT be declared.

| Class | A test belongs to it when |
|---|---|
| `db` | Running it requires a live database |
| `cost` | Running it requires an interpreter no other test shares |
| `dbfree` | Running it requires neither |

Every class but `dbfree` names one resource, and `dbfree` is the complement of
their union. That is what the derived classification above rests on: a test is
classified by the resources it reaches, so neither zero nor two classes is
representable — reaching none is `dbfree`, and reaching two is a contradiction
the collection hook MUST fail on rather than an order of precedence a reader has
to remember.

`cost`'s resource is an interpreter whose heap the test controls. A reading taken
over the whole process — every tracked object, every reference among them, every
collection walking all of them — is a reading of whatever else the runner loaded
as much as of its own subject: it costs what that process holds, and the floor it
is read against moves with it. Such a measurement is meaningful only in a process
it does not share, which is a requirement on the environment in the same sense a
live database is, and is confined the same way.

Each resource-bearing class is confined by a blocking check, and one of the
scope's class aggregates ([§7](#7-command-roles-and-composition)) MUST run it:
`<scope>-check-database-access` for `db`, and `<scope>-check-instrument-access`
for `cost`. `dbfree` is defined by those resources' absence and owes no such
check, because an absence has no entry point to confine.

A scope declares the classes its own tests populate: both where its tests divide,
and one where the other would hold nothing and the commands
[§7](#7-command-roles-and-composition) derives for it would select no test.

Fixing the vocabulary here, rather than leaving each scope to name its own, is
what makes the entry-point restriction enforceable at all. Which resource a class is
about is not readable from a command graph, so a scope free to invent a class is
a scope whose defining resource nothing can confine, and the restriction binds
only the classes the blocking check [§8](#8-graph-inspection) requires was
already told about. A distinction a scope needs beyond this one is therefore a
change to this section and to that check, not a class declared locally. A
selection that is not about a required resource is no scheduling class in the
first place: it is a focused selector ([§3](#3-primary-semantic-surfaces)), which
cross-cuts the partition and stays out of the gate graph.

## 6. Runtime classification

Runtime class is relative execution duration: `fast`, `medium`, or `slow`. It is
guidance rather than a timing budget, and it is orthogonal to both surface and
scheduling class — a class that needs no database is not necessarily fast.

- Every public execution command MUST declare exactly one runtime class.
- A command's effective runtime class is the slowest one in its transitive
  dependency closure. Any command that declares a class MUST NOT declare one
  faster than its effective class. An aggregate and an execution command with
  prerequisites understate the cost of running them the same way, so the rule
  binds both roles.
- Graph inspection ([§8](#8-graph-inspection)) MUST report the effective class,
  and MUST signal a declaration that understates it.
- The declaration MUST be structured data on the command itself, readable by
  machine from the orchestrator's own output rather than from a separate table.
  Its carrier MUST NOT be one the orchestrator also uses to organize the command
  listing it presents to a reader. A classification and a menu answer different
  questions, so overloading one channel for both degrades the listing exactly as
  the classification approaches complete coverage. The same carrier holds the
  scheduling-class declaration ([§5](#5-scheduling-classification)).

Measured durations are supporting evidence, never an acceptance threshold.

## 7. Command roles and composition

Every public command is exactly one of two roles:

| Role | Rule |
|---|---|
| Execution | Has a command body that performs one operation — the one its name declares — over one subject. Several invocations are that one operation when each is a step of it, and are not when any performs work another entry in [§2](#2-operation-vocabulary) names. What an invocation does decides that, not what the tool it runs is called. It MAY depend on the commands producing its required inputs. |
| Aggregate | Has at least one dependency and no command body. |

No command may compose others while also carrying an unrelated body. A command
with neither a body nor a dependency is not a third role: it is an aggregate
that composes nothing, and MUST fail enforcement.

For each scheduling class `<class>` a scope declares:

- `<scope>-test-<class>` is the execution command owning exactly one test-runner
  invocation for that class; and
- `<scope>-check-<class>` is a dependency-only aggregate over that test command
  plus the quality execution commands assigned to the class.

A language scope MUST additionally expose `<scope>-check`, a dependency-only
aggregate over its scheduling-class aggregates: its language spec names one
complete verification command for the implementation, and nothing else in the
graph provides it. Any other scope MAY expose one.

A scope that declares no scheduling class exposes `<scope>-check` as a
dependency-only aggregate over its execution commands directly.

The repository-wide commands follow the same shape one level up. `check-<class>`
is a dependency-only aggregate over each scope's aggregate for that class, the
complete check aggregate of each scope that declares no class, and the
repository-wide execution commands assigned to the class.

Two aggregates stand over those. `check-all` is a dependency-only aggregate over
every class aggregate plus the repository-wide blocking commands belonging to no
single class: it is the COMPLETE aggregate, and every rule elsewhere in this
contract quantifying over the complete aggregate means it. `check` is a
dependency-only aggregate over the same commands less the class aggregates this
section excludes, and is what a merge gates on.

`cost` is the one class `check` excludes. A gate is worth what the frequency it
is actually run at makes it worth, and `cost` is the slowest class by a wide
margin, paid by every local verification of every change including those that
could not move a byte. Excluding it keeps the command a reader runs after each
change fast enough to keep running, and forfeits no coverage: the class stays in
`check-all`, and [§9](#9-continuous-integration-contract)'s job union gates it on
every proposed change like any other. This is the one place this contract weighs
elapsed time, and it weighs it against how often a gate is run rather than as a
threshold anything passes ([§6](#6-runtime-classification)). Excluding a class is
therefore a change to this section, never a local decision.

`check` is consequently NOT complete, and nothing may describe it as though it
were. Every document naming these commands MUST say which aggregate is complete
and which gates a merge, and [§8](#8-graph-inspection)'s blocking check compares
what they say against the graph.

Every composition rule above quantifies over blocking commands
([§2](#2-operation-vocabulary)). A non-blocking command belongs to no gate, and a
repository that exposes one reachable from nothing is conforming. An aggregate
MAY nonetheless depend on a non-blocking command for its output — a success
summary as a terminal dependency, say — which makes that command neither a gate
nor a second verdict.

An ordering constraint between two commands MUST be expressed as a dependency,
never as adjacency inside one body. A constraint that exists only as line order
is invisible to the graph and is not enforced when either command runs alone.

### Declaration order

The file declaring these commands MUST declare them in one fixed order, and that
order MUST be enforced ([§8](#8-graph-inspection)). Order is the only structure a
reader gets before opening a command, so an enforced one is what lets the file be
scanned rather than read; an unenforced one decays into the order each command
happened to be added in.

- **Top level.** The repository-wide blocking commands
  ([§2](#2-operation-vocabulary)), then the repository-wide non-blocking ones,
  then one section per scope — the tooling scopes, then the language scopes, each
  kind alphabetically.
- **Within a section.** Aggregates, the scheduling-class test commands
  ([§5](#5-scheduling-classification)), the semantic-surface commands
  ([§3](#3-primary-semantic-surfaces)), the remaining focused selectors, the
  remaining execution commands, then the mutating helpers.

Both orders run from what composes the most to what composes the least: the top
level from the commands spanning every scope down to one scope's own, and each
section from its aggregates down to the single-purpose commands, ending with the
one operation that rewrites tracked sources. A command the orchestrator requires
but the grammar does not govern — its own default entry point — is not part of
the public interface and sits outside this order.

## 8. Graph inspection

The orchestrator's command graph is the single authoritative description of what
verification runs. A second gate manifest MUST NOT be introduced.

- Inspection MUST read the orchestrator's own structured output, so the
  description cannot disagree with what executes.
- The repository MUST provide a `show` command that displays the resolved
  graph: dependencies, execution owners, scheduling classes, prerequisites, and
  runtime classes.
- Where the graph violates this contract in a way the display would otherwise
  render as ordinary output — a command composing nothing, a declaration its own
  closure outruns — the display MUST say so. Failing on it stays the blocking
  command's job; describing the graph as it is stays the display's.
- The repository MUST provide a blocking `check` command over that graph,
  failing on naming, declaration-order, role, scheduling-composition,
  declared-metadata, test-layout, runner-configuration, documentation, and CI
  drift. `check` MUST depend on it: a graph that has drifted is a gate that has
  drifted, and a merge is what that costs.

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
