# Deferred-work ledger — Python target

Work deliberately deferred while building the Python target, kept in one place so
it is not lost across sessions. It holds **only items that are actively open and
owned by nothing else** — work surfaced during design or implementation that
would otherwise have no home.

Scope is this target. An entry whose repair lands outside `languages/python`
still belongs here when Python work surfaced it and nothing else tracks it, but
it must name its true owner so a second language target inheriting the same gap
can find it. A neutral concern that outlives this target is promoted to a core
specification, an issue, or a ledger of its own rather than left here.

This is not a duplicate of the `languages/python/spec/python.md` §1 deferral
list, which is canonical for deferred capabilities, and it does not restate work
already tracked as a Linear issue.

## Protocol

Read this file at session start. Add an entry in the same session any deferral
happens — never only in a commit message, a code comment, or a task artifact.
Sweep it at claim closure.

Closing, graduating, or otherwise giving an entry a home means **removing it**
and leaving a forwarding line below, so this file stays a work list rather than
an archive. An entry that is resolved, closed, graduated to a Linear issue, or
carried in full by one is not an entry here.

Entry numbering is continuous and never reused. The next new number is **D-58**.

## Standing notes

Not deferrals — decisions already made that a future session is likely to try to
undo.

### `python.md` §3's document-resident nullability bullet is settled. Do not "tighten" it

The bullet states that no layer enforces declared nullability at a
document-resident position, what Entity Graph Construction still validates
there, and the judged boundary under Relational Document Layout stated by stored
state.

It reads like something that wants fixing. It does not. The behavior it
describes is corpus-mandated: `m-value-object-023` grades `city: null` for a leaf
`core/compatibility/models/customer.yaml` declares without `nullable: true`, and
core specifications plus the compatibility corpus outrank the language spec.
Enforcing nullability at construction was implemented once and reverted — it
fails five database-backed reads with `entity-graph-invalid-value:
parallax.compatibility.Customer.address.city is not nullable and admits no null`.

The bullet took five external review rounds to state correctly, because the
truth is a matrix over layout × depth × multiplicity × nullability × stored
state and earlier drafts quantified over positions rather than states. Rewriting
it casually will reintroduce a falsehood.

