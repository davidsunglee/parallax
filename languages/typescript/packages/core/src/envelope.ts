/**
 * Adapter-envelope types for the `parallax-conformance` CLI.
 *
 * These mirror `core/schemas/conformance-adapter.schema.json`: every command
 * writes exactly one JSON document to stdout that validates against that schema,
 * discriminated by a top-level `oneOf` over describe / compile / run / benchmark
 * `ok` shapes and a single `nonOk` shape covering `unsupported` and `error`.
 *
 * The schema is the source of truth; these types are the in-memory mirror the
 * adapter assembles before serializing. Validation against the schema itself is
 * performed with ajv (see `@parallax/conformance`).
 */

/** `schemaVersion` is the constant `"1"` on every envelope. */
export const SCHEMA_VERSION = "1" as const;
export type SchemaVersion = typeof SCHEMA_VERSION;

/** The conformance-adapter sub-commands. */
export type Command = "describe" | "compile" | "run" | "benchmark";

/** Case shapes the harness discriminates. */
export type CaseShape =
  | "read"
  | "writeSequence"
  | "scenario"
  | "conflict"
  | "coherence"
  | "error"
  | "concurrencySuccess"
  | "boundary";

/**
 * A canonical module tag from the closed catalog (`core/spec/modules.md`). The
 * catalog is closed, so this is the exact union of the 32 module slugs — adding a
 * module is one union member.
 */
export type ModuleTag =
  | "m-core"
  | "m-descriptor"
  | "m-pk-gen"
  | "m-inheritance"
  | "m-value-object"
  | "m-op-algebra"
  | "m-agg"
  | "m-sql"
  | "m-sql-agg"
  | "m-dialect"
  | "m-db-port"
  | "m-db-error"
  | "m-navigate"
  | "m-deep-fetch"
  | "m-op-list"
  | "m-batch-write"
  | "m-cascade-delete"
  | "m-unit-work"
  | "m-read-lock"
  | "m-auto-retry"
  | "m-process-cache"
  | "m-temporal-read"
  | "m-audit-write"
  | "m-bitemp-write"
  | "m-business-only"
  | "m-detach"
  | "m-opt-lock"
  | "m-case-format"
  | "m-conformance-adapter"
  | "m-api-conformance"
  | "m-perf-bench"
  | "m-coherence";

/**
 * Adapter identity object carried by every envelope. For the TypeScript
 * adapter this is `{ language: "typescript", name: "@parallax/typescript",
 * version: "0.1.0" }`.
 */
export interface AdapterIdentity {
  readonly language: string;
  readonly name: string;
  readonly version: string;
}

/** Tag filters that narrow broad module / case-shape claims. */
export interface CaseTagClaims {
  readonly include?: readonly string[];
  readonly exclude?: readonly string[];
}

/** The capability claim returned by `describe`. */
export interface Capabilities {
  readonly modules: readonly ModuleTag[];
  readonly dialects: readonly string[];
  readonly caseShapes: readonly CaseShape[];
  readonly caseTags?: CaseTagClaims;
  readonly commands: readonly Command[];
  readonly provisioning: "external-url" | "self-managed";
}

/** A JSON-serializable bind value. */
export type BindValue =
  | string
  | number
  | boolean
  | null
  | readonly BindValue[]
  | { readonly [key: string]: BindValue };

/** A single emitted statement plus its ordered binds and a case pointer. */
export interface Emission {
  readonly casePointer: string;
  readonly sql: string;
  readonly binds: readonly BindValue[];
}

/** A materialized row (column name → value). */
export type Row = Record<string, unknown>;

/** An identity assertion produced by `scenario` runs (`sameObjectAs`). */
export interface IdentityCheck {
  readonly left: string;
  readonly right: string;
  readonly same: boolean;
  readonly identity?: unknown;
}

/** Observations produced by `run`. `roundTrips` is required and lives here. */
export interface Observations {
  readonly roundTrips: number;
  readonly rows?: readonly Row[];
  readonly graph?: Record<string, unknown> | null;
  readonly tableState?: Record<string, readonly Row[]> | null;
  readonly affectedRows?: number | null;
  readonly identityChecks?: readonly IdentityCheck[];
}

/** A diagnostic carried by `unsupported` / `error` envelopes. */
export interface Diagnostic {
  readonly code: string;
  readonly message: string;
  readonly casePointer?: string;
  readonly details?: unknown;
}

/** `describe` success envelope. */
export interface DescribeOk {
  readonly schemaVersion: SchemaVersion;
  readonly command: "describe";
  readonly status: "ok";
  readonly adapter: AdapterIdentity;
  readonly capabilities: Capabilities;
}

/** `compile` success envelope. `roundTrips` is top-level for compile. */
export interface CompileOk {
  readonly schemaVersion: SchemaVersion;
  readonly command: "compile";
  readonly status: "ok";
  readonly adapter: AdapterIdentity;
  readonly case: string;
  readonly dialect: string;
  readonly caseShape: CaseShape;
  readonly emissions: readonly Emission[];
  readonly roundTrips: number;
}

/** `run` success envelope. `roundTrips` lives inside `observations`. */
export interface RunOk {
  readonly schemaVersion: SchemaVersion;
  readonly command: "run";
  readonly status: "ok";
  readonly adapter: AdapterIdentity;
  readonly case: string;
  readonly dialect: string;
  readonly caseShape: CaseShape;
  readonly emissions: readonly Emission[];
  readonly observations: Observations;
}

/** `unsupported` / `error` envelope. */
export interface NonOk {
  readonly schemaVersion: SchemaVersion;
  readonly command: Command;
  readonly status: "unsupported" | "error";
  readonly adapter: AdapterIdentity;
  readonly diagnostics: readonly Diagnostic[];
}

/** Any single envelope the adapter may emit (sans benchmark, deferred). */
export type Envelope = DescribeOk | CompileOk | RunOk | NonOk;

/**
 * Process exit codes, part of the adapter contract:
 * `0` ok, `10` unsupported, `1` error, `2` CLI usage error.
 */
export const ExitCode = {
  Ok: 0,
  Unsupported: 10,
  Error: 1,
  Usage: 2,
} as const;

export type ExitCode = (typeof ExitCode)[keyof typeof ExitCode];
