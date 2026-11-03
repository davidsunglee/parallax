import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import { CONTROL_DATABASE } from "../src/role-bootstrap.ts";
import { TEST_ENVIRONMENT_PARAMETER } from "../src/test-environment.ts";
import { RUNNER_PROJECT_NAME } from "../src/trust.ts";
import {
  ENVIRONMENT_VERSION_INPUT,
  VERDICT_DEADLINE,
  VERDICT_JOB,
} from "../tools/cloud-verification.ts";
import { CLOUD_CELL } from "../tools/required-check.ts";
import { PACKAGE_ROOT } from "./committed-app.ts";

const REPOSITORY_ROOT = join(PACKAGE_ROOT, "../..");
const read = (relative: string): string => readFileSync(join(REPOSITORY_ROOT, relative), "utf8");

interface Workflow {
  readonly on: { workflow_dispatch: { inputs: Record<string, { required: boolean }> } };
  readonly concurrency: { group: string; "cancel-in-progress": boolean };
  readonly jobs: Record<string, Record<string, unknown>>;
}

const ci = parse(read(".github/workflows/ci.yml")) as Workflow;
const cloudJob = ci.jobs["python-check-cloud"] ?? {};

describe("the cloud path this environment serves", () => {
  it("accepts the record version a deployment dispatches it with, and hands it to the suite", () => {
    expect(ci.on.workflow_dispatch.inputs[ENVIRONMENT_VERSION_INPUT]?.required).toBe(false);
    expect((cloudJob["env"] as Record<string, unknown>)["PARALLAX_AWS_ENVIRONMENT_VERSION"]).toBe(
      `\${{ inputs.${ENVIRONMENT_VERSION_INPUT} }}`,
    );
    expect(Object.keys(ci.jobs)).toContain(VERDICT_JOB);
  });

  it("names its AWS cell as the live evidence the required verdict waits for", () => {
    expect(cloudJob["name"]).toBe("python-check-cloud (${{ matrix.provider }})");
    expect(CLOUD_CELL).toBe("python-check-cloud (aws)");
  });

  it("runs its AWS cell on this environment's runner project", () => {
    const matrix = (cloudJob["strategy"] as { matrix: { include: Record<string, string>[] } })
      .matrix;
    expect(matrix.include).toEqual([
      {
        provider: "aws",
        runner: `codebuild-${RUNNER_PROJECT_NAME}-\${{ github.run_id }}-\${{ github.run_attempt }}`,
      },
    ]);
  });

  it("queues cloud cells across refs and events without replacing pending work", () => {
    expect(cloudJob["concurrency"]).toEqual({
      group: "cloud-${{ matrix.provider }}",
      queue: "max",
      "cancel-in-progress": false,
    });
    expect(ci.concurrency["cancel-in-progress"]).toBe(true);
  });

  it("gives every dispatched run a concurrency group of its own, so nothing cancels the one a deployment waits on", () => {
    expect(ci.concurrency.group).toContain("${{ github.event_name }}");
    expect(ci.concurrency.group).toContain(
      "${{ github.event_name == 'workflow_dispatch' && format('-{0}', github.run_id) || '' }}",
    );
  });

  it("lets the relevance and verdict jobs finish before deployment verification expires", () => {
    const relevanceMinutes = Number(ci.jobs["cloud-relevance"]?.["timeout-minutes"]);
    const verdictMinutes = Number(ci.jobs[VERDICT_JOB]?.["timeout-minutes"]);
    expect(VERDICT_DEADLINE).toBeGreaterThan((relevanceMinutes + verdictMinutes) * 60_000);
  });

  it("is read by the suite under the names this environment publishes and creates", () => {
    expect(read("languages/python/tests/_support/aws_environment.py")).toContain(
      `PARAMETER: Final = "${TEST_ENVIRONMENT_PARAMETER}"`,
    );
    expect(read("languages/python/tests/_support/aws_run.py")).toContain(
      `CONTROL_DATABASE: Final = "${CONTROL_DATABASE}"`,
    );
  });
});
