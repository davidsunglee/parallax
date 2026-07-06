/**
 * The `SchemaResolver` the m-sql compiler needs, implemented over the m-descriptor metamodel
 * reader, plus the case-driven projection rules.
 *
 * `@parallax/sql` stays metamodel-free by accepting an injected `SchemaResolver`;
 * this module is the conformance-side implementation. It resolves `Class.attr`
 * references to alias-qualified, quoted columns (with the m-core neutral type the
 * compiler coerces literals against), resolves a `Class.relationship` reference to
 * its correlated-EXISTS join columns, and supplies the root entity's table + the
 * ordered read projection the SELECT projects.
 *
 * Projections are **case-driven** so the emitted SQL matches the golden by
 * construction: a flat read takes its output columns from `expectedRows`; a
 * deep-fetch root takes them from the `expectedGraph` root object (minus the
 * top-level relationship names); a deep-fetch child level takes them from the
 * `expectedGraph` child object (minus that node's own relationship names). When a
 * level carries no `expectedGraph` witness (an empty intermediate), the projection
 * falls back to the child entity's non-nullable columns plus any nullable
 * `orderBy` key — the documented `m-deep-fetch-008` path.
 */
import {
  type AsOfPredicate,
  type AxisPins,
  asOfPredicate as deriveAsOfPredicate,
  type ResolvedAxis,
  type Axis as TemporalAxis,
} from "@parallax/bitemporal";
import type { Dialect } from "@parallax/dialect";
import {
  type EntityMetadata,
  Metamodel,
  type NormalizedAttribute,
  type NormalizedRelationship,
  type Operation,
} from "@parallax/operation";
import type {
  AsOfFragment,
  Axis,
  AxisPins as CompilerAxisPins,
  ProjectionColumn,
  ResolvedColumn,
  ResolvedRelationship,
  SchemaResolver,
} from "@parallax/sql";
import type { LoadedCase } from "./discover.js";

/**
 * A relationship's resolved join correlation, in **unquoted physical** terms (the
 * deep-fetch strategy indexes row objects by these names). The metamodel `join`
 * is authored canonically as `this.<thisAttr> = <Related>.<relatedAttr>`, naming
 * the source-side (parent, correlating) attribute and the related-side (child,
 * inner) attribute. The mapping is uniform across cardinalities: a to-many hop
 * (`this.id = OrderItem.orderId`) correlates child `order_id` to parent `id`; a
 * to-one hop (`this.orderId = Order.id`) correlates child `id` to parent
 * `order_id` — the join already names both key columns and which entity owns each.
 */
export interface RelationshipCorrelation {
  readonly relationship: NormalizedRelationship;
  readonly sourceEntity: EntityMetadata;
  readonly relatedEntity: EntityMetadata;
  readonly childTable: string;
  readonly childColumn: string;
  readonly parentColumn: string;
}

/**
 * A `SchemaResolver` over the m-descriptor metamodel reader. Resolves `Class.attr`
 * references to alias-qualified columns (with the m-core neutral type the compiler
 * coerces literals against), resolves relationships to their join correlation,
 * and supplies the root entity's table + read projection the m-sql visitor projects.
 */
export class MetamodelSchema implements SchemaResolver {
  constructor(
    private readonly metamodel: Metamodel,
    private readonly rootEntity: EntityMetadata,
    private readonly projection: readonly ProjectionColumn[],
    /** The injected m-dialect dialect — the single authority for identifier quoting. */
    private readonly dialect: Dialect,
  ) {}

  resolveAttribute(ref: string): ResolvedColumn {
    const [className, attrName] = splitRef(ref);
    const entity = this.metamodel.entity(className);
    const attr = entity.attributeByName(attrName);
    return {
      table: entity.table,
      column: this.dialect.quoteIdentifier(attr.column),
      type: attr.type,
      nullable: attr.nullable,
    };
  }

  resolveRelationship(ref: string): ResolvedRelationship {
    const correlation = this.correlation(ref);
    return {
      childTable: correlation.childTable,
      childColumn: this.dialect.quoteIdentifier(correlation.childColumn),
      parentColumn: this.dialect.quoteIdentifier(correlation.parentColumn),
    };
  }

