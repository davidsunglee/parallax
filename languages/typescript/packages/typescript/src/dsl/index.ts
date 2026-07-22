/**
 * The fluent query DSL (spec §2) — the entity-agnostic runtime the generated
 * `#parallax` entity symbols delegate to. It builds canonical m-op-algebra operation data
 * (design Q1 Option B, Q3), the identical wire form the m-sql compiler consumes, so
 * the DSL and the conformance adapter share one canonical form.
 */
export {
  AttributeExpression,
  NavigationPath,
  NestedFieldExpression,
  OrderKeyExpression,
  Predicate,
  type StringPredicateOptions,
  ToManyRelationshipExpression,
  ValueObjectExpression,
} from "./expression.js";
export {
  buildFindOperation,
  type FindOptions,
  LATEST,
  type TemporalAxis,
  type TemporalPoint,
  type TemporalRange,
  type TemporalReadOptions,
} from "./find.js";
