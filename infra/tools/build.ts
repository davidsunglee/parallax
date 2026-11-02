import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { isolatedEnvironment, runInherited, type Command, type Runner } from "./isolation.ts";
import { runWhenMain } from "./entry.ts";
import { INFRA_ROOT, providerPackages } from "./workspace.ts";

const TYPESCRIPT_COMPILER = fileURLToPath(import.meta.resolve("typescript/bin/tsc"));
const CDK_CLI = fileURLToPath(import.meta.resolve("aws-cdk/bin/cdk"));

/** The compiled output and cloud assembly a build replaces, relative to a provider package. */
export const BUILD_OUTPUTS = ["dist", "cdk.out"] as const;

/**
 * What building one provider package runs: compile it, then, for a CDK app,
 * synthesize the compiled app through the pinned CLI with lookups disabled, so
 * synthesis reads only committed context and any warning fails it.
 */
export function buildCommands(packageDir: string): Command[] {
  const commands: Command[] = [
    {
      program: process.execPath,
      args: [TYPESCRIPT_COMPILER, "-p", "tsconfig.build.json"],
      cwd: packageDir,
    },
  ];
  if (existsSync(join(packageDir, "cdk.json"))) {
    commands.push({
      program: process.execPath,
      args: [
        CDK_CLI,
        "synth",
        "--strict",
        "--no-lookups",
        "--no-notices",
        "--ci",
        "--quiet",
        "--output",
        "cdk.out",
      ],
      cwd: packageDir,
    });
  }
  return commands;
}

/**
 * Build every provider package from a clean slate in an isolated environment.
 *
 * Exit codes: 0 — every package built; otherwise the first failing step's status,
 * or 2 for a usage error.
 */
export function main(
  argv: readonly string[],
  root: string = INFRA_ROOT,
  run: Runner = runInherited,
): number {
  if (argv.length > 0) {
    console.error("usage: node tools/build.ts");
    return 2;
  }
  const env = isolatedEnvironment(process.env, mkdtempSync(join(tmpdir(), "parallax-infra-")));
  for (const provider of providerPackages(root)) {
    const packageDir = join(root, provider);
    for (const output of BUILD_OUTPUTS) {
      rmSync(join(packageDir, output), { recursive: true, force: true });
    }
    for (const command of buildCommands(packageDir)) {
      const status = run(command, env);
      if (status !== 0) return status;
    }
  }
  return 0;
}

await runWhenMain(import.meta, main);
