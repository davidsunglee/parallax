/**
 * Defaulting / normalization for parsed model descriptors.
 *
 * A descriptor is authored sparsely: schema defaults (`nullable: false`,
 * `direction: asc`, `temporal` derived from `asOfAttributes`, …) are omitted in
 * the YAML but are part of the metamodel's meaning. The reader (`reader.ts`)
 * presents the *fully defaulted* view; this module is where those defaults are
 * filled in and the derived `temporal` classification is computed and checked.
 *
 * Normalization never mutates the parsed input — it produces normalized value
 * objects the reader hands out — and it never reorders arrays.
 */

/**
 * Raw (as-parsed) entity shape: a loose mirror of the schema's `entity`.
 *
 * `table` and `attributes` are OPTIONAL because an inheritance node may omit them
 * (m-inheritance, resolved Q5): an abstract `root` / `abstract-subtype` is
 * tableless, and a concrete subtype declaring only inherited attributes has none
 * of its own. A non-inheritance entity still declares both (enforced by the
 * metamodel schema's conditional requirements).
 */
export interface RawEntity {
  readonly name: string;
  readonly namespace?: string;
  readonly table?: string;
  readonly mutability?: "read-only" | "transactional";
  readonly temporal?:
    | "non-temporal"
    | "unitemporal-processing"
    | "unitemporal-business"
    | "bitemporal";
  readonly attributes?: readonly RawAttribute[];
  readonly asOfAttributes?: readonly RawAsOfAttribute[];
  readonly relationships?: readonly RawRelationship[];
  readonly indices?: readonly RawIndex[];
  readonly valueObjects?: readonly RawValueObject[];
  readonly inheritance?: RawInheritance;
}

export interface RawAttribute {
  readonly name: string;
  readonly type: string;
  readonly column: string;
  readonly primaryKey?: boolean;
  readonly nullable?: boolean;
  readonly maxLength?: number;
  readonly readOnly?: boolean;
  readonly optimisticLocking?: boolean;
  readonly pkGenerator?: RawPkGenerator;
  readonly default?: unknown;
}

export type RawPkGenerator =
  | "none"
  | "max"
  | "sequence"
  | {
      readonly strategy: "none" | "max" | "sequence";
      readonly sequenceName?: string;
      readonly batchSize?: number;
      readonly initialValue?: number;
      readonly incrementSize?: number;
    };

export interface RawRelationship {
  readonly name: string;
  readonly relatedEntity: string;
  readonly cardinality: "one-to-one" | "many-to-one" | "one-to-many" | "many-to-many";
  readonly join: string;
  readonly reverseName?: string;
  readonly dependent?: boolean;
  readonly foreignKey?: string;
  readonly orderBy?: readonly { readonly attr: string; readonly direction?: "asc" | "desc" }[];
}

export interface RawIndex {
  readonly name: string;
  readonly attributes: readonly string[];
  readonly unique?: boolean;
}

export interface RawAsOfAttribute {
  readonly name: string;
  readonly fromColumn: string;
  readonly toColumn: string;
  readonly axis: "processing" | "business";
  readonly toIsInclusive?: boolean;
  readonly infinity?: "infinity";
  readonly default?: "now";
}

/** A raw (as-parsed) typed field of a value object — no per-field column. */
export interface RawValueObjectAttribute {
  readonly name: string;
  readonly type: string;
  readonly nullable?: boolean;
}

/**
 * A raw (as-parsed) value object nested inside another. It shares its top-level
 * ancestor's single structured-document column, so it carries NO `column` /
 * `mapping` storage — otherwise it mirrors a top-level value object: typed
 * attributes, its own `one` / `many` cardinality, and further-nested value
 * objects to arbitrary depth.
 */
export interface RawNestedValueObject {
  readonly name: string;
  readonly nullable?: boolean;
  readonly cardinality?: "one" | "many";
  readonly attributes?: readonly RawValueObjectAttribute[];
  readonly valueObjects?: readonly RawNestedValueObject[];
}

/**
 * A raw (as-parsed) top-level value object: the recursive nested shape PLUS the
 * single-column storage (`column` / `mapping`) only a top-level member carries.
 */
export interface RawValueObject {
  readonly name: string;
  readonly column: string;
  readonly mapping?: "json";
  readonly nullable?: boolean;
  readonly cardinality?: "one" | "many";
  readonly attributes?: readonly RawValueObjectAttribute[];
  readonly valueObjects?: readonly RawNestedValueObject[];
}

/**
 * A raw (as-parsed) inheritance block (m-inheritance): a node's position in a
 * closed class tree. The `root` alone declares the family `strategy`
 * (table-per-hierarchy with a `tag`/`tagValue` discriminator, or
 * table-per-concrete-subtype); descendants name their `parent`. `tag` lives on the
 * table-per-hierarchy root; `tagValue` on each concrete subtype. The pre-ADR
 * `table-per-leaf` / `discriminator` / `discriminatorValue` vocabulary is retired.
 */
