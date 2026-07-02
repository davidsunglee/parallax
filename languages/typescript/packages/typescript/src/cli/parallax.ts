#!/usr/bin/env node
/**
 * `parallax` — the developer-facing CLI (spec §7).
 *
 * Sub-commands:
 *  - `parallax init` — scaffold `parallax.config.js` + add `parallax:generate` /
 *    `parallax:check` scripts (`--dry-run` / `--force` / `--wire-lifecycle`).
 *  - `parallax generate` — materialize the `#parallax` barrel from the config's
 *    descriptors.
 *  - `parallax generate --check` — validate descriptors + generation WITHOUT
 *    writing (fails if generation would fail; generated files are uncommitted, so
 *    this is not a git-drift check).
 *
 * Conformance is exposed through the separate `parallax-conformance` CLI, not
 * here (spec §7).
 */
import { checkGenerate, generate, summarize } from "../codegen/index.js";
import { loadConfig, resolveConfigPath } from "./config-loader.js";
import { applyInitPlan, describeAction, type InitAction, planInit } from "./init.js";

/** A minimal `--flag[=value]` parser: returns the set flags + the positionals. */
function parseArgs(args: readonly string[]): {
  flags: Record<string, string | boolean>;
  positionals: string[];
} {
  const flags: Record<string, string | boolean> = {};
  const positionals: string[] = [];
  for (const arg of args) {
    if (arg.startsWith("--")) {
      const eq = arg.indexOf("=");
      if (eq === -1) {
        flags[arg.slice(2)] = true;
      } else {
        flags[arg.slice(2, eq)] = arg.slice(eq + 1);
      }
    } else {
      positionals.push(arg);
    }
  }
  return { flags, positionals };
}

/** Run `parallax generate [--check] [--config <path>]`. */
async function runGenerate(args: readonly string[]): Promise<number> {
  const { flags } = parseArgs(args);
  const cwd = process.cwd();
  const configPath = resolveConfigPath(
    cwd,
    typeof flags.config === "string" ? flags.config : undefined,
  );
  const config = await loadConfig(configPath);

  if (flags.check === true) {
    const result = checkGenerate(config, cwd);
    process.stderr.write(
      `parallax generate --check: OK (${result.descriptorPaths.length} descriptor(s) valid)\n`,
    );
    return 0;
  }
  const result = generate(config, cwd);
  process.stderr.write(`parallax generate: ${summarize(result, cwd)}\n`);
  return 0;
}

/** Run `parallax init [--dry-run] [--force] [--wire-lifecycle]`. */
function runInit(args: readonly string[]): number {
  const { flags } = parseArgs(args);
  const cwd = process.cwd();
  const plan: readonly InitAction[] = planInit({
    cwd,
    dryRun: flags["dry-run"] === true,
    force: flags.force === true,
    wireLifecycle: flags["wire-lifecycle"] === true,
  });
  if (flags["dry-run"] === true) {
    process.stderr.write("parallax init --dry-run (no files written):\n");
    for (const action of plan) {
      process.stderr.write(`${describeAction(action)}\n`);
    }
    return 0;
  }
  applyInitPlan(plan);
  process.stderr.write("parallax init:\n");
  for (const action of plan) {
    process.stderr.write(`${describeAction(action)}\n`);
  }
  return 0;
}

/** Print the top-level usage line. */
function usage(): void {
  process.stderr.write(
    "usage: parallax <init|generate> [--check] [--config <path>] [--dry-run] [--force] [--wire-lifecycle]\n",
  );
}

async function main(argv: readonly string[]): Promise<number> {
  const [command, ...rest] = argv;
  switch (command) {
    case "generate":
      return runGenerate(rest);
    case "init":
      return runInit(rest);
    case undefined:
    case "":
    case "--help":
    case "-h":
      usage();
      return 2;
    default:
      process.stderr.write(`unknown command: ${command}\n`);
      usage();
      return 2;
  }
}

main(process.argv.slice(2))
  .then((code) => process.exit(code))
  .catch((error: unknown) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exit(1);
  });
