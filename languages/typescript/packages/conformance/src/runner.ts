/**
 * The M12 runner — orchestrates `compile` / `run` for the `read` shape.
 *
 * `compile` (Docker-free): resolve the case's operation against the M1 metamodel
 * reader, lower it with the M3 canonical-by-construction visitor, and assemble a
 * schema-valid `compile` envelope (emissions + binds + `roundTrips`). No database
 * is touched.
 *
 * `run` (database-backed): provision a clean DB via the injected
 * `CompatibilityDatabaseProvider` port, derive + apply DDL from the descriptor,
 * load fixtures per the case lifecycle, execute the compiled SQL, assemble `rows`
 * observations with `observations.roundTrips`, and validate the `run` envelope.
 *
 * The provider is **injected** through the port — the runner imports no driver
 * and no dialect package (it reaches the dialect-owned DDL / quoting helpers
 * through the one allowed `M3 -> M11` facade re-exported by `@parallax/sql`, and
 * the M1 reader through the `M2 -> M1` facade re-exported by
 * `@parallax/operation`).
 */
import type {
  AdapterIdentity,
  BindValue,
  CaseShape,
  CompileOk,
  Diagnostic,
  Emission,
  Envelope,
  NonOk,
  Observations,
  Row,
  RunOk,
} from "@parallax/core";
import {
  type EntityMetadata,
  Metamodel,
  type NormalizedAttribute,
  type Operation,
  parseOperation,
} from "@parallax/operation";
import {
  columnOrder,
  compile,
  ddlForDescriptor,
  quoteIdentifier,
  type ResolvedColumn,
  type SchemaResolver,
} from "@parallax/sql";
import { FIRST_IMPLEMENTATION_MVP_CAPABILITIES } from "./describe.js";
import type { LoadedCase } from "./discover.js";
import { inClaim } from "./gate.js";
import type { CompatibilityDatabaseProvider } from "./provider.js";
import { assertValidEnvelope } from "./schema.js";

/** The case's authored binds carried verbatim (a flat scalar list for a read). */
type WireBind = BindValue;

/**
 * The JSON Pointer an emission carries for a single read-shape operation: the
 * case's `operation` key. The conformance contract names `/operation` as the
 * common read-operation pointer (`conformance-adapter-contract.md` — both the
 * `compile` and `run` examples), reserving the empty pointer `""` for
 * diagnostics that apply to the whole case (e.g. the out-of-claim gate). Write
 * sequences / scenarios / deep fetch use per-statement pointers (Phase 4+).
 */
const READ_OPERATION_POINTER = "/operation" as const;

/**
 * A `SchemaResolver` over the M1 metamodel reader. Resolves `Class.attr`
 * references to alias-qualified columns and supplies the root entity's table +
 * default read projection that the M3 visitor projects.
 */
class MetamodelSchema implements SchemaResolver {
  constructor(
    private readonly metamodel: Metamodel,
    private readonly rootEntity: EntityMetadata,
  ) {}

  resolveAttribute(ref: string): ResolvedColumn {
    const [className, attrName] = splitRef(ref);
    const entity = this.metamodel.entity(className);
    const attr = entity.attributeByName(attrName);
    return { table: entity.table, column: quoteIdentifier(attr.column) };
  }

  rootTable(): string {
    return this.rootEntity.table;
  }

  rootProjection(): readonly string[] {
    return defaultReadProjection(this.rootEntity).map((attr) => quoteIdentifier(attr.column));
  }
}

/**
 * The V1 default read projection for an entity: the primary-key attribute(s)
 * followed by the first non-primary-key attribute (yielding `id, name` for the
 * `orders` root). The corpus authors each entity's read projection into its
 * golden SQL and it is not a pure function of the descriptor across all models,
 * so this is a deliberately small, documented convention that reproduces the
 * Phase 3 golden.
 *
 * Phase 4 generalizes this to the full scalar-column set per case. The seam is
 * localized: only this function (the sole caller is `MetamodelSchema.rootProjection`
 * above; the M3 visitor consumes `schema.rootProjection()` purely) needs to
 * change — no compiler edit. The `[pk, firstNonPk]` shortcut already diverges
 * for models whose golden projects more than two columns, e.g.
 * `models/scalars.yaml` (0003 projects `id, f32, f64, payload_hex, local_time,
 * external_id`) and the wider `orders` reads (`02xx`), so Phase 4 must derive the
 * projection from each entity's full scalar-attribute order (matching the golden
 * SELECT) rather than this two-column heuristic.
 */
export function defaultReadProjection(entity: EntityMetadata): readonly NormalizedAttribute[] {
  const attributes = entity.attributes();
  const primaryKey = attributes.filter((attr) => attr.primaryKey);
  const firstNonPk = attributes.find((attr) => !attr.primaryKey);
  const projection = [...primaryKey];
  if (firstNonPk && !projection.includes(firstNonPk)) {
    projection.push(firstNonPk);
  }
  return projection;
}

/** Split a `Class.attribute` reference into its two parts. */
function splitRef(ref: string): [string, string] {
  const dot = ref.indexOf(".");
  if (dot === -1) {
    throw new Error(`malformed reference '${ref}' (expected 'Class.attribute')`);
  }
  return [ref.slice(0, dot), ref.slice(dot + 1)];
}

/** The root entity a read case queries: the operation references it by `Class.attr`. */
function rootEntityFor(metamodel: Metamodel, operation: Operation): EntityMetadata {
  // The root class is named by the first `Class.attr` reference in the
  // operation, or — for `all` with no reference — the model's first entity.
  const ref = firstClassRef(operation);
  if (ref) {
    return metamodel.entity(ref);
  }
  const [first] = metamodel.entities();
  if (!first) {
    throw new Error("model declares no entities");
  }
  return first;
}

