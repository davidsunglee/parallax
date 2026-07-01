/**
 * The generate driver (spec §5) — the code path `parallax generate` and
 * `parallax generate --check` run.
 *
 * `generate(config, cwd)` resolves the descriptor glob against `cwd`, parses each
 * matched document through the canonical serde seam, merges them into one
 * metamodel, builds the codegen model, emits the `#parallax` barrel, and writes
 * it under `config.output`. `checkGenerate` runs the same pipeline **without
 * writing** (validating descriptors + generation), so `--check` fails if
 * generation would fail without touching the filesystem (spec §5: generated files
 * are uncommitted, so this is not a git-drift check).
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { Metamodel } from "@parallax/metamodel";
import { deserialize } from "@parallax/operation";
import type { ParallaxConfig } from "../config.js";
import { emitBarrel, type GeneratedFile } from "./emit.js";
import { buildCodegenModel } from "./model.js";
import { resolveDescriptorGlobs } from "./resolve.js";

/** The result of a generate / check run: the descriptors + files it produced. */
export interface GenerateResult {
  /** The absolute descriptor paths that matched the glob. */
  readonly descriptorPaths: readonly string[];
  /** The generated files (path relative to `output`, plus contents). */
  readonly files: readonly GeneratedFile[];
  /** The absolute output directory. */
  readonly outputDir: string;
}

/** Parse one descriptor document through the canonical serde seam. */
function parseDescriptor(path: string): unknown {
  const text = readFileSync(path, "utf8");
  const format = path.endsWith(".json") ? "json" : "yaml";
  return deserialize(text, format);
}

/**
 * Lift a parsed descriptor to its flat entity array. A descriptor is either a
 * single `entity` or an `entities` array (spec §2.1); both forms merge into one
 * metamodel so relationships can name siblings across files.
 */
function entitiesOf(descriptor: unknown): readonly unknown[] {
  if (descriptor && typeof descriptor === "object") {
    const record = descriptor as Record<string, unknown>;
    if (Array.isArray(record.entities)) {
      return record.entities;
    }
    if (record.entity) {
      return [record.entity];
    }
  }
  throw new Error("descriptor must declare a single `entity` or an `entities` array");
}

/**
 * Run the generate pipeline (parse → build model → emit) without writing. Shared
 * by `generate` (which then writes) and `checkGenerate` (which does not). Throws
 * on any descriptor / generation failure, so `--check` surfaces it.
 */
export function planGenerate(config: ParallaxConfig, cwd: string = process.cwd()): GenerateResult {
  const descriptorPaths = resolveDescriptorGlobs(config.descriptors, cwd);
  if (descriptorPaths.length === 0) {
    throw new Error(
      `no descriptors matched ${JSON.stringify(config.descriptors)} (relative to ${cwd})`,
    );
  }

  // Merge every matched descriptor into one `entities` document, then read it
  // through the M1 metamodel (which ajv-validates it against metamodel.schema.json
  // and normalizes defaults). Validation failures throw here — the `--check` gate.
  const entities = descriptorPaths.flatMap((path) => entitiesOf(parseDescriptor(path)));
  const descriptor = { entities };
  const metamodel = Metamodel.fromDescriptor(descriptor);

  const model = buildCodegenModel(metamodel);
  const barrel = emitBarrel(model, descriptor);
  const outputDir = isAbsolute(config.output) ? config.output : resolve(cwd, config.output);
  return { descriptorPaths, files: [barrel], outputDir };
}

/** Generate the `#parallax` barrel and write it under `config.output`. */
export function generate(config: ParallaxConfig, cwd: string = process.cwd()): GenerateResult {
  const result = planGenerate(config, cwd);
  for (const file of result.files) {
    const target = join(result.outputDir, file.path);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, file.contents, "utf8");
  }
  return result;
}

/**
 * Validate descriptors + generation WITHOUT writing (spec §5, `generate
 * --check`). Returns the plan on success; throws with a descriptive message on
 * any failure the generate would have hit.
 */
export function checkGenerate(config: ParallaxConfig, cwd: string = process.cwd()): GenerateResult {
  return planGenerate(config, cwd);
}

/** A human-readable one-line summary of a generate result (CLI feedback). */
export function summarize(result: GenerateResult, cwd: string): string {
  const descriptors = result.descriptorPaths
    .map((p) => relative(cwd, p))
    .sort()
    .join(", ");
  const out = relative(cwd, join(result.outputDir, result.files[0]?.path ?? ""));
  return `generated ${result.files.length} file(s) from ${result.descriptorPaths.length} descriptor(s) [${descriptors}] → ${out}`;
}
