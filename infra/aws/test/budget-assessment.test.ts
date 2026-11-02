import { describe, expect, it } from "vitest";
import type { StackBudget } from "../src/rollout-configuration.ts";
import { STACK_BUDGET_FILTERS } from "../src/access-stack.ts";
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
    filters: {},
    actual: ["a@example.com", "b@example.com"],
    forecast: ["b@example.com", "a@example.com"],
    ...overrides,
  };
}

/** The stack-owned budget as the access stack creates it, with *overrides*. */
const tagged = (overrides: Partial<BudgetFacts> = {}): BudgetFacts =>
  budget(STACK.name, { filters: STACK_BUDGET_FILTERS, ...overrides });

const states = (found: readonly { state: string; detail: string }[]) =>
  found.map(({ state, detail }) => [state, detail]);

describe("reading budgets", () => {
  it("collects each budget's shape, limit, scope, alert recipients, and the access stack's own budgets", () => {
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
      budgets: [
        {
          name: "daily",
          guardrailShape: false,
          limitUsd: NaN,
          filters: {},
          actual: [],
          forecast: [],
        },
      ],
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

  it("keeps a budget's filters, values sorted, and any filter expression", () => {
    const { context } = world({
      "budgets describe-budgets": json({
        Budgets: [
          {
            BudgetName: "scoped",
            CostFilters: { Service: ["Amazon S3", "AWS Lambda"] },
            FilterExpression: { Dimensions: { Key: "SERVICE", Values: ["Amazon S3"] } },
          },
        ],
      }),
    });
    expect(readBudgets(context.read, ACCOUNT).budgets[0]?.filters).toEqual({
      Service: ["AWS Lambda", "Amazon S3"],
      FilterExpression: { Dimensions: { Key: "SERVICE", Values: ["Amazon S3"] } },
    });
  });

  it("counts only alerts that fire by the time spending reaches the limit", () => {
    const recipients = (notifications: readonly Record<string, unknown>[]) =>
      readBudgets(
        world({
          "budgets describe-notifications-for-budget": json({ Notifications: notifications }),
        }).context.read,
        ACCOUNT,
      ).budgets[0]?.actual;
    const alert = (fields: Record<string, unknown>) => ({
      NotificationType: "ACTUAL",
      ComparisonOperator: "GREATER_THAN",
      ...fields,
    });
    expect(recipients([alert({ Threshold: 100 })])).toEqual(["owner@example.com"]);
    expect(recipients([alert({ Threshold: 50, ThresholdType: "ABSOLUTE_VALUE" })])).toEqual([
      "owner@example.com",
    ]);
    for (const ineffective of [
      alert({ Threshold: 150 }),
      alert({ Threshold: 60, ThresholdType: "ABSOLUTE_VALUE" }),
      alert({ Threshold: 80, ComparisonOperator: "LESS_THAN" }),
      alert({}),
    ]) {
      expect(recipients([ineffective]), JSON.stringify(ineffective)).toEqual([]);
    }
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
      [
        [budget("guard", { filters: { Service: ["Amazon S3"] } })],
        [],
        "guard watches only part of the account's spending",
      ],
      [[budget("guard", { filters: { FilterExpression: {} } })], [], "watches only part"],
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
        "apply access-stack to create parallax-ci-tagged; manual stays active until it is verified",
      ],
      [
        "confirm",
        "confirm a@example.com, b@example.com completed AWS's recipient verification for manual",
      ],
    ]);
  });

  it("is drift while no manual guardrail is in force to keep spending guarded meanwhile", () => {
    for (const [budgets, detail] of [
      [[], "no monthly cost budget guards the account"],
      [[budget("manual", { forecast: [] })], "manual lacks an actual or a forecast email alert"],
      [[budget("manual", { filters: { Service: ["Amazon S3"] } })], "watches only part"],
      [[budget("one"), budget("two")], "several monthly cost budgets (one, two)"],
    ] as const) {
      expect(budgetFindings(STACK, budgets, new Set())).toEqual([
        { check: "budget", state: "drift", detail: expect.stringContaining(detail) as string },
      ]);
    }
  });

  it("leaves retiring the manual budget to a separately authorized human", () => {
    const found = budgetFindings(STACK, [budget("manual"), tagged()], new Set([STACK.name]));
    expect(states(found)[0]).toEqual([
      "pending",
      "once parallax-ci-tagged's recipients are active, a maintainer retires manual; that deletion is separately authorized",
    ]);
    expect(found[1]?.state).toBe("confirm");
  });

  it("is verified once the stack owns the only guardrail", () => {
    expect(states(budgetFindings(STACK, [tagged()], new Set([STACK.name])))[0]).toEqual([
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
      tagged({ limitUsd: 75 }),
      tagged({ guardrailShape: false }),
      tagged({ actual: ["a@example.com"] }),
      tagged({ forecast: ["c@example.com", "a@example.com"] }),
      tagged({ filters: {} }),
      tagged({ filters: { ...STACK_BUDGET_FILTERS, Service: ["Amazon S3"] } }),
    ]) {
      expect(budgetFindings(STACK, [drifted], new Set([STACK.name]))).toEqual([
        {
          check: "budget",
          state: "drift",
          detail:
            "parallax-ci-tagged no longer matches its configured limit, scope, and recipients",
        },
      ]);
    }
  });
});
