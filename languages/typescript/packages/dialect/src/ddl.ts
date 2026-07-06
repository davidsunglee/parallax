/**
 * Derive `CREATE TABLE` DDL from a parsed model descriptor (m-core type → the
 * injected dialect's column type, behind the m-dialect seam). The database schema is
 * never authored by hand — it is a pure function of the metamodel, exactly as a
 * real implementation's would be (mirrors the harness `ddl_builder`).
 *
 * The create-table *algorithm* — column list, PK + temporal-key derivation,
 * dedup-by-table — is shared across dialects; only the primitives diverge, so the
 * derivation is a free function parameterized by a {@link Dialect} that consults
 * `dialect.columnType` / `dialect.quoteIdentifier` (design decision "DDL
 * derivation: free function parameterized by a `Dialect`"). It defaults to
 * `postgresDialect`, so every existing caller stays byte-identical while a MariaDB
 * caller passes `mariadbDialect` to get `datetime(6)` / `tinyint(1)` / backtick
 * quoting.
 *
 * `@parallax/dialect` reads descriptors as plain JSON-compatible data rather than
 * importing `@parallax/metamodel` (which would create a `dialect → metamodel`
 * edge the DAG forbids). The shapes here are the minimal physical view the DDL
 * needs; the metamodel reader normalizes the same descriptor for the query path.
 */
import type { Dialect } from "./dialect.js";
import { postgresDialect } from "./postgres.js";

/** The minimal attribute view DDL derivation needs. */
interface DdlAttribute {
  readonly name?: string;
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

/** A declared index (its attribute-name references + whether it is unique). */
interface DdlIndex {
  readonly attributes: readonly string[];
  readonly unique?: boolean;
}

/** The minimal entity view DDL derivation needs. */
interface DdlEntity {
  readonly table: string;
  readonly attributes: readonly DdlAttribute[];
  readonly asOfAttributes?: readonly DdlAsOfAttribute[];
  readonly indices?: readonly DdlIndex[];
}

/** A descriptor is either a single `entity` or an `entities` array. */
type DdlDescriptor = { readonly entity: DdlEntity } | { readonly entities: readonly DdlEntity[] };

/** Lift a descriptor to a flat entity list (single- or multi-entity form). */
function entitiesOf(descriptor: DdlDescriptor): readonly DdlEntity[] {
  return "entities" in descriptor ? descriptor.entities : [descriptor.entity];
}

/** Build the `CREATE TABLE` statement for one entity, using the dialect primitives. */
function createTable(entity: DdlEntity, dialect: Dialect): string {
  const columns: string[] = [];
  const pkColumns: string[] = [];

  for (const attr of entity.attributes) {
    const columnType = dialect.columnType(attr.type, attr.maxLength);
    const parts = [dialect.quoteIdentifier(attr.column), columnType];
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
  // admits the milestone chain (m-temporal-read). No-op for non-temporal entities.
  for (const asOf of entity.asOfAttributes ?? []) {
    if (!pkColumns.includes(asOf.fromColumn)) {
      pkColumns.push(asOf.fromColumn);
    }
  }

  // Emit a UNIQUE constraint for each declared unique index whose columns are NOT
  // exactly the physical primary key (the PK is already unique via `primary key
  // (...)` below). This lets a model witness a unique-INDEX violation distinct from
  // a PK collision (m-db-error error classification — `tag_name_uq`); existing slice models
  // declare only PK-backed unique indices, so this is a no-op for them. The
  // comparison is against the PHYSICAL primary key (declared PK + temporal
  // fromColumns appended above), so a temporal full-milestone-key unique index is
  // recognized as PK-backed and not re-emitted.
  const columnByAttr = new Map(
    entity.attributes.map((attr) => [attr.name ?? attr.column, attr.column]),
  );
  const pkColumnSet = new Set(pkColumns);
  for (const index of entity.indices ?? []) {
    if (!index.unique) {
      continue;
    }
    const indexColumns = index.attributes.map((attr) => columnByAttr.get(attr) ?? attr);
    const sameAsPk =
      indexColumns.length === pkColumnSet.size && indexColumns.every((c) => pkColumnSet.has(c));
    if (sameAsPk) {
      continue;
    }
    const quoted = indexColumns.map((column) => dialect.quoteIdentifier(column)).join(", ");
    columns.push(`unique (${quoted})`);
  }

  if (pkColumns.length > 0) {
    const quoted = pkColumns.map((column) => dialect.quoteIdentifier(column)).join(", ");
    columns.push(`primary key (${quoted})`);
  }

  const columnClause = columns.join(",\n  ");
  return `create table ${dialect.quoteIdentifier(entity.table)} (\n  ${columnClause}\n)`;
}

/**
 * Return the ordered DDL statements that create every entity's table — one
 * `CREATE TABLE` per **distinct table**. Foreign keys are intentionally omitted:
 * relationships are a query concern, and leaving FK constraints out keeps the
 * fixture-load order unconstrained (mirrors the harness).
 */
export function ddlForDescriptor(
  descriptor: unknown,
  dialect: Dialect = postgresDialect,
): readonly string[] {
  const byTable = new Map<string, DdlEntity>();
  for (const entity of entitiesOf(descriptor as DdlDescriptor)) {
    // First entity wins per table; a table-per-hierarchy union is a later phase.
    if (!byTable.has(entity.table)) {
      byTable.set(entity.table, entity);
    }
  }
  return [...byTable.values()].map((entity) => createTable(entity, dialect));
}

/**
 * The descriptor's physical column order for an entity's table (matches the DDL
 * and the fixture-load order), so fixture loading and table-state reads stay
 * column-aligned.
 */
export function columnOrder(entity: DdlEntity): readonly string[] {
  return entity.attributes.map((attr) => attr.column);
}
