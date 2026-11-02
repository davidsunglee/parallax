import { describe, expect, it } from "vitest";
import {
  branchesFinding,
  environmentFinding,
  forkApprovalFinding,
  repositoryFinding,
  subjectFinding,
  tokenFinding,
} from "../tools/github-assessment.ts";
import {
  ENVIRONMENT,
  failed,
  json,
  REPOSITORY,
  ROLLOUT,
  world,
  type Reply,
} from "./rollout-world.ts";

const detail = (
  check: (context: ReturnType<typeof world>["context"]) => { detail: string },
  replies: Record<string, Reply>,
) => check(world(replies).context).detail;

describe("the repository checks", () => {
  it("verify the configured repository and its default branch", () => {
    expect(repositoryFinding(world().context).state).toBe("verified");
    expect(
      detail(repositoryFinding, { [`GET ${REPOSITORY}`]: json({ full_name: "someone/fork" }) }),
    ).toBe("the repository resolves to someone/fork");
    expect(
      detail(repositoryFinding, {
        [`GET ${REPOSITORY}`]: json({ full_name: "davidsunglee/parallax", default_branch: "dev" }),
      }),
    ).toBe("the default branch is dev, not main");
  });

  it("require every external contributor's run to wait for approval", () => {
    expect(forkApprovalFinding(world().context).state).toBe("verified");
    expect(
      detail(forkApprovalFinding, {
        [`GET ${REPOSITORY}/actions/permissions/fork-pr-contributor-approval`]: json({
          approval_policy: "first_time_contributors",
        }),
      }),
    ).toContain("first_time_contributors, not all_external_contributors");
  });

  it("require GitHub's default OIDC subject, which the deploy role's trust matches", () => {
    expect(subjectFinding(world().context).state).toBe("verified");
    expect(
      subjectFinding(
        world({
          [`GET ${REPOSITORY}/actions/oidc/customization/sub`]: json({ use_default: false }),
        }).context,
      ).state,
    ).toBe("drift");
  });
});

describe("the deploy environment checks", () => {
  it("are pending while the environment or its branch rule is missing", () => {
    expect(
      environmentFinding(
        world({ [`GET ${ENVIRONMENT}`]: failed("gh: Not Found (HTTP 404)", 1) }).context,
      ).state,
    ).toBe("pending");
    for (const missing of [
      json({ branch_policies: [] }),
      json({}),
      failed("gh: Not Found (HTTP 404)", 1),
    ]) {
      expect(
        branchesFinding(
          world({ [`GET ${ENVIRONMENT}/deployment-branch-policies`]: missing }).context,
        ),
      ).toMatchObject({
        state: "pending",
        detail: "allow main alone: apply github-settings",
      });
    }
  });

  it("require the reviewer, no administrator bypass, and named-branch deployment", () => {
    expect(environmentFinding(world().context).state).toBe("verified");
    const environment = (fields: Record<string, unknown>): Record<string, Reply> => ({
      [`GET ${ENVIRONMENT}`]: json({
        can_admins_bypass: false,
        deployment_branch_policy: { protected_branches: false, custom_branch_policies: true },
        protection_rules: [
          {
            type: "required_reviewers",
            reviewers: [{ type: "User", reviewer: { login: ROLLOUT.reviewer } }],
          },
        ],
        ...fields,
      }),
    });
    for (const [fields, expected] of [
      [{ protection_rules: undefined }, "davidsunglee is not a required reviewer"],
      [{ protection_rules: [{ type: "required_reviewers" }] }, "not a required reviewer"],
      [
        { protection_rules: [{ type: "required_reviewers", reviewers: [{ type: "User" }] }] },
        "not a required reviewer",
      ],
      [{ can_admins_bypass: true }, "administrators may bypass"],
      [
        { deployment_branch_policy: { protected_branches: true, custom_branch_policies: false } },
        "named branches",
      ],
      [{ deployment_branch_policy: null }, "named branches"],
    ] as const) {
      expect(detail(environmentFinding, environment(fields))).toContain(expected);
    }
  });

  it("allow exactly one rule, for the deploy branch", () => {
    expect(branchesFinding(world().context).state).toBe("verified");
    for (const policies of [
      [
        { name: "main", type: "branch" },
        { name: "release/*", type: "branch" },
      ],
      [{ name: "main", type: "tag" }],
      [{ name: "dev", type: "branch" }],
    ]) {
      expect(
        branchesFinding(
          world({
            [`GET ${ENVIRONMENT}/deployment-branch-policies`]: json({ branch_policies: policies }),
          }).context,
        ).state,
      ).toBe("drift");
    }
    expect(
      detail(branchesFinding, {
        [`GET ${ENVIRONMENT}/deployment-branch-policies`]: json({ branch_policies: [{}] }),
      }),
    ).toBe("aws-deploy may deploy from undefined undefined");
  });

  it("see whether the settings token is placed without reading it", () => {
    expect(tokenFinding(world().context).state).toBe("verified");
    expect(tokenFinding(world({ [`GET ${ENVIRONMENT}/secrets`]: json({}) }).context)).toMatchObject(
      {
        state: "pending",
        detail: "place REPOSITORY_SETTINGS_READ_TOKEN: apply settings-token",
      },
    );
  });
});
