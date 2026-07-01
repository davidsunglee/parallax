/**
 * The real-DB developer-showcase harness (Phase 10c).
 *
 * Every showcase case runs the SAME developer code an application would write —
 * `px.*` / `px.transaction` over the SHIPPED `@parallax/db-postgres` adapter — and
 * asserts the corpus's expected results AND the managed shapes (10b). It does NOT
 * touch the grader: the official conformance grade stays contract-driven over the
 * generic runtime (ADR-0010). This harness is additive proof that the shipped
 * adapter + the developer surface produce the corpus's results.
 *
 * Per case it:
 *  1. provisions the case's schema on ONE shared Testcontainers `postgres:17` via
 *     the **Phase 3 provider** (`PostgresProvider` — `reset` / `applyDdl` /
 *     `loadFixtures`, the grader-side provisioning half), and
 *  2. builds a `px` / `tx` handle bound to a **`@parallax/db-postgres`** instance on
 *     that same container (NOT a bespoke provider) — the production path.
 *
 * Three assertion helpers:
 *  - `assertSameOperation(dsl, case)` — the DSL builds the corpus's canonical
 *    `operation` (the no-drift guard; read-shaped cases only).
 *  - `assertResult(actual, case)` — the returned managed rows / graph / table state /
 *    affected rows equal the corpus, REUSING the Phase 4 comparison rules (exact
 *    decimal, boolean never `== 1`, µs timestamps) — grading is not reinvented.
 *  - `assertManagedShape(row, entity)` — every scalar is its managed carrier
 *    (`instanceof` + value, the 10b contract).
 */

import {
  type ColumnTypes,
  compareGraph,
  compareRowSet,
  compareTableState,
  type Graph,
  type LoadedCase,
  loadCase,
  type TableState,
} from "@parallax/conformance";
import { bytesToHex, ParallaxDecimal, Temporal, timestampToWire } from "@parallax/core";
import type { PostgresDatabase } from "@parallax/db-postgres";
import { ddlForDescriptor } from "@parallax/dialect";
import type { Metamodel } from "@parallax/metamodel";
import { Metamodel as MetamodelReader } from "@parallax/metamodel";
import { canonicallyEqual } from "@parallax/operation";
import { expect } from "vitest";
import type { PostgresProvider } from "../../src/conformance/postgres-provider.js";
import { createParallax, type Parallax, type ParallaxRow } from "../../src/index.js";

/** Resolve a case stem to its repo-relative path. */
export function casePath(stem: string): string {
  return `core/compatibility/cases/${stem}.yaml`;
}

/** Load a corpus case by stem (`0002-eq`). */
export function showcaseCase(stem: string): LoadedCase {
  return loadCase(casePath(stem));
}

/** A per-case fixture: the provisioned DB and the developer `px` handle bound to it. */
export interface CaseFixture {
  /** The loaded corpus case (its operation + expected results). */
  readonly loaded: LoadedCase;
  /** The typed developer handle over the shipped adapter (`px`). */
  readonly px: Parallax;
  /** The bound `@parallax/db-postgres` adapter (the production path). */
  readonly db: PostgresDatabase;
  /** The case's metamodel (for DSL entity symbols + managed-shape assertions). */
  readonly metamodel: Metamodel;
}

/**
 * Provision a case's schema on the shared container (via the Phase 3 provider) and
 * build a `px` handle bound to a `@parallax/db-postgres` instance on that same
 * container. The clock is fixed so audit-write processing instants are
 * deterministic across a run.
 */
export async function provisionCase(
  provider: PostgresProvider,
  stem: string,
  options: { readonly loadFixtures?: boolean; readonly now?: string } = {},
): Promise<CaseFixture> {
  const loaded = showcaseCase(stem);
  await provider.reset();
  await provider.applyDdl(ddlForDescriptor(loaded.descriptor));
  if (options.loadFixtures ?? shouldLoadFixtures(loaded)) {
    await loadCaseFixtures(provider, loaded);
  }
  const db = provider.database;
  const metamodel = MetamodelReader.fromDescriptor(loaded.descriptor);
  const px = createParallax({
    database: db,
    descriptor: loaded.descriptor,
    ...(options.now ? { clock: { now: () => options.now as string } } : {}),
  });
  return { loaded, px, db, metamodel };
}

