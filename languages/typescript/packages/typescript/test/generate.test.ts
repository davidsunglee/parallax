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
 *     generated typed surface is statically sound (spec §7, codegen not
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
/** The built `@parallax/dialect` dist the consumer's `postgresDialect` import resolves to. */
const DIALECT_DIST = resolve(PACKAGE_ROOT, "../dialect/dist");

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

  it("generate materializes a barrel that typechecks (spec §7)", () => {
    const outputDir = join(workDir, "generated");
    const config = defineParallaxConfig({ descriptors: ["parallax/**/*.yaml"], output: outputDir });
    const result = generate(config, SAMPLE_APP);
    const barrelPath = join(outputDir, BARREL_FILE);
    expect(result.files).toHaveLength(1);

    // A consumer that exercises the generated typed surface as an application
    // would — crucially, the no-arg `find()` shorthand (MAJOR-2): the generated
    // `EntityFinder<T>` interface MUST accept `find()` with no predicate.
    const consumerPath = join(outputDir, "consumer.ts");
    writeFileSync(consumerPath, CONSUMER_SOURCE, "utf8");

    // Typecheck the emitted barrel + the consumer with `@parallax/typescript`
    // mapped to the built dist (`.d.ts`). A generated symbol that does not
    // typecheck — or a `find()` the interface rejects — fails here.
    const tsconfigPath = join(workDir, "tsconfig.typecheck.json");
    writeFileSync(
      tsconfigPath,
      JSON.stringify(typecheckConfig(barrelPath, consumerPath), null, 2),
      "utf8",
    );
    const tsc = resolve(PACKAGE_ROOT, "../../../../node_modules/.bin/tsc");
    expect(() =>
      execFileSync(tsc, ["-p", tsconfigPath], { stdio: "pipe", cwd: workDir }),
    ).not.toThrow();
  });
});

/**
 * A tiny application consumer of the generated barrel. It proves the generated
 * typed surface accepts BOTH the no-arg `find()` shorthand (spec §2.3, MAJOR-2)
 * and the explicit `find(Entity.all())` form. `orders` is the `Order` finder
 * (its table `orders` camelizes to itself); `Order.all()` is the generated
 * unfiltered predicate.
 */
const CONSUMER_SOURCE = [
  'import { parallax, Order } from "./index.js";',
  'import type { ParallaxDatabase } from "@parallax/typescript";',
  'import { postgresDialect } from "@parallax/dialect";',
  "declare const db: ParallaxDatabase;",
  // The dialect is injected beside the database at the composition root (required).
  "const px = parallax({ database: db, dialect: postgresDialect });",
  "px.orders.find(); // no-arg shorthand — MUST typecheck (MAJOR-2)",
  "px.orders.find(Order.all()); // explicit form still typechecks",
  "// the typed transaction MUST accept + forward TransactionOptions (M8 strategy).",
  'void px.transaction(async (tx) => tx.orders.find().toArray(), { concurrency: "optimistic" });',
  "void px.transaction(async (tx) => tx.orders.find().toArray()); // options are optional",
  "",
].join("\n");

/**
 * A standalone tsconfig that typechecks the generated barrel and its consumer,
 * resolving `@parallax/typescript` (their lone workspace import) to the built
 * dist so the check needs no workspace linkage. Node-next resolution + the strict
 * base flags mirror the package's own tsconfig.
 */
function typecheckConfig(barrelPath: string, consumerPath: string): unknown {
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
        "@parallax/dialect": [join(DIALECT_DIST, "index.d.ts")],
      },
    },
    files: [barrelPath, consumerPath],
  };
}