export interface RawInheritance {
  readonly role: "root" | "abstract-subtype" | "concrete-subtype";
  readonly strategy?: "table-per-hierarchy" | "table-per-concrete-subtype";
  readonly parent?: string;
  readonly tag?: { readonly column: string };
  readonly tagValue?: string;
}

/** A raw descriptor: either a single `entity` or an `entities` array. */
export type RawDescriptor =
  | { readonly entity: RawEntity }
  | { readonly entities: readonly RawEntity[] };

// --- normalized (fully-defaulted) shapes -----------------------------------

export type Temporal =
  | "non-temporal"
  | "unitemporal-processing"
  | "unitemporal-business"
  | "bitemporal";

/** A fully-defaulted attribute. */
export interface NormalizedAttribute {
  readonly name: string;
  readonly type: string;
  readonly column: string;
  readonly primaryKey: boolean;
  readonly nullable: boolean;
  readonly maxLength?: number;
  readonly readOnly: boolean;
  readonly optimisticLocking: boolean;
  readonly pkGenerator?: RawPkGenerator;
  readonly default?: unknown;
}

/** A fully-defaulted relationship (each `orderBy` key carries a `direction`). */
export interface NormalizedRelationship {
  readonly name: string;
  readonly relatedEntity: string;
  readonly cardinality: "one-to-one" | "many-to-one" | "one-to-many" | "many-to-many";
  readonly join: string;
  readonly reverseName?: string;
  readonly dependent: boolean;
  readonly foreignKey?: string;
  readonly orderBy: readonly { readonly attr: string; readonly direction: "asc" | "desc" }[];
}

/** A fully-defaulted index. */
export interface NormalizedIndex {
  readonly name: string;
  readonly attributes: readonly string[];
  readonly unique: boolean;
}

/** A fully-defaulted temporal dimension. */
export interface NormalizedAsOfAttribute {
  readonly name: string;
  readonly fromColumn: string;
  readonly toColumn: string;
  readonly axis: "processing" | "business";
  readonly toIsInclusive: boolean;
  readonly infinity: "infinity";
  readonly default: "now";
}

/** A fully-defaulted typed field of a value object (no per-field column). */
export interface NormalizedValueObjectAttribute {
  readonly name: string;
  readonly type: string;
  readonly nullable: boolean;
}

/**
 * A fully-defaulted value object nested inside another. It shares its top-level
 * ancestor's single structured-document column, so it carries no `column` /
 * `mapping`. Recursive: its own typed attributes, `one` / `many` cardinality,
 * and further-nested value objects to arbitrary depth.
 */
export interface NormalizedNestedValueObject {
  readonly name: string;
  readonly nullable: boolean;
  readonly cardinality: "one" | "many";
  readonly attributes: readonly NormalizedValueObjectAttribute[];
  readonly valueObjects: readonly NormalizedNestedValueObject[];
}

/**
 * A fully-defaulted top-level value object: the recursive nested shape PLUS the
 * single-column storage (`column` / `mapping`) only a top-level member carries.
 */
export interface NormalizedValueObject {
  readonly name: string;
  readonly column: string;
  readonly mapping: "json";
  readonly nullable: boolean;
  readonly cardinality: "one" | "many";
  readonly attributes: readonly NormalizedValueObjectAttribute[];
  readonly valueObjects: readonly NormalizedNestedValueObject[];
}

/** A fully-defaulted, temporal-classified entity. */
export interface NormalizedEntity {
  readonly name: string;
  readonly namespace?: string;
  readonly table: string;
  readonly mutability: "read-only" | "transactional";
  readonly temporal: Temporal;
  readonly attributes: readonly NormalizedAttribute[];
  readonly asOfAttributes: readonly NormalizedAsOfAttribute[];
  readonly relationships: readonly NormalizedRelationship[];
  readonly indices: readonly NormalizedIndex[];
  readonly valueObjects: readonly NormalizedValueObject[];
  readonly inheritance?: RawInheritance;
}

/** Lift a raw descriptor to a flat list of raw entities (single or many form). */
export function rawEntities(descriptor: RawDescriptor): readonly RawEntity[] {
  if ("entities" in descriptor) {
    return descriptor.entities;
  }
  return [descriptor.entity];
}

/** Derive the temporal classification from an entity's as-of attributes. */
export function deriveTemporal(asOf: readonly RawAsOfAttribute[]): Temporal {
  if (asOf.length === 0) {
    return "non-temporal";
  }
  if (asOf.length === 2) {
    return "bitemporal";
  }
  const axis = asOf[0]?.axis;
  return axis === "business" ? "unitemporal-business" : "unitemporal-processing";
}

