/**
 * The M2 operation data model — a tree of **single-key tagged objects**, where
 * the one key names the kind (design Q3, Option A). The wire form and the
 * in-memory form are *identical*, so serde round-trips trivially through
 * `@parallax/serde` and the compile visitor (Phase 3+) switches on the tag.
 *
 * These types mirror `core/schemas/operation.schema.json` one-to-one; ajv
 * (`schema.ts`) remains the source of truth for validation. The types give the
 * compile visitor exhaustive, discriminated access without re-deriving the
 * schema.
 */
import { assertValidOperation } from "./schema.js";

// --- operand reference primitives ------------------------------------------

/** `Class.attribute` — a metamodel attribute reference. */
export type AttributeRef = string;
/** `Class.relationship` — a metamodel relationship reference. */
export type RelationshipRef = string;
/** `Class.asOfAttribute` — a metamodel as-of-attribute reference. */
export type AsOfAttributeRef = string;
/** `Class.valueObject.field[.field…]` — a nested value-object field reference. */
export type NestedRef = string;
/** A scalar literal usable as a bind. */
export type Literal = string | number | boolean | null;
/** An ISO-8601 UTC instant, or the keyword `now`. */
export type TemporalDate = string;
/** An ordered list of relationship refs naming one eager-fetch path. */
export type NavigationPath = readonly RelationshipRef[];

/** An order-by key: an attribute plus an optional direction (default `asc`). */
export interface OrderKey {
  readonly attr: AttributeRef;
  readonly direction?: "asc" | "desc";
}

// --- shared operand bodies -------------------------------------------------

/** `{ attr, value }` — the body of the comparison predicates. */
export interface Comparison {
  readonly attr: AttributeRef;
  readonly value: Literal;
}

/** `{ attr, lower, upper }` — the body of `between`. */
export interface BetweenBody {
  readonly attr: AttributeRef;
  readonly lower: Literal;
  readonly upper: Literal;
}

/** `{ attr }` — the body of the null checks. */
export interface NullCheck {
  readonly attr: AttributeRef;
}

/** `{ attr, value, caseInsensitive? }` — the body of the string predicates. */
export interface StringMatch {
  readonly attr: AttributeRef;
  readonly value: string;
  readonly caseInsensitive?: boolean;
}

/** `{ attr, values }` — the body of the membership predicates. */
export interface Membership {
  readonly attr: AttributeRef;
  readonly values: readonly Literal[];
}

/** `{ operands }` — the body of the boolean junctions (`and` / `or`). */
export interface Junction {
  readonly operands: readonly Operation[];
}

/** `{ operand }` — the body of the unary wrappers (`not` / `group` / `distinct`). */
export interface Unary {
  readonly operand: Operation;
}

/** `{ rel, op? }` — the body of the navigation filters. */
export interface NavigationFilter {
  readonly rel: RelationshipRef;
  readonly op?: Operation;
}

/** `{ path, value }` — the body of the nested value-object comparisons. */
export interface NestedComparison {
  readonly path: NestedRef;
  readonly value: string;
}

// --- identity --------------------------------------------------------------

export interface AllOp {
  readonly all: Record<string, never>;
}
export interface NoneOp {
  readonly none: Record<string, never>;
}

// --- comparison ------------------------------------------------------------

export interface EqOp {
  readonly eq: Comparison;
}
export interface NotEqOp {
  readonly notEq: Comparison;
}
export interface GreaterThanOp {
  readonly greaterThan: Comparison;
}
export interface GreaterThanEqualsOp {
  readonly greaterThanEquals: Comparison;
}
export interface LessThanOp {
  readonly lessThan: Comparison;
}
export interface LessThanEqualsOp {
  readonly lessThanEquals: Comparison;
}
export interface BetweenOp {
  readonly between: BetweenBody;
}

// --- null ------------------------------------------------------------------

export interface IsNullOp {
  readonly isNull: NullCheck;
}
export interface IsNotNullOp {
  readonly isNotNull: NullCheck;
}

// --- string ----------------------------------------------------------------

export interface LikeOp {
  readonly like: StringMatch;
}
export interface NotLikeOp {
  readonly notLike: StringMatch;
}
export interface StartsWithOp {
  readonly startsWith: StringMatch;
}
export interface EndsWithOp {
  readonly endsWith: StringMatch;
}
export interface ContainsOp {
  readonly contains: StringMatch;
}

// --- membership ------------------------------------------------------------

export interface InOp {
  readonly in: Membership;
}
export interface NotInOp {
  readonly notIn: Membership;
}

// --- boolean ---------------------------------------------------------------

export interface AndOp {
  readonly and: Junction;
}
export interface OrOp {
  readonly or: Junction;
}
export interface NotOp {
  readonly not: Unary;
}
export interface GroupOp {
  readonly group: Unary;
}

// --- directives ------------------------------------------------------------

export interface OrderByOp {
  readonly orderBy: {
    readonly operand: Operation;
    readonly keys: readonly OrderKey[];
  };
}
export interface LimitOp {
  readonly limit: {
    readonly operand: Operation;
    readonly count: number;
  };
}
export interface DistinctOp {
  readonly distinct: Unary;
}

// --- navigation ------------------------------------------------------------

export interface NavigateOp {
  readonly navigate: NavigationFilter;
}
export interface ExistsOp {
  readonly exists: NavigationFilter;
}
export interface NotExistsOp {
  readonly notExists: NavigationFilter;
}

