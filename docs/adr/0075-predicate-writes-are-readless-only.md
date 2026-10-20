# Predicate writes are readless only

A predicate-selected write is one readless statement over an unversioned,
non-temporal target. Preparation refuses a predicate write whose target is
versioned or temporal with the portable pre-SQL rule
`set-based-write-target-unsupported`, before its predicate, inheritance family,
or payload is judged, and the refusal names the writes that do reach such a
target: a read followed by keyed writes, or a caller-addressed write stating the
revision its caller holds (`m-batch-write`). This supersedes ADR 0014, and with
it the Materialized Write Group that ADR 0041 admits as planning's one
result-dependent input and whose selection claims ADR 0057 states: a predicate
write now selects, claims, and observes nothing, so neither part has a subject.

Materialization was the same work as a read plus keyed writes — the same lock,
the same per-object observation, the same `1 + N` round trips — with less
expressiveness, since it refused ordering, limits, as-of selection, includes,
and inheritance families. It also changed the cost and the no-op rule of one
call silently when an Entity became versioned or temporal: one statement became
an unpaged read of every match plus a write per row, and one optimistic conflict
aborted all of them. Refusing at preparation makes that model change fail loudly
at the call instead. Only the readless form does something no other verb can,
so it is the whole of the family.

The family's shape follows from that. A predicate write has no Valid-Time
window, because no readless target has Valid Time, so `terminate_where` and the
bounded forms leave it. It gains `replace_where`, which states a whole state as
a canonical `row` completed by the same rules as every other replacement; a key
the payload carries addresses nothing and is never written. An amendment that
assigns nothing is judged in full and then dropped, as it is for keyed and
caller-addressed amendments. The affected-row count a readless write could
report belongs to the later work that runs it at the call.

Two alternatives were rejected. Widening `subtype-write-set-based-unsupported`
to cover these targets would conflate it with the refusal of keyless row writes
to an inheritance family, which is a different rule. Separate codes for
versioned and temporal targets would split one rule whose cases differ only in
the advice they give.
