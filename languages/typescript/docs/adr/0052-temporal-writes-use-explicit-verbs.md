# Temporal writes use explicit verbs

Ordinary `update` uses the target entity's normal write semantics: non-temporal entities update in place, while temporal entities perform their current-row close-and-chain behavior. Bounded-window temporal writes use explicit verbs such as `updateUntil` and `terminateUntil`, because those operations have different business-window semantics and should be visible at the call site.

Temporal entities use `terminate` for closing the current row, while `delete` remains the physical-delete operation for non-temporal entities. This keeps temporal removal semantics explicit and avoids suggesting that historical milestone rows are physically deleted.

Bounded temporal writes accept only a business window, expressed as `{ business: { start, end } }`. The processing axis is audit history and is not directly user-editable through the TypeScript API.

Temporal creates follow the same rule: users may provide business effectivity but never processing timestamps. For business-temporal and bitemporal entities, `create(payload, { business: { start } })` creates a row effective from `start` to infinity, while `createUntil(payload, { business: { start, end } })` creates a bounded business interval.
