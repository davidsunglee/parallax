/**
 * The `SchemaResolver` the m-sql compiler needs, implemented over the m-descriptor metamodel
 * reader, plus the base read-projection rule (m-sql "Read projection").
 *
 * `@parallax/sql` stays metamodel-free by accepting an injected `SchemaResolver`;
 * this module is the conformance-side implementation. It resolves `Class.attr`
 * references to alias-qualified, quoted columns (with the m-core neutral type the
 * compiler coerces literals against), resolves a `Class.relationship` reference to
 * its correlated-EXISTS join columns, and supplies the root entity's table + the
 * ordered read projection the SELECT projects.
 *
 * Projections are **rule-driven** from the model, mirroring the normative base
 * read-projection rule (`m-sql`, "Read projection") the corpus goldens now derive
 * from — a pure function of the target entity and result form, never of the
 * predicate (the `then.rows` / `then.graph` witness is NOT consulted). Slot 1 is the
 * effective scalar columns in `columnOrder` (declaration order — including the
 * `optimisticLocking` version column and each as-of axis's interval columns); slot 4
 * is the value-object document columns, LAST, on an instance-form read only.
 * Slice-mvp-1 targets only concrete, non-polymorphic entities, so the
 * table-per-hierarchy tag (slot 2) and table-per-concrete-subtype variant (slot 3)
 * never appear. Instance-form vs row-form is the `m-case-format` result-form
 * selector: a case asserting `then.graph` / `then.graphs` is instance-form (the
 * object lane); one asserting `then.rows` is row-form (the values lane).
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
  type NormalizedValueObjectMember,
  type Operation,
  type PathSegment,
  type RelationshipMetadata,
} from "@parallax/operation";
import type {
  AsOfFragment,
  AxisPins as CompilerAxisPins,
  ProjectionColumn,
  ResolvedColumn,
  ResolvedNestedPath,
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
  readonly relationship: RelationshipMetadata;
  readonly sourceEntity: EntityMetadata;
  readonly targetEntity: EntityMetadata;
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
   * Resolve a value-object nested path (`Class.vo.field…`, or `Class.vo…` for an
   * exists) against the declared recursive structure (m-value-object). The first
   * segment after the class names a top-level value object (the one
   * structured-document column); each further segment a nested value object or, at
   * the leaf, a typed attribute. `manyIndex` records the first `many` member crossed
   * within the full path — including the TOP-LEVEL value object itself (a top-level
   * `many` is `manyIndex === 0`, a root array), so a `many` crossing turns a flat
   * extraction into an any-element traversal; `leafType` / `leafIsMany` describe the
   * terminal member (a top-level `many` reached with empty `rest` is the to-many
   * leaf of an exists). An
   * unresolved segment throws — but by the time compile runs, the `rejected`-case
   * validator (`@parallax/operation`) has already refused a bad path pre-SQL.
   */
  resolveNested(ref: string): ResolvedNestedPath {
    const [className, voName, ...rest] = ref.split(".");
    const entity = this.metamodel.entity(className as string);
    const top = voName === undefined ? undefined : entity.findValueObject(voName);
    if (top === undefined) {
      throw new Error(
        `'${ref}': '${String(voName)}' is not a value object declared on ${className}`,
      );
    }
    let member: NormalizedValueObjectMember = top;
    // `manyIndex` counts the full nested path with the top-level value object at index
    // 0. A top-level `many` value object makes the ROOT the first `many` crossing
    // (`manyIndex === 0`, an empty `arrayPath` — the document column itself is the
    // array); a nested `many` at `rest[k]` is `k + 1`; a to-one-only path is `-1`.
    let manyIndex = top.multiplicity === "many" ? 0 : -1;
    let leafIsAttribute = false;
    let leafType: string | undefined;
    // An exists path with empty `rest` terminates AT the top-level value object, so a
    // top-level `many` is itself the to-many leaf (`nestedExists(Class.vo)`).
    let leafIsMany = rest.length === 0 && top.multiplicity === "many";
    rest.forEach((segment, index) => {
      const nested = member.valueObjects.find((vo) => vo.name === segment);
      if (nested !== undefined) {
        if (nested.multiplicity === "many" && manyIndex === -1) {
          manyIndex = index + 1;
        }
        member = nested;
        if (index === rest.length - 1) {
          leafIsAttribute = false;
          leafIsMany = nested.multiplicity === "many";
        }
        return;
      }
      const attribute = member.attributes.find((attr) => attr.name === segment);
      if (attribute === undefined) {
        throw new Error(`'${ref}': '${segment}' is not a member of value object '${member.name}'`);
      }
      leafIsAttribute = true;
      leafType = attribute.type;
    });
    return {
      table: entity.table,
      column: this.dialect.quoteIdentifier(top.column),
      segments: rest,
      manyIndex,
      leafIsAttribute,
      ...(leafType === undefined ? {} : { leafType }),
      leafIsMany,
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
    const targetEntity = this.metamodel.entity(relationship.join.target.entity);
    const parent = sourceEntity.attributeByName(relationship.join.source.name);
    const child = targetEntity.attributeByName(relationship.join.target.name);
    return {
      relationship,
      sourceEntity,
      targetEntity,
      childTable: targetEntity.table,
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

  /** The root entity's domain class name (the `then.graph` key). */
  rootEntityName(): string {
    return this.rootEntity.name;
  }

  /**
   * The class name of the related (child) entity a `Class.relationship` reference
   * navigates to — the EXISTS child, for as-of propagation into the semi-join.
   */
  targetEntityName(ref: string): string {
    return this.correlation(ref).targetEntity.name;
  }

  /**
   * The injected as-of predicate for an entity's declared axes under a set of
   * pins, qualified with `alias`. Delegates the per-dimension rule and canonical
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
    return metadata.asOfAxes().map((axis) => ({
      dimension: axis.dimension as TemporalAxis,
      startExpr: `${alias}.${this.dialect.quoteIdentifier(axis.startColumn)}`,
      endExpr: `${alias}.${this.dialect.quoteIdentifier(axis.endColumn)}`,
      toIsInclusive: axis.toIsInclusive,
      infinity: axis.infinity,
    }));
  }
}

/**
 * The base **read projection** (m-sql "Read projection") for an entity: slot 1 —
 * every declared attribute's column in `columnOrder` (declaration order), which
 * already INCLUDES the `optimisticLocking` version column and each as-of axis's
 * `startColumn` / `endColumn` interval columns (all ordinary declared attributes,
 * `m-descriptor`) — followed on an **instance-form** read by slot 4: every declared
 * top-level value object's backing column, LAST. Slots 2/3 (the table-per-hierarchy
 * tag column, the table-per-concrete-subtype `familyVariant` literal) apply only to
 * an abstract-target read; slice-mvp-1 carries no inheritance, so they never appear.
 * A `bytes` column keeps its m-core `type` so the compiler lowers it to the
 * `encode(t0.<col>, ?) <col>_hex` hex form at its slot-1 position (`m-core-001`).
 */
function instanceFormProjection(
  entity: EntityMetadata,
  dialect: Dialect,
): readonly ProjectionColumn[] {
  return [...scalarProjection(entity, dialect), ...valueObjectProjection(entity, dialect)];
}

/** Slot 1 — the effective scalar columns in `columnOrder`. */
function scalarProjection(entity: EntityMetadata, dialect: Dialect): readonly ProjectionColumn[] {
  return entity.attributes().map((attr) => attributeProjection(attr, dialect));
}

/** Slot 4 — the value-object backing columns (instance-form only), in declared order. */
function valueObjectProjection(
  entity: EntityMetadata,
  dialect: Dialect,
): readonly ProjectionColumn[] {
  return entity.valueObjects().map((vo) => ({ column: dialect.quoteIdentifier(vo.column) }));
}

/**
 * A read's result form (`m-case-format` selector): a case is **instance-form** (the
 * object lane — projects slot 4) when it asserts `then.graph` / `then.graphs`, and
 * **row-form** (the values lane — omits slot 4) when it asserts `then.rows`. The
 * form is declared by which result member the case asserts, never by the predicate.
 */
function isInstanceForm(loaded: LoadedCase): boolean {
  const then = loaded.raw.then as { graph?: unknown; graphs?: unknown } | undefined;
  return then?.graph !== undefined || then?.graphs !== undefined;
}

/**
 * Resolve a flat read case's projection from the model per the base **read
 * projection** rule (m-sql) — a pure function of the target entity and result form,
 * NEVER of the predicate. An instance-form read (a value-object materialization
 * graph) projects the full instance-form list (scalars, then the value-object
 * documents last); a row-form read (`then.rows`) projects slot 1 only. Because the
 * list is predicate-independent, an empty `none` read or an empty-result read
 * projects the SAME full column list as any other read of the same entity — the
 * case's `then.rows` / `then.graph` witness is no longer consulted to derive it.
 */
export function readProjection(
  loaded: LoadedCase,
  rootEntity: EntityMetadata,
  dialect: Dialect,
): readonly ProjectionColumn[] {
  return isInstanceForm(loaded)
    ? instanceFormProjection(rootEntity, dialect)
    : scalarProjection(rootEntity, dialect);
}

/** A verbatim projection descriptor for an attribute (quoted column + m-core type). */
function attributeProjection(attr: NormalizedAttribute, dialect: Dialect): ProjectionColumn {
  return { column: dialect.quoteIdentifier(attr.column), type: attr.type };
}

/**
 * The deep-fetch **root** projection: a deep fetch is instance-form (the object
 * lane, m-sql "Read projection"), so its root level projects the root entity's full
 * instance-form list — scalars in `columnOrder`, then the value-object documents
 * last (`m-deep-fetch-018`'s `Customer` root projects `id, name, address`). The root
 * class is the first hop's class (`OrderItem` in `[OrderItem.order]`); a pathless
 * deep fetch (none in the corpus) falls back to the graph root key, then the
 * model's first entity.
 */
export function rootDeepFetchProjection(
  loaded: LoadedCase,
  paths: readonly (readonly PathSegment[])[],
  dialect: Dialect,
): readonly ProjectionColumn[] {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const rootClass = classOf(paths[0]?.[0]?.rel) ?? Object.keys(caseGraph(loaded))[0];
  const rootEntity = rootClass ? metamodel.entity(rootClass) : metamodel.entities()[0];
  return rootEntity ? instanceFormProjection(rootEntity, dialect) : [];
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
 * The deep-fetch **child-level** projection: every deep-fetch / snapshot child
 * level is instance-form (m-sql "Read projection"), so it projects the child
 * entity's own instance-form list — its scalars in `columnOrder` (the correlating
 * foreign key is a declared scalar, always in slot 1), then any value-object
 * document columns it declares, last (`m-deep-fetch-018`: a value-object-bearing
 * child materializes its `address` document at depth).
 */
export function childProjection(
  childEntity: EntityMetadata,
  dialect: Dialect,
): readonly ProjectionColumn[] {
  return instanceFormProjection(childEntity, dialect);
}

/** The `then.graph` of a case, or an empty graph when absent. */
function caseGraph(loaded: LoadedCase): Record<string, readonly Record<string, unknown>[]> {
  return (
    (loaded.raw.then?.graph as Record<string, readonly Record<string, unknown>[]> | undefined) ?? {}
  );
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

/** Build a flat-read `MetamodelSchema` (projection driven by `then.rows`). */
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
