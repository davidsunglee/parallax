import { Stack, Token } from "aws-cdk-lib";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { Ajv2020 } from "ajv/dist/2020.js";
import { Construct, type IDependable } from "constructs";
import schema from "../test-environment.schema.json" with { type: "json" };
import {
  CLUSTER_IDENTIFIER,
  CLUSTER_MEMBERS,
  POSTGRES_PORT,
  type AuroraCluster,
} from "./constructs/aurora-cluster.ts";
import type { TestEnvironment } from "./generated/test-environment.ts";
import { CONFORMANCE_LOGIN } from "./role-bootstrap.ts";

/** Where the deployed record is published for the cloud suite. */
export const TEST_ENVIRONMENT_PARAMETER = "/parallax/ci/aws/test-environment";

/**
 * Stands in for an endpoint hostname CloudFormation resolves only at deploy
 * time. It satisfies the schema's host rule and no other field's, so a token in
 * any field but a host still fails validation.
 */
export const UNRESOLVED_HOST_WITNESS = "unresolved.cluster-token.rds.amazonaws.com";

const ajv = new Ajv2020({ allErrors: true });
const validate = ajv.compile<TestEnvironment>(schema);

/** The record describing *aurora* in *region*, with its endpoints still deploy-time tokens. */
export function testEnvironment(aurora: AuroraCluster, region: string): TestEnvironment {
  const cluster = aurora.cluster;
  return {
    schema: 1,
    writer_host: cluster.clusterEndpoint.hostname,
    reader_host: cluster.clusterReadEndpoint.hostname,
    port: POSTGRES_PORT,
    region,
    login: CONFORMANCE_LOGIN,
    cluster_id: CLUSTER_IDENTIFIER,
    instances: CLUSTER_MEMBERS.map((member) => ({
      identifier: member.identifier,
      host: aurora.memberHost(member),
      role: member.role,
    })),
    ca_bundle_url: `https://truststore.pki.rds.amazonaws.com/${region}/${region}-bundle.pem`,
  };
}

function withTokenWitnesses(value: unknown): unknown {
  if (typeof value === "string") {
    return Token.isUnresolved(value) ? UNRESOLVED_HOST_WITNESS : value;
  }
  if (Array.isArray(value)) return value.map(withTokenWitnesses);
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value).map(([key, field]) => [key, withTokenWitnesses(field)]),
    );
  }
  return value;
}

/**
 * Refuse a record that does not conform to the published schema.
 *
 * Deploy-time tokens are checked as hosts: the schema is the contract the
 * suite validates the deployed record against, so it is never relaxed to admit
 * CloudFormation's token encoding.
 */
export function assertTestEnvironment(record: unknown): asserts record is TestEnvironment {
  if (!validate(withTokenWitnesses(record))) {
    throw new Error(
      `the TestEnvironment record does not conform: ${ajv.errorsText(validate.errors, { dataVar: "record" })}`,
    );
  }
}

export interface TestEnvironmentParameterProps {
  readonly record: TestEnvironment;
  /** What must have succeeded before the record may be published. */
  readonly after: readonly IDependable[];
}

/** The validated record, published as one SSM parameter once everything it describes is ready. */
export class TestEnvironmentParameter extends Construct {
  readonly parameter: ssm.StringParameter;

  constructor(scope: Construct, id: string, props: TestEnvironmentParameterProps) {
    super(scope, id);
    assertTestEnvironment(props.record);
    this.parameter = new ssm.StringParameter(this, "Parameter", {
      parameterName: TEST_ENVIRONMENT_PARAMETER,
      description: "Where the Parallax cloud suite finds its Aurora environment",
      stringValue: Stack.of(this).toJsonString(props.record),
      tier: ssm.ParameterTier.STANDARD,
    });
    for (const dependency of props.after) {
      this.parameter.node.addDependency(dependency);
    }
  }
}