// --- deep fetch ------------------------------------------------------------

export interface DeepFetchOp {
  readonly deepFetch: {
    readonly operand: Operation;
    readonly paths: readonly NavigationPath[];
  };
}

// --- aggregation -----------------------------------------------------------

/** `{ attr, as }` — an aggregate over a named attribute. */
export interface AggregateBody {
  readonly attr: AttributeRef;
  readonly as: string;
}
/** `{ attr?, as }` — `count(attr)` or `count(*)` when `attr` is omitted. */
export interface CountBody {
  readonly attr?: AttributeRef;
  readonly as: string;
}
export type AggregateFunction =
  | { readonly sum: AggregateBody }
  | { readonly avg: AggregateBody }
  | { readonly count: CountBody }
  | { readonly min: AggregateBody }
  | { readonly max: AggregateBody }
  | { readonly stdDevSample: AggregateBody }
  | { readonly stdDevPop: AggregateBody }
  | { readonly varianceSample: AggregateBody }
  | { readonly variancePop: AggregateBody };

/** `{ agg, value }` — an aggregate compared against a literal (a having leaf). */
export interface HavingComparison {
  readonly agg: AggregateFunction;
  readonly value: Literal;
}
export type HavingExpression =
  | { readonly eq: HavingComparison }
  | { readonly notEq: HavingComparison }
  | { readonly gt: HavingComparison }
  | { readonly gte: HavingComparison }
  | { readonly lt: HavingComparison }
  | { readonly lte: HavingComparison }
  | { readonly and: { readonly operands: readonly HavingExpression[] } }
  | { readonly or: { readonly operands: readonly HavingExpression[] } };

export interface GroupByOp {
  readonly groupBy: {
    readonly operand: Operation;
    readonly keys?: readonly AttributeRef[];
    readonly aggregates: readonly AggregateFunction[];
    readonly having?: HavingExpression;
  };
}

// --- temporal --------------------------------------------------------------

export interface AsOfOp {
  readonly asOf: {
    readonly operand: Operation;
    readonly asOfAttr: AsOfAttributeRef;
    readonly date: TemporalDate;
  };
}
export interface AsOfRangeOp {
  readonly asOfRange: {
    readonly operand: Operation;
    readonly asOfAttr: AsOfAttributeRef;
    readonly from: TemporalDate;
    readonly to: TemporalDate;
  };
}
export interface HistoryOp {
  readonly history: {
    readonly operand: Operation;
    readonly asOfAttr: AsOfAttributeRef;
  };
}

// --- value-object access ---------------------------------------------------

export interface NestedEqOp {
  readonly nestedEq: NestedComparison;
}
export interface NestedNotEqOp {
  readonly nestedNotEq: NestedComparison;
}

/**
 * The full M2 operation algebra as a discriminated union. The single key on
 * each node is its discriminant; the compile visitor switches on it.
 */
export type Operation =
  | AllOp
  | NoneOp
  | EqOp
  | NotEqOp
  | GreaterThanOp
  | GreaterThanEqualsOp
  | LessThanOp
  | LessThanEqualsOp
  | BetweenOp
  | IsNullOp
  | IsNotNullOp
  | LikeOp
  | NotLikeOp
  | StartsWithOp
  | EndsWithOp
  | ContainsOp
  | InOp
  | NotInOp
  | AndOp
  | OrOp
  | NotOp
  | GroupOp
  | OrderByOp
  | LimitOp
  | DistinctOp
  | NavigateOp
  | ExistsOp
  | NotExistsOp
  | DeepFetchOp
  | GroupByOp
  | AsOfOp
  | AsOfRangeOp
  | HistoryOp
  | NestedEqOp
  | NestedNotEqOp;

/** The discriminant key names, one per operation kind. */
export type OperationTag = keyof (AllOp &
  NoneOp &
  EqOp &
  NotEqOp &
  GreaterThanOp &
  GreaterThanEqualsOp &
  LessThanOp &
  LessThanEqualsOp &
  BetweenOp &
  IsNullOp &
  IsNotNullOp &
  LikeOp &
  NotLikeOp &
  StartsWithOp &
  EndsWithOp &
  ContainsOp &
  InOp &
  NotInOp &
  AndOp &
  OrOp &
  NotOp &
  GroupOp &
  OrderByOp &
  LimitOp &
  DistinctOp &
  NavigateOp &
  ExistsOp &
  NotExistsOp &
  DeepFetchOp &
  GroupByOp &
  AsOfOp &
  AsOfRangeOp &
  HistoryOp &
  NestedEqOp &
  NestedNotEqOp);

/**
 * Extract the single discriminant tag of an operation node. Every operation is
 * a single-key tagged object, so the tag is its only own key.
 */
export function operationTag(op: Operation): OperationTag {
  const keys = Object.keys(op);
  if (keys.length !== 1) {
    throw new Error(
      `operation node must have exactly one key, found ${keys.length}: ${keys.join(", ")}`,
    );
  }
  return keys[0] as OperationTag;
}

/**
 * Parse an arbitrary value into a validated `Operation`. ajv enforces the
 * single-key tagged shape and the per-kind body, so the cast is sound.
 */
export function parseOperation(value: unknown): Operation {
  return assertValidOperation(value) as Operation;
}
