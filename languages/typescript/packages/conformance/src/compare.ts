/**
 * Adapter-boundary row comparison rules (m-conformance-adapter, the case's row comparison rules).
 *
 * A `run` envelope reports observed `rows` in the **neutral wire form** (§3.2.1):
 * an `int64` arrives as its canonical base-10 string (`"42"`), an exact
 * `decimal(p,s)` as its scale-aware string (`"20.00"`), a `boolean` as a JS
 * boolean, a `timestamp` as its microsecond UTC string. A case's `expectedRows`
 * are authored values parsed by the same serde (numbers / strings / booleans).
 * Comparing them faithfully needs the m-case-format rules, NOT JS `==`:
 *
 *  - **Type-aware scalar equality (carry-forward b).** When the projected column's
 *    m-core neutral type is known, it decides the grading axis: a **numeric** column
 *    (`int64` / `int32` / `float*` / `decimal(p,s)`) reconciles both sides in
 *    decimal space (so `"20.00"` == `20` and two numeric wire strings `"20.0"` /
 *    `"20.00"` compare in decimal, never as text), while a **textual** column
 *    (`string` / `uuid` / `date` / `time` / `timestamp` / `bytes`) is graded as
 *    EXACT text even against a numeric-looking value (so a `sku` of `"042"` never
 *    collapses to `42`). Booleans are their own type and never `== 1`.
 *  - **Genuine-numeric discriminator (fallback).** When no column type is supplied
 *    (a bare `scalarsEqual(a, b)` call, or a column absent from the type map),
 *    decimal space reconciles a numeric STRING only against a genuine `number` /
 *    `bigint`; two strings compare as exact canonical strings. This mirrors the
 *    Python oracle (`_to_decimal` never decimalizes a string) and is the correct
 *    intermediate the type-aware path refines.
 *  - **Microsecond timestamps.** Instant strings compare to microsecond
 *    precision (exact string equality on the canonical µs form).
 *  - **Order-insensitive row-set equality.** A read's rows are a SET: the
 *    observed and expected multisets must match regardless of order (the corpus
 *    makes ordering observable through membership + `limit`, never row order).
 *
 * The comparator lives in the harness (not the runner) because the runner is a
 * pure observation **producer**; grading observed-vs-expected is the harness's
 * job, shared by the run-lane tests and any external runner.
 */
import { ParallaxDecimal } from "@parallax/core";

/** A materialized row keyed by output column name. */
type Row = Record<string, unknown>;

/**
 * A projected `column -> m-core neutral type` map (e.g. `{ id: "int64", name:
 * "string", price: "decimal(18,2)" }`). Supplied by the caller from the metamodel
 * so a column is graded by its declared type; a column absent from the map (or an
 * omitted map) falls back to the genuine-numeric discriminator.
 */
export type ColumnTypes = Readonly<Record<string, string>>;

/** The outcome of comparing an observed row set against the expected one. */
export interface RowSetComparison {
  /** True when the two row sets are equal as order-insensitive multisets. */
  readonly equal: boolean;
  /** A human-readable reason when they differ (empty when equal). */
  readonly reason: string;
}

/**
 * Compare two row sets as **order-insensitive multisets** under the m-case-format scalar
 * rules. Rows match when they have the same column keys and every column's
 * values are scalar-equal (graded by the column's m-core type when supplied); the
 * sets match when each observed row pairs with a distinct expected row (greedy
 * one-to-one matching, correct for the small, duplicate-light corpus row sets).
 */
export function compareRowSet(
  observed: readonly Row[],
  expected: readonly Row[],
  columnTypes: ColumnTypes = {},
): RowSetComparison {
  if (observed.length !== expected.length) {
    return {
      equal: false,
      reason: `row count differs: observed ${observed.length}, expected ${expected.length}`,
    };
  }
  const remaining = expected.map((row) => row);
  for (const obs of observed) {
    const index = remaining.findIndex((exp) => rowsEqual(obs, exp, columnTypes));
    if (index === -1) {
      return { equal: false, reason: `no expected row matches observed ${JSON.stringify(obs)}` };
    }
    remaining.splice(index, 1);
  }
  return { equal: true, reason: "" };
}

/** Two rows are equal when they have the same keys and scalar-equal values. */
function rowsEqual(left: Row, right: Row, columnTypes: ColumnTypes): boolean {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  for (const key of leftKeys) {
    if (!(key in right)) {
      return false;
    }
    if (!scalarsEqual(left[key], right[key], columnTypes[key])) {
      return false;
    }
  }
  return true;
}

