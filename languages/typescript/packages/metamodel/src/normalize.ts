/**
 * Defaulting / normalization for parsed model descriptors.
 *
 * A descriptor is authored sparsely: schema defaults (`nullable: false`,
 * `direction: asc`, conventional columns, …) are omitted in the YAML but are
 * part of the metamodel's meaning. The reader (`reader.ts`) presents the fully
 * defaulted operational view; this module is the one boundary that derives that
 * view from the canonical persisted descriptor vocabulary.
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
  readonly persistence?: "read-write" | "read-only";
  readonly attributes?: readonly RawAttribute[];
  readonly asOfAxes?: readonly RawAsOfAxis[];
  readonly relationships?: readonly RawRelationship[];
  readonly indices?: readonly RawIndex[];
  readonly valueObjects?: readonly RawValueObject[];
  readonly inheritance?: RawInheritance;
}

export interface RawAttribute {
  readonly name: string;
  readonly type: string;
  readonly column?: string;
  readonly primaryKey?: boolean;
  readonly nullable?: boolean;
  readonly maxLength?: number;
  readonly readOnly?: boolean;
  readonly optimisticLocking?: boolean;
  readonly pkGeneration?: RawPkGeneration;
  readonly default?: unknown;
}

export type RawPkGeneration =
  | "application-assigned"
  | "max"
  | {
      readonly strategy: "sequence";
      readonly name: string;
      readonly batchSize?: number;
      readonly initialValue?: number;
      readonly incrementSize?: number;
    };

export interface RawDefiningRelationship {
  readonly name: string;
  readonly cardinality: "one-to-one" | "many-to-one" | "one-to-many";
  readonly join: {
    readonly source: string;
    readonly target: { readonly entity: string; readonly attribute: string };
  };
  readonly dependent?: boolean;
  readonly orderBy?: readonly {
    readonly attribute: string;
    readonly direction?: "asc" | "desc";
  }[];
}

export interface RawReverseRelationship {
  readonly name: string;
  readonly reverseOf: string;
  readonly orderBy?: readonly {
    readonly attribute: string;
    readonly direction?: "asc" | "desc";
  }[];
}

export type RawRelationship = RawDefiningRelationship | RawReverseRelationship;

export interface RawIndex {
  readonly name: string;
  readonly attributes: readonly string[];
  readonly unique?: boolean;
}

export interface RawAsOfAxis {
  readonly dimension: "validTime" | "transactionTime";
  readonly startAttribute: string;
  readonly endAttribute: string;
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
 * attributes, its own `one` / `many` multiplicity, and further-nested value
 * objects to arbitrary depth.
 */
export interface RawNestedValueObject {
  readonly name: string;
  readonly nullable?: boolean;
  readonly multiplicity?: "one" | "many";
  readonly attributes?: readonly RawValueObjectAttribute[];
  readonly valueObjects?: readonly RawNestedValueObject[];
}

/**
 * A raw (as-parsed) top-level value object: the recursive nested shape PLUS the
 * optional conventional `column` storage only a top-level member carries.
 */
export interface RawValueObject {
  readonly name: string;
  readonly column?: string;
  readonly nullable?: boolean;
  readonly multiplicity?: "one" | "many";
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

export type Temporal = "non-temporal" | "transaction-time-only" | "bitemporal";

/** Existing operational PK-generation view derived from canonical `pkGeneration`. */
export type NormalizedPkGenerator =
  | "none"
  | "max"
  | {
      readonly strategy: "sequence";
      readonly sequenceName: string;
      readonly batchSize: number;
      readonly initialValue: number;
      readonly incrementSize: number;
    };

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
  readonly pkGenerator?: NormalizedPkGenerator;
  readonly default?: unknown;
}

export interface AttributeIdentity {
  readonly entity: string;
  readonly name: string;
}

export interface RelationshipIdentity {
  readonly entity: string;
  readonly name: string;
}

export interface RelationshipJoin {
  readonly source: AttributeIdentity;
  readonly target: AttributeIdentity;
}

export interface RelationshipOrder {
  readonly attribute: AttributeIdentity;
  readonly direction: "asc" | "desc";
}