/**
 * Whether a case loads its model fixtures before running. Read cases and scenarios
 * read fixtures; write-sequence cases construct their own state from an empty
 * table (the corpus authors them self-contained), unless they opt in
 * (`loadFixtures: true`, e.g. `0613`). Conflict cases load fixtures.
 */
function shouldLoadFixtures(loaded: LoadedCase): boolean {
  if (loaded.shape === "writeSequence") {
    return loaded.raw.loadFixtures === true;
  }
  return true;
}

/** Load a case's fixtures through the provider (physical table + columns + rows). */
async function loadCaseFixtures(provider: PostgresProvider, loaded: LoadedCase): Promise<void> {
  const metamodel = MetamodelReader.fromDescriptor(loaded.descriptor);
  for (const entity of metamodel.entities()) {
    const rows = loaded.fixtures[entity.name] ?? [];
    if (rows.length === 0) {
      continue;
    }
    const columns = entity.attributes().map((attr) => attr.column);
    const columnByName = new Map(entity.attributes().map((attr) => [attr.name, attr.column]));
    const bindRows = rows.map((row) =>
      columns.map((column) => {
        // Fixtures are authored by DSL attribute name OR physical column name.
        const attrName = [...columnByName.entries()].find(([, c]) => c === column)?.[0];
        const value = attrName !== undefined && attrName in row ? row[attrName] : row[column];
        return value ?? null;
      }),
    );
    await provider.loadFixtures(entity.table, columns, bindRows);
  }
}

// --- assertions -------------------------------------------------------------

/**
 * Assert the DSL builds the corpus's canonical `operation` (the no-drift guard).
 * A read-shaped showcase snippet that stops matching its canonical case fails here.
 */
export function assertSameOperation(operation: unknown, loaded: LoadedCase): void {
  const corpus = loaded.raw.operation;
  expect(
    canonicallyEqual(operation, corpus),
    `DSL for ${loaded.casePath} did not canonicalize to the corpus operation:\n` +
      `  dsl:    ${JSON.stringify(operation)}\n` +
      `  corpus: ${JSON.stringify(corpus)}`,
  ).toBe(true);
}

/**
 * Assert returned managed rows equal the corpus's `expectedRows` under the Phase 4
 * comparison rules.
 *
 * A developer `find` returns FULL managed objects, but the corpus `expectedRows` is
 * projection-specific — it names only the columns the case asserts (`0002` is
 * `{ id, name }`, `0603` omits `version`). So the observed rows are PROJECTED DOWN
 * to the keys the expected row names before comparison: the developer's extra
 * columns are irrelevant to what the case proves. Managed rows are keyed by DSL
 * name and rendered to the neutral wire form; the corpus rows (keyed by physical
 * column) are translated to DSL names first. When a case authors NO rows (`0221`,
 * `0315`), the observed row set must be empty too (the comparator checks the count).
 */
export function assertRows(
  rows: readonly ParallaxRow[],
  loaded: LoadedCase,
  entityName: string,
  metamodel: Metamodel,
): void {
  const entity = metamodel.entity(entityName);
  const expected = expectedRowsFor(loaded).map((row) => translateToDslNames(row, entity));
  const witnessKeys = expected[0] ? Object.keys(expected[0]) : undefined;
  const observed = rows.map((row) => projectRow(renderManaged(row), witnessKeys));
  const columnTypes = dslColumnTypes(metamodel);
  const comparison = compareRowSet(observed, expected, columnTypes);
  expect(
    comparison.equal,
    `${loaded.casePath}: ${comparison.reason}\n observed=${JSON.stringify(
      observed,
    )}\n expected=${JSON.stringify(expected)}`,
  ).toBe(true);
}

/** Project a wire-rendered row down to the expected witness keys (all keys when none). */
function projectRow(
  row: Record<string, unknown>,
  keys: readonly string[] | undefined,
): Record<string, unknown> {
  if (keys === undefined) {
    return row;
  }
  const out: Record<string, unknown> = {};
  for (const key of keys) {
    out[key] = key in row ? row[key] : null;
  }
  return out;
}

/**
 * Assert an assembled deep-fetch graph matches the corpus `expectedGraph`. A
 * developer `find(..., { includes })` returns FULL managed objects; the corpus
 * `expectedGraph` is a projection-specific witness naming only the columns its
 * golden projects (`0311` root shows `id, name, price`). So the observed graph is
 * PROJECTED DOWN to the keys the expected node names (per node), then compared with
 * the shared graph comparator — the developer's extra columns are irrelevant to the
 * graph shape the case proves (relationship structure + the projected values). The
 * managed graph is keyed by DSL names throughout; the corpus graph is translated to
 * DSL names first.
 */
