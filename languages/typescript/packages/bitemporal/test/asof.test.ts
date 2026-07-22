/**
 * m-temporal-read as-of predicate injection + audit-write DML — in-isolation unit tests.
 *
 * Pins the pure per-axis derivation (`asOfPredicate`), the deep-fetch propagation
 * suffix (`propagatedPredicate`), and the milestone-chaining write DML
 * (`auditWriteStatements`) against the corpus goldens they must reproduce —
 * Docker-free, no metamodel — so a lowering regression fails here before the
 * database run lane. The alias-qualified column expressions and infinity sentinel
 * come from the caller (the m-sql resolver / m-navigate propagation), exactly as they do in
 * production.
 */
import { describe, expect, it } from "vitest";
import {
  asOfPredicate,
  auditWriteStatements,
  propagatedPredicate,
  type ResolvedAxis,
  type WriteTarget,
} from "../src/index.js";

/** The Transaction-Time axis of Balance, qualified `t0`. */
const BALANCE_TRANSACTION_TIME: ResolvedAxis = {
  dimension: "transactionTime",
  startExpr: "t0.in_z",
  endExpr: "t0.out_z",
  toIsInclusive: false,
  infinity: "infinity",
};

/** The Transaction-Time axis of the inclusive-bound Ledger model, qualified `t0`. */
const LEDGER_TRANSACTION_TIME: ResolvedAxis = {
  dimension: "transactionTime",
  startExpr: "t0.in_z",
  endExpr: "t0.out_z",
  toIsInclusive: true,
  infinity: "infinity",
};

/** The Valid-Time and Transaction-Time axes of Position, qualified `t0`. */
const POSITION_VALID_TIME: ResolvedAxis = {
  dimension: "validTime",
  startExpr: "t0.from_z",
  endExpr: "t0.thru_z",
  toIsInclusive: false,
  infinity: "infinity",
};
const POSITION_TRANSACTION_TIME: ResolvedAxis = {
  dimension: "transactionTime",
  startExpr: "t0.in_z",
  endExpr: "t0.out_z",
  toIsInclusive: false,
  infinity: "infinity",
};
const POSITION_AXES = [POSITION_VALID_TIME, POSITION_TRANSACTION_TIME] as const;

const D1 = "2024-03-01T00:00:00+00:00";
const D2 = "2024-02-01T00:00:00+00:00";

describe("asOfPredicate — single-axis (audit-only)", () => {
  it("m-temporal-read-001 defaulted-Latest injects `out_z = ?` [infinity]", () => {
    const p = asOfPredicate([BALANCE_TRANSACTION_TIME], {});
    expect(p.sql).toBe("t0.out_z = ?");
    expect(p.binds).toEqual(["infinity"]);
  });

  it("m-temporal-read-002 explicit Latest lowers to the identical open-row equality", () => {
    const p = asOfPredicate([BALANCE_TRANSACTION_TIME], {
      transactionTime: { kind: "latest" },
    });
    expect(p.sql).toBe("t0.out_z = ?");
    expect(p.binds).toEqual(["infinity"]);
  });

  it("m-temporal-read-003 past instant injects the half-open containment `in_z <= ? and out_z > ?` [d,d]", () => {
    const p = asOfPredicate([BALANCE_TRANSACTION_TIME], {
      transactionTime: { kind: "instant", coordinate: "2024-04-01T00:00:00+00:00" },
    });
    expect(p.sql).toBe("t0.in_z <= ? and t0.out_z > ?");
    expect(p.binds).toEqual(["2024-04-01T00:00:00+00:00", "2024-04-01T00:00:00+00:00"]);
  });

  it("m-temporal-read-008 inclusive upper bound injects `out_z >= ?` (not `>`)", () => {
    const p = asOfPredicate([LEDGER_TRANSACTION_TIME], {
      transactionTime: { kind: "instant", coordinate: "2024-06-01T00:00:00+00:00" },
    });
    expect(p.sql).toBe("t0.in_z <= ? and t0.out_z >= ?");
  });

  it("m-temporal-read-006 asOfRange injects the overlap `in_z < ? and out_z > ?` [to, from]", () => {
    const p = asOfPredicate([BALANCE_TRANSACTION_TIME], {
      transactionTime: {
        kind: "range",
        start: "2024-06-15T00:00:00+00:00",
        end: "2024-07-01T00:00:00+00:00",
      },
    });
    expect(p.sql).toBe("t0.in_z < ? and t0.out_z > ?");
    expect(p.binds).toEqual(["2024-07-01T00:00:00+00:00", "2024-06-15T00:00:00+00:00"]);
  });

  it("m-temporal-read-004 history injects no predicate for the axis", () => {
    const p = asOfPredicate([BALANCE_TRANSACTION_TIME], {
      transactionTime: { kind: "history" },
    });
    expect(p.sql).toBe("");
    expect(p.binds).toEqual([]);
  });
});

