import { describe, expect, it } from "vitest";
import { INFRA_ROOT, providerPackages } from "../tools/workspace.ts";
import { scratch } from "./scratch.ts";

describe("provider discovery", () => {
  it("finds each immediate subdirectory holding a package manifest", () => {
    const root = scratch({
      "gcp/package.json": "{}",
      "aws/package.json": "{}",
      "tools/check.ts": "",
      "node_modules/package.json": "{}",
      "nested/deeper/package.json": "{}",
    });
    expect(providerPackages(root)).toEqual(["aws", "gcp"]);
  });

  it("finds the AWS package beside the tooling", () => {
    expect(providerPackages()).toContain("aws");
    expect(providerPackages(INFRA_ROOT)).toEqual(providerPackages());
  });
});
