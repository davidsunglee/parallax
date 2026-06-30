import { defineConfig } from "vitest/config";

/**
 * Workspace-wide vitest config. Tests live in per-package `test/` directories
 * (design decision: separate `test/` per package, trivially excluded from the
 * published `exports`). `vitest run --root languages/typescript` discovers every
 * `packages/<pkg>/test/**\/*.test.ts` across the workspace.
 */
export default defineConfig({
  test: {
    include: ["packages/*/test/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["packages/*/src/**/*.ts"],
    },
  },
});
