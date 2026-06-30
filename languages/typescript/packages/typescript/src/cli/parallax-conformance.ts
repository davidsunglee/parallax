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
  describe,
  loadCase,
  runCompile,
  runRun,
  TYPESCRIPT_ADAPTER,
} from "@parallax/conformance";
import type { Command, Diagnostic, Envelope, NonOk } from "@parallax/core";
import { ExitCode } from "@parallax/core";
import { PostgresProvider } from "../conformance/postgres-provider.js";

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

async function main(argv: readonly string[]): Promise<void> {
  const [command, ...rest] = argv;

  switch (command) {
    case "describe": {
      const envelope = assertValidEnvelope(describe(TYPESCRIPT_ADAPTER));
      emit(envelope, ExitCode.Ok);
      break;
    }
    case "compile": {
      const { caseArg, dialect } = requireCaseAndDialect("compile", parseOptions(rest));
      let envelope: Envelope;
      try {
        envelope = runCompile(loadCase(caseArg), dialect, TYPESCRIPT_ADAPTER);
      } catch (error) {
        envelope = asError("compile", error);
      }
      emit(envelope, exitCodeFor(envelope));
      break;
    }
    case "run": {
      const { caseArg, dialect } = requireCaseAndDialect("run", parseOptions(rest));
      let envelope: Envelope;
      let provider: PostgresProvider | undefined;
      try {
        // Provision the database only for an in-claim case: gate first (cheaply,
        // without booting a container) by compiling, which short-circuits to an
        // `unsupported` envelope for an out-of-claim request.
        const loaded = loadCase(caseArg);
        const gateProbe = runCompile(loaded, dialect, TYPESCRIPT_ADAPTER);
        if (gateProbe.status !== "ok") {
          emit(gateProbe, exitCodeFor(gateProbe));
        }
        provider = await PostgresProvider.start();
        envelope = await runRun(loaded, dialect, TYPESCRIPT_ADAPTER, provider);
      } catch (error) {
        envelope = asError("run", error);
      } finally {
        await provider?.close();
      }
      emit(envelope, exitCodeFor(envelope));
      break;
    }
    case undefined:
    case "":
    case "--help":
    case "-h": {
      process.stderr.write(
        "usage: parallax-conformance <describe|compile|run> [--case <path>] [--dialect <dialect>]\n",
      );
      process.exit(ExitCode.Usage);
      break;
    }
    default: {
      process.stderr.write(`unknown command: ${command}\n`);
      process.exit(ExitCode.Usage);
    }
  }
}

void main(process.argv.slice(2));