function normalizeAttribute(raw: RawAttribute): NormalizedAttribute {
  return {
    name: raw.name,
    type: raw.type,
    column: raw.column,
    primaryKey: raw.primaryKey ?? false,
    nullable: raw.nullable ?? false,
    ...(raw.maxLength === undefined ? {} : { maxLength: raw.maxLength }),
    readOnly: raw.readOnly ?? false,
    optimisticLocking: raw.optimisticLocking ?? false,
    ...(raw.pkGenerator === undefined ? {} : { pkGenerator: raw.pkGenerator }),
    ...(raw.default === undefined ? {} : { default: raw.default }),
  };
}

function normalizeRelationship(raw: RawRelationship): NormalizedRelationship {
  return {
    name: raw.name,
    relatedEntity: raw.relatedEntity,
    cardinality: raw.cardinality,
    join: raw.join,
    ...(raw.reverseName === undefined ? {} : { reverseName: raw.reverseName }),
    dependent: raw.dependent ?? false,
    ...(raw.foreignKey === undefined ? {} : { foreignKey: raw.foreignKey }),
    orderBy: (raw.orderBy ?? []).map((key) => ({
      attr: key.attr,
      direction: key.direction ?? "asc",
    })),
  };
}

function normalizeIndex(raw: RawIndex): NormalizedIndex {
  return { name: raw.name, attributes: raw.attributes, unique: raw.unique ?? false };
}

function normalizeAsOf(raw: RawAsOfAttribute): NormalizedAsOfAttribute {
  return {
    name: raw.name,
    fromColumn: raw.fromColumn,
    toColumn: raw.toColumn,
    axis: raw.axis,
    toIsInclusive: raw.toIsInclusive ?? false,
    infinity: raw.infinity ?? "infinity",
    default: raw.default ?? "now",
  };
}

function normalizeValueObjectAttribute(
  raw: RawValueObjectAttribute,
): NormalizedValueObjectAttribute {
  return { name: raw.name, type: raw.type, nullable: raw.nullable ?? false };
}

function normalizeNestedValueObject(raw: RawNestedValueObject): NormalizedNestedValueObject {
  return {
    name: raw.name,
    nullable: raw.nullable ?? false,
    cardinality: raw.cardinality ?? "one",
    attributes: (raw.attributes ?? []).map(normalizeValueObjectAttribute),
    valueObjects: (raw.valueObjects ?? []).map(normalizeNestedValueObject),
  };
}

function normalizeValueObject(raw: RawValueObject): NormalizedValueObject {
  return {
    name: raw.name,
    column: raw.column,
    mapping: raw.mapping ?? "json",
    nullable: raw.nullable ?? false,
    cardinality: raw.cardinality ?? "one",
    attributes: (raw.attributes ?? []).map(normalizeValueObjectAttribute),
    valueObjects: (raw.valueObjects ?? []).map(normalizeNestedValueObject),
  };
}

/**
 * Fully default and temporal-classify a raw entity. The derived `temporal` is
 * checked against an explicit `temporal` field when present (the schema records
 * it for clarity); a mismatch is a descriptor error.
 */
export function normalizeEntity(raw: RawEntity): NormalizedEntity {
  const asOfAttributes = (raw.asOfAttributes ?? []).map(normalizeAsOf);
  const derived = deriveTemporal(raw.asOfAttributes ?? []);
  if (raw.temporal !== undefined && raw.temporal !== derived) {
    throw new Error(
      `entity '${raw.name}' declares temporal '${raw.temporal}' but its asOfAttributes derive '${derived}'`,
    );
  }
  // An inheritance node may omit `table` (an abstract root / abstract-subtype is
  // tableless) or `attributes` (a concrete subtype declaring only inherited
  // attributes); default them so the normalized view is total (m-inheritance,
  // resolved Q5). An abstract node's empty table surfaces as "".
  const attributes = raw.attributes ?? [];
  // Optimistic-lock composition (m-descriptor/m-temporal-read/m-opt-lock): a temporal (as-of) entity derives its
  // optimistic key from the processing-from column, so it MUST NOT also declare an
  // explicit `optimisticLocking` version attribute (the combination is invalid).
  if (attributes.some((a) => a.optimisticLocking) && (raw.asOfAttributes?.length ?? 0) > 0) {
    throw new Error(
      `entity '${raw.name}' combines an 'optimisticLocking' attribute with 'asOfAttributes'; ` +
        `a temporal entity derives its optimistic key from the processing-from column and MUST NOT ` +
        `declare a version attribute`,
    );
  }
  return {
    name: raw.name,
    ...(raw.namespace === undefined ? {} : { namespace: raw.namespace }),
    table: raw.table ?? "",
    mutability: raw.mutability ?? "read-only",
    temporal: derived,
    attributes: attributes.map(normalizeAttribute),
    asOfAttributes,
    relationships: (raw.relationships ?? []).map(normalizeRelationship),
    indices: (raw.indices ?? []).map(normalizeIndex),
    valueObjects: (raw.valueObjects ?? []).map(normalizeValueObject),
    ...(raw.inheritance === undefined ? {} : { inheritance: raw.inheritance }),
  };
}
