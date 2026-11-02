import { spawnSync } from "node:child_process";
import { cpSync, mkdirSync, symlinkSync, writeFileSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { OUTPUT_DIRECTORIES } from "../tools/check-sources.ts";
import { isolatedEnvironment } from "../tools/isolation.ts";
import { INFRA_ROOT, providerPackages } from "../tools/workspace.ts";
import { scratch } from "./scratch.ts";

export const REPOSITORY_ROOT = dirname(INFRA_ROOT);

/** What a child process exited with and printed. */
export interface Outcome {
  readonly status: number | null;
  readonly output: string;
}

/** Runs *program* in *cwd* with nothing but the isolated environment, capturing its output. */
export function execute(program: string, args: readonly string[], cwd: string): Outcome {
  const result = spawnSync(program, args, {
    cwd,
    encoding: "utf8",
    env: isolatedEnvironment(process.env, scratch()),
  });
  return { status: result.status, output: `${result.stdout}${result.stderr}` };
}

/** A copy of the scope, sharing its installed packages, in which a violation can be planted. */
export interface Sandbox {
  /** The copy's repository root, holding the workspace declaration. */
  readonly root: string;
  /** The copy of the infrastructure scope. */
  readonly infra: string;
  /** Write *content* at *path*, relative to the scope copy. */
  plant(path: string, content: string): void;
}

function isOutput(source: string): boolean {
  return relative(INFRA_ROOT, source)
    .split(sep)
    .some((segment) => OUTPUT_DIRECTORIES.has(segment));
}

/** A fresh copy of the committed scope, with every package's installation linked in. */
export function sandbox(): Sandbox {
  const root = scratch();
  const infra = join(root, "infra");
  cpSync(INFRA_ROOT, infra, { recursive: true, filter: (source) => !isOutput(source) });
  for (const packageDir of ["", ...providerPackages()]) {
    symlinkSync(
      join(INFRA_ROOT, packageDir, "node_modules"),
      join(infra, packageDir, "node_modules"),
    );
  }
  cpSync(join(REPOSITORY_ROOT, "pnpm-workspace.yaml"), join(root, "pnpm-workspace.yaml"));
  writeFileSync(join(root, "package.json"), JSON.stringify({ name: "sandbox", private: true }));
  return {
    root,
    infra,
    plant: (path, content) => {
      mkdirSync(dirname(join(infra, path)), { recursive: true });
      writeFileSync(join(infra, path), content);
    },
  };
}

/** The scope's own installation of a tool's command. */
export function tool(command: string): string {
  return join(INFRA_ROOT, "node_modules", ".bin", command);
}
