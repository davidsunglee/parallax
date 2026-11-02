import { cpSync, readFileSync, symlinkSync } from "node:fs";
import { join } from "node:path";
import { ESLint } from "eslint";
import { check, resolveConfig } from "prettier";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { buildCommands } from "../tools/build.ts";
import { INFRA_ROOT } from "../tools/workspace.ts";
import { execute, REPOSITORY_ROOT, sandbox, tool } from "./sandbox.ts";
import { scratch } from "./scratch.ts";

const TANGLED = `export function tangled(value: number): number {
${Array.from({ length: 10 }, (_, index) => `  if (value === ${String(index)}) return ${String(index)};`).join("\n")}
  return -1;
}
`;

describe("the lint gate", () => {
  it("fails excess complexity, a floating promise, a stale directive, and a ts-ignore", async () => {
    const box = sandbox();
    box.plant("aws/src/tangled.ts", TANGLED);
    box.plant(
      "aws/src/floating.ts",
      "async function settle(): Promise<void> {\n  await Promise.resolve();\n}\nexport function start(): void {\n  settle();\n}\n",
    );
    box.plant(
      "aws/src/directive.ts",
      "// eslint-disable-next-line no-console\nexport const quiet = 1;\n",
    );
    box.plant("aws/src/ignored.ts", "// @ts-ignore\nexport const loose = 1;\n");
    const results = await new ESLint({ cwd: box.infra }).lintFiles([
      "aws/src/tangled.ts",
      "aws/src/floating.ts",
      "aws/src/directive.ts",
      "aws/src/ignored.ts",
    ]);
    const findings = results.map((result) => result.messages.map((message) => message.ruleId));
    expect(findings).toEqual([
      ["complexity"],
      ["@typescript-eslint/no-floating-promises"],
      [null],
      ["@typescript-eslint/ban-ts-comment"],
    ]);
    expect(results[2]?.messages[0]?.message).toContain("Unused eslint-disable directive");
  });
});

describe("the type gate", () => {
  it("fails unchecked indexing, an inexact optional, an unused suppression, and an implicit any", () => {
    const box = sandbox();
    box.plant(
      "aws/src/loose.ts",
      [
        "const values: number[] = [];",
        "export const first: number = values[0];",
        "interface Options { label?: string }",
        "export const options: Options = { label: undefined };",
        "// @ts-expect-error nothing here is an error",
        "export const fine = 1;",
        "export function untyped(value) { return value; }",
        "",
      ].join("\n"),
    );
    const file = join(box.infra, "tsconfig.json");
    const { config } = ts.readConfigFile(file, (path) => ts.sys.readFile(path)) as {
      config: unknown;
    };
    const parsed = ts.parseJsonConfigFileContent(config, ts.sys, box.infra, undefined, file);
    const program = ts.createProgram({ rootNames: parsed.fileNames, options: parsed.options });
    const planted = program.getSourceFile(join(box.infra, "aws/src/loose.ts"));
    const codes = ts.getPreEmitDiagnostics(program, planted).map((diagnostic) => diagnostic.code);
    expect(new Set(codes)).toEqual(new Set([2322, 2375, 2578, 7006]));
  });
});

describe("the format gate", () => {
  it("fails source the formatter would rewrite", async () => {
    const filepath = join(INFRA_ROOT, "aws/src/configuration.ts");
    const options = { ...(await resolveConfig(filepath)), filepath };
    expect(await check("export const settings = {a:1}\n", options)).toBe(false);
    expect(await check("export const settings = { a: 1 };\n", options)).toBe(true);
  });
});

describe("the dead-code gate", () => {
  it("fails an unimported source, an undeclared dependency, and an unused export", () => {
    const box = sandbox();
    box.plant("aws/src/orphan.ts", "export const orphan = 1;\n");
    box.plant(
      "aws/test/borrowed.test.ts",
      'import picomatch from "picomatch";\nimport { it } from "vitest";\nit("matches", () => picomatch("*"));\n',
    );
    const bootstrap = join(box.infra, "aws/src/role-bootstrap.ts");
    box.plant(
      "aws/src/role-bootstrap.ts",
      `${readFileSync(bootstrap, "utf8")}export const unreferenced = 1;\n`,
    );
    const outcome = execute(
      tool("knip"),
      ["--config", "infra/knip.jsonc", "--workspace", "./infra", "--workspace", "./infra/*"],
      box.root,
    );
    expect(outcome.status).toBe(1);
    expect(outcome.output).toMatch(/Unused files[\s\S]*infra\/aws\/src\/orphan\.ts/);
    expect(outcome.output).toMatch(/Unlisted dependencies[\s\S]*picomatch/);
    expect(outcome.output).toMatch(/Unused exports[\s\S]*unreferenced/);
  });
});