/** The class name of the first `Class.attr` reference reachable in an operation. */
function firstClassRef(node: unknown): string | undefined {
  if (node === null || typeof node !== "object") {
    return undefined;
  }
  for (const value of Object.values(node as Record<string, unknown>)) {
    if (typeof value === "string" && /^[A-Z][A-Za-z0-9]*\.[A-Za-z]/.test(value)) {
      return value.slice(0, value.indexOf("."));
    }
    const nested = firstClassRef(value);
    if (nested) {
      return nested;
    }
  }
  return undefined;
}

/** Build the `MetamodelSchema` resolver for a read case. */
function schemaFor(loaded: LoadedCase, operation: Operation): MetamodelSchema {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const rootEntity = rootEntityFor(metamodel, operation);
  return new MetamodelSchema(metamodel, rootEntity);
}

// --- compile lane -----------------------------------------------------------

/**
 * Compile a `read` case to its canonical SQL + binds and assemble a schema-valid
 * `compile` envelope. Single-statement read shape only (Phase 3); the emission's
 * `casePointer` is `/operation` (the JSON Pointer to the case's operation key),
 * per the conformance contract's `compile` example.
 */
export function runCompile(
  loaded: LoadedCase,
  dialect: string,
  adapter: AdapterIdentity,
): Envelope {
  const gate = gateOrNonOk(loaded, "compile", dialect, adapter);
  if (gate) {
    return gate;
  }
  const operation = parseOperation(loaded.raw.operation);
  const schema = schemaFor(loaded, operation);
  const { sql, binds } = compile(operation, schema);

  const emission: Emission = {
    casePointer: READ_OPERATION_POINTER,
    sql,
    binds: binds as readonly WireBind[],
  };
  const envelope: CompileOk = {
    schemaVersion: "1",
    command: "compile",
    status: "ok",
    adapter,
    case: loaded.casePath,
    dialect,
    caseShape: loaded.shape,
    emissions: [emission],
    roundTrips: 1,
  };
  return assertValidEnvelope(envelope);
}

// --- run lane ---------------------------------------------------------------

/**
 * Run a `read` case end-to-end against an injected provider: provision, derive +
 * apply DDL, load fixtures, execute the compiled SQL, and assemble a schema-valid
 * `run` envelope with `rows` + `roundTrips`.
 */
export async function runRun(
  loaded: LoadedCase,
  dialect: string,
  adapter: AdapterIdentity,
  provider: CompatibilityDatabaseProvider,
): Promise<Envelope> {
  const gate = gateOrNonOk(loaded, "run", dialect, adapter);
  if (gate) {
    return gate;
  }
  const operation = parseOperation(loaded.raw.operation);
  const schema = schemaFor(loaded, operation);
  const { sql, binds } = compile(operation, schema);

  await provision(loaded, provider);

  const rows = await provider.query(sql, binds as readonly unknown[]);
  const observations: Observations = {
    roundTrips: 1,
    rows: rows as readonly Row[],
  };
  const emission: Emission = {
    casePointer: READ_OPERATION_POINTER,
    sql,
    binds: binds as readonly WireBind[],
  };
  const envelope: RunOk = {
    schemaVersion: "1",
    command: "run",
    status: "ok",
    adapter,
    case: loaded.casePath,
    dialect,
    caseShape: loaded.shape,
    emissions: [emission],
    observations,
  };
  return assertValidEnvelope(envelope);
}

/** Provision a clean DB: reset, derive + apply DDL, load fixtures. */
async function provision(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
): Promise<void> {
  await provider.reset();
  await provider.applyDdl(ddlForDescriptor(loaded.descriptor));
  await loadFixtures(loaded, provider);
}

/**
 * Load every entity's fixture rows. Fixture rows speak attribute-name
 * vocabulary; resolve them to descriptor column order, filling missing
 * attributes with `null` (mirrors the harness data loader).
 */
async function loadFixtures(
  loaded: LoadedCase,
  provider: CompatibilityDatabaseProvider,
): Promise<void> {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  for (const entity of metamodel.entities()) {
    const rows = loaded.fixtures[entity.name] ?? [];
    if (rows.length === 0) {
      continue;
    }
    const attributes = entity.attributes();
    const columns = columnOrder({
      table: entity.table,
      attributes: attributes.map((a) => ({ type: a.type, column: a.column })),
    });
    const nameByColumn = new Map(attributes.map((a) => [a.column, a.name]));
    const tuples = rows.map((row) =>
      columns.map((column) => row[nameByColumn.get(column) ?? column] ?? null),
    );
    await provider.loadFixtures(entity.table, columns, tuples);
  }
}

// --- shared gating ----------------------------------------------------------

/**
 * Evaluate the in-claim gate; return an `unsupported` envelope (out of claim)
 * or `undefined` (in claim — proceed). The diagnostic names the first failed
 * filter.
 */
function gateOrNonOk(
  loaded: LoadedCase,
  command: "compile" | "run",
  dialect: string,
  adapter: AdapterIdentity,
): NonOk | undefined {
  const gate = inClaim(
    { shape: loaded.shape, tags: loaded.tags },
    command,
    dialect,
    FIRST_IMPLEMENTATION_MVP_CAPABILITIES,
  );
  if (gate.inClaim) {
    return undefined;
  }
  const diagnostic: Diagnostic = {
    code: gate.code,
    message: gate.message,
    casePointer: "",
  };
  return {
    schemaVersion: "1",
    command,
    status: "unsupported",
    adapter,
    diagnostics: [diagnostic],
  };
}

/** Re-export the shape type for consumers assembling envelopes. */
export type { CaseShape };
