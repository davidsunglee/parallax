import { defineConfig } from "vitest/config";
import projects from "./vitest.projects.json" with { type: "json" };

export default defineConfig({
  test: {
    testTimeout: 120_000,
    projects: projects.map(({ name, include }) => ({
      extends: true,
      test: { name, include },
    })),
    coverage: {
      provider: "v8",
      include: ["*.ts", "tools/**/*.ts", "*/bin/**/*.ts", "*/src/**/*.ts", "*/tools/**/*.ts"],
      // Generated output, and this file, which the runner loads before any test can measure it.
      exclude: ["*/src/generated/**", "vitest.config.ts"],
      // Repository-relative paths, which changed-line coverage matches against the diff.
      reporter: ["text", ["lcov", { projectRoot: ".." }]],
      reportsDirectory: "coverage",
      thresholds: {
        statements: 95,
        branches: 95,
        functions: 95,
        lines: 95,
      },
    },
  },
});
