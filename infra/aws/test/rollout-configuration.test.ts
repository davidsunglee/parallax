import { describe, expect, it } from "vitest";
import { ConfigurationError } from "../src/configuration.ts";
import { ROLLOUT_CONTEXT_KEY, rolloutConfiguration } from "../src/rollout-configuration.ts";
import { committedContext } from "./committed-app.ts";
import { CONFIGURATION } from "./rollout-world.ts";

const committed = committedContext()[ROLLOUT_CONTEXT_KEY] as Record<string, unknown>;
const STACK_BUDGET = {
  ownership: "stack",
  name: "parallax-ci-tagged",
  limitUsd: 50,
  recipients: ["owner@example.com"],
};

const read = (value: unknown) => rolloutConfiguration(value, CONFIGURATION);
const withField = (field: string, value: unknown) => ({ ...committed, [field]: value });

describe("the rollout configuration", () => {
  it("reads the committed inputs: the existing provider and connection, and a manual guardrail", () => {
    expect(read(committed)).toEqual({
      repository: { owner: "davidsunglee", name: "parallax" },
      deployEnvironment: "aws-deploy",
      deployBranch: "main",
      reviewer: "davidsunglee",
      oidcProviderArn:
        "arn:aws:iam::407034905514:oidc-provider/token.actions.githubusercontent.com",
      sourceConnectionArn:
        "arn:aws:codeconnections:us-east-2:407034905514:connection/55ccf245-e397-4081-89eb-ed0c32586b61",
      bootstrapQualifier: "parallaxci",
      budget: { ownership: "manual" },
    });
  });

  it("reads a stack-owned budget", () => {
    expect(read(withField("budget", STACK_BUDGET)).budget).toEqual(STACK_BUDGET);
  });

  it.each([
    ["no configuration", undefined, "parallax:rollout must be an object"],
    ["an unqualified repository", withField("repository", "parallax"), "repository must match"],
    [
      "a malformed environment",
      withField("deployEnvironment", "aws deploy"),
      "deployEnvironment must match",
    ],
    ["a malformed branch", withField("deployBranch", "main branch"), "deployBranch must match"],
    ["a malformed reviewer", withField("reviewer", "@davidsunglee"), "reviewer must match"],
    [
      "a provider in another account",
      withField(
        "oidcProviderArn",
        "arn:aws:iam::456421176518:oidc-provider/token.actions.githubusercontent.com",
      ),
      "oidcProviderArn must be arn:aws:iam::407034905514:",
    ],
    [
      "the superseded Builder account's connection",
      withField(
        "sourceConnectionArn",
        "arn:aws:codeconnections:us-east-2:456421176518:connection/b6d9e867-d8b3-4869-ad8a-b1542e47fb80",
      ),
      "sourceConnectionArn must match",
    ],
    [
      "a long qualifier",
      withField("bootstrapQualifier", "parallax-ci-x"),
      "bootstrapQualifier must match",
    ],
    ["no budget", withField("budget", undefined), "budget must be an object"],
    ["an unknown ownership", withField("budget", { ownership: "imported" }), "manual or stack"],
    ["a zero limit", withField("budget", { ...STACK_BUDGET, limitUsd: 0 }), "positive number"],
    [
      "a textual limit",
      withField("budget", { ...STACK_BUDGET, limitUsd: "50" }),
      "positive number",
    ],
    [
      "a malformed name",
      withField("budget", { ...STACK_BUDGET, name: "a b" }),
      "budget.name must match",
    ],
    [
      "no recipients",
      withField("budget", { ...STACK_BUDGET, recipients: [] }),
      "from 1 to 10 addresses",
    ],
    [
      "recipients that are not a list",
      withField("budget", { ...STACK_BUDGET, recipients: "a@b.c" }),
      "from 1 to 10",
    ],
    [
      "too many recipients",
      withField("budget", {
        ...STACK_BUDGET,
        recipients: Array.from({ length: 11 }, (_, n) => `r${String(n)}@example.com`),
      }),
      "from 1 to 10",
    ],
    [
      "a malformed recipient",
      withField("budget", { ...STACK_BUDGET, recipients: ["owner"] }),
      "each budget recipient",
    ],
  ])("refuses %s", (_name, value, message) => {
    expect(() => read(value)).toThrow(ConfigurationError);
    expect(() => read(value)).toThrow(message);
  });
});
