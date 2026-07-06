# m-business-only — Business-Only Temporal Writes (deferred)

**Status: deferred.** `m-business-only` is the **business-only** temporal flavor —
a `unitemporal-business` entity with a single `business` as-of dimension and **no
processing axis**. It is the thing deferred indefinitely; `m-bitemp-write` depends
on `m-audit-write` only and does **not** depend on it.

- **Edges:** `m-business-only --> m-temporal-read`, `m-business-only -->
  m-unit-work`.
- **Behavioral floor.** Reads inject the single-axis as-of predicate over
  `from_z`/`thru_z` (`m-temporal-read`). Writes are the same close-and-chain shape
  as audit-only — close the open business row and chain a new
  `[businessInstant, infinity)` row — but driven by the **business instant** the
  change takes effect rather than the transaction instant, and with **no
  processing-axis residual** (so no rectangle split). Cases
  `m-business-only-001`–`m-business-only-003` (insert / update-chaining /
  terminate) pin that floor and stay green; a business-only entity cannot
  participate in optimistic mode (no processing axis to derive the version
  analogue from). The full specification is deferred beyond that floor.
