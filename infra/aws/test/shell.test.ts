import { afterEach, describe, expect, it, vi } from "vitest";
import { CHECK, guarded, judged, report, sources } from "../tools/findings.ts";
import { CommandError, readJson, readLine, systemShell, type Shell } from "../tools/shell.ts";

afterEach(() => {
  vi.restoreAllMocks();
});

const node = (script: string) => ({ program: process.execPath, args: ["-e", script] });

describe("the system shell", () => {
  it("captures a command's status and output", () => {
    expect(
      systemShell.capture(
        node("process.stdout.write('out'); process.stderr.write('err'); process.exit(3)"),
      ),
    ).toEqual({
      status: 3,
      stdout: "out",
      stderr: "err",
    });
  });

  it("attaches a command to the terminal and returns its status", () => {
    expect(systemShell.attach({ ...node("process.exit(4)"), cwd: process.cwd() })).toBe(4);
  });

  it("reports a command that never ran as failed", () => {
    expect(systemShell.capture({ program: "/nonexistent/program", args: [] }).status).toBe(1);
    expect(systemShell.attach({ program: "/nonexistent/program", args: [] })).toBe(1);
  });
});

describe("reading a command's output", () => {
  const answering = (status: number, stdout: string, stderr = ""): Shell => ({
    capture: () => ({ status, stdout, stderr }),
    attach: () => 0,
  });
  const invocation = { program: "aws", args: ["sts", "get-caller-identity", "--output", "json"] };

  it("parses JSON, or reports a failure by its command and first line", () => {
    expect(readJson(answering(0, '{"a":1}'), invocation)).toEqual({ a: 1 });
    expect(() => readJson(answering(254, "", "denied\nmore"), invocation)).toThrow(
      new CommandError("aws sts get-caller-identity failed: denied"),
    );
    expect(() => readJson(answering(0, "not json"), invocation)).toThrow(
      "aws sts get-caller-identity printed no JSON",
    );
  });

  it("reads an expected absence as nothing", () => {
    expect(
      readJson(answering(254, "", "Stack does not exist"), invocation, /does not exist/),
    ).toBeUndefined();
    expect(() =>
      readJson(answering(254, "", "AccessDenied"), invocation, /does not exist/),
    ).toThrow(CommandError);
  });

  it("reads one line", () => {
    expect(readLine(answering(0, "abc\n"), invocation)).toBe("abc");
    expect(() => readLine(answering(1, ""), invocation)).toThrow(
      "aws sts get-caller-identity failed",
    );
  });
});

describe("the sources", () => {
  it("read AWS in the configured Region as JSON, and GitHub only by GET", () => {
    const seen: { program: string; args: readonly string[] }[] = [];
    const shell: Shell = {
      capture: (invocation) => {
        seen.push(invocation);
        return invocation.args.includes("missing")
          ? { status: 1, stdout: "", stderr: "gh: Not Found (HTTP 404)" }
          : { status: 0, stdout: "{}", stderr: "" };
      },
      attach: () => 0,
    };
    const read = sources(shell, "us-east-2");
    read.aws(["sts", "get-caller-identity"]);
    read.github("repos/a/b");
    expect(read.github("missing", true)).toBeUndefined();
    expect(() => read.github("missing")).toThrow(CommandError);
    expect(seen.slice(0, 2)).toEqual([
      {
        program: "aws",
        args: ["sts", "get-caller-identity", "--region", "us-east-2", "--output", "json"],
      },
      { program: "gh", args: ["api", "--method", "GET", "repos/a/b"] },
    ]);
  });
});

describe("findings", () => {
  it("judge the first unmet expectation as drift", () => {
    expect(
      judged(
        "x",
        [
          [true, "a"],
          [false, "b"],
          [false, "c"],
        ],
        "fine",
      ),
    ).toEqual({ check: "x", state: "drift", detail: "b" });
    expect(judged("x", [[true, "a"]], "fine")).toEqual({
      check: "x",
      state: "verified",
      detail: "fine",
    });
  });

  it("turn a failed read into an unavailable finding, and let anything else propagate", () => {
    expect(
      guarded(CHECK.budget, () => ({ check: "budget", state: "verified", detail: "" })),
    ).toHaveLength(1);
    expect(guarded(CHECK.budget, () => [])).toEqual([]);
    expect(
      guarded(CHECK.budget, () => {
        throw new CommandError("aws budgets failed: AccessDenied");
      }),
    ).toEqual([
      { check: "budget", state: "unavailable", detail: "aws budgets failed: AccessDenied" },
    ]);
    expect(() =>
      guarded(CHECK.budget, () => {
        throw new TypeError("a defect");
      }),
    ).toThrow(TypeError);
  });

  it("report every state apart, and are ready only with nothing pending, drifted, or unchecked", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const all = [
      { check: "a", state: "drift", detail: "d" },
      { check: "b", state: "verified", detail: "v" },
      { check: "c", state: "confirm", detail: "c" },
      { check: "d", state: "pending", detail: "p" },
      { check: "e", state: "unavailable", detail: "u" },
    ] as const;
    expect(report(all, ["a live proof"])).toBe(false);
    expect(log.mock.calls.map(([line]) => String(line)).join("\n")).toBe(
      [
        "Verified:",
        "  b: v",
        "For a human to confirm:",
        "  c: c",
        "Pending:",
        "  d: p",
        "Drift:",
        "  a: d",
        "Could not check:",
        "  e: u",
        "Proven only by the protected deployment and the cloud run:",
        "  a live proof",
      ].join("\n"),
    );
    expect(report(all.slice(1, 3), [])).toBe(true);
  });
});
