/**
 * The normative m-dialect **`Dialect` interface** — layer-1 of the dialect seam.
 *
 * `Dialect` is the single authority over the per-database decision catalog
 * (`core/spec/m-dialect.md`): identifier quoting, ORDER BY / NULL
 * placement, the row-limit clause, in-transaction read-lock application, the
 * neutral-type → column-type vocabulary, driver-boundary placeholder syntax,
 * the typed-bind normalization rules, the normalize-at-boundary value parsers,
 * the infinity representation, and error-code classification. A concrete database (`postgresDialect`,
 * `mariadbDialect`) is *an implementation of* this contract; nothing above the
 * seam imports a concrete dialect — m-sql (`@parallax/sql`) compiles against this
 * **type**, and the composition roots inject the concrete instance.
 *
 * This module is type-only: it declares the contract and depends on `@parallax/core`
 * solely for the managed scalar carriers the parsers return. The implementations
 * live beside it (`postgres.ts`, `mariadb.ts`).
 */
import type { Infinity as InfinitySentinel, ParallaxDecimal, Temporal } from "@parallax/core";
import type { ErrorCategory } from "./errors.js";

/**
 * The normalize-at-boundary value parsers, keyed by **m-core neutral type** (not by a
 * driver's catalog code). An adapter maps its driver's type-codes → these neutral
 * keys and calls the matching parser, so the parse logic stays dialect-owned while
 * the code→key mapping stays adapter-owned (`m-db-port`).
 */
export interface DialectParsers {
  /** Raw `int8` text → native `bigint` (JS `number` cannot hold the full int64 range). */
  int8(raw: string): bigint;
  /** Raw `numeric` text → exact {@link ParallaxDecimal} (never a lossy binary float). */
  numeric(raw: string): ParallaxDecimal;
  /** Raw `timestamp`/`timestamptz` text → `Temporal.Instant`, or the infinity sentinel. */
  timestamp(raw: string): Temporal.Instant | InfinitySentinel;
  /** Raw `bytea`/`blob` rendering → `Uint8Array`. */
  bytes(raw: string): Uint8Array;
  /** Raw `date` text → `Temporal.PlainDate` (calendar date, no time/offset). */
  date(raw: string): Temporal.PlainDate;
  /** Raw `time` text → `Temporal.PlainTime` (wall-clock time, no date/offset). */
  time(raw: string): Temporal.PlainTime;
  /** Raw `uuid` text → canonical lowercase string. */
  uuid(raw: string): string;
}

/**
 * A produced SQL fragment plus the binds it introduces, in placeholder order —
 * the shape a divergent extraction/traversal decision point returns (modeled on
 * `bytesProjection`). The caller splices `sql` into the statement and appends
 * `binds` to its accumulator so the `?` holes and their values stay aligned.
 */
export interface DialectFragment {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/**
 * A resolved element predicate applied to ONE element of a `many` value object
 * (`m-value-object` to-many, `m-op-algebra`). The m-sql compiler resolves the
 * element-relative paths + literal types against the declared array member and
 * hands the dialect this **neutral** tree; each dialect renders it its own way
 * (`m-dialect` array-traversal form) — Postgres a general predicate over the
 * unnested element alias, MariaDB a `json_contains` candidate it can only build
 * from the equality forms (the containment-golden scope). Values are already
 * coerced to their canonical wire form.
 */
export type ResolvedElementPredicate =
  | {
      readonly op: "eq" | "notEq" | "gt" | "gte" | "lt" | "lte";
      readonly path: readonly string[];
      readonly value: unknown;
      readonly valueType: string;
    }
  | {
      readonly op: "in";
      readonly path: readonly string[];
      readonly values: readonly unknown[];
      readonly valueType: string;
    }
  | { readonly op: "isNull" | "isNotNull"; readonly path: readonly string[] }
  | { readonly op: "and" | "or"; readonly operands: readonly ResolvedElementPredicate[] }
  | { readonly op: "not" | "group"; readonly operand: ResolvedElementPredicate };

/**
 * The request the m-sql compiler hands the dialect to lower a to-many
 * value-object predicate through the `m-dialect` **array-traversal** decision
 * point. `column` is the alias-qualified structured-document column
 * (`t0.address`); `arrayPath` the document segments reaching the `many` member
 * (`['phones']`); `elementAlias` the alias the compiler allocated for the
 * Postgres set-returning unnest (unused by MariaDB's containment family);
 * `negated` distinguishes `nestedNotExists` from `nestedExists`; `element` the
 * per-element predicate (absent ⇒ a non-empty existence test).
 */
export interface NestedArrayRequest {
  readonly column: string;
  readonly arrayPath: readonly string[];
  readonly elementAlias: string;
  readonly negated: boolean;
  readonly element?: ResolvedElementPredicate;
}

/**
 * The single normative dialect contract. Every SQL-dialect variation the catalog
 * enumerates is a member here; a concrete database supplies one conforming object.
 */
export interface Dialect {
  /** The dialect identifier — `"postgres" | "mariadb"`; keys `goldenSql`/`expectedNativeCode`. */
  readonly id: string;

  // --- identifier quoting (consulted during assembly) ---
  /** Quote an identifier when reserved / non-simple: `"order"` (Postgres) vs `` `order` `` (MariaDB). */
  quoteIdentifier(name: string): string;

