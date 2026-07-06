/**
 * The normative M11 **`Dialect` interface** — layer-1 of the dialect seam.
 *
 * `Dialect` is the single authority over the per-database decision catalog
 * (`core/spec/m11-dialect-seam.md`): identifier quoting, ORDER BY / NULL
 * placement, the row-limit clause, in-transaction read-lock application, the
 * neutral-type → column-type vocabulary, driver-boundary placeholder syntax,
 * the typed-bind normalization rules, the normalize-at-boundary value parsers,
 * the infinity representation, and error-code classification. A concrete database (`postgresDialect`,
 * `mariadbDialect`) is *an implementation of* this contract; nothing above the
 * seam imports a concrete dialect — M3 (`@parallax/sql`) compiles against this
 * **type**, and the composition roots inject the concrete instance.
 *
 * This module is type-only: it declares the contract and depends on `@parallax/core`
 * solely for the managed scalar carriers the parsers return. The implementations
 * live beside it (`postgres.ts`, `mariadb.ts`).
 */
import type { Infinity as InfinitySentinel, ParallaxDecimal, Temporal } from "@parallax/core";
import type { ErrorCategory } from "./errors.js";

/**
 * The normalize-at-boundary value parsers, keyed by **M0 neutral type** (not by a
 * driver's catalog code). An adapter maps its driver's type-codes → these neutral
 * keys and calls the matching parser, so the parse logic stays dialect-owned while
 * the code→key mapping stays adapter-owned (`m11:44-47`).
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
   * One ORDER BY term with this dialect's NULL placement (`m11:153-167`): Postgres
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

  // --- schema / DDL vocabulary ---
  /** Map an M0 neutral type (+ optional max length) to this dialect's column type. */
  columnType(neutralType: string, maxLength?: number): string;

  /**
   * Normalize one managed runtime value for this dialect's driver boundary, with
   * the logical M0 neutral type available. Most values render to the neutral wire
   * form; dialects without native temporal infinity may keep timestamp values in
   * their managed carrier so the concrete adapter can bind them losslessly.
   */
  bindValue(neutralType: string, value: unknown): unknown;

  // --- driver-boundary binding syntax (applied by the ADAPTER, not compile) ---
  /** Rewrite canonical `?` placeholders to the driver's syntax (`?`→`$n` on Postgres; identity on MariaDB). */
  toPositionalPlaceholders(sql: string): string;

  // --- normalize-at-boundary value parsing (keyed by M0 neutral type) ---
  parsers: DialectParsers;

  // --- infinity representation (M7) ---
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
