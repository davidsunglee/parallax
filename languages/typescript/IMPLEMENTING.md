# Implementing Parallax TypeScript

This handoff note is the operational path for the first TypeScript
implementation. The normative contract remains `core/spec`, `core/schemas`,
`core/compatibility`, and `languages/typescript/spec/01-implementation-spec.md`.

## First Claim

Implement the canonical `slice-mvp-1` conformance slice first. It is
an include-driven slice: a case is in scope only when it carries the
`slice-mvp-1` tag and passes the broad claim filters in
`core/spec/scope-and-tiers.md`.

The TypeScript adapter's `describe` response must claim exactly the canonical
slice capabilities, changing only the adapter identity:

```json
{
  "schemaVersion": "1",
  "command": "describe",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "capabilities": {
    "modules": ["m0","m1","m2","m3","m4","m5","m7","m8","m10","m11","m12"],
    "dialects": ["postgres"],
    "caseShapes": ["read","writeSequence","scenario","conflict"],
    "caseTags": { "include": ["slice-mvp-1"] },
    "commands": ["describe","compile","run"],
    "provisioning": "self-managed"
  }
}
```

Return `status: "unsupported"` for every out-of-slice command, dialect, case
shape, module tag, or case tag. Returning `unsupported` for an in-slice case is a
conformance failure.

## Workspace Shape

TypeScript implementation source lives under `languages/typescript/packages/*`.
The `languages/typescript/spec` and `languages/typescript/docs` directories are
documentation, not runtime packages.

The first scaffold should create real pnpm workspace packages that match the
package map in the TypeScript implementation spec, including the non-numbered
composition package `@parallax/typescript` for the CLI, generator config, public
facade, and generated-barrel support.

## First Milestones

1. Scaffold the workspace, package manifests, shared TypeScript config, vitest,
   dependency-cruiser, and empty `parallax` / `parallax-conformance` CLI entry
   points.
2. Make the dependency-boundary check fail on an illegal package import.
3. Implement M0 scalar utilities and M1 descriptor parsing/normalization until
   all descriptors in `core/compatibility/models` parse and round-trip through
   JSON and YAML.
4. Implement M2 operation serde until operations in `0001`, `0002`, and the
   `02xx` predicate cases parse and round-trip.
5. Implement the first database-backed walking skeleton:
   `core/compatibility/cases/0002-eq.yaml` compiles to matching Postgres SQL and
   binds, runs against `postgres:17`, and reports a valid conformance-adapter
   JSON envelope.
6. Expand by case family in dependency-graph order, using the tagged
   `slice-mvp-1` slice as the active matrix.

## Explicitly Out Of V1

Do not claim or implement these for the first slice unless the conformance claim
is deliberately expanded with matching green cases:

- aggregation and projection
- full M8 identity-cache and query-cache scenarios
- PK generation cases
- value-object and inheritance cases
- M9 detached merge-back lifecycle
- M11 database error classification
- bounded business-window and bitemporal rectangle-split writes
- MariaDB
- M13 benchmark command and numeric targets
- M14 cross-process coherence

## Verification

Use the smallest relevant TypeScript test while developing, then walk upward:

```sh
pnpm --filter @parallax/typescript test
pnpm --filter @parallax/typescript run typecheck
pnpm --filter @parallax/typescript run dep-graph
```

Also keep the core profile gate green:

```sh
just dep-graph
```

For database-backed work, report whether the Postgres conformance slice was run
or skipped, and why.
