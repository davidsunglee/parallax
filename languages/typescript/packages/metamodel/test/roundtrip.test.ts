import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { assertRoundTrip, canonical, deserialize, serialize } from "@parallax/serde";
import { expect, describe as group, it } from "vitest";
import { deriveTemporal, Metamodel, normalizeEntity, validateDescriptor } from "../src/index.js";

/**
 * Resolve a repo-root-relative path from this test file. The metamodel package
 * sits at `languages/typescript/packages/metamodel/test/`, so the repo root is
 * five directories up.
 */
function repoPath(relative: string): string {
  const repoRoot = fileURLToPath(new URL("../../../../../", import.meta.url));
  return `${repoRoot}${relative}`;
}

const MODELS_DIR = repoPath("core/compatibility/models");

/** Every descriptor file in the corpus models directory. */
function modelFiles(): readonly string[] {
  return readdirSync(MODELS_DIR)
    .filter((name) => name.endsWith(".yaml") || name.endsWith(".yml"))
    .sort();
}

/** Parse a model descriptor from disk through the canonical YAML reader. */
function loadDescriptor(name: string): unknown {
  const text = readFileSync(`${MODELS_DIR}/${name}`, "utf8");
  return deserialize(text, "yaml");
}

group("metamodel descriptor round-trip", () => {
  it.each(modelFiles())("%s validates against metamodel.schema.json", (name) => {
    const descriptor = loadDescriptor(name);
    const { valid, errors } = validateDescriptor(descriptor);
    expect(errors).toEqual([]);
    expect(valid).toBe(true);
  });

  it.each(modelFiles())("%s round-trips losslessly through JSON and YAML", (name) => {
    const descriptor = loadDescriptor(name);
    // assertRoundTrip throws on any non-fixed-point or lossy format.
    expect(() => assertRoundTrip(descriptor)).not.toThrow();
  });

  it.each(modelFiles())("%s canonical form is a JSON<->YAML cross-format fixed point", (name) => {
    const descriptor = loadDescriptor(name);
    const canonicalForm = canonical(descriptor);
    // Serializing to JSON then parsing as JSON, and to YAML then parsing as
    // YAML, both recover the identical canonical value.
    const viaJson = canonical(deserialize(serialize(canonicalForm, "json"), "json"));
    const viaYaml = canonical(deserialize(serialize(canonicalForm, "yaml"), "yaml"));
    expect(viaJson).toEqual(canonicalForm);
    expect(viaYaml).toEqual(canonicalForm);
  });

  it.each(modelFiles())("%s reads through the generic reader", (name) => {
    const descriptor = loadDescriptor(name);
    const metamodel = Metamodel.fromDescriptor(descriptor);
    // Every model declares at least one entity with at least one PK attribute.
    expect(metamodel.entityNames().length).toBeGreaterThan(0);
    for (const entity of metamodel.entities()) {
      expect(entity.table.length).toBeGreaterThan(0);
      expect(entity.attributes().length).toBeGreaterThan(0);
      expect(entity.primaryKey().length).toBeGreaterThan(0);
    }
  });
});

