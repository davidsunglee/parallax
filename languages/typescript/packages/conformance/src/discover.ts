/**
 * Case discovery + loading (the m-case-format harness front door).
 *
 * Globs case YAML under `core/compatibility/cases/**`, parses each through the
 * canonical serde seam (re-exported by `@parallax/operation`, the one allowed
 * edge), validates it once against the canonical case JSON Schema behind the
 * `validateCase` seam, and resolves its referenced model descriptor + sibling
 * fixtures. Shape detection is a read of the explicit `shape` field the case
 * carries (checked against the `CaseShape` union), not a sniff of which keys happen
 * to be present.
 *
 * The runner consumes the `LoadedCase` view: the parsed case (typed as the
 * schema-derived `CaseDocument`), its model descriptor (a plain metamodel
 * document), the fixtures keyed by class name, and the repo-relative case path the
 * envelope's `case` field requires.
 */
// The m-case-format lane a case runs on: `harness` (executed) or `api-conformance`
// (schema-validated by the harness, satisfied by the language's suite).
export type CaseLane = "harness" | "api-conformance";

import { readdirSync, readFileSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { CaseShape } from "@parallax/core";
import { deserialize } from "@parallax/operation";
// ajv 8 ships the `Ajv2020` class as a CommonJS named export; ajv-formats ships
// its plugin as the CommonJS default. Both are resolved as CJS under NodeNext.
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import addFormatsModule, { type FormatsPlugin } from "ajv-formats";
import type { CaseDocument } from "./case-format.js";

// Under NodeNext the ajv-formats default import surfaces as the namespace; the
// callable plugin is its `.default`, falling back to the namespace itself.
const addFormats = ((addFormatsModule as unknown as { default?: FormatsPlugin }).default ??
  (addFormatsModule as unknown as FormatsPlugin)) as FormatsPlugin;

/** The repo root, resolved from this module's location (five dirs up). */
export function repoRoot(): string {
  const here = fileURLToPath(import.meta.url);
  return fileURLToPath(new URL("../../../../../", new URL(`file://${here}`)));
}

/** The `core/compatibility` root that case `model` paths are relative to. */
function compatibilityRoot(): string {
  return resolve(repoRoot(), "core/compatibility");
}

/** A parsed compatibility case bound to its model descriptor and fixtures. */
export interface LoadedCase {
  /** The repo-relative case path (the envelope `case` field; uses `/`). */
  readonly casePath: string;
  /** The parsed case document, validated against the canonical case schema. */
  readonly raw: CaseDocument;
  /** The detected case shape. */
  readonly shape: CaseShape;
  /** The module tags (e.g. `["m-op-algebra", "m-conformance-adapter"]`) the case declares. */
  readonly tags: readonly string[];
  /**
   * The conformance lane the case runs on (default `harness`). An
   * `api-conformance`-lane case (every boundary case, plus the read-lock matrix
   * reads `m-read-lock-002`-`m-read-lock-005`) is
   * suite-satisfied, not harness-run: the runner marks it suite-satisfied and the
   * harness sweeps exclude it, while the API Conformance Suite exercises it.
   */
  readonly lane: CaseLane;
  /**
   * The declared unit-of-work config (m-unit-work strategy selection), or `undefined`. A
   * descriptive passthrough: `{ concurrency: "locking" | "optimistic" }` records
   * which mode produced the authored golden SQL (the harness runs it either way).
   */
  readonly uow?: { readonly concurrency?: "locking" | "optimistic" };
  /** The parsed model descriptor (a metamodel document). */
  readonly descriptor: unknown;
  /** Fixture rows keyed by class name (empty when none authored). */
  readonly fixtures: Record<string, readonly Record<string, unknown>[]>;
}

/** The eight case shapes the harness discriminates (the schema `shape` enum). */
const CASE_SHAPES: ReadonlySet<CaseShape> = new Set<CaseShape>([
  "read",
  "writeSequence",
  "scenario",
  "conflict",
  "coherence",
  "error",
  "concurrencySuccess",
  "boundary",
]);

/**
 * Read a case's shape from its explicit `shape` discriminator, checked against the
 * `CaseShape` union. `validateCase` has already pinned it to the schema enum; this
 * re-check keeps the loader honest if a case is loaded without validation.
 */
export function detectShape(raw: CaseDocument): CaseShape {
  const shape = raw.shape;
  if (!CASE_SHAPES.has(shape as CaseShape)) {
    throw new Error(`case declares unknown shape '${String(shape)}'`);
  }
  return shape as CaseShape;
}

let cachedCaseValidate: ValidateFunction | undefined;

/** Compile (once) the canonical compatibility-case schema validator (Ajv2020). */
function caseValidator(): ValidateFunction {
  if (cachedCaseValidate) {
    return cachedCaseValidate;
  }
  const schemaPath = resolve(repoRoot(), "core/schemas/compatibility-case.schema.json");
  const schema = JSON.parse(readFileSync(schemaPath, "utf8")) as object;
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  addFormats(ajv);
  cachedCaseValidate = ajv.compile(schema);
  return cachedCaseValidate;
}

/**
 * The single load-time validation seam: validate a lossless-parsed case document
 * against `core/schemas/compatibility-case.schema.json` (the canonical form),
 * throwing with the collected Ajv errors if it does not conform. Returns the
 * document typed as {@link CaseDocument}. The schema keeps value cells
 * unconstrained, so the serde seam's precision-safe string re-tagging stays
 * conflict-free.
 */
export function validateCase(doc: unknown, casePath: string): CaseDocument {
  const validate = caseValidator();
  if (!validate(doc)) {
    const errors = (validate.errors ?? []).map(
      (e) => `${e.instancePath || "/"} ${e.message ?? "is invalid"}`,
    );
    throw new Error(
      `${casePath} does not validate against compatibility-case.schema.json:\n  ${errors.join("\n  ")}`,
    );
  }
  return doc as CaseDocument;
}

/** Parse a YAML file through the canonical serde seam. */
function loadYaml(path: string): unknown {
  return deserialize(readFileSync(path, "utf8"), "yaml");
}

/**
 * Load the model descriptor a case references, plus its sibling fixtures
 * (`fixtures/<model-stem>.yaml`, keyed by class name; absent ⇒ no fixtures).
 */
function loadModel(modelRel: string): {
  descriptor: unknown;
  fixtures: Record<string, readonly Record<string, unknown>[]>;
} {
  const root = compatibilityRoot();
  const modelPath = resolve(root, modelRel);
  const descriptor = loadYaml(modelPath);

  const stem = modelRel.replace(/^.*\//, "").replace(/\.ya?ml$/, "");
  const fixturesPath = resolve(root, "fixtures", `${stem}.yaml`);
  let fixtures: Record<string, readonly Record<string, unknown>[]> = {};
  try {
    const loaded = loadYaml(fixturesPath);
    if (loaded && typeof loaded === "object") {
      fixtures = loaded as Record<string, readonly Record<string, unknown>[]>;
    }
  } catch {
    // No fixtures file for this model — leave fixtures empty.
  }
  return { descriptor, fixtures };
}

/** Normalize any case path to its repo-relative `/`-separated form. */
export function toCasePath(path: string): string {
  const absolute = isAbsolute(path) ? path : resolve(repoRoot(), path);
  return relative(repoRoot(), absolute).split("\\").join("/");
}

/** Load a single case (by repo-relative or absolute path) into a `LoadedCase`. */
export function loadCase(path: string): LoadedCase {
  const casePath = toCasePath(path);
  const absolute = resolve(repoRoot(), casePath);
  const raw = validateCase(loadYaml(absolute), casePath);
  const { descriptor, fixtures } = loadModel(raw.model);
  const concurrency = raw.when?.uow?.concurrency;
  return {
    casePath,
    raw,
    shape: detectShape(raw),
    tags: raw.tags,
    lane: (raw.lane as CaseLane | undefined) ?? "harness",
    ...(concurrency === undefined ? {} : { uow: { concurrency } }),
    descriptor,
    fixtures,
  };
}

/**
 * Discover every case file under `core/compatibility/cases/**`, sorted by path.
 * Returns repo-relative case paths (the envelope `case` field form).
 */
export function discoverCasePaths(): readonly string[] {
  const casesDir = resolve(repoRoot(), "core/compatibility/cases");
  const files: string[] = [];
  walk(casesDir, files);
  return files
    .filter((p) => p.endsWith(".yaml") || p.endsWith(".yml"))
    .map(toCasePath)
    .sort();
}

/** Recursively collect file paths under `dir`. */
function walk(dir: string, out: string[]): void {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = resolve(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full, out);
    } else {
      out.push(full);
    }
  }
}
