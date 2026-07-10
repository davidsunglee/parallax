/**
 * The developer-runtime **deep-fetch executor** (spec §2.6), at the composition
 * root over the injected `ParallaxDatabase`.
 *
 * A typed `find(predicate, { includes: [...] })` compiles to a `{ deepFetch: {
 * operand, paths } }` operation. The m-sql compiler lowers only the ROOT statement of
 * a deep fetch; the eager multi-level assembly is orchestration owned by
 * `@parallax/relationships` (`deepFetch`, one bulk `IN` query per level, `1 + L`
 * round trips, never N+1). This module wires that pure strategy to the *developer*
 * runtime: it builds the relationship-hop tree from the METAMODEL (full child
 * projections — a developer read returns whole managed objects, not a case's
 * `expectedGraph` witness), runs the strategy through the port, and materializes
 * every level's rows to **managed objects keyed by DSL name** (10b), attaching each
 * relationship under its DSL relationship name.
 *
 * It reuses the SAME m-sql `compile` visitor (through a child-rooted `RuntimeSchema`)
 * and the SAME as-of propagation the conformance path uses, so a temporal deep
 * fetch propagates the root's pins per hop identically — the developer surface and
 * the graded runtime never diverge.
 */

import type { ParallaxDatabase, ParallaxRow } from "@parallax/db";
import type { Dialect } from "@parallax/dialect";
import type { EntityMetadata, Metamodel } from "@parallax/metamodel";
import type { Operation, PathSegment } from "@parallax/operation";
import {
  type DeepFetchNode,
  type Key,
  type LevelQuery,
  type Row,
  deepFetch as runDeepFetch,
} from "@parallax/relationships";
import { type AxisPins, compile } from "@parallax/sql";
import { rowMaterializer } from "./materialize.js";
import { executeRead } from "./read.js";
import { RuntimeSchema } from "./schema.js";
import type { Concurrency } from "./writes.js";

/** The assembled deep-fetch result for the developer runtime. */
export interface DeepFetchGraph {
  /** The decorated root rows (managed objects keyed by DSL name, relationships attached). */
  readonly rows: readonly ParallaxRow[];
  /** The total statements issued: `1` (root) + one per non-elided level. */
  readonly roundTrips: number;
}

/** The `{ operand, paths }` body of a deep-fetch operation (segments are `{ rel }` objects). */
interface DeepFetchBody {
  readonly operand: Operation;
  readonly paths: readonly (readonly PathSegment[])[];
}

/**
 * The in-transaction read context threaded into a deep fetch, so EVERY fetched
 * level — the root AND each included child — participates in the unit of work
 * exactly like a flat read does (spec §3, m-unit-work/m-opt-lock): a `locking`-mode read takes the
 * shared row lock, and the materialized rows record the versions the unit of work
 * observed. The default (an out-of-transaction read, or a root-handle read) takes
 * no lock and records nothing.
 */
export interface DeepFetchReadContext {
  /**
   * The m-unit-work correctness mode of the enclosing unit of work, passed to the shared
   * read executor for every fetched level (the root read AND each child-level
   * `in`-membership read): a `locking`-mode read takes the shared lock, so a
   * concurrent writer cannot mutate an included row out from under a later
   * read-then-write. Absent on a root-handle / out-of-transaction read (no lock).
   */
  readonly concurrency: Concurrency | undefined;
  /**
   * Record the versions the materialized rows of a fetched level observed (the m-opt-lock
   * observed-version map), identified by that level's entity. Called once per
   * fetched entity (root + each included level); a non-versioned entity records
   * nothing. Absent on a root-handle / out-of-transaction read.
   */
  readonly onObserved: ((entity: EntityMetadata, rows: readonly ParallaxRow[]) => void) | undefined;
}

/** The default read context: no lock, no observed-version recording (out-of-transaction reads). */
const NO_READ_CONTEXT: DeepFetchReadContext = { concurrency: undefined, onObserved: undefined };

/** True when an operation is a deep fetch (`{ deepFetch: { operand, paths } }`). */
export function isDeepFetchOperation(operation: Operation): boolean {
  return typeof operation === "object" && operation !== null && "deepFetch" in operation;
}

