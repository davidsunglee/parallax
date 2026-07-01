/**
 * The fluent query DSL (spec §1) — the entity-agnostic runtime the generated
 * `#parallax` entity symbols delegate to. It builds canonical M2 operation data
 * (design Q1 Option B, Q3), the identical wire form the M3 compiler consumes, so
 * the DSL and the conformance adapter share one canonical form.
 */
export {
  AttributeExpression,
  NavigationPath,
  OrderKeyExpression,
  Predicate,
  type StringPredicateOptions,
  ToManyRelationshipExpression,
} from "./expression.js";
export {
  type AxisRefs,
  buildFindOperation,
  type FindOptions,
  type TemporalAxis,
  type TemporalPoint,
  type TemporalRange,
  type TemporalReadOptions,
} from "./find.js";
