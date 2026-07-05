import type { Capabilities, CaseShape } from "@parallax/core";
import { describe, expect, it } from "vitest";
import type { LoadedCase } from "../src/discover.js";
import {
  buildConformanceSliceCoverageReport,
  discoverCasePaths,
  loadCase,
  renderConformanceSliceCoverageMarkdown,
  SLICE_MVP_1_CAPABILITIES,
} from "../src/index.js";

function loaded(id: string, shape: CaseShape, tags: readonly string[]): LoadedCase {
  return {
    casePath: `core/compatibility/cases/${id}-case.yaml`,
    raw: {},
    shape,
    tags,
    lane: "harness",
    descriptor: {},
    fixtures: {},
  };
}

const SYNTHETIC_CAPABILITIES: Capabilities = {
  modules: ["m1", "m2"],
  dialects: ["postgres"],
  caseShapes: ["read", "writeSequence"],
  caseTags: { include: ["slice"] },
  commands: ["describe", "compile", "run"],
  provisioning: "self-managed",
};

describe("conformance slice coverage report", () => {
  it("counts claimed cases and out-of-claim reasons by command", () => {
    const report = buildConformanceSliceCoverageReport(
      [
        loaded("0001", "read", ["m1", "slice"]),
        loaded("0002", "writeSequence", ["m2", "slice"]),
        loaded("0003", "read", ["m3", "slice"]),
        loaded("0004", "read", ["m1"]),
        loaded("0005", "coherence", ["m1", "slice"]),
      ],
      SYNTHETIC_CAPABILITIES,
    );

    expect(report.sliceTag).toBe("slice");
    expect(report.totalCorpusCases).toBe(5);
    expect(report.claimedCases).toBe(2);
    expect(report.claimedCaseIds).toEqual(["0001", "0002"]);
    expect(report.byShape).toEqual({ read: 1, writeSequence: 1 });
    expect(report.byModule).toEqual({ m1: 1, m2: 1 });

    for (const command of report.byCommand) {
      expect(command.claimedCases).toBe(2);
      expect(command.outOfClaim["unsupported-case-tag"]).toBe(1);
      expect(command.outOfClaim["missing-include-tag"]).toBe(1);
      expect(command.outOfClaim["unsupported-shape"]).toBe(1);
    }
  });

  it("renders a GitHub-summary friendly markdown table", () => {
    const report = buildConformanceSliceCoverageReport(
      [loaded("0001", "read", ["m1", "slice"])],
      SYNTHETIC_CAPABILITIES,
    );

    expect(renderConformanceSliceCoverageMarkdown(report)).toContain("Claimed cases: **1 / 1**");
    expect(renderConformanceSliceCoverageMarkdown(report)).toContain("| `compile` | 1 | 0 |");
  });

  it("covers the real slice-mvp-1 slice", () => {
    const cases = discoverCasePaths().map(loadCase);
    const report = buildConformanceSliceCoverageReport(cases, SLICE_MVP_1_CAPABILITIES);

    expect(report.sliceTag).toBe("slice-mvp-1");
    expect(report.claimedCases).toBe(123);
    expect(report.byCommand.map((c) => [c.command, c.claimedCases])).toEqual([
      ["compile", 123],
      ["run", 123],
    ]);
    expect(renderConformanceSliceCoverageMarkdown(report)).toContain(
      "TypeScript Conformance Slice Coverage",
    );
  });
});
