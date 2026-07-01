/**
 * `@parallax/bitemporal` — M7 bitemporal / milestoning.
 *
 * The pure as-of predicate injection (`asof.ts`) — reused by the M3 single-entity
 * read lowering (through the injected `SchemaResolver`) and the M4 deep-fetch
 * as-of propagation — plus audit-only milestone-chaining write DML generation
 * (`audit-writes.ts`). This package is dialect-agnostic and metamodel-free: it
 * takes already-resolved physical column expressions / write targets and produces
 * canonical `?`-placeholder SQL fragments + binds.
 */
export {
  type AsOfBind,
  type AsOfPredicate,
  type Axis,
  type AxisPin,
  type AxisPins,
  asOfPredicate,
  CANONICAL_AXIS_ORDER,
  INFINITY,
  propagatedPredicate,
  propagatedSuffixBinds,
  type ResolvedAxis,
} from "./asof.js";
export {
  auditWriteStatements,
  type MutationKind,
  type WriteStatement,
  type WriteTarget,
} from "./audit-writes.js";
