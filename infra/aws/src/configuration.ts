/** The CDK context key holding the deployment's {@link EnvironmentConfiguration}. */
export const CONFIGURATION_CONTEXT_KEY = "parallax:environment";

export interface AuroraCapacity {
  readonly minCapacity: number;
  readonly maxCapacity: number;
  readonly autoPauseSeconds: number;
}

/** What one deployment of the environment varies: where it lives and how much it may scale. */
export interface EnvironmentConfiguration {
  readonly account: string;
  readonly region: string;
  readonly availabilityZones: readonly string[];
  readonly natInstanceType: string;
  readonly aurora: AuroraCapacity;
}

/** A configuration value that cannot describe a deployable environment. */
export class ConfigurationError extends Error {
  override readonly name = "ConfigurationError";
}

const ACCOUNT = /^\d{12}$/;
const REGION = /^[a-z]{2}(-[a-z]+)+-\d$/;
// The NAT instance runs an arm64 image, so only a Graviton burstable type can boot it.
const NAT_INSTANCE_TYPE = /^t4g\.[a-z0-9]+$/;
const CAPACITY_STEP = 0.5;
const MAX_CAPACITY_LIMIT = 256;
const AUTO_PAUSE_SECONDS = { min: 300, max: 86_400 } as const;

function record(value: unknown, what: string): Readonly<Record<string, unknown>> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ConfigurationError(`${what} must be an object`);
  }
  return value as Record<string, unknown>;
}

function matching(value: unknown, pattern: RegExp, what: string): string {
  if (typeof value !== "string" || !pattern.test(value)) {
    throw new ConfigurationError(`${what} must match ${String(pattern)}`);
  }
  return value;
}

function zones(value: unknown, region: string): readonly string[] {
  const pattern = new RegExp(`^${region}[a-z]$`);
  if (!Array.isArray(value) || value.length < 2) {
    throw new ConfigurationError("availabilityZones must name at least two zones");
  }
  const named = value.map((zone) => matching(zone, pattern, "each availability zone"));
  if (new Set(named).size !== named.length) {
    throw new ConfigurationError("availabilityZones must not repeat a zone");
  }
  return named;
}

function capacityUnits(value: unknown, what: string, min: number, max: number): number {
  if (typeof value !== "number" || value < min || value > max || value % CAPACITY_STEP !== 0) {
    throw new ConfigurationError(
      `${what} must be a multiple of ${String(CAPACITY_STEP)} from ${String(min)} to ${String(max)}`,
    );
  }
  return value;
}

function capacity(value: unknown): AuroraCapacity {
  const fields = record(value, "aurora");
  // Serverless v2 pauses only from a zero-capacity floor.
  const minCapacity = capacityUnits(fields["minCapacity"], "aurora.minCapacity", 0, 0);
  const maxCapacity = capacityUnits(
    fields["maxCapacity"],
    "aurora.maxCapacity",
    1,
    MAX_CAPACITY_LIMIT,
  );
  const autoPauseSeconds = fields["autoPauseSeconds"];
  if (
    typeof autoPauseSeconds !== "number" ||
    !Number.isInteger(autoPauseSeconds) ||
    autoPauseSeconds < AUTO_PAUSE_SECONDS.min ||
    autoPauseSeconds > AUTO_PAUSE_SECONDS.max
  ) {
    throw new ConfigurationError(
      `aurora.autoPauseSeconds must be a whole number of seconds from ${String(AUTO_PAUSE_SECONDS.min)} to ${String(AUTO_PAUSE_SECONDS.max)}`,
    );
  }
  return { minCapacity, maxCapacity, autoPauseSeconds };
}

/** *value*, the deployment's committed context entry, as a validated configuration. */
export function environmentConfiguration(value: unknown): EnvironmentConfiguration {
  const fields = record(value, CONFIGURATION_CONTEXT_KEY);
  const region = matching(fields["region"], REGION, "region");
  return {
    account: matching(fields["account"], ACCOUNT, "account"),
    region,
    availabilityZones: zones(fields["availabilityZones"], region),
    natInstanceType: matching(fields["natInstanceType"], NAT_INSTANCE_TYPE, "natInstanceType"),
    aurora: capacity(fields["aurora"]),
  };
}
