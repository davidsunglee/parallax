/**
 * Value-object **compile-golden + pre-SQL-rejection lane** over the frozen
 * `m-value-object-*` corpus (Docker-free) — Phase 10's behavioral proof.
 *
 * This drives the real metamodel-backed resolver and the m-sql `compile` visitor
 * (the same seam the runner uses) DIRECTLY — NOT through the honesty-gated
 * conformance `describe` lane, which does not yet claim `m-value-object` (Phase 11).
 * It asserts two things over the frozen corpus:
 *
 *  1. **Golden-SQL parity, both dialects.** Every `read`-shape `m-value-object`
 *     case (nested predicates, absence collapse, to-many any/same-element,
 *     projection, graph materialization, temporal reads) compiles to its Postgres
 *     AND MariaDB golden `then.statements` — SQL text + per-dialect binds — proving
 *     the three `m-dialect` decision points (nested extraction, typed cast, array
 *     traversal) and the divergent per-dialect bind holes.
 *  2. **Pre-SQL rejection.** Every `rejected`-shape case's schema-valid input is
 *     refused by the model-aware validator (`@parallax/operation`) with the exact
 *     `then.rejectedRule`, before any SQL — the same refusal each language
 *     implementation must make.
 *
 * The positive reads are ALSO run through the operation validator to prove it
 * accepts every valid nested operation (the negative-only walk never false-rejects).
 */
import { canonicalBinds, mariadbDialect, postgresDialect } from "@parallax/dialect";
import {
  Metamodel,
  parseOperation,
  RejectionError,
  validateOperationValueObjects,
  validateWriteValueObjects,
} from "@parallax/operation";
import { compile } from "@parallax/sql";
import { describe, expect, it } from "vitest";
import { dialectStatements, goldenEntries } from "../src/case-format.js";
import { discoverCasePaths, type LoadedCase, loadCase } from "../src/discover.js";
import { schemaForReadCase } from "../src/schema-resolver.js";

/** Every discovered `m-value-object-*` case, loaded, keyed by its per-module id. */
function valueObjectCases(): readonly { id: string; loaded: LoadedCase }[] {
  return discoverCasePaths()
    .filter((path) => /\/m-value-object-\d{3}-/.test(path))
    .map((path) => ({
      id: path.replace(/^.*\/(m-value-object-\d{3})-.*$/, "$1"),
      loaded: loadCase(path),
    }));
}

const CASES = valueObjectCases();
const READ_CASES = CASES.filter(({ loaded }) => loaded.shape === "read");
const REJECTED_CASES = CASES.filter(({ loaded }) => loaded.shape === "rejected");

/** The one entity a value-object model declares (Customer / Contact / Supplier / Branch). */
function entityOf(loaded: LoadedCase) {
  const [entity] = Metamodel.fromDescriptor(loaded.descriptor).entities();
  if (entity === undefined) {
    throw new Error(`${loaded.casePath}: model declares no entity`);
  }
  return entity;
}

describe("m-value-object compile-golden lane — emitted === golden, both dialects", () => {
  it("discovers the frozen value-object case set (24 reads, 10 rejected)", () => {
    // Exact counts guard against a discovery regression silently dropping a case.
    expect(READ_CASES.length).toBe(28); // 001–024 + temporal reads 028–031
    expect(REJECTED_CASES.length).toBe(10); // 034–043
  });

  for (const dialect of [postgresDialect, mariadbDialect]) {
    describe(`dialect: ${dialect.id}`, () => {
      it.each(READ_CASES)("$id compiles to the golden SQL + binds", ({ loaded }) => {
        const golden = dialectStatements(goldenEntries(loaded.raw), dialect.id);
        expect(golden.length, `${loaded.casePath} declares a ${dialect.id} golden`).toBe(1);
        const operation = parseOperation(loaded.raw.when?.operation);
        const schema = schemaForReadCase(loaded, operation, dialect);
        const { sql, binds } = compile(operation, schema, dialect);
        expect(sql).toBe(golden[0]?.sql);
        // Canonicalize the compiled binds: a to-many read carries the array-guard
        // `rawJson('[]')` sentinel, which collapses to the scalar string `"[]"` the
        // hand-authored golden carries (byte-identical parity).
        expect(canonicalBinds(binds)).toEqual(golden[0]?.binds);
      });
    });
  }

  it("the operation validator accepts every valid nested read operation", () => {
    for (const { loaded } of READ_CASES) {
      const entity = entityOf(loaded);
      expect(
        () => validateOperationValueObjects(entity, loaded.raw.when?.operation),
        `${loaded.casePath} is a valid operation`,
      ).not.toThrow();
    }
  });
});

describe("deferral #1 — non-equality to-many lowering (MariaDB reject, Postgres general)", () => {
  // A schema-valid any-element NON-equality predicate through the `many` `phones`
  // segment: Postgres lowers it generally via jsonb_array_elements; MariaDB's
  // containment golden cannot express it, so the lowering rejects it pre-SQL rather
  // than emitting a json_contains that does not mean what the predicate says.
  const customer = loadCase(
    discoverCasePaths().find((path) => /\/m-value-object-017-/.test(path)) as string,
  );
  const operation = parseOperation({
    nestedNotEq: { path: "Customer.address.phones.type", value: "home" },
  });

  it("Postgres lowers the any-element notEq generally over the unnest alias", () => {
    const schema = schemaForReadCase(customer, operation, postgresDialect);
    const { sql } = compile(operation, schema, postgresDialect);
    expect(sql).toContain("where not jsonb_extract_path_text(t1.value, ?) = ?");
  });

  it("MariaDB rejects the any-element notEq with a capability diagnostic", () => {
    const schema = schemaForReadCase(customer, operation, mariadbDialect);
    expect(() => compile(operation, schema, mariadbDialect)).toThrow(
      /containment golden lowers only equality/,
    );
  });
});

describe("m-value-object rejected lane — pre-SQL refusal names the rule", () => {
  it.each(REJECTED_CASES)("$id is refused pre-SQL with its named rule", ({ loaded }) => {
    const entity = entityOf(loaded);
    const expectedRule = loaded.raw.then?.rejectedRule;
    expect(expectedRule, `${loaded.casePath} declares a rejectedRule`).toBeTypeOf("string");

    const when = loaded.raw.when as { operation?: unknown; write?: Record<string, unknown> };
    // A rejected case carries EXACTLY ONE of when.operation / when.write.
    expect(
      (when.operation === undefined) !== (when.write === undefined),
      `${loaded.casePath} carries exactly one of operation / write`,
    ).toBe(true);

    let caught: unknown;
    try {
      if (when.operation !== undefined) {
        validateOperationValueObjects(entity, when.operation);
      } else {
        validateWriteValueObjects(entity, when.write as Record<string, unknown>);
      }
    } catch (error) {
      caught = error;
    }
    expect(caught, `${loaded.casePath} must be rejected pre-SQL`).toBeInstanceOf(RejectionError);
    expect((caught as RejectionError).rule).toBe(expectedRule);
  });
});
