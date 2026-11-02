/**
 * Run a tool's *main* over the command-line arguments and take its result as
 * the process's exit code, but only when *meta* belongs to the module Node was
 * started with, so importing a tool runs nothing.
 */
export async function runWhenMain(
  meta: Pick<ImportMeta, "main">,
  main: (argv: readonly string[]) => number | Promise<number>,
): Promise<void> {
  if (meta.main) process.exitCode = await main(process.argv.slice(2));
}