  // --- SQL-assembly decisions compile() consults ---
  /**
   * One ORDER BY term with this dialect's NULL placement (`m-dialect`): Postgres
   * `<col> asc` / `<col> desc nulls last`; MariaDB `is null, <col> asc` / `<col> desc`.
   */
  orderByTerm(qualifiedColumn: string, direction: "asc" | "desc"): string;
  /**
   * Apply the row-limit clause. Today every dialect appends ` limit ?`, but this is
   * a *wrappable* hook so a future dialect that must rewrite the query shape (e.g.
   * Oracle `ROWNUM`) can override rather than append.
   */
  rowLimit(sql: string): string;
  /**
   * **Apply** the in-transaction shared read-lock — the dialect owns whether, where,
   * and how it attaches. `locking` is the concurrency mode; `projection` is true for a
   * `select distinct`/aggregation read (no base row to lock ⇒ returned unchanged).
   */
  applyReadLock(
    sql: string,
    ctx: { readonly locking: boolean; readonly projection: boolean },
  ): string;

  /**
   * Lower a `bytes` column to this dialect's stable hex-text projection (a byte
   * column has no stable text rendering across drivers, so the SELECT projects it
   * to hex): Postgres `encode(<col>, ?) <out>` carrying a `'hex'` format bind;
   * MariaDB the argument-less `hex(<col>) <out>` carrying no bind. Returns the SQL
   * fragment plus any binds it introduces (spliced in projection order). This is
   * the one genuinely dialect-divergent projection shape (`m-core-001`/`m-core-004`).
   */
  bytesProjection(
    qualifiedColumn: string,
    outputName: string,
  ): { readonly sql: string; readonly binds: readonly unknown[] };

  // --- value-object structured-column lowering (m-value-object / m-sql) ---
  /**
   * The **nested extraction form** decision point (`m-dialect`): extract a scalar
   * from a structured-document column at the given document path. `baseExpression`
   * is the alias-qualified column (`t0.address`) or a to-many element expression
   * (`t1.value`); `segments` the document path (`['geo', 'country']`). The bind
   * shape **diverges** — Postgres `jsonb_extract_path_text(col, ?, …)` carries one
   * `?` per segment; MariaDB `json_value(col, ?)` carries one `'$.a.b'` path bind —
   * so this returns the SQL plus its own binds (`m-case-format` per-dialect binds).
   */
  nestedExtraction(baseExpression: string, segments: readonly string[]): DialectFragment;
  /**
   * The **typed cast form** decision point (`m-dialect`): wrap a text extraction in
   * a cast to a non-text declared neutral type before comparing (Postgres
   * `cast(… as double precision)` / `… as bigint`, MariaDB `cast(… as double)` /
   * `… as signed`). A `string` (or otherwise text) attribute compares directly, so
   * the extraction is returned unchanged.
   */
  typedCast(extraction: string, neutralType: string): string;
  /**
   * The **array traversal form** decision point (`m-dialect`): lower a to-many
   * value-object predicate. Postgres emits a correlated `jsonb_array_elements`
   * unnest under a `case`/`jsonb_typeof` array guard (fully general over the
   * element predicate); MariaDB the `json_contains` / `json_length` containment
   * family under a `json_type(json_extract(…)) = 'ARRAY'` guard — which lowers only
   * the equality forms of the containment golden and **rejects** a non-equality
   * element predicate with a capability diagnostic (the documented deferred
   * limitation). Returns the predicate SQL plus its per-dialect binds.
   */
  nestedArrayPredicate(request: NestedArrayRequest): DialectFragment;

  // --- schema / DDL vocabulary ---
  /** Map an m-core neutral type (+ optional max length) to this dialect's column type. */
  columnType(neutralType: string, maxLength?: number): string;

  /**
   * Normalize one managed runtime value for this dialect's driver boundary, with
   * the logical m-core neutral type available. Most values render to the neutral wire
   * form; dialects without native temporal infinity may keep timestamp values in
   * their managed carrier so the concrete adapter can bind them losslessly.
   */
  bindValue(neutralType: string, value: unknown): unknown;

  // --- driver-boundary binding syntax (applied by the ADAPTER, not compile) ---
  /** Rewrite canonical `?` placeholders to the driver's syntax (`?`→`$n` on Postgres; identity on MariaDB). */
  toPositionalPlaceholders(sql: string): string;

  // --- normalize-at-boundary value parsing (keyed by m-core neutral type) ---
  parsers: DialectParsers;

  // --- infinity representation (m-temporal-read) ---
  /** The bind value for temporal `infinity`: native `'infinity'` (Postgres) vs a max-sentinel datetime (MariaDB). */
  infinityBind(): unknown;

  // --- error classification (closed neutral category vocabulary) ---
  /** Native code (SQLSTATE string / vendor errno) → neutral {@link ErrorCategory}. */
  classifyErrorCode(code: string | number | null | undefined): ErrorCategory;
  /** Is a failure of this category retriable? (`= deadlock`). */
  isRetriable(category: ErrorCategory): boolean;
  /** Does this category denote a unique-index violation? (`= uniqueViolation`). */
  violatesUniqueIndex(category: ErrorCategory): boolean;
  /** Does this category denote a lock-wait timeout? (`= lockWaitTimeout`). */
  isTimedOut(category: ErrorCategory): boolean;
}
