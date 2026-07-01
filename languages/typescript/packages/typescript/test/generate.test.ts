/**
 * `parallax generate` / `generate --check` + generated-barrel typecheck (Phase 9
 * automated verification).
 *
 * Proves three things against a sample descriptor set:
 *  1. `checkGenerate` validates descriptors + generation WITHOUT writing (the
 *     `--check` gate) and reports the descriptors it consumed.
 *  2. `generate` materializes a well-formed `#parallax` barrel.
 *  3. The generated barrel TYPECHECKS: `tsc --noEmit` over the emitted file
 *     (with `@parallax/typescript` mapped to the built dist) exits 0, so the
 *     generated typed surface is statically sound (spec §5, codegen not
 *     reflection).
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { BARREL_FILE, checkGenerate, generate } from "../src/codegen/index.js";
import { defineParallaxConfig } from "../src/config.js";

/** The typescript package root (this test sits at `<pkg>/test/generate.test.ts`). */
const PACKAGE_ROOT = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
/** The committed sample app whose descriptor the test generates from. */
const SAMPLE_APP = resolve(PACKAGE_ROOT, "../../examples/orders-app");
/** The built dist that the generated barrel's `@parallax/typescript` import resolves to. */
const DIST = resolve(PACKAGE_ROOT, "dist");

let workDir: string;

beforeAll(() => {
  workDir = mkdtempSync(join(tmpdir(), "parallax-generate-"));
});

afterAll(() => {
  rmSync(workDir, { recursive: true, force: true });
});

describe("parallax generate", () => {
  it("generate --check validates the sample descriptor without writing", () => {
    const config = defineParallaxConfig({
      descriptors: ["parallax/**/*.yaml"],
      output: join(workDir, "unwritten"),
    });
    const result = checkGenerate(config, SAMPLE_APP);
    expect(result.descriptorPaths.length).toBeGreaterThan(0);
    expect(result.descriptorPaths.every((p) => p.endsWith(".yaml"))).toBe(true);
    // The check plan carries the barrel it WOULD write, but wrote nothing.
    expect(result.files.map((f) => f.path)).toEqual([BARREL_FILE]);
  });

  it("generate materializes a barrel that typechecks (spec §5)", () => {
    const outputDir = join(workDir, "generated");
    const config = defineParallaxConfig({ descriptors: ["parallax/**/*.yaml"], output: outputDir });
    const result = generate(config, SAMPLE_APP);
    const barrelPath = join(outputDir, BARREL_FILE);
    expect(result.files).toHaveLength(1);

    // Typecheck the emitted barrel with `@parallax/typescript` mapped to the
    // built dist (`.d.ts`). A generated symbol that does not typecheck fails here.
    const tsconfigPath = join(workDir, "tsconfig.typecheck.json");
    writeFileSync(tsconfigPath, JSON.stringify(typecheckConfig(barrelPath), null, 2), "utf8");
    const tsc = resolve(PACKAGE_ROOT, "../../../../node_modules/.bin/tsc");
    expect(() =>
      execFileSync(tsc, ["-p", tsconfigPath], { stdio: "pipe", cwd: workDir }),
    ).not.toThrow();
  });
});

/**
 * A standalone tsconfig that typechecks ONLY the generated barrel, resolving
 * `@parallax/typescript` (its lone workspace import) to the built dist so the
 * check needs no workspace linkage. Node-next resolution + the strict base flags
 * mirror the package's own tsconfig.
 */
function typecheckConfig(barrelPath: string): unknown {
  return {
    compilerOptions: {
      target: "ES2023",
      lib: ["ES2023"],
      module: "NodeNext",
      moduleResolution: "NodeNext",
      strict: true,
      exactOptionalPropertyTypes: true,
      noUncheckedIndexedAccess: true,
      skipLibCheck: true,
      noEmit: true,
      types: [],
      baseUrl: ".",
      paths: {
        "@parallax/typescript": [join(DIST, "index.d.ts")],
        "@parallax/typescript/config": [join(DIST, "config.d.ts")],
      },
    },
    files: [barrelPath],
  };
}
