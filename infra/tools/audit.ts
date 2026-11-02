import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { runWhenMain } from "./entry.ts";
import { INFRA_ROOT } from "./workspace.ts";

/** A reviewed reason a known advisory in the scope's dependency tree stays. */
export interface AuditException {
  readonly advisory: string;
  readonly package: string;
  readonly reason: string;
}

/** One advisory reachable from an infrastructure package. */
export interface Advisory {
  readonly advisory: string;
  readonly package: string;
  readonly severity: string;
  readonly title: string;
}

interface Finding {
  readonly paths?: readonly string[];
}

interface ReportedAdvisory {
  readonly github_advisory_id?: string;
  readonly module_name?: string;
  readonly severity?: string;
  readonly title?: string;
  readonly findings?: readonly Finding[];
}

/** A `pnpm audit` path whose first step, its workspace importer, is an infrastructure package. */
const SCOPE_PATH = /^infra(?:(?:\/|__)[^>]*)?(?:>|$)/;
const fromScope = (path: string): boolean => SCOPE_PATH.test(path);

/**
 * The advisories in a `pnpm audit --json` report that some infrastructure
 * package reaches. The lockfile is shared with the repository root, whose own
 * tooling is not this scope's subject.
 */
export function scopeAdvisories(report: unknown): Advisory[] {
  if (typeof report !== "object" || report === null || !("advisories" in report)) {
    throw new Error("the audit report holds no advisories table");
  }
  const reported = Object.values(report.advisories as Record<string, ReportedAdvisory>);
  return reported
    .filter((entry) =>
      (entry.findings ?? []).some((finding) => (finding.paths ?? []).some(fromScope)),
    )
    .map((entry) => ({
      advisory: entry.github_advisory_id ?? "unidentified",
      package: entry.module_name ?? "unknown",
      severity: entry.severity ?? "unknown",
      title: entry.title ?? "",
    }));
}

/** Every reachable advisory no exception covers, and every exception no longer needed. */
export function auditProblems(
  advisories: readonly Advisory[],
  exceptions: readonly AuditException[],
): string[] {
  const excepted = new Set(exceptions.map((exception) => exception.advisory));
  const found = new Set(advisories.map((advisory) => advisory.advisory));
  return [
    ...advisories
      .filter((advisory) => !excepted.has(advisory.advisory))
      .map(
        (advisory) =>
          `${advisory.package} has ${advisory.severity} advisory ${advisory.advisory}: ${advisory.title}`,
      ),
    ...exceptions
      .filter((exception) => !found.has(exception.advisory))
      .map(
        (exception) =>
          `the exception for ${exception.package} ${exception.advisory} no longer matches an advisory`,
      ),
  ];
}

/** The repository's `pnpm audit --json` report, which covers development dependencies too. */
export function workspaceAuditReport(repositoryRoot: string): unknown {
  const audit = spawnSync("pnpm", ["audit", "--json"], { cwd: repositoryRoot, encoding: "utf8" });
  return auditReport(audit.stdout, audit.stderr);
}

/** The report `pnpm audit --json` printed, refusing output that is not one. */
export function auditReport(stdout: string, stderr: string): unknown {
  try {
    return JSON.parse(stdout) as unknown;
  } catch {
    throw new Error(`pnpm audit produced no readable report: ${stderr.trim()}`);
  }
}

/**
 * Fail on any known advisory reachable from an infrastructure package that
 * `audit-exceptions.json` does not explain, and on any exception gone stale.
 *
 * Exit codes: 0 — nothing unexplained; 1 — an advisory or a stale exception, or an
 * unreadable report; 2 — usage error.
 */
export function main(
  argv: readonly string[],
  root: string = INFRA_ROOT,
  audit: (repositoryRoot: string) => unknown = workspaceAuditReport,
): number {
  if (argv.length > 0) {
    console.error("usage: node tools/audit.ts");
    return 2;
  }
  const exceptions = JSON.parse(
    readFileSync(join(root, "audit-exceptions.json"), "utf8"),
  ) as AuditException[];
  let problems: string[];
  try {
    problems = auditProblems(scopeAdvisories(audit(dirname(root))), exceptions);
  } catch (error) {
    problems = [(error as Error).message];
  }
  for (const problem of problems) console.error(`audit: ${problem}`);
  if (problems.length > 0) return 1;
  console.log(`audit OK: ${String(exceptions.length)} reviewed exception(s), nothing else known`);
  return 0;
}

await runWhenMain(import.meta, main);
