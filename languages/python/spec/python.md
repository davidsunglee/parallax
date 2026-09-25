# Python binding

Python implements the canonical slice below. Core owns its capability claim and
portable behavior; this binding records only Python-specific public choices and
the independently checked dependency/artifact topology.

```language-binding
{"slice":"slice-snapshot-1"}
```

## Public contracts

- [Declarations](declarations.md): class authoring, names, scalar carriers,
  editing, and descriptor/metadata boundaries.
- [Queries and results](queries-and-results.md): Python expressions, temporal
  spelling, result access, Wire projection, and stream lifetime.
- [Execution](execution.md): model publication, root/scope composition,
  transaction options, Python failure boundaries, and observation spelling.

Stable diagnostic text may still use the former monolithic section addresses.
For navigation, §2 moved to the declarations and queries pages, §3 to the
declarations and execution pages, §4 to queries and results, and §5 to execution.

The [core module index](../../../core/spec/modules.md) routes portable semantics;
[slices](../../../core/spec/slices.md) owns the canonical claim. Public Python
signatures and types live in their defining modules. The [API suite](../tests/api/)
owns executable usage examples and the generated guide. Private implementation
structure does not require a public binding specification change.

## Dependency and artifact contracts

The following two sections remain independent specification inputs to dependency
enforcement. Their numbering is retained for the validators and existing links.
Changing a source boundary, an external-package grant, or a deployable artifact
requires updating and validating these contracts together with implementation.

## 7. Source-enforcement topology

