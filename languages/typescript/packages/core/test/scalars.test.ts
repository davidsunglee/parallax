import { expect, describe as group, it } from "vitest";
import { bytesFromHex, bytesToHex, ParallaxDecimal, toWire } from "../src/scalars.js";

group("ParallaxDecimal.from input rules (spec §2.2.1: reject number)", () => {
  it("accepts an exact decimal string and preserves scale digits", () => {
    // The canonical wire form is a string; trailing-zero scale is preserved.
    expect(ParallaxDecimal.from("5.00").toString()).toBe("5");
    expect(ParallaxDecimal.from("5.00").toFixedString(2)).toBe("5.00");
    expect(ParallaxDecimal.from("19.99").toString()).toBe("19.99");
  });

  it("accepts an exact bigint losslessly (no float boundary)", () => {
    expect(ParallaxDecimal.from(20n).toFixedString(2)).toBe("20.00");
  });

  it("is idempotent on an existing ParallaxDecimal", () => {
    const d = ParallaxDecimal.from("3.14");
    expect(ParallaxDecimal.from(d)).toBe(d);
  });

  it("rejects a whole-valued JS number (the precision-drift boundary)", () => {
    // The spec says reject `number` input for decimal — even an integer number
    // is a binary float, so the seam refuses every JS number.
    expect(() => ParallaxDecimal.from(5 as unknown as string)).toThrow(TypeError);
  });

  it("rejects a fractional JS number", () => {
    expect(() => ParallaxDecimal.from(5.01 as unknown as string)).toThrow(TypeError);
  });

  it("compares in decimal space, scale-insensitively", () => {
    // "5" and "5.00" are the same number; the corpus authors decimals as
    // numbers and the grader compares scale-insensitively in Decimal space.
    expect(ParallaxDecimal.from("5").equals(ParallaxDecimal.from("5.00"))).toBe(true);
    expect(ParallaxDecimal.from("19.99").compare(ParallaxDecimal.from("20.00"))).toBe(-1);
  });
});

group("bytesFromHex strict per-chunk validation", () => {
  it("round-trips lowercase hex", () => {
    const bytes = bytesFromHex("deadbeef");
    expect(bytesToHex(bytes)).toBe("deadbeef");
  });

  it("accepts a leading \\x prefix", () => {
    expect(Array.from(bytesFromHex("\\x00ff"))).toEqual([0x00, 0xff]);
  });

  it("throws on a fully non-hex chunk ('zz' would silently store 0)", () => {
    expect(() => bytesFromHex("zz")).toThrow(RangeError);
  });

  it("throws on a partially-valid chunk ('0g' would silently store 0)", () => {
    // Number.parseInt('0g', 16) === 0 stops at the first invalid char; strict
    // validation must reject it rather than round-trip a wrong byte.
    expect(() => bytesFromHex("0g")).toThrow(RangeError);
  });

  it("throws on an odd-length string", () => {
    expect(() => bytesFromHex("abc")).toThrow(RangeError);
  });
});

group("toWire renders the canonical scalar wire forms", () => {
  it("serializes int64 (bigint) and decimal as strings", () => {
    expect(toWire(9_007_199_254_740_993n)).toBe("9007199254740993");
    expect(toWire(ParallaxDecimal.from("19.99"))).toBe("19.99");
  });

  it("recurses into containers", () => {
    expect(toWire({ b: 2n, a: [1, ParallaxDecimal.from("3.5")] })).toEqual({
      b: "2",
      a: [1, "3.5"],
    });
  });
});
