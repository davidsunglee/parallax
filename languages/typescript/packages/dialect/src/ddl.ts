/**
 * Derive `CREATE TABLE` DDL from a parsed model descriptor (M0 type → Postgres
 * column type, behind the M11 seam). The database schema is never authored by
 * hand — it is a pure function of the metamodel, exactly as a real
 * implementation's would be (mirrors the harness `ddl_builder`).
 *
 * `@parallax/dialect` reads descriptors as plain JSON-compatible data rather than
 * importing `@parallax/metamodel` (which would create a `dialect → metamodel`
 * edge the DAG forbids). The shapes here are the minimal physical view the DDL
 * needs; the metamodel reader normalizes the same descriptor for the query path.
 */
import { postgresColumnType, quoteIdentifier } from "./postgres.js";

/** The minimal attribute view DDL derivation needs. */
interface DdlAttribute {
  readonly type: string;
  readonly column: string;
  readonly primaryKey?: boolean;
  readonly nullable?: boolean;
  readonly maxLength?: number;
}

/** A temporal dimension contributes its `fromColumn` to the physical key. */
interface DdlAsOfAttribute {
  readonly fromColumn: string;
}

/** The minimal entity view DDL derivation needs. */
interface DdlEntity {
  readonly table: string;
  readonly attributes: readonly DdlAttribute[];
  readonly asOfAttributes?: readonly DdlAsOfAttribute[];
}

/** A descriptor is either a single `entity` or an `entities` array. */
type DdlDescriptor = { readonly entity: DdlEntity } | { readonly entities: readonly DdlEntity[] };

/** Lift a descriptor to a flat entity list (single- or multi-entity form). */
function entitiesOf(descriptor: DdlDescriptor): readonly DdlEntity[] {
  return "entities" in descriptor ? descriptor.entities : [descriptor.entity];
}

/** Build the `CREATE TABLE` statement for one entity. */
function createTable(entity: DdlEntity): string {
  const columns: string[] = [];
  const pkColumns: string[] = [];

  for (const attr of entity.attributes) {
    const columnType = postgresColumnType(attr.type, attr.maxLength);
    const parts = [quoteIdentifier(attr.column), columnType];
    if (!attr.nullable) {
      parts.push("not null");
    }
    columns.push(parts.join(" "));
    if (attr.primaryKey) {
      pkColumns.push(attr.column);
    }
  }

  // A temporal entity keeps many milestone rows per business key, so the
  // declared PK is not unique on its own — the physical key is the business key
  // PLUS each as-of dimension's `fromColumn` (the milestone start), so the DDL
  // admits the milestone chain (M7). No-op for non-temporal entities.
  for (const asOf of entity.asOfAttributes ?? []) {
    if (!pkColumns.includes(asOf.fromColumn)) {
      pkColumns.push(asOf.fromColumn);
    }
  }

  if (pkColumns.length > 0) {
    const quoted = pkColumns.map(quoteIdentifier).join(", ");
    columns.push(`primary key (${quoted})`);
  }

  const columnClause = columns.join(",\n  ");
  return `create table ${quoteIdentifier(entity.table)} (\n  ${columnClause}\n)`;
}

/**
 * Return the ordered DDL statements that create every entity's table — one
 * `CREATE TABLE` per **distinct table**. Foreign keys are intentionally omitted:
 * relationships are a query concern, and leaving FK constraints out keeps the
 * fixture-load order unconstrained (mirrors the harness).
 */
export function ddlForDescriptor(descriptor: unknown): readonly string[] {
  const byTable = new Map<string, DdlEntity>();
  for (const entity of entitiesOf(descriptor as DdlDescriptor)) {
    // First entity wins per table; a table-per-hierarchy union is a later phase.
    if (!byTable.has(entity.table)) {
      byTable.set(entity.table, entity);
    }
  }
  return [...byTable.values()].map(createTable);
}

/**
 * The descriptor's physical column order for an entity's table (matches the DDL
 * and the fixture-load order), so fixture loading and table-state reads stay
 * column-aligned.
 */
export function columnOrder(entity: DdlEntity): readonly string[] {
  return entity.attributes.map((attr) => attr.column);
}
