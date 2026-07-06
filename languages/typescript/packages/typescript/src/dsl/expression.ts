/**
 * The fluent query DSL expression surface (spec §2.5–§2.7).
 *
 * This is the **entity-agnostic runtime** the generated entity symbols hang off
 * (`codegen/`): an `AttributeExpression` knows only its qualified metamodel ref
 * (`"Order.id"`) and produces canonical m-op-algebra {@link Operation} data — the identical
 * wire form the m-sql compiler already consumes, so the DSL and the conformance
 * adapter share one canonical form (design Q1 Option B, Q3 discriminated-union).
 *
 * Nothing here reaches into a database or the compiler: an expression is a pure
 * builder of operation data. `find(...)` ({@link ./find.ts}) serializes a
 * predicate + read options into the case `operation` tree, and the generic
 * runtime lowers it. Serialization matches the corpus byte-for-byte:
 * `Predicate.toOperation()` equals the case's `operation` for representative
 * cases (`dsl.test.ts`).
 */
import type {
  AttributeRef,
  Comparison,
  Literal,
  Operation,
  OrderKey,
  RelationshipRef,
  StringMatch,
} from "@parallax/operation";

/** Options accepted by the string predicates (`{ caseInsensitive: true }`). */
export interface StringPredicateOptions {
  readonly caseInsensitive?: boolean;
}

/**
 * A predicate expression — a thin, immutable wrapper over one canonical
 * {@link Operation} node, exposing the boolean combinators (`and` / `or` / `not`
 * / `group`) that serialize to the m-op-algebra boolean junctions. Boolean chaining is
 * left-associative; explicit precedence is postfix `.group()` (spec §2.5).
 */
export class Predicate {
  constructor(private readonly node: Operation) {}

  /** The canonical operation this predicate serializes to (the wire form). */
  toOperation(): Operation {
    return this.node;
  }

  /**
   * Left-associative conjunction. `a.and(b).and(c)` flattens to a single
   * three-operand `and`, matching the corpus's flattened junction encoding
   * (`m-op-algebra-031`); nesting is introduced only by an explicit `.group()`.
   */
  and(...others: readonly Predicate[]): Predicate {
    return new Predicate(junction("and", this, others));
  }

  /** Left-associative disjunction (mirrors {@link and}). */
  or(...others: readonly Predicate[]): Predicate {
    return new Predicate(junction("or", this, others));
  }

  /** Postfix negation → the canonical `not` wrapper. */
  not(): Predicate {
    return new Predicate({ not: { operand: this.node } });
  }

  /** Postfix precedence marker → the canonical `group` wrapper (spec §2.5). */
  group(): Predicate {
    return new Predicate({ group: { operand: this.node } });
  }
}

/**
 * Build a boolean junction (`and` / `or`), flattening a same-tag left operand so
 * `a.and(b).and(c)` yields one `{ and: { operands: [a, b, c] } }` rather than a
 * nested tree. A `group()`-wrapped operand keeps its wrapper (that is the point
 * of `group`), so only a bare same-tag junction is flattened.
 */
function junction(tag: "and" | "or", left: Predicate, others: readonly Predicate[]): Operation {
  const leftOp = left.toOperation();
  const head = sameTagOperands(tag, leftOp) ?? [leftOp];
  const operands = [...head, ...others.map((p) => p.toOperation())];
  return tag === "and" ? { and: { operands } } : { or: { operands } };
}

/** The operands of a bare same-tag junction node, or `undefined` when it is not one. */
function sameTagOperands(tag: "and" | "or", op: Operation): readonly Operation[] | undefined {
  if (tag === "and" && "and" in op) {
    return op.and.operands;
  }
  if (tag === "or" && "or" in op) {
    return op.or.operands;
  }
  return undefined;
}

/** A sort key expression (`Order.qty.desc()`) — a query expression, not a JS comparator. */
export class OrderKeyExpression {
  constructor(readonly key: OrderKey) {}
}

