import { Stack, Token } from "aws-cdk-lib";
import { describe, expect, it } from "vitest";
import { defineEnvironment } from "../src/environment-stack.ts";
import type { TestEnvironment } from "../src/generated/test-environment.ts";
import {
  assertTestEnvironment,
  testEnvironment,
  TestEnvironmentParameter,
  UNRESOLVED_HOST_WITNESS,
} from "../src/test-environment.ts";
import { committedApp } from "./committed-app.ts";

const token = (): string => Token.asString({ Ref: "Somewhere" });

function deployedRecord(): TestEnvironment {
  return {
    schema: 1,
    writer_host: "parallax-ci.cluster-abc.us-east-2.rds.amazonaws.com",
    reader_host: "parallax-ci.cluster-ro-abc.us-east-2.rds.amazonaws.com",
    port: 5432,
    region: "us-east-2",
    login: "parallax_conformance_login",
    cluster_id: "parallax-ci",
    instances: [
      {
        identifier: "parallax-ci-writer",
        host: "parallax-ci-writer.abc.us-east-2.rds.amazonaws.com",
        role: "writer",
      },
      {
        identifier: "parallax-ci-reader",
        host: "parallax-ci-reader.abc.us-east-2.rds.amazonaws.com",
        role: "reader",
      },
    ],
    ca_bundle_url: "https://truststore.pki.rds.amazonaws.com/us-east-2/us-east-2-bundle.pem",
  };
}

describe("the TestEnvironment record", () => {
  it("accepts the synthesized record, whose hosts are still deploy-time tokens", () => {
    const stack = defineEnvironment(committedApp());
    const record = testEnvironment(stack.aurora, "us-east-2");
    expect(Token.isUnresolved(record.writer_host)).toBe(true);
    expect(() => {
      assertTestEnvironment(record);
    }).not.toThrow();
  });

  it("accepts a deployed record and stands its witness in for a host only", () => {
    expect(() => {
      assertTestEnvironment(deployedRecord());
    }).not.toThrow();
    expect(() => {
      assertTestEnvironment({ ...deployedRecord(), writer_host: UNRESOLVED_HOST_WITNESS });
    }).not.toThrow();
  });

  it.each([
    ["a token outside a host", { region: token() }, "/region"],
    ["another schema version", { schema: 2 }, "/schema"],
    ["a host outside RDS", { reader_host: "reader.example.com" }, "/reader_host"],
    ["no port", { port: 0 }, "/port"],
    [
      "a certificate bundle from elsewhere",
      { ca_bundle_url: "https://example.com/b.pem" },
      "/ca_bundle_url",
    ],
    ["an undeclared field", { extra: true }, "must NOT have additional properties"],
  ])("refuses %s", (_case, change, message) => {
    expect(() => {
      assertTestEnvironment({ ...deployedRecord(), ...change });
    }).toThrow(message);
  });

  it("refuses a record with no reader, or with two writers", () => {
    const [writer] = deployedRecord().instances;
    expect(() => {
      assertTestEnvironment({ ...deployedRecord(), instances: [writer] });
    }).toThrow("/instances");
    expect(() => {
      assertTestEnvironment({ ...deployedRecord(), instances: [writer, writer] });
    }).toThrow("/instances");
  });

  it("refuses a record missing a field", () => {
    const partial: Partial<TestEnvironment> = deployedRecord();
    delete partial.ca_bundle_url;
    expect(() => {
      assertTestEnvironment(partial);
    }).toThrow("must have required property 'ca_bundle_url'");
  });

  it("refuses to publish a record that does not conform", () => {
    const stack = new Stack();
    expect(
      () =>
        new TestEnvironmentParameter(stack, "Record", {
          record: { ...deployedRecord(), login: "Not A Login" },
          after: [],
        }),
    ).toThrow("/login");
  });
});
