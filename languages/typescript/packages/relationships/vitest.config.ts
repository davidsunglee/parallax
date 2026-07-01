import { defineConfig } from "vitest/config";

/** Package-local vitest config so `pnpm --filter @parallax/relationships test`
 * runs this package's `test/` directory in isolation (and the workspace-wide
 * `packages/*​/test/**​/*.test.ts` glob discovers it under the root config). */
export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
  },
});
