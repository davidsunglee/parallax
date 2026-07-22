# The API Conformance Suite and Usage Guide are MUST deliverables

A language implementation proves conformance two ways: the conformance adapter
grades wire-level behavior through a narrow CLI envelope, and the **API Conformance
Suite** proves the idiomatic developer surface reproduces the corpus, carrying a
paired **Usage Guide** rendered from the suite's own source. Both are MUST
deliverables; the mechanics are specified language-neutrally in
[`core/spec/m-api-conformance.md`](../../core/spec/m-api-conformance.md).

**Considered options.** MUST vs SHOULD vs self-declared scope was the real
trade-off. SHOULD was rejected because it recreates the discoverability failure the
suite fixes: an earlier implementation invented this proof under the name
"showcase," found it caught developer-facing bugs the wire grade ignores, but no
core document told the next implementer to build one or what makes it trustworthy.
Self-declared scope was rejected because it removes the no-silent-gaps property —
the mechanically-asserted coverage partition over the claimed slice — that makes
the suite *proof* rather than a demo.
