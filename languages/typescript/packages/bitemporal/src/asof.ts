/**
 * m-temporal-read as-of predicate injection — the pure derivation the temporal read + deep-fetch
 * propagation paths share.
 *
 * The as-of predicate is **never written by the user**: it is derived from the
 * entity's as-of model and injected on read. This module owns that derivation as
 * a pure, dialect-agnostic function over resolved axis metadata (the start/end
 * column expressions, `toIsInclusive`, and the `infinity` sentinel) — it emits no
 * table/alias itself, taking the already-qualified column expressions from its
 * caller, so both the m-sql single-entity read lowering (through the injected
 * `SchemaResolver`, `@parallax/sql` staying m-temporal-read-free) and the m-deep-fetch deep-fetch
 * propagation (`@parallax/relationships`, the `m-navigate -> m-temporal-read` edge) reuse the identical
 * rule.
 *
 * The per-axis rules (m-temporal-read.md §"As-of read predicates"):
 *
 *  | pin                         | predicate                         | binds        |
 *  |-----------------------------|-----------------------------------|--------------|
 *  | Latest / omitted (default)  | `end = ?`                         | `[infinity]` |
 *  | finite instant, exclusive   | `start <= ? and end > ?`          | `[d, d]`     |
 *  | finite instant, inclusive   | `start <= ? and end >= ?`         | `[d, d]`     |
 *  | range (`asOfRange`)         | `start < ? and end > ?`           | `[end,start]`|
 *  | history                     | (no predicate — axis omitted)     | `[]`         |
 *
 * When an entity declares two dimensions, the injected terms are composed
 * **Valid Time first, then Transaction Time** (the canonical dimension order)
 * and `and`-joined; the
 * whole temporal term is appended **after** any user predicate (so binds read
 * left-to-right: user binds, then the as-of binds).
 */

/** The two temporal dimensions, in canonical composition order. */
export const CANONICAL_AXIS_ORDER = ["validTime", "transactionTime"] as const;

/** A temporal axis identity. */
export type Axis = (typeof CANONICAL_AXIS_ORDER)[number];

/** The temporal-infinity sentinel (the open upper bound), m-core's `"infinity"`. */
export const INFINITY = "infinity" as const;

/** A bind value the as-of predicate contributes (an instant string or `infinity`). */
export type AsOfBind = string;

/**
 * A resolved as-of axis: its axis identity plus the **already-qualified** column
 * expressions (e.g. `t0.from_z`), the half-open/closed flag, and the axis's
 * infinity sentinel. The caller (the m-sql resolver or the m-navigate propagation) resolves
 * these from the metamodel; this module never touches an alias or a metamodel.
 */
export interface ResolvedAxis {
  /** Which temporal dimension this axis represents. */
  readonly dimension: Axis;
  /** The alias-qualified start column expression (e.g. `t0.from_z`). */
  readonly startExpr: string;
  /** The alias-qualified end column expression (e.g. `t0.out_z`). */
  readonly endExpr: string;
  /** `true` when the upper bound is inclusive (`[from, to]`); default `false`. */
  readonly toIsInclusive: boolean;
  /** The axis's open-bound sentinel (`"infinity"`). */
  readonly infinity: AsOfBind;
}

/**
 * A pin selecting which milestone(s) a single axis reads:
 *  - `latest` — the open-ended row (`end = infinity`);
 *  - `instant` — a finite pin, including an instant obtained from the current clock;
 *  - `range` — an `asOfRange` overlap scan (`from < to AND to > from`);
 *  - `history` — the full milestone set (no predicate injected for this axis).
 *
 * An axis with no explicit pin **defaults to Latest** (the default-injection rule).
 */
export type AxisPin =
  | { readonly kind: "latest" }
  | { readonly kind: "instant"; readonly coordinate: AsOfBind }
  | { readonly kind: "range"; readonly start: AsOfBind; readonly end: AsOfBind }
  | { readonly kind: "history" };

/** A per-dimension pin map; an absent declared dimension defaults to Latest. */
export type AxisPins = Partial<Record<Axis, AxisPin>>;

/** A rendered temporal predicate: the SQL fragment and its ordered binds. */
export interface AsOfPredicate {
  /** The `and`-joined SQL fragment (empty when every axis is history/absent). */
  readonly sql: string;
  /** The binds, in fragment (placeholder) order. */
  readonly binds: readonly AsOfBind[];
}

