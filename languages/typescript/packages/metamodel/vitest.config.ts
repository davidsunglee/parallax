import { defineConfig } from "vitest/config";

/** Package-local vitest config so `pnpm --filter @parallax/metamodel test` runs
 * this package's `test/` directory in isolation. */
export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
  },
});
