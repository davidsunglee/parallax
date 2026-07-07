#!/usr/bin/env node
/**
 * Test-file typecheck gate. Each package's `tsconfig.json` only `include`s
 * `src/**`, and vitest strips types without checking — so neither `tsc -b`
 * (the build gate) nor the vitest lanes ever typecheck `test/**`. Test-file
 * type errors are therefore invisible to CI. This script closes that hole.
 *
 * It discovers every `packages/<pkg>/tsconfig.test.json` (a checked-in sibling
 * of each package's `tsconfig.json` that adds `test/**` to `include` and turns
 * off emit / composite) and runs `tsc --noEmit -p <cfg>` for each, reporting a
 * per-package pass/fail summary and exiting non-zero if any package errors.
 *
 * The per-package configs are NOT part of the `tsc -b` solution graph, so they
 * need each sibling package's emitted `dist/*.d.ts` to already exist. The build
 * MUST run first — the `ts:typecheck-tests` script chains `pnpm run ts:typecheck`
 * (i.e. `tsc -b`) before invoking this file. Run standalone only after a build.
 *
 * Run: `pnpm run ts:typecheck-tests`  (builds first, then this)
 * Or, after a build:  `node languages/typescript/scripts/typecheck-tests.mjs`
 */

import { spawnSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const TS_ROOT = resolve(HERE, "..");
const REPO_ROOT = resolve(TS_ROOT, "../..");
const PACKAGES_DIR = resolve(TS_ROOT, "packages");

const require = createRequire(import.meta.url);
// Run tsc's JS entrypoint under the current Node — portable and shell-free.
const TSC = require.resolve("typescript/bin/tsc");

/** Every package that ships a `tsconfig.test.json`, in stable (sorted) order. */
function discoverConfigs() {
  return readdirSync(PACKAGES_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()
    .map((pkg) => ({ pkg, config: resolve(PACKAGES_DIR, pkg, "tsconfig.test.json") }))
    .filter(({ config }) => existsSync(config));
}

function main() {
  const configs = discoverConfigs();
  if (configs.length === 0) {
    process.stderr.write("no tsconfig.test.json files found under packages/*\n");
    process.exit(1);
  }

  process.stdout.write(`Typechecking test files for ${configs.length} package(s)…\n\n`);

  const failed = [];
  for (const { pkg, config } of configs) {
    const result = spawnSync(process.execPath, [TSC, "--noEmit", "-p", config], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    });
    const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
    if (result.status === 0) {
      process.stdout.write(`  PASS  ${pkg}\n`);
    } else {
      failed.push(pkg);
      process.stdout.write(`  FAIL  ${pkg}\n`);
      if (output.length > 0) {
        process.stdout.write(`${indent(output)}\n`);
      }
    }
  }

  process.stdout.write("\n");
  if (failed.length > 0) {
    process.stdout.write(
      `test typecheck FAILED — ${failed.length} package(s) with errors: ${failed.join(", ")}\n`,
    );
    process.exit(1);
  }
  process.stdout.write(`test typecheck passed — ${configs.length} package(s) clean\n`);
}

/** Indent captured tsc output so it nests visibly under its package heading. */
function indent(text) {
  return text
    .split("\n")
    .map((line) => `        ${line}`)
    .join("\n");
}

main();
