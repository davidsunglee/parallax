/**
 * `find(...)` → canonical M2 operation (spec §2.3, §2.9).
 *
 * Serializes a {@link Predicate} plus the read options (`orderBy`, `limit`,
 * `includes`/deep-fetch, and the temporal `asOf` / `range` / `history` axes)
 * into the single case `operation` tree the M3 compiler consumes. This is the
 * one place the developer-facing surface and the conformance corpus meet: the
 * output equals the case `operation` byte-for-byte (`dsl.test.ts`).
 *
 * Directive nesting order matches the corpus goldens: the base predicate is
 * wrapped inside-out by `distinct` → `orderBy` → `limit` (`0224`
 * limit-of-order-by-of-all), and the temporal axes wrap outermost with the
 * business axis **outside** the processing axis (`0801`, matching the core bind
 * order: business binds before processing).
 */
import { type Temporal, timestampToWire } from "@parallax/core";
import type {
  AsOfAttributeRef,
  NavigationPath as NavigationPathRefs,
  Operation,
  OrderKey,
  TemporalDate,
} from "@parallax/operation";
import { NavigationPath, OrderKeyExpression, Predicate } from "./expression.js";

/** The current-row token — serializes to the core `now` temporal pin (spec §2.9). */
export type TemporalPoint = Temporal.Instant | "now";

/** A half-open temporal range `[start, end)` on one axis. */
export interface TemporalRange {
  readonly start: Temporal.Instant;
  readonly end: Temporal.Instant;
}

/** The core temporal axis names (not column names). */
export type TemporalAxis = "processing" | "business";

/**
 * The temporal read options (spec §2.9). `asOf`, `range`, and `history` are
 * mutually exclusive per axis; supplying an axis the entity does not declare is
 * a validation error the caller (a typed `find`) is responsible for — the
 * serializer maps axis names to the entity's as-of-attribute refs it is given.
 */
export interface TemporalReadOptions {
  readonly asOf?: {
    readonly processing?: TemporalPoint;
    readonly business?: TemporalPoint;
  };
  readonly range?: {
    readonly processing?: TemporalRange;
    readonly business?: TemporalRange;
  };
  readonly history?: readonly TemporalAxis[];
}

/**
 * The as-of-attribute refs for an entity's declared axes, resolved by the typed
 * `find` from the metamodel (`processing` maps to the `axis: "processing"`
 * as-of-attribute's ref, `business` to the other). Absent axes are `undefined`.
 */
export interface AxisRefs {
  readonly processing?: AsOfAttributeRef;
  readonly business?: AsOfAttributeRef;
}

/** The non-temporal read options (spec §2.3). */
export interface FindOptions {
  /** Eager-fetch navigation set; longer paths imply their prefixes (spec §2.6). */
  readonly includes?: readonly NavigationPath[];
  /** Generated sort keys (`orderBy: [Order.qty.desc()]`, spec §2.7). */
  readonly orderBy?: readonly OrderKeyExpression[];
  /** Row cap, bound as `?` (`0224`). */
  readonly limit?: number;
  /** Emit a `select distinct` (`0226`). */
  readonly distinct?: boolean;
  /** Temporal read axes (spec §2.9); serialized outermost. */
  readonly temporal?: TemporalReadOptions;
  /** The entity's axis → as-of-attribute-ref mapping (supplied by the typed `find`). */
  readonly axisRefs?: AxisRefs;
}

/** Serialize a temporal point to the core temporal-date wire form. */
function temporalDate(point: TemporalPoint): TemporalDate {
  return point === "now" ? "now" : timestampToWire(point);
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

  // The temporal axes wrap the base predicate INNERMOST (business outside
  // processing), so the result directives (`distinct` / `orderBy` / `limit`)
  // wrap OUTSIDE them — matching the corpus `limit(orderBy(asOf(asOf(all))))`
  // ordering (`0336`): a conforming compiler peels the directives before the
  // temporal wrappers on the root. Non-temporal reads are unaffected (temporal
  // is a no-op), so `0224` stays `limit(orderBy(all))`.
  op = applyTemporal(op, options.temporal, options.axisRefs);

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
    const paths: readonly NavigationPathRefs[] = options.includes.map((p) => p.refs);
    op = { deepFetch: { operand: op, paths } };
  }
  return op;
}

/**
 * Wrap a read operand with the temporal axes (innermost, before the result
 * directives). Explicit-`now` and omitted axes are both left unwrapped for
 * `asOf` (the M7 default-injection rule reads an unwrapped axis as current); an
 * explicit non-`now` `asOf`, a `range`, or a `history` axis each emit their
 * wrapper. The business axis wraps outside the processing axis so business
 * binds precede processing binds (spec §2.9, `0801` / `0803`).
 */
function applyTemporal(
  operand: Operation,
  temporal: TemporalReadOptions | undefined,
  axisRefs: AxisRefs | undefined,
): Operation {
  if (!temporal) {
    return operand;
  }
  let op = operand;
  // Processing axis (innermost), then business axis (outermost).
  op = applyAxis(op, "processing", temporal, axisRefs);
  op = applyAxis(op, "business", temporal, axisRefs);
  return op;
}

/** Wrap one axis (`asOf` / `asOfRange` / `history`) if the caller requested it. */
function applyAxis(
  operand: Operation,
  axis: TemporalAxis,
  temporal: TemporalReadOptions,
  axisRefs: AxisRefs | undefined,
): Operation {
  const asOf = temporal.asOf?.[axis];
  const range = temporal.range?.[axis];
  const history = temporal.history?.includes(axis) ?? false;
  if (asOf === undefined && range === undefined && !history) {
    return operand;
  }
  const asOfAttr = axisRefs?.[axis];
  if (asOfAttr === undefined) {
    throw new Error(`temporal read names axis '${axis}' but the entity declares no such axis`);
  }
  if (history) {
    return { history: { operand, asOfAttr } };
  }
  if (range !== undefined) {
    return {
      asOfRange: {
        operand,
        asOfAttr,
        from: timestampToWire(range.start),
        to: timestampToWire(range.end),
      },
    };
  }
  // An explicit `now` still serializes to an `asOf … now` wrapper (spec §2.9:
  // `"now"` in an asOf option serializes to the core `now` pin — the corpus
  // `0502` authors it explicitly; an OMITTED axis is left unwrapped).
  return { asOf: { operand, asOfAttr, date: temporalDate(asOf as TemporalPoint) } };
}

/** Re-export so the codegen'd factory can build include paths without a deep import. */
export { NavigationPath, OrderKeyExpression, Predicate };
