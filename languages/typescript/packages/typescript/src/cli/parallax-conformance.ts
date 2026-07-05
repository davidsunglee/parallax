#!/usr/bin/env node
/**
 * `parallax-conformance` — the conformance adapter CLI.
 *
 * Contract (`core/spec/conformance-adapter-contract.md`): each command writes
 * exactly one JSON document to stdout that validates against
 * `conformance-adapter.schema.json`; stderr is free-form diagnostics; exit codes
 * are `0` ok, `10` unsupported, `1` error, `2` CLI usage error.
 *
 * `describe` reports the canonical slice claim. `compile` lowers a case to
 * canonical SQL + binds with no database. `run` provisions a clean `postgres:17`
 * via the composition-root provider (injected through the port) and reports the
 * observations. The provider is the **only** place the driver / Testcontainers
 * are touched.
 */
import {
  assertValidEnvelope,
  type CompatibilityDatabaseProvider,
  describe,
  loadCase,
  runCompile,
  runRun,
  TYPESCRIPT_ADAPTER,
} from "@parallax/conformance";
import type { Command, Diagnostic, Envelope, NonOk } from "@parallax/core";
import { ExitCode } from "@parallax/core";
import { MARIADB_DIALECT } from "@parallax/dialect";
import { MariaDbProvider } from "../conformance/mariadb-provider.js";
import { PostgresProvider } from "../conformance/postgres-provider.js";

/**
 * Select and boot the concrete provider for a run key — the composition root is the
 * only place allowed to construct a concrete adapter. `mariadb` boots the shipped
 * `@parallax/db-mariadb` corner; every other key defaults to Postgres. (A `mariadb`
 * run is gated out by the slice claim before this is reached, but the wiring lets
 * `PARALLAX_DATABASES=mariadb` select the second dialect once it is claimed.)
 */
function startProvider(dialect: string): Promise<CompatibilityDatabaseProvider> {
  return dialect === MARIADB_DIALECT ? MariaDbProvider.start() : PostgresProvider.start();
}

/** A resolved command result: the JSON document to emit and its exit code. */
interface Outcome {
  readonly document: unknown;
  readonly code: number;
}

/** Emit one JSON document to stdout and exit with the given code. */
function emit(document: unknown, code: number): never {
  process.stdout.write(`${JSON.stringify(document, null, 2)}\n`);
  process.exit(code);
}

/** Build a non-ok envelope (`error` / `unsupported`) with one diagnostic. */
function nonOk(command: NonOk["command"], status: NonOk["status"], diagnostic: Diagnostic): NonOk {
  return {
    schemaVersion: "1",
    command,
    status,
    adapter: TYPESCRIPT_ADAPTER,
    diagnostics: [diagnostic],
  };
}

/** The exit code that matches an envelope's status. */
function exitCodeFor(envelope: Envelope): number {
  if (envelope.status === "ok") {
    return ExitCode.Ok;
  }
  return envelope.status === "unsupported" ? ExitCode.Unsupported : ExitCode.Error;
}

/** Minimal `--flag value` / `--flag=value` parser for the CLI arguments. */
function parseOptions(args: readonly string[]): Record<string, string> {
  const options: Record<string, string> = {};
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === undefined || !arg.startsWith("--")) {
      continue;
    }
    const eq = arg.indexOf("=");
    if (eq !== -1) {
      options[arg.slice(2, eq)] = arg.slice(eq + 1);
    } else {
      const next = args[i + 1];
      if (next !== undefined && !next.startsWith("--")) {
        options[arg.slice(2)] = next;
        i += 1;
      } else {
        options[arg.slice(2)] = "";
      }
    }
  }
  return options;
}

/** Require `--case` and `--dialect`; emit a usage error if either is missing. */
function requireCaseAndDialect(
  command: "compile" | "run",
  options: Record<string, string>,
): { caseArg: string; dialect: string } {
  const caseArg = options.case;
  const dialect = options.dialect;
  if (!caseArg || !dialect) {
    emit(
      nonOk(command, "error", {
        code: "usage-error",
        message: `'${command}' requires --case <path> and --dialect <dialect>`,
      }),
      ExitCode.Usage,
    );
  }
  return { caseArg, dialect };
}

