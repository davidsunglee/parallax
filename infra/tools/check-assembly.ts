import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { runWhenMain } from "./entry.ts";
import { INFRA_ROOT, providerPackages } from "./workspace.ts";

/** Where a CDK provider package's build leaves its cloud assembly. */
export const ASSEMBLY_DIRECTORY = "cdk.out";

interface Artifact {
  readonly type?: string;
  readonly properties?: { readonly file?: string; readonly templateFile?: string };
  readonly additionalMetadataFile?: string;
}

interface Manifest {
  readonly artifacts?: Readonly<Record<string, Artifact>>;
  readonly missing?: readonly { readonly key: string }[];
}

interface AssetManifest {
  readonly files?: Readonly<Record<string, { readonly source: { readonly path?: string } }>>;
  readonly dockerImages?: Readonly<
    Record<string, { readonly source: { readonly directory?: string } }>
  >;
}

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

function referencedFiles(artifact: Artifact): string[] {
  return [
    artifact.properties?.file,
    artifact.properties?.templateFile,
    artifact.additionalMetadataFile,
  ].filter((file): file is string => file !== undefined);
}

function assetSources(assets: AssetManifest): string[] {
  return [
    ...Object.values(assets.files ?? {}).map((asset) => asset.source.path),
    ...Object.values(assets.dockerImages ?? {}).map((image) => image.source.directory),
  ].filter((source): source is string => source !== undefined);
}

function artifactProblems(assembly: string, name: string, artifact: Artifact): string[] {
  const problems: string[] = [];
  for (const file of referencedFiles(artifact)) {
    if (!existsSync(join(assembly, file))) problems.push(`${name} references missing ${file}`);
  }
  if (artifact.type === "cdk:asset-manifest" && artifact.properties?.file !== undefined) {
    const manifestPath = join(assembly, artifact.properties.file);
    if (existsSync(manifestPath)) {
      for (const source of assetSources(readJson(manifestPath) as AssetManifest)) {
        if (!existsSync(join(assembly, source))) problems.push(`${name} lacks asset ${source}`);
      }
    }
  }
  return problems;
}

/** What makes the cloud assembly at *assembly* incomplete or dependent on a lookup. */
export function assemblyProblems(assembly: string): string[] {
  const manifestPath = join(assembly, "manifest.json");
  if (!existsSync(manifestPath)) return [`${assembly} holds no manifest.json`];
  const manifest = readJson(manifestPath) as Manifest;
  const problems = (manifest.missing ?? []).map(
    (missing) => `synthesis needed context that was not committed: ${missing.key}`,
  );
  for (const [name, artifact] of Object.entries(manifest.artifacts ?? {})) {
    problems.push(...artifactProblems(assembly, name, artifact));
  }
  return problems;
}

/**
 * Check every CDK provider package's cloud assembly.
 *
 * Exit codes: 0 — every assembly is complete; 1 — one is missing a file, an
 * asset, or committed context; 2 — usage error.
 */
export function main(argv: readonly string[], root: string = INFRA_ROOT): number {
  if (argv.length > 0) {
    console.error("usage: node tools/check-assembly.ts");
    return 2;
  }
  const providers = providerPackages(root).filter((provider) =>
    existsSync(join(root, provider, "cdk.json")),
  );
  const problems = providers.flatMap((provider) =>
    assemblyProblems(join(root, provider, ASSEMBLY_DIRECTORY)).map(
      (problem) => `${provider}: ${problem}`,
    ),
  );
  for (const problem of problems) console.error(`assembly check: ${problem}`);
  if (problems.length > 0) return 1;
  console.log(`assembly check OK: ${String(providers.length)} cloud assembly(ies) complete`);
  return 0;
}

await runWhenMain(import.meta, main);
