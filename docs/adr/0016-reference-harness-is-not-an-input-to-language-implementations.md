# The reference harness is not an input to language implementations

The Python reference harness proves the compatibility corpus is internally
self-consistent; it is an executable oracle for that corpus, not a reference
architecture. Its internals — the SQL normalization strategy, the provider seam,
the assertion layering, and the module layout — are non-normative. Language
implementations MUST derive their design only from the spec modules,
`core/schemas/`, the compatibility corpus, and the conformance-adapter contract,
so that each target stays independent and idiomatic rather than reproducing the
harness's incidental structure. This is surprising precisely because the harness
is, elsewhere, the canonical `m-conformance-adapter` reference implementation — canonical for the
*corpus contract*, not for how any one language builds an ORM.