describe("asOfPredicate — Bitemporal (Valid-Time-first composition)", () => {
  it("m-temporal-read-013 both dimensions Latest", () => {
    const p = asOfPredicate(POSITION_AXES, {
      validTime: { kind: "latest" },
      transactionTime: { kind: "latest" },
    });
    expect(p.sql).toBe("t0.thru_z = ? and t0.out_z = ?");
    expect(p.binds).toEqual(["infinity", "infinity"]);
  });

  it("m-temporal-read-014 Valid-Time past / Transaction-Time Latest", () => {
    const p = asOfPredicate(POSITION_AXES, {
      validTime: { kind: "instant", coordinate: D1 },
      transactionTime: { kind: "latest" },
    });
    expect(p.sql).toBe("t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?");
    expect(p.binds).toEqual([D1, D1, "infinity"]);
  });

  it("m-temporal-read-015 finite pins bind Valid Time before Transaction Time", () => {
    const p = asOfPredicate(POSITION_AXES, {
      validTime: { kind: "instant", coordinate: D1 },
      transactionTime: { kind: "instant", coordinate: D2 },
    });
    expect(p.sql).toBe("t0.from_z <= ? and t0.thru_z > ? and t0.in_z <= ? and t0.out_z > ?");
    expect(p.binds).toEqual([D1, D1, D2, D2]);
  });

  it("m-temporal-read-017 omitted Transaction Time defaults to Latest", () => {
    const p = asOfPredicate(POSITION_AXES, {
      validTime: { kind: "instant", coordinate: D1 },
    });
    expect(p.sql).toBe("t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?");
    expect(p.binds).toEqual([D1, D1, "infinity"]);
  });

  it("m-temporal-read-016 double-history injects nothing on either axis", () => {
    const p = asOfPredicate(POSITION_AXES, {
      validTime: { kind: "history" },
      transactionTime: { kind: "history" },
    });
    expect(p.sql).toBe("");
    expect(p.binds).toEqual([]);
  });

  it("a non-temporal entity (no axes) yields an empty predicate", () => {
    const p = asOfPredicate([], {});
    expect(p.sql).toBe("");
    expect(p.binds).toEqual([]);
  });
});

describe("propagatedPredicate — deep-fetch suffix (Valid-Time-first)", () => {
  it("m-navigate-012 both-latest → child `thru_z = ? and out_z = ?` [infinity, infinity]", () => {
    const p = propagatedPredicate(POSITION_AXES, {
      validTime: { kind: "latest" },
      transactionTime: { kind: "latest" },
    });
    expect(p.sql).toBe("t0.thru_z = ? and t0.out_z = ?");
    expect(p.binds).toEqual(["infinity", "infinity"]);
  });

  it("m-navigate-014 Valid-Time Latest / Transaction-Time finite", () => {
    const p = propagatedPredicate(POSITION_AXES, {
      validTime: { kind: "latest" },
      transactionTime: { kind: "instant", coordinate: D2 },
    });
    expect(p.sql).toBe("t0.thru_z = ? and t0.in_z <= ? and t0.out_z > ?");
    expect(p.binds).toEqual(["infinity", D2, D2]);
  });

  it("m-navigate-021 non-temporal root defaults temporal child to Latest", () => {
    const p = propagatedPredicate([BALANCE_TRANSACTION_TIME], {});
    expect(p.sql).toBe("t0.out_z = ?");
    expect(p.binds).toEqual(["infinity"]);
  });

  it("m-navigate-022 non-temporal child → NO as-of term (empty)", () => {
    const p = propagatedPredicate([], { transactionTime: { kind: "latest" } });
    expect(p.sql).toBe("");
    expect(p.binds).toEqual([]);
  });

  it("the suffix is never reordered (Valid Time stays first)", () => {
    const p = propagatedPredicate([POSITION_TRANSACTION_TIME, POSITION_VALID_TIME], {
      validTime: { kind: "latest" },
      transactionTime: { kind: "latest" },
    });
    expect(p.sql).toBe("t0.thru_z = ? and t0.out_z = ?");
  });
});