/**
 * Execute a developer-runtime deep fetch: compile the root, run the m-deep-fetch strategy
 * over the metamodel-derived hop tree, and return the decorated managed root rows
 * plus the `1 + L` round-trip count.
 */
export async function executeDeepFetch(
  metamodel: Metamodel,
  operation: Operation,
  database: ParallaxDatabase,
  dialect: Dialect,
  readContext: DeepFetchReadContext = NO_READ_CONTEXT,
): Promise<DeepFetchGraph> {
  const body = (operation as { deepFetch: DeepFetchBody }).deepFetch;
  const rootEntity = deepFetchRootEntity(metamodel, body.paths, body.operand);
  const rootSchema = new RuntimeSchema(metamodel, rootEntity, dialect);
  // The ROOT read AND each CHILD level are compiled against the injected dialect with
  // the unit of work's `locking` mode, so `compile()` applies the m-read-lock shared read-lock
  // in-line (`for share of t0` in `locking`, `m-read-lock-001`) — the developer writes no lock
  // SQL — and child locking falls out structurally rather than being re-plumbed.
  const locking = readContext.concurrency === "locking";
  const { sql, binds } = compile(body.operand, rootSchema, dialect, { locking });
  const rootPins = collectRootPins(rootSchema, body.operand);

  const rootRows = [...(await executeRead(database, sql, binds as readonly unknown[]))] as Row[];
  const tree = buildTree(metamodel, body.paths, rootPins, dialect, locking);
  const result = await runDeepFetch(rootRows, tree, (levelSql, levelBinds) =>
    executeRead(database, levelSql, levelBinds).then((rows) => [...rows] as Row[]),
  );

  // Materialize the assembled graph to managed objects keyed by DSL name (10b),
  // recursing into the attached relationship arrays / to-one peers, and collect the
  // materialized rows of EVERY fetched level grouped by entity (root + each included
  // child) so the unit of work records the version each level observed (m-opt-lock).
  const observedLevels = new Map<string, ObservedLevel>();
  const materialized = result.rows.map((row) =>
    materializeNode(row, rootEntity, metamodel, observedLevels, dialect),
  );
  // Record the version this unit of work OBSERVED for each fetched versioned row, so
  // a later keyed update of the versioned root OR of an included versioned child gates
  // on / advances from it (m-opt-lock) and does not spuriously raise ParallaxReadBeforeWriteError
  // — every deep-fetch level participates in the read contract exactly like a flat read
  // (the m-unit-work lock above, the m-opt-lock observed-version recording here). A non-versioned level's
  // rows are handed over too; the recorder no-ops for an entity with no version column.
  if (readContext.onObserved) {
    for (const level of observedLevels.values()) {
      readContext.onObserved(level.entity, level.rows);
    }
  }
  return { rows: materialized, roundTrips: result.roundTrips };
}

/** The materialized rows of one fetched level, grouped by entity for observed-version recording. */
interface ObservedLevel {
  readonly entity: EntityMetadata;
  readonly rows: ParallaxRow[];
}

/**
 * Materialize one graph node to a managed object keyed by DSL name, then recurse
 * into any attached relationship values (arrays for to-many, an object / `null`
 * for to-one). A relationship key is renamed to its DSL name (it already IS the
 * DSL relationship name, since the tree decorates by `node.name`).
 *
 * Each materialized row is also accumulated into `observed` under its entity, so
 * the caller can record the version every fetched level observed (m-opt-lock) — not only
 * the root's.
 */
function materializeNode(
  row: Row,
  entity: EntityMetadata,
  metamodel: Metamodel,
  observed: Map<string, ObservedLevel>,
  dialect: Dialect,
): ParallaxRow {
  const scalar = rowMaterializer(entity, dialect)(scalarColumns(row, entity));
  recordObservedRow(observed, entity, scalar);
  for (const rel of entity.relationships()) {
    if (!(rel.name in row)) {
      continue;
    }
    const child = metamodel.entity(rel.relatedEntity);
    const value = row[rel.name];
    if (Array.isArray(value)) {
      scalar[rel.name] = value.map((c) =>
        materializeNode(c as Row, child, metamodel, observed, dialect),
      );
    } else if (value && typeof value === "object") {
      scalar[rel.name] = materializeNode(value as Row, child, metamodel, observed, dialect);
    } else {
      scalar[rel.name] = value ?? null;
    }
  }
  return scalar;
}

