import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  CONFIGURATION_CONTEXT_KEY,
  environmentConfiguration,
  type EnvironmentConfiguration,
} from "../src/configuration.ts";
import {
  ROLLOUT_CONTEXT_KEY,
  rolloutConfiguration,
  type RolloutConfiguration,
} from "../src/rollout-configuration.ts";
import { trustAnchors, type TrustAnchors } from "../src/trust.ts";
import type { AwsContext } from "./aws-assessment.ts";
import { systemClock, type Clock } from "./clock.ts";
import { sources, type Sources } from "./findings.ts";
import type { GitHubContext } from "./github-assessment.ts";
import type { Shell } from "./shell.ts";

/** The AWS provider package: its committed context and deploy inputs. */
export const PACKAGE_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

/** The pinned CDK CLI every setup and deploy command runs. */
export const CDK_CLI = fileURLToPath(import.meta.resolve("aws-cdk/bin/cdk"));

/** The reviewed values a deployment supplies as stack parameters. */
export interface DeployInputs {
  /** The NAT instance's image, or `null` until a reviewed one is committed. */
  readonly natInstanceImage: string | null;
}

const IMAGE = /^ami-(?:[0-9a-f]{8}|[0-9a-f]{17})$/;

/** *value*, the committed `deploy-inputs.json`, validated. */
export function deployInputs(value: unknown): DeployInputs {
  const image = (value as { natInstanceImage?: unknown } | null)?.natInstanceImage;
  if (image === null) return { natInstanceImage: null };
  if (typeof image !== "string" || !IMAGE.test(image)) {
    throw new Error("deploy-inputs.json: natInstanceImage must be null or an image ID");
  }
  return { natInstanceImage: image };
}

/** Everything a rollout command works from: committed configuration, and the shell it reaches the world through. */
export interface RolloutContext extends AwsContext, GitHubContext {
  readonly shell: Shell;
  readonly root: string;
  readonly configuration: EnvironmentConfiguration;
  readonly rollout: RolloutConfiguration;
  readonly anchors: TrustAnchors;
  readonly inputs: DeployInputs;
  readonly read: Sources;
  readonly clock: Clock;
}

function json(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

/** The rollout context committed under *root*, reached through *shell*, spending time on *clock*. */
export function rolloutContext(
  shell: Shell,
  root: string = PACKAGE_ROOT,
  clock: Clock = systemClock,
): RolloutContext {
  const { context } = json(join(root, "cdk.json")) as { context: Record<string, unknown> };
  const configuration = environmentConfiguration(context[CONFIGURATION_CONTEXT_KEY]);
  const rollout = rolloutConfiguration(context[ROLLOUT_CONTEXT_KEY], configuration);
  return {
    shell,
    root,
    configuration,
    rollout,
    anchors: trustAnchors(configuration, rollout),
    inputs: deployInputs(json(join(root, "deploy-inputs.json"))),
    read: sources(shell, configuration.region),
    clock,
  };
}
