/**
 * Model-aware value-object validator unit tests (m-value-object / m-op-algebra,
 * resolved Q7) — the `rejected`-shape refusal in isolation.
 *
 * The whole-corpus rejection lane (every `m-value-object-034..043` case) lives in
 * `@parallax/conformance`; this pins the validator's own branches over a hand-built
 * metamodel — notably the ones the equality-only corpus does not exercise: a
 * violation buried inside an `and` (the ANY-DEPTH scope), an unknown INTERMEDIATE
 * segment, and the element-scope resolution inside a scoped `where`.
 */
import {
  Metamodel,
  RejectedRule,
  RejectionError,
  validateOperationValueObjects,
  validateWriteValueObjects,
} from "@parallax/operation";
import { describe, expect, it } from "vitest";

/** A Customer descriptor with the recursive `address` value object (required inner members). */
const DESCRIPTOR = {
  entity: {
    name: "Customer",
    table: "customer",
    attributes: [
      { name: "id", type: "int64", column: "id", primaryKey: true },
      { name: "name", type: "string", column: "name" },
    ],
    valueObjects: [
      {
        name: "address",
        column: "address",
        mapping: "json",
        nullable: true,
        attributes: [
          { name: "street", type: "string" },
          { name: "city", type: "string" },
        ],
        valueObjects: [
          {
            name: "geo",
            cardinality: "one",
            attributes: [{ name: "country", type: "string" }],
            valueObjects: [
              {
                name: "point",
                cardinality: "one",
                attributes: [
                  { name: "lat", type: "float64" },
                  { name: "lon", type: "float64" },
                ],
              },
            ],
          },
          {
            name: "phones",
            cardinality: "many",
            nullable: true,
            attributes: [
              { name: "type", type: "string", nullable: true },
              { name: "number", type: "string", nullable: true },
            ],
          },
        ],
      },
    ],
  },
};

const CUSTOMER = Metamodel.fromDescriptor(DESCRIPTOR).entity("Customer");

/** Assert an operation is rejected with the expected rule. */
function expectOperationRule(operation: unknown, rule: string): void {
  try {
    validateOperationValueObjects(CUSTOMER, operation);
  } catch (error) {
    expect(error).toBeInstanceOf(RejectionError);
    expect((error as RejectionError).rule).toBe(rule);
    return;
  }
  throw new Error("expected the operation to be rejected");
}

/** Assert a write row is rejected with the expected rule. */
function expectWriteRule(row: Record<string, unknown>, rule: string): void {
  try {
    validateWriteValueObjects(CUSTOMER, row);
  } catch (error) {
    expect(error).toBeInstanceOf(RejectionError);
    expect((error as RejectionError).rule).toBe(rule);
    return;
  }
  throw new Error("expected the write to be rejected");
}

describe("operation validation — path & literal rules", () => {
  it("accepts a valid nested predicate", () => {
    expect(() =>
      validateOperationValueObjects(CUSTOMER, {
        nestedEq: { path: "Customer.address.geo.country", value: "US" },
      }),
    ).not.toThrow();
  });

  it("rejects a first segment that is not a declared value object", () => {
    expectOperationRule(
      { nestedEq: { path: "Customer.contact.city", value: "Oslo" } },
      RejectedRule.NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
    );
  });

  it("rejects an unknown INTERMEDIATE nested value object", () => {
    expectOperationRule(
      { nestedEq: { path: "Customer.address.region.name", value: "x" } },
      RejectedRule.NESTED_PATH_UNKNOWN_MEMBER,
    );
  });

  it("rejects an unknown leaf attribute", () => {
    expectOperationRule(
      { nestedEq: { path: "Customer.address.zip", value: "x" } },
      RejectedRule.NESTED_PATH_UNKNOWN_MEMBER,
    );
  });

  it("rejects a type-mismatched literal", () => {
    expectOperationRule(
      { nestedEq: { path: "Customer.address.city", value: 42 } },
      RejectedRule.NESTED_LITERAL_TYPE_MISMATCH,
    );
  });

  it("rejects a violation buried inside an `and` (enforced at ANY depth)", () => {
    expectOperationRule(
      {
        and: {
          operands: [
            { eq: { attr: "Customer.name", value: "Ada" } },
            { nestedEq: { path: "Customer.address.city", value: 42 } },
          ],
        },
      },
      RejectedRule.NESTED_LITERAL_TYPE_MISMATCH,
    );
  });

  it("rejects a mistyped LITERAL inside a scoped element `where`", () => {
    expectOperationRule(
      {
        nestedExists: {
          path: "Customer.address.phones",
          where: { nestedEq: { path: "type", value: 42 } },
        },
      },
      RejectedRule.NESTED_LITERAL_TYPE_MISMATCH,
    );
  });

  it("rejects an unknown element member inside a scoped `where`", () => {
    expectOperationRule(
      {
        nestedExists: {
          path: "Customer.address.phones",
          where: { nestedIsNull: { path: "zip" } },
        },
      },
      RejectedRule.NESTED_PATH_UNKNOWN_MEMBER,
    );
  });
});

