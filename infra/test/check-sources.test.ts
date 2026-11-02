import { execFileSync } from "node:child_process";
import { describe, expect, it } from "vitest";
import {
  gateScope,
  gitListing,
  inventoryProblems,
  main,
  type GateScope,
} from "../tools/check-sources.ts";
import { INFRA_ROOT } from "../tools/workspace.ts";
import { captured, scratch, written } from "./scratch.ts";

const SCOPE: GateScope = {
  typechecked: new Set([
    "tools/check.ts",
    "aws/src/stack.ts",
    "aws/src/handler/index.mts",
    "aws/src/generated/record.ts",
    "aws/test/stack.test.ts",
    "aws/test/fixture.ts",
    "aws/lib/stray.ts",
    "test/twice.test.ts",
  ]),
  projects: [
    { name: "dbfree", include: ["test/**/*.test.ts", "*/test/**/*.test.ts"] },
    { name: "other", include: ["test/twice.test.ts"] },
  ],
  coverageInclude: ["tools/**/*.ts", "*/src/**/*.ts", "*/src/**/*.mts"],
  coverageExclude: ["*/src/generated/**"],
};

function git(root: string, ...args: string[]): void {
  execFileSync("git", args, { cwd: root, stdio: "ignore" });
}

describe("the source inventory", () => {
  it("accounts for measured sources, generated files, tests, and test support", () => {
    const tracked = [
      "tools/check.ts",
      "aws/src/stack.ts",
      "aws/src/handler/index.mts",
      "aws/src/generated/record.ts",
      "aws/test/stack.test.ts",
      "aws/test/fixture.ts",
      "aws/package.json",
      "README.md",
    ];
    expect(inventoryProblems({ tracked, untracked: [] }, SCOPE)).toEqual([]);
  });

  it("fails an authored file git does not know, but not installed or derived output", () => {
    const untracked = [
      "tools/new.ts",
      "aws/notes.md",
      "node_modules/x/index.js",
      "aws/dist/bin/app.js",
      "aws/cdk.out/manifest.json",
      "coverage/lcov.info",
      ".DS_Store",
    ];
    expect(inventoryProblems({ tracked: [], untracked }, SCOPE)).toEqual([
      "tools/new.ts exists on disk but not in git",
      "aws/notes.md exists on disk but not in git",
      "tools/new.ts is outside the type-checked program",
    ]);
  });

  it("fails authored script, which no TypeScript gate examines", () => {
    expect(inventoryProblems({ tracked: ["tools/run.mjs"], untracked: [] }, SCOPE)).toEqual([
      "tools/run.mjs is script; authored executable code is TypeScript",
    ]);
  });

  it("fails a source no gate reaches, and a test two projects select", () => {
    expect(
      inventoryProblems(
        { tracked: ["aws/lib/stray.ts", "test/twice.test.ts"], untracked: [] },
        SCOPE,
      ),
    ).toEqual([
      "aws/lib/stray.ts is no test, test support, coverage-excluded file, or coverage-measured source",
      "test/twice.test.ts is selected by 2 test projects; a test belongs to one",
    ]);
  });

  it("holds TypeScript of either module format to the same gates", () => {
    expect(
      inventoryProblems(
        { tracked: ["aws/lib/module.mts", "aws/lib/common.cts"], untracked: [] },
        SCOPE,
      ),
    ).toEqual([
      "aws/lib/common.cts is outside the type-checked program",
      "aws/lib/common.cts is no test, test support, coverage-excluded file, or coverage-measured source",
      "aws/lib/module.mts is outside the type-checked program",
      "aws/lib/module.mts is no test, test support, coverage-excluded file, or coverage-measured source",
    ]);
  });

  it("lists tracked files and untracked ones, ignored files included", () => {
    const root = scratch({
      ".gitignore": "ignored.ts\n",
      "tracked.ts": "",
      "untracked.ts": "",
      "ignored.ts": "",
    });
    git(root, "init", "-q");
    git(root, "add", ".gitignore", "tracked.ts");
    const listing = gitListing(root);
    expect([...listing.tracked].sort()).toEqual([".gitignore", "tracked.ts"]);
    expect([...listing.untracked].sort()).toEqual(["ignored.ts", "untracked.ts"]);
  });

  it("reads the scope's own inventories", async () => {
    const scope = await gateScope(INFRA_ROOT);
    expect(scope.projects.map((project) => project.name)).toEqual(["dbfree"]);
    expect(scope.coverageInclude).toContain("tools/**/*.ts");
    expect(scope.coverageExclude).toEqual(["*/src/generated/**", "vitest.config.ts"]);
    expect(scope.typechecked).toContain("tools/check-sources.ts");
    expect(scope.typechecked).toContain("aws/bin/app.ts");
    expect(scope.typechecked).toContain("aws/src/role-bootstrap-handler/index.mts");
    expect(scope.coverageInclude).toContain("*/src/**/*.mts");
  });

  it("refuses a scope whose type-check configuration cannot be read", async () => {
    const root = scratch({
      "vitest.projects.json": "[]",
      "vitest.config.ts": "export default { test: { coverage: { include: [], exclude: [] } } };\n",
    });
    await expect(gateScope(root)).rejects.toThrow("tsconfig.json");
  });

  it("passes the scope as committed", async () => {
    const log = captured("log");
    expect(await main([])).toBe(0);
    expect(written(log)).toContain("source check OK");
  });

  it("fails a scope holding a source outside its gates", async () => {
    const root = scratch({
      "tsconfig.json": JSON.stringify({ include: ["src"] }),
      "vitest.projects.json": JSON.stringify([{ name: "dbfree", include: ["test/**/*.test.ts"] }]),
      "vitest.config.ts":
        'export default { test: { coverage: { include: ["src/**/*.ts"], exclude: [] } } };\n',
      "src/kept.ts": "export const kept = 1;\n",
      "lib/stray.ts": "export const stray = 1;\n",
    });
    git(root, "init", "-q");
    git(root, "add", ".");
    const error = captured("error");
    expect(await main([], root)).toBe(1);
    expect(written(error)).toContain("lib/stray.ts is outside the type-checked program");
  });

  it("refuses arguments", async () => {
    const error = captured("error");
    expect(await main(["infra"])).toBe(2);
    expect(written(error)).toContain("usage:");
  });
});
