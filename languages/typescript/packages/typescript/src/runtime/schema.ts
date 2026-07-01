/**
 * The application-runtime `SchemaResolver` (spec §1, §2.2).
 *
 * The `parallax(...)` factory's `find` compiles a DSL-built operation with the
 * SAME M3 `compile` visitor the conformance adapter uses — so it needs a
 * `SchemaResolver`. The conformance-side `MetamodelSchema` is case-driven (its
 * projection comes from a case's `expectedRows`); the application runtime instead
 * projects the root entity's FULL attribute set, because `find` returns managed
 * domain objects (spec §1.3). Both resolve `Class.attr` / `Class.relationship` /
 * as-of axes the same way, over the shared M1 reader.
 *
 * As-of predicate injection delegates to `@parallax/bitemporal` (the M7 owner),
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
import type { EntityMetadata, Metamodel } from "@parallax/metamodel";
import {
  type AsOfFragment,
  type Axis,
  type AxisPins as CompilerAxisPins,
  type ProjectionColumn,
  quoteIdentifier,
  type ResolvedColumn,
  type ResolvedRelationship,
  type SchemaResolver,
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
 * Parse a canonical relationship `join` (`this.<thisAttr> = <Related>.<attr>`)
 * into its two attribute names. The form is fixed by the metamodel schema.
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

/**
 * A `SchemaResolver` over the M1 reader for the application runtime. Rooted at
 * one entity, it projects that entity's full attribute set and resolves refs
 * across the whole metamodel (a predicate may reference a navigated child).
 */
export class RuntimeSchema implements SchemaResolver {
  constructor(
    private readonly metamodel: Metamodel,
    private readonly rootEntity: EntityMetadata,
  ) {}

  resolveAttribute(ref: string): ResolvedColumn {
    const [className, attrName] = splitRef(ref);
    const entity = this.metamodel.entity(className);
    const attr = entity.attributeByName(attrName);
    return { table: entity.table, column: quoteIdentifier(attr.column), type: attr.type };
  }

  resolveRelationship(ref: string): ResolvedRelationship {
    const [className, relName] = splitRef(ref);
    const source = this.metamodel.entity(className);
    const relationship = source.relationshipByName(relName);
    const { thisAttr, relatedAttr } = parseJoin(relationship.join);
    const related = this.metamodel.entity(relationship.relatedEntity);
    return {
      childTable: related.table,
      childColumn: quoteIdentifier(related.attributeByName(relatedAttr).column),
      parentColumn: quoteIdentifier(source.attributeByName(thisAttr).column),
    };
  }

  rootTable(): string {
    return this.rootEntity.table;
  }

  /** A `find` returns managed objects, so it projects every attribute column. */
  rootProjection(): readonly ProjectionColumn[] {
    return this.rootEntity
      .attributes()
      .map((attr) => ({ column: quoteIdentifier(attr.column), type: attr.type }));
  }

  rootEntityName(): string {
    return this.rootEntity.name;
  }

  resolveAsOfAxis(ref: string): Axis {
    const [className, attrName] = splitRef(ref);
    return this.metamodel.entity(className).asOfAttributeByName(attrName).axis as Axis;
  }

  relatedEntityName(ref: string): string {
    const [className, relName] = splitRef(ref);
    const relationship = this.metamodel.entity(className).relationshipByName(relName);
    return relationship.relatedEntity;
  }

  asOfPredicate(entity: string, alias: string, pins: CompilerAxisPins): AsOfFragment {
    const axes = this.resolveAxes(entity, alias);
    const predicate: AsOfPredicate = deriveAsOfPredicate(axes, pins as AxisPins);
    return { sql: predicate.sql, binds: predicate.binds };
  }

  private resolveAxes(entity: string, alias: string): readonly ResolvedAxis[] {
    return this.metamodel
      .entity(entity)
      .asOfAttributes()
      .map((axis) => ({
        axis: axis.axis as TemporalAxis,
        fromExpr: `${alias}.${quoteIdentifier(axis.fromColumn)}`,
        toExpr: `${alias}.${quoteIdentifier(axis.toColumn)}`,
        toIsInclusive: axis.toIsInclusive,
        infinity: axis.infinity,
      }));
  }
}