export function assertGraph(
  rows: readonly ParallaxRow[],
  loaded: LoadedCase,
  rootEntityName: string,
  metamodel: Metamodel,
): void {
  const expectedRaw = (loaded.raw.expectedGraph ?? {}) as Graph;
  const expected = translateGraph(expectedRaw, metamodel);
  const observedFull = rows.map((row) => renderManagedNode(row));
  const expectedRoot = expected[rootEntityName] ?? [];
  const observed: Graph = {
    [rootEntityName]: projectNodesToWitness(observedFull, expectedRoot),
  };
  const columnTypes = dslColumnTypes(metamodel);
  const comparison = compareGraph(observed, expected as Graph, columnTypes);
  expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
}

/**
 * Project a list of observed graph nodes down to the key set the expected witness
 * names, recursively for relationship-valued keys. Uses the FIRST expected node for
 * the key set (the corpus authors a uniform node shape per level), but derives each
 * relationship key's SHAPE witness from the first expected node that populates it —
 * a nullable to-one (`0314`) leaves it `null` on some rows, so the first node's
 * shape for that key can be `null`; the full expected list carries the populated
 * shape elsewhere. When a level is empty in the expected graph, the observed list
 * must be empty too, so nothing is projected.
 */
function projectNodesToWitness(
  observed: readonly Record<string, unknown>[],
  expected: readonly Record<string, unknown>[],
): readonly Record<string, unknown>[] {
  const witness = expected[0];
  if (witness === undefined) {
    return observed; // empty expected level → the comparator asserts observed is empty too
  }
  const keys = Object.keys(witness);
  return observed.map((node) => projectNodeToWitness(node, keys, expected));
}

/**
 * Project one observed node to the given keys, recursing into relationships. The
 * child shape for a relationship key is taken from the first SIBLING expected node
 * that populates it (a nullable to-one is `null` on some rows), so a populated
 * observed relationship is still projected to the witness column set.
 */
function projectNodeToWitness(
  node: Record<string, unknown>,
  keys: readonly string[],
  siblings: readonly Record<string, unknown>[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of keys) {
    const value = node[key];
    const witnessValue = firstPopulated(siblings, key);
    if (Array.isArray(value) && Array.isArray(witnessValue)) {
      out[key] = projectNodesToWitness(
        value as Record<string, unknown>[],
        witnessValue as Record<string, unknown>[],
      );
    } else if (
      value !== null &&
      typeof value === "object" &&
      witnessValue !== null &&
      typeof witnessValue === "object"
    ) {
      const childKeys = Object.keys(witnessValue as Record<string, unknown>);
      out[key] = projectNodeToWitness(value as Record<string, unknown>, childKeys, [
        witnessValue as Record<string, unknown>,
      ]);
    } else {
      out[key] = value ?? null;
    }
  }
  return out;
}

/** The first non-null value a relationship/scalar key takes across sibling witness nodes. */
function firstPopulated(siblings: readonly Record<string, unknown>[], key: string): unknown {
  for (const sibling of siblings) {
    const value = sibling[key];
    if (value !== null && value !== undefined) {
      return value;
    }
  }
  return siblings[0]?.[key] ?? null;
}

/**
 * Assert the resulting table state equals the corpus `expectedTableState` (write
 * sequences / conflicts). The table state is read straight off the physical tables
 * through the shipped adapter and rendered to wire form; the corpus state is keyed
 * by physical column, so no name translation is needed — but the OBSERVED managed
 * values are rendered to wire form for the shared comparator.
 */
export async function assertTableState(
  db: PostgresDatabase,
  loaded: LoadedCase,
  metamodel: Metamodel,
): Promise<void> {
  const expected = (loaded.raw.expectedTableState ?? {}) as TableState;
  const observed = await readTableState(db, expected, metamodel);
  const columnTypes = physicalColumnTypes(metamodel);
  const comparison = compareTableState(observed, expected, columnTypes);
  expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
}

/**
 * Assert every scalar of a returned row is its MANAGED carrier (the 10b contract),
 * by `instanceof` / `typeof` per the entity's M0 types (null passes for a nullable
 * column). This is what the grader deliberately does NOT check (it grades wire
 * values); the showcase proves the developer receives managed objects.
 */
