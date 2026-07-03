/**
 * M1 generic metamodel reader — introspection over a parsed descriptor with no
 * generated symbols.
 *
 * This is the conformance backbone (ADR-0055): the adapter reads arbitrary
 * corpus descriptors and the generated typed layer (Phase 9) delegates to it.
 * `Metamodel.entity(name)` yields an `EntityMetadata` over the *fully defaulted*
 * normalized view (`normalize.ts`), exposing `attributes`, `attributeByName`,
 * `asOfAttributes`, `relationships`, and `table` — schema defaults surfaced.
 *
 * Descriptors are ajv-validated against `metamodel.schema.json` on read, so a
 * malformed descriptor fails fast rather than producing a half-formed reader.
 */
import {
  type NormalizedAsOfAttribute,
  type NormalizedAttribute,
  type NormalizedEntity,
  type NormalizedIndex,
  type NormalizedRelationship,
  type NormalizedValueObject,
  normalizeEntity,
  type RawDescriptor,
  rawEntities,
} from "./normalize.js";
import { assertValidDescriptor } from "./schema.js";

/**
 * Introspection facade over one entity's fully-defaulted metadata. The typed
 * `Order.*` symbols generated in Phase 9 delegate to this same layer.
 */
export class EntityMetadata {
  constructor(private readonly entity: NormalizedEntity) {}

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

  /** The single `optimisticLocking` version attribute, if declared (M10). */
  versionAttribute(): NormalizedAttribute | undefined {
    return this.entity.attributes.find((attr) => attr.optimisticLocking);
  }

  /**
   * The processing-axis `from` attribute (`in_z`), if this entity has a processing
   * axis. This is the DERIVED optimistic key for a processing-axis temporal entity
   * (M7/M10): a temporal entity carries no version column, so the observed
   * processing-from value is the optimistic-lock version analogue an optimistic
   * close gates on. `undefined` for a non-temporal or business-only entity.
   */
  processingFromAttribute(): NormalizedAttribute | undefined {
    const processing = this.entity.asOfAttributes.find((axis) => axis.axis === "processing");
    if (processing === undefined) {
      return undefined;
    }
    return this.entity.attributes.find((attr) => attr.column === processing.fromColumn);
  }

  /** The temporal dimensions (one for unitemporal, two for bitemporal). */
  asOfAttributes(): readonly NormalizedAsOfAttribute[] {
    return this.entity.asOfAttributes;
  }

  /** Look up a temporal dimension by name; throws if absent. */
  asOfAttributeByName(name: string): NormalizedAsOfAttribute {
    const found = this.entity.asOfAttributes.find((axis) => axis.name === name);
    if (!found) {
      throw new Error(`entity '${this.entity.name}' has no asOfAttribute '${name}'`);
    }
    return found;
  }

  /** All relationships, in declaration order. */
  relationships(): readonly NormalizedRelationship[] {
    return this.entity.relationships;
  }

  /** Look up a relationship by name; throws if absent. */
  relationshipByName(name: string): NormalizedRelationship {
    const found = this.entity.relationships.find((rel) => rel.name === name);
    if (!found) {
      throw new Error(`entity '${this.entity.name}' has no relationship '${name}'`);
    }
    return found;
  }

  /** All declared indices. */
  indices(): readonly NormalizedIndex[] {
    return this.entity.indices;
  }

  /** All declared value objects. */
  valueObjects(): readonly NormalizedValueObject[] {
    return this.entity.valueObjects;
  }

  /** Look up a value object by name; `undefined` if absent. */
  findValueObject(name: string): NormalizedValueObject | undefined {
    return this.entity.valueObjects.find((vo) => vo.name === name);
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

  private constructor(entities: readonly NormalizedEntity[]) {
    this.byName = new Map(entities.map((e) => [e.name, new EntityMetadata(e)]));
  }

  /**
   * Build a metamodel from a parsed descriptor, ajv-validating it against
   * `metamodel.schema.json` and normalizing every entity (defaults surfaced,
   * temporal classification derived).
   */
  static fromDescriptor(descriptor: unknown): Metamodel {
    assertValidDescriptor(descriptor);
    const entities = rawEntities(descriptor as RawDescriptor).map(normalizeEntity);
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
    return [...this.byName.keys()];
  }

  /** All entities, in declaration order. */
  entities(): readonly EntityMetadata[] {
    return [...this.byName.values()];
  }
}
