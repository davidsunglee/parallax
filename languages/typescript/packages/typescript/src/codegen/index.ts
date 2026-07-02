/**
 * The `#parallax` barrel generator (spec §7) — descriptor-first codegen over the
 * canonical metamodel. Generated output is uncommitted / gitignored (ADR-0003)
 * and produced by `parallax generate`.
 */
export { BARREL_FILE, emitBarrel, type GeneratedFile } from "./emit.js";
export {
  checkGenerate,
  type GenerateResult,
  generate,
  planGenerate,
  summarize,
} from "./generate.js";
export {
  type AttributeModel,
  buildCodegenModel,
  type CodegenModel,
  type EntityModel,
  propertyTypeFor,
} from "./model.js";
export { resolveDescriptorGlobs } from "./resolve.js";
