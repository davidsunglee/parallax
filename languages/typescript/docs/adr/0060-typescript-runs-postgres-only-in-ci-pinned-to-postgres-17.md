# TypeScript V1 conformance stays Postgres-only while DB profiles include MariaDB

For V1, the official `parallax-conformance describe` claim remains a single
dialect — Postgres — provisioned with `@testcontainers/postgresql` pinned to the
`postgres:17` image. Postgres is the round-1 normative target
(`core/spec/m11-dialect-seam.md`), and the pin matches the image the reference
harness already uses (`reference-harness/src/reference_harness/providers/postgres.py`,
`POSTGRES_IMAGE = "postgres:17"`), verified during the design discussion. The two
are already aligned, so no harness change and no downgrade is required; if the
harness bumps its major, the TypeScript pin bumps with it.

The container sits behind the same provider seam the `parallax-conformance run` adapter consumes. Per-test resets go through the provider's `reset()` lifecycle: reset to a clean empty schema, apply generated DDL for the case's model, and load fixtures only when the core case lifecycle requires them. The normative Postgres reset is drop-and-recreate of the active schema, matching the Python provider's `drop schema if exists public cascade; create schema public` behavior. A Testcontainers snapshot/restore API may be used only as a documented provider-internal optimization with a drop/recreate fallback; the suite itself does not call container snapshot methods. Per-dialect golden SQL is selected by the provider's own `dialect` identifier, which is the `goldenSql` key; when a case has no entry for the active dialect, database execution is skipped and the dialect-agnostic checks (schema conformance, normalization, serde round-trip, equivalent encodings, round-trip count) still run — the same skip behavior the Python harness applies.

MariaDB is now shipped as the second concrete M11 dialect/adapter/provider, but
it is not added to the V1 adapter claim. It is covered by separate, explicit
database profiles: shared Docker-free dialect tests, shared adapter smoke, shared
provider contract, a selectable API Conformance lane, and the
`mariadb-curated-25` partial M12 profile. Cases without `goldenSql.mariadb` are
profile exclusions with reasons, not silent skips.

Running Postgres and MariaDB as a single all-or-nothing V1 conformance claim is
still rejected: it would make the V1 slice claim broader than the canonical
`slice-mvp-1` Postgres profile. MariaDB remains first-class evidence for the M11
seam, but as a declared partial database profile until its full case coverage is
claimed.