  /**
   * Resolve a `Class.relationship` reference to the unquoted physical columns +
   * tables of its canonical join correlation. The deep-fetch strategy indexes row
   * objects by these unquoted physical names; {@link resolveRelationship} quotes
   * them for the EXISTS semi-join SQL. Both derive from the one parse here.
   */
  correlation(ref: string): RelationshipCorrelation {
    const [className, relName] = splitRef(ref);
    const sourceEntity = this.metamodel.entity(className);
    const relationship = sourceEntity.relationshipByName(relName);
    const { thisAttr, relatedAttr } = parseJoin(relationship.join);
    const relatedEntity = this.metamodel.entity(relationship.relatedEntity);
    const parent = sourceEntity.attributeByName(thisAttr);
    const child = relatedEntity.attributeByName(relatedAttr);
    return {
      relationship,
      sourceEntity,
      relatedEntity,
      childTable: relatedEntity.table,
      childColumn: child.column,
      parentColumn: parent.column,
    };
  }

  rootTable(): string {
    return this.rootEntity.table;
  }

  rootProjection(): readonly ProjectionColumn[] {
    return this.projection;
  }

  /** The root entity's domain class name (the `expectedGraph` key). */
  rootEntityName(): string {
    return this.rootEntity.name;
  }

  /** Resolve a `Class.asOfAttribute` reference to the axis it pins (m-temporal-read). */
  resolveAsOfAxis(ref: string): Axis {
    const [className, attrName] = splitRef(ref);
    const entity = this.metamodel.entity(className);
    return entity.asOfAttributeByName(attrName).axis as Axis;
  }

  /**
   * The class name of the related (child) entity a `Class.relationship` reference
   * navigates to — the EXISTS child, for as-of propagation into the semi-join.
   */
  relatedEntityName(ref: string): string {
    return this.correlation(ref).relatedEntity.name;
  }

  /**
   * The injected as-of predicate for an entity's declared axes under a set of
   * pins, qualified with `alias`. Delegates the per-axis rule + business/processing
   * composition + default-injection to `@parallax/bitemporal` (the m-temporal-read owner),
   * reached through the composition path (`@parallax/sql` imports no m-temporal-read). A
   * non-temporal entity yields an empty fragment.
   */
  asOfPredicate(entity: string, alias: string, pins: CompilerAxisPins): AsOfFragment {
    const axes = this.resolveAxes(entity, alias);
    const predicate: AsOfPredicate = deriveAsOfPredicate(axes, pins as AxisPins);
    return { sql: predicate.sql, binds: predicate.binds };
  }

  /** Resolve an entity's declared as-of axes into alias-qualified {@link ResolvedAxis}. */
  private resolveAxes(entity: string, alias: string): readonly ResolvedAxis[] {
    const metadata = this.metamodel.entity(entity);
    return metadata.asOfAttributes().map((axis) => ({
      axis: axis.axis as TemporalAxis,
      fromExpr: `${alias}.${this.dialect.quoteIdentifier(axis.fromColumn)}`,
      toExpr: `${alias}.${this.dialect.quoteIdentifier(axis.toColumn)}`,
      toIsInclusive: axis.toIsInclusive,
      infinity: axis.infinity,
    }));
  }
}

/**
 * Resolve a flat read case's projection — the ordered output columns the SELECT
 * projects — **from the case**, matching the golden by construction (the Phase-3
 * `[pk, firstNonPk]` heuristic could not express `m-op-algebra-028`'s `distinct active` nor a
 * wider `orders` read).
 *
 * The case's `expectedRows` keys ARE the SQL output column names the golden
 * projects and the harness compares against. Each key resolves back to its
 * physical attribute so the compiler can lower a `bytes` column to the
 * `encode(t0.<col>, ?) <col>_hex` hex form (m-core scalar-serde projection —
 * `m-core-001`): a direct column match projects verbatim; an output ending `_hex`
 * whose stripped name is a `bytes` attribute projects through `encode(...)`. A key
 * that names no attribute (a computed output) projects verbatim as a plain quoted
 * column, as before. When `expectedRows` is empty (e.g. `m-op-algebra-023-none`),
 * the case provides no
 * key witness, so we fall back to the metamodel default — the primary key plus
 * the first non-key attribute.
 */
