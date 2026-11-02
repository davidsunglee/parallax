import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { vi, type MockInstance } from "vitest";

/** A fresh directory holding *files*, each given by its relative path. */
export function scratch(files: Readonly<Record<string, string>> = {}): string {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "parallax-infra-test-")));
  for (const [path, content] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), content);
  }
  return root;
}

/** Silences one console stream for the test and records what was written to it. */
export function captured(stream: "log" | "error"): MockInstance<(...data: unknown[]) => void> {
  return vi.spyOn(console, stream).mockImplementation(() => undefined);
}

/** Every line written to a captured stream, joined. */
export function written(spy: MockInstance<(...data: unknown[]) => void>): string {
  return spy.mock.calls.map((call) => call.map(String).join(" ")).join("\n");
}