/**
 * Scalar equality under the m-case-format rules, reconciling the wire form of an observed
 * value with the authored form of an expected value. The optional `columnType`
 * is the projected column's m-core neutral type; it selects the grading axis:
 *
 *  - `null` matches only `null`.
 *  - booleans compare only to booleans (never `== 1`).
 *  - **numeric column** (`columnType` is `int64` / `int32` / `float*` /
 *    `decimal(p,s)`): both sides reconcile in **decimal space**, so a numeric
 *    wire string `"20.00"` equals the authored `20` and money never drifts —
 *    even when BOTH sides are strings (the column is authoritatively numeric).
 *  - **textual column** (`columnType` is `string` / `uuid` / `date` / `time` /
 *    `timestamp` / `bytes`): compared as **exact text**, even against a
 *    numeric-looking value — a textual `"042"` never collapses to `42`.
 *  - **no `columnType`** (fallback, oracle-faithful): decimal space reconciles a
 *    numeric string only against a genuine `number` / `bigint`; two strings
 *    compare as exact canonical strings (the Python oracle's `str == str`).
 *  - everything else compares as exact strings (timestamps to µs, uuid, text,
 *    hex bytes, dates, times).
 *
 * **Why the fallback discriminator (oracle fidelity).** The Python oracle
 * (`reference_harness.case_runner._scalars_equal` / `_to_decimal`) decimalizes
 * ONLY native `int` / `float` / `Decimal`, never a `str`. TypeScript's driver
 * path produces the canonical *string* wire form instead, so the comparator must
 * decimalize a numeric string — but, absent a column type, ONLY to reconcile it
 * against a genuine numeric counterpart. The type-aware path is the full form the
 * `08` MAJOR deferred: it grades a textual column as text and a numeric column in
 * decimal space regardless of which side is the string.
 */
export function scalarsEqual(observed: unknown, expected: unknown, columnType?: string): boolean {
  if (observed === null || expected === null) {
    return observed === expected;
  }
  // Boolean is its own type: never coerced to/from 1/0.
  if (typeof observed === "boolean" || typeof expected === "boolean") {
    return observed === expected;
  }

  // Type-aware grading (carry-forward b), when the column's m-core type is known.
  if (columnType !== undefined) {
    if (isNumericType(columnType)) {
      const obsNumeric = asDecimal(observed);
      const expNumeric = asDecimal(expected);
      if (obsNumeric !== undefined && expNumeric !== undefined) {
        return obsNumeric.equals(expNumeric);
      }
      // A numeric column with a non-numeric value on a side (should not happen
      // for well-formed wire data): fall through to exact-string comparison so a
      // malformed value surfaces rather than silently matching.
      return String(observed) === String(expected);
    }
    // A textual column is graded as exact text, even against a numeric value.
    return String(observed) === String(expected);
  }

  // Fallback (no column type): decimal space only reconciles a numeric STRING
  // against a genuine number / bigint. When neither side is a genuine
  // number/bigint (both are strings), fall through to exact-string equality —
  // matching the Python oracle, which never decimalizes strings.
  if (isGenuineNumber(observed) || isGenuineNumber(expected)) {
    const obsNumeric = asDecimal(observed);
    const expNumeric = asDecimal(expected);
    if (obsNumeric !== undefined && expNumeric !== undefined) {
      return obsNumeric.equals(expNumeric);
    }
  }

  // Non-numeric, or two strings (text / uuid / timestamp µs string / date /
  // time / hex bytes / two canonical numeric wire strings): exact string
  // equality on the canonical wire form.
  return String(observed) === String(expected);
}

/**
 * Element-wise scalar equality over two ordered bind lists, under the same m-case-format
 * scalar rules ({@link scalarsEqual}, no column type — the genuine-numeric
 * discriminator reconciles a decimal money value across representations). The
 * write-sequence / conflict compile lanes use it to cross-check the binds a
 * generating adapter DERIVES from the neutral write input (①) against the
 * authored golden binds (②) — a genuine independent check, never a golden parse.
 */
export function bindsEqual(left: readonly unknown[], right: readonly unknown[]): boolean {
  return (
    left.length === right.length && left.every((value, index) => scalarsEqual(value, right[index]))
  );
}

// --- table-state comparison (write sequences) -------------------------------

/** An observed / expected table state: table name -> its full row set. */
export type TableState = Readonly<Record<string, readonly Row[]>>;

/**
 * Compare an observed table state against `expectedTableState` (m-temporal-read write
 * sequences). Each named table's rows are compared as an order-insensitive
 * multiset under the m-case-format scalar rules (exact decimal, µs timestamps, native
 * `infinity` read back as the `"infinity"` string), graded by each column's m-core
 * type. The tables must match on the set the expected state names.
 */
export function compareTableState(
  observed: TableState,
  expected: TableState,
  columnTypes: ColumnTypes = {},
): RowSetComparison {
  const expectedTables = Object.keys(expected).sort();
  for (const table of expectedTables) {
    const comparison = compareRowSet(observed[table] ?? [], expected[table] ?? [], columnTypes);
    if (!comparison.equal) {
      return { equal: false, reason: `table '${table}': ${comparison.reason}` };
    }
  }
  return { equal: true, reason: "" };
}

// --- graph comparison -------------------------------------------------------

/** A decorated graph observation: root entity domain name -> decorated rows. */
export type Graph = Readonly<Record<string, readonly Row[]>>;

/**
 * Resolve the m-core type of a (possibly-nested) output column by physical column
 * name across every projected entity. Deep-fetch child columns (`order_id`,
 * `code`, …) live on their own entities, so the caller supplies one flat map
 * merged across the root + every fetched entity (physical column names are
 * unique enough within the orders corpus to key by name).
 */
