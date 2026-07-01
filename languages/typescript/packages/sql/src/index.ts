/**
 * `@parallax/sql` — M3 SQL generation contract.
 *
 * The canonical-by-construction compile visitor: switch on the operation tag,
 * thread a first-appearance alias allocator and a binds accumulator, emit the
 * five M3 normalization rules directly. Schema knowledge is injected via the
 * `SchemaResolver` port so this package imports no metamodel.
 */

// Re-export the dialect-owned DDL / identifier-quoting helpers the M12 harness
// needs (`@parallax/conformance` may not import `@parallax/dialect` directly —
// there is no `conformance -> dialect` allowlist edge — but `M3 -> M11` is an
// allowed edge, so M3 is the facade). Driver-bound helpers (placeholder
// translation, raw-type parsers) stay in `@parallax/dialect` for the
// composition-root provider, which imports it directly.
//
// Phase 4+ revisit (review Finding 5): this re-export blurs ownership — the
// compiler does not own DDL/provisioning. It is tolerated while the surface is
// these three pure schema helpers. If the facade accretes more DDL/provisioning
// concern, replace it with an explicit `conformance -> dialect` allowlist edge
// (in `.dependency-cruiser.cjs`) or a small `@parallax/db-schema` (M11-adjacent)
// package that owns `ddlForDescriptor` / `columnOrder` / `quoteIdentifier`, so
// M3 stops being the conduit. No change now: the M3 -> M11 edge is real and the
// arrangement is dependency-cruiser-clean.
export { columnOrder, ddlForDescriptor, quoteIdentifier } from "@parallax/dialect";
export { coerceBind, exceedsSafeInteger } from "./bind.js";
export {
  aliasFor,
  type Bind,
  type CompileCtx,
  type CompileResult,
  compile,
  compilePredicate,
  newCompileCtx,
  type ResolvedColumn,
  type ResolvedRelationship,
  type SchemaResolver,
} from "./compile.js";
