/** The database the cluster creates at birth; the cloud suite serializes its runs on it. */
export const CONTROL_DATABASE = "parallax_ci_control";

/**
 * The IAM-authenticated login every cloud route uses, and the roles it may act
 * as. They are the conformance provisioner's own names, so the shared reset and
 * grant path applies unchanged on Aurora.
 */
export const CONFORMANCE_LOGIN = "parallax_conformance_login";
export const DEFAULT_ROLE = "parallax_conformance_default";
export const CONFORMANCE_ROLES = [
  DEFAULT_ROLE,
  "parallax_conformance_role_a",
  "parallax_conformance_role_b",
] as const;

const roleArray = CONFORMANCE_ROLES.map((role) => `'${role}'`).join(", ");

/**
 * One statement converging the login and its roles, safe to run any number of
 * times.
 *
 * It runs as the cluster's master user, which is not a superuser, so it sets
 * only attributes that user may set. The control database already exists, made
 * with the cluster, because `CREATE DATABASE` cannot run inside the
 * transaction a `DO` block is; ownership moves to the login, which first lets
 * the master act as it.
 */
export const ROLE_BOOTSTRAP_SQL = `DO $bootstrap$
DECLARE
  member name;
BEGIN
  FOREACH member IN ARRAY ARRAY[${roleArray}]::name[] LOOP
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = member) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN', member);
    END IF;
  END LOOP;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${CONFORMANCE_LOGIN}') THEN
    CREATE ROLE ${CONFORMANCE_LOGIN} LOGIN;
  END IF;
  ALTER ROLE ${CONFORMANCE_LOGIN} WITH LOGIN CREATEDB;
  GRANT rds_iam TO ${CONFORMANCE_LOGIN};
  FOREACH member IN ARRAY ARRAY[${roleArray}]::name[] LOOP
    EXECUTE format('GRANT %I TO ${CONFORMANCE_LOGIN}', member);
  END LOOP;
  ALTER ROLE ${CONFORMANCE_LOGIN} SET role TO ${DEFAULT_ROLE};
  GRANT ${CONFORMANCE_LOGIN} TO CURRENT_USER;
  ALTER DATABASE ${CONTROL_DATABASE} OWNER TO ${CONFORMANCE_LOGIN};
END
$bootstrap$`;
