/**
 * m-descriptor generic metamodel reader — introspection over a parsed descriptor with no
 * generated symbols.
 *
 * This is the conformance backbone (ADR-0008): the adapter reads arbitrary
 * corpus descriptors and the generated typed layer (Phase 9) delegates to it.
 * `Metamodel.entity(name)` yields an `EntityMetadata` over the *fully defaulted*
 * normalized view (`normalize.ts`), exposing `attributes`, `attributeByName`,
 * `asOfAxes`, `relationships`, and `table` — schema defaults surfaced.
 *
 * Descriptors are ajv-validated against `metamodel.schema.json` on read, so a
 * malformed descriptor fails fast rather than producing a half-formed reader.
 */
import {
  type DefiningRelationshipDeclaration,
  type NormalizedAsOfAxis,
  type NormalizedAttribute,
  type NormalizedEntity,
  type NormalizedIndex,
  type NormalizedNestedValueObject,
  type NormalizedValueObject,
  type NormalizedValueObjectAttribute,
  normalizeEntities,
  type RawDescriptor,
  type RelationshipDeclaration,
  type RelationshipIdentity,
  type RelationshipMetadata,
  type ReverseRelationshipDeclaration,
} from "./normalize.js";
import { assertValidDescriptor } from "./schema.js";

/**
 * The recursive members a value object (top-level or nested) exposes: its own
 * `multiplicity`, typed `attributes`, and further-nested `valueObjects`. Both a
 * top-level `NormalizedValueObject` and a `NormalizedNestedValueObject` satisfy
 * it, so the free accessors below traverse either without caring which is the
 * storage-carrying root.
 */
export type NormalizedValueObjectMember = NormalizedValueObject | NormalizedNestedValueObject;

/** Look up a nested value object by name within a value-object member; `undefined` if absent. */
export function findNestedValueObject(
  member: NormalizedValueObjectMember,
  name: string,
): NormalizedNestedValueObject | undefined {
  return member.valueObjects.find((vo) => vo.name === name);
}

/** Look up a typed attribute by name within a value-object member; `undefined` if absent. */
export function findValueObjectAttribute(
  member: NormalizedValueObjectMember,
  name: string,
): NormalizedValueObjectAttribute | undefined {
  return member.attributes.find((attr) => attr.name === name);
}

function relationshipKey(identity: RelationshipIdentity): string {
  return `${identity.entity}#${identity.name}`;
}

function invertCardinality(
  cardinality: DefiningRelationshipDeclaration["cardinality"],
): DefiningRelationshipDeclaration["cardinality"] {
  if (cardinality === "one-to-many") {
    return "many-to-one";
  }
  if (cardinality === "many-to-one") {
    return "one-to-many";
  }
  return "one-to-one";
}

/** Immutable directional relationship semantics compiled from local declarations. */
export class RelationshipFacet {
  private readonly byIdentity: ReadonlyMap<string, RelationshipMetadata>;
  private readonly byEntity: ReadonlyMap<string, readonly RelationshipMetadata[]>;

  constructor(entities: readonly NormalizedEntity[]) {
    const declarations = entities.flatMap((entity) => [...entity.relationships]);
    const declarationsByIdentity = new Map(
      declarations.map((declaration) => [relationshipKey(declaration.identity), declaration]),
    );
    const metadata = declarations.map((declaration) =>
      this.compile(declaration, declarations, declarationsByIdentity),
    );
    this.byIdentity = new Map(
      metadata.map((relationship) => [relationshipKey(relationship.identity), relationship]),
    );
    const byEntity = new Map<string, RelationshipMetadata[]>();
    for (const relationship of metadata) {
      const current = byEntity.get(relationship.identity.entity) ?? [];
      current.push(relationship);
      byEntity.set(relationship.identity.entity, current);
    }
    this.byEntity = byEntity;
  }

  relationship(identity: RelationshipIdentity): RelationshipMetadata | undefined {
    return this.byIdentity.get(relationshipKey(identity));
  }

  relationships(entity: string): readonly RelationshipMetadata[] {
    return this.byEntity.get(entity) ?? [];
  }

