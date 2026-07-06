/**
 * Generator configuration (spec §7, ADR-0001) — exposed as the
 * `@parallax/typescript/config` subpath.
 *
 * A project authors a `parallax.config.ts` that default-exports
 * `defineParallaxConfig({ descriptors, output, importAlias })`; `parallax
 * generate` reads it, resolves the descriptor glob against the canonical
 * metamodel, and materializes the `#parallax` barrel at `output`. Codegen is
 * **descriptor-first**: the source of truth is the canonical Parallax YAML/JSON
 * descriptor set (validated against `metamodel.schema.json`), not TypeScript
 * decorators or builders.
 */

/**
 * The resolved generator configuration. All paths are project-relative (resolved
 * against the config file's directory at generate time).
 */
export interface ParallaxConfig {
  /**
   * Glob(s) selecting the canonical descriptor documents to generate from (e.g.
   * `["./parallax/**\/*.yaml"]`). Each matched file validates against
   * `metamodel.schema.json` (spec §3.1).
   */
  readonly descriptors: readonly string[];
  /**
   * Where the generated `#parallax` barrel is written (default
   * `./.parallax/generated`, outside `src/`, gitignored — ADR-0002).
   */
  readonly output: string;
  /**
   * The package-local import alias the barrel is reachable through (default
   * `#parallax`, spec §2.1). Applications import the generated API through it so
   * the physical output path stays hidden.
   */
  readonly importAlias: string;
}

/** The config `defineParallaxConfig` accepts — `output` / `importAlias` default. */
export interface ParallaxConfigInput {
  readonly descriptors: readonly string[];
  readonly output?: string;
  readonly importAlias?: string;
}

/** The default output directory for generated code (ADR-0002 — gitignored). */
export const DEFAULT_OUTPUT = "./.parallax/generated" as const;

/** The default package-local import alias (spec §2.1). */
export const DEFAULT_IMPORT_ALIAS = "#parallax" as const;

/**
 * Define a Parallax generator configuration (spec §7). Applies the `output` and
 * `importAlias` defaults and freezes the result so a config object is a stable,
 * shareable value; a project default-exports the return value from its
 * `parallax.config.ts`.
 *
 * ```ts
 * import { defineParallaxConfig } from "@parallax/typescript/config";
 *
 * export default defineParallaxConfig({
 *   descriptors: ["./parallax/**\/*.yaml"],
 *   output: "./.parallax/generated",
 *   importAlias: "#parallax",
 * });
 * ```
 */
export function defineParallaxConfig(input: ParallaxConfigInput): ParallaxConfig {
  if (!Array.isArray(input.descriptors) || input.descriptors.length === 0) {
    throw new Error("parallax config requires a non-empty `descriptors` glob array");
  }
  return Object.freeze({
    descriptors: [...input.descriptors],
    output: input.output ?? DEFAULT_OUTPUT,
    importAlias: input.importAlias ?? DEFAULT_IMPORT_ALIAS,
  });
}
