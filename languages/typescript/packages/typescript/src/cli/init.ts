/**
 * `parallax init` — the conservative setup assistant (spec §7).
 *
 * Scaffolds a `parallax.config.js` (if absent) and adds explicit
 * `parallax:generate` / `parallax:check` scripts to the project `package.json`;
 * it wires `prebuild` / `pretest` lifecycle hooks only under `--wire-lifecycle`.
 * `--dry-run` reports the planned edits without writing; `--force` overwrites an
 * existing config. The function is pure over an in-memory plan so it is testable
 * without touching the filesystem — `applyInitPlan` performs the writes.
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { DEFAULT_IMPORT_ALIAS, DEFAULT_OUTPUT } from "../config.js";

/** Flags accepted by `parallax init`. */
export interface InitOptions {
  readonly cwd: string;
  readonly dryRun?: boolean;
  readonly force?: boolean;
  readonly wireLifecycle?: boolean;
}

/** One planned filesystem action (a write or a skip), for `--dry-run` reporting. */
export interface InitAction {
  readonly path: string;
  readonly kind: "create" | "overwrite" | "update" | "skip";
  readonly reason: string;
  /** The contents to write (absent for a skip). */
  readonly contents?: string;
}

/** The default `parallax.config.js` scaffold (a conservative, editable starter). */
export function configScaffold(): string {
  return [
    'import { defineParallaxConfig } from "@parallax/typescript/config";',
    "",
    "export default defineParallaxConfig({",
    '  descriptors: ["./parallax/**/*.yaml"],',
    `  output: ${JSON.stringify(DEFAULT_OUTPUT)},`,
    `  importAlias: ${JSON.stringify(DEFAULT_IMPORT_ALIAS)},`,
    "});",
    "",
  ].join("\n");
}

/** The scripts `init` adds by default (spec §7). */
const DEFAULT_SCRIPTS: Record<string, string> = {
  "parallax:generate": "parallax generate",
  "parallax:check": "parallax generate --check",
};

/** The lifecycle hooks `init` adds only under `--wire-lifecycle`. */
const LIFECYCLE_SCRIPTS: Record<string, string> = {
  prebuild: "parallax generate",
  pretest: "parallax generate",
};

/**
 * Compute the init plan (the actions `init` would take) without writing. The CLI
 * applies it via {@link applyInitPlan}, or prints it for `--dry-run`.
 */
export function planInit(options: InitOptions): readonly InitAction[] {
  const actions: InitAction[] = [];

  // 1. The config scaffold.
  const configPath = resolve(options.cwd, "parallax.config.js");
  if (existsSync(configPath) && !options.force) {
    actions.push({
      path: configPath,
      kind: "skip",
      reason: "already exists (use --force to overwrite)",
    });
  } else {
    actions.push({
      path: configPath,
      kind: existsSync(configPath) ? "overwrite" : "create",
      reason: "parallax generator config",
      contents: configScaffold(),
    });
  }

  // 2. package.json scripts (only if a package.json exists).
  const pkgPath = resolve(options.cwd, "package.json");
  if (!existsSync(pkgPath)) {
    actions.push({ path: pkgPath, kind: "skip", reason: "no package.json to add scripts to" });
    return actions;
  }
  const pkg = JSON.parse(readFileSync(pkgPath, "utf8")) as { scripts?: Record<string, string> };
  const scripts = { ...pkg.scripts };
  const wanted = {
    ...DEFAULT_SCRIPTS,
    ...(options.wireLifecycle ? LIFECYCLE_SCRIPTS : {}),
  };
  let changed = false;
  for (const [name, command] of Object.entries(wanted)) {
    if (scripts[name] === undefined) {
      scripts[name] = command;
      changed = true;
    }
  }
  if (changed) {
    const updated = { ...pkg, scripts };
    actions.push({
      path: pkgPath,
      kind: "update",
      reason: "add parallax scripts",
      contents: `${JSON.stringify(updated, null, 2)}\n`,
    });
  } else {
    actions.push({ path: pkgPath, kind: "skip", reason: "parallax scripts already present" });
  }
  return actions;
}

/** Apply an init plan to the filesystem (no-op for `skip` actions). */
export function applyInitPlan(plan: readonly InitAction[]): void {
  for (const action of plan) {
    if (action.kind !== "skip" && action.contents !== undefined) {
      writeFileSync(action.path, action.contents, "utf8");
    }
  }
}

/** A one-line human-readable summary of one planned action. */
export function describeAction(action: InitAction): string {
  return `  [${action.kind}] ${action.path} — ${action.reason}`;
}
