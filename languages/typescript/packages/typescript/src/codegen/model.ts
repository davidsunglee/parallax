/**
 * The codegen intermediate model — the per-entity shape the emitter renders from
 * (spec §7, §3.2). Derived purely from the fully-defaulted M1 metamodel reader,
 * so codegen emits only artifacts the descriptor declares (no invented enum or
 * value-object field types — spec §2.1).
 */
import type { EntityMetadata, Metamodel, NormalizedAttribute } from "@parallax/metamodel";

/** The generated TS property type for one M0 neutral scalar (spec §3.2.1). */
export function propertyTypeFor(type: string): string {
  if (/^decimal\(\d+,\d+\)$/.test(type)) {
    return "ParallaxDecimal";
  }
  switch (type) {
    case "boolean":
      return "boolean";
    case "int32":
    case "float32":
    case "float64":
      return "number";
    case "int64":
      return "bigint";
    case "string":
    case "uuid":
      return "string";
    case "bytes":
      return "Uint8Array";
    case "date":
      return "Temporal.PlainDate";
    case "time":
      return "Temporal.PlainTime";
    case "timestamp":
      return "Temporal.Instant";
    case "json":
      return "ParallaxJsonValue";
    default:
      // An unrecognized type is a descriptor the codegen cannot type; fall back
      // to the structural JSON value rather than inventing a type (spec §2.1).
      return "ParallaxJsonValue";
  }
}

/** A generated attribute — its DSL ref, property name/type, and physical column. */
export interface AttributeModel {
  /** The DSL name (`id`), used as the property key on the entity symbol. */
  readonly name: string;
  /** The qualified metamodel ref (`Order.id`) the DSL serializes. */
  readonly ref: string;
  /** The raw M0 neutral type (`int64`, `decimal(18,2)`), for import decisions. */
  readonly attributeType: string;
  /** The generated managed-object property type (spec §3.2.1). */
  readonly propertyType: string;
  /** Whether the property/input unions `| null` (spec §3.2.1). */
  readonly nullable: boolean;
}

/** A generated to-many relationship — quantified with `exists` / `notExists`. */
export interface ToManyRelationshipModel {
  readonly name: string;
  readonly ref: string;
  readonly relatedEntity: string;
}

/** A generated to-one relationship — a navigable path prefix. */
export interface ToOneRelationshipModel {
  readonly name: string;
  readonly ref: string;
  readonly relatedEntity: string;
}

/** The generated shape of one entity. */
export interface EntityModel {
  /** The domain class name (`Order`) — the entity symbol + managed-object type. */
  readonly name: string;
  /** The DSL accessor property (`orders`) on the `px` handle. */
  readonly finderName: string;
  /** The mapped table name. */
  readonly table: string;
  readonly attributes: readonly AttributeModel[];
  readonly toMany: readonly ToManyRelationshipModel[];
  readonly toOne: readonly ToOneRelationshipModel[];
}

/** The whole generated model: every entity plus the bundled descriptor. */
export interface CodegenModel {
  readonly entities: readonly EntityModel[];
}

/** Whether an M0 type maps to a `ParallaxDecimal` (needs the decimal re-export). */
function isDecimal(type: string): boolean {
  return /^decimal\(\d+,\d+\)$/.test(type);
}

/** True when any attribute across the model maps to `ParallaxDecimal`. */
export function usesDecimal(model: CodegenModel): boolean {
  return model.entities.some((e) => e.attributes.some((a) => isDecimal(a.attributeType)));
}

/** True when any attribute maps to a Temporal type (needs the `Temporal` import). */
export function usesTemporal(model: CodegenModel): boolean {
  const temporalTypes = new Set(["date", "time", "timestamp"]);
  return model.entities.some((e) => e.attributes.some((a) => temporalTypes.has(a.attributeType)));
}

/** True when any attribute maps to `ParallaxJsonValue`. */
export function usesJson(model: CodegenModel): boolean {
  return model.entities.some((e) =>
    e.attributes.some((a) => propertyTypeFor(a.attributeType) === "ParallaxJsonValue"),
  );
}

/** The default finder accessor name for an entity (`Order` → `orders`). */
export function finderNameFor(entity: EntityMetadata): string {
  const table = entity.table;
  // The table name is already the pluralized/physical form the developer expects
  // (`orders`, `order_item`); use it verbatim, camelized on `_`, as the accessor.
  return camelize(table);
}

/** Camel-case a snake_case identifier (`order_item` → `orderItem`). */
function camelize(name: string): string {
  return name.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase());
}

/** Build one entity's codegen model from its metadata. */
function entityModel(entity: EntityMetadata): EntityModel {
  const attributes: AttributeModel[] = entity.attributes().map((attr: NormalizedAttribute) => ({
    name: attr.name,
    ref: `${entity.name}.${attr.name}`,
    attributeType: attr.type,
    propertyType: propertyTypeFor(attr.type),
    nullable: attr.nullable,
  }));
  const toMany: ToManyRelationshipModel[] = [];
  const toOne: ToOneRelationshipModel[] = [];
  for (const rel of entity.relationships()) {
    const ref = `${entity.name}.${rel.name}`;
    if (rel.cardinality === "one-to-many" || rel.cardinality === "many-to-many") {
      toMany.push({ name: rel.name, ref, relatedEntity: rel.relatedEntity });
    } else {
      toOne.push({ name: rel.name, ref, relatedEntity: rel.relatedEntity });
    }
  }
  return {
    name: entity.name,
    finderName: finderNameFor(entity),
    table: entity.table,
    attributes,
    toMany,
    toOne,
  };
}

/** Build the whole codegen model from a metamodel reader. */
export function buildCodegenModel(metamodel: Metamodel): CodegenModel {
  return { entities: metamodel.entities().map(entityModel) };
}
