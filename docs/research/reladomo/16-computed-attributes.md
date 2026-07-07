# Calculated attributes: expression methods wrap `AttributeCalculator`s that render SQL text and also evaluate in memory against cached objects

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`test/`** =
> `reladomo/src/test/java/com/gs/fw/common/mithra/test/`.

Reladomo's query language supports scalar expressions as **calculated attributes**: calling an
expression method on a typed finder attribute returns a `Calculated<Type>Attribute` that *is* an
attribute of the same type, so everything an attribute can do (eq/in/greaterThan, aggregation,
further arithmetic) composes on top. There is one calculated class per result type —
`CalculatedIntegerAttribute`, `-Long`, `-Float`, `-Double`, `-BigDecimal`, `-String`
(`mithra/attribute/CalculatedIntegerAttribute.java:68-75`). Each holds a single `calculator`
(`NumericAttributeCalculator` / `StringAttributeCalculator`,
`mithra/attribute/calculator/NumericAttributeCalculator.java`,
`StringAttributeCalculator.java`) and delegates value access, nullness, SQL text, and
update-count tracking to it.

## Building expressions

- **Arithmetic on two attributes**: `IntegerAttribute.plus/minus/times/dividedBy(otherAttribute)`
  builds a calculated attribute via the numeric-type tower; result type follows the wider operand
  (int+long → `LongAttribute`, int+double → `DoubleAttribute`, etc.)
  (`mithra/attribute/IntegerAttribute.java:477-628`). The calculators are
  `AdditionCalculator`/`SubstractionCalculator`/`MultiplicationCalculator`/`DivisionCalculator`
  in `mithra/attribute/calculator/arithmeticCalculator/`, whose SQL is
  `"(" + lhs + op + rhs + ")"` (`AbstractArithmeticAttributeCalculator.java:59-67`, operator
  strings at `AdditionCalculator.java:51-54` etc.).
- **Arithmetic with constants**: `plus(int)`, `times(double)`, `dividedBy(BigDecimal)` etc. use
  `ConstAdditionCalculatorInteger`/`-Double`/`-BigDecimal` and friends; `minus(c)` is implemented
  as `plus(-c)` (`mithra/attribute/IntegerAttribute.java:719-777`). The constant is embedded as a
  SQL literal: `col + 3` (`arithmeticCalculator/ConstAdditionCalculatorInteger.java:68-71`).
- **`absoluteValue()`**: one calculator per type (`AbsoluteValueCalculatorInteger` etc.), SQL
  `abs(<expr>)` (`mithra/attribute/calculator/AbstractAbsoluteValueCalculator.java:44-47`),
  in-memory `Math.abs` (`AbsoluteValueCalculatorInteger.java:35-50`).
- **`mod(int divisor)`** (constant divisor only): `ModCalculatorInteger.java:69-72` delegates to
  `DatabaseType.getModFunction`, default `MOD(expr, d)`
  (`mithra/databasetype/AbstractDatabaseType.java:460-463`).
- **String functions**: `toLowerCase()` → `lower(<expr>)`
  (`mithra/attribute/StringAttribute.java:315-318`,
  `calculator/StringToLowerCaseCalculator.java:63-66`); `substring(start, end)` (zero-based,
  lenient, `end = -1` means to-end; `StringAttribute.java:320-331`) → dialect
  `createSubstringExpression`, default `substr(expr, start+1, end-start)`
  (`AbstractDatabaseType.java:721-725`). There is no `toUpperCase`, concat, or trim.
- **Date/timestamp part extraction**: `year()/month()/dayOfMonth()` on `DateAttribute`
  (`mithra/attribute/DateAttribute.java:233-246`) and `TimestampAttribute`
  (`mithra/attribute/TimestampAttribute.java:484-497`) return `CalculatedIntegerAttribute`s over
  `DateYearCalculator`/`TimestampYearCalculator` etc. (in `arithmeticCalculator/`).
- **Type conversion**: `IntegerAttribute.convertToStringAttribute()`
  (`IntegerAttribute.java:330-333`, `IntegerToStringCalculator`) and
  `StringAttribute.convertToIntegerAttribute()` (`StringAttribute.java:470-473`,
  `StringToIntegerNumericAttributeCalculator`), lowered via
  `DatabaseType.getConversionFunctionIntegerToString/StringToInteger`
  (`mithra/databasetype/DatabaseType.java:227-229`; Sybase: `convert(char(11), expr)` /
  `convert(int, expr)`, `SybaseDatabaseType.java:489-497`).

Expressions **nest** freely because operands are plain `NumericAttribute`s:
`BookFinder.manufacturerId().minus(BookFinder.inventoryLevel()).absoluteValue().eq(195)`
(`test/TestArithmeticOperationInSearch.java:48-51`).
Operands may even be relationship-navigated attributes — the calculator contributes join SQL via
`generateMapperSql`/`createMappedOperation`
(`AbstractArithmeticAttributeCalculator.java:173-182`).

