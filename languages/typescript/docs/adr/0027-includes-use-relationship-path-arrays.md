# Includes use relationship path arrays

TypeScript eager loading uses an `includes` option containing generated relationship paths. A longer include path implies its intermediate paths, so `Order.lineItems.product` also includes `Order.lineItems`; this keeps call sites concise while preserving the deep-fetch plan required by the core specification.
