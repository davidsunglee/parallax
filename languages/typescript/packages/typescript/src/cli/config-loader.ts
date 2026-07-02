/**
 * Locate + load a project's `parallax.config.*` (spec §7).
 *
 * `parallax generate` reads a config module that default-exports the result of
 * `defineParallaxConfig(...)`. V1 loads a JS/MJS/CJS config by dynamic import (no
 * TypeScript loader dependency); a project authoring a `.ts` config compiles it
 * first (its build already runs `tsc`) or passes an explicit `--config` path to a
 * built module. The loader validates the shape so a malformed config fails
 * loudly.
 */
import { existsSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import type { ParallaxConfig } from "../config.js";

/** The config file names `parallax generate` searches for, in order. */
export const CONFIG_CANDIDATES = [
  "parallax.config.js",
  "parallax.config.mjs",
  "parallax.config.cjs",
] as const;

/** True when a value looks like a resolved {@link ParallaxConfig}. */
function isParallaxConfig(value: unknown): value is ParallaxConfig {
  if (value === null || typeof value !== "object") {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    Array.isArray(record.descriptors) &&
    typeof record.output === "string" &&
    typeof record.importAlias === "string"
  );
}

/** Resolve the config module path: an explicit `--config`, else the first candidate. */
export function resolveConfigPath(cwd: string, explicit?: string): string {
  if (explicit) {
    return isAbsolute(explicit) ? explicit : resolve(cwd, explicit);
  }
  for (const candidate of CONFIG_CANDIDATES) {
    const path = resolve(cwd, candidate);
    if (existsSync(path)) {
      return path;
    }
  }
  throw new Error(
    `no parallax config found (looked for ${CONFIG_CANDIDATES.join(" / ")} in ${cwd}); ` +
      "author a parallax.config.js exporting defineParallaxConfig(...) or pass --config <path>",
  );
}

/** Load + validate the config module at `path` (its default export). */
export async function loadConfig(path: string): Promise<ParallaxConfig> {
  const module = (await import(pathToFileURL(path).href)) as { default?: unknown };
  const config = module.default;
  if (!isParallaxConfig(config)) {
    throw new Error(
      `${path} must default-export defineParallaxConfig({ descriptors, output, importAlias })`,
    );
  }
  return config;
}
