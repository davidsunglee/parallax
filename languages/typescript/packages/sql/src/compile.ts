/**
 * The m-sql **canonical-by-construction** compile visitor (design Q2/Q3, Option A).
 *
 * The visitor switches on the operation's single discriminant tag and emits the
 * five m-sql normalization rules *directly* as it builds text — table aliases
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
 * table, quoted column, and m-core neutral type) and the entity's read projection
 * through an injected {@link SchemaResolver}, so `@parallax/sql` depends only on
 * `@parallax/operation` (the DAG forbids `sql → metamodel`). The runner builds the
 * resolver from the m-descriptor reader.
 */
import type { Dialect, ResolvedElementPredicate } from "@parallax/dialect";
import { type Operation, operationTag } from "@parallax/operation";
import { coerceBind } from "./bind.js";

/**
 * A resolved physical column: the table alias plus the quoted column name, ready
 * to splice into SQL as `<alias>.<column>`, plus the attribute's m-core neutral type
 * so the compiler can normalize a literal bound against it into the canonical
 * wire form (§3.2.1 — int64 / decimal beyond float-safe range become canonical
 * strings; everything else keeps its authored JSON form).
 */
export interface ResolvedColumn {
  /** The owning entity's table name (used to allocate / look up the alias). */
  readonly table: string;
  /** The dialect-quoted physical column name. */
  readonly column: string;
  /** The attribute's m-core neutral type (e.g. `int64`, `decimal(18,2)`, `string`). */
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
 * A resolved value-object nested path (`Class.vo.field…` / `Class.vo…` for
 * exists), against the declared recursive structure (m-value-object). The
 * top-level value object maps to one structured-document `column` on `table`;
 * `segments` is the document path AFTER the value-object name. `manyIndex` is the
 * index of the first `many` member crossed within the FULL nested path (the
 * top-level value object at index 0, then `segments`): `-1` for a to-one-only path
 * (a flat extraction), `0` for a top-level `many` value object (the document column
 * itself is the array — an empty `arrayPath`), and `k + 1` for a nested `many` at
 * `segments[k]`. A `manyIndex >= 0` path lowers to the array-traversal any-element
 * form. `leafIsAttribute` / `leafType` describe an attribute leaf (a comparison /
 * null / membership target); `leafIsMany` marks an exists path terminating at a
 * `many` value object.
 */
export interface ResolvedNestedPath {
  /** The owning entity's UNQUOTED physical table name (used to look up the root alias). */
  readonly table: string;
  /** The dialect-quoted structured-document column of the TOP-LEVEL value object. */
  readonly column: string;
  /** The document path segments after the value-object name (`['geo', 'country']`). */
  readonly segments: readonly string[];
  /**
   * Index of the first `many` member crossed within the full nested path (the
   * top-level value object at index 0): `-1` (all to-one), `0` (top-level `many` —
   * root array), or `k + 1` (a nested `many` at `segments[k]`).
   */
  readonly manyIndex: number;
  /** Whether the terminal segment resolves to a typed attribute (vs. a value-object member). */
  readonly leafIsAttribute: boolean;
  /** The terminal attribute's m-core neutral type, when `leafIsAttribute`. */
  readonly leafType?: string;
  /** Whether the terminal value-object member is `many` (an exists-over-array target). */
  readonly leafIsMany: boolean;
}

/**
 * A resolved relationship correlation, derived mechanically from the metamodel
 * `join` predicate (m-navigate — the user never writes a join). A navigation filter
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
  /**
   * The related (child) entity's UNQUOTED physical table name. The alias map is
   * keyed by this unquoted name (`registerAlias`/`aliasFor`), so the resolver must
   * NOT quote it; the EXISTS `from` emission site quotes it through
   * `ctx.dialect.quoteIdentifier` right before splicing it into SQL.
   */
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
 * free of a metamodel import. The runner implements this over the m-descriptor reader.
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
   * Resolve a value-object nested path (`Class.vo.field…`, or `Class.vo…`
   * terminating at a value object for exists) against the declared recursive
   * structure (m-value-object). Present only when the resolver supports value
   * objects (the nested predicate family probes for it and throws a clear error
   * when absent, mirroring the temporal-resolver probe).
   */
  resolveNested?(ref: string): ResolvedNestedPath;
  /**
   * The root entity's UNQUOTED physical table name (the `from` target). The alias
   * map is keyed by this unquoted name (`aliasFor`), so the resolver must NOT quote
   * it; `compile` quotes it through `dialect.quoteIdentifier` right before splicing
   * it into the `from` clause.
   */
  rootTable(): string;
  /**
   * The read projection columns for the root entity, in projection order. Each is
   * the quoted physical column plus its m-core type / output name, so a `bytes` column
   * can lower to the `encode(...)` hex form while every other type projects
   * verbatim (m-core scalar-serde projection).
   */
  rootProjection(): readonly ProjectionColumn[];
  /**
   * Resolve a `Class.asOfAttribute` reference (`Balance.processingDate`) to the
   * axis it pins. Used to key the collected as-of pins by axis. Present only when
   * the resolver supports temporal reads (m-temporal-read); the compiler probes for it.
   */
  resolveAsOfAxis?(ref: string): Axis;
  /** The root entity's domain class name (for the root as-of injection). */
  rootEntityName?(): string;
  /**
   * The injected as-of predicate for an entity's declared axes under a set of
   * pins, qualified with the given alias (the m-temporal-read default-injection + composition
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
 * projection position, so the byte payload materializes as stable hex text (m-core
 * scalar-serde projection — case `m-core-001`). The projection binds land BEFORE any
 * `where` binds, matching left-to-right placeholder order.
 */
export interface ProjectionColumn {
  /** The dialect-quoted physical column name (`payload`, `"order"`). */
  readonly column: string;
  /**
   * The attribute's m-core neutral type. A `bytes` type triggers the `encode(...)`
   * hex lowering; every other type (or `undefined`) projects the column verbatim.
   */
  readonly type?: string;
  /**
   * The output column name for a lowered projection (`payload_hex`). Only used by
   * the `bytes` `encode(...)` form, where the output name differs from the
   * physical column; a verbatim column's output name is the column itself.
   */
  readonly outputName?: string;
  /**
   * A value-object inner-field projection: the document path within `column` to
   * extract (m-value-object structured-column read — case `m-value-object-003`).
   * When present, the column is projected through the dialect's nested-extraction
   * form (`jsonb_extract_path_text(t0.address, ?) city` / `json_value(…)`) aliased
   * to `outputName` (defaulting to the leaf segment), with the path carried as a
   * `?` bind spliced in projection order.
   */
  readonly nested?: readonly string[];
}

/**
 * The mutable compile context threaded through one traversal: the schema
 * resolver, a first-appearance alias allocator, and the binds accumulator. The
 * as-of pins collected off the operation's temporal wrappers travel here too, so
 * a correlated-EXISTS semi-join can **propagate** them into its child subquery
 * (m-navigate as-of propagation across a temporal hop).
 */
export interface CompileCtx {
  readonly schema: SchemaResolver;
  /**
   * The injected {@link Dialect}, carried on the context so a deeply-nested
   * emission site (the EXISTS semi-join's child `from`, `existsSemiJoin`) can
   * route a table name through `dialect.quoteIdentifier` without threading a
   * separate parameter through the whole `compilePredicate` recursion.
   */
  readonly dialect: Dialect;
  /** table name → assigned alias (`t0`, `t1`, …), in first-appearance order. */
  readonly aliases: Map<string, string>;
  /** The binds accumulator, appended to in placeholder order. */
  readonly binds: Bind[];
  /** The as-of pins for this read, propagated into any temporal EXISTS child. */
  asOfPins: AxisPins;
}

/** Build a fresh compile context for a single operation. */
export function newCompileCtx(schema: SchemaResolver, dialect: Dialect): CompileCtx {
  return { schema, dialect, aliases: new Map(), binds: [], asOfPins: {} };
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
 * makes *during* assembly (the m-sql → m-dialect inversion): whether this read takes the
 * in-transaction shared read-lock, and (m-navigate propagation) the pre-seeded as-of pins.
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
   * Pre-seed the read's as-of pins before peeling — the m-deep-fetch deep-fetch propagation
   * path injects the root's pins (matched by axis) into a child level's temporal
   * predicate, so the child reads as of the same instant(s).
   */
  readonly seedPins?: AxisPins;
}

/**
 * Compile an m-op-algebra operation into **dialect-optimized** SQL plus its ordered binds,
 * against the injected {@link Dialect} contract (the m-sql → m-dialect edge).
 *
 * The result directives (`distinct`, `orderBy`, `limit`) wrap the predicate from
 * the outside; they are peeled first so they can lower into their fixed clause
 * positions (`distinct` on the `select`, `order by` after `where`, `limit` last).
 * The root table is aliased `t0` up front (it is the `from` target and so the
 * first table reference), then the inner operation lowers to a `where` predicate
 * (or none for `all`). Binds are accumulated in the same traversal — the limit
 * bind appends after any predicate binds, matching placeholder order.
 *
 * Every divergent fragment is routed through the `dialect`: the root/EXISTS-child
 * `from` table (`dialect.quoteIdentifier`, so a reserved physical table name like
 * MariaDB's `position` is quoted — the same identifier contract already applied to
 * every column), ORDER BY NULL placement (`dialect.orderByTerm`, for NULL-bearing
 * keys), the row-limit clause (`dialect.rowLimit`), and — the final in-compile step
 * — the in-transaction shared read-lock (`dialect.applyReadLock`, gated on
 * `exec.locking`; `compile` already knows whether it emitted `distinct`, so the
 * projection flag needs no regex). The emitted SQL still carries canonical `?`
 * placeholders; the adapter translates them to the driver's syntax at the boundary.
 *
 * `exec.seedPins` pre-seeds the read's as-of pins before peeling — the m-deep-fetch deep-fetch
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
  const ctx = newCompileCtx(schema, dialect);
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
  // before the `where` in the statement, so its `?` is left-most (m-sql placeholder
  // order). A plain column emits no bind; a `bytes` column emits `'hex'` here.
  const projection = renderProjection(schema.rootProjection(), alias, ctx, dialect);
  const select = directives.distinct ? `select distinct ${projection}` : `select ${projection}`;

  // Compile the user predicate FIRST so its binds precede the injected as-of binds
  // and the trailing `limit` bind (left-to-right placeholder order).
  const userWhere = compilePredicate(base, ctx);
  // The injected as-of term is appended AFTER the user predicate (m-temporal-read): its binds
  // land after the user binds. Default-injection + axis composition are owned by
  // the resolver (delegating to `@parallax/bitemporal`); a non-temporal entity or
  // an all-`history` read yields an empty fragment.
  const asOf = injectRootAsOf(ctx, alias);
  const where = combineWhere(userWhere, asOf?.sql);

  if (directives.limit !== undefined) {
    ctx.binds.push(directives.limit);
  }

  // The root table name routes through the dialect's identifier quoting (the m-sql →
  // m-dialect identifier contract already applied to every column) so a reserved word
  // (MariaDB's `position`) is quoted; Postgres's reserved set excludes every
  // corpus table, so this is byte-identical there.
  let sql = `${select} from ${dialect.quoteIdentifier(table)} ${alias}`;
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
  // The in-transaction shared read-lock is the FINAL in-compile step (m-read-lock automatic
  // read-lock correctness, owned by m-dialect): the dialect decides whether/where/how it
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
 * form (the m-core scalar-serde projection — `m-core-001`). A lowered column pushes its
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
  if (column.nested !== undefined) {
    // A value-object inner-field projection lowers through the dialect's
    // nested-extraction form (per-dialect bind shape), aliased to the output name.
    // The extraction bind lands here in projection order (before any `where` binds).
    const extraction = dialect.nestedExtraction(qualified, column.nested);
    for (const bind of extraction.binds) {
      ctx.binds.push(bind as Bind);
    }
    const output = column.outputName ?? (column.nested[column.nested.length - 1] as string);
    return `${extraction.sql} ${output}`;
  }
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
      const body = (
        current as {
          asOf: { operand: Operation; asOfAttr: string; date: string };
        }
      ).asOf;
      recordPin(ctx, body.asOfAttr, temporalPinForDate(body.date));
      current = body.operand;
      continue;
    }
    if (tag === "asOfRange") {
      const body = (
        current as {
          asOfRange: {
            operand: Operation;
            asOfAttr: string;
            from: string;
            to: string;
          };
        }
      ).asOfRange;
      recordPin(ctx, body.asOfAttr, {
        kind: "range",
        from: body.from,
        to: body.to,
      });
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
          orderBy: {
            operand: Operation;
            keys: readonly { attr: string; direction?: string }[];
          };
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
      // two inline literals the m-sql normalizer keeps (it is not a bind).
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
      // A navigation FILTER is the positive semi-join (m-navigate): keep parent rows for
      // which a correlated related row (optionally satisfying the inner op)
      // exists. `navigate` and `exists` lower to the identical EXISTS form; they
      // differ only at the algebra level (navigate always carries an inner op).
      return existsSemiJoin(ctx, (op as { navigate: NavigationBody }).navigate, false, scope);
    case "exists":
      return existsSemiJoin(ctx, (op as { exists: NavigationBody }).exists, false, scope);
    case "notExists":
      return existsSemiJoin(ctx, (op as { notExists: NavigationBody }).notExists, true, scope);

    // --- value-object nested predicates (m-value-object / m-op-algebra) ------
    case "nestedEq":
      return nestedComparison(ctx, (op as { nestedEq: NestedComparisonBody }).nestedEq, EQ);
    case "nestedNotEq":
      return nestedComparison(
        ctx,
        (op as { nestedNotEq: NestedComparisonBody }).nestedNotEq,
        NOT_EQ,
      );
    case "nestedGt":
      return nestedComparison(ctx, (op as { nestedGt: NestedComparisonBody }).nestedGt, GT);
    case "nestedGte":
      return nestedComparison(ctx, (op as { nestedGte: NestedComparisonBody }).nestedGte, GTE);
    case "nestedLt":
      return nestedComparison(ctx, (op as { nestedLt: NestedComparisonBody }).nestedLt, LT);
    case "nestedLte":
      return nestedComparison(ctx, (op as { nestedLte: NestedComparisonBody }).nestedLte, LTE);
    case "nestedIn":
      return nestedMembership(ctx, (op as { nestedIn: NestedMembershipBody }).nestedIn);
    case "nestedIsNull":
      return nestedNull(ctx, (op as { nestedIsNull: NestedNullBody }).nestedIsNull, false);
    case "nestedIsNotNull":
      return nestedNull(ctx, (op as { nestedIsNotNull: NestedNullBody }).nestedIsNotNull, true);
    case "nestedExists":
      return nestedExists(ctx, (op as { nestedExists: NestedExistsBody }).nestedExists, false);
    case "nestedNotExists":
      return nestedExists(ctx, (op as { nestedNotExists: NestedExistsBody }).nestedNotExists, true);

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

/** `{ path, value }` — a flat nested comparison (`nestedEq` … `nestedLte`). */
interface NestedComparisonBody {
  readonly path: string;
  readonly value: Bind;
}
/** `{ path, values }` — `nestedIn`. */
interface NestedMembershipBody {
  readonly path: string;
  readonly values: readonly Bind[];
}
/** `{ path }` — `nestedIsNull` / `nestedIsNotNull`. */
interface NestedNullBody {
  readonly path: string;
}
/** `{ path, where? }` — `nestedExists` / `nestedNotExists` (the `where` is element-scoped). */
interface NestedExistsBody {
  readonly path: string;
  readonly where?: Record<string, unknown>;
}

/**
 * A flat nested comparison descriptor: the SQL operator, the equivalent
 * element-scope op (for an any-element predicate through a `many` segment), and
 * whether the whole predicate is negated (a leading `not`, `nestedNotEq`). Every
 * comparison casts the text extraction to the declared leaf type before comparing
 * (m-sql / m-dialect typed-cast form) — a no-op for a text leaf — so no per-operator
 * cast flag is needed.
 */
interface FlatNestedOp {
  readonly sqlOp: string;
  readonly elementOp: "eq" | "notEq" | "gt" | "gte" | "lt" | "lte";
  readonly negated: boolean;
}
const EQ: FlatNestedOp = { sqlOp: "=", elementOp: "eq", negated: false };
const NOT_EQ: FlatNestedOp = { sqlOp: "=", elementOp: "notEq", negated: true };
const GT: FlatNestedOp = { sqlOp: ">", elementOp: "gt", negated: false };
const GTE: FlatNestedOp = { sqlOp: ">=", elementOp: "gte", negated: false };
const LT: FlatNestedOp = { sqlOp: "<", elementOp: "lt", negated: false };
const LTE: FlatNestedOp = { sqlOp: "<=", elementOp: "lte", negated: false };

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
function escapeLikeLiteral(value: string): {
  pattern: string;
  usedEscape: boolean;
} {
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
 * `EXISTS` semi-join (m-navigate). The child table is aliased with the next free alias
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
  // As-of propagation (m-navigate): a temporal semi-join child carries its OWN as-of
  // predicate. The root's pins propagate into it matched by axis, and any axis the
  // root left unpinned defaults to `now` (the per-entity default-injection rule), so
  // the EXISTS subquery reads the child as of the same instant(s) even when the root
  // omitted its as-of entirely (the default-now case `m-navigate-023`). The child's as-of binds
  // land after its inner user bind and before the outer root as-of (left-to-right
  // placeholder order). A non-temporal child yields an empty fragment.
  const childAsOf = propagateChildAsOf(ctx, body.rel, childAlias);
  if (childAsOf !== undefined && childAsOf.sql !== "") {
    inner += ` and ${childAsOf.sql}`;
    ctx.binds.push(...childAsOf.binds);
  }
  // The child table name routes through the dialect too (`ctx.dialect`, since this
  // emission site sits deep inside the recursive `compilePredicate` chain, which
  // carries no separate `dialect` parameter) — the same identifier contract as the
  // root `from` above.
  const exists = `exists (select 1 from ${ctx.dialect.quoteIdentifier(rel.childTable)} ${childAlias} where ${inner})`;
  return negated ? `not ${exists}` : exists;
}

/**
 * The propagated child as-of fragment for a semi-join hop: the read's collected
 * pins applied to the CHILD entity's declared axes (matched by axis, each unpinned
 * axis defaulting to `now`), qualified with the child alias.
 *
 * The child is asked for its predicate **regardless of whether the root collected
 * any pins** — m-temporal-read's default-injection rule is entity-local (each temporal read
 * derives its own as-of predicate), so a temporal child in the semi-join carries
 * its current-row predicate even when the root omitted its as-of (the default-now
 * case `m-navigate-023`) or the root is non-temporal (a temporal child of a non-temporal root
 * defaults every axis to `now`, per m-navigate). A non-temporal child resolves to no axes
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

// --- value-object nested predicates (m-value-object / m-op-algebra) ----------

/**
 * Resolve a value-object nested path against the model-aware resolver, throwing a
 * clear error when the resolver is not value-object-capable (mirroring the
 * temporal-resolver probe). The `rejected` cases' model-aware refusal is a
 * SEPARATE pre-SQL validation pass (`@parallax/operation`); by the time an
 * operation reaches `compile`, its paths resolve.
 */
function requireNested(ctx: CompileCtx, path: string): ResolvedNestedPath {
  if (ctx.schema.resolveNested === undefined) {
    throw new Error(
      "compile: nested value-object predicates require a value-object-capable SchemaResolver",
    );
  }
  return ctx.schema.resolveNested(path);
}

/** The alias-qualified structured-document column a nested path reads (`t0.address`). */
function nestedColumn(ctx: CompileCtx, resolved: ResolvedNestedPath): string {
  return `${aliasFor(ctx, resolved.table)}.${resolved.column}`;
}

/** The declared leaf type, defaulting to `string` (a value object's default text compare). */
function leafType(resolved: ResolvedNestedPath): string {
  return resolved.leafType ?? "string";
}

/**
 * Emit the dialect's nested extraction for a to-one path, pushing its path binds
 * (per-segment on Postgres, one `'$.a.b'` on MariaDB) onto the accumulator in
 * order, and return the extraction SQL fragment.
 */
function pushExtraction(ctx: CompileCtx, resolved: ResolvedNestedPath): string {
  const extraction = ctx.dialect.nestedExtraction(nestedColumn(ctx, resolved), resolved.segments);
  for (const bind of extraction.binds) {
    ctx.binds.push(bind as Bind);
  }
  return extraction.sql;
}

/**
 * The document path reaching (and including) the first `many` member. `manyIndex`
 * counts the full nested path with the top-level value object at index 0, so a
 * nested `many` at `segments[k]` (`manyIndex === k + 1`) yields `segments[0..k]`,
 * and a top-level `many` (`manyIndex === 0`) yields the EMPTY path — the document
 * column itself is the array (root array).
 */
function arrayPathOf(resolved: ResolvedNestedPath): readonly string[] {
  return resolved.segments.slice(0, resolved.manyIndex);
}

/**
 * The element-relative path AFTER the first `many` member. For a top-level `many`
 * (`manyIndex === 0`) this is the whole of `segments` — the leaves are relative to
 * the array element root.
 */
function elementPathOf(resolved: ResolvedNestedPath): readonly string[] {
  return resolved.segments.slice(resolved.manyIndex);
}

/**
 * Lower a flat nested comparison (`nestedEq` … `nestedLte`). A to-one path lowers
 * to a scalar extraction (`<extraction> = ?`, a range operator casting first); a
 * path crossing a `many` segment lowers to the any-element array-traversal form
 * (the same operator applied to one element).
 */
function nestedComparison(ctx: CompileCtx, body: NestedComparisonBody, flat: FlatNestedOp): string {
  const resolved = requireNested(ctx, body.path);
  const type = leafType(resolved);
  if (resolved.manyIndex >= 0) {
    const element: ResolvedElementPredicate = {
      op: flat.elementOp,
      path: elementPathOf(resolved),
      value: coerceBind(body.value, type),
      valueType: type,
    };
    return emitArrayPredicate(ctx, resolved, arrayPathOf(resolved), element, false);
  }
  const extraction = pushExtraction(ctx, resolved);
  // Every nested comparison casts the text extraction to the declared leaf type
  // before comparing (m-sql / m-dialect typed-cast form), not just the range ops:
  // `typedCast` is a no-op for a string/text leaf (so string goldens stay
  // byte-identical) and a real cast for a numeric one, so a numeric `nestedEq` /
  // `nestedNotEq` compares against a correctly-typed extraction. A boolean leaf has
  // no specified cast and compares as JSON text (see `nestedComparisonBind`).
  const target = ctx.dialect.typedCast(extraction, type);
  ctx.binds.push(nestedComparisonBind(body.value, type));
  const predicate = `${target} ${flat.sqlOp} ?`;
  return flat.negated ? `not ${predicate}` : predicate;
}

/** Lower `nestedIn` — a to-one `<extraction> in (?, …)`, or an any-element membership. */
function nestedMembership(ctx: CompileCtx, body: NestedMembershipBody): string {
  const resolved = requireNested(ctx, body.path);
  const type = leafType(resolved);
  if (resolved.manyIndex >= 0) {
    const element: ResolvedElementPredicate = {
      op: "in",
      path: elementPathOf(resolved),
      values: body.values.map((value) => coerceBind(value, type)),
      valueType: type,
    };
    return emitArrayPredicate(ctx, resolved, arrayPathOf(resolved), element, false);
  }
  const extraction = pushExtraction(ctx, resolved);
  // A nested membership casts the extraction to the declared leaf type too (no-op for
  // a string leaf; a real cast for a numeric one; a boolean compares as JSON text),
  // so `<cast> in (?, …)` is a valid typed membership rather than a text/number mix.
  const target = ctx.dialect.typedCast(extraction, type);
  const placeholders = body.values
    .map((value) => {
      ctx.binds.push(nestedComparisonBind(value, type));
      return "?";
    })
    .join(", ");
  return `${target} in (${placeholders})`;
}

/** Lower `nestedIsNull` / `nestedIsNotNull` — the presence collapse over an extraction. */
function nestedNull(ctx: CompileCtx, body: NestedNullBody, negated: boolean): string {
  const resolved = requireNested(ctx, body.path);
  if (resolved.manyIndex >= 0) {
    const element: ResolvedElementPredicate = {
      op: negated ? "isNotNull" : "isNull",
      path: elementPathOf(resolved),
    };
    return emitArrayPredicate(ctx, resolved, arrayPathOf(resolved), element, false);
  }
  const predicate = `${pushExtraction(ctx, resolved)} is null`;
  return negated ? `not ${predicate}` : predicate;
}

/**
 * Lower `nestedExists` / `nestedNotExists` over a to-many value object: a non-empty
 * test (no `where`) or a same-element scoped compound (one element satisfies the
 * whole `where`). Only a `many`-terminated path is lowered — a to-one presence
 * exists has no golden in this phase.
 */
function nestedExists(ctx: CompileCtx, body: NestedExistsBody, negated: boolean): string {
  const resolved = requireNested(ctx, body.path);
  if (resolved.leafIsAttribute || !resolved.leafIsMany) {
    throw new Error(
      `compile: nestedExists/nestedNotExists on '${body.path}' must terminate at a to-many ` +
        `value object (to-one presence is unsupported in this phase)`,
    );
  }
  const element =
    body.where === undefined ? undefined : resolveElementPredicate(ctx, body.path, body.where);
  return emitArrayPredicate(ctx, resolved, resolved.segments, element, negated);
}

/**
 * Allocate the element alias for a to-many traversal (Postgres's unnest alias;
 * unused by MariaDB's containment family) and hand the request to the dialect's
 * array-traversal form, pushing its per-dialect binds in order. Two independent
 * any-element predicates in one `and` therefore get `t1` and `t2` (the alias
 * counter advances per call).
 */
function emitArrayPredicate(
  ctx: CompileCtx,
  resolved: ResolvedNestedPath,
  arrayPath: readonly string[],
  element: ResolvedElementPredicate | undefined,
  negated: boolean,
): string {
  const column = nestedColumn(ctx, resolved);
  const alias = nextAlias(ctx);
  registerAlias(ctx, `__vo_element_${alias}`, alias);
  const result = ctx.dialect.nestedArrayPredicate({
    column,
    arrayPath,
    elementAlias: alias,
    negated,
    ...(element === undefined ? {} : { element }),
  });
  for (const bind of result.binds) {
    ctx.binds.push(bind as Bind);
  }
  return result.sql;
}

/**
 * Resolve an element-scoped `where` sub-predicate (element-relative paths) into the
 * dialect-neutral {@link ResolvedElementPredicate} the array-traversal form
 * renders: each leaf's element-relative path + literal type resolves against the
 * `many` member (`baseRef` is the value-object-terminated exists path), and values
 * are coerced to their wire form. The dialect decides how to lower it (Postgres
 * general; MariaDB the equality-only containment candidate).
 */
function resolveElementPredicate(
  ctx: CompileCtx,
  baseRef: string,
  node: Record<string, unknown>,
): ResolvedElementPredicate {
  const tag = operationTag(node as unknown as Operation);
  switch (tag) {
    case "nestedEq":
      return elementComparison(ctx, baseRef, node.nestedEq as NestedComparisonBody, "eq");
    case "nestedNotEq":
      return elementComparison(ctx, baseRef, node.nestedNotEq as NestedComparisonBody, "notEq");
    case "nestedGt":
      return elementComparison(ctx, baseRef, node.nestedGt as NestedComparisonBody, "gt");
    case "nestedGte":
      return elementComparison(ctx, baseRef, node.nestedGte as NestedComparisonBody, "gte");
    case "nestedLt":
      return elementComparison(ctx, baseRef, node.nestedLt as NestedComparisonBody, "lt");
    case "nestedLte":
      return elementComparison(ctx, baseRef, node.nestedLte as NestedComparisonBody, "lte");
    case "nestedIn": {
      const body = node.nestedIn as NestedMembershipBody;
      const type = elementLeafType(ctx, baseRef, body.path);
      return {
        op: "in",
        path: body.path.split("."),
        values: body.values.map((value) => coerceBind(value, type)),
        valueType: type,
      };
    }
    case "nestedIsNull":
      return {
        op: "isNull",
        path: (node.nestedIsNull as NestedNullBody).path.split("."),
      };
    case "nestedIsNotNull":
      return {
        op: "isNotNull",
        path: (node.nestedIsNotNull as NestedNullBody).path.split("."),
      };
    case "and":
    case "or":
      return {
        op: tag,
        operands: ((node[tag] as { operands: Record<string, unknown>[] }).operands ?? []).map(
          (operand) => resolveElementPredicate(ctx, baseRef, operand),
        ),
      };
    case "not":
    case "group":
      return {
        op: tag,
        operand: resolveElementPredicate(
          ctx,
          baseRef,
          (node[tag] as { operand: Record<string, unknown> }).operand,
        ),
      };
    default:
      throw new Error(`compile: unsupported element predicate '${tag}' in a scoped 'where'`);
  }
}

/** Resolve one element-relative comparison leaf into a typed {@link ResolvedElementPredicate}. */
function elementComparison(
  ctx: CompileCtx,
  baseRef: string,
  body: NestedComparisonBody,
  op: "eq" | "notEq" | "gt" | "gte" | "lt" | "lte",
): ResolvedElementPredicate {
  const type = elementLeafType(ctx, baseRef, body.path);
  return {
    op,
    path: body.path.split("."),
    value: coerceBind(body.value, type),
    valueType: type,
  };
}

/**
 * The declared neutral type of an element-relative leaf: resolve
 * `<arrayMemberRef>.<elementPath>` as a full nested path (`Customer.address.phones`
 * + `type` = `Customer.address.phones.type`) and read its leaf type.
 */
function elementLeafType(ctx: CompileCtx, baseRef: string, elementPath: string): string {
  return leafType(requireNested(ctx, `${baseRef}.${elementPath}`));
}

/**
 * Render one ORDER BY term for a sort key, consulting the dialect's NULL placement
 * (`dialect.orderByTerm`) **only** for a NULL-bearing column. The canonical
 * ordered-relationship rule (m-navigate) sorts NULLs last on every key, but the two
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
 * form against the attribute's m-core neutral type (§3.2.1). Float-safe authored
 * numbers keep their JSON form; an int64 / decimal value the serde reader
 * preserved as an exact source string (precision-unsafe) becomes the canonical
 * wire string here.
 */
function pushBind(ctx: CompileCtx, value: Bind, type: string): void {
  ctx.binds.push(coerceBind(value, type));
}

/**
 * The wire form of a nested value-object comparison literal. A numeric or `decimal`
 * leaf coerces through the ordinary {@link coerceBind} (and the extraction is cast to
 * the matching neutral type). A **boolean** leaf is the one type m-dialect specifies
 * NO cast for (the typed-cast table lists only int / float / decimal), so — rather
 * than invent an unspecified cast — the boolean compares against its JSON-text form
 * (`'true'` / `'false'`): both dialect extractions (`jsonb_extract_path_text` /
 * `json_value`) yield the JSON text `'true'` / `'false'` for a stored JSON boolean,
 * so `<extraction> = ?` stays a valid text-to-text comparison (and the absence
 * collapse still holds — a NULL extraction is neither `'true'` nor `'false'`).
 */
function nestedComparisonBind(value: Bind, type: string): Bind {
  if (type === "boolean" && typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return coerceBind(value, type);
}