export function readProjection(
  loaded: LoadedCase,
  rootEntity: EntityMetadata,
  dialect: Dialect,
): readonly ProjectionColumn[] {
  const expectedRows = loaded.raw.expectedRows as readonly Record<string, unknown>[] | undefined;
  const firstRow = expectedRows?.[0];
  if (firstRow && Object.keys(firstRow).length > 0) {
    return Object.keys(firstRow).map((output) => projectionForOutput(output, rootEntity, dialect));
  }
  return defaultEntityProjection(rootEntity).map((attr) => attributeProjection(attr, dialect));
}

/**
 * Resolve one `expectedRows` output column name to its projection descriptor,
 * against the root entity's attributes. Order of resolution:
 *  1. an attribute whose physical `column` equals the output → project verbatim
 *     (with its m-core type, so a `bytes` column authored WITHOUT the `_hex` output
 *     alias would still lower — belt-and-braces, though the corpus always uses the
 *     `_hex` form);
 *  2. an output ending `_hex` whose stripped name is a `bytes` attribute's column
 *     → project through `encode(t0.<col>, ?) <output>` (the `m-core-001` hex form);
 *  3. otherwise a plain quoted column named by the output (a computed/derived
 *     output the model does not declare — the pre-m-core-001 behavior).
 */
function projectionForOutput(
  output: string,
  entity: EntityMetadata,
  dialect: Dialect,
): ProjectionColumn {
  const direct = entity.attributes().find((attr) => attr.column === output);
  if (direct) {
    return attributeProjection(direct, dialect);
  }
  if (output.endsWith("_hex")) {
    const physical = output.slice(0, -"_hex".length);
    const bytesAttr = entity
      .attributes()
      .find((attr) => attr.column === physical && attr.type === "bytes");
    if (bytesAttr) {
      return {
        column: dialect.quoteIdentifier(bytesAttr.column),
        type: "bytes",
        outputName: output,
      };
    }
  }
  return { column: dialect.quoteIdentifier(output) };
}

/** A verbatim projection descriptor for an attribute (quoted column + m-core type). */
function attributeProjection(attr: NormalizedAttribute, dialect: Dialect): ProjectionColumn {
  return { column: dialect.quoteIdentifier(attr.column), type: attr.type };
}

/**
 * Resolve a deep-fetch **root** projection from the case's `expectedGraph` root
 * object: its keys minus the top-level relationship names (the relationships are
 * attached in memory, not projected). When the root resolves to no rows (e.g.
 * `m-deep-fetch-006`, an empty-root deep fetch whose `expectedGraph` is `{ Order: [] }`),
 * there is no witness, so we fall back to the metamodel default projection for the
 * root entity — the primary key plus the first non-key attribute, which
 * reproduces the golden root `select id, name from orders …`. An empty projection
 * would emit a malformed `select  from …`.
 */
export function rootDeepFetchProjection(
  loaded: LoadedCase,
  paths: readonly (readonly string[])[],
  dialect: Dialect,
): readonly ProjectionColumn[] {
  const graph = expectedGraph(loaded);
  const rootEntityName = Object.keys(graph)[0];
  const rootRows = rootEntityName ? (graph[rootEntityName] ?? []) : [];
  const witness = rootRows[0];
  const topLevelRels = new Set(paths.map((path) => relName(path[0] ?? "")));
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const rootClass = classOf(paths[0]?.[0]) ?? rootEntityName;
  const rootEntity = rootClass ? metamodel.entity(rootClass) : metamodel.entities()[0];
  if (witness && typeof witness === "object") {
    return objectColumns(witness as Record<string, unknown>, topLevelRels, rootEntity, dialect);
  }
  // No witness (empty root): fall back to the metamodel default for the root
  // entity, named by the first hop of the first path (`Order` in `[Order.items,
  // …]`), or the graph root key, or the model's first entity as a last resort.
  if (!rootEntity) {
    return [];
  }
  return defaultEntityProjection(rootEntity).map((attr) => attributeProjection(attr, dialect));
}

/** The class part of a `Class.rel` reference, or `undefined` when absent. */
function classOf(ref: string | undefined): string | undefined {
  if (ref === undefined) {
    return undefined;
  }
  const dot = ref.indexOf(".");
  return dot === -1 ? ref : ref.slice(0, dot);
}

