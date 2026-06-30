/**
 * `@parallax/sql` — M3 SQL generation contract.
 *
 * The canonical-by-construction compile visitor: switch on the operation tag,
 * thread a first-appearance alias allocator and a binds accumulator, emit the
 * five M3 normalization rules directly. Schema knowledge is injected via the
 * `SchemaResolver` port so this package imports no metamodel.
 */

// Re-export the dialect-owned DDL / identifier-quoting helpers the M12 harness
// needs (`@parallax/conformance` may not import `@parallax/dialect` directly,
// but `M3 -> M11` is an allowed edge, so M3 is the facade). Driver-bound helpers
// (placeholder translation, raw-type parsers) stay in `@parallax/dialect` for
// the composition-root provider, which imports it directly.
export { columnOrder, ddlForDescriptor, quoteIdentifier } from "@parallax/dialect";
export {
  aliasFor,
  type Bind,
  type CompileCtx,
  type CompileResult,
  compile,
  compilePredicate,
  newCompileCtx,
  type ResolvedColumn,
  type SchemaResolver,
} from "./compile.js";
