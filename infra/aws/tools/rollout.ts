import { parseArgs } from "node:util";
import {
  accessStackFinding,
  bootstrapFinding,
  identityFinding,
  natImageFinding,
  offeringFinding,
  oidcProviderFinding,
  sourceConnectionFinding,
} from "./aws-assessment.ts";
import { budgetFindings, readBudgets } from "./budget-assessment.ts";
import { systemClock, type Clock } from "./clock.ts";
import { verifyCloud } from "./cloud-verification.ts";
import { deploy, rolloutEvidence } from "./deployment.ts";
import { CHECK, guarded, report, type Finding } from "./findings.ts";
import {
  branchesFinding,
  environmentFinding,
  forkApprovalFinding,
  repositoryFinding,
  subjectFinding,
  tokenFinding,
} from "./github-assessment.ts";
import { PACKAGE_ROOT, rolloutContext, type RolloutContext } from "./rollout-context.ts";
import { applyStep } from "./setup-steps.ts";
import { systemShell, type Shell } from "./shell.ts";

const USAGE = `usage: node aws/tools/rollout.ts [preflight]
       node aws/tools/rollout.ts verify-github | verify-aws
       node aws/tools/rollout.ts deploy --revision <sha>
       node aws/tools/rollout.ts evidence --revision <sha> --run-url <url>
       node aws/tools/rollout.ts verify-cloud --revision <sha>
       node aws/tools/rollout.ts apply <step> --authorize <step> --revision <sha>`;

/** What no configuration check can establish: only the protected deployment and the cloud run prove them. */
export const LIVE_PROOFS: readonly string[] = [
  "Aurora PostgreSQL 18.6 Serverless v2 accepts IAM authentication (first deployment)",
  "the role bootstrap signs in as the master user from inside the VPC, by IAM once the first run has made it IAM-only (deployment evidence)",
  "the bounded execution policy covers every environment resource (first deployment)",
  "the role bootstrap converges on its first and on a repeated run (deployment evidence)",
  "the runner reads the source through the existing connection and its webhook queues jobs (first cloud job)",
  "verify-full TLS and IAM tokens on the writer and reader hostnames (cloud suite)",
];

/** The repository protections the deploy workflow verifies before it obtains AWS credentials. */
export function githubGate(context: RolloutContext): Finding[] {
  return [
    ...guarded(CHECK.repository, () => repositoryFinding(context)),
    ...guarded(CHECK.forkApproval, () => forkApprovalFinding(context)),
    ...guarded(CHECK.environment, () => environmentFinding(context)),
    ...guarded(CHECK.branches, () => branchesFinding(context)),
    ...guarded(CHECK.subject, () => subjectFinding(context)),
  ];
}

/** What the deploy workflow verifies as the deploy role before it deploys. */
export function awsGate(context: RolloutContext): Finding[] {
  return [
    ...guarded(CHECK.identity, () => identityFinding(context, "deploy")),
    ...guarded(CHECK.offering, () => offeringFinding(context)),
    ...guarded(CHECK.natImage, () =>
      natImageFinding(context, context.inputs.natInstanceImage, false),
    ),
  ];
}

/** Every configuration check, read-only, as a maintainer runs them before any setup step. */
export function preflightFindings(context: RolloutContext): Finding[] {
  return [
    ...guarded(CHECK.identity, () => identityFinding(context, "maintainer")),
    ...guarded(CHECK.provider, () => oidcProviderFinding(context)),
    ...guarded(CHECK.connection, () => sourceConnectionFinding(context)),
    ...guarded(CHECK.offering, () => offeringFinding(context)),
    ...guarded(CHECK.natImage, () =>
      natImageFinding(context, context.inputs.natInstanceImage, true),
    ),
    ...guarded(CHECK.budget, () => {
      const { budgets, owned } = readBudgets(context.read, context.anchors.account);
      return budgetFindings(context.rollout.budget, budgets, owned);
    }),
    ...guarded(CHECK.accessStack, () => accessStackFinding(context)),
    ...guarded(CHECK.bootstrap, () => bootstrapFinding(context)),
    ...githubGate(context),
    ...guarded(CHECK.token, () => tokenFinding(context)),
  ];
}

interface Options {
  readonly revision?: string | undefined;
  readonly authorize?: string | undefined;
  readonly "run-url"?: string | undefined;
}

function evidence(context: RolloutContext, options: Options): number {
  const { revision, "run-url": runUrl } = options;
  if (revision === undefined || runUrl === undefined) return usage();
  const { evidence: found, problems } = rolloutEvidence(context, revision, runUrl);
  return printed(found, problems, "evidence");
}

function printed(found: unknown, problems: readonly string[], command: string): number {
  console.log(["```json", JSON.stringify(found, null, 2), "```"].join("\n"));
  for (const problem of problems) console.error(`${command}: ${problem}`);
  return problems.length === 0 ? 0 : 1;
}

function cloudVerification(context: RolloutContext, revision: string): number {
  const { verification, problems } = verifyCloud(context, revision, context.clock);
  return printed(verification, problems, "verify-cloud");
}

function usage(): number {
  console.error(USAGE);
  return 2;
}

type Command = (context: RolloutContext, step: string | undefined, options: Options) => number;

const verdict = (ready: boolean): number => (ready ? 0 : 1);

const COMMANDS: Readonly<Record<string, Command>> = {
  preflight: (context) => verdict(report(preflightFindings(context), LIVE_PROOFS)),
  "verify-github": (context) => verdict(report(githubGate(context), [])),
  "verify-aws": (context) => verdict(report(awsGate(context), [])),
  deploy: (context, _step, { revision }) =>
    revision === undefined ? usage() : deploy(context, revision),
  evidence: (context, _step, options) => evidence(context, options),
  "verify-cloud": (context, _step, { revision }) =>
    revision === undefined ? usage() : cloudVerification(context, revision),
  apply: (context, step, { revision, authorize = "" }) =>
    step === undefined || revision === undefined
      ? usage()
      : applyStep(context, step, authorize, revision),
};

/**
 * Check, set up, deploy, record, or prove the AWS rollout. With no command it
 * runs the read-only preflight; only `apply`, under an explicit per-step
 * authorization, and `deploy` and `verify-cloud`, which protected CI runs,
 * change anything — `verify-cloud` by dispatching the cloud path for the
 * deployed commit. No verification gate runs this tool.
 *
 * Exit codes: 0 — everything checked holds, or the command succeeded;
 * 1 — something is pending, drifted, unchecked, or refused; 2 — usage error.
 */
export function main(
  argv: readonly string[],
  shell: Shell = systemShell,
  root: string = PACKAGE_ROOT,
  clock: Clock = systemClock,
): number {
  let parsed;
  try {
    parsed = parseArgs({
      args: [...argv],
      allowPositionals: true,
      options: {
        revision: { type: "string" },
        authorize: { type: "string" },
        "run-url": { type: "string" },
      },
    });
  } catch {
    return usage();
  }
  const [command = "preflight", step, ...extra] = parsed.positionals;
  const run = COMMANDS[command];
  if (run === undefined || extra.length > 0 || (step !== undefined && command !== "apply"))
    return usage();
  return run(rolloutContext(shell, root, clock), step, parsed.values);
}

if (import.meta.main) process.exitCode = main(process.argv.slice(2));