/**
 * A typed attribute reference (`Order.id`). Every predicate method serializes to
 * the matching single-key m-op-algebra node with `attr` set to this ref; the value is
 * carried as a bind by the compiler, so the literal passes straight through
 * (`m-op-algebra-002`: `Order.id.eq(42)` → `{ eq: { attr: "Order.id", value: 42 } }`).
 */
export class AttributeExpression {
  constructor(readonly ref: AttributeRef) {}

  private cmp(tag: keyof ComparisonTags, value: Literal): Predicate {
    const body: Comparison = { attr: this.ref, value };
    return new Predicate({ [tag]: body } as unknown as Operation);
  }

  /** `= ?` (`m-op-algebra-002`). `eq(null)` is rejected in favor of {@link isNull} (spec §2.5). */
  eq(value: Exclude<Literal, null>): Predicate {
    return this.cmp("eq", value);
  }

  /** `<> ?` (`m-op-algebra-003`). `notEq(null)` is rejected in favor of {@link isNotNull}. */
  notEq(value: Exclude<Literal, null>): Predicate {
    return this.cmp("notEq", value);
  }

  /** `> ?` (`m-op-algebra-004`). */
  gt(value: Exclude<Literal, null>): Predicate {
    return this.cmp("greaterThan", value);
  }

  /** `>= ?` (`m-op-algebra-005`). */
  gte(value: Exclude<Literal, null>): Predicate {
    return this.cmp("greaterThanEquals", value);
  }

  /** `< ?` (`m-op-algebra-006`). */
  lt(value: Exclude<Literal, null>): Predicate {
    return this.cmp("lessThan", value);
  }

  /** `<= ?` (`m-op-algebra-007`). */
  lte(value: Exclude<Literal, null>): Predicate {
    return this.cmp("lessThanEquals", value);
  }

  /** `between ? and ?` (`m-op-algebra-008`), lower → upper. */
  between(lower: Exclude<Literal, null>, upper: Exclude<Literal, null>): Predicate {
    return new Predicate({ between: { attr: this.ref, lower, upper } });
  }

  /** `is null` (`m-op-algebra-009`). */
  isNull(): Predicate {
    return new Predicate({ isNull: { attr: this.ref } });
  }

  /** `is not null` (`m-op-algebra-010`). */
  isNotNull(): Predicate {
    return new Predicate({ isNotNull: { attr: this.ref } });
  }

  /** `like ?` (`m-op-algebra-011` / `m-op-algebra-016` case-insensitive). */
  like(value: string, options?: StringPredicateOptions): Predicate {
    return this.stringMatch("like", value, options);
  }

  /** `not like ?` (`m-op-algebra-012`). */
  notLike(value: string, options?: StringPredicateOptions): Predicate {
    return this.stringMatch("notLike", value, options);
  }

  /** Prefix match (`m-op-algebra-013` / `m-op-algebra-033` escape). */
  startsWith(value: string, options?: StringPredicateOptions): Predicate {
    return this.stringMatch("startsWith", value, options);
  }

  /** Suffix match (`m-op-algebra-014`). */
  endsWith(value: string, options?: StringPredicateOptions): Predicate {
    return this.stringMatch("endsWith", value, options);
  }

  /** Substring match (`m-op-algebra-015` escape). */
  contains(value: string, options?: StringPredicateOptions): Predicate {
    return this.stringMatch("contains", value, options);
  }

  /**
   * `in (?, …)` (`m-op-algebra-018`). Empty membership normalizes before serialization:
   * `in([])` → `none` (spec §2.5).
   */
  in(values: readonly Exclude<Literal, null>[]): Predicate {
    if (values.length === 0) {
      return new Predicate({ none: {} });
    }
    return new Predicate({ in: { attr: this.ref, values } });
  }