The behavior is owned onward by
[COR-85](https://linear.app/flimflam/issue/COR-85/report-nodes-whose-stored-state-violates-the-declared-model-instead-of).
Reopen the bullet only if a change to conversion alters the behavior it
describes — and read COR-85 first, since its first phase reconciles the
underlying core-spec contradiction.

### `SnapshotDecodingError` keeps its chained cause. The stored value is meant to be reachable

The refusal's own message names only the Entity and the member at fault. The
value that provoked it survives on the chained `LeafEncodingError`, which quotes
it. A review will read `python.md`'s "exposes no raw database value" as covering
the whole exception chain and call this a violation; it has been raised twice and
answered by decision.

Two facts make keeping the cause the right call. `core/spec/m-db-port.md:56` uses
"raw database value" for a driver-native value *before* normalization, so nothing
above the adapter seam holds one under the term of art. More importantly,
`decode_leaf` enforces **canonical spelling**, not type: a decimal short of its
declared scale, uppercase hexadecimal, a non-UTC timestamp, an uppercase or
hyphenless UUID, and a non-shortest float are all the right kind and the right
type and still wrong. `'12.5' is not the document encoding of any
Decimal(precision=10, scale=2) value` is diagnosable; the same sentence with the
value removed reads "a `str` is not the document encoding of a decimal", which is
both false and unactionable. Suppressing the value deletes exactly what
distinguishes these failures from one another.

The accepted cost is that a caller who logs the exception chain writes stored
data into a log. `python.md` §3 states the boundary the code implements —
message clean, cause carrying — rather than an absolute that contradicts the same
sentence's requirement to carry a cause.

Considered and not taken: carrying the value as a structured field while making
every rendered message value-free. It is a genuine improvement and would let both
readings hold at once, but it changes a shared core refusal's text for the
write-lowering and conformance-assembly lanes. Revisit it there, not by
re-litigating this bullet.

## Entries

### D-53 — Three off-path bare-name reductions remain, each with a reproduced defect and a non-determinate repair

*Low — off every production path, recorded so the sweep is not re-run from
scratch.* Relates to `parallax.descriptor._records.concrete_descendant_names`,
`parallax.conformance._descriptor_family.validate`, `parallax.conformance.engine`.

**What.** One defect class — an exact `EntityIdentity` reduced to a bare local
name — was chased through five call sites and fixed at all five. Three further
sites of the same class were found, verified off-path, and left:

- `_records.concrete_descendant_names` keys `by_name` on `candidate.name` and
  indexes children by the raw authored `parent` string, so two same-local-name
  entities overwrite each other and a model mixing qualified and relative parent
  spellings splits the child index. It has **no production caller at all** — only
  its own `__all__`, the module docstring, and a unit suite.
- `_descriptor_family.validate` builds a bare `by_name` map, and everything it
  feeds inherits the defect: a legal qualified cross-namespace parent is rejected
  as `inheritance-unknown-parent`, a chain crossing two namespaces sharing a
  local name is reported as `inheritance-cycle`, and two same-local-name roots
  merge into one family. It runs from exactly one place —
  `engine.run_rejected_case` grading an inline `when.model` — and never from the
  observation-keying path.
- The conformance engine's default-target convention returns bare names
  (`_rejected_target`, `_conflict_target`), which feed `meta.entity(...)` and
  would raise `KeyError` on a duplicated local name.

**Why it is deferred rather than fixed.** Each repair changes an exported
contract with no caller to validate it against. `concrete_descendant_names`'s fix
makes both `position` and the returned names canonical, and the prior question is
whether an unused export should exist at all. `_descriptor_family`'s fix needs
the relative-reference resolution `_records._parent_identity` implements, which
means exporting it across a module boundary — legal in direction, but a contract
decision — and its diagnostics all quote `entity.name`. All three are
unwitnessed: no `rejected` corpus model declares a namespace.

### D-54 — Every inherited Pydantic field on an Entity subtype defaults to the ancestor descriptor's class-access expression, so a subtype constructs with no arguments

*High — a required member silently holds a query expression.* Relates to
`parallax.core.entity._declaration._build_entity`.

**What.** `Tug()` — a concrete subtype of an abstract temporal root declaring no
members of its own — constructs with no arguments, and every inherited member,
**including required ones like `id`**, holds an `AttributeExpr`:

```text
Tug() -> Tug
  .id       -> <parallax.core.entity._expressions.AttributeExpr object>
  .tx_start -> <parallax.core.entity._expressions.AttributeExpr object>
```

**Why it is open.** `_build_entity` `setattr`s the class-access descriptor over
the class attribute *after* Pydantic has built the parent model, and Pydantic
re-reads that attribute when it collects a subclass's inherited fields — so the
descriptor object itself becomes the inherited field's default. The Entity's own
declared members are unaffected; only inherited ones are.

**Why it is deferred rather than fixed.** It is pre-existing: a subtype's
inherited members carried this default whether or not the parent supplied one.
The fix is an ordering change in the declaration engine — install descriptors
before Pydantic collects subclass fields, or strip them from the collected
defaults — which touches the shared metaclass engine both the Entity and Value
Object frontends depend on, so it wants its own coverage rather than a rider.

### D-55 — The reference harness grades a scenario find's `expectRows` against the raw projected row, disagreeing with `m-case-format` for a family target

*Low — narrows what a corpus case may assert, never produces a wrong pass.*
**Owned by the reference harness, not this target** — the only entry here whose
repair lands outside `languages/python`, kept because Python work surfaced it and
nothing else tracks it. Relates to `reference-harness`
`case_runner._materialize_family_variant`.

**What.** `m-case-format` (*Read result form*) states that a scenario observation
find is **instance-form**, and the Python run sweep grades it that way. The
harness grades that step's `expectRows` against the raw projected row instead.
The two agree except for a **family target**, where the projection and the
materialized instance differ.

**Why it is deferred rather than fixed.** The one case needing an abstract-root
find inside a `uow` group worked around the gap by having that find assert no
rows of its own, with the row assertion carried by the concrete verify read that
follows — so the case is correct and complete, and nothing is mis-graded. Closing
the gap means threading a step's own target and golden projection into
`_materialize_family_variant`, which is harness work outside any Python-target
ticket.

### D-56 — A table-per-concrete-subtype union-all read cannot run inside a transaction in either concurrency mode

*Medium — a legal read shape is unreachable from `Transaction.find`.* Relates to
`read_lock.mode_for`, `parallax.core.sql_gen._inheritance._plan_tpcs_read`.

**What.** `read_lock.mode_for` is the identity function, so a read carries a
non-`None` lock mode under **both** `locking` and `optimistic`, and
`_plan_tpcs_read` refuses a union-all read carrying any lock (its "has no
goldened lowering yet" refusal). A TPCS family — the corpus's `Rate` — is
therefore readable through `db.find` and not through `Transaction.find`.

**Why it is deferred rather than fixed.** It is a lowering gap with a goldening
cost. The abstract-target licensing proof that hit this used a
table-per-hierarchy family instead; the symptom the proof needed — one read whose
rows resolve to their own concretes — is the same either way, so nothing was
lost. Any later work reaching for a TPCS family through a transaction hits the
same wall and must plan around it or close it.

## Forwarding pointers

Removed entries whose number a live document still cites. One line each; drop a
line once nothing cites it. This section is not an entry list and must never grow
prose.

- **D-38** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P7. Mirror the remaining 15 corpus models.
- **D-40** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P4. Eager `fetchall` at the adapter boundary; port-level streaming is [COR-83](https://linear.app/flimflam/issue/COR-83/stream-deep-fetch-reads-at-fixed-memory).
- **D-44** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P2. Deep-fetch depth beyond two hops.
- **D-45** → [COR-86](https://linear.app/flimflam/issue/COR-86/implement-history-with-includes-execution-and-empty-the-deferred). History-with-includes execution.
- **D-46**, **D-48** → [COR-85](https://linear.app/flimflam/issue/COR-85/report-nodes-whose-stored-state-violates-the-declared-model-instead-of). Stored state violating the declared model.
- **D-47** → fixed. `reduce_declared_members` gained `preserve_presence`, orthogonal to the `named_by` authored-member mask; `snapshot.materialize._convert._decode_element` passes it. Presence survives materialization at every containment depth, as `python.md` §3 and `core/spec/m-document-codec.md` state.
- **D-51** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P6, item 6d. A defining to-one whose foreign key sits on the target side.
- **D-52** → [COR-51](https://linear.app/flimflam/issue/COR-51/integrate-snapshot-writes-and-remove-legacy-frontend-surfaces). An ambiguous bare entity spelling silently unbinds a keyed write from its observation. Returns here if COR-51 re-defers it.
- **D-57** → [COR-51](https://linear.app/flimflam/issue/COR-51/integrate-snapshot-writes-and-remove-legacy-frontend-surfaces). `identity_row` carries raw primary-key values while `full_row` and `edited_row` carry serialized ones. Returns here if COR-51 re-defers it.

## History

Entries D-1 … D-51 were kept in per-ticket task directories under
`.humanlayer/tasks/`, which hold the full text of every resolved, closed, and
graduated entry. Consult them when a commit message or document cites a D-number
this file does not hold:

- `.humanlayer/tasks/cor-3-build-python-slice/05-deferred-ledger.md` — D-1 … D-37.
- `.humanlayer/tasks/cor-47-build-python-declarations/09-deferred-ledger.md` — D-36 … D-48.
