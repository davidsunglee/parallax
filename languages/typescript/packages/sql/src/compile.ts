/**
 * The M3 **canonical-by-construction** compile visitor (design Q2/Q3, Option A).
 *
 * The visitor switches on the operation's single discriminant tag and emits the
 * five M3 normalization rules *directly* as it builds text — table aliases
 * `t0,t1,…` in first-appearance order, alias-qualified columns, lowercase
 * keywords/identifiers, `?` placeholders consumed left-to-right, and the fixed
 * clause order `select … from … [where …] … [limit …]`. Each predicate leaf
 * emits its `?` into the SQL **and** enqueues its bind in the *same* traversal
 * step (Reladomo's deferred-token discipline), so `binds` always matches
 * placeholder order. The conformance suite asserts `emitted === golden`, so a
 * single exact-string diff points straight at the offending clause.
 *
 * Phase 3 covers `all`, `eq`, and the `select … from … where` skeleton; the
 * remaining single-entity algebra (comparison / null / string / membership /
 * boolean / directives) is layered onto this same switch in Phase 4.
 *
 * The visitor imports no metamodel: it resolves a `Class.attr` reference and the
 * entity's default read projection through an injected {@link SchemaResolver},
 * so `@parallax/sql` depends only on `@parallax/operation` and
 * `@parallax/dialect` (the DAG forbids `sql → metamodel`). The runner builds the
 * resolver from the M1 reader.
 */
import { type Operation, operationTag } from "@parallax/operation";

/**
 * A resolved physical column: the table alias plus the quoted column name, ready
 * to splice into SQL as `<alias>.<column>`.
 */
export interface ResolvedColumn {
  /** The owning entity's table name (used to allocate / look up the alias). */
  readonly table: string;
  /** The dialect-quoted physical column name. */
  readonly column: string;
}

/**
 * The schema knowledge the compiler needs, injected so `@parallax/sql` stays
 * free of a metamodel import. The runner implements this over the M1 reader.
 */
export interface SchemaResolver {
  /** Resolve a `Class.attribute` reference to its table + quoted column. */
  resolveAttribute(ref: string): ResolvedColumn;
  /**
   * The root entity's table name (the `from` target) and its default read
   * projection — the ordered quoted columns the canonical SELECT projects.
   */
  rootTable(): string;
  /** The default read projection columns for the root entity (quoted names). */
  rootProjection(): readonly string[];
}

/** A bind value carried alongside a `?` placeholder, in placeholder order. */
export type Bind = string | number | boolean | null;

/**
 * The mutable compile context threaded through one traversal: the schema
 * resolver, a first-appearance alias allocator, and the binds accumulator.
 */
export interface CompileCtx {
  readonly schema: SchemaResolver;
  /** table name → assigned alias (`t0`, `t1`, …), in first-appearance order. */
  readonly aliases: Map<string, string>;
  /** The binds accumulator, appended to in placeholder order. */
  readonly binds: Bind[];
}

/** Build a fresh compile context for a single operation. */
export function newCompileCtx(schema: SchemaResolver): CompileCtx {
  return { schema, aliases: new Map(), binds: [] };
}

/**
 * Allocate (or look up) the alias for a table, assigning `t0,t1,…` in
 * first-appearance order. The root table is always `t0` because it appears
 * first (in the `from` clause).
 */
export function aliasFor(ctx: CompileCtx, table: string): string {
  const existing = ctx.aliases.get(table);
  if (existing !== undefined) {
    return existing;
  }
  const alias = `t${ctx.aliases.size}`;
  ctx.aliases.set(table, alias);
  return alias;
}

/** The result of compiling one operation: canonical SQL plus ordered binds. */
export interface CompileResult {
  readonly sql: string;
  readonly binds: readonly Bind[];
}

/**
 * Compile an M2 operation into canonical Postgres SQL plus its ordered binds.
 *
 * The root table is aliased `t0` up front (it is the `from` target and so the
 * first table reference), then the operation lowers to a `where` predicate (or
 * none for `all`). Binds are accumulated in the same traversal, so the returned
 * `binds` already match the `?` placeholders left-to-right.
 */
export function compile(op: Operation, schema: SchemaResolver): CompileResult {
  const ctx = newCompileCtx(schema);
  const table = schema.rootTable();
  const alias = aliasFor(ctx, table);
  const projection = schema
    .rootProjection()
    .map((column) => `${alias}.${column}`)
    .join(", ");

  const where = compilePredicate(op, ctx);
  const head = `select ${projection} from ${table} ${alias}`;
  const sql = where === undefined ? head : `${head} where ${where}`;
  return { sql, binds: ctx.binds };
}

/**
 * Lower one operation node to a `where`-clause predicate fragment, threading
 * binds into `ctx`. Returns `undefined` for `all` (the identity — no predicate).
 *
 * The switch is exhaustive over the Phase 3 tags; unimplemented tags throw a
 * clear "not yet supported" error so an out-of-phase operation fails loudly
 * rather than emitting wrong SQL. Phase 4+ extends this switch.
 */
export function compilePredicate(op: Operation, ctx: CompileCtx): string | undefined {
  const tag = operationTag(op);
  switch (tag) {
    case "all":
      return undefined;
    case "eq": {
      const { attr, value } = (op as { eq: { attr: string; value: Bind } }).eq;
      const target = qualify(ctx, attr);
      ctx.binds.push(value);
      return `${target} = ?`;
    }
    default:
      throw new Error(`compile: operation '${tag}' is not supported in this phase`);
  }
}

/** Resolve a `Class.attr` reference to its alias-qualified column text. */
function qualify(ctx: CompileCtx, ref: string): string {
  const { table, column } = ctx.schema.resolveAttribute(ref);
  const alias = aliasFor(ctx, table);
  return `${alias}.${column}`;
}
