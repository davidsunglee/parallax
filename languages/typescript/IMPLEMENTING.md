# Operating The TypeScript Implementation

This guide contains the TypeScript implementation's commands, database setup,
milestone checks, and status-reporting rules. It does not define the
implementation's design or repeat its canonical claim.

Before changing runtime code, follow the two-stage workflow in the
[repository README](../../README.md#building-a-language-implementation) and the
[root implementation guide](../../IMPLEMENTING.md). Treat the completed
[TypeScript language spec](spec/01-implementation-spec.md) as the source of
TypeScript API, lifecycle, source-boundary, deployable-topology, database, and
quality-toolchain decisions. The [slice catalog](../../core/spec/slices.md) is
the sole source of the current claim's capabilities and case membership.

The reference harness's internals are non-normative and MUST NOT be used as
design input. The binding inputs are the core module specs, schemas,
compatibility corpus, conformance-adapter contract, and completed TypeScript
language spec.

## Operational Milestones

Use the dependency-respecting common spine and lifecycle branch in the
[root guide](../../IMPLEMENTING.md#dependency-respecting-milestones)
for sequencing. At each milestone, run the narrowest applicable TypeScript
check below before expanding to the active-claim verification lanes.

| Milestone evidence | Command |
| --- | --- |
| Workspace, source boundaries, lint, and static types | `just ts-lint && just ts-typecheck && just ts-typecheck-tests` |
| Unit-level internal seams and diagnostics | `just ts-test` |
| Package exports and built-artifact health | `just ts-package-check` |
| Dialect and provider-profile declarations without Docker | `just ts-db-fast` |
| Active-claim compile coverage and capability honesty | `just ts-conformance-compile` |
| Primary database adapter, compatibility matrix, API suite, and Usage Guide | `just ts-db` |
| Additional database profile and API lanes | `just ts-db-all` |

Case-focused development must select the intersection of the active
Conformance Slice tag and the capability tags for the current milestone. Do not
use filename prefixes as the complete selection rule. The initial database
proof is a tracer case or walking skeleton, not a Conformance Slice.

## Local Database Setup

Install the repository's pinned Node dependencies and make sure a
Docker-compatible daemon is available:

```sh
pnpm install --frozen-lockfile
docker info
```

The database-backed Vitest suites provision their containers and reset schemas
through the TypeScript provider composition root; no manually maintained local
schema is required. Postgres is the default API Conformance Suite database.
Select an explicitly supported alternative for a focused run with
`PARALLAX_DATABASES`, for example:

```sh
PARALLAX_DATABASES=postgres pnpm exec vitest run \
  --root languages/typescript packages/typescript/test/api-conformance
PARALLAX_DATABASES=mariadb pnpm exec vitest run \
  --root languages/typescript packages/typescript/test/api-conformance
```

Use the named `just ts-db` and `just ts-db-all` recipes for the maintained
provider profiles rather than reconstructing profile membership by hand.

## Focused Development Commands

Run a single TypeScript test file while developing, then move upward through
the milestone checks:

```sh
pnpm exec vitest run --root languages/typescript path/to/test.ts
pnpm run ts:typecheck
pnpm run ts:lint
```

Keep the core claim and dependency gates green when implementation boundaries
or conformance selection change:

```sh
just core-dep-graph
just core-schemas
```

The repository-level primary merge gate is:

```sh
just verify
```

## Status And Verification Reporting

Treat the commands above as executable status: a milestone is complete only
when its applicable command is green. Every implementation handoff must report:

- the active canonical claim, obtained from the implementation's `describe`
  response and checked against `core/spec/slices.md`;
- the smallest active-claim and capability-tag intersection exercised;
- the static, package, adapter, API, and root commands that ran;
- each database-backed command skipped, with the unavailable substrate or
  other reason; and
- any blocker that requires a decision change in the completed TypeScript
  language spec.

If a blocker changes an API, lifecycle, topology, provider, or quality-toolchain
decision, update the completed language spec first. Keep this guide operational.
