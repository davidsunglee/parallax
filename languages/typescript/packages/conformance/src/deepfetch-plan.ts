/**
 * Build an executable **deep-fetch plan** from a loaded case (M4 + M12).
 *
 * A deep-fetch operation is `{ deepFetch: { operand, paths } }`: a root predicate
 * plus a set of navigation paths. This module turns it into the inputs the pure
 * `@parallax/relationships` deep-fetch strategy needs:
 *
 *  - the **root** statement (the `operand` compiled with the deep-fetch root
 *    projection), and
 *  - a tree of `DeepFetchNode`s — one per *distinct* relationship hop across all
 *    paths (shared prefixes merged, so `[items]` and `[items, statuses]` share a
 *    single `items` node) — each carrying its correlation columns, cardinality,
 *    and a `compileLevel(keys)` closure that compiles `… where <childCol> in (?,
 *    …) [order by …]` for a set of distinct parent keys.
 *
 * Compiling every level reuses the M3 `compile` visitor (via a child-rooted
 * `MetamodelSchema`), so the canonical-by-construction guarantees (alias `t0`,
 * quoted columns, the relationship's `orderBy`) hold uniformly for child levels.
 * The projection each level emits is derived from the case's `expectedGraph`
 * witness (the object shape the corpus authored), matching the golden by
 * construction; an empty level with no witness falls back to the child entity's
 * non-nullable columns plus any nullable `orderBy` keys (the documented
 * empty-intermediate path, exercised only by `0318`).
 */
import { type Operation, parseOperation } from "@parallax/operation";
import type { DeepFetchNode, Key, LevelQuery } from "@parallax/relationships";
import { type AxisPins, type Bind, compile } from "@parallax/sql";
import type { LoadedCase } from "./discover.js";
import {
  childProjection,
  type MetamodelSchema,
  rootDeepFetchProjection,
  schemaForEntity,
  schemaForRoot,
} from "./schema-resolver.js";

/** The compiled root statement plus the relationship-hop tree. */
export interface DeepFetchPlan {
  /** The root entity's domain class name (the `expectedGraph` key). */
  readonly rootEntity: string;
  /** The root level: its SQL, its binds, and the root projection columns. */
  readonly root: LevelQuery;
  /** The de-duplicated relationship-hop tree (shared prefixes merged). */
  readonly tree: readonly DeepFetchNode[];
}

/** A deep-fetch operation body. */
interface DeepFetchBody {
  readonly operand: Operation;
  readonly paths: readonly (readonly string[])[];
}

/** True when a case's operation is a deep fetch. */
export function isDeepFetch(rawOperation: unknown): boolean {
  return typeof rawOperation === "object" && rawOperation !== null && "deepFetch" in rawOperation;
}

/** Extract the `{ operand, paths }` body of a deep-fetch operation. */
function deepFetchBody(rawOperation: unknown): DeepFetchBody {
  const body = (rawOperation as { deepFetch: DeepFetchBody }).deepFetch;
  return { operand: body.operand, paths: body.paths };
}

/**
 * Build the executable plan: compile the root from the operand (deep-fetch root
 * projection), then build the de-duplicated relationship tree from the paths.
 *
 * The root ENTITY is the class named by the first hop of the first path
 * (`OrderItem` in `[OrderItem.order]`) — NOT the operand's first `Class.attr`
 * reference. A deep fetch whose operand is `all: {}` (no class ref) carries the
 * root class only in its paths, and the root may not be the model's first entity
 * (`0310`/`0314` root at `OrderItem`, not `Order`), so rooting the schema at the
 * path class is what makes the root SELECT hit the right table.
 */
