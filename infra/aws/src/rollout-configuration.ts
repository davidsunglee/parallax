import {
  ConfigurationError,
  matching,
  record,
  type EnvironmentConfiguration,
} from "./configuration.ts";

/** The CDK context key holding the deployment's {@link RolloutConfiguration}. */
export const ROLLOUT_CONTEXT_KEY = "parallax:rollout";

export interface Repository {
  readonly owner: string;
  readonly name: string;
}

/** The manual budget stays the guardrail; nothing in the stacks owns a budget. */
export interface ManualBudget {
  readonly ownership: "manual";
}

/** The access stack owns a budget, alerting on actual and forecast spend against its limit. */
export interface StackBudget {
  readonly ownership: "stack";
  readonly name: string;
  readonly limitUsd: number;
  readonly recipients: readonly string[];
}

/**
 * The approved inputs the trust path is built from: who may deploy, the
 * existing identity provider and source connection it reuses, the bootstrap it
 * deploys through, and who owns the spending guardrail.
 */
export interface RolloutConfiguration {
  readonly repository: Repository;
  readonly deployEnvironment: string;
  readonly deployBranch: string;
  readonly reviewer: string;
  readonly oidcProviderArn: string;
  readonly sourceConnectionArn: string;
  readonly bootstrapQualifier: string;
  readonly budget: ManualBudget | StackBudget;
}

const REPOSITORY = /^[A-Za-z0-9-]+\/[A-Za-z0-9._-]+$/;
const NAME = /^[A-Za-z0-9_-]+$/;
const BRANCH = /^[A-Za-z0-9._-]+$/;
const QUALIFIER = /^[a-z0-9]{1,10}$/;
const BUDGET_NAME = /^[A-Za-z0-9_.-]{1,100}$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
// Budgets admits at most ten email subscribers to one notification.
const MAX_RECIPIENTS = 10;

function exactly(value: unknown, expected: string, what: string): string {
  if (value !== expected) throw new ConfigurationError(`${what} must be ${expected}`);
  return expected;
}

function recipients(value: unknown): readonly string[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_RECIPIENTS) {
    throw new ConfigurationError(
      `budget.recipients must list from 1 to ${String(MAX_RECIPIENTS)} addresses`,
    );
  }
  return value.map((address) => matching(address, EMAIL, "each budget recipient"));
}

function budget(value: unknown): ManualBudget | StackBudget {
  const fields = record(value, "budget");
  const ownership = fields["ownership"];
  if (ownership === "manual") return { ownership };
  if (ownership !== "stack")
    throw new ConfigurationError("budget.ownership must be manual or stack");
  const limitUsd = fields["limitUsd"];
  if (typeof limitUsd !== "number" || !(limitUsd > 0)) {
    throw new ConfigurationError("budget.limitUsd must be a positive number");
  }
  return {
    ownership,
    name: matching(fields["name"], BUDGET_NAME, "budget.name"),
    limitUsd,
    recipients: recipients(fields["recipients"]),
  };
}

/**
 * *value*, the deployment's committed rollout context entry, as a validated
 * configuration for *environment*: the provider and connection it names must
 * belong to the environment's own account and Region.
 */
export function rolloutConfiguration(
  value: unknown,
  environment: EnvironmentConfiguration,
): RolloutConfiguration {
  const fields = record(value, ROLLOUT_CONTEXT_KEY);
  const [owner = "", name = ""] = matching(fields["repository"], REPOSITORY, "repository").split(
    "/",
  );
  const { account, region } = environment;
  return {
    repository: { owner, name },
    deployEnvironment: matching(fields["deployEnvironment"], NAME, "deployEnvironment"),
    deployBranch: matching(fields["deployBranch"], BRANCH, "deployBranch"),
    reviewer: matching(fields["reviewer"], NAME, "reviewer"),
    oidcProviderArn: exactly(
      fields["oidcProviderArn"],
      `arn:aws:iam::${account}:oidc-provider/token.actions.githubusercontent.com`,
      "oidcProviderArn",
    ),
    sourceConnectionArn: matching(
      fields["sourceConnectionArn"],
      new RegExp(`^arn:aws:codeconnections:${region}:${account}:connection/[0-9a-f-]{36}$`),
      "sourceConnectionArn",
    ),
    bootstrapQualifier: matching(fields["bootstrapQualifier"], QUALIFIER, "bootstrapQualifier"),
    budget: budget(fields["budget"]),
  };
}