export interface DefiningRelationshipDeclaration {
  readonly kind: "defining";
  readonly identity: RelationshipIdentity;
  readonly cardinality: "one-to-one" | "many-to-one" | "one-to-many";
  readonly join: RelationshipJoin;
  readonly dependent: boolean;
  readonly orderBy: readonly RelationshipOrder[];
}

export interface ReverseRelationshipDeclaration {
  readonly kind: "reverse";
  readonly identity: RelationshipIdentity;
  readonly reverseOf: RelationshipIdentity;
  readonly orderBy: readonly RelationshipOrder[];
}

export type RelationshipDeclaration =
  | DefiningRelationshipDeclaration
  | ReverseRelationshipDeclaration;

/** One directional relationship value compiled by the m-relationship facet. */
export interface RelationshipMetadata {
  readonly identity: RelationshipIdentity;
  readonly cardinality: "one-to-one" | "many-to-one" | "one-to-many";
  readonly join: RelationshipJoin;
  readonly reverse?: string;
  readonly dependent: boolean;
  readonly orderBy: readonly RelationshipOrder[];
}

/** A fully-defaulted index. */
export interface NormalizedIndex {
  readonly name: string;
  readonly attributes: readonly string[];
  readonly unique: boolean;
}

/** A fully-defaulted temporal dimension. */
export interface NormalizedAsOfAxis {
  readonly dimension: "validTime" | "transactionTime";
  readonly startColumn: string;
  readonly endColumn: string;
  readonly toIsInclusive: boolean;
  readonly infinity: "infinity";
  readonly default: "latest";
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
 * storage properties. Recursive: its own typed attributes, `one` / `many` multiplicity,
 * and further-nested value objects to arbitrary depth.
 */
export interface NormalizedNestedValueObject {
  readonly name: string;
  readonly nullable: boolean;
  readonly multiplicity: "one" | "many";
  readonly attributes: readonly NormalizedValueObjectAttribute[];
  readonly valueObjects: readonly NormalizedNestedValueObject[];
}

/**
 * A fully-defaulted top-level value object: the recursive nested shape plus the
 * single `column` storage location only a top-level member carries.
 */
export interface NormalizedValueObject {
  readonly name: string;
  readonly column: string;
  readonly nullable: boolean;
  readonly multiplicity: "one" | "many";
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
  readonly asOfAxes: readonly NormalizedAsOfAxis[];
  readonly relationships: readonly RelationshipDeclaration[];
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

/** Derive the existing operational temporal classification from canonical axes. */
export function deriveTemporal(axes: readonly RawAsOfAxis[]): Temporal {
  if (axes.length === 0) {
    return "non-temporal";
  }
  if (axes.length === 1 && axes[0]?.dimension === "transactionTime") {
    return "transaction-time-only";
  }
  if (
    axes.length === 2 &&
    axes[0]?.dimension === "validTime" &&
    axes[1]?.dimension === "transactionTime"
  ) {
    return "bitemporal";
  }
  throw new Error(
    "unsupported asOfAxes shape: expected transactionTime only or validTime followed by transactionTime",
  );
}

function normalizePkGeneration(raw: RawPkGeneration): NormalizedPkGenerator {
  if (raw === "application-assigned") {
    return "none";
  }
  if (raw === "max") {
    return "max";
  }
  return {
    strategy: "sequence",
    sequenceName: raw.name,
    batchSize: raw.batchSize ?? 1,
    initialValue: raw.initialValue ?? 1,
    incrementSize: raw.incrementSize ?? 1,
  };
}

function normalizeAttribute(raw: RawAttribute): NormalizedAttribute {
  const primaryKey = raw.primaryKey ?? false;
  const generation =
    raw.pkGeneration === undefined
      ? primaryKey
        ? "none"
        : undefined
      : normalizePkGeneration(raw.pkGeneration);
  return {
    name: raw.name,
    type: raw.type,
    column: raw.column ?? raw.name,
    primaryKey,
    nullable: raw.nullable ?? false,
    ...(raw.maxLength === undefined ? {} : { maxLength: raw.maxLength }),
    readOnly: raw.readOnly ?? false,
    optimisticLocking: raw.optimisticLocking ?? false,
    ...(generation === undefined ? {} : { pkGenerator: generation }),
    ...(raw.default === undefined ? {} : { default: raw.default }),
  };
}

function canonicalEntityName(entity: RawEntity): string {
  return entity.namespace === undefined ? entity.name : `${entity.namespace}.${entity.name}`;
}

function resolveEntityReference(
  owner: RawEntity,
  reference: string,
  entities: readonly RawEntity[],
): RawEntity {
  const canonical = reference.includes(".")
    ? reference
    : owner.namespace === undefined
      ? reference
      : `${owner.namespace}.${reference}`;
  const target = entities.find((entity) => canonicalEntityName(entity) === canonical);
  if (target === undefined) {
    throw new Error(
      `entity '${canonicalEntityName(owner)}' references unknown entity '${reference}'`,
    );
  }
  return target;
}

function effectivePersistence(
  entity: RawEntity,
  entities: readonly RawEntity[],
  seen: ReadonlySet<RawEntity> = new Set(),
): "read-write" | "read-only" {
  if (entity.persistence !== undefined) {
    return entity.persistence;
  }
  const parentName = entity.inheritance?.parent;
  if (parentName === undefined || seen.has(entity)) {
    return "read-write";
  }
  const parent = (() => {
    try {
      return resolveEntityReference(entity, parentName, entities);
    } catch {
      // Invalid families are diagnosed by m-model-formation. Keep this input
      // adapter total enough for that validator to inspect the whole candidate.
      return undefined;
    }
  })();
  if (parent === undefined) {
    return "read-write";
  }
  return effectivePersistence(parent, entities, new Set([...seen, entity]));
}

function splitReverseOf(reverseOf: string): { entity: string; relationship: string } {
  const split = reverseOf.lastIndexOf(".");
  if (split <= 0 || split === reverseOf.length - 1) {
    throw new Error(`invalid reverseOf '${reverseOf}' (expected '<entity>.<relationship>')`);
  }
  return { entity: reverseOf.slice(0, split), relationship: reverseOf.slice(split + 1) };
}

function normalizeOrderBy(
  orderBy: RawRelationship["orderBy"],
  targetEntity: string,
): readonly RelationshipOrder[] {
  return (orderBy ?? []).map((key) => ({
    attribute: { entity: targetEntity, name: key.attribute },
    direction: key.direction ?? "asc",
  }));
}

function normalizeDefiningRelationship(
  owner: RawEntity,
  raw: RawDefiningRelationship,
  entities: readonly RawEntity[],
): DefiningRelationshipDeclaration {
  const sourceEntity = canonicalEntityName(owner);
  const target = resolveEntityReference(owner, raw.join.target.entity, entities);
  const targetEntity = canonicalEntityName(target);
  return {
    kind: "defining",
    identity: { entity: sourceEntity, name: raw.name },
    cardinality: raw.cardinality,
    join: {
      source: { entity: sourceEntity, name: raw.join.source },
      target: { entity: targetEntity, name: raw.join.target.attribute },
    },
    dependent: raw.dependent ?? false,
    orderBy: normalizeOrderBy(raw.orderBy, targetEntity),
  };
}

function normalizeReverseRelationship(
  owner: RawEntity,
  raw: RawReverseRelationship,
  entities: readonly RawEntity[],
): ReverseRelationshipDeclaration {
  const reference = splitReverseOf(raw.reverseOf);
  const definingOwner = resolveEntityReference(owner, reference.entity, entities);
  const targetEntity = canonicalEntityName(definingOwner);
  return {
    kind: "reverse",
    identity: { entity: canonicalEntityName(owner), name: raw.name },
    reverseOf: { entity: targetEntity, name: reference.relationship },
    orderBy: normalizeOrderBy(raw.orderBy, targetEntity),
  };
}

function normalizeRelationship(
  owner: RawEntity,
  raw: RawRelationship,
  entities: readonly RawEntity[],
): RelationshipDeclaration {
  return "reverseOf" in raw
    ? normalizeReverseRelationship(owner, raw, entities)
    : normalizeDefiningRelationship(owner, raw, entities);
}

function normalizeIndex(raw: RawIndex): NormalizedIndex {
  return { name: raw.name, attributes: raw.attributes, unique: raw.unique ?? false };
}

function normalizeAsOf(raw: RawAsOfAxis, attributes: readonly RawAttribute[]): NormalizedAsOfAxis {
  const start = attributes.find((attribute) => attribute.name === raw.startAttribute);
  const end = attributes.find((attribute) => attribute.name === raw.endAttribute);
  if (start === undefined || end === undefined) {
    throw new Error(
      `asOfAxis '${raw.dimension}' references unknown attributes ` +
        `'${raw.startAttribute}'/'${raw.endAttribute}'`,
    );
  }
  return {
    dimension: raw.dimension,
    startColumn: start.column ?? start.name,
    endColumn: end.column ?? end.name,
    toIsInclusive: false,
    infinity: "infinity",
    default: "latest",
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
    multiplicity: raw.multiplicity ?? "one",
    attributes: (raw.attributes ?? []).map(normalizeValueObjectAttribute),
    valueObjects: (raw.valueObjects ?? []).map(normalizeNestedValueObject),
  };
}

function normalizeValueObject(raw: RawValueObject): NormalizedValueObject {
  return {
    name: raw.name,
    column: raw.column ?? raw.name,
    nullable: raw.nullable ?? false,
    multiplicity: raw.multiplicity ?? "one",
    attributes: (raw.attributes ?? []).map(normalizeValueObjectAttribute),
    valueObjects: (raw.valueObjects ?? []).map(normalizeNestedValueObject),
  };
}

/**
 * Fully default and temporal-classify one canonical raw entity. Whole-model
 * context is used only to resolve the closed defining/reverse relationship form.
 */
export function normalizeEntity(
  raw: RawEntity,
  entities: readonly RawEntity[] = [raw],
): NormalizedEntity {
  // An inheritance node may omit `table` (an abstract root / abstract-subtype is
  // tableless) or `attributes` (a concrete subtype declaring only inherited
  // attributes); default them so the normalized view is total (m-inheritance,
  // resolved Q5). An abstract node's empty table surfaces as "".
  const attributes = raw.attributes ?? [];
  const asOfAxes = (raw.asOfAxes ?? []).map((axis) => normalizeAsOf(axis, attributes));
  const derived = deriveTemporal(raw.asOfAxes ?? []);
  // Optimistic-lock composition (m-descriptor/m-temporal-read/m-opt-lock): a temporal (as-of) entity derives its
  // optimistic key from the Transaction-Time start column, so it MUST NOT also declare an
  // explicit `optimisticLocking` version attribute (the combination is invalid).
  if (attributes.some((a) => a.optimisticLocking) && (raw.asOfAxes?.length ?? 0) > 0) {
    throw new Error(
      `entity '${raw.name}' combines an 'optimisticLocking' attribute with 'asOfAxes'; ` +
        `a temporal entity derives its optimistic key from the Transaction-Time start column and MUST NOT ` +
        `declare a version attribute`,
    );
  }
  return {
    name: raw.name,
    ...(raw.namespace === undefined ? {} : { namespace: raw.namespace }),
    table: raw.table ?? "",
    mutability:
      effectivePersistence(raw, entities) === "read-write" ? "transactional" : "read-only",
    temporal: derived,
    attributes: attributes.map(normalizeAttribute),
    asOfAxes,
    relationships: (raw.relationships ?? []).map((relationship) =>
      normalizeRelationship(raw, relationship, entities),
    ),
    indices: (raw.indices ?? []).map(normalizeIndex),
    valueObjects: (raw.valueObjects ?? []).map(normalizeValueObject),
    ...(raw.inheritance === undefined ? {} : { inheritance: raw.inheritance }),
  };
}

/**
 * Normalize canonical declarations without compiling module-owned semantic facets.
 */
export function normalizeEntities(descriptor: RawDescriptor): readonly NormalizedEntity[] {
  const entities = rawEntities(descriptor);
  return entities.map((entity) => normalizeEntity(entity, entities));
}