describe("the import-boundary gate", () => {
  it("fails each forbidden dependency", () => {
    const box = sandbox();
    box.plant("aws/src/uses-dev.ts", 'export { describe } from "vitest";\n');
    box.plant("aws/src/uses-test.ts", 'export { PACKAGE_ROOT } from "../test/committed-app.ts";\n');
    box.plant("aws/src/cycle-a.ts", 'export { b } from "./cycle-b.ts";\nexport const a = 1;\n');
    box.plant("aws/src/cycle-b.ts", 'export { a } from "./cycle-a.ts";\nexport const b = 1;\n');
    box.plant(
      "aws/src/reaches-tools.ts",
      'export { INFRA_ROOT } from "../../tools/workspace.ts";\n',
    );
    box.plant("aws/src/transitive.ts", 'export { parse } from "yaml";\n');
    box.plant(
      "aws/src/constructs/composes.ts",
      'export { ENVIRONMENT_STACK_NAME } from "../environment-stack.ts";\n',
    );
    box.plant(
      "tools/reaches-provider.ts",
      'export { CONTROL_DATABASE } from "../aws/src/role-bootstrap.ts";\n',
    );
    const outcome = execute(
      tool("depcruise"),
      ["--config", ".dependency-cruiser.json", "."],
      box.infra,
    );
    expect(outcome.status).not.toBe(0);
    for (const violation of [
      "production-not-to-development-dependency: aws/src/uses-dev.ts",
      "production-not-to-tests-or-tools: aws/src/uses-test.ts",
      "no-circular: aws/src/cycle-a.ts",
      "provider-not-to-another-package: aws/src/reaches-tools.ts",
      "not-to-undeclared: aws/src/transitive.ts",
      "constructs-not-to-composition: aws/src/constructs/composes.ts",
      "tooling-not-to-provider: tools/reaches-provider.ts",
    ]) {
      expect(outcome.output).toContain(violation);
    }
  });
});

describe("the coverage gate", () => {
  it("fails an uncovered branch and counts a source no test imports", () => {
    const root = scratch({
      "canary/src/branch.ts":
        "export function sign(value: number): string {\n  return value < 0 ? 'negative' : 'other';\n}\n",
      "canary/src/unimported.ts": "export function never(): number {\n  return 1;\n}\n",
      "canary/test/branch.test.ts":
        'import { expect, it } from "vitest";\nimport { sign } from "../src/branch.ts";\nit("signs", () => expect(sign(1)).toBe("other"));\n',
    });
    for (const file of ["vitest.config.ts", "vitest.projects.json", "package.json"]) {
      cpSync(join(INFRA_ROOT, file), join(root, file));
    }
    symlinkSync(join(INFRA_ROOT, "node_modules"), join(root, "node_modules"));
    const outcome = execute(tool("vitest"), ["run", "--project", "dbfree", "--coverage"], root);
    expect(outcome.status).toBe(1);
    expect(outcome.output).toMatch(/unimported\.ts\s*\|\s*0\s*\|/);
    expect(outcome.output).toContain(
      "Coverage for branches (50%) does not meet global threshold (95%)",
    );
  });
});

describe("the duplication gate", () => {
  it("fails a repeated block over the scope's limits", () => {
    const box = sandbox();
    const block = `export function repeated(value: number): number {\n${Array.from(
      { length: 60 },
      (_, index) =>
        `  const step${String(index)} = value * ${String(index + 2)} + Math.max(value, ${String(index)});`,
    ).join("\n")}\n  return step0 + step59;\n}\n`;
    box.plant("aws/src/first.ts", block);
    box.plant("aws/src/second.ts", block.replace("repeated", "again"));
    const outcome = execute(
      join(REPOSITORY_ROOT, "node_modules", ".bin", "jscpd"),
      ["--config", "infra/.jscpd.json"],
      box.root,
    );
    expect(outcome.status).not.toBe(0);
    expect(outcome.output).toContain("too many duplicates");
  });
});

describe("the build gate", () => {
  it("fails a synthesis that needs a context lookup no one committed", () => {
    const root = scratch({
      "cdk.json": JSON.stringify({ app: "node app.mjs" }),
      "app.mjs": [
        'import { App, Stack } from "aws-cdk-lib";',
        'import { Vpc } from "aws-cdk-lib/aws-ec2";',
        "const app = new App();",
        'const stack = new Stack(app, "Lookup", { env: { account: "111111111111", region: "us-east-2" } });',
        'Vpc.fromLookup(stack, "Vpc", { isDefault: true });',
        "app.synth();",
        "",
      ].join("\n"),
    });
    symlinkSync(join(INFRA_ROOT, "aws", "node_modules"), join(root, "node_modules"));
    const synthesize = buildCommands(root)[1];
    expect(synthesize).toBeDefined();
    const outcome = execute(synthesize?.program ?? "", synthesize?.args ?? [], root);
    expect(outcome.status).not.toBe(0);
    expect(outcome.output).toContain("Context lookups have been disabled");
  });
});
