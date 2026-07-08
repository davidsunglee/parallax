/**
 * `@parallax/sql` — m-sql SQL generation contract.
 *
 * The canonical-by-construction compile visitor: switch on the operation tag,
 * thread a first-appearance alias allocator and a binds accumulator, emit the
 * five m-sql normalization rules directly. Schema knowledge is injected via the
 * `SchemaResolver` port so this package imports no metamodel.
 */

export { coerceBind, exceedsSafeInteger } from "./bind.js";
export {
  type AsOfFragment,
  type Axis,
  type AxisPin,
  type AxisPins,
  aliasFor,
  type Bind,
  type CompileCtx,
  type CompileExec,
  type CompileResult,
  compile,
  compilePredicate,
  newCompileCtx,
  type ProjectionColumn,
  type ResolvedColumn,
  type ResolvedNestedPath,
  type ResolvedRelationship,
  type SchemaResolver,
} from "./compile.js";
