import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { parse } from "yaml";
import { runWhenMain } from "./entry.ts";
import { INFRA_ROOT, providerPackages } from "./workspace.ts";

/** The only specification an infrastructure package may give a dependency. */
export const CATALOG_SPECIFIER = "catalog:";

const EXACT_VERSION = /^\d+\.\d+\.\d+$/;
const DEPENDENCY_FIELDS = [
  "dependencies",
  "devDependencies",
  "peerDependencies",
  "optionalDependencies",
] as const;

type Manifest = Partial<Record<(typeof DEPENDENCY_FIELDS)[number], Record<string, string>>>;

/** One package manifest under the scope, by its scope-relative path. */
export interface ScopeManifest {
  readonly path: string;
  readonly manifest: Manifest;
}

/**
 * Every way the scope's dependencies could drift from one exact, reviewed pin:
 * a package specifying a version of its own, a catalog entry that is a range,
 * or a catalog entry nothing uses.
 */
export function pinProblems(
  catalog: Readonly<Record<string, unknown>>,
  manifests: readonly ScopeManifest[],
): string[] {
  const problems: string[] = [];
  const referenced = new Set<string>();
  for (const { path, manifest } of manifests) {
    for (const field of DEPENDENCY_FIELDS) {
      for (const [name, specifier] of Object.entries(manifest[field] ?? {})) {
        referenced.add(name);
        const problem = specifierProblem(catalog, name, specifier);
        if (problem !== undefined) problems.push(`${path} ${field} ${problem}`);
      }
    }
  }
  return [...problems, ...catalogProblems(catalog, referenced)];
}

function specifierProblem(
  catalog: Readonly<Record<string, unknown>>,
  name: string,
  specifier: string,
): string | undefined {
  if (specifier !== CATALOG_SPECIFIER) return `gives ${name} "${specifier}" rather than "catalog:"`;
  if (!(name in catalog)) return `names ${name}, which the catalog does not pin`;
  return undefined;
}

function catalogProblems(
  catalog: Readonly<Record<string, unknown>>,
  referenced: ReadonlySet<string>,
): string[] {
  const problems: string[] = [];
  for (const [name, version] of Object.entries(catalog).sort()) {
    if (typeof version !== "string" || !EXACT_VERSION.test(version)) {
      problems.push(
        `the catalog pins ${name} to "${String(version)}" rather than one exact version`,
      );
    } else if (!referenced.has(name)) {
      problems.push(`the catalog pins ${name}, which no infrastructure package uses`);
    }
  }
  return problems;
}

function readManifest(root: string, path: string): ScopeManifest {
  return { path, manifest: JSON.parse(readFileSync(join(root, path), "utf8")) as Manifest };
}

/**
 * Check that every infrastructure dependency is pinned exactly, once, in the
 * workspace catalog.
 *
 * Exit codes: 0 — every pin is exact and used; 1 — one is not; 2 — usage error.
 */
export function main(argv: readonly string[], root: string = INFRA_ROOT): number {
  if (argv.length > 0) {
    console.error("usage: node tools/audit-dependencies.ts");
    return 2;
  }
  const workspace = parse(readFileSync(join(dirname(root), "pnpm-workspace.yaml"), "utf8")) as {
    catalog?: Record<string, unknown>;
  };
  const manifests = [
    readManifest(root, "package.json"),
    ...providerPackages(root).map((provider) => readManifest(root, join(provider, "package.json"))),
  ];
  const problems = pinProblems(workspace.catalog ?? {}, manifests);
  for (const problem of problems) console.error(`dependency audit: ${problem}`);
  if (problems.length > 0) return 1;
  console.log(
    `dependency audit OK: ${String(manifests.length)} package(s) pinned through the catalog`,
  );
  return 0;
}

await runWhenMain(import.meta, main);
