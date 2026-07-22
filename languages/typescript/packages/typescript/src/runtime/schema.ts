/**
 * The application-runtime `SchemaResolver` (spec §2, §3.2).
 *
 * The `parallax(...)` factory's `find` compiles a DSL-built operation with the
 * SAME m-sql `compile` visitor the conformance adapter uses — so it needs a
 * `SchemaResolver`. The conformance-side `MetamodelSchema` is case-driven (its
 * projection comes from a case's `expectedRows`); the application runtime instead
 * projects the root entity's FULL attribute set, because `find` returns managed
 * domain objects (spec §2.3). Both resolve `Class.attr` / `Class.relationship` /
 * as-of axes the same way, over the shared m-descriptor reader.
 *
 * As-of predicate injection delegates to `@parallax/bitemporal` (the m-temporal-read owner),
 * reached directly from the composition root, so temporal reads (`asOf` / range /
 * history) lower identically to the adapter.
 */
import {
  type AsOfPredicate,
  type AxisPins,
  asOfPredicate as deriveAsOfPredicate,
  type ResolvedAxis,
  type Axis as TemporalAxis,
} from "@parallax/bitemporal";
import type { Dialect } from "@parallax/dialect";
import type { EntityMetadata, Metamodel, NormalizedValueObjectMember } from "@parallax/metamodel";
import type {
  AsOfFragment,
  AxisPins as CompilerAxisPins,
  ProjectionColumn,
  ResolvedColumn,
  ResolvedNestedPath,
  ResolvedRelationship,
  SchemaResolver,
} from "@parallax/sql";

/** Split a `Class.member` reference into its class + member parts. */
function splitRef(ref: string): [string, string] {
  const dot = ref.indexOf(".");
  if (dot === -1) {
    throw new Error(`malformed reference '${ref}' (expected 'Class.member')`);
  }
  return [ref.slice(0, dot), ref.slice(dot + 1)];
}

/**
 * A `SchemaResolver` over the m-descriptor reader for the application runtime. Rooted at
 * one entity, it projects that entity's full attribute set and resolves refs
 * across the whole metamodel (a predicate may reference a navigated child).
 */
export class RuntimeSchema implements SchemaResolver {
  constructor(
    private readonly metamodel: Metamodel,
    private readonly rootEntity: EntityMetadata,
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
    const [className, relName] = splitRef(ref);
    const source = this.metamodel.entity(className);
    const relationship = source.relationshipByName(relName);
    const related = this.metamodel.entity(relationship.join.target.entity);
    return {
      childTable: related.table,
      childColumn: this.dialect.quoteIdentifier(
        related.attributeByName(relationship.join.target.name).column,
      ),
      parentColumn: this.dialect.quoteIdentifier(
        source.attributeByName(relationship.join.source.name).column,
      ),
    };
  }

  /**
   * Resolve a value-object nested path (`Class.vo.field…` / `Class.vo…`) against
   * the declared recursive structure (m-value-object) — the runtime mirror of the
   * conformance `MetamodelSchema.resolveNested`, so a developer nested predicate
   * (`Customer.address.city.eq(...)`, `Customer.address.phones.exists(...)`) lowers
   * to the same golden SQL. `manyIndex` records the first `many` crossing (the
   * top-level value object is index 0), turning a flat extraction into an
   * any-element traversal.
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
    let manyIndex = top.multiplicity === "many" ? 0 : -1;
    let leafIsAttribute = false;
    let leafType: string | undefined;
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

  rootTable(): string {
    return this.rootEntity.table;
  }

  /**
   * A `find` returns managed objects, so it projects every attribute column.
   *
   * A `bytes` column is projected **verbatim** (no `type`), NOT through the
   * `encode(<alias>.<col>, ?) <col>_hex` hex lowering: the runtime normalizes
   * bytes to a fresh `Uint8Array` in `EntityFinder`'s row materializer (spec
   * §3.2.1). The `encode(...,'hex')` lowering — which fires solely when a
   * projection carries `type === "bytes"` in the compiler — stays EXCLUSIVE to
   * the conformance `MetamodelSchema`/`readProjection` case-driven path (the
   * `_hex` row-observation seam, case `m-core-001`). Every non-bytes column keeps its
   * m-core `type` (no consumer other than the bytes trigger, but harmless).
   */
  rootProjection(): readonly ProjectionColumn[] {
    const attributeColumns = this.rootEntity
      .attributes()
      .map((attr) =>
        attr.type === "bytes"
          ? { column: this.dialect.quoteIdentifier(attr.column) }
          : { column: this.dialect.quoteIdentifier(attr.column), type: attr.type },
      );
    // A top-level value object projects its ONE structured-document column
    // verbatim (m-value-object): the whole nested composite materializes with the
    // owner in one round trip; the row materializer decodes + projects it to the
    // declared shape. No child statement, no reverse getter.
    const valueObjectColumns = this.rootEntity
      .valueObjects()
      .map((vo) => ({ column: this.dialect.quoteIdentifier(vo.column) }));
    return [...attributeColumns, ...valueObjectColumns];
  }

  rootEntityName(): string {
    return this.rootEntity.name;
  }

  targetEntityName(ref: string): string {
    const [className, relName] = splitRef(ref);
    const relationship = this.metamodel.entity(className).relationshipByName(relName);
    return relationship.join.target.entity;
  }

  asOfPredicate(entity: string, alias: string, pins: CompilerAxisPins): AsOfFragment {
    const axes = this.resolveAxes(entity, alias);
    const predicate: AsOfPredicate = deriveAsOfPredicate(axes, pins as AxisPins);
    return { sql: predicate.sql, binds: predicate.binds };
  }

  private resolveAxes(entity: string, alias: string): readonly ResolvedAxis[] {
    return this.metamodel
      .entity(entity)
      .asOfAxes()
      .map((axis) => ({
        dimension: axis.dimension as TemporalAxis,
        startExpr: `${alias}.${this.dialect.quoteIdentifier(axis.startColumn)}`,
        endExpr: `${alias}.${this.dialect.quoteIdentifier(axis.endColumn)}`,
        toIsInclusive: axis.toIsInclusive,
        infinity: axis.infinity,
      }));
  }
}
