import { describe, expect, it } from "vitest";
import {
  auditProblems,
  auditReport,
  main,
  scopeAdvisories,
  workspaceAuditReport,
} from "../tools/audit.ts";
import { captured, scratch, written } from "./scratch.ts";

function advisory(id: string, paths: string[]): object {
  return {
    github_advisory_id: id,
    module_name: "pkg",
    severity: "high",
    title: "a flaw",
    findings: [{ paths }],
  };
}

const report = {
  advisories: {
    1: advisory("GHSA-root", [".>markdownlint-cli2>katex"]),
    2: advisory("GHSA-tooling", ["infra>eslint>minimatch"]),
    3: advisory("GHSA-provider", ["infra__aws>aws-cdk-lib>x", ".>y"]),
    4: advisory("GHSA-nested", ["infra/aws>ajv"]),
    5: {},
    6: { findings: [{}, { paths: ["infrastructure>x"] }] },
    7: { findings: [{ paths: ["infra"] }] },
  },
};

const exceptions = [{ advisory: "GHSA-tooling", package: "minimatch", reason: "reviewed" }];

describe("the dependency audit", () => {
  it("judges only advisories some infrastructure package reaches", () => {
    expect(scopeAdvisories(report).map((found) => found.advisory)).toEqual([
      "GHSA-tooling",
      "GHSA-provider",
      "GHSA-nested",
      "unidentified",
    ]);
  });

  it("still names an advisory the report describes only partly", () => {
    expect(scopeAdvisories({ advisories: { 7: report.advisories[7] } })).toEqual([
      { advisory: "unidentified", package: "unknown", severity: "unknown", title: "" },
    ]);
  });

  it("refuses a report with no advisories table", () => {
    expect(() => scopeAdvisories({ error: "offline" })).toThrow("no advisories table");
    expect(() => scopeAdvisories(null)).toThrow("no advisories table");
  });

  it("fails each unexplained advisory and each stale exception", () => {
    const found = scopeAdvisories(report);
    expect(auditProblems(found, exceptions)).toEqual([
      "pkg has high advisory GHSA-provider: a flaw",
      "pkg has high advisory GHSA-nested: a flaw",
      "unknown has unknown advisory unidentified: ",
    ]);
    expect(auditProblems([], exceptions)).toEqual([
      "the exception for minimatch GHSA-tooling no longer matches an advisory",
    ]);
  });

  it("passes when every reachable advisory has a reviewed exception", () => {
    const root = scratch({ "audit-exceptions.json": JSON.stringify(exceptions) });
    const log = captured("log");
    expect(main([], root, () => ({ advisories: { 2: report.advisories[2] } }))).toBe(0);
    expect(written(log)).toContain("audit OK: 1 reviewed exception(s)");
  });

  it("fails on an unreadable report rather than passing it", () => {
    const root = scratch({ "audit-exceptions.json": "[]" });
    const error = captured("error");
    expect(
      main([], root, () => {
        throw new Error("pnpm audit produced no readable report: offline");
      }),
    ).toBe(1);
    expect(written(error)).toContain("offline");
  });

  it("reads the report pnpm prints", () => {
    expect(auditReport('{"advisories": {}}', "")).toEqual({ advisories: {} });
  });

  it("fails a repository pnpm cannot audit", () => {
    expect(() => workspaceAuditReport(scratch())).toThrow(
      "pnpm audit produced no readable report: Error: ERR_PNPM_AUDIT_NO_LOCKFILE",
    );
  });

  it("refuses arguments", () => {
    const error = captured("error");
    expect(main(["--fix"])).toBe(2);
    expect(written(error)).toContain("usage:");
  });
});
