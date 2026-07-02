/**
 * Descriptor-glob resolution for the generate driver (spec §7).
 *
 * Resolves the config `descriptors` glob(s) against the config-file directory
 * with Node's built-in `fs.globSync` (Node ≥ 22) — no glob dependency is added.
 * Results are deduped and sorted so generation is deterministic, mirroring the
 * conformance harness's deduped, sorted case discovery.
 */
import { globSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Resolve descriptor globs (relative to `cwd`) to a deduped, sorted list of
 * absolute paths. Only `.yaml` / `.yml` / `.json` matches are kept (a glob may
 * match a sidecar the generator does not consume).
 */
export function resolveDescriptorGlobs(
  patterns: readonly string[],
  cwd: string = process.cwd(),
): readonly string[] {
  const matches = new Set<string>();
  for (const pattern of patterns) {
    for (const match of globSync(pattern, { cwd })) {
      if (/\.(ya?ml|json)$/.test(match)) {
        matches.add(resolve(cwd, match));
      }
    }
  }
  return [...matches].sort();
}
