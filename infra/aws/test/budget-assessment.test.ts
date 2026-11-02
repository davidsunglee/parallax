import { describe, expect, it } from "vitest";
import type { StackBudget } from "../src/rollout-configuration.ts";
import { ACCESS_STACK_NAME } from "../src/trust.ts";
import { budgetFindings, readBudgets, type BudgetFacts } from "../tools/budget-assessment.ts";
import { ABSENT_STACK, ACCOUNT, json, world } from "./rollout-world.ts";

const MANUAL = { ownership: "manual" } as const;
const STACK: StackBudget = {
  ownership: "stack",
  name: "parallax-ci-tagged",
  limitUsd: 50,
  recipients: ["b@example.com", "a@example.com"],
};

function budget(name: string, overrides: Partial<BudgetFacts> = {}): BudgetFacts {
  return {
    name,
    guardrailShape: true,
    limitUsd: 50,
    actual: ["a@example.com", "b@example.com"],
    forecast: ["b@example.com", "a@example.com"],
    ...overrides,
  };
}

const states = (found: readonly { state: string; detail: string }[]) =>
  found.map(({ state, detail }) => [state, detail]);

describe("reading budgets", () => {
  it("collects each budget's shape, limit, alert recipients, and the access stack's own budgets", () => {
    const { context } = world({
      [`cloudformation describe-stack-resources --stack-name ${ACCESS_STACK_NAME}`]: json({
        StackResources: [{ ResourceType: "AWS::Budgets::Budget", PhysicalResourceId: "owned" }],
      }),
    });
    expect(readBudgets(context.read, ACCOUNT)).toEqual({
      budgets: [
        budget("parallax-ci-monthly", {
          actual: ["owner@example.com"],
          forecast: ["owner@example.com"],
        }),
      ],
      owned: new Set(["owned"]),
    });
  });

  it("reads an absent access stack as owning nothing, and tolerates empty answers", () => {
    const { context } = world({
      [`cloudformation describe-stack-resources --stack-name ${ACCESS_STACK_NAME}`]:
        ABSENT_STACK(ACCESS_STACK_NAME),
      "budgets describe-budgets": json({
        Budgets: [{ BudgetName: "daily", BudgetType: "COST", TimeUnit: "DAILY" }],
      }),
      "budgets describe-notifications-for-budget": json({
        Notifications: [{ NotificationType: "ACTUAL" }],
      }),
      "budgets describe-subscribers-for-notification": json({}),
    });
    expect(readBudgets(context.read, ACCOUNT)).toEqual({
      budgets: [{ name: "daily", guardrailShape: false, limitUsd: NaN, actual: [], forecast: [] }],
      owned: new Set(),
    });
    const empty = world({
      [`cloudformation describe-stack-resources --stack-name ${ACCESS_STACK_NAME}`]: json({}),
      "budgets describe-budgets": json({}),
    });
    expect(readBudgets(empty.context.read, ACCOUNT)).toEqual({ budgets: [], owned: new Set() });
    const quiet = world({ "budgets describe-notifications-for-budget": json({}) });
    expect(readBudgets(quiet.context.read, ACCOUNT).budgets[0]).toMatchObject({
      actual: [],
      forecast: [],
    });
  });
});

describe("a manual guardrail", () => {
  it("is verified when exactly one alerting monthly cost budget exists, whose recipients a human confirms", () => {
    expect(
      states(
        budgetFindings(
          MANUAL,
          [budget("guard"), budget("other", { guardrailShape: false })],
          new Set(),
        ),
      ),
    ).toEqual([
      ["verified", "manual guardrail guard: $50 monthly, actual and forecast alerts"],
      [
        "confirm",
        "confirm a@example.com, b@example.com completed AWS's recipient verification for guard",
      ],
    ]);
  });

  it("is drift when missing, ambiguous, silent, or owned by the stack", () => {
    for (const [budgets, owned, detail] of [
      [[], [], "no monthly cost budget guards the account"],
      [[budget("one"), budget("two")], [], "several monthly cost budgets (one, two)"],
      [[budget("guard", { forecast: [] })], [], "guard lacks an actual or a forecast email alert"],
      [[budget("guard", { actual: [] })], [], "lacks an actual or a forecast"],
      [[budget("guard"), budget("owned")], ["owned"], `${ACCESS_STACK_NAME} owns owned although`],
    ] as const) {
      expect(budgetFindings(MANUAL, budgets, new Set(owned))).toEqual([
        { check: "budget", state: "drift", detail: expect.stringContaining(detail) as string },
      ]);
    }
  });
});

describe("the transition to a stack-owned budget", () => {
  it("creates the stack budget beside the manual guardrail, keeping spending guarded", () => {
    expect(states(budgetFindings(STACK, [budget("manual")], new Set()))).toEqual([
      [
        "pending",
        "apply access-stack to create parallax-ci-tagged; manual stay active until it is verified",
      ],
      [
        "confirm",
        "confirm a@example.com, b@example.com completed AWS's recipient verification for manual",
      ],
    ]);
    expect(states(budgetFindings(STACK, [], new Set()))).toEqual([
      [
        "pending",
        "apply access-stack to create parallax-ci-tagged; no budget guards the account meanwhile",
      ],
    ]);
  });

  it("leaves retiring the manual budget to a separately authorized human", () => {
    const found = budgetFindings(
      STACK,
      [budget("manual"), budget(STACK.name)],
      new Set([STACK.name]),
    );
    expect(states(found)[0]).toEqual([
      "pending",
      "once parallax-ci-tagged's recipients are active, a maintainer retires manual; that deletion is separately authorized",
    ]);
    expect(found[1]?.state).toBe("confirm");
  });

  it("is verified once the stack owns the only guardrail", () => {
    expect(states(budgetFindings(STACK, [budget(STACK.name)], new Set([STACK.name])))[0]).toEqual([
      "verified",
      `${ACCESS_STACK_NAME} owns parallax-ci-tagged`,
    ]);
  });

  it("never adopts a same-named budget outside the stack, and refuses a drifted stack budget", () => {
    expect(budgetFindings(STACK, [budget(STACK.name)], new Set())).toEqual([
      {
        check: "budget",
        state: "drift",
        detail: `a budget named parallax-ci-tagged exists outside ${ACCESS_STACK_NAME}; it is never imported`,
      },
    ]);
    for (const drifted of [
      budget(STACK.name, { limitUsd: 75 }),
      budget(STACK.name, { guardrailShape: false }),
      budget(STACK.name, { actual: ["a@example.com"] }),
      budget(STACK.name, { forecast: ["c@example.com", "a@example.com"] }),
    ]) {
      expect(budgetFindings(STACK, [drifted], new Set([STACK.name]))).toEqual([
        {
          check: "budget",
          state: "drift",
          detail: "parallax-ci-tagged no longer matches its configured limit and recipients",
        },
      ]);
    }
  });
});
