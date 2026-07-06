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

/** The processing axis of the audit-only Balance model, qualified `t0`. */
const BALANCE_PROCESSING: ResolvedAxis = {
  axis: "processing",
  fromExpr: "t0.in_z",
  toExpr: "t0.out_z",
  toIsInclusive: false,
  infinity: "infinity",
};

/** The processing axis of the INCLUSIVE-bound Ledger model, qualified `t0`. */
const LEDGER_PROCESSING: ResolvedAxis = {
  axis: "processing",
  fromExpr: "t0.in_z",
  toExpr: "t0.out_z",
  toIsInclusive: true,
  infinity: "infinity",
};

/** The business + processing axes of the bitemporal Position model, qualified `t0`. */
const POSITION_BUSINESS: ResolvedAxis = {
  axis: "business",
  fromExpr: "t0.from_z",
  toExpr: "t0.thru_z",
  toIsInclusive: false,
  infinity: "infinity",
};
const POSITION_PROCESSING: ResolvedAxis = {
  axis: "processing",
  fromExpr: "t0.in_z",
  toExpr: "t0.out_z",
  toIsInclusive: false,
  infinity: "infinity",
};
const POSITION_AXES = [POSITION_BUSINESS, POSITION_PROCESSING] as const;

const D1 = "2024-03-01T00:00:00+00:00";
const D2 = "2024-02-01T00:00:00+00:00";

describe("asOfPredicate — single-axis (audit-only)", () => {
  it("m-temporal-read-001 defaulted-now injects the current-row equality `out_z = ?` [infinity]", () => {
    const p = asOfPredicate([BALANCE_PROCESSING], {});
    expect(p.sql).toBe("t0.out_z = ?");
    expect(p.binds).toEqual(["infinity"]);
  });

  it("m-temporal-read-002 explicit now lowers to the identical current-row equality", () => {
    const p = asOfPredicate([BALANCE_PROCESSING], { processing: { kind: "now" } });
    expect(p.sql).toBe("t0.out_z = ?");
    expect(p.binds).toEqual(["infinity"]);
  });

  it("m-temporal-read-003 past instant injects the half-open containment `in_z <= ? and out_z > ?` [d,d]", () => {
    const p = asOfPredicate([BALANCE_PROCESSING], {
      processing: { kind: "instant", date: "2024-04-01T00:00:00+00:00" },
    });
    expect(p.sql).toBe("t0.in_z <= ? and t0.out_z > ?");
    expect(p.binds).toEqual(["2024-04-01T00:00:00+00:00", "2024-04-01T00:00:00+00:00"]);
  });

  it("m-temporal-read-008 inclusive upper bound injects `out_z >= ?` (not `>`)", () => {
    const p = asOfPredicate([LEDGER_PROCESSING], {
      processing: { kind: "instant", date: "2024-06-01T00:00:00+00:00" },
    });
    expect(p.sql).toBe("t0.in_z <= ? and t0.out_z >= ?");
  });

  it("m-temporal-read-006 asOfRange injects the overlap `in_z < ? and out_z > ?` [to, from]", () => {
    const p = asOfPredicate([BALANCE_PROCESSING], {
      processing: {
        kind: "range",
        from: "2024-06-15T00:00:00+00:00",
        to: "2024-07-01T00:00:00+00:00",
      },
    });
    expect(p.sql).toBe("t0.in_z < ? and t0.out_z > ?");
    expect(p.binds).toEqual(["2024-07-01T00:00:00+00:00", "2024-06-15T00:00:00+00:00"]);
  });

  it("m-temporal-read-004 history injects no predicate for the axis", () => {
    const p = asOfPredicate([BALANCE_PROCESSING], { processing: { kind: "history" } });
    expect(p.sql).toBe("");
    expect(p.binds).toEqual([]);
  });
});

