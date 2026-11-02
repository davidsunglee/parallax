import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join, matchesGlob, relative, sep } from "node:path";
import ts from "typescript";
import { runWhenMain } from "./entry.ts";
import { INFRA_ROOT } from "./workspace.ts";

/** Directories holding only derived or installed files, never authored ones. */
export const OUTPUT_DIRECTORIES: ReadonlySet<string> = new Set([
  "node_modules",
  "dist",
  "cdk.out",
  "coverage",
]);

const AUTHORED_EXTENSIONS = [
  ".ts",
  ".js",
  ".mjs",
  ".cjs",
  ".json",
  ".jsonc",
  ".md",
  ".yaml",
  ".yml",
];
const SCRIPT_EXTENSIONS = [".js", ".mjs", ".cjs"];
const TEST_DIRECTORIES = ["test/**", "*/test/**"];

/** Which files under the scope git knows, and which it does not. */
export interface SourceListing {
  readonly tracked: readonly string[];
  readonly untracked: readonly string[];
}

export interface TestProject {
  readonly name: string;
  readonly include: readonly string[];
}

/** Every inventory the scope's gates read, as root-relative paths and globs. */
export interface GateScope {
  readonly typechecked: ReadonlySet<string>;
  readonly projects: readonly TestProject[];
  readonly coverageInclude: readonly string[];
  readonly coverageExclude: readonly string[];
}

function isAuthored(path: string): boolean {
  return (
    !path.split("/").some((segment) => OUTPUT_DIRECTORIES.has(segment)) &&
    AUTHORED_EXTENSIONS.some((extension) => path.endsWith(extension))
  );
}

const matchesAny = (path: string, patterns: readonly string[]): boolean =>
  patterns.some((pattern) => matchesGlob(path, pattern));

function classificationProblem(path: string, scope: GateScope): string | undefined {
  const projects = scope.projects.filter((project) => matchesAny(path, project.include));
  if (projects.length > 1) {
    return `${path} is selected by ${String(projects.length)} test projects; a test belongs to one`;
  }
  const inventoried = [scope.coverageInclude, scope.coverageExclude, TEST_DIRECTORIES].some(
    (patterns) => matchesAny(path, patterns),
  );
  if (projects.length === 0 && !inventoried) {
    return `${path} is no test, test support, coverage-excluded file, or coverage-measured source`;
  }
  return undefined;
}

/**
 * Every way an authored file under the scope could escape its gates: by being
 * unknown to git, so that changed-line coverage never sees it; by being script
 * rather than TypeScript; or by falling outside the type-checked program, every
 * test project, and the coverage inventory alike.
 */
export function inventoryProblems(listing: SourceListing, scope: GateScope): string[] {
  const problems = listing.untracked
    .filter(isAuthored)
    .map((path) => `${path} exists on disk but not in git`);
  const authored = [...listing.tracked, ...listing.untracked].filter(isAuthored).sort();
  for (const path of authored) {
    if (SCRIPT_EXTENSIONS.some((extension) => path.endsWith(extension))) {
      problems.push(`${path} is script; authored executable code is TypeScript`);
      continue;
    }
    if (!path.endsWith(".ts")) continue;
    if (!scope.typechecked.has(path)) problems.push(`${path} is outside the type-checked program`);
    const problem = classificationProblem(path, scope);
    if (problem !== undefined) problems.push(problem);
  }
  return problems;
}

function gitFiles(root: string, args: readonly string[]): string[] {
  return execFileSync("git", ["ls-files", "-z", ...args, "--", "."], {
    cwd: root,
    encoding: "utf8",
  })
    .split("\0")
    .filter((path) => path.length > 0);
}

/** What git knows about *root*, untracked files including ignored ones. */
export function gitListing(root: string): SourceListing {
  return { tracked: gitFiles(root, ["--cached"]), untracked: gitFiles(root, ["--others"]) };
}

function typechecked(root: string): Set<string> {
  const file = join(root, "tsconfig.json");
  const read = ts.readConfigFile(file, (path) => ts.sys.readFile(path));
  if (read.error !== undefined) {
    throw new Error(ts.flattenDiagnosticMessageText(read.error.messageText, "\n"));
  }
  const config: unknown = read.config;
  const parsed = ts.parseJsonConfigFileContent(config, ts.sys, root, undefined, file);
  return new Set(parsed.fileNames.map((path) => relative(root, path).split(sep).join("/")));
}

interface CoverageSettings {
  readonly test: { readonly coverage: { readonly include: string[]; readonly exclude: string[] } };
}

/** The inventories the scope's own configuration declares. */
export async function gateScope(root: string): Promise<GateScope> {
  const projects = JSON.parse(
    readFileSync(join(root, "vitest.projects.json"), "utf8"),
  ) as TestProject[];
  const module = (await import(join(root, "vitest.config.ts"))) as { default: CoverageSettings };
  const { include, exclude } = module.default.test.coverage;
  return {
    typechecked: typechecked(root),
    projects,
    coverageInclude: include,
    coverageExclude: exclude,
  };
}

/**
 * Check that every authored infrastructure source is tracked and reached by
 * the scope's gates.
 *
 * Exit codes: 0 — every source is accounted for; 1 — one escapes; 2 — usage error.
 */
export async function main(argv: readonly string[], root: string = INFRA_ROOT): Promise<number> {
  if (argv.length > 0) {
    console.error("usage: node tools/check-sources.ts");
    return 2;
  }
  const listing = gitListing(root);
  const problems = inventoryProblems(listing, await gateScope(root));
  for (const problem of problems) console.error(`source check: ${problem}`);
  if (problems.length > 0) return 1;
  console.log(`source check OK: ${String(listing.tracked.length)} tracked file(s) accounted for`);
  return 0;
}

await runWhenMain(import.meta, main);
