# Source writes are admitted only by a read of the current attempt

An ordinary source mutation — `amend`, `replace`, `delete`, `terminate`, and
their bounded forms, Typed or Wire — is admitted only by Read Evidence a read of
the current writable transaction attempt produced, under either Effective
Concurrency Strategy, or by the standing authority of an insertion that attempt
admitted. A value a standalone read, a read-only transaction, or an earlier
attempt published is refused at the verb, whatever key or revision it shares
with the stored row. Admission also precedes the elimination of an empty
amendment, so an amendment that assigns nothing cannot pass an ineligible
source.

Under the Optimistic strategy a standalone observation used to license a write
in a later transaction, gated on the revision that read saw. That made one verb
carry two intents: "write what this attempt read", and "write only if the row
still holds what someone observed earlier". The second is a precondition the
caller holds, and replay must never rebase it; the first is evidence the
attempt gathers, and replay must gather it again. Carrying a captured value
across attempts blurred them: a replayed callback handed the previous attempt's
value wrote against a revision the replay never read, and a read-only result —
a new capability with no unit of work — would have become write authority
merely by being kept. A caller holding an earlier observation now states its
revision through a caller-addressed write (`amend_if`, `replace_if`), which
keeps that revision fixed across replay and fails as a precondition when it no
longer holds.

The empty-amendment exemption fell for the same reason. An unchanged value from
an ineligible source returned silently, and the same call refused the moment
any member was edited; admission now answers the same for both, while an
admitted empty amendment still buffers nothing and spends no evidence.

This supersedes the Optimistic outcome recorded by the 2026-08 amendment to
[Python ADR 0010](../../languages/python/docs/adr/0010-a-framework-managed-source-is-a-lifecycle-not-a-database-handle.md),
which let a standalone source's retained observation gate a later transaction's
write. ADR 0010's decision that a source is a value lifecycle rather than a
Database handle stands: provenance is unchanged, and admission is a separate
question asked after it.

Alternatives considered: keeping the Optimistic standalone license, which keeps
stale evidence alive across replay and makes read-only results licensing; and
refreshing a source's evidence when its write enrolls, as Reladomo's locking
mode does, which silently replaces the state the caller observed with the
current one. Both were rejected.

The contract lives in `core/spec/m-unit-work.md` (*Current-attempt source
admission*) and `core/spec/m-opt-lock.md` (*Version values are
framework-owned*).
