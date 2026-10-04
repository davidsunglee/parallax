# Optimistic-lock version values are framework-owned

Parallax sources optimistic-lock version values from the row the unit of work observed and computes the advanced version itself. Callers never supply a raw version number; "caller-driven" refers only to conflict handling. Updating a versioned row the unit of work never observed is a read-before-write error, and a versioned update that changes no attribute issues no DML. The normative detail lives in `core/spec/m-opt-lock.md` §Version values are framework-owned.

## Amendment (2026-10): a caller may state the revision a write starts from

The decision above lets no caller supply a version number at all.

**Superseding decision:** a caller-addressed write — a patch or a replacement of an
object its caller names by key — states, as an argument of its own, the version an
earlier query returned, as a precondition on the state it starts from. The
statement is never a row member and never the new version: the gate binds it under
Optimistic, a locked read of the row is compared with it under Locking, and the
framework still computes the advance. Observed writes keep the rule above: their
version comes from the row the unit of work observed. The normative detail lives
in `core/spec/m-unit-work.md` *Caller-addressed writes* and `core/spec/m-opt-lock.md`
§Version values are framework-owned.
