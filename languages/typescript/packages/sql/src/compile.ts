/**
 * The M3 **canonical-by-construction** compile visitor (design Q2/Q3, Option A).
 *
 * The visitor switches on the operation's single discriminant tag and emits the
 * five M3 normalization rules *directly* as it builds text — table aliases
 * `t0,t1,…` in first-appearance order, alias-qualified columns, lowercase
 * keywords/identifiers, `?` placeholders consumed left-to-right, and the fixed
 * clause order `select [distinct] … from … [where …] [order by …] [limit …]`.
 * Each predicate leaf emits its `?` into the SQL **and** enqueues its bind in the
 * *same* traversal step (Reladomo's deferred-token discipline), so `binds` always
 * matches placeholder order. The conformance suite asserts `emitted === golden`,
 * so a single exact-string diff points straight at the offending clause.
 *
 * Phase 4 broadens the switch to the complete single-entity read algebra:
 * comparison (`notEq`, `>` / `>=` / `<` / `<=`, `between`), null (`isNull`,
 * `isNotNull`), string (`like` / `notLike`, the affix forms with wildcard
 * escaping + optional `escape ?`, and `caseInsensitive` lowering), membership
 * (`in` / `notIn`), boolean (`and` / `or` / `not` / `group` with the corpus's
 * precedence carried by explicit `group` nodes), the result directives
 * (`orderBy`, `limit` bound as `?`, `distinct`), and the `none` identity
 * (`1 = 0`, the one inline literal alongside the `eq` skeleton).
 *
 * The visitor imports no metamodel: it resolves a `Class.attr` reference (to its
 * table, quoted column, and M0 neutral type) and the entity's read projection
 * through an injected {@link SchemaResolver}, so `@parallax/sql` depends only on
 * `@parallax/operation` and `@parallax/dialect` (the DAG forbids `sql → metamodel`).
 * The runner builds the resolver from the M1 reader.
 */
import { type Operation, operationTag } from "@parallax/operation";
import { coerceBind } from "./bind.js";

/**
 * A resolved physical column: the table alias plus the quoted column name, ready
 * to splice into SQL as `<alias>.<column>`, plus the attribute's M0 neutral type
 * so the compiler can normalize a literal bound against it into the canonical
 * wire form (§2.2.1 — int64 / decimal beyond float-safe range become canonical
 * strings; everything else keeps its authored JSON form).
 */
export interface ResolvedColumn {
  /** The owning entity's table name (used to allocate / look up the alias). */
  readonly table: string;
  /** The dialect-quoted physical column name. */
  readonly column: string;
  /** The attribute's M0 neutral type (e.g. `int64`, `decimal(18,2)`, `string`). */
  readonly type: string;
}

/**
 * The schema knowledge the compiler needs, injected so `@parallax/sql` stays
 * free of a metamodel import. The runner implements this over the M1 reader.
 */