  private compile(
    declaration: RelationshipDeclaration,
    declarations: readonly RelationshipDeclaration[],
    declarationsByIdentity: ReadonlyMap<string, RelationshipDeclaration>,
  ): RelationshipMetadata {
    if (declaration.kind === "defining") {
      const reverse = declarations.find(
        (candidate): candidate is ReverseRelationshipDeclaration =>
          candidate.kind === "reverse" &&
          relationshipKey(candidate.reverseOf) === relationshipKey(declaration.identity),
      );
      return {
        identity: declaration.identity,
        cardinality: declaration.cardinality,
        join: declaration.join,
        ...(reverse === undefined ? {} : { reverse: reverse.identity.name }),
        dependent: declaration.dependent,
        orderBy: declaration.orderBy,
      };
    }

    const defining = declarationsByIdentity.get(relationshipKey(declaration.reverseOf));
    if (defining === undefined || defining.kind !== "defining") {
      throw new Error(
        `relationship '${declaration.identity.entity}.${declaration.identity.name}' reverses ` +
          `missing defining relationship '${declaration.reverseOf.entity}.${declaration.reverseOf.name}'`,
      );
    }
    if (defining.join.target.entity !== declaration.identity.entity) {
      throw new Error(
        `reverse relationship '${declaration.identity.entity}.${declaration.identity.name}' ` +
          `is not the target of '${defining.identity.entity}.${defining.identity.name}'`,
      );
    }
    return {
      identity: declaration.identity,
      cardinality: invertCardinality(defining.cardinality),
      join: { source: defining.join.target, target: defining.join.source },
      reverse: defining.identity.name,
      dependent: false,
      orderBy: declaration.orderBy,
    };
  }
}

/**
 * Introspection facade over one entity's fully-defaulted metadata. The typed
 * `Order.*` symbols generated in Phase 9 delegate to this same layer.
 */
export class EntityMetadata {
  constructor(
    private readonly entity: NormalizedEntity,
    private readonly relationshipFacet: RelationshipFacet,
  ) {}

  /** The domain class name (e.g. `"Order"`). */
  get name(): string {
    return this.entity.name;
  }

  /** The logical namespace, if declared. */
  get namespace(): string | undefined {
    return this.entity.namespace;
  }

  /** The mapped table name (e.g. `"orders"`). */
  get table(): string {
    return this.entity.table;
  }

  /** `read-only` (default) or `transactional`. */
  get mutability(): "read-only" | "transactional" {
    return this.entity.mutability;
  }

  /** The derived temporal classification. */
  get temporal(): NormalizedEntity["temporal"] {
    return this.entity.temporal;
  }

  /** The inheritance mapping, if this entity participates in a hierarchy. */
  get inheritance(): NormalizedEntity["inheritance"] {
    return this.entity.inheritance;
  }

  /** All attributes, in declaration order. */
  attributes(): readonly NormalizedAttribute[] {
    return this.entity.attributes;
  }

  /** Look up an attribute by name; throws if absent. */
  attributeByName(name: string): NormalizedAttribute {
    const found = this.entity.attributes.find((attr) => attr.name === name);
    if (!found) {
      throw new Error(`entity '${this.entity.name}' has no attribute '${name}'`);
    }
    return found;
  }

  /** Look up an attribute by name; `undefined` if absent. */
  findAttribute(name: string): NormalizedAttribute | undefined {
    return this.entity.attributes.find((attr) => attr.name === name);
  }

  /** The primary-key attributes (the entity's logical key), in declaration order. */
  primaryKey(): readonly NormalizedAttribute[] {
    return this.entity.attributes.filter((attr) => attr.primaryKey);
  }

  /** The single `optimisticLocking` version attribute, if declared (m-opt-lock). */
  versionAttribute(): NormalizedAttribute | undefined {
    return this.entity.attributes.find((attr) => attr.optimisticLocking);
  }

  /**
   * The Transaction-Time start attribute (`in_z`), if this entity has that
   * dimension. This is the derived optimistic key for a Transaction-Time entity
   * (m-temporal-read/m-opt-lock): a temporal entity carries no version column, so the observed
   * Transaction-Time start value is the optimistic-lock version analogue an optimistic
   * close gates on. `undefined` for a non-temporal entity.
   */
  txStartAttribute(): NormalizedAttribute | undefined {
    const transactionTime = this.entity.asOfAxes.find(
      (axis) => axis.dimension === "transactionTime",
    );
    if (transactionTime === undefined) {
      return undefined;
    }
    return this.entity.attributes.find((attr) => attr.column === transactionTime.startColumn);
  }

  /**
   * The Transaction-Time end attribute (`out_z`), if this entity has that
   * dimension. This is the Latest-milestone marker for a Transaction-Time entity
   * (m-temporal-read/m-opt-lock): the Latest row is the one whose end is `infinity` (the
   * open upper bound). Recording the observed start filters on this so a
   * multi-milestone as-of/history read does not overwrite the current observation
   * with a closed milestone's `in_z`. `undefined` for a non-temporal
   * entity.
   */
  txEndAttribute(): NormalizedAttribute | undefined {
    const transactionTime = this.entity.asOfAxes.find(
      (axis) => axis.dimension === "transactionTime",
    );
    if (transactionTime === undefined) {
      return undefined;
    }
    return this.entity.attributes.find((attr) => attr.column === transactionTime.endColumn);
  }

  /** The temporal dimensions (one for unitemporal, two for bitemporal). */
  asOfAxes(): readonly NormalizedAsOfAxis[] {
    return this.entity.asOfAxes;
  }

