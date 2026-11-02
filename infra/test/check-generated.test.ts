import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { GENERATED_DIRECTORY, main } from "../tools/check-generated.ts";
import { captured, scratch, written } from "./scratch.ts";

const SCHEMA = JSON.stringify({
  title: "Widget",
  type: "object",
  additionalProperties: false,
  required: ["name"],
  properties: { name: { type: "string" } },
});

function provider(): { root: string; output: string } {
  const root = scratch({ "aws/package.json": "{}", "aws/widget.schema.json": SCHEMA });
  return { root, output: join(root, "aws", GENERATED_DIRECTORY, "widget.ts") };
}

describe("generated-type freshness", () => {
  it("passes over the committed derived types", async () => {
    const log = captured("log");
    expect(await main([])).toBe(0);
    expect(written(log)).toContain("generated check OK");
  });

  it("writes a type for each schema and then finds it current", async () => {
    const { root, output } = provider();
    captured("log");
    expect(await main(["--write"], root)).toBe(0);
    expect(readFileSync(output, "utf8")).toContain("export interface Widget");
    expect(await main([], root)).toBe(0);
  });

  it("fails on a derived type that no longer matches its schema", async () => {
    const { root, output } = provider();
    captured("log");
    await main(["--write"], root);
    writeFileSync(output, `${readFileSync(output, "utf8")}export type Stale = never;\n`);
    const error = captured("error");
    expect(await main([], root)).toBe(1);
    expect(written(error)).toContain("aws/src/generated/widget.ts is stale");
  });

  it("fails on a schema whose type was never generated", async () => {
    const { root, output } = provider();
    const error = captured("error");
    expect(await main([], root)).toBe(1);
    expect(existsSync(output)).toBe(false);
    expect(written(error)).toContain("aws/src/generated/widget.ts is missing");
  });

  it("fails on a generated file no schema derives, even after rewriting", async () => {
    const { root } = provider();
    captured("log");
    await main(["--write"], root);
    rmSync(join(root, "aws", "widget.schema.json"));
    writeFileSync(join(root, "aws", GENERATED_DIRECTORY, "orphan.ts"), "export {};\n");
    const error = captured("error");
    expect(await main(["--write"], root)).toBe(1);
    expect(written(error)).toContain("aws/src/generated/orphan.ts is derived from no schema");
    expect(written(error)).toContain("aws/src/generated/widget.ts is derived from no schema");
  });

  it.each([[["--check"]], [["--write", "--write"]]])("refuses the arguments %j", async (argv) => {
    const error = captured("error");
    expect(await main(argv)).toBe(2);
    expect(written(error)).toContain("usage:");
  });
});
