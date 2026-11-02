import { describe, expect, it } from "vitest";
import {
  CONFIGURATION_CONTEXT_KEY,
  ConfigurationError,
  environmentConfiguration,
} from "../src/configuration.ts";
import { committedContext } from "./committed-app.ts";

const committed = committedContext()[CONFIGURATION_CONTEXT_KEY] as Record<string, unknown>;
const aurora = committed["aurora"] as Record<string, unknown>;

function withField(field: string, value: unknown): Record<string, unknown> {
  return { ...committed, [field]: value };
}

function withCapacity(field: string, value: unknown): Record<string, unknown> {
  return { ...committed, aurora: { ...aurora, [field]: value } };
}

describe("the environment configuration", () => {
  it("reads the committed configuration", () => {
    expect(environmentConfiguration(committed)).toEqual({
      account: "407034905514",
      region: "us-east-2",
      availabilityZones: ["us-east-2a", "us-east-2b"],
      natInstanceType: "t4g.nano",
      aurora: { minCapacity: 0, maxCapacity: 2, autoPauseSeconds: 300 },
    });
  });

  it.each([
    ["no configuration", undefined, "parallax:environment must be an object"],
    ["a list", [], "parallax:environment must be an object"],
    ["a short account", withField("account", "40703490551"), "account must match"],
    ["a numeric account", withField("account", 407034905514), "account must match"],
    ["a malformed Region", withField("region", "us-east"), "region must match"],
    ["one zone", withField("availabilityZones", ["us-east-2a"]), "at least two zones"],
    ["no zone list", withField("availabilityZones", "us-east-2a"), "at least two zones"],
    [
      "a zone in another Region",
      withField("availabilityZones", ["us-east-2a", "us-east-1b"]),
      "each availability zone must match",
    ],
    [
      "a repeated zone",
      withField("availabilityZones", ["us-east-2a", "us-east-2a"]),
      "must not repeat a zone",
    ],
    ["an x86 NAT type", withField("natInstanceType", "t3.nano"), "natInstanceType must match"],
    ["no capacity", withField("aurora", undefined), "aurora must be an object"],
    ["a floor above zero", withCapacity("minCapacity", 0.5), "aurora.minCapacity must be"],
    ["a ceiling below one unit", withCapacity("maxCapacity", 0.5), "aurora.maxCapacity must be"],
    ["a ceiling above the limit", withCapacity("maxCapacity", 256.5), "aurora.maxCapacity must be"],
    ["a ceiling off the half-unit step", withCapacity("maxCapacity", 2.25), "a multiple of 0.5"],
    ["a textual ceiling", withCapacity("maxCapacity", "2"), "aurora.maxCapacity must be"],
    ["too short a pause delay", withCapacity("autoPauseSeconds", 299), "aurora.autoPauseSeconds"],
    ["too long a pause delay", withCapacity("autoPauseSeconds", 86_401), "aurora.autoPauseSeconds"],
    ["a fractional pause delay", withCapacity("autoPauseSeconds", 300.5), "whole number"],
    ["a textual pause delay", withCapacity("autoPauseSeconds", "300"), "whole number"],
  ])("refuses %s", (_case, value, message) => {
    expect(() => environmentConfiguration(value)).toThrow(ConfigurationError);
    expect(() => environmentConfiguration(value)).toThrow(message);
  });
});
