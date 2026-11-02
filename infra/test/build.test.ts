import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { BUILD_OUTPUTS, buildCommands, main } from "../tools/build.ts";
import type { Command } from "../tools/isolation.ts";
import { captured, scratch, written } from "./scratch.ts";

interface Recorded {
  readonly command: Command;
  readonly env: Readonly<Record<string, string>>;
}

function recorder(statuses: readonly number[] = []): {
  calls: Recorded[];
  run: (command: Command, env: Readonly<Record<string, string>>) => number;
} {
  const calls: Recorded[] = [];
  return {
    calls,
    run: (command, env) => {
      calls.push({ command, env });
      return statuses[calls.length - 1] ?? 0;
    },
  };
}

describe("the infrastructure build", () => {
  it("compiles every package and synthesizes a CDK app strictly with lookups disabled", () => {
    const [compile, synthesize] = buildCommands(scratch({ "cdk.json": "{}" }));
    expect(compile?.args.slice(1)).toEqual(["-p", "tsconfig.build.json"]);
    expect(compile?.args[0]).toMatch(/typescript[/\\]bin[/\\]tsc$/);
    expect(synthesize?.args[0]).toMatch(/aws-cdk[/\\]bin[/\\]cdk$/);
    expect(synthesize?.args).toEqual(expect.arrayContaining(["synth", "--strict", "--no-lookups"]));
    expect(buildCommands(scratch())).toHaveLength(1);
  });

  it("removes earlier output, then runs each package's steps in an isolated environment", () => {
    const root = scratch({
      "aws/package.json": "{}",
      "aws/cdk.json": "{}",
      "aws/dist/stale.js": "",
      "aws/cdk.out/manifest.json": "{}",
      "gcp/package.json": "{}",
    });
    const { calls, run } = recorder();
    expect(main([], root, run)).toBe(0);
    for (const output of BUILD_OUTPUTS) expect(existsSync(join(root, "aws", output))).toBe(false);
    expect(calls.map(({ command }) => command.cwd)).toEqual([
      join(root, "aws"),
      join(root, "aws"),
      join(root, "gcp"),
    ]);
    for (const { env } of calls) {
      expect(
        Object.keys(env)
          .filter((key) => key.startsWith("AWS_"))
          .sort(),
      ).toEqual(["AWS_CONFIG_FILE", "AWS_EC2_METADATA_DISABLED", "AWS_SHARED_CREDENTIALS_FILE"]);
    }
  });

  it("stops at the first failing step with its status", () => {
    const root = scratch({
      "aws/package.json": "{}",
      "aws/cdk.json": "{}",
      "gcp/package.json": "{}",
    });
    const { calls, run } = recorder([0, 3]);
    expect(main([], root, run)).toBe(3);
    expect(calls).toHaveLength(2);
  });

  it("refuses arguments", () => {
    const error = captured("error");
    expect(main(["aws"])).toBe(2);
    expect(written(error)).toContain("usage:");
  });
});
