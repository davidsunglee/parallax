import { describe, expect, it } from "vitest";
import { main, pinProblems } from "../tools/audit-dependencies.ts";
import { captured, scratch, written } from "./scratch.ts";

describe("the dependency pins", () => {
  it("passes the committed catalog and manifests", () => {
    const log = captured("log");
    expect(main([])).toBe(0);
    expect(written(log)).toContain("pinned through the catalog");
  });

  it("fails a package that specifies its own version", () => {
    expect(
      pinProblems({ vitest: "5.0.5" }, [
        { path: "aws/package.json", manifest: { devDependencies: { vitest: "^5.0.5" } } },
      ]),
    ).toEqual(['aws/package.json devDependencies gives vitest "^5.0.5" rather than "catalog:"']);
  });

  it("fails a package naming a dependency the catalog does not pin", () => {
    expect(
      pinProblems({}, [{ path: "package.json", manifest: { dependencies: { ajv: "catalog:" } } }]),
    ).toEqual(["package.json dependencies names ajv, which the catalog does not pin"]);
  });

  it("fails a catalog entry that is a range, or one nothing uses", () => {
    expect(
      pinProblems({ ajv: "^8.20.0", constructs: "10.8.1", stale: "1.0.0" }, [
        {
          path: "aws/package.json",
          manifest: { dependencies: { ajv: "catalog:", constructs: "catalog:" } },
        },
      ]),
    ).toEqual([
      'the catalog pins ajv to "^8.20.0" rather than one exact version',
      "the catalog pins stale, which no infrastructure package uses",
    ]);
  });

  it("reads the workspace catalog and every package manifest", () => {
    const root = scratch({
      "pnpm-workspace.yaml": "packages:\n  - infra\n",
      "infra/package.json": JSON.stringify({ devDependencies: { yaml: "2" } }),
      "infra/aws/package.json": "{}",
    });
    const error = captured("error");
    expect(main([], `${root}/infra`)).toBe(1);
    expect(written(error)).toContain('package.json devDependencies gives yaml "2"');
  });

  it("refuses arguments", () => {
    const error = captured("error");
    expect(main(["--fix"])).toBe(2);
    expect(written(error)).toContain("usage:");
  });
});
