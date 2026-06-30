#!/usr/bin/env node
import { assertValidEnvelope, describe, TYPESCRIPT_ADAPTER } from "@parallax/conformance";
import type { Diagnostic, NonOk } from "@parallax/core";
/**
 * `parallax-conformance` — the conformance adapter CLI.
 *
 * Contract (`core/spec/conformance-adapter-contract.md`): each command writes
 * exactly one JSON document to stdout that validates against
 * `conformance-adapter.schema.json`; stderr is free-form diagnostics; exit codes
 * are `0` ok, `10` unsupported, `1` error, `2` CLI usage error.
 *
 * This phase implements `describe` only. `compile` and `run` are registered but
 * return a usage-error placeholder until Phase 3 wires the runner.
 */
import { ExitCode } from "@parallax/core";

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

function main(argv: readonly string[]): void {
  const [command, ...rest] = argv;

  switch (command) {
    case "describe": {
      const envelope = assertValidEnvelope(describe(TYPESCRIPT_ADAPTER));
      emit(envelope, ExitCode.Ok);
      break;
    }
    case "compile":
    case "run": {
      // Registered but not yet wired (Phase 3). Surface a usage error so the
      // contract's exit-code semantics hold rather than emitting a malformed
      // envelope. Parsing options here keeps the dispatch shape stable.
      parseOptions(rest);
      emit(
        nonOk(command, "error", {
          code: "not-implemented",
          message: `'${command}' is not implemented until the Phase 3 walking skeleton lands`,
        }),
        ExitCode.Usage,
      );
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

main(process.argv.slice(2));
