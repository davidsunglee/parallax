import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { compile, type JSONSchema } from "json-schema-to-typescript";
import { format, resolveConfig } from "prettier";
import { runWhenMain } from "./entry.ts";
import { INFRA_ROOT, providerPackages } from "./workspace.ts";

const SCHEMA_SUFFIX = ".schema.json";

/** Where a provider package keeps the types derived from its schemas. */
export const GENERATED_DIRECTORY = join("src", "generated");

/** One derived file: where it lives, relative to the scope root, and what it must hold. */
export interface Derivation {
  readonly path: string;
  readonly expected: string | undefined;
}

async function render(schemaPath: string, outputPath: string, schemaName: string): Promise<string> {
  const schema = JSON.parse(readFileSync(schemaPath, "utf8")) as JSONSchema;
  const source = await compile(schema, schemaName, {
    bannerComment: `// Generated from ${schemaName}${SCHEMA_SUFFIX} by tools/check-generated.ts --write; do not edit.`,
    format: false,
    additionalProperties: false,
    strictIndexSignatures: true,
  });
  const options = await resolveConfig(outputPath);
  return format(source, { ...options, filepath: outputPath });
}

/**
 * Every derived file of every provider package under *root*: one per schema at
 * a package's root, plus any file in its generated directory no schema derives,
 * which must not exist.
 */
export async function derivations(root: string = INFRA_ROOT): Promise<Derivation[]> {
  const found: Derivation[] = [];
  for (const provider of providerPackages(root)) {
    const packageDir = join(root, provider);
    const generatedDir = join(packageDir, GENERATED_DIRECTORY);
    const derived = new Set<string>();
    for (const entry of readdirSync(packageDir).sort()) {
      if (!entry.endsWith(SCHEMA_SUFFIX)) continue;
      const schemaName = entry.slice(0, -SCHEMA_SUFFIX.length);
      const output = join(generatedDir, `${schemaName}.ts`);
      derived.add(output);
      found.push({
        path: join(provider, GENERATED_DIRECTORY, `${schemaName}.ts`),
        expected: await render(join(packageDir, entry), output, schemaName),
      });
    }
    const existing = existsSync(generatedDir) ? readdirSync(generatedDir).sort() : [];
    for (const entry of existing) {
      if (!derived.has(join(generatedDir, entry))) {
        found.push({ path: join(provider, GENERATED_DIRECTORY, entry), expected: undefined });
      }
    }
  }
  return found;
}

/** What is wrong with each derived file as it stands on disk, as one line each. */
export function drift(root: string, expected: readonly Derivation[]): string[] {
  const problems: string[] = [];
  for (const { path, expected: content } of expected) {
    const absolute = join(root, path);
    if (content === undefined) {
      problems.push(`${path} is derived from no schema`);
    } else if (!existsSync(absolute)) {
      problems.push(`${path} is missing`);
    } else if (readFileSync(absolute, "utf8") !== content) {
      problems.push(`${path} is stale`);
    }
  }
  return problems;
}

function write(root: string, expected: readonly Derivation[]): void {
  for (const { path, expected: content } of expected) {
    if (content === undefined) continue;
    const absolute = join(root, path);
    mkdirSync(join(absolute, ".."), { recursive: true });
    writeFileSync(absolute, content);
  }
}

/**
 * Check, or with `--write` regenerate, every type derived from a provider
 * package's schemas.
 *
 * Exit codes: 0 — every derived file is current (or was rewritten); 1 — one is
 * stale, missing, or derived from nothing; 2 — usage error.
 */
export async function main(argv: readonly string[], root: string = INFRA_ROOT): Promise<number> {
  if (argv.length > 1 || (argv.length === 1 && argv[0] !== "--write")) {
    console.error("usage: node tools/check-generated.ts [--write]");
    return 2;
  }
  const expected = await derivations(root);
  if (argv[0] === "--write") {
    write(root, expected);
  }
  const problems = drift(root, expected);
  for (const problem of problems) {
    console.error(`generated check: ${problem}; run \`node tools/check-generated.ts --write\``);
  }
  if (problems.length > 0) return 1;
  console.log(`generated check OK: ${String(expected.length)} derived file(s) current`);
  return 0;
}

await runWhenMain(import.meta, main);
