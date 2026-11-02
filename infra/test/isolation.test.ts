import { devNull } from "node:os";
import { describe, expect, it } from "vitest";
import { isolatedEnvironment, runInherited } from "../tools/isolation.ts";
import { scratch } from "./scratch.ts";

const CREDENTIAL_SOURCES = {
  PATH: "/usr/bin",
  HOME: "/home/maintainer",
  AWS_ACCESS_KEY_ID: "AKIAEXAMPLE",
  AWS_SECRET_ACCESS_KEY: "secret",
  AWS_SESSION_TOKEN: "token",
  AWS_PROFILE: "admin",
  AWS_ROLE_ARN: "arn:aws:iam::123456789012:role/admin",
  AWS_WEB_IDENTITY_TOKEN_FILE: "/var/run/token",
  AWS_CONTAINER_CREDENTIALS_FULL_URI: "http://169.254.170.2/credentials",
  CDK_DEFAULT_ACCOUNT: "123456789012",
};

describe("the isolated environment", () => {
  it("keeps only the search path and leaves every credential source unreachable", () => {
    expect(isolatedEnvironment(CREDENTIAL_SOURCES, "/tmp/home")).toEqual({
      PATH: "/usr/bin",
      HOME: "/tmp/home",
      AWS_CONFIG_FILE: devNull,
      AWS_SHARED_CREDENTIALS_FILE: devNull,
      AWS_EC2_METADATA_DISABLED: "true",
      CDK_DISABLE_CLI_TELEMETRY: "true",
      CI: "true",
    });
  });

  it("gives an empty search path when none is inherited", () => {
    expect(isolatedEnvironment({}, "/tmp/home")["PATH"]).toBe("");
  });

  it("runs a child with exactly that environment and reports its status", () => {
    const env = isolatedEnvironment({ PATH: process.env["PATH"] }, scratch());
    const probe =
      "process.exit(process.env.AWS_PROFILE === undefined && process.env.CI === 'true' ? 7 : 1)";
    expect(
      runInherited({ program: process.execPath, args: ["-e", probe], cwd: scratch() }, env),
    ).toBe(7);
  });

  it("reports a child that could not start as a failure", () => {
    expect(runInherited({ program: "/nonexistent/program", args: [], cwd: scratch() }, {})).toBe(1);
  });
});
