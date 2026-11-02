import { afterEach, describe, expect, it, vi } from "vitest";
import { runWhenMain } from "../tools/entry.ts";

const startingExitCode = process.exitCode;

afterEach(() => {
  process.exitCode = startingExitCode;
});

describe("a tool's entry", () => {
  it("runs nothing when the tool is imported", async () => {
    const main = vi.fn(() => 1);
    await runWhenMain({ main: false }, main);
    expect(main).not.toHaveBeenCalled();
    expect(process.exitCode).toBe(startingExitCode);
  });

  it("takes the tool's result over its arguments as the exit code when it is the program", async () => {
    const main = vi.fn(() => Promise.resolve(3));
    await runWhenMain({ main: true }, main);
    expect(main).toHaveBeenCalledWith(process.argv.slice(2));
    expect(process.exitCode).toBe(3);
  });
});