export interface SchemaResolver {
  /** Resolve a `Class.attribute` reference to its table, quoted column + type. */
  resolveAttribute(ref: string): ResolvedColumn;
  /**
   * The root entity's table name (the `from` target) and its read projection —
   * the ordered quoted columns the canonical SELECT projects.
   */
  rootTable(): string;
  /** The read projection columns for the root entity (quoted names). */
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

/** The directive decorations peeled off the outside of a read operation. */
interface Directives {
  /** `distinct` was requested on the projection. */
  readonly distinct: boolean;
  /** The rendered `order by …` clause body (without the keyword), if any. */
  readonly orderBy?: string;
  /** The `limit` row cap, bound as a trailing `?` (after any predicate binds). */
  readonly limit?: number;
  /** The innermost operation once every directive wrapper is removed. */
  readonly predicate: Operation;
}

/**
 * Compile an M2 operation into canonical Postgres SQL plus its ordered binds.
 *
 * The result directives (`distinct`, `orderBy`, `limit`) wrap the predicate from
 * the outside; they are peeled first so they can lower into their fixed clause
 * positions (`distinct` on the `select`, `order by` after `where`, `limit` last).
 * The root table is aliased `t0` up front (it is the `from` target and so the
 * first table reference), then the inner operation lowers to a `where` predicate
 * (or none for `all`). Binds are accumulated in the same traversal — the limit
 * bind appends after any predicate binds, matching placeholder order.
 */
export function compile(op: Operation, schema: SchemaResolver): CompileResult {
  const ctx = newCompileCtx(schema);
  const table = schema.rootTable();
  const alias = aliasFor(ctx, table);

  const directives = peelDirectives(op, ctx);
  const projection = schema
    .rootProjection()
    .map((column) => `${alias}.${column}`)
    .join(", ");
  const select = directives.distinct ? `select distinct ${projection}` : `select ${projection}`;

  // Compile the predicate FIRST so its binds precede the trailing `limit` bind.
  const where = compilePredicate(directives.predicate, ctx);
  if (directives.limit !== undefined) {
    ctx.binds.push(directives.limit);
  }

  let sql = `${select} from ${table} ${alias}`;
  if (where !== undefined) {
    sql += ` where ${where}`;
  }
  if (directives.orderBy !== undefined) {
    sql += ` order by ${directives.orderBy}`;
  }
  if (directives.limit !== undefined) {
    sql += " limit ?";
  }
  return { sql, binds: ctx.binds };
}

/**
 * Peel the result directives (`distinct` / `orderBy` / `limit`) off the outside
 * of a read operation, recording the `distinct` flag, the rendered `order by`
 * body, and the `limit` row cap. Returns the innermost predicate. The directives
 * nest predicate-inward (the corpus authors `limit { orderBy { <predicate> } }`);
 * the caller binds `limit` last so its `?` sits after any predicate binds.
 */
function peelDirectives(op: Operation, ctx: CompileCtx): Directives {
  let current = op;
  let distinct = false;
  let orderBy: string | undefined;
  let limit: number | undefined;

  for (;;) {
    const tag = operationTag(current);
    if (tag === "distinct") {
      distinct = true;
      current = (current as { distinct: { operand: Operation } }).distinct.operand;
      continue;
    }
    if (tag === "limit") {
      const body = (current as { limit: { operand: Operation; count: number } }).limit;
      limit = body.count;
      current = body.operand;
      continue;
    }
    if (tag === "orderBy") {
      const body = (
        current as {
          orderBy: { operand: Operation; keys: readonly { attr: string; direction?: string }[] };
        }
      ).orderBy;
      orderBy = body.keys
        .map((key) => `${qualify(ctx, key.attr)} ${key.direction ?? "asc"}`)
        .join(", ");
      current = body.operand;
      continue;
    }
    break;
  }

  return {
    distinct,
    predicate: current,
    ...(orderBy === undefined ? {} : { orderBy }),
    ...(limit === undefined ? {} : { limit }),
  };
}

/**
 * Lower one operation node to a `where`-clause predicate fragment, threading
 * binds into `ctx`. Returns `undefined` for `all` (the identity — no predicate).
 *
 * The switch is exhaustive over the single-entity read algebra; an out-of-phase
 * tag (navigation / temporal / aggregation / nested) throws a clear "not yet
 * supported" error so it fails loudly rather than emitting wrong SQL. Later
 * phases extend this switch.
 */
export function compilePredicate(op: Operation, ctx: CompileCtx): string | undefined {
  const tag = operationTag(op);
  switch (tag) {
    case "all":
      return undefined;
    case "none":
      // The absorbing element: an unsatisfiable predicate. `1 = 0` is one of the
      // two inline literals the M3 normalizer keeps (it is not a bind).
      return "1 = 0";

    case "eq":
      return comparison(ctx, (op as { eq: ComparisonBody }).eq, "=");
    case "notEq":
      return comparison(ctx, (op as { notEq: ComparisonBody }).notEq, "<>");
    case "greaterThan":
      return comparison(ctx, (op as { greaterThan: ComparisonBody }).greaterThan, ">");
    case "greaterThanEquals":
      return comparison(ctx, (op as { greaterThanEquals: ComparisonBody }).greaterThanEquals, ">=");
    case "lessThan":
      return comparison(ctx, (op as { lessThan: ComparisonBody }).lessThan, "<");
    case "lessThanEquals":
      return comparison(ctx, (op as { lessThanEquals: ComparisonBody }).lessThanEquals, "<=");
    case "between":
      return between(ctx, (op as { between: BetweenBody }).between);

    case "isNull":
      return `${qualify(ctx, (op as { isNull: NullBody }).isNull.attr)} is null`;
    case "isNotNull":
      // Canonical fixed point: the negation normalizes to a leading `not`.
      return `not ${qualify(ctx, (op as { isNotNull: NullBody }).isNotNull.attr)} is null`;

    case "like":
      return stringPredicate(ctx, (op as { like: StringBody }).like, "verbatim", false);
    case "notLike":
      return stringPredicate(ctx, (op as { notLike: StringBody }).notLike, "verbatim", true);
    case "startsWith":
      return stringPredicate(ctx, (op as { startsWith: StringBody }).startsWith, "prefix", false);
    case "endsWith":
      return stringPredicate(ctx, (op as { endsWith: StringBody }).endsWith, "suffix", false);
    case "contains":
      return stringPredicate(ctx, (op as { contains: StringBody }).contains, "infix", false);

    case "in":
      return membership(ctx, (op as { in: MembershipBody }).in, false);
    case "notIn":
      return membership(ctx, (op as { notIn: MembershipBody }).notIn, true);

    case "and":
      return junction(ctx, (op as { and: JunctionBody }).and.operands, "and");
    case "or":
      return junction(ctx, (op as { or: JunctionBody }).or.operands, "or");
    case "not":
      return `not ${requirePredicate(ctx, (op as { not: UnaryBody }).not.operand)}`;
    case "group":
      return `(${requirePredicate(ctx, (op as { group: UnaryBody }).group.operand)})`;

    default:
      throw new Error(`compile: operation '${tag}' is not supported in this phase`);
  }
}

// --- predicate-body shapes (structural, mirroring the operation schema) -------

interface ComparisonBody {
  readonly attr: string;
  readonly value: Bind;
}
interface BetweenBody {
  readonly attr: string;
  readonly lower: Bind;
  readonly upper: Bind;
}
interface NullBody {
  readonly attr: string;
}
interface StringBody {
  readonly attr: string;
  readonly value: string;
  readonly caseInsensitive?: boolean;
}
interface MembershipBody {
  readonly attr: string;
  readonly values: readonly Bind[];
}
interface JunctionBody {
  readonly operands: readonly Operation[];
}
interface UnaryBody {
  readonly operand: Operation;
}

// --- leaf emitters ----------------------------------------------------------

/** `t0.col <op> ?`, enqueuing the type-coerced literal in the same step. */
function comparison(ctx: CompileCtx, body: ComparisonBody, sqlOp: string): string {
  const resolved = ctx.schema.resolveAttribute(body.attr);
  const alias = aliasFor(ctx, resolved.table);
  pushBind(ctx, body.value, resolved.type);
  return `${alias}.${resolved.column} ${sqlOp} ?`;
}

/** `t0.col between ? and ?` — two ordered binds (lower, upper). */
function between(ctx: CompileCtx, body: BetweenBody): string {
  const resolved = ctx.schema.resolveAttribute(body.attr);
  const alias = aliasFor(ctx, resolved.table);
  pushBind(ctx, body.lower, resolved.type);
  pushBind(ctx, body.upper, resolved.type);
  return `${alias}.${resolved.column} between ? and ?`;
}

/** How a string predicate's literal is wrapped into a `like` pattern. */
type StringMode = "verbatim" | "prefix" | "suffix" | "infix";

/** The SQL backslash escape used for the affix forms (carried as a bind). */
const ESCAPE_CHAR = "\\";

/**
 * Lower a string predicate.
 *  - `verbatim` (`like` / `notLike`): the literal is already a pattern; bind it
 *    as-is, with the `not like` keyword pair for the negated form. No escape.
 *  - affix forms (`startsWith` / `endsWith` / `contains`): the literal is taken
 *    literally — any `%` / `_` wildcard in it is escaped and the affix `%`
 *    wildcard(s) are placed by us, so a fat-fingered literal cannot over-match.
 *    When the literal carried a wildcard char an `escape ?` clause is emitted.
 *  - `caseInsensitive`: both sides lower through `lower(...)`.
 */
function stringPredicate(
  ctx: CompileCtx,
  body: StringBody,
  mode: StringMode,
  negated: boolean,
): string {
  const resolved = ctx.schema.resolveAttribute(body.attr);
  const alias = aliasFor(ctx, resolved.table);
  const ci = body.caseInsensitive === true;
  const target = ci ? `lower(${alias}.${resolved.column})` : `${alias}.${resolved.column}`;
  const keyword = negated ? "not like" : "like";

  if (mode === "verbatim") {
    // The value is already a pattern; case-insensitive folds it too.
    pushBind(ctx, ci ? body.value.toLowerCase() : body.value, resolved.type);
    const rhs = ci ? "lower(?)" : "?";
    return `${target} ${keyword} ${rhs}`;
  }

  // Affix form: escape wildcard chars in the literal, then wrap with `%`.
  const escaped = escapeLikeLiteral(body.value);
  const wrapped = wrapAffix(escaped.pattern, mode);
  const literal = ci ? wrapped.toLowerCase() : wrapped;
  pushBind(ctx, literal, resolved.type);
  const rhs = ci ? "lower(?)" : "?";
  if (escaped.usedEscape) {
    pushBind(ctx, ESCAPE_CHAR, "string");
    return `${target} ${keyword} ${rhs} escape ?`;
  }
  return `${target} ${keyword} ${rhs}`;
}

/** Wrap an escaped literal in the affix wildcards for its mode. */
function wrapAffix(escaped: string, mode: StringMode): string {
  if (mode === "prefix") {
    return `${escaped}%`;
  }
  if (mode === "suffix") {
    return `%${escaped}`;
  }
  // infix (contains)
  return `%${escaped}%`;
}

/**
 * Escape the SQL `like` wildcard characters (`%` `_`) and the escape char itself
 * in a literal search term so they match literally. Reports whether any escaping
 * happened so the caller knows to emit the `escape ?` clause.
 */
function escapeLikeLiteral(value: string): { pattern: string; usedEscape: boolean } {
  let used = false;
  let out = "";
  for (const ch of value) {
    if (ch === "%" || ch === "_" || ch === ESCAPE_CHAR) {
      out += ESCAPE_CHAR + ch;
      used = true;
    } else {
      out += ch;
    }
  }
  return { pattern: out, usedEscape: used };
}

/** `[not ]t0.col in (?, ?, …)` — one bind per value, in list order. */
function membership(ctx: CompileCtx, body: MembershipBody, negated: boolean): string {
  const resolved = ctx.schema.resolveAttribute(body.attr);
  const alias = aliasFor(ctx, resolved.table);
  const placeholders = body.values
    .map((value) => {
      pushBind(ctx, value, resolved.type);
      return "?";
    })
    .join(", ");
  const expr = `${alias}.${resolved.column} in (${placeholders})`;
  return negated ? `not ${expr}` : expr;
}

/** Join boolean operands with ` and ` / ` or `; binds follow left-to-right. */
function junction(ctx: CompileCtx, operands: readonly Operation[], connector: string): string {
  return operands.map((operand) => requirePredicate(ctx, operand)).join(` ${connector} `);
}

/**
 * Compile an inner operation that MUST be a predicate (a boolean operand). The
 * identities `all` / `none` are not legal operands of `and` / `or` / `not` /
 * `group` (they carry no predicate text), so a missing fragment is an error.
 */
function requirePredicate(ctx: CompileCtx, op: Operation): string {
  const fragment = compilePredicate(op, ctx);
  if (fragment === undefined) {
    throw new Error(`compile: '${operationTag(op)}' has no predicate text to combine`);
  }
  return fragment;
}

/** Resolve a `Class.attr` reference to its alias-qualified column text. */
function qualify(ctx: CompileCtx, ref: string): string {
  const resolved = ctx.schema.resolveAttribute(ref);
  const alias = aliasFor(ctx, resolved.table);
  return `${alias}.${resolved.column}`;
}

/**
 * Append a literal to the binds accumulator, normalized to its canonical wire
 * form against the attribute's M0 neutral type (§2.2.1). Float-safe authored
 * numbers keep their JSON form; an int64 / decimal value the serde reader
 * preserved as an exact source string (precision-unsafe) becomes the canonical
 * wire string here.
 */
function pushBind(ctx: CompileCtx, value: Bind, type: string): void {
  ctx.binds.push(coerceBind(value, type));
}