group("default surfacing", () => {
  it("surfaces attribute boolean defaults (nullable/readOnly/primaryKey)", () => {
    const metamodel = Metamodel.fromDescriptor(loadDescriptor("orders.yaml"));
    const order = metamodel.entity("Order");
    const name = order.attributeByName("name");
    // `name` declares no nullable/primaryKey/readOnly — all default to false.
    expect(name.nullable).toBe(false);
    expect(name.primaryKey).toBe(false);
    expect(name.readOnly).toBe(false);
    expect(name.optimisticLocking).toBe(false);
    // `sku` is explicitly nullable.
    expect(order.attributeByName("sku").nullable).toBe(true);
    // `id` is the declared primary key.
    expect(order.attributeByName("id").primaryKey).toBe(true);
  });

  it("derives temporal from asOfAttributes and surfaces it", () => {
    const orders = Metamodel.fromDescriptor(loadDescriptor("orders.yaml"));
    expect(orders.entity("Order").temporal).toBe("non-temporal");

    const balance = Metamodel.fromDescriptor(loadDescriptor("balance.yaml"));
    expect(balance.entity("Balance").temporal).toBe("unitemporal-processing");

    const position = Metamodel.fromDescriptor(loadDescriptor("position.yaml"));
    expect(position.entity("Position").temporal).toBe("bitemporal");
    expect(position.entity("Position").asOfAttributes().length).toBe(2);
  });

  it("defaults relationship orderBy direction to asc", () => {
    const metamodel = Metamodel.fromDescriptor(loadDescriptor("orders.yaml"));
    const order = metamodel.entity("Order");
    // `items` declares `{ attr: id, direction: desc }` — kept verbatim.
    expect(order.relationshipByName("items").orderBy).toEqual([{ attr: "id", direction: "desc" }]);
    // `statuses` declares no orderBy at all.
    expect(order.relationshipByName("statuses").orderBy).toEqual([]);
    // `dependent` defaults to false where unspecified (`tags`).
    expect(order.relationshipByName("tags").dependent).toBe(false);
    expect(order.relationshipByName("items").dependent).toBe(true);
  });

  it("surfaces the optimisticLocking version attribute (M10 metamodel surface)", () => {
    const metamodel = Metamodel.fromDescriptor(loadDescriptor("account.yaml"));
    const account = metamodel.entity("Account");
    const version = account.versionAttribute();
    expect(version?.name).toBe("version");
    expect(version?.optimisticLocking).toBe(true);
  });

  it("derives the temporal optimistic key from the processing-from column (in_z), M7/M10", () => {
    const balance = Metamodel.fromDescriptor(loadDescriptor("balance.yaml")).entity("Balance");
    // A processing-axis temporal entity carries no version column; its optimistic key
    // is derived from the processing-from column (in_z) — the version analogue.
    const inZ = balance.processingFromAttribute();
    expect(inZ?.name).toBe("processingFrom");
    expect(inZ?.column).toBe("in_z");
    expect(balance.versionAttribute()).toBeUndefined();
    // A non-temporal entity has no processing axis, so no derived key.
    const order = Metamodel.fromDescriptor(loadDescriptor("orders.yaml")).entity("Order");
    expect(order.processingFromAttribute()).toBeUndefined();
  });

  it("resolves the processing-to column (out_z), the current-milestone marker, M7/M10", () => {
    const balance = Metamodel.fromDescriptor(loadDescriptor("balance.yaml")).entity("Balance");
    // The current milestone is the row whose processing-to (out_z) is infinity; observed
    // recording filters on it so a closed milestone cannot overwrite the current in_z.
    const outZ = balance.processingToAttribute();
    expect(outZ?.name).toBe("processingTo");
    expect(outZ?.column).toBe("out_z");
    // A non-temporal entity has no processing axis, so no to-attribute.
    const order = Metamodel.fromDescriptor(loadDescriptor("orders.yaml")).entity("Order");
    expect(order.processingToAttribute()).toBeUndefined();
  });

  it("rejects optimisticLocking + asOfAttributes on one entity (invalid composition, M1/M7/M10)", () => {
    // A temporal entity DERIVES its optimistic key from the processing-from column, so
    // combining an explicit `optimisticLocking` attribute with `asOfAttributes` is invalid.
    const bad = JSON.parse(JSON.stringify(loadDescriptor("balance.yaml"))) as {
      entity: { attributes: { name: string; optimisticLocking?: boolean }[] };
    };
    const value = bad.entity.attributes.find((a) => a.name === "value");
    if (value === undefined) {
      throw new Error("balance model has no 'value' attribute");
    }
    value.optimisticLocking = true;
    // Rejected at the SCHEMA layer (the entity `contains` rule) — `fromDescriptor`
    // validates before it normalizes, so it fails here.
    expect(validateDescriptor(bad).valid).toBe(false);
    expect(() => Metamodel.fromDescriptor(bad)).toThrow();
    // Rejected ALSO by the imperative normalize check (defense-in-depth), which owns
    // the descriptive message — exercised directly by bypassing the schema layer.
    expect(() =>
      normalizeEntity({
        name: "Bad",
        table: "bad",
        attributes: [
          { name: "id", type: "int64", column: "id", primaryKey: true },
          { name: "v", type: "int64", column: "v", optimisticLocking: true },
        ],
        asOfAttributes: [{ name: "p", fromColumn: "in_z", toColumn: "out_z", axis: "processing" }],
      }),
    ).toThrow(/optimisticLocking|asOfAttributes/);
  });

  it("surfaces asOfAttribute defaults (toIsInclusive/infinity/default)", () => {
    const metamodel = Metamodel.fromDescriptor(loadDescriptor("balance.yaml"));
    const axis = metamodel.entity("Balance").asOfAttributeByName("processingDate");
    expect(axis.toIsInclusive).toBe(false);
    expect(axis.infinity).toBe("infinity");
    expect(axis.default).toBe("now");
    expect(axis.axis).toBe("processing");
  });

  it("defaults value-object mapping to json and surfaces nullability", () => {
    const metamodel = Metamodel.fromDescriptor(loadDescriptor("customer.yaml"));
    const address = metamodel.entity("Customer").findValueObject("address");
    expect(address?.mapping).toBe("json");
    expect(address?.nullable).toBe(true);
  });

  it("deriveTemporal classifies each cardinality of asOf set", () => {
    expect(deriveTemporal([])).toBe("non-temporal");
    expect(
      deriveTemporal([{ name: "p", fromColumn: "in_z", toColumn: "out_z", axis: "processing" }]),
    ).toBe("unitemporal-processing");
    expect(
      deriveTemporal([{ name: "b", fromColumn: "from_z", toColumn: "thru_z", axis: "business" }]),
    ).toBe("unitemporal-business");
    expect(
      deriveTemporal([
        { name: "b", fromColumn: "from_z", toColumn: "thru_z", axis: "business" },
        { name: "p", fromColumn: "in_z", toColumn: "out_z", axis: "processing" },
      ]),
    ).toBe("bitemporal");
  });
});