A claim about observable behavior is graded by behavior at the API boundary,
never by inspecting source structure. This specification constrains structure
only where a decision is itself about the source: which scope owns a module and
which artifact ships it, what a surface exports and what it keeps private,
whether anything is generated and where it lands, and what the toolchain runs.
That test is the rule, and it is applied to a sentence wherever the sentence
stands. The [binding pages](#public-contracts), §8, and
[workspace configuration](../pyproject.toml) hold such decisions, and the enforcement
scopes and reaches are recorded here; that list orients a reader and bounds
nothing, so a structural decision standing in a section it does not name answers
to the same test rather than being licensed by its absence from it. A behavioral
section that phrases a consequence as a fact about source text has misplaced it —
restate it as what a caller observes, or record it here.

Behavioral modules map onto Python submodules (enforcement scopes) inside the
distributions of §8. `m-metamodel`, `m-model-formation`, `m-inheritance`,
`m-storage-layout`, and `m-relationship` own the dedicated
`parallax.core.metamodel`, `parallax.core.model_formation`,
`parallax.core.inheritance`, `parallax.core.storage_layout`, and
`parallax.core.relationship` scopes.
`parallax.core._formation_profile` is the built-in Model Formation
composition root; its declared grants are exactly the formation runner plus every
module whose Formation Manifest row supplies a Rule Set or compiler, and
`m-pk-gen` supplies neither and is not imported. Every behavioral scope reaches
the metamodel it needs through `m-metamodel` and the typed owner facets.
`m-descriptor` maps to the separate `parallax.descriptor` scope and imports the
common runtime only through its language-neutral `m-core`, `m-metamodel`, and
`m-inheritance` edges — the last because a descriptor document may declare an
inheritance family that never forms, and the pre-formation walk that classifies
such a family reports it in `m-inheritance`'s own rule vocabulary rather than
minting a second one. Its private child support scope `parallax.descriptor._hub` alone imports
the Python-specific Domain Model construction and accepted-model read seams in
`parallax.core.entity`. This direct support edge is required because the class
and Descriptor Frontends deliberately return one concrete `DomainModel` type,
while the Domain Model's class-backed constructor owns Python realization and
therefore does not belong to the
representation-independent `parallax.core.metamodel` module. No
common-runtime, Snapshot, or Postgres scope imports the descriptor package.

The enforcement unit is the **scope**, not a package's `__all__`: an importer
granted `parallax.core.entity` reaches every module that scope owns, private
ones included. Three Snapshot modules use that grant for six names the Entity
frontend deliberately does not export — `parallax.snapshot._inspection` and
`parallax.snapshot.handle._write_inputs` read what a class carries from
`parallax.core.entity._declaration` (`declaration_of`, `is_entity_class`,
`members_of`, and the family-merged member-name correspondences
`wire_names_of`), and `parallax.snapshot.handle._database` reads the accepted
Metamodel and the class index from `parallax.core.entity._model` (`model_of`,
`class_index`), the two facts it prepares a selection over.
Each is a seam between two first-party packages that a developer
never needs, so exporting the names to spell the reach publicly would widen the
developer surface to serve one lifecycle package. None of the three modules
takes a scope row of its own: they belong to `parallax.core.entity`, whose edge
every importer above already declares, and
`parallax.core.entity._construction_input`, `._expressions`, `._instance_state`,
`._layout`, and `._pydantic_storage` carry rows below because each needs a
NARROWER grant than its parent — not because they are the only children an
importer may reach.

`parallax.core.entity._instance_state` owns the physical backing beneath a
published Entity or Value Object — the per-class publication plan, the compact
slot, the tuple and its presence bitmap, both Adapters, and the Pydantic root
that answers for a value's instance state — and its grant row is what keeps that
a deep module rather than a second declaration engine. Granted two siblings and
nothing else, it can reach neither the engine that builds a class nor the writer
that publishes one, so a publication plan has to ARRIVE as plain data the engine
computed rather than be derived here from a model the scope could import.
`._construction_input` is the first sibling, and is granted `(none)`: the
sentinels a positional construction input spells, and the opaque handle a
relationship position names a node by, are read by the layout side, by a runtime
that lays a stored row out against one, by the writer, by the descriptors that
answer a member read, and by the backing above, which are scopes that
deliberately cannot reach one another — so they are housed where every one of
them may reach and nothing may be reached back, which is also what keeps a row's
producer structurally unable to reach the writer, `construct`, or model
formation. `._pydantic_storage` is the second, and is granted `(none)` for its own
reason: it reaches a value's attribute storage past every binding over it —
including the framework's own presentation, which is layered directly on it —
and what it reaches is Pydantic's own slot descriptors and nothing else, so a
first-party import of any kind would mean it had grown a second job. All three
are **sealed**, for the reason the three below them are.

`parallax.core.entity._layout` is reached the other way round. It carries a row
of its own because a runtime that materializes values from stored rows needs the
member layouts — the positions a row is laid out at and the canonical
broad-relationship order a full-width relationship row is written at — without
the frontend's own closure. So every Snapshot module that carries one
connection's cataloged model, or the layouts inside it, names the declared scope
that owns what it reads rather than reaching a private module through the
parent's edge; the same is true of the sentinel a row spells absence with, which
is why that runtime is granted `._construction_input` as well. Both are
**sealed**, because "nothing else" is a claim about the package they sit in as
much as about the ones they do not.

`parallax.core.object_query._fluent` is the one child scope declared for the
opposite reason: it needs a WIDER grant than its parent. The typed Object Query is
generic over Entity Classes, so it reaches the Entity frontend for the descriptor
values a clause call is written with, while `m-object-query` itself must stay
reachable by `m-temporal-read`, `m-deep-fetch`, `m-sql`, and the read-preflight
seam — none of which may reach that frontend. The parent package's own interface
therefore does not import this module: a consumer of the canonical query value
never pulls the typed surface in, and one that wants the typed surface names this
module. That is what keeps the widening contained rather than leaking through the
package.

`parallax.snapshot.handle._read_scope` is the read composition both modeled execution surfaces
delegate to, scoped apart from its package so its row states what a read ladder
reaches and what it does not: the query and temporal vocabulary it lowers
through, the page plan a stream is delivered against, the read result it
publishes, the Database Port, the unit of work, and the lifecycle activities it
opens — and none of batch writes, Transaction-Time writes, or Bitemporal writes,
which nothing in that closure names. Bounded automatic retry is deliberately NOT
among the exclusions, and the row does not claim it: `modules.md` declares
`m-execution-lifecycle --> m-auto-retry`, and a forbidden row is the complement
of a closure, so a scope granted the lifecycle module it needs for the re-entry
gate and the read roots carries retry with it whatever the composition itself
imports. What the row says about retry is that this scope inherits it, not that
it is forbidden. Write lowering is a child scope of the same parent, which the
general target set excludes, so not importing it is the only exclusion available
there.

`parallax.snapshot.handle._keyed_writes` is the keyed write ingress both
representations enter, scoped apart from its package for the converse reason:
its row states what a keyed write reaches and what it does not. A keyed write
addresses a row its caller already holds, so it resolves nothing from the store,
and the read half of the parent's grant falls outside this closure — row-to-graph
materialization, the read result, and the read lock are each forbidden here and
each granted to the parent. So are batch writes, Transaction-Time writes, and
Bitemporal writes, which the sibling lowering scopes own. `m-db-port`,
`m-deep-fetch`, and `m-navigate` are deliberately NOT among those exclusions,
and the row does not claim them: `modules.md` routes the port through
`m-execution-lifecycle`, which the re-entry gate requires, and the two traversal
modules through `parallax.core.entity`, whose values every Typed write is stated
over. A forbidden row is the complement of a closure, so each rides in whatever
the ingress itself imports, and what the row says about them is that this scope
inherits them rather than that they are forbidden. `m-document-codec` IS named
for the opposite reason, and not because the closure would otherwise lack it:
`parallax.core.entity` already carries the codec in, exactly as it carries the two
traversal modules, so naming it moves no generated contract. What the row states
is direct use — an effective change set is the codec's answer and the ingress asks
for it itself — which is what tells a reader where the ingress's own imports end
rather than leaving the codec to be inferred from a transitive edge. The
verb-input step library this ingress composes, the family answers it resolves
through, and the predicate-selected lane beside it are all modules of the parent
package rather than declared scopes, so no contract can name any of them either
way.

A behavioral module maps to the scope that needs its whole edge set.
`m-execution-lifecycle` is owned by `parallax.core.execution_lifecycle`, while
the Snapshot handle package is the composition scope that publishes snapshot reads and
streams through the injected internal publisher. Snapshot results and Page /
Root View representation scopes neither import the lifecycle module nor retain
events. The delivery-materialization seam imports lifecycle activities because
it owns statement execution and Page assembly, but retains no event history.
This keeps observation at the delivery boundary without granting SQL generation
to Page / Root View representation.

import-linter forbids every production scope-pair import the DAG does not
permit — the generated forbidden-edge complement below, with the
conformance-family scopes exempted as importers per `modules.md` — so illegal
non-edges are rejected, not merely wrong directions; artifact separation never
legalizes a forbidden edge.

A grant names a whole scope, so a scope granted a parent may ordinarily import
anything nested inside it. A child whose import policy the child-scope table
below states as **isolated** is the exception: it is a forbidden target in every
production row that neither contains it nor is contained by it, whatever those
rows are granted, so reaching it is a rejected import rather than an unstated
grant. The rows carrying that policy are the whole of it. The one import no row
can reject is its own ancestors' —
a forbidden entry there would overlap that contract's source, and import-linter
skips it — so `tools/check_scope_ownership.py` rejects that edge over the files
instead, resolving relative imports and reading an imported name as a possible
submodule, so no spelling escapes — neither the dotted path nor the relative
one, and neither naming the scope nor naming a member of it. No production
module imports an isolated scope, and the two halves together are what enforce
it.

A child whose policy is **sealed** is that same overlap seen from the other
side: one whose row is the whole of what it imports, inside the package holding
it as well as outside it. A row can neither forbid what sits inside its own source
package nor except it, so it refuses a neighbour only through the chain that
leaves it — reaching one whose own closure escapes the row is reported at
whatever it escapes to, which is what keeps the writer, `construct`, and model
formation out of reach of the scopes below. A neighbour that reaches nothing the
row does not already permit leaves no chain to report, so nothing rejects that
import, and a narrow grant's completeness would rest on what the modules beside
it happen to import. The same `tools/check_scope_ownership.py` walk closes that
residue over the sealed scope's own files, in every spelling, so what a sealed
scope reaches inside its parent package is what its row grants and nothing more,
and a granted sibling stays legal however the import that reaches it is written.
The rows carrying that policy are the whole of it; an **ordinary** child is
judged by its contract alone, and reaching a private module of its parent is
what child scopes ordinarily do. Write-observation
retention is sealed for the rule read the other way round: the find executor
drives it while its rows are live, and retention names nothing of that executor
back. The executor is a module of the parent package, so no contract sourced at
the child can reject that import, and the seal is where the one-way rule is
graded rather than merely stated.

`parallax.snapshot.handle._publication` is sealed for what a prepared Model
Selection must not hold ([Models, roots, and scopes](execution.md#models-roots-and-scopes)): every
other module of the handle package carries a connection, an attempt, or an
activity, and a selection that could name one would no longer be process-local
state a Serving Model can hand to any execution. Its row — the Entity frontend
and `m-unit-work` — is the whole of what the selection, its projections, and
the Serving Model reach, and the seal is where that absence is graded over the
package they live in rather than merely stated.

Sealing generates nothing, so a scope losing that policy silently keeps every
contract it had; isolation shapes the target set of nearly every generated
contract, so losing it changes them all at once. Each child's parent and policy
are therefore declared exactly once — one row of the child-scope table below,
naming the parent the policy's guarantee is stated against — and
`tools/check_dag_sync.py` compares that table, parent and policy alike, with the
`CHILD_SCOPES` table `tools/check_scope_ownership.py` enforces, so declaring a
child in one place alone, against the wrong parent, under the wrong policy, or
twice — a second row is a contradiction to reject, not a later reading to keep —
fails the sync check.

The relations this section declares are stated as four strict tables, each the
whole of one relation and each read back by `tools/check_dag_sync.py` and
compared with the one declaration the tool holds of it: the behavioral mapping
with `MODULE_SCOPE` and the `PYTEST_BOUNDED_SCOPES` row beside it, the
first-party support relation with `PYTHON_FIRST_PARTY_GRANTS`, the
restricted-external ownership with `RESTRICTED_EXTERNAL_GRANTS`, and the child
topology with `CHILD_SCOPES`. A table edited alone, or a declaration edited
alone, fails the sync check before anything is generated, and `--write`
regenerates nothing past a disagreement. A cell declares only what it spells
in backticks, and a cell holding anything beside its backticked names is
rejected rather than read around; the two bare spellings are `(none)` as the
whole of an empty grant and the import policy word, each stated by the table
that uses it. Source paths, enforcement-tool names, and descriptive labels
stay out of the tables and are stated once in prose after them.

The first table maps every behavioral module — each claimed module and each
unclaimed transitive prerequisite — to the enforcement scope that owns it. A
behavioral module's allowed direct dependencies are its edges in the fenced
`dependency-graph` block of `core/spec/modules.md`, mapped through this table,
and are restated nowhere here. `m-api-conformance` is the one module whose
scope is not a `parallax` package: `tests.api` is a pytest collection boundary,
which is what enforces it, so its row satisfies the core template's
row-per-module rule and is the one row `tools/check_dag_sync.py` compares with
its `PYTEST_BOUNDED_SCOPES` declaration rather than with `MODULE_SCOPE`, which
holds only the scopes contracts are sourced from; the row is required as that
declaration spells it, so dropping it or mapping the module into the package
tree fails the sync check.

| Behavioral module | Enforcement scope |
|---|---|
| `m-api-conformance` | `tests.api` |
| `m-auto-retry` | `parallax.core.auto_retry` |
| `m-batch-write` | `parallax.core.batch_write` |
| `m-bitemp-write` | `parallax.core.bitemp_write` |
| `m-case-format` | `parallax.conformance.case_format` |
| `m-conformance-adapter` | `parallax.conformance.cli` |
| `m-core` | `parallax.core.base` |
| `m-db-error` | `parallax.core.db_error` |
| `m-db-port` | `parallax.core.db_port` |
| `m-deep-fetch` | `parallax.core.deep_fetch` |
| `m-descriptor` | `parallax.descriptor` |
| `m-dialect` | `parallax.core.dialect` |
| `m-document-codec` | `parallax.core.document_codec` |
| `m-edit` | `parallax.core.entity._edit` |
| `m-execution-authority` | `parallax.snapshot.handle._execution_authority` |
| `m-execution-lifecycle` | `parallax.core.execution_lifecycle` |
| `m-inheritance` | `parallax.core.inheritance` |
| `m-metamodel` | `parallax.core.metamodel` |
| `m-model-evolution` | `parallax.evolution.model_evolution` |
| `m-model-formation` | `parallax.core.model_formation` |
| `m-navigate` | `parallax.core.navigate` |
| `m-object-query` | `parallax.core.object_query` |
| `m-opt-lock` | `parallax.core.opt_lock` |
| `m-pk-gen` | `parallax.core.pk_gen` |
| `m-predicate` | `parallax.core.predicate` |
| `m-read-lock` | `parallax.core.read_lock` |
| `m-relationship` | `parallax.core.relationship` |
| `m-schema-delta` | `parallax.evolution.schema_delta` |
| `m-snapshot-read` | `parallax.snapshot._read_result` |
| `m-sql` | `parallax.core.sql_gen` |
| `m-storage-layout` | `parallax.core.storage_layout` |
| `m-temporal-read` | `parallax.core.temporal_read` |
| `m-txtime-write` | `parallax.core.txtime_write` |
| `m-unit-work` | `parallax.core.unit_work` |
| `m-value-object` | `parallax.core.value_object` |
| `m-wire` | `parallax.core.wire` |

The second table declares the edges no module tag carries: for a support scope,
which has no tag and so no edge in `core/spec/modules.md`, everything it may
import directly; for a behavioral scope, the Python-only supplement to its
tagged edges — `parallax.core.db_port` and `parallax.core.execution_lifecycle`
each reach the detached diagnostic projection this way, and
`parallax.snapshot._read_result` reaches the row-to-graph package it publishes
results from, a Python scope with no language-neutral tag. A behavioral scope
with no such supplement has no row. The dependency cell holds `(none)` alone
or comma-separated backticked tokens, each a module tag or a `parallax.*`
scope a row of the first two tables declares; a token of any other shape is
rejected rather than skipped — a third-party package is never a grant here,
and is declared by the restricted-external table below — and `(none)` beside
a real grant is a contradiction rather than a wider grant. A scope granting
nothing must still be declared, because its emptiness is what it enforces. A
group of scopes sharing one grant names every member in the scope cell: the
write-execution cluster is the one such group, enforced as one boundary so that
helpers may move between its three modules without a spec edit. Each scope is
declared by exactly one row, a second row being a contradiction to reject
rather than a later reading to keep.
`parallax.descriptor._hub --> parallax.core.entity` is the descriptor
distribution's sole Python-only edge; the parent `m-descriptor` scope's
`m-core`, `m-metamodel`, and `m-inheritance` edges remain language-neutral and
come from `core/spec/modules.md`.

| Enforcement scope | Allowed direct first-party dependencies |
|---|---|
| `parallax.aws` | `m-db-port` |
| `parallax.aws.postgres` | `m-db-port`, `parallax.postgres` |
| `parallax.core._formation_profile` | `m-metamodel`, `m-model-formation`, `m-inheritance`, `m-storage-layout`, `m-value-object`, `m-relationship`, `m-temporal-read`, `m-opt-lock` |
| `parallax.core.continuation` | `m-metamodel`, `m-inheritance`, `m-predicate`, `m-object-query`, `m-temporal-read`, `m-wire` |
| `parallax.core.db_port` | `parallax.core.diagnostics` |
| `parallax.core.diagnostics` | (none) |
| `parallax.core.entity` | `m-core`, `m-metamodel`, `m-inheritance`, `m-relationship`, `m-predicate`, `m-object-query`, `m-temporal-read`, `m-document-codec`, `parallax.core._formation_profile` |
| `parallax.core.entity._construction_input` | (none) |
| `parallax.core.entity._expressions` | `m-core`, `m-wire`, `m-metamodel`, `m-predicate`, `m-object-query`, `m-document-codec` |
| `parallax.core.entity._instance_state` | `parallax.core.entity._construction_input`, `parallax.core.entity._pydantic_storage` |
| `parallax.core.entity._layout` | `m-metamodel`, `m-inheritance`, `m-relationship` |
| `parallax.core.entity._pydantic_storage` | (none) |
| `parallax.core.execution_lifecycle` | `parallax.core.diagnostics` |
| `parallax.core.object_query._fluent` | `m-core`, `m-metamodel`, `m-predicate`, `parallax.core.entity` |
| `parallax.descriptor._hub` | `parallax.core.entity` |
| `parallax.postgres` | `m-core`, `m-wire`, `m-db-port`, `m-db-error`, `m-dialect` |
| `parallax.snapshot._inspection` | `parallax.core.entity`, `m-metamodel`, `m-inheritance`, `m-relationship`, `m-temporal-read` |
| `parallax.snapshot._read_result` | `parallax.snapshot.materialize` |
| `parallax.snapshot.handle` | `parallax.core.continuation`, `parallax.snapshot.materialize`, `parallax.snapshot._read_result`, `parallax.snapshot._inspection`, `parallax.core.entity`, `m-core`, `m-wire`, `m-metamodel`, `m-predicate`, `m-inheritance`, `m-storage-layout`, `m-temporal-read`, `m-deep-fetch`, `m-navigate`, `m-dialect`, `m-db-port`, `m-sql`, `m-unit-work`, `m-read-lock`, `m-auto-retry`, `m-execution-lifecycle`, `m-opt-lock`, `m-batch-write`, `m-txtime-write`, `m-bitemp-write` |
| `parallax.snapshot.handle._errors` | (none) |
| `parallax.snapshot.handle._family`, `parallax.snapshot.handle._keyed_sql`, `parallax.snapshot.handle._write_lowering` | `m-core`, `m-wire`, `m-metamodel`, `m-inheritance`, `m-storage-layout`, `m-document-codec`, `m-temporal-read`, `m-dialect`, `m-db-port`, `m-sql`, `m-unit-work`, `m-opt-lock`, `m-txtime-write`, `m-bitemp-write` |
| `parallax.snapshot.handle._keyed_writes` | `parallax.core.entity`, `parallax.snapshot._inspection`, `m-metamodel`, `m-document-codec`, `m-temporal-read`, `m-unit-work`, `m-execution-lifecycle` |
| `parallax.snapshot.handle._materialization` | `parallax.core.continuation`, `parallax.snapshot.materialize`, `parallax.snapshot._read_result`, `parallax.snapshot._inspection`, `parallax.core.entity`, `m-metamodel`, `m-inheritance`, `m-temporal-read`, `m-db-port`, `m-sql`, `m-read-lock`, `m-execution-lifecycle` |
| `parallax.snapshot.handle._preflight` | `m-metamodel`, `m-predicate`, `m-object-query` |
| `parallax.snapshot.handle._publication` | `parallax.core.entity`, `m-unit-work` |
| `parallax.snapshot.handle._read_scope` | `parallax.core.entity`, `parallax.core.continuation`, `parallax.snapshot._read_result`, `parallax.snapshot._inspection`, `m-object-query`, `m-temporal-read`, `m-db-port`, `m-unit-work`, `m-read-lock`, `m-opt-lock`, `m-execution-authority`, `m-execution-lifecycle` |
| `parallax.snapshot.handle._retention` | `m-metamodel`, `m-unit-work`, `m-temporal-read`, `parallax.snapshot.handle._family` |
| `parallax.snapshot.materialize` | `parallax.core.entity`, `parallax.core.entity._construction_input`, `parallax.core.entity._layout`, `parallax.snapshot._inspection`, `m-deep-fetch`, `m-document-codec`, `m-metamodel`, `m-inheritance`, `m-relationship`, `m-temporal-read`, `m-wire` |

Third-party packages are outside every scope, and a first-party grant says
nothing about them. A **restricted external package** is one the framework
confines to the scopes that own the substrate it provides — the Pydantic
packages beneath an Entity value, the Psycopg packages beneath the Postgres
adapter, and botocore beneath the AWS credential provider — and the table below
is the whole of who may import each one
**directly**. The package column names the top-level import name, never a
distribution or a submodule: import-linter forbids an external only as one
top-level node and folds every submodule import into it, so `pydantic` covers
`pydantic.fields` and `pydantic_core` is a package of its own.
`tools/check_dag_sync.py` parses the table, requires each owner to be a
declared production scope or `parallax.conformance`, compares it with its own
`RESTRICTED_EXTERNAL_GRANTS` table — a package or an owner added to either
alone fails the sync check before anything is generated — and emits one
`forbidden` contract per package, sourced from every production scope the row
does not grant and confined to **direct** imports (`allow_indirect_imports`).
A blocked scope inside a blocked ancestor's package is left to the ancestor's
entry. A granted child inside a blocked ancestor's package is delegated back to
the child by two `ignore_imports` expressions, the module and its undeclared
descendants, and such a child must be a leaf of the child topology: import-linter
has no expression for a package less a declared child beneath it, so generation
refuses rather than widening the grant. The import-linter roots are derived,
not listed: the top package of every declared scope, and `parallax.conformance`.
The package interfaces no scope owns — each root outside the conformance tree
that is not itself a declared scope, today `parallax.core`,
`parallax.evolution`, and `parallax.snapshot` — are derived from those roots and
sourced exactly, as modules rather than packages, in one further contract over
every restricted package. The direct-only shape is what lets the first-party closure
stay deep: a scope granted `parallax.core.entity` reaches Pydantic through the
Entity frontend and never names it, so Snapshot reaches an Entity value's
substrate without importing it, and a Snapshot module that imports `pydantic`
fails `just python-check-imports` on the `pydantic` contract.

A grant here is a permission to name the package, and nothing else carries one.
It enters no closure, so first-party reachability confers nothing:
`parallax.core.entity._pydantic_storage` owns `pydantic` while its first-party
row grants `(none)`. A parent's grant does not carry its declared children:
every Entity child that imports the substrate is granted it by name, and
`._construction_input`, `._expressions`, and `._layout`, which do not, are
contract sources of their own. Ownership is independent of §8's manifests both
ways: a manifest dependency never grants source permission —
`parallax-snapshot` installs Pydantic through `parallax-core` and may not import
it — and a source grant needs no direct manifest declaration.

`parallax.conformance` is granted `pydantic` and `psycopg`. Its edit-model
fixtures (`edit_models.py`, `edit_runner.py`) are deliberately native Pydantic
models that witness the Entity frontend from outside it, so rewriting them over
the frontend — the alternative considered — would weaken what they witness, and
was rejected. Its Postgres control seam imports the driver for the sessions the
harness opens that no application would (*the conformance family's accepted
private reaches*, below). Both grants are parity-checked documentation and
generate no contract, because no contract is sourced from a conformance scope.
The contracts therefore enforce the Pydantic and Psycopg boundaries for the
framework's own scopes.

| Restricted external package | Granted enforcement scopes |
|---|---|
| `pydantic` | `parallax.core.entity`, `parallax.core.entity._edit`, `parallax.core.entity._instance_state`, `parallax.core.entity._pydantic_storage`, `parallax.conformance` |
| `pydantic_core` | `parallax.core.entity._instance_state` |
| `psycopg` | `parallax.postgres`, `parallax.aws.postgres`, `parallax.conformance` |
| `psycopg_pool` | `parallax.postgres` |
| `botocore` | `parallax.aws`, `parallax.aws.postgres` |

A scope may declare **child enforcement scopes** over its own private
implementation modules (*Child enforcement scopes*, below), and the table below
is the whole of that topology: one row per child, naming the parent it is
nested inside and the **import policy** governing it. A child is `ordinary`
when its generated row is the whole of its enforcement; `isolated` and `sealed`
are the two policies whose other half `tools/check_scope_ownership.py` grades
over the files, as stated above. Parent and policy are properties of one
declared relationship, so they are declared together, once, here.
`tools/check_dag_sync.py` parses the table — every child and parent must be a
declared scope, a child must be nested inside its parent, the policy vocabulary
is closed, and a child is declared by one row, a second being a contradiction
to reject rather than a later reading to keep — and compares it, parent and
policy alike, with its own `CHILD_SCOPES` table, so a child declared,
re-parented, or re-policied on either side alone fails the sync check before
anything is generated.
`tools/check_scope_ownership.py` reads that same table for the parent/child
chains a file may resolve along, for the siblings a zero-grant row names, and
for the scopes each policy governs.

| Child enforcement scope | Parent enforcement scope | Import policy |
|---|---|---|
| `parallax.aws.postgres` | `parallax.aws` | isolated |
| `parallax.core.entity._construction_input` | `parallax.core.entity` | sealed |
| `parallax.core.entity._edit` | `parallax.core.entity` | ordinary |
| `parallax.core.entity._expressions` | `parallax.core.entity` | ordinary |
| `parallax.core.entity._instance_state` | `parallax.core.entity` | sealed |
| `parallax.core.entity._layout` | `parallax.core.entity` | sealed |
| `parallax.core.entity._pydantic_storage` | `parallax.core.entity` | sealed |
| `parallax.core.object_query._fluent` | `parallax.core.object_query` | ordinary |
| `parallax.descriptor._hub` | `parallax.descriptor` | ordinary |
| `parallax.snapshot.handle._errors` | `parallax.snapshot.handle` | ordinary |
| `parallax.snapshot.handle._execution_authority` | `parallax.snapshot.handle` | sealed |
| `parallax.snapshot.handle._family` | `parallax.snapshot.handle` | ordinary |
| `parallax.snapshot.handle._keyed_sql` | `parallax.snapshot.handle` | ordinary |
| `parallax.snapshot.handle._keyed_writes` | `parallax.snapshot.handle` | ordinary |
| `parallax.snapshot.handle._materialization` | `parallax.snapshot.handle` | ordinary |
| `parallax.snapshot.handle._preflight` | `parallax.snapshot.handle` | ordinary |
| `parallax.snapshot.handle._publication` | `parallax.snapshot.handle` | sealed |
| `parallax.snapshot.handle._read_scope` | `parallax.snapshot.handle` | ordinary |
| `parallax.snapshot.handle._retention` | `parallax.snapshot.handle` | sealed |
| `parallax.snapshot.handle._write_lowering` | `parallax.snapshot.handle` | ordinary |

Generated first-party and direct-external contracts are the default for every
framework-owned production scope the tables above declare: each sources one
first-party `forbidden` contract, the complement of its closure, and is a
source of every restricted package's contract it is not granted. Three cases
stand outside that default and are stated here once. The conformance-family
scopes `parallax.conformance.case_format` and `parallax.conformance.cli` are
parity-checked like any other and exempt as importing sources — the core
conformance-family exception of `modules.md` — while every production scope
stays forbidden from importing `parallax.conformance` as one package. A
production scope is a declared scope outside `parallax.conformance`, so any
scope declared beneath that root is exempt the same way by where it sits.
`tests.api` is a pytest collection boundary rather than an import-linter scope.
The application composition root — application or test code calling
`parallax.snapshot.connect` — is owned by no scope and graded by no contract:
it imports `parallax.snapshot` and one concrete adapter such as
`parallax.postgres`, which is how a deployment selects a `DatabaseAdapter`
without Snapshot naming one.

A change is made in the relation that owns it, on both sides of the parity
check. A new behavioral scope is an edge change in `core/spec/modules.md` where
its dependencies change, plus a row of the behavioral table and a
`MODULE_SCOPE` entry. A new support scope or Python-only edge is a row of the
first-party table and a `PYTHON_FIRST_PARTY_GRANTS` entry, kept as `(none)`
only where an empty grant is enforced. A new restricted package is a row of the
restricted-external table and a `RESTRICTED_EXTERNAL_GRANTS` entry, together
with literal negative and positive `lint-imports` canaries naming it: a package
misspelled consistently on both sides would forbid a node the graph never
holds, and import-linter drops such a node without a word. A new or changed
child is a row of the child table and a `CHILD_SCOPES` entry. A first scope in
a new `parallax` package needs no root declared: the import-linter roots derive
from the declared scopes, so that package is a root from then on, and its
interface module is either a declared scope or an exact ownership exemption,
which `tools/check_scope_ownership.py` demands (*Filesystem ownership*, below).

- **Dependency-analysis tool.** import-linter; configuration in
  `languages/python/pyproject.toml` (`[tool.importlinter]`) **generated** by
  `languages/python/tools/check_dag_sync.py`, which parses the fenced
  `dependency-graph` block in `core/spec/modules.md`, computes the DAG's
  transitive closure over the relations above (core edges mapped through the
  behavioral table, plus the declared first-party grants), and emits the
  **forbidden-edge complement**
  as import-linter `forbidden` contracts — one forbidden import per
  production scope pair the closure does not permit. The composition scope's
  `m-sql` edge is deliberate: `m-unit-work` takes no edge to SQL generation
  (core routes dialect SQL through the `m-db-port` execution seam at the
  composition surface), so `parallax.snapshot.handle` is where claimed finds
  are compiled and buffered DML is lowered, and the generated complement
  permits that edge rather than forbidding it. The composition scope's `m-navigate`
  edge follows the identical reasoning: `Transaction.find`
  is a claimed find, and the `m-deep-fetch` plan it reads by canonicalizes
  navigation immediately after `m-temporal-read`'s root injection, mirroring the
  conformance engine's own composition-at-the-engine order. The generator also encodes
  the core **conformance-family exception** (`modules.md`): the
  conformance-family scopes (`parallax.conformance.*`, plus the
  pytest-bounded `tests.api`) are exempted from the complement
  on the **importing** side — the CLI may import any compiler/runtime scope
  it harnesses — while every production scope remains forbidden from
  importing any conformance scope, so the production → conformance
  direction stays a generated `forbidden` contract. Layer contracts alone
  cannot encode this
  partial order: a `layers` contract lets a higher layer import *every* lower
  layer, silently legalizing illegal non-edges (e.g. `m-batch-write`
  importing `m-temporal-read`), so the gate must reject illegal non-edges,
  not merely confirm that listed edges match `modules.md`. The script
  re-generates and fails on any diff against the committed contracts. Local:
  `uv run python tools/check_dag_sync.py && uv run lint-imports`. CI: the
  same pair as a blocking job; any import outside the closure, and any
  generated-contract drift, fails.
- **Carrier-neutral private compiler reaches.** The defining leaves, imported
  names, and authorized importing modules are exact. A second importer or name is
  a new topology decision, not an incidental use of an existing scope grant.

  ```carrier-neutral-private-reaches
  parallax.core.sql_gen._compile | CompiledRead, CompiledTemplate, compile_read, compile_template | parallax.snapshot.handle._read_plan
  parallax.core.sql_gen._compile | CompiledRead, compile_read | parallax.snapshot.handle._predicate_writes
  parallax.core.sql_gen._compile | CompiledRead | parallax.snapshot.handle._materialization; parallax.snapshot.handle._read
  parallax.core.sql_gen._seek | null_pattern | parallax.snapshot.handle._read_plan
  parallax.core.sql_gen._write | compile_write_step | parallax.snapshot.handle._write_lowering; parallax.conformance._lanes.scenario
  ```

  Snapshot's imports are first-party private implementation reaches;
  conformance imports are development-only adapter reaches. No defining leaf
  is exported from `parallax.core.sql_gen`, and no other consumer imports these
  names. The topology contract test pins this block independently of the
  broader generated scope graph. The source exact-set inventories MUST read
  every Snapshot and conformance import from a private `parallax.core.sql_gen`
  module as exactly this importer/name set, so an implementation cannot widen
  either set silently.
- **The conformance family's accepted private reaches.** The enforcement unit is
  the scope, so the importing-side exemption above already reaches a granted
  scope's private modules; what the exemption does not decide is *which* of them
  the adapter may read. The adapter drives production through supported entry
  points, and the residue is an enumerated set rather than a habit, one that
  **reaches the common runtime and one prepared selection's projection**:
  `parallax.core.entity._model.model_of` in its corpus-model loader, and — in its
  second-frontend fixture — `parallax.snapshot.handle._publication.read_projection`
  and two exact imports of `parallax.core.object_query._fluent`.
  `parallax.conformance.another_source` binds `ObjectQuery` and
  `object_query_node` to drive the second frontend; `parallax.conformance.workloads`
  binds those same two names so a catalog entry can retain the typed query and
  compare its normalized node with a class-backed consumer before handing either
  to production preflight. These reaches are **rebutted rather than exempted**:
  `model_of` and the two typed-query names are already accepted private seams of
  production's own composition root and read preflight, and the typed surface is
  reached by naming the module that owns it — which is what a consumer wanting it
  does above, the Snapshot composition scope included. `ObjectQuery` appears in both exact
  imports although §8 re-exports it because each importer also requires the
  module-owned `object_query_node`. `model_of` exists precisely so a separately
  distributed frontend can read the accepted model out of a Domain Model
  (*Canonical descriptor input*), which is what the adapter is doing.
  `read_projection` is accepted for the same reason the second frontend needs
  it: a source that drives the production find executor takes the prepared
  selection's read projection — the accepted model, the layout catalog paired
  with it, and the graph construction derived over both — exactly as the source
  under test holds them, rather than reading any half separately or deriving a
  second catalog beside the selection's. A second managed value lifecycle merges and constructs for
  itself — that is what makes it second — but a node member row is neither: it
  crosses `populate` as its Root View laid it out, against the same model-owned
  member layout the writer reads it against, so the fixture hands a row over the
  one way production hands one over and no rule is restated in a second place.
  The adapter engine's model-facts mechanism and the second-source fixture also
  import the private Snapshot `preflight` operation so compile-only and
  alternate-source reads consume the same validated execution token as
  production. The scenario lane's private `m-sql` write-step compiler reach is
  enumerated separately in the carrier-neutral block above,
  and the case loader's `wire._json.authored_number` reach is the production YAML
  token-preservation seam. Compatibility inputs use canonical Wire literals, so
  case ingress needs no private token-inspection reach. Each remaining reach stays
  keyed by its exact importing module and imported names in the source inventory.
  Widening
  `parallax.core.entity`'s shipped surface to serve a development-only consumer
  of a documented first-party seam would be the wrong repair.

  One further reach is the harness's own driver sessions:
  `parallax.conformance._postgres_control` imports
  `parallax.postgres._connection.initialize_connection` and
  `parallax.postgres._connection.PostgresConnection`, plus the shared
  `parallax.postgres._authorization.install_role` and `restore_role` operations.
  The latter keep the dedicated-session authority envelope identical to the
  pooled provider's without giving the harness a second role implementation.
  The harness opens sessions
  an application never would — the per-case schema reset, a peer holding its own
  transaction, a case's verbatim golden SQL, and the dedicated session an
  interleaved choreography may destroy — and every statement it runs on one must
  be decoded, classified and demarcated exactly as an application's own would be.
  The alternative is a second implementation of the codecs, the error
  translation and the transaction outcomes inside the harness, which would grade
  the adapter against a database nobody runs. What is deliberately NOT reached is
  the runtime: a session the harness may cancel, close, or tear down at the
  socket must be one nothing else can be handed, so the controlled adapter beside
  this reach is the harness's own and the shipped `PostgresAdapter` serves every
  other lane.

  The `m-descriptor` record graph is **not** in the set: corpus models
  reach the adapter through the public `domain_model_from_*` doors and are read
  through the accepted model's own vocabulary, so no `parallax.descriptor`
  private module is imported at all. Each reach is keyed by the module that
  makes it, so a second importer of an accepted name is a new decision here.
  `tests/unit/test_source_enforcement_topology.py` holds the exact set for both
  this family and Snapshot's, as an inventory that fails when it drifts.
- **Child enforcement scopes.** A support scope MAY declare child scopes over
  its own private implementation modules when the child's declared grants are
  materially narrower than the parent's closure or when one orchestration leaf
  requires a narrowly additive first-party grant that must remain forbidden to
  the rest of the parent package. The declared children of
  `parallax.snapshot.handle` are the narrower wrapping and read-preflight
  scopes, the write-lowering scopes, and the zero-grant refusal leaf.
  `parallax.descriptor._hub` is the additive case: its sole extra grant is the
  first-party Entity frontend seam required to construct and read the one
  concrete `DomainModel` type. `parallax.snapshot.handle._errors` is the empty case: the
  read-preflight and write-lowering scopes raise one error class while granting
  disjoint dependencies, so the module holding it may reach nothing at all. A
  grant row of `(none)` forbids it every scope outside its own package **and**
  every sibling child scope inside it. A sibling is neither an ancestor nor a
  descendant of a zero-grant scope, so — unlike the shared parent package, which
  a package-scoped `forbidden` row cannot name from inside — it is a target the
  row can state, and an import of a **declared** sibling is refused rather than
  left to convention. Only a **zero-grant** row takes its siblings as targets: a
  scope with grants has a closure to complement, and naming siblings in its row
  would forbid intra-package edges this section permits. A sibling module over
  which this section declares no child scope is not stated in the row either;
  `tools/check_scope_ownership.py` requires such a module to carry a first-party
  import, so that importing it is reported wherever the chain through it leaves
  the package. The shared parent package stays the single name such a row cannot
  state, which no scope declaration could change. What makes two scopes granting
  disjoint dependencies able to share a zero-grant module is their **own** rows:
  each forbids everything its grants do not reach, so a dependency added to the
  shared module breaks the row of whichever consumer is not already granted it.
  `parallax.core.entity._layout` is the **grantable**
  case: a child scope may also be named as another scope's grant,
  which is how a consumer takes a narrow part of a package without taking what
  the rest of that package reaches. `parallax.core.entity._expressions` is the
  narrowing case within one package: query authoring reaches no model, so the
  values a developer composes must reach no model formation and no whole-model
  semantic view. Its document-codec edge is restricted to validating one
  retained member shape against a live authored Value Object; the codec neither
  supplies a model view nor resolves an Entity position. The row is what proves
  those boundaries rather than the module docstring alone.
  `parallax.core.entity._edit` is declared beside it as a child of the
  Entity frontend, but its behavioral `m-edit` row and module-DAG edge supply its
  grants, so it has no first-party support row. All are
  generated as ordinary contract sources, and none is a new supported import
  path. Because
  import-linter's `forbidden` contracts are package-scoped on both sides, a
  child is emitted as a contract **source**, and as a forbidden target only in
  a *sibling's* zero-grant row: naming it as a forbidden target of its own
  parent would overlap the parent's source package and be skipped, and naming
  it in any other scope's row would only restate what the parent's own entry
  already forbids for every descendant. When a child has an additive grant,
  the generator keeps the
  parent's forbidden row unchanged and emits one wildcarded `ignore_imports`
  entry for each exact child-to-direct-grant edge. A grant naming a scope inside
  the parent's own package is not one: a row can neither forbid nor except what
  sits inside its source, and whatever that sibling reaches further is already
  reported from the sibling itself. Ignoring that first hop also
  withdraws import-linter's indirect chains through it; no transitive grant
  receives a second exception. `unmatched_ignore_imports_alerting="error"`
  ensures an exception cannot outlive the import it describes. The composition
  scope declares no `m-pk-gen` grant: nothing
  under `parallax.snapshot.handle` imports primary-key generation, so the
  generated complement forbids it. The unused direct `m-navigate` grant is
  retained on purpose — navigation stays reachable through `m-snapshot-read`
  → `m-deep-fetch` → `m-navigate`, so removing it would forbid nothing while
  contradicting the deliberate edge described above.
- **Boundaries a scope must not reach.** A forbidden row is the complement of a
  closure, so a scope is never forbidden what its own grants reach transitively.
  A scope that exists in order to stay clear of some boundary must therefore be
  granted narrowly enough that the boundary falls **outside** its closure; there
  is no exception mechanism that puts a reachable target back into a row.
  `parallax.snapshot.handle._preflight` is the case in point: the seam resolves
  a target and validates a query before any I/O, so it must reach no
  Database Port, and the `parallax.core.entity` package reaches one through
  `parallax.core._formation_profile` → `m-opt-lock` → `m-unit-work` →
  `m-db-port`. Its grants are therefore `m-metamodel`, `m-predicate` and
  `m-object-query` — the canonical query value plus what resolves and validates
  it — none of which reaches the Entity frontend, and the ordinary generated row
  forbids `parallax.core.entity` outright along with `m-db-port`, `m-opt-lock`,
  `m-unit-work` and `parallax.core._formation_profile`, with indirect chains
  reported. `_preflight` naming `parallax.core.entity._model` therefore breaks
  the gate twice over: on the frontend package it may not name at all, and on
  `_model`'s own edge to `parallax.core._formation_profile`.
  Granting a child scope instead omits that child's ancestors from the row,
  because a forbidden entry naming the ancestor package would also forbid the
  granted child inside it. Only the ancestor's **name** is given up: what the
  rest of that package reaches stays forbidden and is reported as an indirect
  chain, which is why `parallax.snapshot.materialize`, granted
  `parallax.core.entity._layout`, still has `parallax.core._formation_profile`
  in its own row.
- **Filesystem ownership.** `languages/python/tools/check_scope_ownership.py`
  walks every `packages/*/src/**/*.py` file in the production distributions and
  proves it resolves to exactly one **most-specific** enforcement scope of this
  section — plus, where child scopes are declared, that scope's declared
  ancestors — or to an exact, listed package-interface exemption. A file inside
  a child scope is deliberately owned by both the child and its parent: that is
  the state child scopes exist to create, and the child's tighter grant row is
  what governs it. Zero owners, **undeclared** overlapping owners (two or more
  matching scopes that do not form a parent/child chain of the child-scope
  table, read as `check_dag_sync.CHILD_SCOPES`), and stale exemptions each fail
  the check, which runs in `just python-check-scope-ownership`. The exemptions
  are verified to be exactly the package interfaces `check_dag_sync.py` derives
  from the declared scopes and sources as modules: an interface with no
  exemption — its file present or missing — and an exemption for an unowned
  file that is no such interface each fail, so a new distribution's interface
  is either declared a scope or exempted with its reason before the gate is
  green. The same tool adds
  the file-level requirement no scope table can state: inside a
  package holding a scope granted `(none)`, every module must either resolve to
  a scope that row names — the zero-grant scope itself, one of its declared
  siblings, or any scope declared beneath them, since a forbidden target is
  package-scoped and covers its whole subtree — or carry a first-party import,
  so that importing it is reported wherever the chain through it leaves the
  package. A module that is neither is refused. The rule is derived
  from the declared scopes rather than written against one package; the
  package's own interface module is outside it, because no declaration could
  bring it inside a row that cannot name its own ancestor. The same tool also
  carries the other half of the **isolated** scope rule: a forbidden row may not
  name a module inside its own source package, so the tool parses the files of an
  isolated scope's ancestors — resolving relative imports, and reading an
  imported name as a possible submodule — and refuses any import reaching that
  scope in any spelling. The **sealed** scope rule is the same overlap read the
  other way, and is carried the same way: the tool parses a sealed scope's own
  files and refuses every import landing inside its parent package that no
  granted scope covers, so the grants stated for it are complete rather than
  complete only outside that package. `from <parent> import <sibling>` is read
  as one reach at the sibling rather than at the parent alone, so a grant holds
  in every spelling of the import it permits, exactly as a refusal does.
- **Scopes sharing one artifact.** Every behavioral module in `parallax-core`
  is its own submodule; the generated forbidden contracts operate at
  submodule granularity, so co-location in one wheel cannot legalize a
  forbidden edge. Cross-package contracts permit the production artifact edges
  `descriptor → core`, `snapshot → core`, and `postgres → core` only.
  Consequently core cannot import descriptor, Snapshot, or Postgres;
  descriptor cannot import Snapshot or Postgres; and Snapshot and Postgres
  cannot import one another or descriptor. The development-only conformance
  family may import every artifact it harnesses.
- **Database seam scopes.** Pure dialect strategy in `parallax.core.dialect`
  (driver-free), abstract port in `parallax.core.db_port`, error
  classification in `parallax.core.db_error`, the concrete adapter in
  `parallax.postgres`, and the composition root in application/test code. Only
  the composition root imports the concrete adapter; the port imports nothing
  application-specific.

## 8. Deployable artifact topology

uv workspace under `languages/python/`; PEP 420 namespace `parallax.*` shared
by separately installable distributions (the dormant PyPI `parallax` SSH tool
would collide only if co-installed; documented, accepted). Build backend:
hatchling.

| Artifact/package | Production or development-only | Included source scopes | External runtime dependencies | Depends on artifacts | Public exports/entry points |
|---|---|---|---|---|---|
| `parallax-core` (the common runtime) | production | all `parallax.core.*` scopes of §7 (behavioral modules, Entity/Object Query frontend, driver-free postgres dialect strategy) | `pydantic` | (none) | `parallax.core`: the `Entity`/`TxTemporal`/`Bitemporal`/`ValueObject` bases, `Attr`, `Rel`, `attr`, `rel`, `index`, `desc`, `asc`, `Int32`, `Float32`, `MAX`, `Sequence`, the cardinality, persistence, inheritance role and strategy values, `DomainModel`, the Object Query authoring vocabulary — `ObjectQuery`, `AttributeExpr`, `RelationshipPath`, `Predicate`, `AllPredicate`, `SortKey` — `LATEST`, `VALID_TIME`, `TX_TIME`, `Pin`, `Edge`, and its documented errors; `parallax.core.wire`: `WireValue`, `WireDecodingReason`, `WireDecodingError`, `WireEncodingError`, `loads`, `decode_wire`, `decode_canonical_wire`, and `encode_wire`; `parallax.core.sql_gen`: `LoweredStatement` and `SqlGenError`; `parallax.core.diagnostics`: `FailureDiagnostic`, `MESSAGE_LIMIT_BYTES`, and `STACK_LIMIT_BYTES` — the one import home for the detached exception projection three scopes share; `parallax.core.db_port`: `DatabaseConnection`, `DatabaseAdapter`, `DatabaseRuntime`, `ConnectionContextSource`, `ConnectionContext`, `InvalidAuthorizationError`, the transaction outcomes, `IsolationLevel`, `ConnectionAcquisitionError`, `DatabaseStartupError`, `Returned`, `Invalidated`, `ReleaseUnconfirmed`, `CleanupIssue`, and the pool-sample contract — `PoolMetricsSource`, `PoolMeasurements`, `PoolAvailable`, `PoolUnavailable`, `PoolDetached`, `PoolSample`; `parallax.core.execution_lifecycle`: the Provider/Handler protocols, root and event values, outcomes and diagnostics, lifecycle errors, `PoolMetricsObserver`, `PoolObservation`, `FanoutLifecycleProvider`, `LoggingLifecycleProvider`, and `LifecycleLogDetail` |
| `parallax-descriptor` (descriptor interchange) | production, optional | `parallax.descriptor` (`m-descriptor` plus its private Hub orchestration) | `pyyaml`, `jsonschema` | `parallax-core` | `parallax.descriptor`: `domain_model_from_document`, `domain_model_from_json`, `domain_model_from_yaml`, `export_document`, `export_json`, `export_yaml`, `validate_inheritance_families`, `DescriptorError`, `DescriptorSyntaxError`, `DescriptorSchemaError`, `DescriptorValueError`, `DescriptorSchemaViolation`, `DescriptorValueViolation`, `DescriptorExportError` |
| `parallax-evolution` (model evolution and schema deltas) | production, optional | `parallax.evolution.*` (`model_evolution`, `schema_delta`) | (none beyond core) | `parallax-core` | `parallax.evolution`: `evolve`, `ABSENT`, `UnilateralEvolution`, `CoordinatedEvolution`, and the closed Evolution Operation, field-delta, Behavioral Impact, and coordination vocabularies those two results carry; `schema_delta`, `SchemaDelta`, `CreatedIndex`, `UnsupportedSchemaEvolutionError`, `UnsupportedSchemaOperation`, `PhysicalIndexNameCollisionError`, `CollisionGroup`, `CollidingIndex`, `IndexPresence`, and `PhysicalLocation` |
| `parallax-snapshot` (snapshot lifecycle extension) | production | `parallax.snapshot.*` (`materialize`, `handle`) | (none beyond core) | `parallax-core` | `parallax.snapshot`: `connect()`, `DatabaseOptions`, `Principal`, `ScopedDatabase`, `InvalidPrincipalError`, `TransactionAuthorityError`, `prepare_model()`, `ModelSelection`, `ServingModel`, `PublicationConflictError`, `ExecutionFailure`, `Snapshot[T]`, `CheckedSnapshot[T]`, `RowsResult`, `WireEntity`, `WireDatabaseView`, `WireTransactionView`, `WireQuery`, `WireChanges`, `WirePredicateTarget`, `InvalidData[T]`, `StoredDataIssue`, `MISSING_STORED_VALUE`, `ObjectKey`, `InvalidDataError`, `NoResultFound`, `TooManyResultsFound`, `is_view_loaded`, `view`, `pin_of`, `edge_of`, `UnloadedRelationshipError`, `DeferredFeatureError`, `SnapshotConnectionError`, `SnapshotConsistencyError`, `SnapshotDecodingError`, `SnapshotMaterializationError`, `SnapshotInspectionError`, `TransactionOwnershipError`, `QueryTargetError`, `KeyedWriteValueError`, `KEYED_WRITE_VALUE_CODES`, `WriteEvidenceError`, `WriteEvidenceErrorCode`, `WRITE_EVIDENCE_CODES`, `WriteInstructionError` |
| `parallax-postgres` (Postgres database adapter and owned runtime) | production | `parallax.postgres.*` (concrete adapter, runtime, acquisition context and scoped execution over psycopg) | `psycopg[binary]`, `psycopg-pool` (sole declarer of both) | `parallax-core` | `parallax.postgres`: `PostgresAdapter`, `PostgresRole`, `PoolOptions`, `OnDemandOptions`, `isolation_spelling` |
| `parallax-aws` (AWS credential providers) | production, optional | `parallax.aws` (the RDS IAM Credential Source), `parallax.aws.postgres` (its engine-specific slice, behind the `postgres` extra) | `botocore` (sole declarer) | `parallax-core`; `parallax-postgres` under the `postgres` extra | `parallax.aws`: `RdsIamCredentials`; `parallax.aws.postgres`: `rds_postgres` |
| `parallax-conformance` | development-only | `parallax.conformance.*` (CLI, case format, corpus loading, provider harness) | `testcontainers`, `jsonschema` | `parallax-core`, `parallax-descriptor`, `parallax-evolution`, `parallax-snapshot`, `parallax-postgres` | `parallax-conformance` console script (`describe` / `compile` / `run`) |

- **Common runtime manifest proof.** `parallax-core`'s manifest declares only
  `pydantic`; the clean-install check installs it alone and proves
  `parallax-descriptor`, `pyyaml`, `jsonschema`, `psycopg`,
  `parallax.snapshot`, testcontainers, and conformance modules are absent from
  both the installed distribution list and the import space.
- **Descriptor manifest and schema-resource proof.** `parallax-descriptor`
  directly declares `parallax-core`, `pyyaml`, and `jsonschema`, so every
  installed Descriptor Frontend can execute all three ingestion phases without
  an optional-import failure branch. The language-neutral
  `core/schemas/metamodel.schema.json` remains authoritative; the wheel and
  sdist embed a byte-for-byte package-data copy loaded through
  `importlib.resources`. Build and artifact checks compare the packaged
  resource with the authoritative source and fail on drift. Runtime code never
  searches repository-relative paths.
- **Evolution manifest proof.** `parallax-evolution` depends only on
  `parallax-core`; the clean-install check proves no Descriptor Frontend,
  descriptor parser, schema validator, sibling lifecycle artifact, or concrete
  driver arrives with it. Describing an evolution is pure, so the wheel declares
  no external runtime dependency at all — the fingerprint a schema consumer needs
  comes from the standard library.
- **The provisioning path is the shipped generator.** The development-only
  `parallax.conformance.provision.schema_statements` composes no DDL of its own:
  it is `schema_delta(evolve(ABSENT, model), dialect)`, provisioning being the
  Unilateral Evolution from the explicit absent endpoint. Every database-backed
  Python test therefore executes the generator's own statements, and an authored
  secondary Index exists in a test database as the separately named object a
  violation can report.
- **Lifecycle extension manifest proof.** `parallax-snapshot` depends only on
  `parallax-core`; the clean-install check proves no sibling lifecycle
  artifact, Descriptor Frontend, descriptor parser, schema validator, or
  concrete driver is present.
- **Adapter manifest proof.** `parallax-postgres` alone declares the driver,
  and it declares `psycopg[binary]`: the `binary` extra bundles a self-contained
  `libpq` in the wheel, so the adapter — and the clean-install topology proof
  below — installs and imports with **no system `libpq`** present. The accepted
  trade-off is the pre-built binary build over compiling `psycopg[c]`/pure
  `psycopg` against a system `libpq` (the binary build is discouraged only for
  large-scale production connection tuning, out of scope for this slice), so the
  self-contained deployment the topology proof relies on is the deliberate
  default. The driver-free dialect strategy ships inside `parallax-core`
  (explicitly permitted by core), keeping `compile` Docker- and driver-free.
- **Credential-provider manifest proof.** `parallax-aws` declares `parallax-core`
  and `botocore` unconditionally and nothing else, and it is the sole botocore
  declarer: the built wheel's `Requires-Dist` is asserted to be exactly those
  two beside the one requirement its `postgres` extra gates, and every other
  clean-install fixture proves botocore absent. A credential provider is a leaf
  beside the adapters rather than a layer above them — it produces
  configuration the composition root hands to whichever adapter it selected — so
  `parallax.aws` is granted `m-db-port` alone and the clean-install fixture
  proves an installed provider brings no adapter and no driver with it. Its
  engine-specific slice `parallax.aws.postgres` composes that configuration for
  one adapter and is therefore granted it, as a child enforcement scope wider
  than its parent (§7) and as the one extra the manifest declares: selecting
  the extra is what installs an adapter, and without it the slice is absent
  from the import space. That child is **isolated** (§7), because the grant
  has to stop at it: the parent's row excepts the slice's adapter import by
  name, and an exception withdraws every chain through it, so nothing else in
  `parallax.aws` may reach the adapter by reaching the slice.
- **Composition root.** Application/test code constructs the adapter and calls
  `parallax.snapshot.connect(adapter=...)`; neither dependency leaks into
  common-runtime code, and no umbrella artifact exists.
- **Clean-install and runtime-load checks.** Seven uv-venv fixtures
  (`uv run pytest tests/distribution/test_clean_install.py`): core alone; core + descriptor; core +
  evolution; core + snapshot; core + snapshot + postgres; core + aws; core + snapshot + postgres +
  aws[postgres]. Each inspects installed
  distributions and import-probes to prove unselected interchange, lifecycle, adapter,
  driver, credential provider, conformance, benchmark, and container dependencies are absent from
  the installed and loaded production graph. The descriptor fixture also
  imports its packaged schema and exercises one JSON and one YAML round trip.

## Development configuration

[TESTING.md](../TESTING.md) routes verification. Tool versions, quality thresholds,
package dependencies, and execution commands are owned by the workspace
configuration, package manifests, and root justfile. Quantitative contracts are
the structured files beside this document, including
[memory gates](memory-gates.yaml); their schemas and consumers define their form.
Open work is tracked in the [deferred ledger](../docs/deferred-ledger.md).