/**
 * Build the injected as-of predicate for an entity's declared axes under a set of
 * pins. Axes are composed in canonical order (Valid Time, then Transaction Time); each
 * pinned/defaulted axis contributes its term and binds, a `history` axis
 * contributes nothing. Returns an empty predicate when no axis contributes (every
 * axis is `history`, or the entity is non-temporal).
 */
export function asOfPredicate(axes: readonly ResolvedAxis[], pins: AxisPins): AsOfPredicate {
  const ordered = orderAxes(axes);
  const terms: string[] = [];
  const binds: AsOfBind[] = [];
  for (const axis of ordered) {
    const pin = pins[axis.dimension] ?? { kind: "latest" };
    const term = axisTerm(axis, pin);
    if (term === undefined) {
      continue;
    }
    terms.push(term.sql);
    binds.push(...term.binds);
  }
  return { sql: terms.join(" and "), binds };
}

/** Order the resolved axes into canonical dimension order. */
function orderAxes(axes: readonly ResolvedAxis[]): readonly ResolvedAxis[] {
  const byAxis = new Map(axes.map((a) => [a.dimension, a]));
  const ordered: ResolvedAxis[] = [];
  for (const axis of CANONICAL_AXIS_ORDER) {
    const found = byAxis.get(axis);
    if (found) {
      ordered.push(found);
    }
  }
  return ordered;
}

/** Render one axis's term under its pin, or `undefined` for a `history` axis. */
function axisTerm(axis: ResolvedAxis, pin: AxisPin): AsOfPredicate | undefined {
  switch (pin.kind) {
    case "history":
      return undefined;
    case "latest":
      // Latest is the open-ended-row equality, not a finite clock instant.
      return { sql: `${axis.endExpr} = ?`, binds: [axis.infinity] };
    case "instant": {
      // A past pin: the containment predicate. The upper comparison is `>=` for an
      // inclusive axis (`[from, to]`), `>` for the default half-open (`[from, to)`).
      const upper = axis.toIsInclusive ? ">=" : ">";
      return {
        sql: `${axis.startExpr} <= ? and ${axis.endExpr} ${upper} ?`,
        binds: [pin.coordinate, pin.coordinate],
      };
    }
    case "range":
      // Overlap of a half-open milestone `[from, to)` with the window `[from, to)`:
      // `milestone.from < window.to AND milestone.to > window.from`. The binds read
      // window end then window start (`from < ?` then `to > ?`).
      return {
        sql: `${axis.startExpr} < ? and ${axis.endExpr} > ?`,
        binds: [pin.end, pin.start],
      };
  }
}

/**
 * The as-of **suffix** binds a temporal child level carries after its `IN`-list
 * (the deep-fetch propagation oracle). Per declared child axis, in canonical
 * order, the propagated value is the root pin for that axis or the child's own
 * default (Latest); Latest lowers to the single `infinity` bind, a finite instant to
 * `[d, d]`. A non-temporal child yields `[]`. This mirrors the reference oracle's
 * `_expected_asof_suffix` exactly — the suffix is an **ordered** list (never
 * sorted / reordered).
 */
export function propagatedSuffixBinds(
  childAxes: readonly ResolvedAxis[],
  rootPins: AxisPins,
): readonly AsOfBind[] {
  const predicate = asOfPredicate(childAxes, propagate(childAxes, rootPins));
  return predicate.binds;
}

/**
 * The child-level as-of predicate (SQL + binds) for a temporal deep-fetch hop:
 * every declared child axis pinned from the root (matched by axis) or defaulted to
 * Latest. Non-temporal child ⇒ empty predicate.
 */
export function propagatedPredicate(
  childAxes: readonly ResolvedAxis[],
  rootPins: AxisPins,
): AsOfPredicate {
  return asOfPredicate(childAxes, propagate(childAxes, rootPins));
}

/**
 * Map the root pins onto the child's declared axes: an axis the root pinned
 * propagates that pin; an axis the child declares but the root did not pin
 * defaults to Latest (the per-axis default-injection rule). `history`/`range` root
 * pins are not part of the propagation oracle (deep fetch propagates only `asOf`
 * pins), so only Latest / finite-instant pins carry across; any other child axis
 * defaults to Latest.
 */
function propagate(childAxes: readonly ResolvedAxis[], rootPins: AxisPins): AxisPins {
  const pins: AxisPins = {};
  for (const axis of childAxes) {
    const rootPin = rootPins[axis.dimension];
    pins[axis.dimension] =
      rootPin && (rootPin.kind === "latest" || rootPin.kind === "instant")
        ? rootPin
        : { kind: "latest" };
  }
  return pins;
}
