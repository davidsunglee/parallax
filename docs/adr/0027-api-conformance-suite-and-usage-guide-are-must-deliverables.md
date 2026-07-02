# The API Conformance Suite and Usage Guide are MUST deliverables

A language implementation proves conformance two ways: the conformance adapter
grades wire-level behavior through a narrow CLI envelope, and the **API Conformance
Suite** proves the idiomatic developer surface reproduces the corpus by running the
code an application actually writes — through the shipped adapter, against a real
database — and asserting the corpus's expected results. The suite carries a
paired **Usage Guide**, a rendered document generated from the suite's own source
with a CI drift check. Both are MUST deliverables, specified language-neutrally in
[`core/spec/api-conformance-contract.md`](../../core/spec/api-conformance-contract.md);
the TypeScript suite (`test/api-conformance/` + `docs/guide/`) is the worked
example. The suite is additive proof beside the adapter grade — it never replaces
the grade and never touches the grader.

**Considered options.** MUST vs SHOULD vs self-declared scope was the real
trade-off. SHOULD was rejected because it recreates the discoverability failure the
suite fixes: the TypeScript implementation invented this proof under the name
"showcase," found it caught developer-facing bugs the wire grade ignores, but no
core document told the next implementer to build one or what makes it trustworthy.
Self-declared scope was rejected because it removes the no-silent-gaps property —
the mechanically-asserted coverage partition over the claimed slice — that makes
the suite *proof* rather than a demo. Requiring the portable properties (coverage
partition, reasoned skips, no-drift guard, corpus-oracle assertions, guide rendered
from suite source) while leaving each mechanism language-local keeps the bar high
without pinning any language to TypeScript's tooling.
