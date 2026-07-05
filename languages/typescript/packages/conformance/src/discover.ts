/**
 * Case discovery + loading (the M12 harness front door).
 *
 * Globs case YAML under `core/compatibility/cases/**`, parses each through the
 * canonical serde seam (re-exported by `@parallax/operation`, the one allowed
 * edge), and resolves its referenced model descriptor + sibling fixtures. Shape
 * detection keys off the discriminating fields the case carries (`operation` →
 * `read`, `writeSequence`, `scenario`, `conflict`).
 *
 * The runner consumes the `LoadedCase` view: the parsed case, its model
 * descriptor (a plain metamodel document), the fixtures keyed by class name, and
 * the repo-relative case path the envelope's `case` field requires.
 */
// The M12 lane a case runs on: `harness` (executed) or `api-conformance`
// (schema-validated by the harness, satisfied by the language's suite).
export type CaseLane = "harness" | "api-conformance";

import { readdirSync, readFileSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { CaseShape } from "@parallax/core";
import { deserialize } from "@parallax/operation";

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
  /** The raw parsed case document. */
  readonly raw: Record<string, unknown>;
  /** The detected case shape. */
  readonly shape: CaseShape;
  /** The module tags (e.g. `["m2", "m12"]`) the case declares. */
  readonly tags: readonly string[];
  /**
   * The M12 lane the case runs on (default `harness`). An `api-conformance`-lane
   * case (every boundary case, plus the read-lock matrix reads `0616`-`0619`) is
   * suite-satisfied, not harness-run: the runner marks it suite-satisfied and the
   * harness sweeps exclude it, while the API Conformance Suite exercises it.
   */
  readonly lane: CaseLane;
  /**
   * The declared unit-of-work config (M8 strategy selection), or `undefined`. A
   * descriptive passthrough: `{ concurrency: "locking" | "optimistic" }` records
   * which mode produced the authored golden SQL (the harness runs it either way).
   */
  readonly uow?: { readonly concurrency?: "locking" | "optimistic" };
  /** The parsed model descriptor (a metamodel document). */
  readonly descriptor: unknown;
  /** Fixture rows keyed by class name (empty when none authored). */
  readonly fixtures: Record<string, readonly Record<string, unknown>[]>;
}

/** Detect a case's shape from its discriminating top-level fields. */
export function detectShape(raw: Record<string, unknown>): CaseShape {
  if ("writeSequence" in raw) {
    return "writeSequence";
  }
  if ("scenario" in raw) {
    return "scenario";
  }
  // An error-classification case (`errorClass` + `expectedNativeCode`), single- or
  // two-connection (`concurrency`). Checked before `conflict`/`read` so `0728`'s
  // read-lock-blocks-writer concurrency shape resolves to `error`, not `read`.
  if ("errorClass" in raw) {
    return "error";
  }
  if ("expectedAffectedRows" in raw || "attempts" in raw) {
    return "conflict";
  }
  if ("coherence" in raw) {
    return "coherence";
  }
  if ("boundary" in raw) {
    return "boundary";
  }
  return "read";
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
  const raw = loadYaml(absolute) as Record<string, unknown>;
  const { descriptor, fixtures } = loadModel(raw.model as string);
  return {
    casePath,
    raw,
    shape: detectShape(raw),
    tags: (raw.tags as string[] | undefined) ?? [],
    lane: (raw.lane as CaseLane | undefined) ?? "harness",
    ...(raw.uow === undefined
      ? {}
      : { uow: raw.uow as { concurrency?: "locking" | "optimistic" } }),
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