  /** Look up a temporal dimension; throws if absent. */
  asOfAxis(dimension: NormalizedAsOfAxis["dimension"]): NormalizedAsOfAxis {
    const found = this.entity.asOfAxes.find((axis) => axis.dimension === dimension);
    if (!found) {
      throw new Error(`entity '${this.entity.name}' has no temporal dimension '${dimension}'`);
    }
    return found;
  }

  /** Local defining/reverse declarations, in authoring order. */
  relationshipDeclarations(): readonly RelationshipDeclaration[] {
    return this.entity.relationships;
  }

  /** Directional relationship semantics compiled by the Relationship Facet. */
  relationships(): readonly RelationshipMetadata[] {
    return this.relationshipFacet.relationships(this.canonicalName);
  }

  /** Look up a relationship by name; throws if absent. */
  relationshipByName(name: string): RelationshipMetadata {
    const found = this.relationshipFacet.relationship({ entity: this.canonicalName, name });
    if (!found) {
      throw new Error(`entity '${this.entity.name}' has no relationship '${name}'`);
    }
    return found;
  }

  private get canonicalName(): string {
    return this.entity.namespace === undefined
      ? this.entity.name
      : `${this.entity.namespace}.${this.entity.name}`;
  }

  /** All declared indices. */
  indices(): readonly NormalizedIndex[] {
    return this.entity.indices;
  }

  /** All declared value objects. */
  valueObjects(): readonly NormalizedValueObject[] {
    return this.entity.valueObjects;
  }

  /** Look up a top-level value object by name; `undefined` if absent. */
  findValueObject(name: string): NormalizedValueObject | undefined {
    return this.entity.valueObjects.find((vo) => vo.name === name);
  }

  /** Look up a top-level value object by name; throws if absent. */
  valueObjectByName(name: string): NormalizedValueObject {
    const found = this.findValueObject(name);
    if (!found) {
      throw new Error(`entity '${this.entity.name}' has no value object '${name}'`);
    }
    return found;
  }

  /**
   * Resolve a value-object member path relative to this entity: the first
   * segment names a top-level value object, each further segment a nested value
   * object declared on the preceding member (to arbitrary depth). Returns the
   * resolved member (whose `multiplicity` / `attributes` / nested `valueObjects`
   * are then readable) or `undefined` if any segment is unresolved. An empty
   * path resolves to `undefined`.
   */
  resolveValueObjectPath(segments: readonly string[]): NormalizedValueObjectMember | undefined {
    const [head, ...rest] = segments;
    if (head === undefined) {
      return undefined;
    }
    let member: NormalizedValueObjectMember | undefined = this.findValueObject(head);
    for (const segment of rest) {
      if (member === undefined) {
        return undefined;
      }
      member = findNestedValueObject(member, segment);
    }
    return member;
  }

  /** The fully-defaulted normalized entity, for callers that need the record. */
  get normalized(): NormalizedEntity {
    return this.entity;
  }
}

/**
 * A metamodel: the set of entities a single descriptor declares. Resolves both
 * the single-`entity` and multi-`entities` descriptor forms.
 */
export class Metamodel {
  private readonly byName: Map<string, EntityMetadata>;
  private readonly ordered: readonly EntityMetadata[];

  private constructor(entities: readonly NormalizedEntity[]) {
    const relationshipFacet = new RelationshipFacet(entities);
    this.ordered = entities.map((entity) => new EntityMetadata(entity, relationshipFacet));
    this.byName = new Map(
      this.ordered.map((entity) => [
        entity.namespace === undefined ? entity.name : `${entity.namespace}.${entity.name}`,
        entity,
      ]),
    );
    const localCounts = new Map<string, number>();
    for (const entity of this.ordered) {
      localCounts.set(entity.name, (localCounts.get(entity.name) ?? 0) + 1);
    }
    for (const entity of this.ordered) {
      if (localCounts.get(entity.name) === 1) {
        this.byName.set(entity.name, entity);
      }
    }
  }

  /**
   * Build a metamodel from a parsed descriptor, ajv-validating it against
   * `metamodel.schema.json` and normalizing every entity (defaults surfaced,
   * temporal classification derived).
   */
  static fromDescriptor(descriptor: unknown): Metamodel {
    assertValidDescriptor(descriptor);
    const entities = normalizeEntities(descriptor as RawDescriptor);
    return new Metamodel(entities);
  }

  /** Look up an entity by name; throws if absent. */
  entity(name: string): EntityMetadata {
    const found = this.byName.get(name);
    if (!found) {
      throw new Error(`metamodel has no entity '${name}'`);
    }
    return found;
  }

  /** Look up an entity by name; `undefined` if absent. */
  findEntity(name: string): EntityMetadata | undefined {
    return this.byName.get(name);
  }

  /** All entity names declared in the descriptor. */
  entityNames(): readonly string[] {
    return this.ordered.map((entity) =>
      entity.namespace === undefined ? entity.name : `${entity.namespace}.${entity.name}`,
    );
  }

  /** All entities, in declaration order. */
  entities(): readonly EntityMetadata[] {
    return this.ordered;
  }
}