## Participation in operations, aggregation, ORDER BY

Since `CalculatedIntegerAttribute extends IntegerAttribute`, ordinary operation factories work on
it: `eq/notEq/in/notIn/greaterThan/lessThanEquals` return the standard atomic operations
(`IntegerEqOperation` etc.) with the calculated attribute as the left-hand attribute
(`CalculatedIntegerAttribute.java:246-323`). `eq(int)` routes through
`calculator.optimizedIntegerEq(...)` (`NumericAttributeCalculator.java:73`): the default is a
plain equality (`AbstractArithmeticAttributeCalculator.java:328-332`), but the *year* calculators
**rewrite the operation onto the base column** — `orderDate().year().eq(2004)` becomes
`orderDate >= 2004-01-01 AND orderDate < 2005-01-01`
(`arithmeticCalculator/TimestampYearCalculator.java:87-97`, `DateYearCalculator.java:71-78`) —
while `month().eq(...)` and `dayOfMonth().eq(...)` remain equality operations on the calculated
attribute and render the SQL date-part function (`DateMonthCalculator.java:71-75`,
`TimestampDayOfMonthCalculator.java:83-87`). `convertToIntegerAttribute().eq(123)` becomes
`trackingId = "123"` (`StringToIntegerNumericAttributeCalculator.java:228-231`).

Aggregation composes on top: `sum()/avg()/min()/max()` inherited from the numeric attribute wrap
the calculated attribute (`IntegerAttribute.java:780-799`), e.g.
`quantity().times(originalPrice()).sum()`
(`test/aggregate/TestDatedAggregation.java:137`).

ORDER BY is **not supported** for numeric calculated attributes:
`ascendingOrderBy()/descendingOrderBy()` throw `"not implemented"`
(`CalculatedIntegerAttribute.java:226-234`, `CalculatedDoubleAttribute.java:211-219`).
`CalculatedStringAttribute` inherits the generic implementation from `NonPrimitiveAttribute`
(`mithra/attribute/NonPrimitiveAttribute.java:118`). Calculated attributes are read-only —
setters, `getColumnName()`, and (for numeric types) `constructEqualityMapper`/`joinEq` throw
(`CalculatedIntegerAttribute.java:127-171, 148-151, 158-161, 330-349`); calculated *string*
attributes can be used in an `EqualityMapper` via the base `Attribute.constructEqualityMapper`
(`mithra/attribute/Attribute.java:246`).

## Lowering to SQL vs evaluating in memory

Atomic operations render their left side by calling
`attribute.getFullyQualifiedLeftHandExpression(query)`
(`mithra/finder/AtomicEqualityOperation.java:172-176`,
`mithra/finder/GreaterThanOperation.java:39`). For plain attributes that is a qualified column
name; a calculated attribute overrides it to return
`calculator.getFullyQualifiedCalculatedExpression(query)`
(`CalculatedIntegerAttribute.java:137-140`), which recurses through nested calculators down to
real columns. Dialect hooks on `DatabaseType` supply function spellings: date parts
(`DatabaseType.java:247-257`; Postgres `EXTRACT(YEAR FROM col)` and
`extract(year from col at time zone 'UTC' at time zone ...)` for timezone-converted timestamps,
`PostgresDatabaseType.java:439-475`; Sybase `datepart(year, col)`,
`SybaseDatabaseType.java:1413-1430`), substring, mod, and int/string conversion. Timestamp
attributes stored in UTC or database time pass a conversion flag; dialects without a
`...WithConversion` override throw `MithraBusinessException` when conversion cannot be elided
(`AbstractDatabaseType.java:840-893`).

The same calculator evaluates **in memory**: calculated attributes implement the extractor
interfaces (`IntExtractor` etc.), so cache filtering calls
`matchesWithoutDeleteCheck(o, extractor)` → `intValueOf(o)` →
`calculator.intValueOf(o)`, which reads operand attributes off the cached object
(`mithra/finder/integer/IntegerEqOperation.java:48-53`,
`CalculatedIntegerAttribute.java:117-125`, `ConstAdditionCalculatorInteger.java:43-46`,
`TimestampYearCalculator.java:59-64` — Joda-Time on the cached `Timestamp`). Bulk evaluation
(aggregation) uses the `forEach(Procedure...)` pattern with `WrappedProcedureAndContext`
(`mithra/attribute/calculator/WrappedProcedureAndContext.java`). Cached-query invalidation works
because the calculated attribute delegates `getUpdateCount()` to its calculator: binary arithmetic
calculators sum both operands' update counts (`AbstractArithmeticAttributeCalculator.java:151-159`),
while single-attribute calculators delegate to their one base attribute
(`AbstractSingleAttributeCalculator.java:101-108`).

