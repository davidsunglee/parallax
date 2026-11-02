import { existsSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** The infrastructure scope's root: the tooling package every provider package sits beside. */
export const INFRA_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

/**
 * Every provider package under *root*, by directory name, sorted.
 *
 * A provider is any immediate subdirectory holding a `package.json`, which is
 * what `pnpm-workspace.yaml` admits, so a new provider is discovered without a
 * change here.
 */
export function providerPackages(root: string = INFRA_ROOT): string[] {
  return readdirSync(root, { withFileTypes: true })
    .filter(
      (entry) =>
        entry.isDirectory() &&
        entry.name !== "node_modules" &&
        existsSync(join(root, entry.name, "package.json")),
    )
    .map((entry) => entry.name)
    .sort();
}