export function buildDeepFetchPlan(loaded: LoadedCase): DeepFetchPlan {
  const body = deepFetchBody(loaded.raw.operation);
  const operand = parseOperation(body.operand);
  const rootEntity = deepFetchRootEntity(body.paths);
  const projection = rootDeepFetchProjection(loaded, body.paths);
  const rootSchema =
    rootEntity === undefined
      ? schemaForRoot(loaded, operand, projection)
      : schemaForEntity(loaded, rootEntity, projection);
  // The root statement compiles the (possibly temporal) operand directly — the M3
  // visitor injects the root's own as-of predicate. The pins collected off the
  // operand also PROPAGATE per-hop into every temporal child level (M4 as-of
  // propagation), so gather them once here and seed each level's compile.
  const compiled = compile(operand, rootSchema);
  const rootPins = collectRootPins(rootSchema, operand);
  const tree = buildTree(loaded, body.paths, rootPins);
  return {
    rootEntity: rootSchema.rootEntityName(),
    root: { sql: compiled.sql, binds: compiled.binds as readonly unknown[] },
    tree,
  };
}

/**
 * Collect the deep-fetch root's as-of pins from the nested `asOf` wrappers of its
 * operand, keyed by axis (via the resolver). `asOfRange` / `history` roots are not
 * part of the propagation oracle — deep fetch propagates only `asOf` pins — so
 * only `asOf` nodes are gathered; an unpinned axis defaults to `now` at the child.
 *
 * The result directives (`distinct` / `orderBy` / `limit`) are peeled FIRST — the
 * root `compile()` peels them before the temporal wrappers, so a directive-wrapped
 * temporal root (`limit(orderBy(asOf(…)))`, case `0336`) still seeds the child
 * propagation pins from the authored instant rather than silently defaulting the
 * child to `now`.
 */
function collectRootPins(schema: MetamodelSchema, operand: Operation): AxisPins {
  const pins: AxisPins = {};
  let node: unknown = peelDirectiveWrappers(operand);
  while (node !== null && typeof node === "object" && "asOf" in (node as object)) {
    const asOf = (node as { asOf: { operand: unknown; asOfAttr: string; date: string } }).asOf;
    const axis = schema.resolveAsOfAxis(asOf.asOfAttr);
    pins[axis] = asOf.date === "now" ? { kind: "now" } : { kind: "instant", date: asOf.date };
    node = asOf.operand;
  }
  return pins;
}

/**
 * Descend past the result-directive wrappers (`distinct` / `orderBy` / `limit`) the
 * root `compile()` peels before the temporal wrappers, returning the innermost node
 * (the temporal wrappers, or the base predicate). Mirrors `peelDirectives` in
 * `@parallax/sql` so pin collection sees the same `asOf` nodes the root compile does.
 */