describe("operation validation — value-object misuse rules", () => {
  it("rejects a deepFetch path segment naming a value object", () => {
    expectOperationRule(
      { deepFetch: { operand: { all: {} }, paths: [[{ rel: "Customer.address" }]] } },
      RejectedRule.DEEP_FETCH_VALUE_OBJECT_SEGMENT,
    );
  });

  it("rejects a navigation targeting a value object", () => {
    expectOperationRule(
      { navigate: { rel: "Customer.address" } },
      RejectedRule.NAVIGATE_VALUE_OBJECT_TARGET,
    );
  });

  it("rejects a find() rooted at a value object", () => {
    expectOperationRule(
      { isNotNull: { attr: "address.city" } },
      RejectedRule.FIND_ROOT_VALUE_OBJECT,
    );
  });
});

describe("write validation", () => {
  it("accepts a structurally complete document", () => {
    expect(() =>
      validateWriteValueObjects(CUSTOMER, {
        id: 1,
        name: "Ada",
        address: {
          street: "1 Park Ave",
          city: "Oslo",
          geo: { country: "NO", point: { lat: 59.9, lon: 10.7 } },
        },
      }),
    ).not.toThrow();
  });

  it("accepts a null (nullable) value object", () => {
    expect(() =>
      validateWriteValueObjects(CUSTOMER, { id: 1, name: "Ada", address: null }),
    ).not.toThrow();
  });

  it("rejects a missing required attribute at depth", () => {
    expectWriteRule(
      {
        id: 1,
        name: "Ada",
        address: { city: "Oslo", geo: { country: "NO", point: { lat: 1, lon: 2 } } },
      },
      RejectedRule.WRITE_REQUIRED_ATTRIBUTE_MISSING,
    );
  });

  it("rejects a missing required nested value object", () => {
    expectWriteRule(
      { id: 1, name: "Ada", address: { street: "1 Park Ave", city: "Oslo" } },
      RejectedRule.WRITE_REQUIRED_VALUE_OBJECT_MISSING,
    );
  });

  it("rejects a type-mismatched document field", () => {
    expectWriteRule(
      {
        id: 1,
        name: "Ada",
        address: { street: 42, city: "Oslo", geo: { country: "NO", point: { lat: 1, lon: 2 } } },
      },
      RejectedRule.WRITE_VALUE_TYPE_MISMATCH,
    );
  });

  it("accepts an empty `many` array (emptiness is not a nullability violation)", () => {
    expect(() =>
      validateWriteValueObjects(CUSTOMER, {
        id: 1,
        name: "Ada",
        address: {
          street: "1 Park Ave",
          city: "Oslo",
          geo: { country: "NO", point: { lat: 1, lon: 2 } },
          phones: [],
        },
      }),
    ).not.toThrow();
  });
});