**Null handling**: relational matching treats null as no-match
(`IntegerEqOperation.java:51`); `StringToLowerCaseCalculator.stringValueOf` returns null for
null input (lines 40-45); the procedure layer propagates nulls via
`NullHandlingProcedure.executeForNull` and `Inner*ProcedureForNull` wrappers
(`AbstractArithmeticAttributeCalculator.java:184-244, 487-576`;
`calculator/procedure/NullHandlingProcedure.java`). Note the quirk: the binary arithmetic
calculator's own `isAttributeNull` returns `false` unconditionally
(`AbstractArithmeticAttributeCalculator.java:96-99`).

## Testing patterns

The dominant pattern: run a finder with a calculated-attribute operation, then re-verify each
returned object with plain Java (`Math.abs`, `%`, `String.toLowerCase`) — implicitly exercising
both the SQL and in-memory paths.

- `test/TestCalculated.java` (extends `TestSqlDatatypes`): `absoluteValue()` × {eq, notEq, lessThan,
  greaterThanEquals, ...} for int/double/long/float/BigDecimal, plus `mod`, constant
  plus/times/dividedBy, and a dated-object case (`testAbsoluteValueWithDated`, lines 184-192).
- `test/TestArithmeticOperationInSearch.java`: nested attribute-to-attribute arithmetic; each test
  asserts `assertEqualsAndHashCode(op, op2)` on independently rebuilt operations (operation
  equality/caching) before `findOne` (lines 39-62).
- `test/TestYearMonthDayOfMonth.java`: `year()/month()/dayOfMonth()` with `eq` and `in(IntHashSet)`,
  on both `Date` and `Timestamp`, directly and through relationships
  (`OrderFinder.orderStatus().expectedDate().year().eq(2005)`, lines 31-92).
- `test/TestCalculatedString.java`: `toLowerCase()` combined with `startsWith/endsWith/contains`,
  substring, conversions in both directions, mapper/join usage
  (`testIntegerToStringInMapper`, line 363), and as-of interplay (`testAsOfAttributesWithToLower`,
  line 342).
- `test/aggregate/TestAggregateWithNull.java` (lines 378-658) and `test/aggregate/TestDatedAggregation.java`
  (lines 137, 170): `sum()` over `plus/times/dividedBy` expressions including nullable operands
  and relationship-navigated operands. Dialect suites (`TestSybaseGeneralTestCases`,
  `TestPostgresGeneralTestCases`, etc.) re-run the calculated tests against real databases.

## Code references

- `mithra/attribute/CalculatedIntegerAttribute.java` (68, eq 246, orderBy throws 226, LHS SQL 137), `CalculatedDoubleAttribute.java`, `CalculatedStringAttribute.java`
- `mithra/attribute/IntegerAttribute.java` (attribute arithmetic 477-628, const arithmetic 719-777, absoluteValue 631, mod 662, convertToStringAttribute 330, sum 791)
- `mithra/attribute/StringAttribute.java` (toLowerCase 315, substring 328, convertToIntegerAttribute 470); `DateAttribute.java` (233-246); `TimestampAttribute.java` (484-497)
- `mithra/attribute/calculator/` — `NumericAttributeCalculator.java` (optimizedIntegerEq 73), `AbstractAbsoluteValueCalculator.java` (44), `ModCalculatorInteger.java` (69), `StringToLowerCaseCalculator.java` (63), `SubstringCalculator.java` (44, 64), `IntegerToStringCalculator.java` (63), `StringToIntegerNumericAttributeCalculator.java` (57, 228)
- `mithra/attribute/calculator/arithmeticCalculator/` — `AbstractArithmeticAttributeCalculator.java` (SQL 59, null quirk 96, updateCount 151, mapper SQL 173), `ConstAdditionCalculatorInteger.java` (43, 68), `TimestampYearCalculator.java` (39, 59, 87), `DateYearCalculator.java` (71)
- `mithra/databasetype/DatabaseType.java` (227-229, 247-257); `AbstractDatabaseType.java` (mod 460, substr 721, timestamp-part fallback 840-893); `PostgresDatabaseType.java` (439-475); `SybaseDatabaseType.java` (489-497, 1413-1430)
- `mithra/finder/AtomicEqualityOperation.java` (172-176); `mithra/finder/GreaterThanOperation.java` (39); `mithra/finder/integer/IntegerEqOperation.java` (48-53)
- Tests: `test/TestCalculated.java`, `test/TestArithmeticOperationInSearch.java`, `test/TestYearMonthDayOfMonth.java`, `test/TestCalculatedString.java`, `test/aggregate/TestAggregateWithNull.java`, `test/aggregate/TestDatedAggregation.java`
