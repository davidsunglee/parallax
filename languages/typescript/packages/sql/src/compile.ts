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
 * `@parallax/operation` (the DAG forbids `sql → metamodel`). The runner builds the
 * resolver from the M1 reader.
 */
import type { Dialect } from "@parallax/dialect";
import { type Operation, operationTag } from "@parallax/operation";
import { coerceBind } from "./bind.js";

/**
 * A resolved physical column: the table alias plus the quoted column name, ready
 * to splice into SQL as `<alias>.<column>`, plus the attribute's M0 neutral type
 * so the compiler can normalize a literal bound against it into the canonical
 * wire form (§3.2.1 — int64 / decimal beyond float-safe range become canonical
 * strings; everything else keeps its authored JSON form).
 */
export interface ResolvedColumn {
  /** The owning entity's table name (used to allocate / look up the alias). */
  readonly table: string;
  /** The dialect-quoted physical column name. */
  readonly column: string;
  /** The attribute's M0 neutral type (e.g. `int64`, `decimal(18,2)`, `string`). */
  readonly type: string;
  /**
   * Whether the column admits `NULL`. Consulted by ORDER BY assembly so a NULL-
   * bearing key is placed through the dialect's NULL-placement rule
   * (`dialect.orderByTerm`) while a NOT-NULL key — where NULL placement is moot —
   * emits the bare `<col> asc|desc` form (byte-identical to the hand-authored
   * goldens). Optional: a resolver that omits it defaults a column to NOT-NULL.
   */
  readonly nullable?: boolean;
}

/**
 * A resolved relationship correlation, derived mechanically from the metamodel
 * `join` predicate (M4 — the user never writes a join). A navigation filter
 * lowers to `exists (select 1 from <childTable> <childAlias> where
 * <childAlias>.<childColumn> = <parentAlias>.<parentColumn> [and <inner>])`.
 *
 * The columns come from the canonical join form `this.<thisAttr> =
 * <Related>.<relatedAttr>`: the **parent** (correlating, outer) side is the
 * relationship's *source* entity (column `parentColumn` from `thisAttr`), the
 * **child** (inner EXISTS) side is the *related* entity (table `childTable`,
 * column `childColumn` from `relatedAttr`). The mapping is uniform across
 * cardinalities — a to-one hop correlates `t1.id = t0.fk`, a to-many hop
 * correlates `t1.fk = t0.id` — because the join predicate already names the two
 * key columns and which entity owns each.
 */
export interface ResolvedRelationship {
  /** The related (child) entity's physical table name. */
  readonly childTable: string;
  /** The dialect-quoted child-side correlation column (the related-attr column). */
  readonly childColumn: string;
  /** The dialect-quoted parent-side correlation column (the this-attr column). */
  readonly parentColumn: string;
}

/** A temporal axis identity — `business` (from_z/thru_z) or `processing` (in_z/out_z). */
export type Axis = "business" | "processing";

/**
 * A per-axis as-of pin collected off the operation's `asOf` / `asOfRange` /
 * `history` wrappers (an axis absent from the map defaults to `now` — the
 * default-injection rule). `history` marks an axis as read as edge points (no
 * predicate injected for it).
 */
export type AxisPin =
  | { readonly kind: "now" }
  | { readonly kind: "instant"; readonly date: string }
  | { readonly kind: "range"; readonly from: string; readonly to: string }
  | { readonly kind: "history" };

/** The as-of pins gathered for one entity read, keyed by axis. */
export type AxisPins = Partial<Record<Axis, AxisPin>>;

/** A rendered as-of predicate: the `and`-joined SQL fragment and its ordered binds. */
export interface AsOfFragment {
  /** The SQL fragment (empty when the entity is non-temporal / every axis history). */
  readonly sql: string;
  /** The binds, in placeholder order (appended after the user binds). */
  readonly binds: readonly Bind[];
}

/**
 * The schema knowledge the compiler needs, injected so `@parallax/sql` stays
 * free of a metamodel import. The runner implements this over the M1 reader.
 */
