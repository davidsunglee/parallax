# Language Binding

A language binding records decisions the portable contracts leave to that
language. Its entry point is `languages/<target>/spec/<target>.md`; supporting
pages may be linked without becoming separate completed specifications.

Select one lifecycle-complete canonical claim from [slices.md](slices.md) in
exactly one fenced manifest:

```language-binding
{"slice": "slice-snapshot-1"}
```

The manifest contains only `slice`. Capabilities, lifecycle, dialects, and
commands are inherited from that canonical claim instead of copied here.
The [core specification](00-overview.md), [schemas](../schemas/), and
[compatibility corpus](../compatibility/) own portable behavior.

Record public decisions where types and inherited contracts leave choices:
API spelling, scalar mappings, error translation, resource ownership, and
language-specific constraints. Link to tested examples. Resolve decisions
before implementing their public surface; unresolved placeholders fail the
binding check.

Do not inventory private implementation details, phases, test coverage, or
quality-tool commands here. Executable configuration owns those facts.

Dependency declarations remain independently authored and checked: retain the
source-enforcement and artifact topology sections below. The canonical graph
in [modules.md](modules.md), the language's scope mappings, and their drift and
ownership checks remain binding. For Python these are `spec/python.md` §7/§8,
`tools/check_dag_sync.py`, and `tools/check_scope_ownership.py`.

## 7. Source-enforcement topology

A claim about observable behavior is graded by behavior at the API boundary,
never by inspecting source structure. The specification constrains structure only
where a decision is itself about the source: which scope owns a module and which
artifact ships it, what a surface exports and what it keeps private, whether
anything is generated and where it lands, and what the toolchain runs. That test
is the rule, and it is applied to a sentence wherever the sentence stands. Public
binding pages, §8, and executable configuration own those decisions; the
enforcement scopes and reaches are recorded here. A behavioral section that phrases a
consequence as a fact about source text has misplaced it — restate it as what a
caller observes, or record it here.

The behavioral-module DAG governs dependencies between source enforcement
scopes even when many scopes live in one source tree or common-runtime artifact.
Record the source-enforcement map as four relations, each one strict table
whose cells declare only what they spell in backticks, with two bare
spellings: the explicit empty grant, and the import policy word, which comes
from the closed vocabulary the language's tooling defines. Source paths, tool
names, and descriptive labels belong in prose beside the tables, not in them,
so that each table can be read back mechanically and compared with the one
declaration the enforcement tooling holds of the same relation. Do not use
these tables as a deployable-artifact list.

The first table maps every claimed module and every unclaimed transitive
prerequisite to the enforcement scope that owns it, one row per module. A
behavioral module's allowed direct dependencies are its edges in
[`modules.md`](modules.md) and are not restated here.

| Behavioral module | Enforcement scope |
|---|---|
| **(decide and record — All slices)** | |

The second table declares every edge no module tag carries: for each language
support scope, its allowed direct first-party dependencies; for a behavioral
scope, only the language-specific supplement to its tagged edges. A scope
granting nothing states so explicitly, since the empty grant is what it
enforces.

| Enforcement scope | Allowed direct first-party dependencies |
|---|---|
| **(decide and record — All slices)** | |

The third table names each third-party package the implementation confines to
the scopes that own the substrate it provides, by exact top-level import name,
and the scopes granted a direct import of it. A grant here is independent of
first-party reachability and of any artifact manifest.

| Restricted external package | Granted enforcement scopes |
|---|---|
| **(decide and record — All slices)** | |

The fourth table declares every enforcement scope nested inside another: its
parent, and the import policy that says which half of its boundary the
generated contracts grade and which half a complementary check must.

| Child enforcement scope | Parent enforcement scope | Import policy |
|---|---|---|
| **(decide and record — All slices)** | | |

- **(decide and record — All slices)** The dependency-analysis tool, exact
  configuration path, local command, and blocking CI command. State how the
  configuration is derived from the complete DAG in [`modules.md`](modules.md)
  and from the tables above, how each table is checked against the tool's own
  declaration of that relation so that neither can be edited alone, and how a
  forbidden direction, an illegal non-edge, and a direct import of a
  restricted external package each fail.
- **(decide and record — All slices)** If several enforcement scopes live inside
  one source tree or deployable artifact, the import/namespace/internal-package
  boundaries that keep their directions mechanically distinguishable. Artifact
  co-location MUST NOT make a forbidden source edge legal.
- **(decide and record — All slices)** Database seam scopes for pure dialect
  strategy, abstract `m-db-port`, error classification, each concrete adapter,
  and the composition root. Only the composition root imports a concrete adapter;
  the port imports nothing application-specific.

## 8. Deployable artifact topology

Complete a separate row for every production artifact and development-only
tooling artifact. At minimum this includes one independently deployable,
lifecycle-neutral common runtime; the selected lifecycle extension; and one
separately deployable adapter per supported database.

| Artifact/package | Production or development-only | Included source scopes | External runtime dependencies | Depends on artifacts | Public exports/entry points |
|---|---|---|---|---|---|
| **(decide and record — All slices)** | | | | | |

- **(decide and record — All slices)** The common runtime manifest and proof that
  it depends on neither lifecycle extension nor concrete database driver.
- **(decide and record — All slices)** The selected lifecycle extension manifest
  and proof that it depends downward on common behavior but not a sibling
  lifecycle or concrete adapter.
- **(decide and record — All slices)** Each concrete adapter manifest and proof
  that it alone introduces its matching driver. Record where pure driver-free
  dialect strategies ship.
- **(decide and record — All slices)** The application/test composition root that
  selects the lifecycle extension and adapter without leaking either dependency
  into common runtime code.
- **(decide and record — All slices)** Clean-install and runtime-load checks for:
  common runtime alone; common plus the selected lifecycle; and common plus that
  lifecycle plus one adapter. Each check MUST prove unselected lifecycles,
  adapters, drivers, conformance harnesses, benchmarks, and container tooling are
  absent from the installed and loaded production graph.
