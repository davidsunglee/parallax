# m-validtime-only — Valid-Time-Only Temporal Writes

`m-validtime-only` is the deferred **Valid-Time-Only** temporal formation. When
composed, this formation has one Valid-Time dimension and no Transaction-Time
dimension.

- **Edges:** `m-validtime-only --> m-temporal-read`, `m-validtime-only -->
  m-unit-work`.
- **Behavior.** Reads inject the single-axis as-of predicate over
  `from_z`/`thru_z` (`m-temporal-read`). Writes are driven by the Valid-Time
  instant at which the change takes effect and have no Transaction-Time
  residual. A Valid-Time-Only Entity cannot participate in temporal optimistic
  mode because it has no Transaction-Time `tx_start` version analogue.
