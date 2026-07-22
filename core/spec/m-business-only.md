# m-business-only — Valid-Time-Only Temporal Writes

The module ID `m-business-only` is a retained legacy identifier; its domain term
is **Valid-Time-Only**. When composed, this formation has one Valid-Time
dimension and no Transaction-Time dimension.

- **Edges:** `m-business-only --> m-temporal-read`, `m-business-only -->
  m-unit-work`.
- **Behavior.** Reads inject the single-axis as-of predicate over
  `from_z`/`thru_z` (`m-temporal-read`). Writes are driven by the Valid-Time
  instant at which the change takes effect and have no Transaction-Time
  residual. A Valid-Time-Only Entity cannot participate in temporal optimistic
  mode because it has no Transaction-Time `tx_start` version analogue.