describe("auditWriteStatements — milestone-chaining DML (audit-only)", () => {
  const BALANCE: WriteTarget = {
    table: "balance",
    columns: ["bal_id", "acct_num", "val", "in_z", "out_z"],
    pkColumn: "bal_id",
    txEndColumn: "out_z",
  };
  const EVENT: WriteTarget = {
    table: "event",
    columns: ["id", "occurred_at"],
    pkColumn: "id",
  };

  it("m-audit-write-001 insert opens one current milestone row (1 statement)", () => {
    expect(auditWriteStatements("insert", BALANCE)).toEqual([
      "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
    ]);
  });

  it("m-audit-write-002 update closes the current row (keyed pk AND out_z), then chains a new row (2)", () => {
    expect(auditWriteStatements("update", BALANCE)).toEqual([
      "update balance set out_z = ? where bal_id = ? and out_z = ?",
      "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
    ]);
  });

  it("m-audit-write-003 terminate closes the current row only — inserts nothing (1)", () => {
    expect(auditWriteStatements("terminate", BALANCE)).toEqual([
      "update balance set out_z = ? where bal_id = ? and out_z = ?",
    ]);
  });

  it("m-core-002/m-core-003 non-temporal insert lowers to a plain single-row insert", () => {
    expect(auditWriteStatements("insert", EVENT)).toEqual([
      "insert into event(id, occurred_at) values (?, ?)",
    ]);
  });

  it("a close on a non-temporal entity fails loudly (no out_z axis)", () => {
    expect(() => auditWriteStatements("terminate", EVENT)).toThrow(/non-temporal/);
  });
});

describe("auditWriteStatements — full-bitemporal rectangle-split DML (m-bitemp-write)", () => {
  // The Bitemporal Position target carries both temporal dimensions.
  const POSITION: WriteTarget = {
    table: "position",
    columns: ["pos_id", "acct_num", "val", "from_z", "thru_z", "in_z", "out_z"],
    pkColumn: "pos_id",
    txEndColumn: "out_z",
    txStartColumn: "in_z",
    validStartColumn: "from_z",
  };
  const INSERT =
    "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) values (?, ?, ?, ?, ?, ?, ?)";
  const PLAIN_CLOSE = "update position set out_z = ? where pos_id = ? and out_z = ?";

  it("m-bitemp-write-003 insertUntil opens one Valid-Time-bounded milestone", () => {
    expect(auditWriteStatements("insertUntil", POSITION)).toEqual([INSERT]);
  });

  it("m-bitemp-write-001 updateUntil is inactivate + head/middle/tail (4 statements)", () => {
    expect(auditWriteStatements("updateUntil", POSITION)).toEqual([
      PLAIN_CLOSE,
      INSERT,
      INSERT,
      INSERT,
    ]);
  });

  it("m-bitemp-write-002 terminateUntil is inactivate + head/tail, no middle (3 statements)", () => {
    expect(auditWriteStatements("terminateUntil", POSITION)).toEqual([PLAIN_CLOSE, INSERT, INSERT]);
  });

  it("m-bitemp-write-008 gated close adds the Valid-Time discriminator", () => {
    // The optimistic gated close targets exactly the observed rectangle: the Valid-Time
    // discriminator `from_z` slots between the `out_z` and `in_z` gates.
    const [gatedClose] = auditWriteStatements("terminate", POSITION, { gated: true });
    expect(gatedClose).toBe(
      "update position set out_z = ? where pos_id = ? and out_z = ? and from_z = ? and in_z = ?",
    );
  });

  it("a Transaction-Time-Only gated close omits the Valid-Time discriminator", () => {
    const AUDIT_GATED: WriteTarget = {
      table: "balance",
      columns: ["bal_id", "acct_num", "val", "in_z", "out_z"],
      pkColumn: "bal_id",
      txEndColumn: "out_z",
      txStartColumn: "in_z",
    };
    const [gatedClose] = auditWriteStatements("terminate", AUDIT_GATED, { gated: true });
    expect(gatedClose).toBe(
      "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?",
    );
  });

  it("a QUOTED table INSERT canonically spaces the column list (m-sql spacing)", () => {
    // A reserved table name is quoted by the dialect seam (MariaDB backtick, Postgres
    // double-quote). The m-sql normalizer renders such a quoted table with a space before
    // its INSERT column list (an IDENTIFIER token), unlike a bare name (a function-call
    // VAR, tight). The builder follows suit so `emitted === golden` on the quoted-table lane
    // — for BOTH quote characters, since spacing keys on quoting, not the specific char.
    const MARIADB_POSITION: WriteTarget = { ...POSITION, table: "`position`" };
    expect(auditWriteStatements("insert", MARIADB_POSITION)).toEqual([
      "insert into `position` (pos_id, acct_num, val, from_z, thru_z, in_z, out_z) values (?, ?, ?, ?, ?, ?, ?)",
    ]);

    const POSTGRES_QUOTED: WriteTarget = {
      table: '"order"',
      columns: ["id", "label"],
      pkColumn: "id",
    };
    expect(auditWriteStatements("insert", POSTGRES_QUOTED)).toEqual([
      'insert into "order" (id, label) values (?, ?)',
    ]);
  });
});
