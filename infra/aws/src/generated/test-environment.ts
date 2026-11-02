// Generated from test-environment.schema.json by tools/check-generated.ts --write; do not edit.

export type Host = string;

/**
 * Where the cloud suite finds the deployed Aurora environment and how it authenticates there. Infrastructure publishes one record; the suite reads the schema version the record names.
 */
export interface TestEnvironment {
  /**
   * The version of this record's shape.
   */
  schema: 1;
  /**
   * The cluster (writer) endpoint.
   */
  writer_host: string;
  /**
   * The cluster reader endpoint.
   */
  reader_host: string;
  port: number;
  region: string;
  /**
   * The IAM-authenticated database login every route uses.
   */
  login: string;
  cluster_id: string;
  /**
   * Every instance endpoint, so a test can inspect each physical instance directly.
   */
  instances: Instance[];
  /**
   * Where the certificate bundle verifying every endpoint is published.
   */
  ca_bundle_url: string;
}
export interface Instance {
  identifier: string;
  host: Host;
  role: "writer" | "reader";
}
