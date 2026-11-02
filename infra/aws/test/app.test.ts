import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ACCESS_STACK_NAME, ENVIRONMENT_STACK_NAME } from "../src/trust.ts";
import { committedContext } from "./committed-app.ts";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("the app entry point", () => {
  it("synthesizes both stacks from the context the CLI hands it", async () => {
    const outdir = mkdtempSync(join(tmpdir(), "parallax-app-"));
    vi.stubEnv("CDK_OUTDIR", outdir);
    vi.stubEnv("CDK_CONTEXT_JSON", JSON.stringify(committedContext()));

    await import("../bin/app.ts");

    const manifest = JSON.parse(readFileSync(join(outdir, "manifest.json"), "utf8")) as {
      artifacts: Record<string, unknown>;
      missing?: unknown;
    };
    expect(manifest.missing).toBeUndefined();
    for (const stack of [ACCESS_STACK_NAME, ENVIRONMENT_STACK_NAME]) {
      expect(Object.keys(manifest.artifacts)).toContain(stack);
      expect(existsSync(join(outdir, `${stack}.template.json`))).toBe(true);
    }
  });
});
