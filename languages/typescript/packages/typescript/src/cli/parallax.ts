#!/usr/bin/env node
/**
 * `parallax` — the developer-facing CLI.
 *
 * Sub-commands (`init`, `generate`, `generate --check`) land in Phase 9 with the
 * codegen / DSL surface. This phase ships the entry point only.
 */
function main(argv: readonly string[]): void {
  const [command] = argv;
  switch (command) {
    case undefined:
    case "":
    case "--help":
    case "-h": {
      process.stderr.write("usage: parallax <init|generate> (sub-commands land in Phase 9)\n");
      process.exit(2);
      break;
    }
    default: {
      process.stderr.write(
        `'${command}' is not implemented until the Phase 9 developer surface lands\n`,
      );
      process.exit(2);
    }
  }
}

main(process.argv.slice(2));