export interface SchemaResolver {
  /** Resolve a `Class.attribute` reference to its table, quoted column + type. */
  resolveAttribute(ref: string): ResolvedColumn;
  /**
   * Resolve a `Class.relationship` reference to its correlation columns + child
   * table (the navigation/EXISTS semi-join correlation, derived from the join).
   */
  resolveRelationship(ref: string): ResolvedRelationship;
  /**
   * The root entity's table name (the `from` target) and its read projection —
   * the ordered quoted columns the canonical SELECT projects.
   */
  rootTable(): string;
  /**
   * The read projection columns for the root entity, in projection order. Each is
   * the quoted physical column plus its M0 type / output name, so a `bytes` column
   * can lower to the `encode(...)` hex form while every other type projects
   * verbatim (M0 scalar-serde projection).
   */
  rootProjection(): readonly ProjectionColumn[];
  /**
   * Resolve a `Class.asOfAttribute` reference (`Balance.processingDate`) to the
   * axis it pins. Used to key the collected as-of pins by axis. Present only when
   * the resolver supports temporal reads (M7); the compiler probes for it.
   */
  resolveAsOfAxis?(ref: string): Axis;
  /** The root entity's domain class name (for the root as-of injection). */
  rootEntityName?(): string;
  /**
   * The injected as-of predicate for an entity's declared axes under a set of
   * pins, qualified with the given alias (the M7 default-injection + composition
   * rule, delegated to `@parallax/bitemporal` through the composition path). The
   * `entity` is named by the class the read roots at (or the EXISTS child
   * entity); a non-temporal entity yields an empty fragment. Present only when the
   * resolver supports temporal reads.
   */
  asOfPredicate?(entity: string, alias: string, pins: AxisPins): AsOfFragment;
  /**
   * The class name of the related (child) entity a `Class.relationship` reference
   * navigates to (the EXISTS child), so the compiler can propagate the root as-of
   * pins into the semi-join subquery. Present only when temporal reads are
   * supported.
   */
  relatedEntityName?(ref: string): string;
}

/** A bind value carried alongside a `?` placeholder, in placeholder order. */
export type Bind = string | number | boolean | null;

/**
 * One column of a read's SELECT projection. A plain scalar column projects
 * verbatim (`<alias>.<column>`); a `bytes` column lowers through Postgres
 * `encode(<alias>.<column>, ?) <outputName>` with the `'hex'` format bound in the
 * projection position, so the byte payload materializes as stable hex text (M0
 * scalar-serde projection — case `0003`). The projection binds land BEFORE any
 * `where` binds, matching left-to-right placeholder order.
 */
export interface ProjectionColumn {
  /** The dialect-quoted physical column name (`payload`, `"order"`). */
  readonly column: string;
  /**
   * The attribute's M0 neutral type. A `bytes` type triggers the `encode(...)`
   * hex lowering; every other type (or `undefined`) projects the column verbatim.
   */
  readonly type?: string;
  /**
   * The output column name for a lowered projection (`payload_hex`). Only used by
   * the `bytes` `encode(...)` form, where the output name differs from the
   * physical column; a verbatim column's output name is the column itself.
   */
  readonly outputName?: string;
}

/**
 * The mutable compile context threaded through one traversal: the schema
 * resolver, a first-appearance alias allocator, and the binds accumulator. The
 * as-of pins collected off the operation's temporal wrappers travel here too, so
 * a correlated-EXISTS semi-join can **propagate** them into its child subquery
 * (M4 as-of propagation across a temporal hop).
 */
export interface CompileCtx {
  readonly schema: SchemaResolver;
  /** table name → assigned alias (`t0`, `t1`, …), in first-appearance order. */
  readonly aliases: Map<string, string>;
  /** The binds accumulator, appended to in placeholder order. */
  readonly binds: Bind[];
  /** The as-of pins for this read, propagated into any temporal EXISTS child. */
  asOfPins: AxisPins;
}

