/**
 * `find(...)` → canonical m-op-algebra operation (spec §2.3, §2.9).
 *
 * Serializes a {@link Predicate} plus the read options (`orderBy`, `limit`,
 * `includes`/deep-fetch, and the temporal `asOf` / `range` / `history` axes)
 * into the single case `operation` tree the m-sql compiler consumes. This is the
 * one place the developer-facing surface and the conformance corpus meet: the
 * output equals the case `operation` byte-for-byte (`dsl.test.ts`).
 *
 * Directive nesting order matches the corpus goldens: the base predicate is
 * wrapped inside-out by `distinct` → `orderBy` → `limit` (`m-op-algebra-026`
 * limit-of-order-by-of-all), and the temporal axes wrap outermost with the
 * Valid Time **outside** Transaction Time (`m-temporal-read-013`, matching the
 * core bind order: Valid-Time binds before Transaction-Time binds).
 */
import { type Temporal, timestampToWire } from "@parallax/core";
import type {
  NavigationPath as NavigationPathRefs,
  Operation,
  OrderKey,
  TemporalCoordinate,
} from "@parallax/operation";
import { NavigationPath, OrderKeyExpression, Predicate } from "./expression.js";

/** The open-ended-row coordinate; distinct from a finite instant obtained from the clock. */
export const LATEST = "latest" as const;

/** A temporal coordinate: Latest or a finite instant (including explicit Now). */
export type TemporalPoint = Temporal.Instant | typeof LATEST;

/** A half-open temporal range `[start, end)` on one axis. */
export interface TemporalRange {
  readonly start: Temporal.Instant;
  readonly end: Temporal.Instant;
}

/** The core temporal axis names (not column names). */
export type TemporalAxis = "validTime" | "transactionTime";

/**
 * The temporal read options (spec §2.9). `asOf`, `range`, and `history` are
 * mutually exclusive per dimension; supplying a dimension the entity does not
 * declare is a validation error checked against the metamodel before execution.
 */
export interface TemporalReadOptions {
  readonly asOf?: {
    readonly validTime?: TemporalPoint;
    readonly transactionTime?: TemporalPoint;
  };
  readonly range?: {
    readonly validTime?: TemporalRange;
    readonly transactionTime?: TemporalRange;
  };
  readonly history?: readonly TemporalAxis[];
}

/** The non-temporal read options (spec §2.3). */
export interface FindOptions {
  /** Eager-fetch navigation set; longer paths imply their prefixes (spec §2.6). */
  readonly includes?: readonly NavigationPath[];
  /** Generated sort keys (`orderBy: [Order.qty.desc()]`, spec §2.7). */
  readonly orderBy?: readonly OrderKeyExpression[];
  /** Row cap, bound as `?` (`m-op-algebra-026`). */
  readonly limit?: number;
  /** Emit a `select distinct` (row-preserving over the full read projection; `m-read-lock-003`). */
  readonly distinct?: boolean;
  /** Temporal read axes (spec §2.9); serialized outermost. */
  readonly temporal?: TemporalReadOptions;
}

/** Serialize a temporal point to the core coordinate wire form. */
function temporalCoordinate(point: TemporalPoint): TemporalCoordinate {
  return point === LATEST ? LATEST : timestampToWire(point);
}

/**
 * Build the case `operation` for a `find(predicate, options)` call.
 *
 * The base is the predicate's operation (an unfiltered `find()` is
 * `Entity.all()`, so the caller passes an `all` predicate). Directives wrap the
 * base inside-out (`distinct`, then `orderBy`, then `limit`); a deep fetch wraps
 * the whole read in `deepFetch`; the temporal axes wrap outermost.
 */
export function buildFindOperation(predicate: Predicate, options: FindOptions = {}): Operation {
  let op: Operation = predicate.toOperation();

  // The temporal dimensions wrap the base predicate INNERMOST (Valid Time outside
  // Transaction Time), so the result directives (`distinct` / `orderBy` / `limit`)
  // wrap OUTSIDE them — matching the corpus `limit(orderBy(asOf(asOf(all))))`
  // ordering (`m-navigate-024`): a conforming compiler peels the directives before the
  // temporal wrappers on the root. Non-temporal reads are unaffected (temporal
  // is a no-op), so `m-op-algebra-026` stays `limit(orderBy(all))`.
  op = applyTemporal(op, options.temporal);

  if (options.distinct) {
    op = { distinct: { operand: op } };
  }
  if (options.orderBy && options.orderBy.length > 0) {
    const keys: readonly OrderKey[] = options.orderBy.map((k) => k.key);
    op = { orderBy: { operand: op, keys } };
  }
  if (options.limit !== undefined) {
    op = { limit: { operand: op, count: options.limit } };
  }

  if (options.includes && options.includes.length > 0) {
    // Each include is an ordered list of relationship refs; a deep-fetch path
    // segment is a closed `{ rel }` object (m-op-algebra), so wrap each ref.
    const paths: readonly NavigationPathRefs[] = options.includes.map((p) =>
      p.refs.map((rel) => ({ rel })),
    );
    op = { deepFetch: { operand: op, paths } };
  }
  return op;
}

/**
 * Wrap a read operand with the temporal axes (innermost, before the result
 * directives). An omitted declared dimension defaults to Latest; an explicit
 * Latest or finite `asOf`, a `range`, or a `history` dimension emits a wrapper.
 * Valid Time wraps outside Transaction Time so its binds come first.
 */
function applyTemporal(operand: Operation, temporal: TemporalReadOptions | undefined): Operation {
  if (!temporal) {
    return operand;
  }
  let op = operand;
  // Transaction Time (innermost), then Valid Time (outermost).
  op = applyAxis(op, "transactionTime", temporal);
  op = applyAxis(op, "validTime", temporal);
  return op;
}

/** Wrap one axis (`asOf` / `asOfRange` / `history`) if the caller requested it. */
function applyAxis(
  operand: Operation,
  axis: TemporalAxis,
  temporal: TemporalReadOptions,
): Operation {
  const asOf = temporal.asOf?.[axis];
  const range = temporal.range?.[axis];
  const history = temporal.history?.includes(axis) ?? false;
  if (asOf === undefined && range === undefined && !history) {
    return operand;
  }
  if (history) {
    return { history: { operand, dimension: axis } };
  }
  if (range !== undefined) {
    return {
      asOfRange: {
        operand,
        dimension: axis,
        start: timestampToWire(range.start),
        end: timestampToWire(range.end),
      },
    };
  }
  return {
    asOf: { operand, dimension: axis, coordinate: temporalCoordinate(asOf as TemporalPoint) },
  };
}

/** Re-export so the codegen'd factory can build include paths without a deep import. */
export { NavigationPath, OrderKeyExpression, Predicate };