describe("asOfPredicate — bitemporal (both axes, business-first composition)", () => {
  it("m-temporal-read-013 both-axes-now composes `thru_z = ? and out_z = ?` [infinity, infinity]", () => {
    const p = asOfPredicate(POSITION_AXES, {
      business: { kind: "now" },
      processing: { kind: "now" },
    });
    expect(p.sql).toBe("t0.thru_z = ? and t0.out_z = ?");
    expect(p.binds).toEqual(["infinity", "infinity"]);
  });

  it("m-temporal-read-014 business-past / processing-now — business range first, then processing eq", () => {
    const p = asOfPredicate(POSITION_AXES, {
      business: { kind: "instant", date: D1 },
      processing: { kind: "now" },
    });
    expect(p.sql).toBe("t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?");
    expect(p.binds).toEqual([D1, D1, "infinity"]);
  });

  it("m-temporal-read-015 both-axes-past — business binds first, then processing (each [d,d])", () => {
    const p = asOfPredicate(POSITION_AXES, {
      business: { kind: "instant", date: D1 },
      processing: { kind: "instant", date: D2 },
    });
    expect(p.sql).toBe("t0.from_z <= ? and t0.thru_z > ? and t0.in_z <= ? and t0.out_z > ?");
    expect(p.binds).toEqual([D1, D1, D2, D2]);
  });

  it("m-temporal-read-017 business-past / processing OMITTED defaults processing to now", () => {
    const p = asOfPredicate(POSITION_AXES, { business: { kind: "instant", date: D1 } });
    expect(p.sql).toBe("t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?");
    expect(p.binds).toEqual([D1, D1, "infinity"]);
  });

  it("m-temporal-read-016 double-history injects nothing on either axis", () => {
    const p = asOfPredicate(POSITION_AXES, {
      business: { kind: "history" },
      processing: { kind: "history" },
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

describe("propagatedPredicate — deep-fetch as-of suffix (business-first, ordered)", () => {
  it("m-navigate-012 both-latest → child `thru_z = ? and out_z = ?` [infinity, infinity]", () => {
    const p = propagatedPredicate(POSITION_AXES, {
      business: { kind: "now" },
      processing: { kind: "now" },
    });
    expect(p.sql).toBe("t0.thru_z = ? and t0.out_z = ?");
    expect(p.binds).toEqual(["infinity", "infinity"]);
  });

  it("m-navigate-014 business-latest / processing-past → `thru_z = ? and in_z <= ? and out_z > ?`", () => {
    const p = propagatedPredicate(POSITION_AXES, {
      business: { kind: "now" },
      processing: { kind: "instant", date: D2 },
    });
    expect(p.sql).toBe("t0.thru_z = ? and t0.in_z <= ? and t0.out_z > ?");
    expect(p.binds).toEqual(["infinity", D2, D2]);
  });

  it("m-navigate-021 non-temporal root (no pins) → temporal child defaults every axis to now", () => {
    const p = propagatedPredicate([BALANCE_PROCESSING], {});
    expect(p.sql).toBe("t0.out_z = ?");
    expect(p.binds).toEqual(["infinity"]);
  });

  it("m-navigate-022 non-temporal child → NO as-of term (empty)", () => {
    const p = propagatedPredicate([], { processing: { kind: "now" } });
    expect(p.sql).toBe("");
    expect(p.binds).toEqual([]);
  });

  it("the suffix is NEVER reordered (business stays before processing)", () => {
    // Pass axes in processing-first order; the derivation still emits business first.
    const p = propagatedPredicate([POSITION_PROCESSING, POSITION_BUSINESS], {
      business: { kind: "now" },
      processing: { kind: "now" },
    });
    expect(p.sql).toBe("t0.thru_z = ? and t0.out_z = ?");
  });
});

describe("auditWriteStatements — milestone-chaining DML (audit-only)", () => {
  const BALANCE: WriteTarget = {
    table: "balance",
    columns: ["bal_id", "acct_num", "val", "in_z", "out_z"],
    pkColumn: "bal_id",
    toColumn: "out_z",
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
