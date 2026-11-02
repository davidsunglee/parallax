import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  CONFORMANCE_LOGIN,
  CONFORMANCE_ROLES,
  CONTROL_DATABASE,
  CONVERGED_ROLE_FACTS,
  DEFAULT_ROLE,
  ROLE_BOOTSTRAP_SQL,
  ROLE_FACTS_SQL,
} from "../src/role-bootstrap.ts";
import { PACKAGE_ROOT } from "./committed-app.ts";

const PROVISIONER = join(
  PACKAGE_ROOT,
  "../../languages/python/packages/parallax-conformance/src/parallax/conformance/provision.py",
);

describe("the role bootstrap statement", () => {
  it("is one DO block, which runs as a single statement", () => {
    expect(ROLE_BOOTSTRAP_SQL.startsWith("DO $bootstrap$\n")).toBe(true);
    expect(ROLE_BOOTSTRAP_SQL.endsWith("\n$bootstrap$")).toBe(true);
    expect(ROLE_BOOTSTRAP_SQL.match(/\$bootstrap\$/g)).toHaveLength(2);
  });

  it("creates the database nowhere, because the cluster already did", () => {
    expect(ROLE_BOOTSTRAP_SQL).not.toMatch(/CREATE\s+DATABASE/i);
    expect(ROLE_BOOTSTRAP_SQL).toContain(
      `ALTER DATABASE ${CONTROL_DATABASE} OWNER TO ${CONFORMANCE_LOGIN};`,
    );
  });

  it("creates each role only when it is missing, so a repeated run converges", () => {
    const creations = ROLE_BOOTSTRAP_SQL.split("\n").filter((line) => line.includes("CREATE ROLE"));
    expect(creations).toHaveLength(2);
    expect(ROLE_BOOTSTRAP_SQL).toContain(
      "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = member)",
    );
    expect(ROLE_BOOTSTRAP_SQL).toContain(
      `IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${CONFORMANCE_LOGIN}')`,
    );
  });

  it("converges the login's attributes, IAM membership, roles, and default role", () => {
    for (const statement of [
      `ALTER ROLE ${CONFORMANCE_LOGIN} WITH LOGIN CREATEDB;`,
      `GRANT rds_iam TO ${CONFORMANCE_LOGIN};`,
      `EXECUTE format('GRANT %I TO ${CONFORMANCE_LOGIN}', member);`,
      `ALTER ROLE ${CONFORMANCE_LOGIN} SET role TO ${DEFAULT_ROLE};`,
    ]) {
      expect(ROLE_BOOTSTRAP_SQL).toContain(statement);
    }
    for (const role of CONFORMANCE_ROLES) expect(ROLE_BOOTSTRAP_SQL).toContain(`'${role}'`);
  });

  it("names exactly the roles the conformance provisioner grants", () => {
    const provisioner = readFileSync(PROVISIONER, "utf8");
    expect(provisioner).toContain(`CONFORMANCE_LOGIN: Final[str] = "${CONFORMANCE_LOGIN}"`);
    expect(provisioner).toContain(`_DEFAULT_ROLE = "${DEFAULT_ROLE}"`);
    const granted = [...provisioner.matchAll(/"role-[ab]": "([a-z_]+)"/g)].map((match) => match[1]);
    expect([DEFAULT_ROLE, ...granted]).toEqual([...CONFORMANCE_ROLES]);
  });
});

describe("the converged facts", () => {
  it("are read back by one query yielding one JSON text value", () => {
    expect(ROLE_FACTS_SQL.startsWith("SELECT json_build_object(")).toBe(true);
    expect(ROLE_FACTS_SQL.endsWith(")::text")).toBe(true);
    expect(ROLE_FACTS_SQL).not.toContain(";");
    for (const key of Object.keys(CONVERGED_ROLE_FACTS))
      expect(ROLE_FACTS_SQL).toContain(`'${key}'`);
    for (const name of [CONFORMANCE_LOGIN, ...CONFORMANCE_ROLES, CONTROL_DATABASE]) {
      expect(ROLE_FACTS_SQL).toContain(`'${name}'`);
    }
  });

  it("are what the statement converges: every role, the login's attributes, memberships, default role, and the database's owner", () => {
    expect(CONVERGED_ROLE_FACTS).toEqual({
      roles: [
        "parallax_conformance_default",
        "parallax_conformance_login",
        "parallax_conformance_role_a",
        "parallax_conformance_role_b",
      ],
      login: { canLogin: true, createdb: true },
      memberships: [
        "parallax_conformance_default",
        "parallax_conformance_role_a",
        "parallax_conformance_role_b",
        "rds_iam",
      ],
      settings: ["role=parallax_conformance_default"],
      controlOwner: CONFORMANCE_LOGIN,
    });
  });
});
