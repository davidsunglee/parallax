import { isDeepStrictEqual } from "node:util";
import type { RolloutConfiguration } from "../src/rollout-configuration.ts";
import { CHECK, judged, type Finding, type Sources } from "./findings.ts";

/**
 * The `aws-deploy` secret holding a fine-grained token limited to this
 * repository with read access to Administration and Actions alone: the
 * approval policy needs the first, the environment and OIDC settings the second.
 */
export const SETTINGS_TOKEN_SECRET = "REPOSITORY_SETTINGS_READ_TOKEN";

/** The fork pull request approval policy the cloud check's trust rests on. */
export const FORK_APPROVAL_POLICY = "all_external_contributors";

/** The deployment branch rule the protected environment must have: custom rules, not protected branches. */
export const DEPLOYMENT_BRANCH_POLICY = {
  protected_branches: false,
  custom_branch_policies: true,
} as const;

export interface GitHubContext {
  readonly read: Sources;
  readonly rollout: RolloutConfiguration;
}

const repositoryPath = (rollout: RolloutConfiguration): string =>
  `repos/${rollout.repository.owner}/${rollout.repository.name}`;

/** The REST path of the deploy environment. */
export const environmentPath = (rollout: RolloutConfiguration): string =>
  `${repositoryPath(rollout)}/environments/${rollout.deployEnvironment}`;

export function repositoryFinding(context: GitHubContext): Finding {
  const { rollout } = context;
  const expected = `${rollout.repository.owner}/${rollout.repository.name}`;
  const repository = context.read.github(repositoryPath(rollout)) as {
    full_name?: string;
    default_branch?: string;
  };
  return judged(
    CHECK.repository,
    [
      [
        repository.full_name === expected,
        `the repository resolves to ${String(repository.full_name)}`,
      ],
      [
        repository.default_branch === rollout.deployBranch,
        `the default branch is ${String(repository.default_branch)}, not ${rollout.deployBranch}`,
      ],
    ],
    `${expected}, default branch ${rollout.deployBranch}`,
  );
}

export function forkApprovalFinding(context: GitHubContext): Finding {
  const { approval_policy: policy } = context.read.github(
    `${repositoryPath(context.rollout)}/actions/permissions/fork-pr-contributor-approval`,
  ) as { approval_policy?: string };
  return judged(
    CHECK.forkApproval,
    [
      [
        policy === FORK_APPROVAL_POLICY,
        `fork pull request runs need approval for ${String(policy)}, not ${FORK_APPROVAL_POLICY}`,
      ],
    ],
    `every external contributor's run needs a maintainer's approval`,
  );
}

interface EnvironmentJson {
  readonly can_admins_bypass?: boolean;
  readonly deployment_branch_policy?: unknown;
  readonly protection_rules?: readonly {
    type?: string;
    reviewers?: readonly { type?: string; reviewer?: { login?: string; slug?: string } }[];
  }[];
}

export function environmentFinding(context: GitHubContext): Finding {
  const { rollout } = context;
  const environment = context.read.github(environmentPath(rollout), true) as
    EnvironmentJson | undefined;
  if (environment === undefined) {
    return {
      check: CHECK.environment,
      state: "pending",
      detail: `create ${rollout.deployEnvironment}: apply github-settings`,
    };
  }
  // Any one listed reviewer's approval releases a deployment, so the reviewer must be alone.
  const reviewers = (environment.protection_rules ?? [])
    .filter((rule) => rule.type === "required_reviewers")
    .flatMap((rule) => rule.reviewers ?? [])
    .map(
      (entry) => `${String(entry.type)} ${String(entry.reviewer?.login ?? entry.reviewer?.slug)}`,
    );
  return judged(
    CHECK.environment,
    [
      [
        isDeepStrictEqual(reviewers, [`User ${rollout.reviewer}`]),
        `the required reviewers are [${reviewers.join(", ")}], not ${rollout.reviewer} alone`,
      ],
      [
        environment.can_admins_bypass === false,
        "administrators may bypass the environment's protections",
      ],
      [
        isDeepStrictEqual(environment.deployment_branch_policy, DEPLOYMENT_BRANCH_POLICY),
        "the environment does not restrict deployments to named branches",
      ],
    ],
    `${rollout.deployEnvironment} requires ${rollout.reviewer}'s approval alone, without administrator bypass`,
  );
}

export function branchesFinding(context: GitHubContext): Finding {
  const { rollout } = context;
  // A missing environment, or one without custom branch rules, has no such list.
  const { branch_policies: policies = [] } = (context.read.github(
    `${environmentPath(rollout)}/deployment-branch-policies`,
    true,
  ) ?? {}) as { branch_policies?: readonly { name?: string; type?: string }[] };
  if (policies.length === 0) {
    return {
      check: CHECK.branches,
      state: "pending",
      detail: `allow ${rollout.deployBranch} alone: apply github-settings`,
    };
  }
  return judged(
    CHECK.branches,
    [
      [
        policies.length === 1 &&
          policies[0]?.name === rollout.deployBranch &&
          policies[0].type === "branch",
        `${rollout.deployEnvironment} may deploy from ${policies.map((policy) => `${String(policy.type)} ${String(policy.name)}`).join(", ")}`,
      ],
    ],
    `${rollout.deployEnvironment} deploys only from branch ${rollout.deployBranch}`,
  );
}

/** Whether the OIDC subject keeps GitHub's default form, which the deploy role's trust matches. */
export function subjectFinding(context: GitHubContext): Finding {
  const { use_default: useDefault } = context.read.github(
    `${repositoryPath(context.rollout)}/actions/oidc/customization/sub`,
  ) as { use_default?: boolean };
  return judged(
    CHECK.subject,
    [
      [
        useDefault === true,
        "the repository customizes its OIDC subject, which the deploy role does not match",
      ],
    ],
    "OIDC subjects keep GitHub's default form",
  );
}

/** Whether the settings token is placed. Its value is never read; only the protected deploy uses it. */
export function tokenFinding(context: GitHubContext): Finding {
  const { secrets = [] } = context.read.github(`${environmentPath(context.rollout)}/secrets`) as {
    secrets?: readonly { name?: string }[];
  };
  return secrets.some((secret) => secret.name === SETTINGS_TOKEN_SECRET)
    ? {
        check: CHECK.token,
        state: "verified",
        detail: `${SETTINGS_TOKEN_SECRET} is placed in ${context.rollout.deployEnvironment}`,
      }
    : {
        check: CHECK.token,
        state: "pending",
        detail: `place ${SETTINGS_TOKEN_SECRET}: apply settings-token`,
      };
}