function peelDirectiveWrappers(node: unknown): unknown {
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

/**
 * The root entity class of a deep fetch: the class part of the first hop of the
 * first path (`OrderItem` from `[OrderItem.order]`). Every path roots at the same
 * class (they all navigate off the same root row set), so the first is
 * authoritative. Returns `undefined` only for a pathless deep fetch (none in the
 * corpus), which falls back to operand-ref resolution.
 */
function deepFetchRootEntity(paths: readonly (readonly string[])[]): string | undefined {
  const firstRef = paths[0]?.[0];
  if (firstRef === undefined) {
    return undefined;
  }
  const [className] = splitRelRef(firstRef);
  return className;
}

/**
 * Build the de-duplicated relationship-hop tree. Each path is a sequence of
 * `Class.rel` refs; a shared prefix is merged so the hop is one node (one level,
 * one statement). Each hop names its source class in the `Class.rel` ref itself,
 * so the correlation is resolved from the ref (no parent-entity threading needed).
 */
function buildTree(
  loaded: LoadedCase,
  paths: readonly (readonly string[])[],
  rootPins: AxisPins,
): readonly DeepFetchNode[] {
  const roots: NodeBuilder[] = [];
  for (const path of paths) {
    let siblings = roots;
    for (const relRef of path) {
      let node = siblings.find((n) => n.relRef === relRef);
      if (!node) {
        node = { relRef, children: [] };
        siblings.push(node);
      }
      siblings = node.children;
    }
  }
  return roots.map((node) => materialize(loaded, node, rootPins));
}

/** A mutable tree node accumulated while merging shared path prefixes. */
interface NodeBuilder {
  readonly relRef: string;
  readonly children: NodeBuilder[];
}

/**
 * Materialize a `NodeBuilder` into a `DeepFetchNode`: resolve the relationship's
 * correlation + cardinality, derive the child projection, and bind a
 * `compileLevel` closure that compiles the child IN-list query for a key set. The
 * child level is compiled with the root pins SEEDED, so a temporal child level
 * carries the propagated as-of predicate (matched by axis, defaulted to `now`)
 * appended after its IN list — the M4 as-of-propagation rule.
 */
function materialize(loaded: LoadedCase, builder: NodeBuilder, rootPins: AxisPins): DeepFetchNode {
  const [, relName] = splitRelRef(builder.relRef);
  const schema = schemaForRoot(loaded, parseOperation({ all: {} }), []);
  const correlation = schema.correlation(builder.relRef);
  const childEntity = correlation.relatedEntity.name;
  const childAttr = childAttrName(correlation.relatedEntity, correlation.childColumn);
  const projection = childProjection(loaded, builder, correlation.relatedEntity);
  const toOne =
    correlation.relationship.cardinality === "many-to-one" ||
    correlation.relationship.cardinality === "one-to-one";

  const compileLevel = (keys: readonly Key[]): LevelQuery => {
    const childSchema = schemaForEntity(loaded, childEntity, projection);
    const levelOp = childLevelOperation(childEntity, childAttr, keys, correlation.relationship);
    const compiled = compile(levelOp, childSchema, rootPins);
    return { sql: compiled.sql, binds: compiled.binds as readonly unknown[] };
  };

  return {
    name: relName,
    toOne,
    parentColumn: correlation.parentColumn,
    childColumn: correlation.childColumn,
    compileLevel,
    children: builder.children.map((child) => materialize(loaded, child, rootPins)),
  };
}

/**
 * The child-level operation: an `in` membership on the child correlation
 * attribute, wrapped in the relationship's declared `orderBy` (lowered onto the
 * child entity). The `in` values are the distinct parent keys; the compiler emits
 * `… where <childCol> in (?, …) [order by …]`.
 */
function childLevelOperation(
  childEntity: string,
  childAttr: string,
  keys: readonly Key[],
  relationship: { readonly orderBy: readonly { attr: string; direction: "asc" | "desc" }[] },
): Operation {
  const membership: Operation = {
    in: { attr: `${childEntity}.${childAttr}`, values: keys.map(toLiteral) },
  } as Operation;
  if (relationship.orderBy.length === 0) {
    return membership;
  }
  return {
    orderBy: {
      operand: membership,
      keys: relationship.orderBy.map((key) => ({
        attr: `${childEntity}.${key.attr}`,
        direction: key.direction,
      })),
    },
  } as Operation;
}

/** Coerce a correlation key into an operation literal (bigint → base-10 string). */
function toLiteral(key: Key): Bind {
  return typeof key === "bigint" ? key.toString() : key;
}

/** The child attribute *name* for a resolved (unquoted) physical column. */
function childAttrName(
  entity: { attributes(): readonly { name: string; column: string }[] },
  column: string,
): string {
  const attr = entity.attributes().find((a) => a.column === column);
  if (!attr) {
    throw new Error(`no attribute maps to child column '${column}'`);
  }
  return attr.name;
}

/** Split a `Class.relationship` ref into its parts. */
function splitRelRef(ref: string): [string, string] {
  const dot = ref.indexOf(".");
  if (dot === -1) {
    throw new Error(`malformed relationship reference '${ref}'`);
  }
  return [ref.slice(0, dot), ref.slice(dot + 1)];
}
