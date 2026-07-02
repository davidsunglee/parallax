# Parallax TypeScript

Parallax TypeScript is the first language implementation of the language-neutral
[Parallax](../../README.md) core contract: an idiomatic TypeScript API, a
descriptor-driven code generator, and a conformance adapter that proves the
generated API reproduces the shared compatibility corpus.

The normative contract is always the core specification in
[`../../core/spec`](../../core/spec), the schemas in `../../core/schemas`, and the
compatibility corpus in `../../core/compatibility`. This directory records only
the TypeScript choices the core deliberately leaves open, plus the code that
discharges them.

> The reference harness's internals are non-normative and MUST NOT be used as
> design input for a language implementation; the binding inputs are the spec
> modules, `core/schemas/`, the compatibility corpus, and the conformance-adapter
> contract.

## Conformance Slice

TypeScript V1 declares the canonical **`slice-mvp-1`** Conformance Slice defined
in [`../../core/spec/scope-and-tiers.md`](../../core/spec/scope-and-tiers.md). It
claims the cases tagged `slice-mvp-1` across modules M0–M5, M7, M8, M10, M11, and
M12, on the Postgres dialect, for the `read`, `writeSequence`, `scenario`, and
`conflict` case shapes.

Capabilities the core defines but this first slice does not yet claim —
aggregation and projection, the M8 identity/query caches, value objects,
inheritance, bounded business-window and bitemporal writes, MariaDB, M13
benchmarks, and M14 coherence, among others — are documented as future
TypeScript surface but are not claimed until their compatibility slice passes.
The full deferral list is in
[`spec/00-overview.md`](spec/00-overview.md) §16.

The adapter's machine-readable form is a `describe` envelope whose `capabilities`
are byte-equal to the canonical slice, differing only in adapter identity. An
anti-drift test in the reference harness asserts that equality so the two can
never silently diverge — see [`IMPLEMENTING.md`](IMPLEMENTING.md).

## Two Proofs

The slice is proven the two official ways described under
[Building A Language Implementation](../../README.md#building-a-language-implementation)
in the root README:

- **Conformance-adapter grade.** The `parallax-conformance` CLI emits the wire
  envelope defined by
  [`../../core/spec/conformance-adapter-contract.md`](../../core/spec/conformance-adapter-contract.md);
  its SQL and observations are compared against the corpus oracles.
- **API Conformance Suite and Usage Guide.** The idiomatic `px.*` API is run
  through the shipped `@parallax/db-postgres` adapter against a real Postgres,
  reproducing the corpus results (contract:
  [`../../core/spec/api-conformance-contract.md`](../../core/spec/api-conformance-contract.md)).
  The suite lives in `packages/typescript/test/api-conformance/`, and the
  developer [Usage Guide](docs/guide/index.md) is rendered from that suite's
  source, so it can never drift from tested code.

## The Developer Surface

Applications import a generated API through the package-local `#parallax` alias
and drive it through a single `Parallax` handle, conventionally named `px`:

```ts
import { Order, parallax, type Parallax } from "#parallax";

const px: Parallax = parallax({ database, clock });

// Reads return an async, operation-backed ParallaxList.
const orders = await px.orders
  .find(
    Order.status.eq("Processing").and(
      Order.lineItems.exists(item => item.quantity.gt(2)),
    ),
    {
      includes: [Order.customer, Order.lineItems.product],
      orderBy: [Order.createdAt.desc(), Order.id.asc()],
      limit: 50,
    },
  )
  .toArray();

// Writes require an explicit transaction.
await px.transaction(async tx => {
  const order = await tx.orders.create(input);
  await tx.orders.update(Order.id.eq(order.id), {
    set: [Order.status.set("Processing")],
  });
});
```

One generated fluent expression DSL covers predicates, relationship navigation,
includes, ordering, and assignments. Temporal reads use `Temporal.Instant` and
the core axis names; snapshots are the plain-JSON detached surface; entity
inputs (`OrderInput.parse` / `safeParse`) validate create payloads; and the
public error hierarchy is rooted at `ParallaxError`. The full surface is
specified in
[`spec/01-implementation-spec.md`](spec/01-implementation-spec.md) and toured in
the [Usage Guide](docs/guide/index.md).

Code generation is descriptor-first — the source of truth is the canonical
Parallax descriptor set, configured with `defineParallaxConfig`. Generated output
is derived code (gitignored, regenerated on install, build, and CI). Two CLIs
ship: `parallax` (`init`, `generate`, `generate --check`) and
`parallax-conformance` (`describe`, `compile`, `run`).

## Layout

```text
languages/typescript/
  spec/           TypeScript language spec (00-overview, 01-implementation-spec)
  packages/       pnpm workspace of @parallax/* packages (runtime, adapter, CLI)
  docs/
    guide/        Usage Guide, rendered from the API Conformance Suite
    adr/          TypeScript architecture decision records
  examples/
    orders-app/   Runnable example: descriptors, config, and the generated API
  scripts/        Coverage and guide-rendering tooling
  IMPLEMENTING.md Operational path for the first implementation
  AGENTS.md       Standing instructions for agents working in this directory
  CONTEXT.md      TypeScript API glossary
```

Runtime source lives under `packages/*`; `spec/` and `docs/` are documentation.
The non-numbered `@parallax/typescript` package is the composition package — the
CLI, generator config, public runtime facade, and generated-barrel support. The
full package map is in
[`spec/01-implementation-spec.md`](spec/01-implementation-spec.md).

## Building And Verifying

The workspace uses pnpm and is driven from the repository root through `just`:

```bash
just ts-typecheck            # tsc -b across project references
just ts-lint                 # Biome + the dependency-cruiser DAG gate
just ts-test                 # vitest unit / adapter tests
just ts-conformance-compile  # full-slice compile sweep + honesty gate (Docker-free)
just ts-conformance-run      # the slice end-to-end over postgres:17 (Docker)
just ts-api-conformance      # API Conformance Suite + Usage Guide drift check (Docker)
```

`just verify` from the repository root runs the whole merge gate: both
conformance lanes, the API Conformance Suite lane, the static checks (typecheck,
Biome, dependency-cruiser, package-export health), and the Python suite. The
Docker-backed lanes provision Postgres through Testcontainers.

## Learn More

- [`spec/00-overview.md`](spec/00-overview.md) — the TypeScript surface at a glance
- [`spec/01-implementation-spec.md`](spec/01-implementation-spec.md) — the normative TypeScript spec
- [`IMPLEMENTING.md`](IMPLEMENTING.md) — first claim, milestones, and verification
- [Usage Guide](docs/guide/index.md) — a tour of the API, rendered from tests
- [`examples/orders-app`](examples/orders-app) — a runnable example application
- [`CONTEXT.md`](CONTEXT.md) — the TypeScript API glossary
- [Root README](../../README.md#building-a-language-implementation) — the slice-first process for any language
