# TypeScript timestamps use Temporal.Instant with a microsecond boundary

The TypeScript API maps core `timestamp` values to `Temporal.Instant`, but Parallax accepts and emits only instants representable at core microsecond precision. `Temporal.Instant` has nanosecond precision, so the TypeScript boundary rejects values with non-zero sub-microsecond digits rather than silently truncating data that Postgres `timestamptz` and MariaDB `datetime(6)` cannot round-trip.