export function assertManagedShape(
  row: ParallaxRow,
  entityName: string,
  metamodel: Metamodel,
): void {
  const entity = metamodel.entity(entityName);
  for (const attr of entity.attributes()) {
    const value = row[attr.name];
    // The physical column name must be gone — the row is keyed by DSL name (10b).
    if (attr.column !== attr.name) {
      expect(attr.column in row, `${entityName}: physical column '${attr.column}' leaked`).toBe(
        false,
      );
    }
    if (value === null || value === undefined) {
      continue;
    }
    assertScalarManaged(value, attr.type, `${entityName}.${attr.name}`);
  }
}

/** Assert one scalar is its managed carrier for its M0 type. */
function assertScalarManaged(value: unknown, type: string, label: string): void {
  if (/^decimal\(\d+,\d+\)$/.test(type)) {
    expect(value instanceof ParallaxDecimal, `${label}: expected ParallaxDecimal`).toBe(true);
    return;
  }
  switch (type) {
    case "int64":
      expect(typeof value, `${label}: expected bigint`).toBe("bigint");
      return;
    case "int32":
    case "float32":
    case "float64":
      expect(typeof value, `${label}: expected number`).toBe("number");
      return;
    case "boolean":
      expect(typeof value, `${label}: expected boolean`).toBe("boolean");
      return;
    case "string":
    case "uuid":
      expect(typeof value, `${label}: expected string`).toBe("string");
      return;
    case "bytes":
      expect(value instanceof Uint8Array, `${label}: expected Uint8Array`).toBe(true);
      return;
    case "date":
      expect(value instanceof Temporal.PlainDate, `${label}: expected Temporal.PlainDate`).toBe(
        true,
      );
      return;
    case "time":
      expect(value instanceof Temporal.PlainTime, `${label}: expected Temporal.PlainTime`).toBe(
        true,
      );
      return;
    case "timestamp":
      // The `infinity` sentinel stays a string; a real instant is a Temporal.Instant.
      if (value === "infinity") {
        return;
      }
      expect(value instanceof Temporal.Instant, `${label}: expected Temporal.Instant`).toBe(true);
      return;
    default:
      // json / other: no carrier assertion beyond non-null.
      return;
  }
}

// --- wire rendering + name translation --------------------------------------

/** The corpus `expectedRows`, or a scenario's terminal `expectRows`. */
function expectedRowsFor(loaded: LoadedCase): readonly Record<string, unknown>[] {
  if (loaded.shape === "scenario") {
    const steps = (loaded.raw.scenario as { expectRows?: Record<string, unknown>[] }[]) ?? [];
    for (let i = steps.length - 1; i >= 0; i -= 1) {
      const rows = steps[i]?.expectRows;
      if (rows !== undefined) {
        return rows;
      }
    }
    return [];
  }
  return (loaded.raw.expectedRows as Record<string, unknown>[] | undefined) ?? [];
}

/** Render a managed row to the neutral wire form keyed by its (DSL) name. */
function renderManaged(row: ParallaxRow): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(row)) {
    out[key] = renderScalar(value);
  }
  return out;
}

/** Render a managed graph node (scalars to wire; relationships recurse). */
function renderManagedNode(row: ParallaxRow): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(row)) {
    if (Array.isArray(value)) {
      out[key] = value.map((child) => renderManagedNode(child as ParallaxRow));
    } else if (value !== null && typeof value === "object" && !isManagedScalar(value)) {
      out[key] = renderManagedNode(value as ParallaxRow);
    } else {
      out[key] = renderScalar(value);
    }
  }
  return out;
}

/** True for a managed scalar carrier (so a graph walk does not recurse into it). */
function isManagedScalar(value: object): boolean {
  return (
    value instanceof ParallaxDecimal ||
    value instanceof Temporal.Instant ||
    value instanceof Temporal.PlainDate ||
    value instanceof Temporal.PlainTime ||
    value instanceof Uint8Array
  );
}

/**
 * Render one managed scalar to its neutral wire form (the grading domain) — the
 * SAME renderer the run envelope uses, so a `Temporal.Instant` renders to the
 * corpus `+00:00` µs form (not the JS `Z` form), a `ParallaxDecimal` to its
 * scale-aware string, a `bigint` to base-10, a `Uint8Array` to lowercase hex.
 */
