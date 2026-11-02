import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ASSEMBLY_DIRECTORY, assemblyProblems, main } from "../tools/check-assembly.ts";
import { captured, scratch, written } from "./scratch.ts";

interface AssemblyFiles {
  readonly manifest?: object;
  readonly assets?: object;
  readonly present?: readonly string[];
}

const STACK = {
  type: "aws:cloudformation:stack",
  properties: { templateFile: "Stack.template.json" },
  additionalMetadataFile: "Stack.metadata.json",
};
const ASSETS = { type: "cdk:asset-manifest", properties: { file: "Stack.assets.json" } };
const ASSET_MANIFEST = {
  files: { a: { source: { path: "asset.a" } } },
  dockerImages: { b: { source: { directory: "asset.b" } } },
};
const COMPLETE = ["Stack.template.json", "Stack.metadata.json", "asset.a", "asset.b/Dockerfile"];

function assembly({ manifest, assets, present = COMPLETE }: AssemblyFiles): string {
  const files: Record<string, string> = Object.fromEntries(
    present.map((path) => [`aws/${ASSEMBLY_DIRECTORY}/${path}`, "{}"]),
  );
  files["aws/cdk.json"] = "{}";
  files["aws/package.json"] = "{}";
  if (manifest !== undefined) {
    files[`aws/${ASSEMBLY_DIRECTORY}/manifest.json`] = JSON.stringify(manifest);
  }
  if (assets !== undefined) {
    files[`aws/${ASSEMBLY_DIRECTORY}/Stack.assets.json`] = JSON.stringify(assets);
  }
  return scratch(files);
}

const complete = {
  manifest: { artifacts: { Stack: STACK, Assets: ASSETS, Report: { type: "cdk:report" } } },
  assets: ASSET_MANIFEST,
};

describe("cloud-assembly completeness", () => {
  it("passes a complete assembly that needed no lookup", () => {
    const root = assembly(complete);
    const log = captured("log");
    expect(main([], root)).toBe(0);
    expect(written(log)).toContain("1 cloud assembly(ies) complete");
  });

  it("fails an assembly that was never synthesized", () => {
    const root = assembly({});
    const error = captured("error");
    expect(main([], root)).toBe(1);
    expect(written(error)).toContain("holds no manifest.json");
  });

  it("fails an assembly that needed context nobody committed", () => {
    const problems = assemblyProblems(
      join(
        assembly({ manifest: { missing: [{ key: "availability-zones:account=1:region=r" }] } }),
        "aws",
        ASSEMBLY_DIRECTORY,
      ),
    );
    expect(problems).toEqual([
      "synthesis needed context that was not committed: availability-zones:account=1:region=r",
    ]);
  });

  it("fails an assembly whose stack lacks its template or metadata", () => {
    const root = assembly({ ...complete, present: ["asset.a", "asset.b"] });
    expect(assemblyProblems(join(root, "aws", ASSEMBLY_DIRECTORY))).toEqual([
      "Stack references missing Stack.template.json",
      "Stack references missing Stack.metadata.json",
    ]);
  });

  it("fails an assembly missing an asset it publishes", () => {
    const root = assembly({
      ...complete,
      present: ["Stack.template.json", "Stack.metadata.json", "asset.b"],
    });
    const error = captured("error");
    expect(main([], root)).toBe(1);
    expect(written(error)).toContain("aws: Assets lacks asset asset.a");
  });

  it("fails an assembly whose asset manifest is gone", () => {
    const root = assembly({ manifest: complete.manifest });
    expect(assemblyProblems(join(root, "aws", ASSEMBLY_DIRECTORY))).toEqual([
      "Assets references missing Stack.assets.json",
    ]);
  });

  it("skips a provider that is no CDK app", () => {
    const root = scratch({ "gcp/package.json": "{}" });
    captured("log");
    expect(main([], root)).toBe(0);
  });

  it("refuses arguments", () => {
    const error = captured("error");
    expect(main(["cdk.out"])).toBe(2);
    expect(written(error)).toContain("usage:");
  });
});
