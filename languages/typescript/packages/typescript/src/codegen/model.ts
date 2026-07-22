/**
 * The codegen intermediate model — the per-entity shape the emitter renders from
 * (spec §7, §3.2). Derived purely from the fully-defaulted m-descriptor metamodel reader,
 * so codegen emits only artifacts the descriptor declares (no invented enum or
 * value-object field types — spec §2.1).
 */
import type {
  EntityMetadata,
  Metamodel,
  NormalizedAttribute,
  NormalizedValueObjectMember,
} from "@parallax/metamodel";

/** The generated TS property type for one m-core neutral scalar (spec §3.2.1). */
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
  /** The raw m-core neutral type (`int64`, `decimal(18,2)`), for import decisions. */
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
}

/** A generated to-one relationship — a navigable path prefix. */
export interface ToOneRelationshipModel {
  readonly name: string;
  readonly ref: string;
}

/** A generated typed leaf field of a value object (`address.city`). */
export interface ValueObjectFieldModel {
  /** The declared field name (`city`). */
  readonly name: string;
  /** The generated managed property type (`string`). */
  readonly propertyType: string;
  /** Whether the property unions `| null`. */
  readonly nullable: boolean;
  /** The FULL dotted DSL ref (`Customer.address.geo.country`) for a flat / any-element predicate. */
  readonly ref: string;
}

/**
 * A generated typed value object — its declared fields and self-nested value
 * objects to arbitrary depth (m-value-object). The managed shape is one typed
 * interface ({@link typeName}), and the DSL builder exposes typed
 * nested-predicate accessors (comparisons on fields, `exists`/`notExists` on the
 * member) carrying the dotted path. No reverse getter and no lock/cache/statement
 * machinery — a value object rides its owner.
 */
export interface ValueObjectModel {
  /** The member name (`address`, `geo`, `phones`). */
  readonly name: string;
  /** `one` (a nested object) or `many` (an array). */
  readonly multiplicity: "one" | "many";
  /** Whether the member is nullable (`one` → `| null`). */
  readonly nullable: boolean;
  /** The generated managed interface name (`CustomerAddressGeo`). */
  readonly typeName: string;
  /** The FULL dotted DSL ref to this member (`Customer.address.phones`) — the `exists` path. */
  readonly ref: string;
  /** The declared typed leaf fields. */
  readonly fields: readonly ValueObjectFieldModel[];
  /** The self-nested value objects (recursive, arbitrary depth). */
  readonly nested: readonly ValueObjectModel[];
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
  /** The declared top-level value objects (m-value-object), recursive. */
  readonly valueObjects: readonly ValueObjectModel[];
}

/** The whole generated model: every entity plus the bundled descriptor. */
export interface CodegenModel {
  readonly entities: readonly EntityModel[];
}

/** Whether an m-core type maps to a `ParallaxDecimal` (needs the decimal re-export). */
function isDecimal(type: string): boolean {
  return /^decimal\(\d+,\d+\)$/.test(type);
}

/** True when any attribute across the model maps to `ParallaxDecimal`. */
export function usesDecimal(model: CodegenModel): boolean {
  return model.entities.some((e) => e.attributes.some((a) => isDecimal(a.attributeType)));
}

/** True when any attribute maps to a Temporal type (needs the `Temporal` import). */
export function usesTemporal(model: CodegenModel): boolean {
  const temporalTypes = new Set(["Temporal.PlainDate", "Temporal.PlainTime", "Temporal.Instant"]);
  return model.entities.some(
    (e) =>
      e.attributes.some((a) => new Set(["date", "time", "timestamp"]).has(a.attributeType)) ||
      valueObjectFieldTypes(e.valueObjects).some((t) => temporalTypes.has(t)),
  );
}

/** True when any attribute maps to `ParallaxJsonValue`. */
export function usesJson(model: CodegenModel): boolean {
  return model.entities.some((e) =>
    e.attributes.some((a) => propertyTypeFor(a.attributeType) === "ParallaxJsonValue"),
  );
}

/** True when any entity declares a value object (needs the nested-predicate builders). */
export function usesValueObjects(model: CodegenModel): boolean {
  return model.entities.some((e) => e.valueObjects.length > 0);
}

/** Whether any value-object field (at any depth) maps to a Temporal type. */
function valueObjectFieldTypes(vos: readonly ValueObjectModel[]): readonly string[] {
  return vos.flatMap((vo) => [
    ...vo.fields.map((f) => f.propertyType),
    ...valueObjectFieldTypes(vo.nested),
  ]);
}

/** Pascal-case a snake/camel segment for a generated type name (`geo` → `Geo`). */
function pascal(name: string): string {
  const camel = name.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase());
  return camel.charAt(0).toUpperCase() + camel.slice(1);
}

/**
 * Build one value object's recursive codegen model. `entityRef` is the dotted DSL
 * ref of this member (`Customer.address.geo`); children accumulate onto it for
 * their full ref. The element-relative paths a scoped `where` uses are recomputed
 * per-`exists`-root in the emitter (they depend on which member `exists` is called
 * on), so the model carries only the full ref + the declared structure.
 */
function valueObjectModel(
  vo: NormalizedValueObjectMember,
  entityRef: string,
  typePrefix: string,
): ValueObjectModel {
  const ref = `${entityRef}.${vo.name}`;
  const typeName = `${typePrefix}${pascal(vo.name)}`;
  const fields: ValueObjectFieldModel[] = vo.attributes.map((attr) => ({
    name: attr.name,
    propertyType: propertyTypeFor(attr.type),
    nullable: attr.nullable,
    ref: `${ref}.${attr.name}`,
  }));
  const nested = vo.valueObjects.map((child) => valueObjectModel(child, ref, typeName));
  return {
    name: vo.name,
    multiplicity: vo.multiplicity,
    nullable: vo.nullable,
    typeName,
    ref,
    fields,
    nested,
  };
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
    const name = rel.identity.name;
    const ref = `${entity.name}.${name}`;
    if (rel.cardinality === "one-to-many") {
      toMany.push({ name, ref });
    } else {
      toOne.push({ name, ref });
    }
  }
  const valueObjects = entity
    .valueObjects()
    .map((vo) => valueObjectModel(vo, entity.name, entity.name));
  return {
    name: entity.name,
    finderName: finderNameFor(entity),
    table: entity.table,
    attributes,
    toMany,
    toOne,
    valueObjects,
  };
}

/** Build the whole codegen model from a metamodel reader. */
export function buildCodegenModel(metamodel: Metamodel): CodegenModel {
  return { entities: metamodel.entities().map(entityModel) };
}
