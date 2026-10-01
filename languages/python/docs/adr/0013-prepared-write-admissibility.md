# Prepared writes are the sole admissibility judgment

Every write ingress — the Typed keyed and `_where` verbs, their `tx.wire`
peers, and the conformance engine's case ingress — reaches the Unit of Work
through `prepare_typed_write` or `prepare_wire_write`, and those two producers
are the only place a write is judged against its target. Each resolves the
target first, then judges whether the target admits the verb (a temporal target
refuses `delete`), the window (stated as the verb's form requires, admitted by
the target's temporal profile, and ordered), the verb's other applicability (a
non-temporal target refuses a milestone verb), and a temporal keyed
instruction's single row. Only then is the payload judged: a keyed row's
subtype shape, members, and values, or a predicate-selected write's predicate,
family refusal, and assignments, each assignment completed — its member
resolved, then its value prepared and judged — before the next.

Snapshot ingress keeps only what needs a live transaction or a representation:
lifecycle re-entry, Wire document shape, source provenance and pin, and the
acquisition of authored input through the representation's own codec. A keyed
source acquires its row after provenance and pin and hands the caller's raw
bounds to preparation, so an acquisition refusal can precede a window refusal.
Neither the predicate buffering seam nor write settlement re-judges family,
verb applicability, or temporal row count; settlement keeps only routing and
execution refusals such as a missing Temporal Observation.

`PreparedKeyedWrite` and `PreparedPredicateWrite` are frozen slotted
`init=False` dataclasses built only by private factories in their defining
module; `derive_keyed_write` retains already-owned rows through the same
factory. Strict pyright's private-usage rule and the absent field constructor
are the enforcement. A settlement assertion would be a second copy of the rule
reachable through no interface, and an AST architecture test would restate what
the type already enforces.

Instruction bounds are `datetime | None`. A serialized instruction's bounds are
finite `m-wire` timestamps decoded by `deserialize`; explicit `infinity` is
refused rather than read as omission, and an unbounded write omits `until`.
A non-instant bound is `InstantError`; pairing, profile, and order refusals are
`WriteInstructionError`, as are assignment composition faults on every ingress.

This supersedes the assignment-error part of ADR 0007: a Typed `_where`
assignment that is absent, duplicated, or addresses another Entity no longer
raises `QueryDefinitionError(code="query-assignment-target-mismatch")` before
the family refusal. It is judged by preparation after the predicate and the
family, raises `WriteInstructionError`, and the code leaves the query-definition
vocabulary; `query-not-mutation-compatible` remains the query's own refusal. A
Typed predicate target the connected model does not declare is likewise refused
by preparation with `WriteInstructionError` rather than `QueryTargetError`.