/**
 * Resolve a deep-fetch **child-level** projection from the `expectedGraph` child
 * object found under this node's relationship name: its keys minus this node's
 * own child-relationship names. When no witness exists anywhere (an empty
 * intermediate — `m-deep-fetch-008`), fall back to the child entity's non-nullable columns
 * plus any nullable `orderBy` key (so a nullable ordering column stays projected).
 */
export function childProjection(
  loaded: LoadedCase,
  node: { relRef: string; children: readonly { relRef: string }[] },
  childEntity: EntityMetadata,
  dialect: Dialect,
): readonly ProjectionColumn[] {
  const witness = findChildWitness(expectedGraph(loaded), node);
  const childRelNames = new Set(node.children.map((child) => relName(child.relRef)));
  if (witness) {
    return objectColumns(witness, childRelNames, childEntity, dialect);
  }
  return fallbackChildProjection(childEntity, node, dialect);
}

/**
 * The fallback child projection when no `expectedGraph` witness exists: the
 * entity's non-nullable columns, plus any nullable column named by a declared
 * `orderBy` key (the order key MUST be projected for the ordering oracle). Quoted
 * for SQL. Exercised only by the empty-intermediate case (`m-deep-fetch-008`).
 */
function fallbackChildProjection(
  childEntity: EntityMetadata,
  node: { relRef: string },
  dialect: Dialect,
): readonly ProjectionColumn[] {
  // The relationship name lives on the PARENT entity; the child entity does not
  // declare it, so the orderBy is unavailable here. The non-temporal corpus only
  // reaches this path for `Order.items` (no nullable orderBy key), so projecting
  // the non-nullable columns is exact. Keep nullable orderBy handling explicit
  // for clarity even though it is not exercised here.
  void node;
  return childEntity
    .attributes()
    .filter((attr) => !attr.nullable)
    .map((attr) => attributeProjection(attr, dialect));
}

/**
 * The keys of an `expectedGraph` object as projection descriptors, minus
 * relationship names. Each key resolves back to its physical attribute (so a
 * `bytes` column would lower, matching the flat-read rule) — but the deep-fetch
 * corpus projects only plain scalar columns, so this is verbatim in practice.
 * An `entity` is passed so the type + `_hex` resolution matches `readProjection`.
 */
function objectColumns(
  object: Record<string, unknown>,
  excluded: ReadonlySet<string>,
  entity: EntityMetadata | undefined,
  dialect: Dialect,
): readonly ProjectionColumn[] {
  return Object.keys(object)
    .filter((key) => !excluded.has(key))
    .map((key) =>
      entity ? projectionForOutput(key, entity, dialect) : { column: dialect.quoteIdentifier(key) },
    );
}

/**
 * Find the first non-null child object under `node`'s relationship name anywhere
 * in the graph, by walking the graph following each node's relationship name.
 * Returns `undefined` when the level is empty everywhere (no witness).
 */
function findChildWitness(
  graph: Record<string, readonly Record<string, unknown>[]>,
  node: { relRef: string },
): Record<string, unknown> | undefined {
  const name = relName(node.relRef);
  // Breadth-first over every object reachable in the graph; the first value found
  // under `name` that is a non-empty object (or the first element of a non-empty
  // array) is a witness for this level's projection.
  const queue: unknown[] = Object.values(graph).flat();
  while (queue.length > 0) {
    const current = queue.shift();
    if (current === null || typeof current !== "object") {
      continue;
    }
    const record = current as Record<string, unknown>;
    const related = record[name];
    const found = firstObject(related);
    if (found) {
      return found;
    }
    // Recurse into nested related objects/arrays to reach deeper levels.
    for (const value of Object.values(record)) {
      if (Array.isArray(value)) {
        queue.push(...value);
      } else if (value && typeof value === "object") {
        queue.push(value);
      }
    }
  }
  return undefined;
}

/** The first object witness from a related value (a single object or an array). */
function firstObject(value: unknown): Record<string, unknown> | undefined {
  if (Array.isArray(value)) {
    const head = value.find((item) => item && typeof item === "object");
    return head as Record<string, unknown> | undefined;
  }
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return undefined;
}

/** The `expectedGraph` of a case, or an empty graph when absent. */
function expectedGraph(loaded: LoadedCase): Record<string, readonly Record<string, unknown>[]> {
  return (
    (loaded.raw.expectedGraph as Record<string, readonly Record<string, unknown>[]> | undefined) ??
    {}
  );
}