/** Accumulate one materialized row under its entity for later observed-version recording. */
function recordObservedRow(
  observed: Map<string, ObservedLevel>,
  entity: EntityMetadata,
  row: ParallaxRow,
): void {
  const level = observed.get(entity.name);
  if (level) {
    level.rows.push(row);
  } else {
    observed.set(entity.name, { entity, rows: [row] });
  }
}

/** The physical scalar columns of a decorated row (relationship keys stripped). */
function scalarColumns(row: Row, entity: EntityMetadata): ParallaxRow {
  const out: ParallaxRow = {};
  for (const attr of entity.attributes()) {
    out[attr.column] = row[attr.column];
  }
  return out;
}

/**
 * The root entity of a deep fetch: the class named by the first hop of the first
 * path (`OrderItem` in `[OrderItem.order]`) — every path roots at the same class.
 * Falls back to the operand's first class ref for a pathless deep fetch.
 */
function deepFetchRootEntity(
  metamodel: Metamodel,
  paths: readonly (readonly PathSegment[])[],
  operand: Operation,
): EntityMetadata {
  const firstRef = paths[0]?.[0]?.rel;
  if (firstRef !== undefined) {
    return metamodel.entity(firstRef.slice(0, firstRef.indexOf(".")));
  }
  const classRef = firstClassRef(operand);
  if (classRef) {
    return metamodel.entity(classRef);
  }
  const first = metamodel.entities()[0];
  if (first === undefined) {
    throw new Error("deep-fetch operand references no entity and the model declares none");
  }
  return first;
}

/** Collect the root's `asOf` pins (business/processing) for per-hop propagation. */
function collectRootPins(schema: RuntimeSchema, operand: Operation): AxisPins {
  const pins: AxisPins = {};
  let node: unknown = peelDirectives(operand);
  while (node !== null && typeof node === "object" && "asOf" in (node as object)) {
    const asOf = (node as { asOf: { operand: unknown; asOfAttr: string; date: string } }).asOf;
    const axis = schema.resolveAsOfAxis(asOf.asOfAttr);
    pins[axis] = asOf.date === "now" ? { kind: "now" } : { kind: "instant", date: asOf.date };
    node = asOf.operand;
  }
  return pins;
}

/** Descend past `distinct` / `orderBy` / `limit` wrappers (mirrors the root compile). */
function peelDirectives(node: unknown): unknown {
  let current = node;
  while (current !== null && typeof current === "object") {
    if ("distinct" in current) {
      current = (current as { distinct: { operand: unknown } }).distinct.operand;
    } else if ("orderBy" in current) {
      current = (current as { orderBy: { operand: unknown } }).orderBy.operand;
    } else if ("limit" in current) {
      current = (current as { limit: { operand: unknown } }).limit.operand;
    } else {
      break;
    }
  }
  return current;
}

/** Build the de-duplicated relationship-hop tree from the navigation paths. */
function buildTree(
  metamodel: Metamodel,
  paths: readonly (readonly PathSegment[])[],
  rootPins: AxisPins,
  dialect: Dialect,
  locking: boolean,
): readonly DeepFetchNode[] {
  const roots: NodeBuilder[] = [];
  for (const path of paths) {
    let siblings = roots;
    for (const segment of path) {
      const relRef = segment.rel;
      let node = siblings.find((n) => n.relRef === relRef);
      if (!node) {
        node = { relRef, children: [] };
        siblings.push(node);
      }
      siblings = node.children;
    }
  }
  return roots.map((node) => materialize(metamodel, node, rootPins, dialect, locking));
}

/** A mutable tree node accumulated while merging shared path prefixes. */
interface NodeBuilder {
  readonly relRef: string;
  readonly children: NodeBuilder[];
}

