import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { assertRoundTrip, canonical, deserialize, serialize } from "@parallax/serde";
import { expect, describe as group, it } from "vitest";
import {
  deriveTemporal,
  findNestedValueObject,
  findValueObjectAttribute,
  Metamodel,
  normalizeEntity,
  validateDescriptor,
} from "../src/index.js";

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
    expect(metamodel.entityNames().length).toBeGreaterThan(0);
    for (const entity of metamodel.entities()) {
      const inheritance = entity.inheritance;
      // Standalone entities and TPH roots own a table. TPH descendants and
      // abstract TPCS nodes are tableless; concrete TPCS subtypes own a table.
      if (
        inheritance === undefined ||
        (inheritance.role === "root" && inheritance.strategy === "table-per-hierarchy") ||
        (inheritance.role === "concrete-subtype" && entity.table.length > 0)
      ) {
        expect(entity.table.length).toBeGreaterThan(0);
      }
      // A non-inheritance entity declares at least one attribute and a primary key
      // LOCALLY. An inheritance participant may declare only inherited attributes and
      // inherit its primary key from an ancestor (the generic reader does not flatten
      // the ancestry chain), so the local-declaration check is exempt for it.
      if (entity.inheritance === undefined) {
        expect(entity.attributes().length).toBeGreaterThan(0);
        expect(entity.primaryKey().length).toBeGreaterThan(0);
      }
    }
  });

  it("rejects every retired descriptor spelling instead of dual-reading it", () => {
    const retired = {
      entity: {
        name: "Legacy",
        table: "legacy",
        mutability: "transactional",
        attributes: [
          {
            name: "id",
            type: "int64",
            column: "id",
            primaryKey: true,
            pkGenerator: "none",
          },
        ],
      },
    };
    expect(validateDescriptor(retired).valid).toBe(false);
    expect(() => Metamodel.fromDescriptor(retired)).toThrow();
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

  it("derives the operational temporal view from canonical asOfAxes", () => {
    const orders = Metamodel.fromDescriptor(loadDescriptor("orders.yaml"));
    expect(orders.entity("Order").temporal).toBe("non-temporal");

    const balance = Metamodel.fromDescriptor(loadDescriptor("balance.yaml"));
    expect(balance.entity("Balance").temporal).toBe("transaction-time-only");

    const position = Metamodel.fromDescriptor(loadDescriptor("position.yaml"));
    expect(position.entity("Position").temporal).toBe("bitemporal");
    expect(position.entity("Position").asOfAxes().length).toBe(2);
  });

  it("defaults relationship orderBy direction to asc", () => {
    const metamodel = Metamodel.fromDescriptor(loadDescriptor("orders.yaml"));
    const order = metamodel.entity("Order");
    // `items` declares `{ attribute: id, direction: desc }` — normalized once.
    expect(order.relationshipByName("items").orderBy).toEqual([
      {
        attribute: { entity: "parallax.compatibility.OrderItem", name: "id" },
        direction: "desc",
      },
    ]);
    // `statuses` declares no orderBy at all.
    expect(order.relationshipByName("statuses").orderBy).toEqual([]);
    // `dependent` defaults to false where unspecified (`tags`).
    expect(order.relationshipByName("tags").dependent).toBe(false);
    expect(order.relationshipByName("items").dependent).toBe(true);

    // The reverse declaration repeats no association facts; the Relationship
    // Facet derives its directional cardinality and structured join.
    const itemOrder = metamodel.entity("OrderItem").relationshipByName("order");
    expect(itemOrder.cardinality).toBe("many-to-one");
    expect(itemOrder.join).toEqual({
      source: { entity: "parallax.compatibility.OrderItem", name: "orderId" },
      target: { entity: "parallax.compatibility.Order", name: "id" },
    });
    expect(itemOrder).not.toHaveProperty("target");
    expect(itemOrder).not.toHaveProperty("relatedEntity");
    expect(itemOrder).not.toHaveProperty("reverseName");
    expect(itemOrder).not.toHaveProperty("foreignKey");
  });

  it("preserves exact relationship identity across namespaces", () => {
    const model = Metamodel.fromDescriptor({
      entities: [
        {
          name: "Source",
          namespace: "alpha",
          table: "source",
          attributes: [{ name: "id", type: "int64", primaryKey: true }],
          relationships: [
            {
              name: "targets",
              cardinality: "one-to-many",
              join: {
                source: "id",
                target: { entity: "beta.Target", attribute: "sourceId" },
              },
            },
          ],
        },
        {
          name: "Target",
          namespace: "alpha",
          table: "alpha_target",
          attributes: [{ name: "id", type: "int64", primaryKey: true }],
        },
        {
          name: "Target",
          namespace: "beta",
          table: "beta_target",
          attributes: [
            { name: "id", type: "int64", primaryKey: true },
            { name: "sourceId", type: "int64" },
          ],
          relationships: [{ name: "source", reverseOf: "alpha.Source.targets" }],
        },
      ],
    });

    expect(model.entity("alpha.Source").relationshipByName("targets").join.target.entity).toBe(
      "beta.Target",
    );
    expect(model.entity("beta.Target").relationshipByName("source").join.target.entity).toBe(
      "alpha.Source",
    );
    expect(model.findEntity("Target")).toBeUndefined();
  });

  it("defaults persistence to read-write and inherits a read-only family root", () => {
    const ordinary = Metamodel.fromDescriptor({
      entity: {
        name: "Widget",
        table: "widget",
        attributes: [{ name: "id", type: "int64", primaryKey: true }],
      },
    }).entity("Widget");
    expect(ordinary.mutability).toBe("transactional");
    expect(ordinary.attributeByName("id").column).toBe("id");
    expect(ordinary.attributeByName("id").pkGenerator).toBe("none");

    const family = Metamodel.fromDescriptor({
      entities: [
        {
          name: "Asset",
          table: "asset",
          persistence: "read-only",
          attributes: [{ name: "id", type: "int64", primaryKey: true }],
          inheritance: {
            role: "root",
            strategy: "table-per-hierarchy",
            tag: { column: "kind" },
          },
        },
        {
          name: "Bond",
          inheritance: { role: "concrete-subtype", parent: "Asset", tagValue: "BOND" },
        },
      ],
    });
    expect(family.entity("Asset").mutability).toBe("read-only");
    expect(family.entity("Bond").mutability).toBe("read-only");
  });

  it("surfaces the optimisticLocking version attribute (m-opt-lock metamodel surface)", () => {
    const metamodel = Metamodel.fromDescriptor(loadDescriptor("account.yaml"));
    const account = metamodel.entity("Account");
    const version = account.versionAttribute();
    expect(version?.name).toBe("version");
    expect(version?.optimisticLocking).toBe(true);
  });

  it("derives the temporal optimistic key from the Transaction-Time start column", () => {
    const balance = Metamodel.fromDescriptor(loadDescriptor("balance.yaml")).entity("Balance");
    // A Transaction-Time temporal entity carries no version column; its optimistic key
    // is derived from the Transaction-Time start column (in_z) — the version analogue.
    const inZ = balance.txStartAttribute();
    expect(inZ?.name).toBe("tx_start");
    expect(inZ?.column).toBe("in_z");
    expect(balance.versionAttribute()).toBeUndefined();
    // A non-temporal entity has no Transaction-Time dimension, so no derived key.
    const order = Metamodel.fromDescriptor(loadDescriptor("orders.yaml")).entity("Order");
    expect(order.txStartAttribute()).toBeUndefined();
  });

  it("resolves the Transaction-Time end column, the Latest-milestone marker", () => {
    const balance = Metamodel.fromDescriptor(loadDescriptor("balance.yaml")).entity("Balance");
    // The current milestone is the row whose Transaction-Time end (out_z) is infinity; observed
    // recording filters on it so a closed milestone cannot overwrite the current in_z.
    const outZ = balance.txEndAttribute();
    expect(outZ?.name).toBe("tx_end");
    expect(outZ?.column).toBe("out_z");
    // A non-temporal entity has no Transaction-Time dimension, so no to-attribute.
    const order = Metamodel.fromDescriptor(loadDescriptor("orders.yaml")).entity("Order");
    expect(order.txEndAttribute()).toBeUndefined();
  });

  it("rejects optimisticLocking + asOfAxes on one entity (invalid composition, m-descriptor/m-temporal-read/m-opt-lock)", () => {
    // A temporal entity DERIVES its optimistic key from the Transaction-Time start column, so
    // combining an explicit `optimisticLocking` attribute with `asOfAxes` is invalid.
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
          { name: "txStart", type: "timestamp", column: "in_z" },
          { name: "txEnd", type: "timestamp", column: "out_z" },
        ],
        asOfAxes: [
          {
            dimension: "transactionTime",
            startAttribute: "txStart",
            endAttribute: "txEnd",
          },
        ],
      }),
    ).toThrow(/optimisticLocking|asOfAxes/);
  });

  it("derives the operation-axis view from canonical interval metadata", () => {
    const metamodel = Metamodel.fromDescriptor(loadDescriptor("balance.yaml"));
    const axis = metamodel.entity("Balance").asOfAxis("transactionTime");
    expect(axis.toIsInclusive).toBe(false);
    expect(axis.infinity).toBe("infinity");
    expect(axis.default).toBe("latest");
    expect(axis.dimension).toBe("transactionTime");
  });

  it("surfaces value-object nullability without a mapping discriminator", () => {
    const metamodel = Metamodel.fromDescriptor(loadDescriptor("customer.yaml"));
    const address = metamodel.entity("Customer").findValueObject("address");
    expect(address?.nullable).toBe(true);
    expect(address).not.toHaveProperty("mapping");
  });

  it("normalizes the recursive value-object structure (attributes, nested VOs, multiplicity)", () => {
    const customer = Metamodel.fromDescriptor(loadDescriptor("customer.yaml")).entity("Customer");
    const address = customer.valueObjectByName("address");
    // Top-level `address`: a single document with typed attributes and nested VOs.
    expect(address.multiplicity).toBe("one");
    expect(address.attributes.map((a) => a.name)).toEqual(["street", "city"]);
    expect(address.attributes.every((a) => a.type === "string")).toBe(true);
    expect(address.valueObjects.map((vo) => vo.name)).toEqual(["geo", "phones"]);

    // Nested to-one `geo`: its own typed attributes (elevation nullable) and further nesting.
    const geo = findNestedValueObject(address, "geo");
    expect(geo).toBeDefined();
    if (geo) {
      expect(geo.multiplicity).toBe("one");
      expect(findValueObjectAttribute(geo, "country")?.nullable).toBe(false);
      expect(findValueObjectAttribute(geo, "elevation")).toEqual({
        name: "elevation",
        type: "float64",
        nullable: true,
      });
    }

    // Three-level path resolves through the reader accessor.
    const point = customer.resolveValueObjectPath(["address", "geo", "point"]);
    expect(point?.name).toBe("point");
    expect(point?.multiplicity).toBe("one");
    expect(point?.attributes.map((a) => a.name)).toEqual(["lat", "lon"]);

    // The to-many `phones` member surfaces `many` multiplicity.
    const phones = findNestedValueObject(address, "phones");
    expect(phones?.multiplicity).toBe("many");
    expect(phones?.attributes.map((a) => a.name)).toEqual(["type", "number"]);

    // Unresolved segments / names are reported rather than silently coerced.
    expect(customer.resolveValueObjectPath(["address", "nope"])).toBeUndefined();
    expect(() => customer.valueObjectByName("nope")).toThrow();
  });

  it("defaults value-object multiplicity to one and nullability to false", () => {
    // A value object that omits multiplicity / column / nullable takes the schema
    // defaults (one / non-null); its attributes default non-null too, at
    // every depth.
    const widget = Metamodel.fromDescriptor({
      entity: {
        name: "Widget",
        table: "widget",
        attributes: [{ name: "id", type: "int64", column: "id", primaryKey: true }],
        valueObjects: [
          {
            name: "spec",
            attributes: [{ name: "code", type: "string" }],
            valueObjects: [{ name: "dims", attributes: [{ name: "w", type: "int32" }] }],
          },
        ],
      },
    }).entity("Widget");

    const spec = widget.valueObjectByName("spec");
    expect(spec.multiplicity).toBe("one");
    expect(spec).not.toHaveProperty("mapping");
    expect(spec.nullable).toBe(false);
    expect(findValueObjectAttribute(spec, "code")).toEqual({
      name: "code",
      type: "string",
      nullable: false,
    });

    const dims = widget.resolveValueObjectPath(["spec", "dims"]);
    expect(dims).toBeDefined();
    if (dims) {
      expect(dims.multiplicity).toBe("one");
      expect(dims.nullable).toBe(false);
      expect(findValueObjectAttribute(dims, "w")?.nullable).toBe(false);
    }
  });

  it("deriveTemporal accepts only the active temporal formations", () => {
    expect(deriveTemporal([])).toBe("non-temporal");
    expect(
      deriveTemporal([
        { dimension: "transactionTime", startAttribute: "txStart", endAttribute: "txEnd" },
      ]),
    ).toBe("transaction-time-only");
    expect(() =>
      deriveTemporal([
        { dimension: "validTime", startAttribute: "validStart", endAttribute: "validEnd" },
      ]),
    ).toThrow(/unsupported asOfAxes shape/);
    expect(
      deriveTemporal([
        { dimension: "validTime", startAttribute: "validStart", endAttribute: "validEnd" },
        { dimension: "transactionTime", startAttribute: "txStart", endAttribute: "txEnd" },
      ]),
    ).toBe("bitemporal");
  });

  it("rejects a Valid-Time-Only descriptor at the schema boundary", () => {
    const descriptor = {
      entity: {
        name: "Reservation",
        table: "reservation",
        attributes: [
          { name: "id", type: "int64", primaryKey: true },
          { name: "valid_start", type: "timestamp" },
          { name: "valid_end", type: "timestamp" },
        ],
        asOfAxes: [
          {
            dimension: "validTime",
            startAttribute: "valid_start",
            endAttribute: "valid_end",
          },
        ],
      },
    };

    expect(validateDescriptor(descriptor).valid).toBe(false);
    expect(() => Metamodel.fromDescriptor(descriptor)).toThrow();
  });
});