function renderScalar(value: unknown): unknown {
  if (value === null || value === undefined) {
    return value;
  }
  if (typeof value === "bigint") {
    return value.toString();
  }
  if (value instanceof ParallaxDecimal) {
    return value.toString();
  }
  if (value instanceof Temporal.Instant) {
    return timestampToWire(value);
  }
  if (value instanceof Temporal.PlainDate || value instanceof Temporal.PlainTime) {
    return value.toString();
  }
  if (value instanceof Uint8Array) {
    return bytesToHex(value);
  }
  return value;
}

/** Translate a corpus row keyed by physical column to DSL attribute names. */
function translateToDslNames(
  row: Record<string, unknown>,
  entity: { attributes(): readonly { name: string; column: string; type: string }[] },
): Record<string, unknown> {
  const nameByColumn = new Map(entity.attributes().map((attr) => [attr.column, attr.name]));
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(row)) {
    // A corpus key may be a physical column, a DSL name (fixtures), or the `_hex`
    // computed output the `bytes` scalar projects (`0003`: `payload_hex` names the
    // `payload` bytes attribute the developer receives as a `Uint8Array` → hex).
    const direct = nameByColumn.get(key);
    if (direct !== undefined) {
      out[direct] = value;
      continue;
    }
    if (key.endsWith("_hex")) {
      const physical = key.slice(0, -"_hex".length);
      const bytesAttr = entity
        .attributes()
        .find((attr) => attr.column === physical && attr.type === "bytes");
      if (bytesAttr !== undefined) {
        out[bytesAttr.name] = value;
        continue;
      }
    }
    out[key] = value;
  }
  return out;
}

/** Translate a corpus graph keyed by physical columns / relationship names to DSL names. */
function translateGraph(graph: Graph, metamodel: Metamodel): Graph {
  const out: Record<string, readonly Record<string, unknown>[]> = {};
  for (const [rootEntity, rows] of Object.entries(graph)) {
    out[rootEntity] = rows.map((row) => translateGraphNode(row, rootEntity, metamodel));
  }
  return out;
}

/** Translate one graph node's columns + relationship keys to DSL names, recursively. */
function translateGraphNode(
  node: Record<string, unknown>,
  entityName: string,
  metamodel: Metamodel,
): Record<string, unknown> {
  const entity = metamodel.entity(entityName);
  const nameByColumn = new Map(entity.attributes().map((attr) => [attr.column, attr.name]));
  const relByName = new Map(entity.relationships().map((rel) => [rel.name, rel]));
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(node)) {
    const rel = relByName.get(key);
    if (rel !== undefined) {
      if (Array.isArray(value)) {
        out[key] = value.map((child) =>
          translateGraphNode(child as Record<string, unknown>, rel.relatedEntity, metamodel),
        );
      } else if (value !== null && typeof value === "object") {
        out[key] = translateGraphNode(
          value as Record<string, unknown>,
          rel.relatedEntity,
          metamodel,
        );
      } else {
        out[key] = value;
      }
      continue;
    }
    out[nameByColumn.get(key) ?? key] = value;
  }
  return out;
}

/** A `DSL name -> M0 type` map merged across all entities (for row/graph grading). */
function dslColumnTypes(metamodel: Metamodel): ColumnTypes {
  const types: Record<string, string> = {};
  for (const entity of metamodel.entities()) {
    for (const attr of entity.attributes()) {
      types[attr.name] = attr.type;
    }
  }
  return types;
}

/** A `physical column -> M0 type` map merged across all entities (for table state). */
function physicalColumnTypes(metamodel: Metamodel): ColumnTypes {
  const types: Record<string, string> = {};
  for (const entity of metamodel.entities()) {
    for (const attr of entity.attributes()) {
      types[attr.column] = attr.type;
    }
  }
  return types;
}

/** Read the expected tables' full state off the physical tables (wire-rendered). */
async function readTableState(
  db: PostgresDatabase,
  expected: TableState,
  metamodel: Metamodel,
): Promise<TableState> {
  const tableToEntity = new Map(metamodel.entities().map((e) => [e.table, e]));
  const out: Record<string, readonly Record<string, unknown>[]> = {};
  for (const table of Object.keys(expected)) {
    const entity = tableToEntity.get(table);
    const columns = entity
      ? entity.attributes().map((attr) => attr.column)
      : Object.keys(expected[table]?.[0] ?? {});
    const quoted = columns.map((c) => `"${c}"`).join(", ");
    const rows = await db.execute(`select ${quoted} from "${table}"`, []);
    out[table] = rows.map((row) => renderManaged(row));
  }
  return out;
}