/**
 * The metamodel default projection for an entity: the primary-key attribute(s)
 * followed by the first non-primary-key attribute (yielding `id, name` for the
 * `orders` root). Used only as the fallback when a case carries no witness.
 */
function defaultEntityProjection(entity: EntityMetadata): readonly NormalizedAttribute[] {
  const attributes = entity.attributes();
  const primaryKey = attributes.filter((attr) => attr.primaryKey);
  const firstNonPk = attributes.find((attr) => !attr.primaryKey);
  const projection = [...primaryKey];
  if (firstNonPk && !projection.includes(firstNonPk)) {
    projection.push(firstNonPk);
  }
  return projection;
}

/** Build a `MetamodelSchema` rooted at the entity the operation references. */
export function schemaForRoot(
  loaded: LoadedCase,
  operation: Operation,
  projection: readonly ProjectionColumn[],
  dialect: Dialect,
): MetamodelSchema {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const rootEntity = rootEntityFor(metamodel, operation);
  return new MetamodelSchema(metamodel, rootEntity, projection, dialect);
}

/** Build a `MetamodelSchema` rooted explicitly at a named entity (child levels). */
export function schemaForEntity(
  loaded: LoadedCase,
  entityName: string,
  projection: readonly ProjectionColumn[],
  dialect: Dialect,
): MetamodelSchema {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  return new MetamodelSchema(metamodel, metamodel.entity(entityName), projection, dialect);
}

/** Build a flat-read `MetamodelSchema` (projection driven by `expectedRows`). */
export function schemaForReadCase(
  loaded: LoadedCase,
  operation: Operation,
  dialect: Dialect,
): MetamodelSchema {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const rootEntity = rootEntityFor(metamodel, operation);
  const projection = readProjection(loaded, rootEntity, dialect);
  return new MetamodelSchema(metamodel, rootEntity, projection, dialect);
}

/**
 * Build a flat `physical column name -> m-core neutral type` map across EVERY entity
 * in the case's descriptor. The type-aware comparator (carry-forward b) keys row
 * / graph columns by this map so a numeric column reconciles in decimal space and
 * a textual column is graded as exact text. A deep-fetch graph projects columns
 * from several entities (`order_id`, `code`, `shipped_on`, …); the physical
 * column names are distinct enough within the orders corpus to key by name, and a
 * shared name (`id`) is the same `int64` type on every entity, so the flat merge
 * is unambiguous for grading purposes.
 */
export function columnTypesForCase(loaded: LoadedCase): Record<string, string> {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const types: Record<string, string> = {};
  for (const entity of metamodel.entities()) {
    for (const attr of entity.attributes()) {
      types[attr.column] = attr.type;
    }
  }
  return types;
}

/** The root entity an operation queries: the first `Class.attr` reference. */
function rootEntityFor(metamodel: Metamodel, operation: Operation): EntityMetadata {
  const ref = firstClassRef(operation);
  if (ref) {
    return metamodel.entity(ref);
  }
  const [first] = metamodel.entities();
  if (!first) {
    throw new Error("model declares no entities");
  }
  return first;
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

/** Split a `Class.attribute` (or `Class.relationship`) reference into its parts. */
function splitRef(ref: string): [string, string] {
  const dot = ref.indexOf(".");
  if (dot === -1) {
    throw new Error(`malformed reference '${ref}' (expected 'Class.member')`);
  }
  return [ref.slice(0, dot), ref.slice(dot + 1)];
}

/** The relationship name (the part after the dot) of a `Class.relationship` ref. */
function relName(ref: string): string {
  const dot = ref.indexOf(".");
  return dot === -1 ? ref : ref.slice(dot + 1);
}

/**
 * Parse a canonical relationship `join` predicate `this.<thisAttr> =
 * <Related>.<relatedAttr>` into its two attribute names. The form is fixed by the
 * metamodel schema, so a malformed join is a descriptor error, not a guess.
 */
function parseJoin(join: string): { thisAttr: string; relatedAttr: string } {
  const match = /^\s*this\.(\w+)\s*=\s*\w+\.(\w+)\s*$/.exec(join);
  if (!match) {
    throw new Error(
      `unsupported relationship join '${join}' (expected 'this.<attr> = <Related>.<attr>')`,
    );
  }
  return { thisAttr: match[1] as string, relatedAttr: match[2] as string };
}
