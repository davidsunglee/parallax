/**
 * Shared M12 provider contract suite for composition-root database providers.
 *
 * Providers are selected through the same registry as the API Conformance Suite
 * (`PARALLAX_DATABASES`, default Postgres). The dedicated just lane selects both
 * Postgres and MariaDB.
 */
import type { Dialect } from "@parallax/dialect";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import type { ApiConformanceProvider } from "./api-conformance/_harness.js";
import { HAS_DOCKER, selectedProviders } from "./api-conformance/_providers.js";

const BOOT_TIMEOUT = 600_000;

for (const selected of selectedProviders()) {
  group.skipIf(!HAS_DOCKER)(`${selected.dialect} provider contract (${selected.label})`, () => {
    let provider: ApiConformanceProvider | undefined;

    beforeAll(async () => {
      provider = await selected.start();
    }, BOOT_TIMEOUT);

    afterAll(async () => {
      await provider?.close();
    });

    it(
      "provisions, loads fixtures, executes DML, rolls back DML, and exposes a peer",
      async () => {
        const dbp = mustProvider(provider);
        const dialect = dbp.dialectImpl;
        const ddl = contractDdl(dialect);

        await dbp.reset();
        await dbp.applyDdl([ddl]);
        await dbp.loadFixtures(
          "provider_contract",
          ["id", "note", "payload"],
          [[1, "fixture", new Uint8Array([0xde, 0xad, 0xbe, 0xef])]],
        );

        await expect(
          dbp.query("select t0.id, t0.note, t0.payload from provider_contract t0", []),
        ).resolves.toEqual([{ id: "1", note: "fixture", payload: "deadbeef" }]);

        await expect(
          dbp.exec("update provider_contract set note = ? where id = ?", ["updated", 1]),
        ).resolves.toBe(1);
        await expect(
          dbp.exec("update provider_contract set note = ? where id = ?", ["missing", 99]),
        ).resolves.toBe(0);
        await expect(
          dbp.query("select t0.note from provider_contract t0 where t0.id = ?", [1]),
        ).resolves.toEqual([{ note: "updated" }]);

        await expect(
          dbp.execRolledBack("update provider_contract set note = ? where id = ?", [
            "rolled-back",
            1,
          ]),
        ).resolves.toBe(1);
        await expect(
          dbp.query("select t0.note from provider_contract t0 where t0.id = ?", [1]),
        ).resolves.toEqual([{ note: "updated" }]);

        await dbp.peer.executeWrite(
          "insert into provider_contract (id, note, payload) values (?, ?, ?)",
          [2, "peer", dialect.bindValue("bytes", new Uint8Array([0xca, 0xfe]))],
        );
        await expect(
          dbp.query("select t0.note, t0.payload from provider_contract t0 where t0.id = ?", [2]),
        ).resolves.toEqual([{ note: "peer", payload: "cafe" }]);

        await dbp.reset();
        await dbp.applyDdl([ddl]);
        await expect(
          dbp.query("select t0.id, t0.note from provider_contract t0", []),
        ).resolves.toEqual([]);
      },
      BOOT_TIMEOUT,
    );
  });
}

function mustProvider(provider: ApiConformanceProvider | undefined): ApiConformanceProvider {
  if (provider === undefined) {
    throw new Error("provider was not started");
  }
  return provider;
}

function contractDdl(dialect: Dialect): string {
  const q = (name: string) => dialect.quoteIdentifier(name);
  return (
    `create table ${q("provider_contract")} (` +
    `${q("id")} ${dialect.columnType("int64")} primary key, ` +
    `${q("note")} ${dialect.columnType("string")}, ` +
    `${q("payload")} ${dialect.columnType("bytes")})`
  );
}