/**
 * Materialize a `NodeBuilder` into a `DeepFetchNode`: resolve the relationship's
 * correlation + cardinality from the metamodel, project the FULL child attribute
 * set, and bind a `compileLevel` closure that compiles `… where <childCol> in (?,
 * …) [order by …]` for a key set, seeding the root pins for temporal propagation.
 *
 * The level statement is compiled against the injected dialect with the unit of
 * work's `locking` mode, so `compile()` applies the m-read-lock shared lock in-line for a
 * `locking` deep-fetch level exactly as it does for the root and a flat read.
 */
function materialize(
  metamodel: Metamodel,
  builder: NodeBuilder,
  rootPins: AxisPins,
  dialect: Dialect,
  locking: boolean,
): DeepFetchNode {
  const [className, relName] = splitRef(builder.relRef);
  const sourceEntity = metamodel.entity(className);
  const relationship = sourceEntity.relationshipByName(relName);
  const relatedEntity = metamodel.entity(relationship.relatedEntity);
  const { thisAttr, relatedAttr } = parseJoin(relationship.join);
  const parentColumn = sourceEntity.attributeByName(thisAttr).column;
  const childColumn = relatedEntity.attributeByName(relatedAttr).column;
  const toOne =
    relationship.cardinality === "many-to-one" || relationship.cardinality === "one-to-one";

  const compileLevel = (keys: readonly Key[]): LevelQuery => {
    const childSchema = new RuntimeSchema(metamodel, relatedEntity, dialect);
    const levelOp = childLevelOperation(relatedEntity, relatedAttr, keys, relationship);
    const compiled = compile(levelOp, childSchema, dialect, { locking, seedPins: rootPins });
    return { sql: compiled.sql, binds: compiled.binds as readonly unknown[] };
  };

  return {
    name: relName,
    toOne,
    parentColumn,
    childColumn,
    compileLevel,
    children: builder.children.map((child) =>
      materialize(metamodel, child, rootPins, dialect, locking),
    ),
  };
}

/**
 * The child-level operation: an `in` membership on the child correlation
 * attribute, wrapped in the relationship's declared `orderBy` (lowered onto the
 * child entity). Full attribute projection is supplied by the child `RuntimeSchema`.
 */
function childLevelOperation(
  childEntity: EntityMetadata,
  relatedAttr: string,
  keys: readonly Key[],
  relationship: {
    readonly orderBy: readonly { readonly attr: string; readonly direction?: "asc" | "desc" }[];
  },
): Operation {
  const membership: Operation = {
    in: { attr: `${childEntity.name}.${relatedAttr}`, values: keys.map(toLiteral) },
  } as Operation;
  if (relationship.orderBy.length === 0) {
    return membership;
  }
  return {
    orderBy: {
      operand: membership,
      keys: relationship.orderBy.map((key) => ({
        attr: `${childEntity.name}.${key.attr}`,
        direction: key.direction ?? "asc",
      })),
    },
  } as Operation;
}

/** Coerce a correlation key into an operation literal (bigint → base-10 string). */
function toLiteral(key: Key): string | number {
  return typeof key === "bigint" ? key.toString() : (key as string | number);
}

/** The class name of the first `Class.attr` reference reachable in an operation. */
function firstClassRef(node: unknown): string | undefined {
  if (node === null || typeof node !== "object") {
    return undefined;
  }
  for (const value of Object.values(node as Record<string, unknown>)) {
    if (typeof value === "string" && /^[A-Z][A-Za-z0-9]*\.[A-Za-z]/.test(value)) {
      return value.slice(0, value.indexOf("."));
    }
    const nested = firstClassRef(value);
    if (nested) {
      return nested;
    }
  }
  return undefined;
}

/** Split a `Class.member` reference into its parts. */
function splitRef(ref: string): [string, string] {
  const dot = ref.indexOf(".");
  if (dot === -1) {
    throw new Error(`malformed reference '${ref}' (expected 'Class.member')`);
  }
  return [ref.slice(0, dot), ref.slice(dot + 1)];
}

/** Parse a canonical relationship `join` into its two attribute names. */
function parseJoin(join: string): { thisAttr: string; relatedAttr: string } {
  const match = /^\s*this\.(\w+)\s*=\s*\w+\.(\w+)\s*$/.exec(join);
  if (!match) {
    throw new Error(`unsupported relationship join '${join}'`);
  }
  return { thisAttr: match[1] as string, relatedAttr: match[2] as string };
}