/** Wrap a thrown adapter failure into an `error` envelope (exit `1`). */
function asError(command: Command, error: unknown): NonOk {
  return nonOk(command, "error", {
    code: "adapter-error",
    message: error instanceof Error ? error.message : String(error),
  });
}

/** Resolve `describe` to its outcome. */
function handleDescribe(): Outcome {
  const envelope = assertValidEnvelope(describe(TYPESCRIPT_ADAPTER));
  return { document: envelope, code: ExitCode.Ok };
}

/** Resolve `compile` to its outcome (no database is touched). */
function handleCompile(rest: readonly string[]): Outcome {
  const { caseArg, dialect } = requireCaseAndDialect("compile", parseOptions(rest));
  let envelope: Envelope;
  try {
    envelope = runCompile(loadCase(caseArg), dialect, TYPESCRIPT_ADAPTER);
  } catch (error) {
    envelope = asError("compile", error);
  }
  return { document: envelope, code: exitCodeFor(envelope) };
}

/**
 * Resolve `run` to its outcome.
 *
 * The "no container for an out-of-claim case" invariant is structural here: the
 * cheap gate probe (`runCompile`, Docker-free) runs and **returns** for any
 * non-`ok` result BEFORE `PostgresProvider.start()`, so an out-of-claim or
 * load-error request never boots a container. The driver `try/finally` wraps only
 * the provisioning path, so any provider that was started is always closed.
 */
async function handleRun(rest: readonly string[]): Promise<Outcome> {
  const { caseArg, dialect } = requireCaseAndDialect("run", parseOptions(rest));

  // Gate first, without a container. A non-`ok` probe (out-of-claim ⇒
  // `unsupported`, or a load/compile failure ⇒ `error`) is the final outcome.
  let loaded: ReturnType<typeof loadCase>;
  let gateProbe: Envelope;
  try {
    loaded = loadCase(caseArg);
    gateProbe = runCompile(loaded, dialect, TYPESCRIPT_ADAPTER);
  } catch (error) {
    const envelope = asError("run", error);
    return { document: envelope, code: exitCodeFor(envelope) };
  }
  if (gateProbe.status !== "ok") {
    return { document: gateProbe, code: exitCodeFor(gateProbe) };
  }

  // In claim: provision a clean container, run, and always close the provider.
  let envelope: Envelope;
  let provider: CompatibilityDatabaseProvider | undefined;
  try {
    provider = await startProvider(dialect);
    envelope = await runRun(loaded, dialect, TYPESCRIPT_ADAPTER, provider);
  } catch (error) {
    envelope = asError("run", error);
  } finally {
    await provider?.close();
  }
  return { document: envelope, code: exitCodeFor(envelope) };
}

/**
 * Dispatch a command to its outcome. Known commands return an {@link Outcome}
 * for `main` to emit as one JSON document; anything else writes a usage line to
 * stderr and exits `2` (it emits no JSON document, so it never returns).
 */
async function resolveOutcome(
  command: string | undefined,
  rest: readonly string[],
): Promise<Outcome> {
  if (command === "describe") return handleDescribe();
  if (command === "compile") return handleCompile(rest);
  if (command === "run") return handleRun(rest);

  if (command === undefined || command === "" || command === "--help" || command === "-h") {
    process.stderr.write(
      "usage: parallax-conformance <describe|compile|run> [--case <path>] [--dialect <dialect>]\n",
    );
  } else {
    process.stderr.write(`unknown command: ${command}\n`);
  }
  process.exit(ExitCode.Usage);
}

async function main(argv: readonly string[]): Promise<void> {
  const [command, ...rest] = argv;
  const { document, code } = await resolveOutcome(command, rest);
  emit(document, code);
}

void main(process.argv.slice(2));
