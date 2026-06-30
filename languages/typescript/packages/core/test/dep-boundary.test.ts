import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

/** Resolve a path relative to the TypeScript workspace root (`languages/typescript/`). */
function tsWorkspacePath(relative: string): string {
  const root = fileURLToPath(new URL("../../../", import.meta.url));
  return `${root}${relative}`;
}

/** Resolve the dependency-cruiser CLI entry from the repo-root node_modules. */
function depcruiseBin(): string {
  return tsWorkspacePath("../../node_modules/dependency-cruiser/bin/dependency-cruise.mjs");
}

/**
 * Run dependency-cruiser against a single target with the workspace allowlist
 * config, from the TypeScript workspace root. Invoked via `node` directly (not
 * `pnpm exec`) because the TypeScript workspace root has no `package.json`.
 */
function depcruise(target: string): { status: number; output: string } {
  const cwd = tsWorkspacePath("");
  const result = spawnSync(
    process.execPath,
    [depcruiseBin(), "--config", ".dependency-cruiser.cjs", target],
    { cwd, encoding: "utf8" },
  );
  return {
    status: result.status ?? -1,
    output: `${result.stdout ?? ""}${result.stderr ?? ""}`,
  };
}

it("flags the planted illegal core -> operation import (negative test)", () => {
  const fixture = "packages/core/test/fixtures/illegal-import.ts";
  const { status, output } = depcruise(fixture);

  // A wrong-direction edge must fail the build (non-zero exit) and be reported.
  expect(status, `depcruise output:\n${output}`).not.toBe(0);
  expect(output).toMatch(/not-in-allowed|error/i);
});

it("passes on a legal same-package target (positive control)", () => {
  const { status } = depcruise("packages/core/src/index.ts");
  expect(status).toBe(0);
});