export type GraphColumnTypes = ColumnTypes;

/**
 * Compare two decorated graphs structurally under the same scalar rules. Each
 * root entity's row list is compared as an order-insensitive multiset; a row's
 * relationship-valued keys (an array for to-many, an object / `null` for to-one)
 * recurse under the same rules, so childless parents (`items: []`) and to-one
 * `null` peers grade correctly. Scalar columns grade by `columnTypes` when known.
 */
export function compareGraph(
  observed: Graph,
  expected: Graph,
  columnTypes: GraphColumnTypes = {},
): RowSetComparison {
  const obsKeys = Object.keys(observed).sort();
  const expKeys = Object.keys(expected).sort();
  if (obsKeys.length !== expKeys.length || obsKeys.some((k, i) => k !== expKeys[i])) {
    return {
      equal: false,
      reason: `graph root entities differ: observed [${obsKeys}], expected [${expKeys}]`,
    };
  }
  for (const key of obsKeys) {
    const comparison = compareNodeList(observed[key] ?? [], expected[key] ?? [], columnTypes);
    if (!comparison.equal) {
      return { equal: false, reason: `under root '${key}': ${comparison.reason}` };
    }
  }
  return { equal: true, reason: "" };
}

/**
 * Compare two lists of graph nodes as an order-insensitive multiset. Two nodes
 * are equal when they carry the same keys and every value is equal under
 * {@link nodeValuesEqual} (scalars by the scalar rules, relationships recursively).
 */
function compareNodeList(
  observed: readonly Row[],
  expected: readonly Row[],
  columnTypes: ColumnTypes,
): RowSetComparison {
  if (observed.length !== expected.length) {
    return {
      equal: false,
      reason: `node count differs: observed ${observed.length}, expected ${expected.length}`,
    };
  }
  const remaining = expected.map((row) => row);
  for (const obs of observed) {
    const index = remaining.findIndex((exp) => nodesEqual(obs, exp, columnTypes));
    if (index === -1) {
      return { equal: false, reason: `no expected node matches observed ${JSON.stringify(obs)}` };
    }
    remaining.splice(index, 1);
  }
  return { equal: true, reason: "" };
}

/** Two graph nodes are equal when they have the same keys and equal values. */
function nodesEqual(left: Row, right: Row, columnTypes: ColumnTypes): boolean {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  for (const key of leftKeys) {
    if (!(key in right)) {
      return false;
    }
    if (!nodeValuesEqual(left[key], right[key], columnTypes[key], columnTypes)) {
      return false;
    }
  }
  return true;
}

/**
 * Compare one node value. A relationship-valued key is an array (to-many) or an
 * object / `null` (to-one), and recurses under the graph rules; a scalar grades
 * by the scalar rules (with the column's m-core type when known).
 */
function nodeValuesEqual(
  left: unknown,
  right: unknown,
  columnType: string | undefined,
  columnTypes: ColumnTypes,
): boolean {
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right)) {
      return false;
    }
    return compareNodeList(left as Row[], right as Row[], columnTypes).equal;
  }
  if (isPlainObject(left) || isPlainObject(right)) {
    if (!isPlainObject(left) || !isPlainObject(right)) {
      return false;
    }
    return nodesEqual(left, right, columnTypes);
  }
  return scalarsEqual(left, right, columnType);
}

/** True for a non-null, non-array object (a to-one related node). */
function isPlainObject(value: unknown): value is Row {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// --- scalar helpers ---------------------------------------------------------

/**
 * True when an m-core neutral type is numeric (graded in decimal space): the integer
 * families, the float families, and any `decimal(p,s)`. Everything else (string,
 * uuid, boolean, date, time, timestamp, bytes) is textual / its own type.
 */
function isNumericType(type: string): boolean {
  return (
    type === "int64" ||
    type === "int32" ||
    type === "int16" ||
    type === "int8" ||
    type === "float64" ||
    type === "float32" ||
    type === "float" ||
    type.startsWith("decimal")
  );
}

/** A genuine JS numeric value (a finite `number` or a `bigint`), not a string. */
function isGenuineNumber(value: unknown): boolean {
  return typeof value === "bigint" || (typeof value === "number" && Number.isFinite(value));
}

/**
 * Interpret a value as an exact decimal when it is a finite number, a bigint, or
 * a numeric string; otherwise `undefined` (it is genuinely textual). A boolean is
 * never numeric (handled before this is reached). A non-numeric string (e.g. a
 * timestamp `2024-…`) returns `undefined` so it compares as text.
 */
function asDecimal(value: unknown): ParallaxDecimal | undefined {
  if (typeof value === "bigint") {
    return ParallaxDecimal.from(value);
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? ParallaxDecimal.from(String(value)) : undefined;
  }
  if (typeof value === "string" && isNumericString(value)) {
    return ParallaxDecimal.from(value);
  }
  return undefined;
}

/** A plain signed decimal token (no exponent, no date/time punctuation). */
function isNumericString(text: string): boolean {
  return /^[+-]?(\d+\.?\d*|\.\d+)$/.test(text.trim());
}