  /** `not in (?, …)` (`m-op-algebra-019`). Empty membership → `all` (spec §2.5). */
  notIn(values: readonly Exclude<Literal, null>[]): Predicate {
    if (values.length === 0) {
      return new Predicate({ all: {} });
    }
    return new Predicate({ notIn: { attr: this.ref, values } });
  }

  /**
   * A named write assignment (`Balance.value.set(150)`), spec §4. The write DSL is
   * explicit assignment arrays (not partial objects); the runtime's write surface
   * consumes `{ attr, value }`. The `attr` is the DSL attribute NAME (the part
   * after the class), which the runtime resolves to a physical column.
   */
  set(value: unknown): { readonly attr: string; readonly value: unknown } {
    const dot = this.ref.indexOf(".");
    return { attr: dot === -1 ? this.ref : this.ref.slice(dot + 1), value };
  }

  /** Ascending sort key (`orderBy` option). */
  asc(): OrderKeyExpression {
    return new OrderKeyExpression({ attr: this.ref, direction: "asc" });
  }

  /** Descending sort key (`orderBy` option, `m-op-algebra-026`). */
  desc(): OrderKeyExpression {
    return new OrderKeyExpression({ attr: this.ref, direction: "desc" });
  }

  private stringMatch(
    tag: keyof StringTags,
    value: string,
    options: StringPredicateOptions | undefined,
  ): Predicate {
    const body: StringMatch = {
      attr: this.ref,
      value,
      ...(options?.caseInsensitive ? { caseInsensitive: true } : {}),
    };
    return new Predicate({ [tag]: body } as unknown as Operation);
  }
}

/** Helper: the comparison node tags an {@link AttributeExpression} produces. */
type ComparisonTags = {
  eq: unknown;
  notEq: unknown;
  greaterThan: unknown;
  greaterThanEquals: unknown;
  lessThan: unknown;
  lessThanEquals: unknown;
};

/** Helper: the string-match node tags an {@link AttributeExpression} produces. */
type StringTags = {
  like: unknown;
  notLike: unknown;
  startsWith: unknown;
  endsWith: unknown;
  contains: unknown;
};

/**
 * A to-many relationship reference (`Order.items`). To-many relationships
 * require an explicit quantifier (spec §2.6): `exists` / `notExists`, optionally
 * filtered by an inner predicate over the child entity (`m-navigate-008` multi-hop).
 */
export class ToManyRelationshipExpression {
  constructor(readonly ref: RelationshipRef) {}

  /** `exists (select 1 …)` — optionally filtered by an inner child predicate. */
  exists(inner?: Predicate): Predicate {
    return new Predicate({
      exists: { rel: this.ref, ...(inner ? { op: inner.toOperation() } : {}) },
    });
  }

  /** `not exists (select 1 …)` (`m-navigate-003`). */
  notExists(inner?: Predicate): Predicate {
    return new Predicate({
      notExists: { rel: this.ref, ...(inner ? { op: inner.toOperation() } : {}) },
    });
  }

  /**
   * Navigate the relationship, filtering the root by an inner predicate over the
   * related entity (`m-navigate-001` `Order.items.navigate(OrderItem.sku.eq("A-100"))`). A
   * `navigate` lowers to the same correlated-EXISTS semi-join as `exists`, but is a
   * distinct algebra node that always carries an inner predicate (spec §2.6). Used
   * for both to-many and to-one navigations (`m-navigate-007` / `m-navigate-011`).
   */
  navigate(inner: Predicate): Predicate {
    return new Predicate({ navigate: { rel: this.ref, op: inner.toOperation() } });
  }
}

/**
 * A navigation path used by the eager-fetch `includes` / `deepFetch` option — an
 * ordered list of relationship refs (`[Order.items, OrderItem.statuses]`). A
 * single relationship ref is the one-element path; multi-hop paths are built by
 * `codegen`'s typed accessors chaining refs.
 */
export class NavigationPath {
  constructor(readonly refs: readonly RelationshipRef[]) {}
}
