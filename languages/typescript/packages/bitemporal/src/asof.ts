/**
 * M7 as-of predicate injection — the pure derivation the temporal read + deep-fetch
 * propagation paths share.
 *
 * The as-of predicate is **never written by the user**: it is derived from the
 * entity's as-of model and injected on read. This module owns that derivation as
 * a pure, dialect-agnostic function over resolved axis metadata (the from/to
 * column expressions, `toIsInclusive`, and the `infinity` sentinel) — it emits no
 * table/alias itself, taking the already-qualified column expressions from its
 * caller, so both the M3 single-entity read lowering (through the injected
 * `SchemaResolver`, `@parallax/sql` staying M7-free) and the M4 deep-fetch
 * propagation (`@parallax/relationships`, the `M4 -> M7` edge) reuse the identical
 * rule.
 *
 * The per-axis rules (m7-temporal.md §"As-of read predicates"):
 *
 *  | pin                         | predicate                         | binds        |
 *  |-----------------------------|-----------------------------------|--------------|
 *  | now / omitted (default)     | `to = ?`                          | `[infinity]` |
 *  | past instant, exclusive     | `from <= ? and to > ?`            | `[d, d]`     |
 *  | past instant, inclusive     | `from <= ? and to >= ?`           | `[d, d]`     |
 *  | range (`asOfRange`)         | `from < ? and to > ?`             | `[to, from]` |
 *  | history                     | (no predicate — axis omitted)     | `[]`         |
 *
 * When an entity declares two axes, the injected terms are composed **business
 * axis first, then processing** (the canonical axis order) and `and`-joined; the
 * whole temporal term is appended **after** any user predicate (so binds read
 * left-to-right: user binds, then the as-of binds).
 */

/** The two temporal axes, in the canonical composition order (business first). */
export const CANONICAL_AXIS_ORDER = ["business", "processing"] as const;

/** A temporal axis identity. */
export type Axis = (typeof CANONICAL_AXIS_ORDER)[number];

/** The temporal-infinity sentinel (the open upper bound), M0's `"infinity"`. */
export const INFINITY = "infinity" as const;

/** A bind value the as-of predicate contributes (an instant string or `infinity`). */
export type AsOfBind = string;

/**
 * A resolved as-of axis: its axis identity plus the **already-qualified** column
 * expressions (e.g. `t0.from_z`), the half-open/closed flag, and the axis's
 * infinity sentinel. The caller (the M3 resolver or the M4 propagation) resolves
 * these from the metamodel; this module never touches an alias or a metamodel.
 */
export interface ResolvedAxis {
  /** Which axis this dimension is (`business` or `processing`). */
  readonly axis: Axis;
  /** The alias-qualified `from` column expression (e.g. `t0.from_z`). */
  readonly fromExpr: string;
  /** The alias-qualified `to` column expression (e.g. `t0.out_z`). */
  readonly toExpr: string;
  /** `true` when the upper bound is inclusive (`[from, to]`); default `false`. */
  readonly toIsInclusive: boolean;
  /** The axis's open-bound sentinel (`"infinity"`). */
  readonly infinity: AsOfBind;
}

/**
 * A pin selecting which milestone(s) a single axis reads:
 *  - `now` — the current row (`to = infinity`);
 *  - `instant` — a past pin (the half-open/closed containment predicate);
 *  - `range` — an `asOfRange` overlap scan (`from < to AND to > from`);
 *  - `history` — the full milestone set (no predicate injected for this axis).
 *
 * An axis with no explicit pin **defaults to `now`** (the default-injection rule).
 */
export type AxisPin =
  | { readonly kind: "now" }
  | { readonly kind: "instant"; readonly date: AsOfBind }
  | { readonly kind: "range"; readonly from: AsOfBind; readonly to: AsOfBind }
  | { readonly kind: "history" };

/** A per-axis pin map (keyed by axis identity); an absent axis defaults to `now`. */
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
 * pins. Axes are composed in canonical order (business, then processing); each
 * pinned/defaulted axis contributes its term and binds, a `history` axis
 * contributes nothing. Returns an empty predicate when no axis contributes (every
 * axis is `history`, or the entity is non-temporal).
 */
export function asOfPredicate(axes: readonly ResolvedAxis[], pins: AxisPins): AsOfPredicate {
  const ordered = orderAxes(axes);
  const terms: string[] = [];
  const binds: AsOfBind[] = [];
  for (const axis of ordered) {
    const pin = pins[axis.axis] ?? { kind: "now" };
    const term = axisTerm(axis, pin);
    if (term === undefined) {
      continue;
    }
    terms.push(term.sql);
    binds.push(...term.binds);
  }
  return { sql: terms.join(" and "), binds };
}

/** Order the resolved axes into canonical (business, processing) order. */
function orderAxes(axes: readonly ResolvedAxis[]): readonly ResolvedAxis[] {
  const byAxis = new Map(axes.map((a) => [a.axis, a]));
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
    case "now":
      // The current-row equality: a single equality against infinity (one bind),
      // not a two-sided range — the cheapest as-of-now read.
      return { sql: `${axis.toExpr} = ?`, binds: [axis.infinity] };
    case "instant": {
      // A past pin: the containment predicate. The upper comparison is `>=` for an
      // inclusive axis (`[from, to]`), `>` for the default half-open (`[from, to)`).
      const upper = axis.toIsInclusive ? ">=" : ">";
      return {
        sql: `${axis.fromExpr} <= ? and ${axis.toExpr} ${upper} ?`,
        binds: [pin.date, pin.date],
      };
    }
    case "range":
      // Overlap of a half-open milestone `[from, to)` with the window `[from, to)`:
      // `milestone.from < window.to AND milestone.to > window.from`. The binds read
      // window end then window start (`from < ?` then `to > ?`).
      return {
        sql: `${axis.fromExpr} < ? and ${axis.toExpr} > ?`,
        binds: [pin.to, pin.from],
      };
  }
}

/**
 * The as-of **suffix** binds a temporal child level carries after its `IN`-list
 * (the deep-fetch propagation oracle). Per declared child axis, in canonical
 * order, the propagated value is the root pin for that axis or the child's own
 * default (`now`); `now` lowers to the single `infinity` bind, a past instant to
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
 * `now`. Non-temporal child ⇒ empty predicate.
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
 * defaults to `now` (the per-axis default-injection rule). `history`/`range` root
 * pins are not part of the propagation oracle (deep fetch propagates only `asOf`
 * pins), so only `now` / `instant` pins carry across; any other child axis
 * defaults to `now`.
 */
function propagate(childAxes: readonly ResolvedAxis[], rootPins: AxisPins): AxisPins {
  const pins: AxisPins = {};
  for (const axis of childAxes) {
    const rootPin = rootPins[axis.axis];
    pins[axis.axis] =
      rootPin && (rootPin.kind === "now" || rootPin.kind === "instant") ? rootPin : { kind: "now" };
  }
  return pins;
}
