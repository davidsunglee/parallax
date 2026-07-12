# Write instructions are hosted in m-unit-work, and cases declare compile eligibility

Reads have a canonical, language-neutral intermediate representation — the operation
algebra, pinned by `operation.schema.json` and hosted by `m-op-algebra`. Writes did not:
the keyed `writeSequence` shape and the predicate-selected write shape lived only inside
`compatibility-case.schema.json`, their instant surface overloaded (`at` meant the
processing instant on an audit-only step but the business-from on a bitemporal
`insertUntil`, and the business axis was spelled both `businessAt` and `businessFrom`).
Separately, the conformance contract assumed every claimed case command could be
compiled, but a minority of cases cannot: some intend a single-connection
concurrency/locking interaction, and others emit binds that are a function of a query
result, so a static `compile` cannot represent them.

Two coupled decisions resolve these gaps.

First, the write side gets a canonical IR **hosted, not moduled**. The instruction
vocabulary is extracted into [`core/schemas/write-instruction.schema.json`](../../core/schemas/write-instruction.schema.json)
— the write-side analogue of `operation.schema.json` — and its normative prose lands as
a section of `m-unit-work`, whose defining job is buffering exactly these instructions
and which already depends on `m-op-algebra` (making an embedded predicate legal
vocabulary). This adds no DAG node, no case re-tagging, and no canonical-claim churn,
mirroring how `m-op-algebra` hosts the operation schema. The canonical schema makes the
instant surface **axis-explicit** — business bounds named uniformly `businessFrom` /
`businessTo`, and the processing instant defined as harness / Clock-supplied context
rather than an instruction field — and defines a serde round-trip contract. The corpus's
`at` / `businessAt` / `until` spellings survive as **authoring aliases**; re-authoring
the corpus to the canonical spellings is deferred.

Second, a case declares its **compile eligibility**. A case is compile-eligible by
default; a top-level `compileEligibility` block declares it **run-only** when its
emissions cannot be a pure function of `when` + `given`, for one of two reasons:
`single-connection` (concurrency/locking intent) or `query-result-dependent`
(deep-fetch fan-out binds, materialized predicate writes, `sequence`-strategy PK
allocations, framework-owned observed-version / `in_z` binds). Eligibility is an
authored, reviewed intent declaration; the harness mechanically backstops the detectable
`single-connection` cases, and each language's refusing compile port structurally
enforces `query-result-dependent` at runtime. The adapter's `compile` answer for a
claimed run-only case is a defined `status: "run-only"` with a `compile-run-only`
diagnostic (exit code `11`) — not `unsupported`, which stays invalid for any claimed case
command. This is a genuine contract gap every language target would hit, fixed
consistently across spec, schemas, corpus, and harness rather than worked around in a
single implementation.

The normative homes are [`core/spec/m-unit-work.md`](../../core/spec/m-unit-work.md)
(the write-instruction vocabulary), [`core/spec/m-case-format.md`](../../core/spec/m-case-format.md)
(the compile-eligibility declaration), and
[`core/spec/m-conformance-adapter.md`](../../core/spec/m-conformance-adapter.md) (the
`run-only` compile answer). The behavioral DAG is unchanged: hosting the write IR in an
existing scope creates no new edge, and the eligibility declaration is a per-case
property, not a capability claim.