/** Build a fresh compile context for a single operation. */
export function newCompileCtx(schema: SchemaResolver): CompileCtx {
  return { schema, aliases: new Map(), binds: [], asOfPins: {} };
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
 * The execution context `compile` consults for the dialect-divergent decisions it
 * makes *during* assembly (the M3 → M11 inversion): whether this read takes the
 * in-transaction shared read-lock, and (M4 propagation) the pre-seeded as-of pins.
 */
export interface CompileExec {
  /**
   * The enclosing unit of work is a `locking`-mode in-transaction read, so the
   * dialect's shared read-lock is applied as the final in-compile step. Absent /
   * false for an out-of-transaction or `optimistic`-mode read.
   */
  readonly locking?: boolean;
  /**
   * A projection / aggregation read (no base row to lock). Reserved for an explicit
   * override; `compile` otherwise derives it from whether it emitted `distinct`.
   */
  readonly projection?: boolean;
  /**
   * Pre-seed the read's as-of pins before peeling — the M4 deep-fetch propagation
   * path injects the root's pins (matched by axis) into a child level's temporal
   * predicate, so the child reads as of the same instant(s).
   */
  readonly seedPins?: AxisPins;
}

/**
 * Compile an M2 operation into **dialect-optimized** SQL plus its ordered binds,
 * against the injected {@link Dialect} contract (the M3 → M11 edge).
 *
 * The result directives (`distinct`, `orderBy`, `limit`) wrap the predicate from
 * the outside; they are peeled first so they can lower into their fixed clause
 * positions (`distinct` on the `select`, `order by` after `where`, `limit` last).
 * The root table is aliased `t0` up front (it is the `from` target and so the
 * first table reference), then the inner operation lowers to a `where` predicate
 * (or none for `all`). Binds are accumulated in the same traversal — the limit
 * bind appends after any predicate binds, matching placeholder order.
 *
 * Every divergent fragment is routed through the `dialect`: ORDER BY NULL placement
 * (`dialect.orderByTerm`, for NULL-bearing keys), the row-limit clause
 * (`dialect.rowLimit`), and — the final in-compile step — the in-transaction shared
 * read-lock (`dialect.applyReadLock`, gated on `exec.locking`; `compile` already
 * knows whether it emitted `distinct`, so the projection flag needs no regex). The
 * emitted SQL still carries canonical `?` placeholders; the adapter translates them
 * to the driver's syntax at the boundary.
 *
 * `exec.seedPins` pre-seeds the read's as-of pins before peeling — the M4 deep-fetch
 * **propagation** path uses it to inject the root's pins (matched by axis) into a
 * child level's temporal predicate, so the child reads as of the same instant(s).
 * A single-entity read leaves it empty and collects its pins from its own
 * `asOf` / `asOfRange` / `history` wrappers.
 */
export function compile(
  op: Operation,
  schema: SchemaResolver,
  dialect: Dialect,
  exec?: CompileExec,
): CompileResult {
  const ctx = newCompileCtx(schema);
  if (exec?.seedPins !== undefined) {
    ctx.asOfPins = { ...exec.seedPins };
  }
  const table = schema.rootTable();
  const alias = aliasFor(ctx, table);

  const directives = peelDirectives(op, ctx, dialect);
  // Peel the temporal wrappers (`asOf` / `asOfRange` / `history`) off the
  // predicate, collecting per-axis pins into the context (so a temporal EXISTS
  // child can propagate them). What remains is the base user predicate.
  const base = peelTemporal(directives.predicate, ctx);

  // Render the projection FIRST so any projection bind (the `bytes` `encode(…, ?)`
  // hex format) precedes the predicate / as-of / limit binds — the projection sits
  // before the `where` in the statement, so its `?` is left-most (M3 placeholder
  // order). A plain column emits no bind; a `bytes` column emits `'hex'` here.
  const projection = renderProjection(schema.rootProjection(), alias, ctx, dialect);
  const select = directives.distinct ? `select distinct ${projection}` : `select ${projection}`;

  // Compile the user predicate FIRST so its binds precede the injected as-of binds
  // and the trailing `limit` bind (left-to-right placeholder order).
  const userWhere = compilePredicate(base, ctx);
  // The injected as-of term is appended AFTER the user predicate (M7): its binds
  // land after the user binds. Default-injection + axis composition are owned by
  // the resolver (delegating to `@parallax/bitemporal`); a non-temporal entity or
  // an all-`history` read yields an empty fragment.
  const asOf = injectRootAsOf(ctx, alias);
  const where = combineWhere(userWhere, asOf?.sql);

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
  // The row-limit clause goes THROUGH the dialect (a *wrappable* hook, not a bare
  // suffix) so a future dialect that must rewrite the query shape can override it;
  // today every dialect appends ` limit ?`, so this stays byte-identical.
  if (directives.limit !== undefined) {
    sql = dialect.rowLimit(sql);
  }
  // The in-transaction shared read-lock is the FINAL in-compile step (M8 automatic
  // read-lock correctness, owned by M11): the dialect decides whether/where/how it
  // attaches. `compile` knows authoritatively whether it emitted `distinct`, so the
  // projection flag comes straight from the directives (no post-hoc regex). A non-
  // locking read returns unchanged.
  sql = dialect.applyReadLock(sql, {
    locking: exec?.locking ?? false,
    projection: directives.distinct,
  });
  return { sql, binds: ctx.binds };
}

/**
 * Render the SELECT projection list, alias-qualifying each column and lowering a
 * `bytes` column to the Postgres `encode(<alias>.<column>, ?) <column>_hex` hex
 * form (the M0 scalar-serde projection — `0003`). A lowered column pushes its
 * `'hex'` format bind onto the accumulator IN projection order (before the `where`
 * binds); a plain scalar column projects verbatim and pushes nothing.
 */
function renderProjection(
  columns: readonly ProjectionColumn[],
  alias: string,
  ctx: CompileCtx,
  dialect: Dialect,
): string {
  return columns.map((column) => renderProjectionColumn(column, alias, ctx, dialect)).join(", ");
}

/** Render one projection column (verbatim, or the dialect's `bytes` hex form). */
function renderProjectionColumn(
  column: ProjectionColumn,
  alias: string,
  ctx: CompileCtx,
  dialect: Dialect,
): string {
  const qualified = `${alias}.${column.column}`;
  if (column.type === "bytes") {
    // A byte column has no stable text rendering across drivers/dialects, so the
    // projection is lowered to the dialect's hex form (Postgres `encode(t0.payload,
    // ?) payload_hex` with a `'hex'` bind; MariaDB the bind-free `hex(t0.payload)
    // payload_hex`). The dialect owns both the SQL and any bind it introduces, which
    // is spliced here in projection order (before the `where` binds).
    const output = column.outputName ?? `${column.column}_hex`;
    const projected = dialect.bytesProjection(qualified, output);
    for (const bind of projected.binds) {
      ctx.binds.push(bind as Bind);
    }
    return projected.sql;
  }
  return qualified;
}

/**
 * Combine the user predicate fragment and the injected as-of fragment into one
 * `where` body (either, both `and`-joined, or `undefined` when neither is present
 * — an `all` read on a non-temporal entity).
 */
function combineWhere(user: string | undefined, asOf: string | undefined): string | undefined {
  if (user !== undefined && asOf !== undefined && asOf !== "") {
    return `${user} and ${asOf}`;
  }
  if (user !== undefined) {
    return user;
  }
  return asOf !== undefined && asOf !== "" ? asOf : undefined;
}

/**
 * Peel every `asOf` / `asOfRange` / `history` wrapper off the outside of a
 * predicate, recording each into `ctx.asOfPins` keyed by the axis its
 * `asOfAttr` names. Returns the innermost base predicate (the user filter). A
 * resolver without temporal support (`resolveAsOfAxis` absent) leaves the wrappers
 * in place, so the base compile path throws the clear "not supported" error.
 */
function peelTemporal(op: Operation, ctx: CompileCtx): Operation {
  let current = op;
  for (;;) {
    const tag = operationTag(current);
    if (tag === "asOf") {
      const body = (current as { asOf: { operand: Operation; asOfAttr: string; date: string } })
        .asOf;
      recordPin(ctx, body.asOfAttr, temporalPinForDate(body.date));
      current = body.operand;
      continue;
    }
    if (tag === "asOfRange") {
      const body = (
        current as {
          asOfRange: { operand: Operation; asOfAttr: string; from: string; to: string };
        }
      ).asOfRange;
      recordPin(ctx, body.asOfAttr, { kind: "range", from: body.from, to: body.to });
      current = body.operand;
      continue;
    }
    if (tag === "history") {
      const body = (current as { history: { operand: Operation; asOfAttr: string } }).history;
      recordPin(ctx, body.asOfAttr, { kind: "history" });
      current = body.operand;
      continue;
    }
    break;
  }
  return current;
}

/** A single-instant pin lowers to `now` (current row) or a past `instant`. */
function temporalPinForDate(date: string): AxisPin {
  return date === "now" ? { kind: "now" } : { kind: "instant", date };
}

/** Record an as-of pin under the axis its `Class.asOfAttribute` reference names. */
function recordPin(ctx: CompileCtx, asOfAttrRef: string, pin: AxisPin): void {
  if (ctx.schema.resolveAsOfAxis === undefined) {
    throw new Error("compile: temporal reads require a temporal-capable SchemaResolver");
  }
  const axis = ctx.schema.resolveAsOfAxis(asOfAttrRef);
  ctx.asOfPins[axis] = pin;
}

/**
 * The injected as-of fragment for the root entity under the collected pins, its
 * binds pushed onto the accumulator (after the user binds). `undefined` when the
 * resolver is non-temporal or the entity is non-temporal / all-history.
 */
function injectRootAsOf(ctx: CompileCtx, alias: string): AsOfFragment | undefined {
  if (ctx.schema.asOfPredicate === undefined || ctx.schema.rootEntityName === undefined) {
    return undefined;
  }
  const fragment = ctx.schema.asOfPredicate(ctx.schema.rootEntityName(), alias, ctx.asOfPins);
  if (fragment.sql === "") {
    return undefined;
  }
  ctx.binds.push(...fragment.binds);
  return fragment;
}

/**
 * Peel the result directives (`distinct` / `orderBy` / `limit`) off the outside
 * of a read operation, recording the `distinct` flag, the rendered `order by`
 * body, and the `limit` row cap. Returns the innermost predicate. The directives
 * nest predicate-inward (the corpus authors `limit { orderBy { <predicate> } }`);
 * the caller binds `limit` last so its `?` sits after any predicate binds.
 */
function peelDirectives(op: Operation, ctx: CompileCtx, dialect: Dialect): Directives {
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
      orderBy = body.keys.map((key) => orderByTerm(ctx, dialect, key)).join(", ");
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
export function compilePredicate(op: Operation, ctx: CompileCtx, scope = "t0"): string | undefined {
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
      return junction(ctx, (op as { and: JunctionBody }).and.operands, "and", scope);
    case "or":
      return junction(ctx, (op as { or: JunctionBody }).or.operands, "or", scope);
    case "not":
      return `not ${requirePredicate(ctx, (op as { not: UnaryBody }).not.operand, scope)}`;
    case "group":
      return `(${requirePredicate(ctx, (op as { group: UnaryBody }).group.operand, scope)})`;

    case "navigate":
      // A navigation FILTER is the positive semi-join (M4): keep parent rows for
      // which a correlated related row (optionally satisfying the inner op)
      // exists. `navigate` and `exists` lower to the identical EXISTS form; they
      // differ only at the algebra level (navigate always carries an inner op).
      return existsSemiJoin(ctx, (op as { navigate: NavigationBody }).navigate, false, scope);
    case "exists":
      return existsSemiJoin(ctx, (op as { exists: NavigationBody }).exists, false, scope);
    case "notExists":
      return existsSemiJoin(ctx, (op as { notExists: NavigationBody }).notExists, true, scope);

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
interface NavigationBody {
  readonly rel: string;
  readonly op?: Operation;
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

/**
 * Lower a navigation filter (`navigate` / `exists` / `notExists`) to a correlated
 * `EXISTS` semi-join (M4). The child table is aliased with the next free alias
 * (`t1`, then `t2` for a nested hop) so the inner predicate — which references
 * the child entity by `Class.attr` — resolves against that alias. The correlation
 * predicate `t1.<childCol> = t0.<parentCol>` is derived mechanically from the
 * relationship join; the optional inner op (which may itself be a nested
 * navigation, giving multi-hop nested EXISTS) is appended with ` and `. A
 * `notExists` prepends `not ` to the whole semi-join (the canonical negated form).
 *
 * The correlation binds none; the inner op's binds (if any) accumulate in
 * traversal order, so an outer scalar bind composed via `and` lands after them.
 */
function existsSemiJoin(
  ctx: CompileCtx,
  body: NavigationBody,
  negated: boolean,
  parentAlias: string,
): string {
  const rel = ctx.schema.resolveRelationship(body.rel);
  // The child gets a fresh alias; the inner predicate is compiled in the CHILD's
  // scope, so a deeper nested navigation correlates back to THIS child (not the
  // root) — that is what produces `t2.order_item_id = t1.id` for a 2-hop EXISTS.
  const childAlias = nextAlias(ctx);
  registerAlias(ctx, rel.childTable, childAlias);
  const correlation = `${childAlias}.${rel.childColumn} = ${parentAlias}.${rel.parentColumn}`;
  let inner = correlation;
  if (body.op !== undefined) {
    const fragment = compilePredicate(body.op, ctx, childAlias);
    if (fragment !== undefined) {
      inner += ` and ${fragment}`;
    }
  }
  // As-of propagation (M4): a temporal semi-join child carries its OWN as-of
  // predicate. The root's pins propagate into it matched by axis, and any axis the
  // root left unpinned defaults to `now` (the per-entity default-injection rule), so
  // the EXISTS subquery reads the child as of the same instant(s) even when the root
  // omitted its as-of entirely (the default-now case `0335`). The child's as-of binds
  // land after its inner user bind and before the outer root as-of (left-to-right
  // placeholder order). A non-temporal child yields an empty fragment.
  const childAsOf = propagateChildAsOf(ctx, body.rel, childAlias);
  if (childAsOf !== undefined && childAsOf.sql !== "") {
    inner += ` and ${childAsOf.sql}`;
    ctx.binds.push(...childAsOf.binds);
  }
  const exists = `exists (select 1 from ${rel.childTable} ${childAlias} where ${inner})`;
  return negated ? `not ${exists}` : exists;
}

/**
 * The propagated child as-of fragment for a semi-join hop: the read's collected
 * pins applied to the CHILD entity's declared axes (matched by axis, each unpinned
 * axis defaulting to `now`), qualified with the child alias.
 *
 * The child is asked for its predicate **regardless of whether the root collected
 * any pins** — M7's default-injection rule is entity-local (each temporal read
 * derives its own as-of predicate), so a temporal child in the semi-join carries
 * its current-row predicate even when the root omitted its as-of (the default-now
 * case `0335`) or the root is non-temporal (a temporal child of a non-temporal root
 * defaults every axis to `now`, per M4). A non-temporal child resolves to no axes
 * and so yields an empty fragment, which the caller drops. `undefined` only when the
 * resolver is non-temporal (no `asOfPredicate` / `relatedEntityName`).
 */
function propagateChildAsOf(
  ctx: CompileCtx,
  relRef: string,
  childAlias: string,
): AsOfFragment | undefined {
  if (ctx.schema.asOfPredicate === undefined || ctx.schema.relatedEntityName === undefined) {
    return undefined;
  }
  const childEntity = ctx.schema.relatedEntityName(relRef);
  return ctx.schema.asOfPredicate(childEntity, childAlias, ctx.asOfPins);
}

/** Allocate the next fresh alias (`t${size}`) for a new correlation scope. */
function nextAlias(ctx: CompileCtx): string {
  return `t${ctx.aliases.size}`;
}

/** Register a freshly-allocated alias for a table so the inner predicate resolves it. */
function registerAlias(ctx: CompileCtx, table: string, alias: string): void {
  ctx.aliases.set(table, alias);
}

/** Join boolean operands with ` and ` / ` or `; binds follow left-to-right. */
function junction(
  ctx: CompileCtx,
  operands: readonly Operation[],
  connector: string,
  scope: string,
): string {
  return operands.map((operand) => requirePredicate(ctx, operand, scope)).join(` ${connector} `);
}

/**
 * Compile an inner operation that MUST be a predicate (a boolean operand). The
 * identities `all` / `none` are not legal operands of `and` / `or` / `not` /
 * `group` (they carry no predicate text), so a missing fragment is an error.
 */
function requirePredicate(ctx: CompileCtx, op: Operation, scope: string): string {
  const fragment = compilePredicate(op, ctx, scope);
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
 * Render one ORDER BY term for a sort key, consulting the dialect's NULL placement
 * (`dialect.orderByTerm`) **only** for a NULL-bearing column. The canonical
 * ordered-relationship rule (M4) sorts NULLs last on every key, but the two
 * dialects reach that order differently (Postgres `desc nulls last`; MariaDB a
 * leading `is null,` term for `asc`) — so a nullable key must go through the
 * dialect. A NOT-NULL key has no NULLs to place, so it emits the bare `<col>
 * asc|desc` form, which is byte-identical to the hand-authored goldens (the corpus
 * has no NULL-bearing `desc` key, so wiring the dialect in is a zero-diff change).
 */
function orderByTerm(
  ctx: CompileCtx,
  dialect: Dialect,
  key: { readonly attr: string; readonly direction?: string },
): string {
  const resolved = ctx.schema.resolveAttribute(key.attr);
  const column = `${aliasFor(ctx, resolved.table)}.${resolved.column}`;
  const direction = key.direction === "desc" ? "desc" : "asc";
  return resolved.nullable ? dialect.orderByTerm(column, direction) : `${column} ${direction}`;
}

/**
 * Append a literal to the binds accumulator, normalized to its canonical wire
 * form against the attribute's M0 neutral type (§3.2.1). Float-safe authored
 * numbers keep their JSON form; an int64 / decimal value the serde reader
 * preserved as an exact source string (precision-unsafe) becomes the canonical
 * wire string here.
 */
function pushBind(ctx: CompileCtx, value: Bind, type: string): void {
  ctx.binds.push(coerceBind(value, type));
}
