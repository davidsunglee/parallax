# Python cost report comparison

Timing deltas within 5% and byte deltas within 3% are read as noise; count deltas are exact. A cell present on one side alone, or whose unit differs, is not compared.

## feature-boundary

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | elapsedUs | 0.209 | 0.167 | -0.042 us (-20.10%) | 9 | faster |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | retainedBytes | 88.000 | 88.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | elapsedUs | 301.625 | 298.625 | -3.000 us (-0.99%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | peakBytes | 18246.000 | 18246.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | retainedBytes | 16512.000 | 16512.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | elapsedUs | 19.375 | 19.583 | +0.208 us (+1.07%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | peakBytes | 2886.000 | 2886.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | retainedBytes | 1152.000 | 1152.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-0.decode | elapsedUs | 0.209 | 0.209 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-0.decode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-0.decode | retainedBytes | 88.000 | 88.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-128.decode | elapsedUs | 32.167 | 32.000 | -0.167 us (-0.52%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-128.decode | peakBytes | 2392.000 | 2392.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-128.decode | retainedBytes | 1152.000 | 1152.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-8.decode | elapsedUs | 2.333 | 2.375 | +0.042 us (+1.80%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-8.decode | peakBytes | 704.000 | 704.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-8.decode | retainedBytes | 192.000 | 192.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-0.decode | elapsedUs | 0.208 | 0.209 | +0.001 us (+0.48%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-0.decode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-0.decode | retainedBytes | 88.000 | 88.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-128.decode | elapsedUs | 11.708 | 12.333 | +0.625 us (+5.34%) | 9 | slower |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-128.decode | peakBytes | 2280.000 | 2280.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-128.decode | retainedBytes | 1152.000 | 1152.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-8.decode | elapsedUs | 1.083 | 1.042 | -0.041 us (-3.79%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-8.decode | peakBytes | 376.000 | 376.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-8.decode | retainedBytes | 192.000 | 192.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | elapsedUs | 0.125 | 0.125 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | elapsedUs | 243.791 | 246.000 | +2.209 us (+0.91%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | peakBytes | 8400.000 | 8400.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | retainedBytes | 6856.000 | 6856.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | elapsedUs | 15.750 | 15.708 | -0.042 us (-0.27%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | peakBytes | 1809.000 | 1809.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-0.encode | elapsedUs | 0.125 | 0.125 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-0.encode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-128.encode | elapsedUs | 50.083 | 48.792 | -1.291 us (-2.58%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-128.encode | peakBytes | 2336.000 | 2336.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-128.encode | retainedBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-8.encode | elapsedUs | 3.209 | 3.334 | +0.125 us (+3.90%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-8.encode | peakBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-8.encode | retainedBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-0.encode | elapsedUs | 0.125 | 0.125 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-0.encode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-128.encode | elapsedUs | 65.375 | 66.625 | +1.250 us (+1.91%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-128.encode | peakBytes | 2336.000 | 2336.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-128.encode | retainedBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-8.encode | elapsedUs | 4.417 | 4.458 | +0.041 us (+0.93%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-8.encode | peakBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-8.encode | retainedBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.nested-all.cold-plan | elapsedUs | 101.375 | 101.583 | +0.208 us (+0.21%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.nested-all.cold-plan | peakBytes | 15147.000 | 15147.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.nested-all.cold-plan | retainedBytes | 9883.000 | 9883.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | elapsedUs | 113.834 | 108.916 | -4.918 us (-4.32%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | peakBytes | 14889.000 | 14889.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | retainedBytes | 9705.000 | 9705.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.scalar-any.cold-plan | elapsedUs | 98.083 | 94.000 | -4.083 us (-4.16%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.scalar-any.cold-plan | peakBytes | 14582.000 | 14582.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.scalar-any.cold-plan | retainedBytes | 9454.000 | 9454.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.shallow-scalar.cold-plan | elapsedUs | 83.542 | 83.458 | -0.084 us (-0.10%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.shallow-scalar.cold-plan | peakBytes | 14202.000 | 14198.000 | -4.000 B (-0.03%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.shallow-scalar.cold-plan | retainedBytes | 8994.000 | 8990.000 | -4.000 B (-0.04%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | elapsedUs | 117.209 | 112.500 | -4.709 us (-4.02%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | peakBytes | 14741.000 | 14741.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | retainedBytes | 9533.000 | 9533.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | elapsedUs | 119.792 | 117.541 | -2.251 us (-1.88%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | peakBytes | 14965.000 | 14965.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | retainedBytes | 9461.000 | 9461.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.nested-all.binding | elapsedUs | 9.333 | 9.333 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.nested-all.binding | peakBytes | 3471.000 | 3471.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.nested-all.binding | retainedBytes | 368.000 | 368.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | elapsedUs | 14.750 | 13.875 | -0.875 us (-5.93%) | 9 | faster |
| 3.13 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | peakBytes | 3548.000 | 3548.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | retainedBytes | 424.000 | 424.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.scalar-any.binding | elapsedUs | 7.417 | 7.458 | +0.041 us (+0.55%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.scalar-any.binding | peakBytes | 2998.000 | 2998.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.scalar-any.binding | retainedBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.shallow-scalar.binding | elapsedUs | 6.500 | 6.500 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.shallow-scalar.binding | peakBytes | 2982.000 | 2982.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.shallow-scalar.binding | retainedBytes | 200.000 | 200.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.subtype-narrowing.binding | elapsedUs | 14.416 | 14.375 | -0.041 us (-0.28%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.subtype-narrowing.binding | peakBytes | 3878.000 | 3878.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.subtype-narrowing.binding | retainedBytes | 424.000 | 424.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.two-hop-to-one.binding | elapsedUs | 17.250 | 17.708 | +0.458 us (+2.66%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.two-hop-to-one.binding | peakBytes | 3646.000 | 3646.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.two-hop-to-one.binding | retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | elapsedUs | 0.209 | 0.250 | +0.041 us (+19.62%) | 9 | slower |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | retainedBytes | 96.000 | 96.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | elapsedUs | 270.042 | 270.125 | +0.083 us (+0.03%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | peakBytes | 18438.000 | 18438.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | retainedBytes | 16528.000 | 16528.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | elapsedUs | 17.417 | 17.458 | +0.041 us (+0.24%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | peakBytes | 3078.000 | 3078.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | retainedBytes | 1168.000 | 1168.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-0.decode | elapsedUs | 0.209 | 0.209 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-0.decode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-0.decode | retainedBytes | 96.000 | 96.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-128.decode | elapsedUs | 31.084 | 30.416 | -0.668 us (-2.15%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-128.decode | peakBytes | 2504.000 | 2504.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-128.decode | retainedBytes | 1168.000 | 1168.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-8.decode | elapsedUs | 2.209 | 2.250 | +0.041 us (+1.86%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-8.decode | peakBytes | 760.000 | 760.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-8.decode | retainedBytes | 208.000 | 208.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-0.decode | elapsedUs | 0.209 | 0.209 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-0.decode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-0.decode | retainedBytes | 96.000 | 96.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-128.decode | elapsedUs | 10.250 | 10.291 | +0.041 us (+0.40%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-128.decode | peakBytes | 2384.000 | 2384.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-128.decode | retainedBytes | 1168.000 | 1168.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-8.decode | elapsedUs | 0.916 | 0.917 | +0.001 us (+0.11%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-8.decode | peakBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-8.decode | retainedBytes | 208.000 | 208.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | elapsedUs | 0.125 | 0.125 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | elapsedUs | 228.791 | 229.459 | +0.668 us (+0.29%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | peakBytes | 8648.000 | 8648.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | retainedBytes | 6864.000 | 6864.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | elapsedUs | 14.875 | 14.875 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | peakBytes | 1969.000 | 1969.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | retainedBytes | 504.000 | 504.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-0.encode | elapsedUs | 0.125 | 0.167 | +0.042 us (+33.60%) | 9 | slower |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-0.encode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-128.encode | elapsedUs | 45.458 | 45.208 | -0.250 us (-0.55%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-128.encode | peakBytes | 2440.000 | 2440.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-128.encode | retainedBytes | 1104.000 | 1104.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-8.encode | elapsedUs | 3.083 | 3.042 | -0.041 us (-1.33%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-8.encode | peakBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-8.encode | retainedBytes | 144.000 | 144.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-0.encode | elapsedUs | 0.125 | 0.125 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-0.encode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-128.encode | elapsedUs | 55.875 | 56.167 | +0.292 us (+0.52%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-128.encode | peakBytes | 2440.000 | 2440.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-128.encode | retainedBytes | 1104.000 | 1104.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-8.encode | elapsedUs | 3.833 | 3.750 | -0.083 us (-2.17%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-8.encode | peakBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-8.encode | retainedBytes | 144.000 | 144.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.nested-all.cold-plan | elapsedUs | 98.709 | 102.166 | +3.457 us (+3.50%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.nested-all.cold-plan | peakBytes | 15618.000 | 15614.000 | -4.000 B (-0.03%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.nested-all.cold-plan | retainedBytes | 10786.000 | 10782.000 | -4.000 B (-0.04%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | elapsedUs | 107.333 | 123.959 | +16.626 us (+15.49%) | 9 | slower |
| 3.14 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | peakBytes | 15432.000 | 15432.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | retainedBytes | 10600.000 | 10600.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.scalar-any.cold-plan | elapsedUs | 88.375 | 89.333 | +0.958 us (+1.08%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.scalar-any.cold-plan | peakBytes | 15117.000 | 15117.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.scalar-any.cold-plan | retainedBytes | 10341.000 | 10341.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.shallow-scalar.cold-plan | elapsedUs | 80.042 | 80.250 | +0.208 us (+0.26%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.shallow-scalar.cold-plan | peakBytes | 14641.000 | 14641.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.shallow-scalar.cold-plan | retainedBytes | 9865.000 | 9865.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | elapsedUs | 112.791 | 112.166 | -0.625 us (-0.55%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | peakBytes | 15204.000 | 15204.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | retainedBytes | 10428.000 | 10428.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | elapsedUs | 114.583 | 115.542 | +0.959 us (+0.84%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | peakBytes | 15436.000 | 15436.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | retainedBytes | 10348.000 | 10348.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.nested-all.binding | elapsedUs | 9.166 | 8.875 | -0.291 us (-3.17%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.nested-all.binding | peakBytes | 4289.000 | 4289.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.nested-all.binding | retainedBytes | 368.000 | 368.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | elapsedUs | 13.125 | 13.500 | +0.375 us (+2.86%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | peakBytes | 4007.000 | 4007.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | retainedBytes | 424.000 | 424.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.scalar-any.binding | elapsedUs | 7.125 | 7.125 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.scalar-any.binding | peakBytes | 3800.000 | 3800.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.scalar-any.binding | retainedBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.shallow-scalar.binding | elapsedUs | 6.333 | 6.417 | +0.084 us (+1.33%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.shallow-scalar.binding | peakBytes | 3800.000 | 3800.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.shallow-scalar.binding | retainedBytes | 200.000 | 200.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.subtype-narrowing.binding | elapsedUs | 14.209 | 13.958 | -0.251 us (-1.77%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.subtype-narrowing.binding | peakBytes | 4751.000 | 4751.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.subtype-narrowing.binding | retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.two-hop-to-one.binding | elapsedUs | 16.666 | 16.458 | -0.208 us (-1.25%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.two-hop-to-one.binding | peakBytes | 4139.000 | 4139.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.two-hop-to-one.binding | retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 1 | within noise |

## instance-state

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| - | - | cpython-3.13 | aggregate.bare.after | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.before | 6384.000 | 6384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.reduction | 0.617 | 0.617 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.before | 7200.000 | 7200.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.reduction | 0.547 | 0.547 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.564 | 3.409 | -0.156 ratio (-4.37%) | 0 | smaller |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.564 | 3.409 | -0.156 ratio (-4.37%) | 0 | smaller |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.461 | 3.427 | -0.034 ratio (-1.00%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 0.500 | 0.507 | +0.007 ratio (+1.44%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.likeForLike | 0.481 | 0.487 | +0.006 ratio (+1.19%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 1.526 | 1.554 | +0.028 ratio (+1.83%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.159 | 2.191 | +0.032 ratio (+1.49%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.159 | 2.191 | +0.032 ratio (+1.49%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.152 | 2.214 | +0.062 ratio (+2.87%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 1603.317 | 1410.723 | -192.594 ns (-12.01%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 6678.912 | 7011.965 | +333.052 ns (+4.99%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.directWireNs | 11091.854 | 11085.645 | -6.209 ns (-0.06%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.dumpNs | 5957.771 | 6097.709 | +139.938 ns (+2.35%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 4770.000 | 4770.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionNs | 14772.750 | 14932.812 | +160.062 ns (+1.08%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | 7776.000 | 7776.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | 1240.000 | 1240.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | 12558.183 | 12500.438 | -57.746 ns (-0.46%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | 6536.000 | 6536.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.readNs | 83.954 | 86.679 | +2.725 ns (+3.25%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 303.673 | 535.942 | +232.270 ns (+76.49%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.transientBytes | 3706.000 | 3706.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 303.673 | 535.942 | +232.270 ns (+76.49%) | 0 | larger |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | 300.090 | 96.925 | -203.165 ns (-67.70%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 10175.285 | 10448.825 | +273.540 ns (+2.69%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2516.229 | 2521.063 | +4.834 ns (+0.19%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 4960.000 | 4960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.readNs | 23.367 | 25.350 | +1.983 ns (+8.49%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2168.000 | 2168.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 348.065 | 502.717 | +154.652 ns (+44.43%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 6011.769 | 6085.971 | +74.202 ns (+1.23%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2602.000 | 2508.375 | -93.625 ns (-3.60%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 26.108 | 25.067 | -1.042 ns (-3.99%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.retainedBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.transientBytes | 1336.000 | 1336.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | vsLegacy.bareReduction | 0.651 | 0.651 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | vsLegacy.retainedReduction | 0.619 | 0.619 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | vsOrdinary.bareReduction | 0.699 | 0.699 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | vsOrdinary.retainedReduction | 0.655 | 0.655 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.bareBytes | 328.000 | 328.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.callNs | 1419.593 | 1396.802 | -22.791 ns (-1.61%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 2332.177 | 2331.510 | -0.667 ns (-0.03%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.directWireNs | 5902.916 | 5975.146 | +72.229 ns (+1.22%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1830.229 | 1813.042 | -17.187 ns (-0.94%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionNs | 8431.708 | 7988.229 | -443.480 ns (-5.26%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | 2624.000 | 2624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | 6344.610 | 6315.694 | -28.917 ns (-0.46%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | 2152.000 | 2152.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.readNs | 75.171 | 74.375 | -0.796 ns (-1.06%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 256.748 | 200.953 | -55.795 ns (-21.73%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 256.748 | 200.953 | -55.795 ns (-21.73%) | 0 | smaller |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 164.608 | 301.983 | +137.375 ns (+83.46%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5572.954 | 5533.454 | -39.500 ns (-0.71%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 865.250 | 913.229 | +47.979 ns (+5.55%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 20.773 | 23.212 | +2.440 ns (+11.74%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 189.417 | 204.381 | +14.965 ns (+7.90%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1208.208 | 1209.931 | +1.723 ns (+0.14%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 876.500 | 852.625 | -23.875 ns (-2.72%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 21.829 | 22.242 | +0.412 ns (+1.89%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.retainedBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.transientBytes | 1336.000 | 1336.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | vsLegacy.bareReduction | 0.610 | 0.610 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | vsLegacy.retainedReduction | 0.525 | 0.525 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | vsOrdinary.bareReduction | 0.717 | 0.717 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | vsOrdinary.retainedReduction | 0.600 | 0.600 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.bareBytes | 296.000 | 296.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.callNs | 1380.836 | 1317.304 | -63.532 ns (-4.60%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 2109.248 | 2151.987 | +42.740 ns (+2.03%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.directWireNs | 5190.917 | 5437.667 | +246.750 ns (+4.75%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.dumpNs | 1851.542 | 1847.688 | -3.854 ns (-0.21%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 3432.000 | 3432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionNs | 7388.542 | 7397.417 | +8.875 ns (+0.12%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | 2536.000 | 2536.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | 5540.529 | 5497.235 | -43.294 ns (-0.78%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | 2152.000 | 2152.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.readNs | 75.098 | 75.960 | +0.863 ns (+1.15%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 215.013 | 173.646 | -41.367 ns (-19.24%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 215.013 | 173.646 | -41.367 ns (-19.24%) | 0 | smaller |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 213.956 | 127.858 | -86.098 ns (-40.24%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5171.190 | 5183.433 | +12.244 ns (+0.24%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.dumpNs | 895.500 | 869.604 | -25.896 ns (-2.89%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 21.250 | 22.721 | +1.471 ns (+6.92%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 227.671 | 210.785 | -16.885 ns (-7.42%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 935.121 | 933.715 | -1.406 ns (-0.15%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 904.980 | 907.145 | +2.166 ns (+0.24%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 21.508 | 22.556 | +1.048 ns (+4.87%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.retainedBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.transientBytes | 960.000 | 960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | vsLegacy.bareReduction | 0.648 | 0.648 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | vsLegacy.retainedReduction | 0.557 | 0.557 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | vsOrdinary.bareReduction | 0.543 | 0.543 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | vsOrdinary.retainedReduction | 0.333 | 0.333 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.bareBytes | 272.000 | 272.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.callNs | 1350.062 | 1355.612 | +5.550 ns (+0.41%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 2197.063 | 2190.137 | -6.925 ns (-0.32%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | 5956.479 | 5987.979 | +31.500 ns (+0.53%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1651.750 | 1679.479 | +27.729 ns (+1.68%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 3408.000 | 3408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | 7893.542 | 8023.250 | +129.708 ns (+1.64%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | 2896.000 | 2896.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | 6052.883 | 6001.806 | -51.077 ns (-0.84%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | 2424.000 | 2424.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.readNs | 79.036 | 78.479 | -0.557 ns (-0.70%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 234.141 | 209.193 | -24.948 ns (-10.66%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 234.141 | 209.193 | -24.948 ns (-10.66%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 193.075 | 167.016 | -26.058 ns (-13.50%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4106.717 | 4179.817 | +73.100 ns (+1.78%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 789.250 | 793.584 | +4.334 ns (+0.55%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 24.262 | 23.777 | -0.485 ns (-2.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 187.292 | 227.492 | +40.200 ns (+21.46%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1044.042 | 1038.342 | -5.700 ns (-0.55%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 788.105 | 774.875 | -13.230 ns (-1.68%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 23.833 | 23.390 | -0.443 ns (-1.86%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.retainedBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.transientBytes | 1288.000 | 1288.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | vsLegacy.bareReduction | 0.580 | 0.580 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | vsLegacy.retainedReduction | 0.480 | 0.480 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | vsOrdinary.bareReduction | 0.766 | 0.766 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | vsOrdinary.retainedReduction | 0.648 | 0.648 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.bareBytes | 248.000 | 248.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.callNs | 1330.721 | 1333.829 | +3.108 ns (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 2058.342 | 2043.483 | -14.858 ns (-0.72%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.directWireNs | 7266.875 | 7259.500 | -7.375 ns (-0.10%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1415.854 | 1413.125 | -2.729 ns (-0.19%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 3384.000 | 3384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionNs | 9027.708 | 9173.458 | +145.749 ns (+1.61%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | 3414.000 | 3414.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | 430.000 | 430.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | 5488.196 | 5487.448 | -0.748 ns (-0.01%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | 2984.000 | 2984.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.readNs | 90.969 | 88.286 | -2.682 ns (-2.95%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 209.067 | 195.927 | -13.140 ns (-6.29%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 209.067 | 195.927 | -13.140 ns (-6.29%) | 0 | smaller |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 308.471 | 165.016 | -143.455 ns (-46.51%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2846.154 | 2763.192 | -82.963 ns (-2.91%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 718.854 | 710.375 | -8.480 ns (-1.18%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 24.729 | 25.328 | +0.599 ns (+2.42%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 200.050 | 208.808 | +8.758 ns (+4.38%) | 0 | larger |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 774.992 | 790.692 | +15.700 ns (+2.03%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 709.937 | 726.854 | +16.917 ns (+2.38%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 25.510 | 26.464 | +0.953 ns (+3.74%) | 0 | larger |
| - | - | cpython-3.13/shallow | ordinary.retainedBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.transientBytes | 856.000 | 856.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | vsLegacy.bareReduction | 0.557 | 0.557 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | vsLegacy.retainedReduction | 0.448 | 0.448 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | vsOrdinary.bareReduction | 0.557 | 0.557 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | vsOrdinary.retainedReduction | 0.314 | 0.314 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.bareBytes | 670.000 | 670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.callNs | 1647.935 | 1671.787 | +23.852 ns (+1.45%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 4065.106 | 4069.796 | +4.690 ns (+0.12%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1721.063 | 1706.167 | -14.896 ns (-0.87%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 3384.000 | 3384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.readNs | 87.396 | 91.458 | +4.063 ns (+4.65%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 221.827 | 204.991 | -16.836 ns (-7.59%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.transientBytes | 2578.000 | 2578.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 221.827 | 204.991 | -16.836 ns (-7.59%) | 0 | smaller |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 92.415 | 86.840 | -5.575 ns (-6.03%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 3846.419 | 3875.160 | +28.742 ns (+0.75%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 700.250 | 722.750 | +22.500 ns (+3.21%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 24.625 | 26.641 | +2.016 ns (+8.19%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 230.111 | 215.877 | -14.234 ns (-6.19%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1714.869 | 1734.748 | +19.879 ns (+1.16%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 710.208 | 703.813 | -6.396 ns (-0.90%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 25.745 | 26.005 | +0.260 ns (+1.01%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.retainedBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.transientBytes | 964.000 | 964.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | vsLegacy.bareReduction | 0.244 | 0.244 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | vsLegacy.retainedReduction | 0.211 | 0.211 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | vsOrdinary.bareReduction | 0.160 | 0.160 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | vsOrdinary.retainedReduction | -0.010 | -0.010 | +0.000 ratio (-0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.bareBytes | 376.000 | 376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.callNs | 1427.303 | 1422.117 | -5.186 ns (-0.36%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 2573.740 | 2603.821 | +30.081 ns (+1.17%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.directWireNs | 6990.146 | 7135.791 | +145.645 ns (+2.08%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.dumpNs | 2432.187 | 2478.062 | +45.875 ns (+1.89%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 3512.000 | 3512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionNs | 9614.750 | 10080.583 | +465.833 ns (+4.84%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | 664.000 | 664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | 7513.615 | 7613.271 | +99.656 ns (+1.33%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | 2696.000 | 2696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.readNs | 79.068 | 78.932 | -0.135 ns (-0.17%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 200.272 | 206.955 | +6.683 ns (+3.34%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 200.272 | 206.955 | +6.683 ns (+3.34%) | 0 | larger |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 227.723 | 345.452 | +117.730 ns (+51.70%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 8034.610 | 8043.423 | +8.812 ns (+0.11%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1226.938 | 1188.021 | -38.917 ns (-3.17%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 21.214 | 21.224 | +0.010 ns (+0.05%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 250.912 | 233.750 | -17.163 ns (-6.84%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1787.254 | 1738.271 | -48.983 ns (-2.74%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1153.875 | 1155.209 | +1.333 ns (+0.12%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 20.837 | 21.143 | +0.306 ns (+1.47%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.retainedBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.transientBytes | 2008.000 | 2008.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | vsLegacy.bareReduction | 0.552 | 0.552 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | vsLegacy.retainedReduction | 0.475 | 0.475 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | vsOrdinary.bareReduction | 0.722 | 0.722 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | vsOrdinary.retainedReduction | 0.621 | 0.621 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.bare.after | 2776.000 | 2776.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.bare.before | 6632.000 | 6632.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.bare.reduction | 0.581 | 0.581 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.retained.before | 7448.000 | 7448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.retained.reduction | 0.518 | 0.518 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.105 | 3.126 | +0.021 ratio (+0.68%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.105 | 3.126 | +0.021 ratio (+0.68%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.030 | 3.021 | -0.009 ratio (-0.29%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 0.514 | 0.520 | +0.006 ratio (+1.18%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.likeForLike | 0.497 | 0.499 | +0.002 ratio (+0.50%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 1.490 | 1.483 | -0.007 ratio (-0.44%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.141 | 2.124 | -0.017 ratio (-0.80%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.141 | 2.124 | -0.017 ratio (-0.80%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.164 | 2.147 | -0.017 ratio (-0.78%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 1518.941 | 1468.871 | -50.071 ns (-3.30%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 5885.350 | 5910.171 | +24.821 ns (+0.42%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.directWireNs | 10210.042 | 10302.500 | +92.458 ns (+0.91%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.dumpNs | 5678.667 | 5495.396 | -183.271 ns (-3.23%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 5034.000 | 5034.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionNs | 13992.250 | 13822.146 | -170.104 ns (-1.22%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | 8674.000 | 8674.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | 1248.000 | 1248.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | 12042.750 | 11937.692 | -105.058 ns (-0.87%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | 7426.000 | 7426.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.readNs | 78.512 | 77.979 | -0.533 ns (-0.68%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 0.531 | 247.412 | +246.881 ns (+46519.18%) | 0 | larger |
| - | - | cpython-3.14/nested | compact.transientBytes | 3802.000 | 3802.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 0.531 | 247.412 | +246.881 ns (+46519.18%) | 0 | larger |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 116.306 | 26.427 | -89.879 ns (-77.28%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 9427.715 | 9416.740 | -10.975 ns (-0.12%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.dumpNs | 2425.125 | 2403.354 | -21.771 ns (-0.90%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5184.000 | 5184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.readNs | 25.600 | 25.242 | -0.358 ns (-1.40%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2264.000 | 2264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 201.800 | 216.900 | +15.100 ns (+7.48%) | 0 | larger |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 5612.637 | 5636.683 | +24.046 ns (+0.43%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 2439.583 | 2394.604 | -44.979 ns (-1.84%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4744.000 | 4744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 25.675 | 25.071 | -0.604 ns (-2.35%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.retainedBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.transientBytes | 1536.000 | 1536.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | vsLegacy.bareReduction | 0.606 | 0.606 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | vsLegacy.retainedReduction | 0.578 | 0.578 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | vsOrdinary.bareReduction | 0.658 | 0.658 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | vsOrdinary.retainedReduction | 0.616 | 0.616 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.bareBytes | 360.000 | 360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.callNs | 1326.238 | 1351.073 | +24.835 ns (+1.87%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 2043.054 | 2023.802 | -19.252 ns (-0.94%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.directWireNs | 5364.208 | 5302.729 | -61.479 ns (-1.15%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.dumpNs | 1672.687 | 1630.646 | -42.042 ns (-2.51%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 3672.000 | 3672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionNs | 7258.771 | 7344.813 | +86.042 ns (+1.19%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | 2864.000 | 2864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | 480.000 | 480.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | 5818.990 | 5750.821 | -68.169 ns (-1.17%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | 2384.000 | 2384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.readNs | 68.783 | 69.081 | +0.298 ns (+0.43%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 200.102 | 159.800 | -40.302 ns (-20.14%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 200.102 | 159.800 | -40.302 ns (-20.14%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 53.719 | 163.588 | +109.869 ns (+204.53%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 4599.406 | 4512.037 | -87.369 ns (-1.90%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 815.250 | 811.146 | -4.104 ns (-0.50%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 22.629 | 21.065 | -1.565 ns (-6.91%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 195.983 | 185.135 | -10.848 ns (-5.54%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1080.058 | 1058.781 | -21.277 ns (-1.97%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 799.750 | 789.417 | -10.333 ns (-1.29%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 24.204 | 22.044 | -2.160 ns (-8.93%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.retainedBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.transientBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | vsLegacy.bareReduction | 0.583 | 0.583 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | vsLegacy.retainedReduction | 0.504 | 0.504 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | vsOrdinary.bareReduction | 0.696 | 0.696 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | vsOrdinary.retainedReduction | 0.581 | 0.581 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.bareBytes | 328.000 | 328.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.callNs | 1192.175 | 1366.290 | +174.115 ns (+14.60%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 1952.617 | 1944.565 | -8.052 ns (-0.41%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.directWireNs | 4841.938 | 4868.708 | +26.771 ns (+0.55%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.dumpNs | 1600.958 | 1653.771 | +52.813 ns (+3.30%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 3576.000 | 3576.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionNs | 6545.292 | 6512.958 | -32.333 ns (-0.49%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | 2744.000 | 2744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | 392.000 | 392.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | 5164.244 | 5148.663 | -15.581 ns (-0.30%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | 2352.000 | 2352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.readNs | 67.829 | 68.660 | +0.831 ns (+1.23%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 215.323 | 194.108 | -21.215 ns (-9.85%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 215.323 | 194.108 | -21.215 ns (-9.85%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 135.635 | 212.635 | +77.000 ns (+56.77%) | 0 | larger |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 4401.219 | 4319.135 | -82.083 ns (-1.87%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.dumpNs | 790.875 | 797.208 | +6.333 ns (+0.80%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 22.412 | 22.775 | +0.362 ns (+1.62%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 182.965 | 189.004 | +6.039 ns (+3.30%) | 0 | larger |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 831.848 | 862.725 | +30.877 ns (+3.71%) | 0 | larger |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 796.708 | 793.875 | -2.833 ns (-0.36%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 23.679 | 26.887 | +3.208 ns (+13.55%) | 0 | larger |
| - | - | cpython-3.14/partial | ordinary.retainedBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.transientBytes | 1040.000 | 1040.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | vsLegacy.bareReduction | 0.620 | 0.620 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | vsLegacy.retainedReduction | 0.536 | 0.536 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | vsOrdinary.bareReduction | 0.512 | 0.512 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | vsOrdinary.retainedReduction | 0.310 | 0.310 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.bareBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.callNs | 1282.458 | 1235.654 | -46.804 ns (-3.65%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 1984.208 | 1969.346 | -14.862 ns (-0.75%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | 5431.688 | 5333.458 | -98.230 ns (-1.81%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1490.021 | 1510.292 | +20.271 ns (+1.36%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 3552.000 | 3552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | 7313.708 | 7020.312 | -293.396 ns (-4.01%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | 480.000 | 480.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | 5520.283 | 5488.313 | -31.971 ns (-0.58%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | 2632.000 | 2632.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.readNs | 71.378 | 71.958 | +0.580 ns (+0.81%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 204.622 | 216.673 | +12.051 ns (+5.89%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 204.622 | 216.673 | +12.051 ns (+5.89%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 98.969 | 232.298 | +133.329 ns (+134.72%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 3523.677 | 3539.848 | +16.171 ns (+0.46%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 716.271 | 730.417 | +14.146 ns (+1.97%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 24.119 | 25.461 | +1.342 ns (+5.57%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 206.710 | 170.596 | -36.114 ns (-17.47%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 940.102 | 1002.362 | +62.260 ns (+6.62%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 710.271 | 721.813 | +11.542 ns (+1.62%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 23.759 | 26.170 | +2.411 ns (+10.15%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | ordinary.retainedBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.transientBytes | 1368.000 | 1368.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | vsLegacy.bareReduction | 0.548 | 0.548 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | vsLegacy.retainedReduction | 0.455 | 0.455 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | vsOrdinary.bareReduction | 0.743 | 0.743 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | vsOrdinary.retainedReduction | 0.628 | 0.628 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.bareBytes | 280.000 | 280.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.callNs | 1256.644 | 1273.392 | +16.748 ns (+1.33%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 1884.294 | 1868.462 | -15.831 ns (-0.84%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.directWireNs | 6768.541 | 6603.791 | -164.750 ns (-2.43%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1278.916 | 1262.792 | -16.125 ns (-1.26%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 3528.000 | 3528.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionNs | 8189.896 | 8118.708 | -71.188 ns (-0.87%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | 3718.000 | 3718.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | 438.000 | 438.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | 5083.290 | 5077.021 | -6.269 ns (-0.12%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | 3280.000 | 3280.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.readNs | 83.370 | 81.974 | -1.396 ns (-1.67%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 214.450 | 196.959 | -17.490 ns (-8.16%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 214.450 | 196.959 | -17.490 ns (-8.16%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 179.175 | 235.032 | +55.857 ns (+31.17%) | 0 | larger |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 2466.471 | 2381.885 | -84.585 ns (-3.43%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 669.500 | 673.792 | +4.292 ns (+0.64%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 25.521 | 25.979 | +0.458 ns (+1.80%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 188.481 | 191.004 | +2.523 ns (+1.34%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 720.956 | 735.413 | +14.456 ns (+2.01%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 663.271 | 661.063 | -2.208 ns (-0.33%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 25.333 | 24.990 | -0.344 ns (-1.36%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.retainedBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.transientBytes | 936.000 | 936.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | vsLegacy.bareReduction | 0.521 | 0.521 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | vsLegacy.retainedReduction | 0.422 | 0.422 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | vsOrdinary.bareReduction | 0.521 | 0.521 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | vsOrdinary.retainedReduction | 0.288 | 0.288 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.bareBytes | 702.000 | 702.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.callNs | 1475.692 | 1539.671 | +63.979 ns (+4.34%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 3758.496 | 3775.954 | +17.458 ns (+0.46%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1599.000 | 1563.000 | -36.000 ns (-2.25%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 3528.000 | 3528.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.readNs | 79.870 | 79.734 | -0.135 ns (-0.17%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 236.104 | 194.362 | -41.742 ns (-17.68%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.transientBytes | 2690.000 | 2690.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 236.104 | 194.362 | -41.742 ns (-17.68%) | 0 | smaller |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 108.154 | 110.521 | +2.366 ns (+2.19%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 3386.367 | 3511.792 | +125.425 ns (+3.70%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 694.771 | 669.730 | -25.041 ns (-3.60%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 24.562 | 25.375 | +0.813 ns (+3.31%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 179.994 | 191.004 | +11.010 ns (+6.12%) | 0 | larger |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1608.527 | 1627.413 | +18.885 ns (+1.17%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 674.729 | 669.355 | -5.374 ns (-0.80%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 25.620 | 25.141 | -0.479 ns (-1.87%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.retainedBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.transientBytes | 1050.000 | 1050.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | vsLegacy.bareReduction | 0.229 | 0.229 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | vsLegacy.retainedReduction | 0.199 | 0.199 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | vsOrdinary.bareReduction | 0.146 | 0.146 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | vsOrdinary.retainedReduction | -0.019 | -0.019 | +0.000 ratio (-0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.bareBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.callNs | 1278.146 | 1309.342 | +31.196 ns (+2.44%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 2281.646 | 2280.512 | -1.133 ns (-0.05%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.directWireNs | 6498.729 | 6449.917 | -48.812 ns (-0.75%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.dumpNs | 2167.521 | 2165.958 | -1.563 ns (-0.07%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 3720.000 | 3720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionNs | 8707.459 | 8579.396 | -128.063 ns (-1.47%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | 3616.000 | 3616.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | 6972.429 | 6926.806 | -45.623 ns (-0.65%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | 2944.000 | 2944.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.readNs | 75.320 | 76.122 | +0.802 ns (+1.06%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 204.808 | 225.760 | +20.952 ns (+10.23%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 204.808 | 225.760 | +20.952 ns (+10.23%) | 0 | larger |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 135.638 | 357.871 | +222.233 ns (+163.84%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 6796.550 | 6615.900 | -180.650 ns (-2.66%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1068.688 | 1042.396 | -26.292 ns (-2.46%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 23.107 | 22.087 | -1.020 ns (-4.41%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 170.129 | 175.394 | +5.265 ns (+3.09%) | 0 | larger |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 1575.642 | 1490.127 | -85.515 ns (-5.43%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1009.542 | 1029.625 | +20.083 ns (+1.99%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 24.288 | 22.402 | -1.885 ns (-7.76%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.retainedBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.transientBytes | 2088.000 | 2088.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | vsLegacy.bareReduction | 0.528 | 0.528 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | vsLegacy.retainedReduction | 0.456 | 0.456 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | vsOrdinary.bareReduction | 0.703 | 0.703 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | vsOrdinary.retainedReduction | 0.605 | 0.605 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |

## lifecycle-overhead

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.092 | 3.123 | +0.031 us/event (+1.01%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 3.966 | 3.798 | -0.168 us/event (-4.24%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.268 | 0.264 | -0.005 ratio (-1.73%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.020 | 0.020 | +0.000 ratio (+0.80%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.065 | 0.066 | +0.000 ratio (+0.33%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.004 | 0.004 | +0.000 ratio (+0.96%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.166 | 0.164 | -0.001 ratio (-0.70%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p50 | 409.666 | 419.375 | +9.709 us (+2.37%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p95 | 437.917 | 444.000 | +6.083 us (+1.39%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 86.584 | 87.458 | +0.874 us (+1.01%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 111.042 | 106.333 | -4.709 us (-4.24%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.269 | 0.264 | -0.005 ratio (-1.72%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.339 | 0.320 | -0.019 ratio (-5.63%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | plain.p50 | 322.791 | 331.792 | +9.001 us (+2.79%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | plain.p95 | 343.250 | 351.834 | +8.584 us (+2.50%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.269 | 0.264 | -0.005 ratio (-1.92%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.276 | 0.262 | -0.014 ratio (-5.02%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.223 | 2.228 | +0.005 us/event (+0.20%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 2.957 | 2.905 | -0.052 us/event (-1.76%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.194 | 0.189 | -0.005 ratio (-2.73%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.014 | 0.014 | -0.000 ratio (-0.02%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.047 | 0.047 | -0.000 ratio (-0.53%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | +0.000 ratio (+0.15%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.120 | 0.118 | -0.002 ratio (-1.62%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p50 | 383.333 | 392.916 | +9.583 us (+2.50%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p95 | 408.458 | 416.834 | +8.376 us (+2.05%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 62.249 | 62.375 | +0.126 us (+0.20%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 82.791 | 81.333 | -1.458 us (-1.76%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.194 | 0.189 | -0.005 ratio (-2.78%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.258 | 0.245 | -0.013 ratio (-4.92%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | plain.p50 | 320.750 | 330.416 | +9.666 us (+3.01%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | plain.p95 | 345.125 | 350.667 | +5.542 us (+1.61%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.195 | 0.189 | -0.006 ratio (-3.05%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.184 | 0.189 | +0.005 ratio (+2.82%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 3.744 | 3.759 | +0.015 us/event (+0.40%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.629 | 4.436 | -0.193 us/event (-4.18%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.324 | 0.317 | -0.007 ratio (-2.19%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.024 | 0.024 | +0.000 ratio (+0.20%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.079 | 0.079 | -0.000 ratio (-0.25%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.005 | 0.005 | +0.000 ratio (+0.36%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.200 | 0.198 | -0.002 ratio (-1.22%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | observed.p50 | 428.791 | 438.208 | +9.417 us (+2.20%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | observed.p95 | 456.542 | 464.875 | +8.333 us (+1.83%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 104.833 | 105.250 | +0.417 us (+0.40%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 129.625 | 124.209 | -5.416 us (-4.18%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.323 | 0.316 | -0.007 ratio (-2.17%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.399 | 0.370 | -0.029 ratio (-7.16%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | plain.p50 | 323.917 | 332.500 | +8.583 us (+2.65%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | plain.p95 | 348.458 | 353.750 | +5.292 us (+1.52%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.324 | 0.318 | -0.006 ratio (-1.81%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.310 | 0.314 | +0.004 ratio (+1.28%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 3.557 | 3.624 | +0.067 us/event (+1.88%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 4.467 | 4.362 | -0.106 us/event (-2.36%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.308 | 0.305 | -0.002 ratio (-0.81%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.023 | 0.023 | +0.000 ratio (+1.68%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.075 | 0.076 | +0.001 ratio (+1.21%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.005 | 0.005 | +0.000 ratio (+1.84%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.190 | 0.191 | +0.000 ratio (+0.20%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 423.500 | 433.792 | +10.292 us (+2.43%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 452.542 | 462.000 | +9.458 us (+2.09%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 99.583 | 101.459 | +1.876 us (+1.88%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 125.083 | 122.125 | -2.958 us (-2.36%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.308 | 0.305 | -0.003 ratio (-0.83%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.386 | 0.364 | -0.023 ratio (-5.86%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 323.666 | 332.458 | +8.792 us (+2.72%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 346.167 | 353.291 | +7.124 us (+2.06%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.308 | 0.305 | -0.004 ratio (-1.18%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.307 | 0.308 | +0.000 ratio (+0.13%) | 0 | within noise |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.369 | 1.406 | +0.037 us/event (+2.72%) | 0 | within noise |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 2.064 | 2.115 | +0.051 us/event (+2.45%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.119 | 0.119 | -0.000 ratio (-0.06%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.009 | 0.009 | +0.000 ratio (+2.51%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.029 | 0.030 | +0.001 ratio (+2.03%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | +0.000 ratio (+2.68%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.074 | 0.074 | +0.001 ratio (+0.99%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p50 | 359.375 | 369.083 | +9.708 us (+2.70%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p95 | 383.959 | 397.000 | +13.041 us (+3.40%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 38.333 | 39.376 | +1.043 us (+2.72%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 57.791 | 59.209 | +1.418 us (+2.45%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.120 | 0.120 | +0.000 ratio (+0.13%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.179 | 0.178 | -0.001 ratio (-0.70%) | 0 | within noise |
| - | - | one Handler that keeps nothing | plain.p50 | 320.875 | 329.792 | +8.917 us (+2.78%) | 0 | within noise |
| - | - | one Handler that keeps nothing | plain.p95 | 341.750 | 352.917 | +11.167 us (+3.27%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.120 | 0.119 | -0.001 ratio (-0.70%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.124 | 0.125 | +0.001 ratio (+1.14%) | 0 | within noise |
| - | - | workload | events | 28.000 | 28.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | workload | statements | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |

## snapshot-delivery

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 9775.333 | 9698.917 | -76.416 us (-0.78%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1392.861 | 1392.861 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 693.328 | 693.328 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 106295.292 | 103783.333 | -2511.959 us (-2.36%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 12652.338 | 12652.338 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 6931.836 | 6931.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 17380.041 | 16089.125 | -1290.916 us (-7.43%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 391.807 | 391.807 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.458 | 3.458 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 110052.458 | 107103.833 | -2948.625 us (-2.68%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 775.244 | 775.244 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.489 | 3.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8157.542 | 8075.041 | -82.501 us (-1.01%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1192.139 | 1192.139 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 477.848 | 477.848 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 81701.708 | 80762.000 | -939.708 us (-1.15%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11110.373 | 11110.373 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4775.730 | 4775.730 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 16197.584 | 14978.000 | -1219.584 us (-7.53%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 332.436 | 332.436 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.524 | 2.524 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 96184.458 | 94236.041 | -1948.417 us (-2.03%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 774.357 | 774.357 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.556 | 2.556 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 19093.667 | 17812.959 | -1280.708 us (-6.71%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1298.314 | 1298.314 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 708.953 | 708.953 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 201766.833 | 178113.708 | -23653.125 us (-11.72%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12084.102 | 12084.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7088.086 | 7088.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 25681.500 | 23765.541 | -1915.959 us (-7.46%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 507.689 | 507.689 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.536 | 3.536 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 184191.375 | 182061.500 | -2129.875 us (-1.16%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 874.955 | 874.955 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.567 | 3.567 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 16078.166 | 15864.833 | -213.333 us (-1.33%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1208.674 | 1208.674 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 501.285 | 501.285 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 159250.875 | 158121.541 | -1129.334 us (-0.71%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12084.531 | 12084.531 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5010.105 | 5010.105 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 23857.458 | 21930.041 | -1927.417 us (-8.08%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 474.014 | 474.014 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.642 | 2.642 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 170986.792 | 163540.166 | -7446.626 us (-4.36%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 871.240 | 871.240 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.673 | 2.673 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6012.791 | 5928.542 | -84.249 us (-1.40%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 456.371 | 456.371 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 227.253 | 227.253 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 825.500 | 842.750 | +17.250 us (+2.09%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 69.370 | 69.370 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 28.146 | 28.146 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4503.000 | 4431.584 | -71.416 us (-1.59%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 390.489 | 390.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 186.823 | 186.823 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 695.459 | 657.125 | -38.334 us (-5.51%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 62.152 | 62.152 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.200 | 23.200 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8639.959 | 8591.417 | -48.542 us (-0.56%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 580.786 | 580.786 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 293.815 | 293.815 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1199.083 | 1193.917 | -5.166 us (-0.43%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 86.676 | 86.676 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 36.802 | 36.802 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6870.000 | 6743.958 | -126.042 us (-1.83%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 524.941 | 524.941 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 257.698 | 257.698 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 985.917 | 1001.208 | +15.291 us (+1.55%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 81.229 | 81.229 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.388 | 32.388 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10704.250 | 10797.708 | +93.458 us (+0.87%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 725.670 | 725.670 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 384.511 | 384.511 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1530.708 | 1485.500 | -45.208 us (-2.95%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 105.743 | 105.743 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 48.544 | 48.544 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8473.625 | 8425.250 | -48.375 us (-0.57%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 664.742 | 664.742 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 333.909 | 333.909 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1263.583 | 1236.042 | -27.541 us (-2.18%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 99.369 | 99.369 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.247 | 42.247 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 419.222 | 420.996 | +1.774 KiB (+0.42%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 296.780 | 297.176 | +0.396 KiB (+0.13%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.531 | 0.404 | -0.127 ms (-23.90%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.750 | 0.644 | -0.105 ms (-14.06%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 4.865 | 4.702 | -0.163 ms (-3.36%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 39425.376 | 41835.166 | +2409.791 roots/s (+6.11%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 5.332 | 5.521 | +0.189 ms (+3.55%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 37673.056 | 39126.180 | +1453.124 roots/s (+3.86%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 7.433 | 7.383 | -0.050 ms (-0.67%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 26740.499 | 26522.121 | -218.378 roots/s (-0.82%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 220.542 | 219.224 | -1.318 KiB (-0.60%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.114 | 44.738 | +2.624 KiB (+6.23%) | 6 | larger |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 80.071 | 80.877 | +0.806 KiB (+1.01%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 9.824 | 10.950 | +1.126 KiB (+11.46%) | 6 | larger |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1232.190 | 1232.261 | +0.070 KiB (+0.01%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.973 | 521.973 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.671 | 0.669 | -0.002 ms (-0.37%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.010 | 1.095 | +0.086 ms (+8.51%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 8.380 | 8.562 | +0.183 ms (+2.18%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23650.215 | 23464.883 | -185.331 roots/s (-0.78%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 9.071 | 9.210 | +0.139 ms (+1.53%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 21891.119 | 21969.674 | +78.555 roots/s (+0.36%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 11.769 | 11.890 | +0.121 ms (+1.02%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 16373.255 | 16446.692 | +73.437 roots/s (+0.45%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 667.780 | 667.897 | +0.117 KiB (+0.02%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 29.103 | 29.220 | +0.117 KiB (+0.40%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 188.050 | 188.167 | +0.117 KiB (+0.06%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 5.002 | 5.002 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1586.529 | 1586.600 | +0.070 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.645 | 869.645 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.841 | 0.827 | -0.014 ms (-1.64%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.007 | 2.010 | +0.003 ms (+0.14%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 21.958 | 24.528 | +2.570 ms (+11.70%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 9068.324 | 8276.547 | -791.778 roots/s (-8.73%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 22.824 | 24.768 | +1.944 ms (+8.52%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8674.924 | 4285.806 | -4389.118 roots/s (-50.60%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 25.528 | 26.212 | +0.684 ms (+2.68%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 7806.427 | 7103.954 | -702.472 roots/s (-9.00%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1038.378 | 1038.502 | +0.124 KiB (+0.01%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 56.446 | 57.180 | +0.733 KiB (+1.30%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 290.467 | 290.226 | -0.241 KiB (-0.08%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 7.666 | 7.715 | +0.049 KiB (+0.64%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1289.890 | 1289.960 | +0.070 KiB (+0.01%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 545.004 | 545.004 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.855 | 0.817 | -0.038 ms (-4.47%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.423 | 1.505 | +0.082 ms (+5.79%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 15.932 | 16.068 | +0.136 ms (+0.85%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 12452.008 | 12382.304 | -69.704 roots/s (-0.56%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 15.862 | 15.987 | +0.125 ms (+0.79%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12625.731 | 12533.160 | -92.571 roots/s (-0.73%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 18.796 | 19.309 | +0.513 ms (+2.73%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10654.994 | 10585.605 | -69.389 roots/s (-0.65%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1132.690 | 1132.808 | +0.117 KiB (+0.01%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 37.985 | 38.103 | +0.117 KiB (+0.31%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 302.011 | 302.128 | +0.117 KiB (+0.04%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 5.627 | 5.627 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 292.583 | 292.653 | +0.070 KiB (+0.02%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.810 | 171.863 | +0.054 KiB (+0.03%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.476 | 0.469 | -0.007 ms (-1.37%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.687 | 0.656 | -0.030 ms (-4.42%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.166 | 5.041 | -0.125 ms (-2.43%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 39448.051 | 38832.441 | -615.610 roots/s (-1.56%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 5.666 | 5.543 | -0.123 ms (-2.17%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 36063.653 | 36056.338 | -7.315 roots/s (-0.02%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 7.868 | 7.790 | -0.078 ms (-0.99%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 24819.796 | 25027.245 | +207.449 roots/s (+0.84%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 177.027 | 177.098 | +0.070 KiB (+0.04%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 31.711 | 32.916 | +1.205 KiB (+3.80%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 68.164 | 68.241 | +0.077 KiB (+0.11%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 3.091 | 3.137 | +0.046 KiB (+1.48%) | 6 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 4.617 | 4.667 | +0.050 us/projection (+1.09%) | 9 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 214585.079 | 216124.980 | +1539.901 projections/s (+0.72%) | 9 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 35.895 | 35.895 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 41.653 | 41.653 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 434.312 | 434.312 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 140.000 | 140.000 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 5.825 | 5.863 | +0.038 us/projection (+0.66%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 171696.854 | 173637.952 | +1941.098 projections/s (+1.13%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 39.090 | 39.090 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 56.621 | 56.621 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 434.312 | 434.312 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 191.125 | 191.125 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.459 | 8.672 | +0.212 ms (+2.51%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 23757.673 | 23259.194 | -498.478 roots/s (-2.10%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.352 | 9.412 | +0.060 ms (+0.64%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 21470.840 | 21571.094 | +100.253 roots/s (+0.47%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.446 | 41.159 | +24.713 ms (+150.26%) | 9 | slower |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 12202.563 | 11292.948 | -909.614 roots/s (-7.45%) | 9 | slower |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 16.449 | 18.319 | +1.870 ms (+11.37%) | 9 | slower |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 12134.389 | 11340.306 | -794.082 roots/s (-6.54%) | 9 | slower |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 31.999 | 31.158 | -0.841 us/root (-2.63%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 96.629 | 96.629 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.852 | 50.852 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 31.953 | 31.879 | -0.074 us/root (-0.23%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 101.980 | 101.980 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.852 | 50.852 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 47.949 | 45.652 | -2.297 us/root (-4.79%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 144.445 | 144.445 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.977 | 87.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 47.590 | 46.732 | -0.858 us/root (-1.80%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 149.680 | 149.680 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.977 | 87.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 65.896 | 66.025 | +0.129 us/root (+0.20%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 215.234 | 215.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.477 | 137.477 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 66.780 | 66.078 | -0.702 us/root (-1.05%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 218.836 | 218.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.477 | 137.477 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 23.018 | 22.723 | -0.296 us/root (-1.28%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 60.105 | 60.105 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.102 | 24.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 23.298 | 23.576 | +0.277 us/root (+1.19%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 67.457 | 67.457 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.102 | 24.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 152.921 | 151.103 | -1.818 us/root (-1.19%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 621.332 | 621.332 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.102 | 428.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 153.298 | 151.561 | -1.737 us/root (-1.13%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 626.340 | 626.340 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.102 | 428.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 56.958 | 55.909 | -1.049 us/root (-1.84%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 191.219 | 191.219 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.102 | 125.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 55.927 | 56.190 | +0.263 us/root (+0.47%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 194.910 | 194.910 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.102 | 125.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 46.251 | 46.861 | +0.609 us/root (+1.32%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 126.313 | 126.313 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.945 | 35.945 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 48.768 | 47.641 | -1.128 us/root (-2.31%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 131.665 | 131.665 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.945 | 35.945 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 54.724 | 72.888 | +18.164 us/root (+33.19%) | 9 | slower |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 214.492 | 214.492 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.727 | 136.727 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 55.294 | 55.242 | -0.052 us/root (-0.09%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 219.359 | 219.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.727 | 136.727 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 146.436 | 149.339 | +2.902 us/root (+1.98%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 757.062 | 757.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.227 | 480.227 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 146.324 | 148.568 | +2.243 us/root (+1.53%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 761.930 | 761.930 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.227 | 480.227 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 240.291 | 231.917 | -8.374 us (-3.48%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 28.539 | 28.543 | +0.004 KiB (+0.01%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 21.832 | 21.832 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 348.042 | 348.042 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 38.534 | 38.530 | -0.004 KiB (-0.01%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 30.401 | 30.405 | +0.004 KiB (+0.01%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 454.667 | 457.208 | +2.541 us (+0.56%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 47.896 | 47.896 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 38.455 | 38.455 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 83.834 | 82.541 | -1.293 us (-1.54%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 17.167 | 17.167 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 10.972 | 10.972 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 82.833 | 83.375 | +0.542 us (+0.65%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 17.182 | 17.182 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 11.236 | 11.236 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 82.833 | 80.709 | -2.124 us (-2.56%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 17.167 | 17.167 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 10.972 | 10.968 | -0.004 KiB (-0.04%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 85.458 | 82.750 | -2.708 us (-3.17%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 17.182 | 17.182 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 11.236 | 11.236 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 80.750 | 80.000 | -0.750 us (-0.93%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 17.168 | 17.168 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 10.973 | 10.973 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 83.791 | 84.542 | +0.751 us (+0.90%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 17.183 | 17.183 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 11.237 | 11.237 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 2.209 | 2.209 | +0.000 us (+0.01%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 2.708 | 2.708 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 3.291 | 3.292 | +0.001 us (+0.03%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.closed.retainedKiB | 71.484 | 71.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.shared.retainedKiB | 50.789 | 50.789 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | small.closed.retainedKiB | 118.438 | 118.438 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | small.shared.retainedKiB | 111.070 | 111.070 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 8918.459 | 8914.417 | -4.042 us (-0.05%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1351.897 | 1351.897 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 741.773 | 741.773 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 92964.000 | 97788.625 | +4824.625 us (+5.19%) | 9 | slower |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 13106.237 | 13106.237 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 7416.219 | 7416.219 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 18155.709 | 17405.500 | -750.209 us (-4.13%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 172.350 | 172.350 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.700 | 3.700 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 106991.917 | 105757.334 | -1234.583 us (-1.15%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 178.662 | 178.662 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.731 | 3.731 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 7567.959 | 7921.500 | +353.541 us (+4.67%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1180.812 | 1180.812 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 487.230 | 487.230 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 75964.458 | 84425.083 | +8460.625 us (+11.14%) | 9 | slower |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11346.004 | 11346.004 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4869.488 | 4869.488 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 15543.500 | 16612.708 | +1069.208 us (+6.88%) | 9 | slower |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 176.319 | 176.319 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.571 | 2.571 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 88960.125 | 92222.542 | +3262.417 us (+3.67%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 178.226 | 178.226 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.603 | 2.603 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 16942.375 | 17078.541 | +136.166 us (+0.80%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1297.487 | 1297.487 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 758.961 | 758.961 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 171206.250 | 171858.750 | +652.500 us (+0.38%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12747.543 | 12747.543 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7588.094 | 7588.094 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 24408.125 | 23676.250 | -731.875 us (-3.00%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 281.568 | 281.568 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.786 | 3.786 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 175145.834 | 175303.541 | +157.707 us (+0.09%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 286.896 | 286.896 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.817 | 3.817 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 15119.875 | 15070.917 | -48.958 us (-0.32%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1274.736 | 1274.736 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 510.668 | 510.668 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 154248.416 | 158078.542 | +3830.126 us (+2.48%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12748.236 | 12748.236 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5103.863 | 5103.863 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 22584.834 | 21963.875 | -620.959 us (-2.75%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 281.983 | 281.983 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.688 | 2.688 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 156319.334 | 156043.208 | -276.126 us (-0.18%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 283.546 | 283.546 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.720 | 2.720 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 5600.834 | 6652.167 | +1051.333 us (+18.77%) | 9 | slower |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 402.662 | 402.662 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 245.097 | 245.097 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 788.834 | 899.292 | +110.458 us (+14.00%) | 9 | slower |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 69.286 | 69.286 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 34.177 | 34.177 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4049.000 | 4076.250 | +27.250 us (+0.67%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 360.378 | 360.378 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 190.003 | 190.003 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 628.042 | 622.042 | -6.000 us (-0.96%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 61.471 | 61.471 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.606 | 23.606 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8133.333 | 8128.584 | -4.749 us (-0.06%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 531.056 | 531.056 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 317.237 | 317.237 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1143.375 | 1156.041 | +12.666 us (+1.11%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 86.559 | 86.559 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 42.489 | 42.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6235.958 | 6187.709 | -48.249 us (-0.77%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 497.139 | 497.139 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 261.722 | 261.722 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 925.916 | 915.334 | -10.582 us (-1.14%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 81.329 | 81.329 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.903 | 32.903 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10217.375 | 10120.000 | -97.375 us (-0.95%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 686.044 | 686.044 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 415.769 | 415.769 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1432.791 | 1418.375 | -14.416 us (-1.01%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 105.635 | 105.635 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 54.958 | 54.958 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 7817.875 | 7834.375 | +16.500 us (+0.21%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 639.041 | 639.041 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 339.104 | 339.104 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1180.292 | 1150.167 | -30.125 us (-2.55%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 99.258 | 99.258 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.911 | 42.911 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 382.197 | 379.533 | -2.664 KiB (-0.70%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 295.975 | 290.361 | -5.613 KiB (-1.90%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.506 | 0.497 | -0.008 ms (-1.68%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.674 | 0.672 | -0.002 ms (-0.33%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 4.480 | 4.354 | -0.126 ms (-2.81%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 45036.596 | 45704.717 | +668.121 roots/s (+1.48%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 4.870 | 4.989 | +0.119 ms (+2.45%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 41049.504 | 40878.896 | -170.607 roots/s (-0.42%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 7.375 | 7.195 | -0.180 ms (-2.44%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 27886.388 | 27860.974 | -25.414 roots/s (-0.09%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 202.710 | 196.382 | -6.328 KiB (-3.12%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 40.492 | 41.003 | +0.511 KiB (+1.26%) | 6 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 73.856 | 73.391 | -0.466 KiB (-0.63%) | 6 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 13.382 | 13.382 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1221.798 | 1221.868 | +0.070 KiB (+0.01%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.383 | 531.383 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.753 | 0.692 | -0.061 ms (-8.05%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.071 | 1.033 | -0.038 ms (-3.51%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 7.884 | 7.763 | -0.121 ms (-1.53%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 25686.995 | 25919.608 | +232.613 roots/s (+0.91%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 8.816 | 8.596 | -0.220 ms (-2.50%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 23444.941 | 23447.802 | +2.861 roots/s (+0.01%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 11.476 | 11.350 | -0.126 ms (-1.10%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 17519.463 | 17592.212 | +72.749 roots/s (+0.42%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 665.801 | 665.918 | +0.117 KiB (+0.02%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 31.615 | 31.732 | +0.117 KiB (+0.37%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 188.855 | 188.973 | +0.117 KiB (+0.06%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 5.107 | 5.107 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1629.932 | 1629.948 | +0.017 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.708 | 883.808 | +0.100 KiB (+0.01%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.858 | 0.801 | -0.057 ms (-6.66%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 1.895 | 1.910 | +0.015 ms (+0.78%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 20.401 | 20.263 | -0.138 ms (-0.68%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 9722.700 | 9808.169 | +85.469 roots/s (+0.88%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 21.233 | 21.165 | -0.068 ms (-0.32%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 9319.339 | 9382.330 | +62.991 roots/s (+0.68%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 24.309 | 23.969 | -0.340 ms (-1.40%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 8334.940 | 8361.859 | +26.920 roots/s (+0.32%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1066.213 | 1066.283 | +0.070 KiB (+0.01%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 53.855 | 53.752 | -0.104 KiB (-0.19%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 297.565 | 297.457 | -0.108 KiB (-0.04%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 7.894 | 7.949 | +0.056 KiB (+0.71%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1356.597 | 1356.667 | +0.070 KiB (+0.01%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.414 | 554.414 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.758 | 0.843 | +0.085 ms (+11.17%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.417 | 1.428 | +0.011 ms (+0.76%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 15.173 | 14.849 | -0.325 ms (-2.14%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 13112.999 | 13457.479 | +344.479 roots/s (+2.63%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 14.996 | 14.628 | -0.368 ms (-2.46%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 13444.023 | 13452.726 | +8.704 roots/s (+0.06%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 18.360 | 18.029 | -0.331 ms (-1.80%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10986.621 | 11218.597 | +231.975 roots/s (+2.11%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1145.113 | 1145.230 | +0.117 KiB (+0.01%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 41.064 | 41.182 | +0.117 KiB (+0.29%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 307.512 | 307.629 | +0.117 KiB (+0.04%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 5.764 | 5.764 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 253.586 | 253.656 | +0.070 KiB (+0.03%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 174.945 | 174.895 | -0.051 KiB (-0.03%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.487 | 0.466 | -0.021 ms (-4.32%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.620 | 0.619 | -0.000 ms (-0.07%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 4.794 | 4.736 | -0.057 ms (-1.20%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 41491.986 | 38246.710 | -3245.276 roots/s (-7.82%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 5.309 | 5.402 | +0.093 ms (+1.76%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 36602.102 | 37572.211 | +970.109 roots/s (+2.65%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 7.871 | 7.783 | -0.087 ms (-1.11%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 24941.416 | 25095.677 | +154.261 roots/s (+0.62%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 183.047 | 183.117 | +0.070 KiB (+0.04%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 29.996 | 28.152 | -1.844 KiB (-6.15%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 64.672 | 64.733 | +0.062 KiB (+0.10%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 3.113 | 3.064 | -0.049 KiB (-1.57%) | 6 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 4.298 | 4.280 | -0.018 us/projection (-0.41%) | 9 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 234575.692 | 231743.784 | -2831.908 projections/s (-1.21%) | 9 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 37.535 | 37.535 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 45.827 | 45.827 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 460.703 | 460.703 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 139.859 | 139.859 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 5.531 | 5.381 | -0.150 us/projection (-2.71%) | 9 | within noise |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 188443.106 | 187545.799 | -897.307 projections/s (-0.48%) | 9 | within noise |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 40.730 | 40.730 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 61.998 | 61.998 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 460.703 | 460.703 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 190.984 | 190.984 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 7.837 | 7.782 | -0.055 ms (-0.70%) | 9 | within noise |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 25432.887 | 25748.171 | +315.284 roots/s (+1.24%) | 9 | within noise |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 8.665 | 8.596 | -0.069 ms (-0.80%) | 9 | within noise |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 23142.234 | 23220.152 | +77.918 roots/s (+0.34%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 15.247 | 15.248 | +0.001 ms (+0.00%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 13012.891 | 13162.839 | +149.948 roots/s (+1.15%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 15.142 | 15.156 | +0.014 ms (+0.09%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 13107.341 | 13153.027 | +45.686 roots/s (+0.35%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.elapsedUsPerRoot | 103.258 | 103.724 | +0.466 us/root (+0.45%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.peakKiB | 442.059 | 442.059 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.retainedKiB | 162.484 | 162.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.elapsedUsPerRoot | 103.043 | 103.405 | +0.362 us/root (+0.35%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.peakKiB | 447.270 | 447.270 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.retainedKiB | 162.484 | 162.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.elapsedUsPerRoot | 354.790 | 354.185 | -0.605 us/root (-0.17%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.peakKiB | 952.093 | 952.093 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.retainedKiB | 313.047 | 313.047 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.elapsedUsPerRoot | 356.697 | 358.415 | +1.719 us/root (+0.48%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.peakKiB | 955.663 | 955.663 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.retainedKiB | 313.047 | 313.047 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.elapsedUsPerRoot | 390.270 | 385.973 | -4.297 us/root (-1.10%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.peakKiB | 770.371 | 770.371 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.retainedKiB | 192.965 | 192.965 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.elapsedUsPerRoot | 383.844 | 384.467 | +0.624 us/root (+0.16%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.peakKiB | 774.168 | 774.168 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.retainedKiB | 192.965 | 192.965 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.elapsedUsPerRoot | 847.639 | 847.417 | -0.223 us/root (-0.03%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.peakKiB | 1298.807 | 1298.807 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.retainedKiB | 271.797 | 271.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.elapsedUsPerRoot | 851.977 | 862.768 | +10.792 us/root (+1.27%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.peakKiB | 1302.635 | 1302.635 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.retainedKiB | 271.797 | 271.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.elapsedUsPerRoot | 740.081 | 751.283 | +11.202 us/root (+1.51%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.peakKiB | 689.181 | 689.181 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.elapsedUsPerRoot | 735.777 | 741.904 | +6.126 us/root (+0.83%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.peakKiB | 692.751 | 692.751 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.elapsedUsPerRoot | 281.051 | 280.573 | -0.478 us/root (-0.17%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.peakKiB | 655.274 | 655.274 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.elapsedUsPerRoot | 279.565 | 280.940 | +1.375 us/root (+0.49%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.peakKiB | 658.845 | 658.845 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.elapsedUsPerRoot | 143.994 | 144.564 | +0.570 us/root (+0.40%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.peakKiB | 634.207 | 634.207 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.retainedKiB | 354.480 | 354.480 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.elapsedUsPerRoot | 144.932 | 145.108 | +0.176 us/root (+0.12%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.peakKiB | 639.418 | 639.418 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.retainedKiB | 354.480 | 354.480 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.elapsedUsPerRoot | 153.419 | 150.009 | -3.410 us/root (-2.22%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.peakKiB | 646.176 | 646.176 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.retainedKiB | 366.484 | 366.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.elapsedUsPerRoot | 150.486 | 149.950 | -0.535 us/root (-0.36%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.peakKiB | 651.387 | 651.387 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.retainedKiB | 366.484 | 366.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.elapsedUsPerRoot | 508.230 | 504.777 | -3.453 us/root (-0.68%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.peakKiB | 827.571 | 827.571 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.retainedKiB | 277.984 | 277.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.elapsedUsPerRoot | 509.371 | 510.993 | +1.622 us/root (+0.32%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.peakKiB | 831.142 | 831.142 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.retainedKiB | 277.984 | 277.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.elapsedUsPerRoot | 750.003 | 753.665 | +3.663 us/root (+0.49%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.peakKiB | 934.302 | 936.304 | +2.002 KiB (+0.21%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.retainedKiB | 302.832 | 303.467 | +0.635 KiB (+0.21%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.elapsedUsPerRoot | 750.294 | 762.375 | +12.081 us/root (+1.61%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.peakKiB | 952.618 | 937.481 | -15.137 KiB (-1.59%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.retainedKiB | 303.223 | 303.564 | +0.342 KiB (+0.11%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.elapsedUsPerRoot | 513.401 | 515.780 | +2.379 us/root (+0.46%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.peakKiB | 1277.242 | 1277.242 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.retainedKiB | 321.297 | 321.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.elapsedUsPerRoot | 514.975 | 511.044 | -3.931 us/root (-0.76%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.peakKiB | 1281.070 | 1281.070 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.retainedKiB | 321.297 | 321.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 29.052 | 28.849 | -0.203 us/root (-0.70%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 95.539 | 95.539 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.109 | 51.109 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 29.730 | 29.180 | -0.551 us/root (-1.85%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 99.250 | 99.250 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.109 | 51.109 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 42.129 | 43.197 | +1.068 us/root (+2.53%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 145.752 | 145.752 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.234 | 88.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 42.582 | 42.566 | -0.016 us/root (-0.04%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 149.158 | 149.158 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.234 | 88.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 61.552 | 60.350 | -1.202 us/root (-1.95%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 220.354 | 220.354 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.734 | 137.734 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 61.171 | 60.478 | -0.693 us/root (-1.13%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 224.174 | 224.174 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.734 | 137.734 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 20.629 | 20.944 | +0.315 us/root (+1.53%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 58.370 | 58.370 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.359 | 24.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 21.906 | 21.388 | -0.518 us/root (-2.37%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 65.917 | 65.917 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.359 | 24.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 141.066 | 140.773 | -0.293 us/root (-0.21%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 624.949 | 624.949 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.359 | 428.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 140.263 | 141.229 | +0.966 us/root (+0.69%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 629.922 | 629.922 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.359 | 428.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 52.771 | 52.576 | -0.195 us/root (-0.37%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 193.785 | 193.785 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.359 | 125.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 52.340 | 52.224 | -0.116 us/root (-0.22%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 197.992 | 197.992 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.359 | 125.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 46.595 | 44.882 | -1.714 us/root (-3.68%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 125.427 | 125.427 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.203 | 36.203 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 45.711 | 45.529 | -0.182 us/root (-0.40%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 129.138 | 129.138 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.203 | 36.203 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 50.191 | 50.009 | -0.182 us/root (-0.36%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 217.340 | 217.340 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.984 | 136.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 51.082 | 50.155 | -0.927 us/root (-1.81%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 222.434 | 222.434 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.984 | 136.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 134.483 | 133.833 | -0.650 us/root (-0.48%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 760.059 | 760.059 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.484 | 480.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 135.000 | 132.728 | -2.272 us/root (-1.68%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 765.152 | 765.152 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.484 | 480.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 226.917 | 224.250 | -2.667 us (-1.18%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 28.824 | 28.824 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 22.754 | 22.754 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 327.500 | 330.125 | +2.625 us (+0.80%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 38.890 | 38.890 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 31.702 | 31.702 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 433.000 | 431.042 | -1.958 us (-0.45%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 47.736 | 47.736 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 40.127 | 40.123 | -0.004 KiB (-0.01%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 77.042 | 82.917 | +5.875 us (+7.63%) | 9 | slower |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 17.204 | 17.204 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 11.880 | 11.880 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 77.125 | 85.417 | +8.292 us (+10.75%) | 9 | slower |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 17.352 | 17.348 | -0.004 KiB (-0.02%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 12.168 | 12.168 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 77.167 | 77.292 | +0.125 us (+0.16%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 17.204 | 17.204 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 11.880 | 11.880 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 78.958 | 78.166 | -0.792 us (-1.00%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 17.352 | 17.352 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 12.168 | 12.168 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 74.834 | 78.750 | +3.916 us (+5.23%) | 9 | slower |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 17.205 | 17.205 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 11.881 | 11.877 | -0.004 KiB (-0.03%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 80.459 | 82.292 | +1.833 us (+2.28%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 17.353 | 17.353 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 12.169 | 12.169 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 1.917 | 1.917 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 2.292 | 2.250 | -0.042 us (-1.83%) | 9 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 2.750 | 2.792 | +0.042 us (+1.52%) | 9 | within noise |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | result-held-metadata | control-held | large.closed.retainedKiB | 76.867 | 76.867 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | result-held-metadata | control-held | large.shared.retainedKiB | 55.297 | 55.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | result-held-metadata | control-held | small.closed.retainedKiB | 126.336 | 126.336 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | result-held-metadata | control-held | small.shared.retainedKiB | 118.828 | 118.828 | +0.000 KiB (+0.00%) | 3 | within noise |

## write-lowering

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 168.292 | 177.250 | +8.958 us/row (+5.32%) | 9 | slower |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 848.000 | 848.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 8594.000 | 9036.000 | +442.000 B/row (+5.14%) | 9 | larger |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 169.125 | 183.834 | +14.709 us/row (+8.70%) | 9 | slower |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 848.000 | 848.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 9506.000 | 10013.000 | +507.000 B/row (+5.33%) | 9 | larger |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 209.416 | 224.833 | +15.417 us/row (+7.36%) | 9 | slower |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 848.000 | 848.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 6967.000 | 7410.000 | +443.000 B/row (+6.36%) | 9 | larger |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 184.375 | 200.500 | +16.125 us/row (+8.75%) | 9 | slower |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 848.000 | 848.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 7623.000 | 8131.000 | +508.000 B/row (+6.66%) | 9 | larger |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 224.875 | 232.167 | +7.292 us/row (+3.24%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1128.000 | 1128.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 11357.000 | 11800.000 | +443.000 B/row (+3.90%) | 9 | larger |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 209.458 | 214.000 | +4.542 us/row (+2.17%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1128.000 | 1128.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 12350.000 | 12858.000 | +508.000 B/row (+4.11%) | 9 | larger |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 444.042 | 445.250 | +1.208 us/row (+0.27%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2248.000 | 2248.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 19673.000 | 20116.000 | +443.000 B/row (+2.25%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 350.458 | 363.125 | +12.667 us/row (+3.61%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2248.000 | 2248.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 22890.000 | 23398.000 | +508.000 B/row (+2.22%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 282.250 | 280.916 | -1.334 us/row (-0.47%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 1624.000 | 1624.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 13615.000 | 18643.000 | +5028.000 B/row (+36.93%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 268.333 | 256.542 | -11.791 us/row (-4.39%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 1656.000 | 1656.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 14275.000 | 19119.000 | +4844.000 B/row (+33.93%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 275.708 | 269.416 | -6.292 us/row (-2.28%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 1624.000 | 1624.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 14617.000 | 17838.000 | +3221.000 B/row (+22.04%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 264.417 | 254.042 | -10.375 us/row (-3.92%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 1656.000 | 1656.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 15037.000 | 18314.000 | +3277.000 B/row (+21.79%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | elapsedUs | 439.041 | 431.792 | -7.249 us/row (-1.65%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | transientBytes | 19807.000 | 24587.000 | +4780.000 B/row (+24.13%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | elapsedUs | 425.500 | 418.875 | -6.625 us/row (-1.56%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | transientBytes | 20801.000 | 24070.000 | +3269.000 B/row (+15.72%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | elapsedUs | 463.500 | 458.916 | -4.584 us/row (-0.99%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | retainedBytes | 2040.000 | 2040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | transientBytes | 19775.000 | 24555.000 | +4780.000 B/row (+24.17%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | elapsedUs | 450.250 | 424.583 | -25.667 us/row (-5.70%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | transientBytes | 19807.000 | 24587.000 | +4780.000 B/row (+24.13%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | elapsedUs | 440.583 | 441.459 | +0.876 us/row (+0.20%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | retainedBytes | 2040.000 | 2040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | transientBytes | 20769.000 | 24038.000 | +3269.000 B/row (+15.74%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | elapsedUs | 433.208 | 418.291 | -14.917 us/row (-3.44%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | transientBytes | 20801.000 | 24070.000 | +3269.000 B/row (+15.72%) | 9 | larger |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 120.958 | 124.000 | +3.042 us/row (+2.51%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1544.000 | 1544.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 7860.000 | 7892.000 | +32.000 B/row (+0.41%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 116.750 | 124.000 | +7.250 us/row (+6.21%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1544.000 | 1544.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 8268.000 | 8292.000 | +24.000 B/row (+0.29%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 155.042 | 160.042 | +5.000 us/row (+3.22%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2216.000 | 2216.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 9621.000 | 9653.000 | +32.000 B/row (+0.33%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 155.833 | 157.541 | +1.708 us/row (+1.10%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2216.000 | 2216.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 9913.000 | 9937.000 | +24.000 B/row (+0.24%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 202.417 | 208.459 | +6.042 us/row (+2.98%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3112.000 | 3112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 12914.000 | 12882.000 | -32.000 B/row (-0.25%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 199.500 | 209.583 | +10.083 us/row (+5.05%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3112.000 | 3112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 13024.000 | 12992.000 | -32.000 B/row (-0.25%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 94.875 | 96.833 | +1.958 us/row (+2.06%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1040.000 | 1040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 6825.000 | 6857.000 | +32.000 B/row (+0.47%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 94.750 | 100.125 | +5.375 us/row (+5.67%) | 9 | slower |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1040.000 | 1040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 6983.000 | 7007.000 | +24.000 B/row (+0.34%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 427.667 | 439.625 | +11.958 us/row (+2.80%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8504.000 | 8504.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 26784.000 | 26816.000 | +32.000 B/row (+0.12%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 430.042 | 434.334 | +4.292 us/row (+1.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8504.000 | 8504.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 27083.000 | 27107.000 | +24.000 B/row (+0.09%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 183.334 | 185.833 | +2.499 us/row (+1.36%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 2936.000 | 2936.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 11328.000 | 11360.000 | +32.000 B/row (+0.28%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 181.042 | 184.541 | +3.499 us/row (+1.93%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 2936.000 | 2936.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 11660.000 | 11684.000 | +24.000 B/row (+0.21%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 161.666 | 167.667 | +6.001 us/row (+3.71%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1544.000 | 1544.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 7673.000 | 7705.000 | +32.000 B/row (+0.42%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 163.209 | 166.083 | +2.874 us/row (+1.76%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1544.000 | 1544.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 8065.000 | 8089.000 | +24.000 B/row (+0.30%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 201.041 | 205.625 | +4.584 us/row (+2.28%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2384.000 | 2384.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 10855.000 | 10887.000 | +32.000 B/row (+0.29%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 205.334 | 204.084 | -1.250 us/row (-0.61%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2384.000 | 2384.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 11304.000 | 11328.000 | +24.000 B/row (+0.21%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 529.292 | 536.792 | +7.500 us/row (+1.42%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5744.000 | 5744.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23095.000 | 23127.000 | +32.000 B/row (+0.14%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 527.792 | 533.833 | +6.041 us/row (+1.14%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5744.000 | 5744.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 24648.000 | 24672.000 | +24.000 B/row (+0.10%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 121.958 | 127.375 | +5.417 us/row (+4.44%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 1832.000 | 1832.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 7277.000 | 7245.000 | -32.000 B/row (-0.44%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 116.292 | 117.209 | +0.917 us/row (+0.79%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 1864.000 | 1864.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 8141.000 | 8109.000 | -32.000 B/row (-0.39%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 136.958 | 136.958 | +0.000 us/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 1832.000 | 1832.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 8201.000 | 8169.000 | -32.000 B/row (-0.39%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 122.333 | 124.750 | +2.417 us/row (+1.98%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 1864.000 | 1864.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 9065.000 | 9033.000 | -32.000 B/row (-0.35%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.columns.wire | elapsedUs | 193.459 | 188.458 | -5.001 us/row (-2.59%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-patch.columns.wire | retainedBytes | 2432.000 | 2432.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-patch.columns.wire | transientBytes | 12752.000 | 12752.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.document.wire | elapsedUs | 223.584 | 222.208 | -1.376 us/row (-0.62%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-patch.document.wire | retainedBytes | 2432.000 | 2432.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-patch.document.wire | transientBytes | 14827.000 | 14827.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.typed | elapsedUs | 198.500 | 202.791 | +4.291 us/row (+2.16%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-replace.columns.typed | retainedBytes | 2400.000 | 2400.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-replace.columns.typed | transientBytes | 12680.000 | 12680.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.wire | elapsedUs | 185.542 | 192.958 | +7.416 us/row (+4.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-replace.columns.wire | retainedBytes | 2432.000 | 2432.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-replace.columns.wire | transientBytes | 12748.000 | 12748.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.typed | elapsedUs | 229.916 | 237.125 | +7.209 us/row (+3.14%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-replace.document.typed | retainedBytes | 2400.000 | 2400.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-replace.document.typed | transientBytes | 14756.000 | 14756.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.wire | elapsedUs | 218.666 | 227.500 | +8.834 us/row (+4.04%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-replace.document.wire | retainedBytes | 2432.000 | 2432.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-replace.document.wire | transientBytes | 14823.000 | 14823.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 174.083 | 186.250 | +12.167 us/row (+6.99%) | 9 | slower |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 1576.000 | 1576.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 9859.000 | 10314.000 | +455.000 B/row (+4.62%) | 9 | larger |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 166.750 | 180.750 | +14.000 us/row (+8.40%) | 9 | slower |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 1608.000 | 1608.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 10463.000 | 10918.000 | +455.000 B/row (+4.35%) | 9 | larger |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 186.250 | 203.958 | +17.708 us/row (+9.51%) | 9 | slower |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 1576.000 | 1576.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 10996.000 | 11508.000 | +512.000 B/row (+4.66%) | 9 | larger |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 177.750 | 188.125 | +10.375 us/row (+5.84%) | 9 | slower |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 1608.000 | 1608.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 11360.000 | 11872.000 | +512.000 B/row (+4.51%) | 9 | larger |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 122.708 | 124.792 | +2.084 us/row (+1.70%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1768.000 | 1768.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 9739.000 | 9851.000 | +112.000 B/row (+1.15%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 121.458 | 125.250 | +3.792 us/row (+3.12%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1960.000 | 1960.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 10099.000 | 10211.000 | +112.000 B/row (+1.11%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 119.375 | 123.250 | +3.875 us/row (+3.25%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 1768.000 | 1768.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 9518.000 | 9574.000 | +56.000 B/row (+0.59%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 121.833 | 127.292 | +5.459 us/row (+4.48%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 1960.000 | 1960.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 9918.000 | 9974.000 | +56.000 B/row (+0.56%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | elapsedUs | 309.833 | 321.459 | +11.626 us/row (+3.75%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | transientBytes | 18031.000 | 17711.000 | -320.000 B/row (-1.77%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | elapsedUs | 318.125 | 327.167 | +9.042 us/row (+2.84%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.document.wire | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-patch.document.wire | transientBytes | 18632.000 | 18312.000 | -320.000 B/row (-1.72%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | elapsedUs | 326.500 | 334.333 | +7.833 us/row (+2.40%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | retainedBytes | 1992.000 | 1992.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | transientBytes | 17999.000 | 17679.000 | -320.000 B/row (-1.78%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | elapsedUs | 307.375 | 324.334 | +16.959 us/row (+5.52%) | 9 | slower |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | transientBytes | 18031.000 | 17711.000 | -320.000 B/row (-1.77%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | elapsedUs | 333.291 | 341.000 | +7.709 us/row (+2.31%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.typed | retainedBytes | 1992.000 | 1992.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.typed | transientBytes | 18600.000 | 18280.000 | -320.000 B/row (-1.72%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | elapsedUs | 324.542 | 327.750 | +3.208 us/row (+0.99%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.wire | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.wire | transientBytes | 18632.000 | 18312.000 | -320.000 B/row (-1.72%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 31.417 | 31.834 | +0.417 us/row (+1.33%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 3642.000 | 3642.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 26.167 | 27.000 | +0.833 us/row (+3.18%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 3590.000 | 3590.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 32.875 | 32.459 | -0.416 us/row (-1.27%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 3644.000 | 3644.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 26.042 | 26.875 | +0.833 us/row (+3.20%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 3593.000 | 3593.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3329.833 | 3354.667 | +24.834 us (+0.75%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | retainedBytes | 427360.000 | 427360.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 439696.000 | 439696.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | 309.000 | 302.709 | -6.291 us (-2.04%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | 24056.000 | 24056.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared.family | transientBytes | 28416.000 | 28416.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 20.568 | 19.936 | -0.633 us/row (-3.08%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 915.438 | 915.500 | +0.062 B/row (+0.01%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 1822.250 | 1822.250 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 20.944 | 20.653 | -0.290 us/row (-1.39%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1916.938 | 1917.000 | +0.062 B/row (+0.00%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2222.328 | 2222.328 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 23.820 | 24.969 | +1.148 us/row (+4.82%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1046.750 | 1047.000 | +0.250 B/row (+0.02%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2266.375 | 2266.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 24.889 | 26.461 | +1.572 us/row (+6.31%) | 9 | slower |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2052.750 | 2053.000 | +0.250 B/row (+0.01%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 2588.688 | 2588.688 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 40.307 | 40.896 | +0.589 us/row (+1.46%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1580.000 | 1581.000 | +1.000 B/row (+0.06%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 3734.500 | 3734.500 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 41.177 | 42.021 | +0.844 us/row (+2.05%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2604.000 | 2605.000 | +1.000 B/row (+0.04%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 3966.750 | 3966.750 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.columns | elapsedUs | 131.974 | 129.738 | -2.236 us/row (-1.69%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.columns | retainedBytes | 1554.410 | 1565.762 | +11.352 B/row (+0.73%) | 1 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.columns | transientBytes | 2225.117 | 2204.742 | -20.375 B/row (-0.92%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.document | elapsedUs | 123.045 | 122.282 | -0.763 us/row (-0.62%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.document | retainedBytes | 1757.641 | 1769.188 | +11.547 B/row (+0.66%) | 1 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.document | transientBytes | 2693.172 | 2673.516 | -19.656 B/row (-0.73%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.unchanged.objects-128.document | elapsedUs | 50.717 | 51.361 | +0.643 us/row (+1.27%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.unchanged.objects-128.document | retainedBytes | 137.508 | 148.664 | +11.156 B/row (+8.11%) | 1 | larger |
| 3.13 | predicate-flush | predicate-flush.unchanged.objects-128.document | transientBytes | 1365.625 | 1372.406 | +6.781 B/row (+0.50%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.wide.history-128.document | elapsedUs | 70.537 | 71.495 | +0.958 us/row (+1.36%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.wide.history-128.document | retainedBytes | 1313.721 | 1313.566 | -0.155 B/row (-0.01%) | 1 | within noise |
| 3.13 | predicate-flush | predicate-flush.wide.history-128.document | transientBytes | 6376.395 | 6373.853 | -2.543 B/row (-0.04%) | 9 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | elapsedUs | 61.000 | 63.542 | +2.542 us/row (+4.17%) | 9 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | retainedBytes | 8176.000 | 8184.000 | +8.000 B/row (+0.10%) | 1 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | transientBytes | 7696.000 | 7696.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 182.083 | 184.708 | +2.625 us/row (+1.44%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 856.000 | 856.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 9306.000 | 9716.000 | +410.000 B/row (+4.41%) | 9 | larger |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 184.083 | 195.875 | +11.792 us/row (+6.41%) | 9 | slower |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 856.000 | 856.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 10282.000 | 10853.000 | +571.000 B/row (+5.55%) | 9 | larger |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 218.875 | 222.167 | +3.292 us/row (+1.50%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 856.000 | 856.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 7631.000 | 8130.000 | +499.000 B/row (+6.54%) | 9 | larger |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 192.666 | 207.709 | +15.043 us/row (+7.81%) | 9 | slower |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 856.000 | 856.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 8415.000 | 8987.000 | +572.000 B/row (+6.80%) | 9 | larger |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 236.708 | 233.250 | -3.458 us/row (-1.46%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1136.000 | 1136.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 12093.000 | 12592.000 | +499.000 B/row (+4.13%) | 9 | larger |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 221.542 | 215.875 | -5.667 us/row (-2.56%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1136.000 | 1136.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13214.000 | 13786.000 | +572.000 B/row (+4.33%) | 9 | larger |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 420.791 | 429.291 | +8.500 us/row (+2.02%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2256.000 | 2256.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 20353.000 | 20852.000 | +499.000 B/row (+2.45%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 347.833 | 348.041 | +0.208 us/row (+0.06%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2256.000 | 2256.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23698.000 | 24270.000 | +572.000 B/row (+2.41%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 296.208 | 277.958 | -18.250 us/row (-6.16%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 1640.000 | 1640.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 14135.000 | 19483.000 | +5348.000 B/row (+37.84%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 279.250 | 263.250 | -16.000 us/row (-5.73%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 1672.000 | 1672.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15015.000 | 20123.000 | +5108.000 B/row (+34.02%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 294.250 | 274.041 | -20.209 us/row (-6.87%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 1640.000 | 1640.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15185.000 | 18542.000 | +3357.000 B/row (+22.11%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 282.542 | 254.625 | -27.917 us/row (-9.88%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 1672.000 | 1672.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 15825.000 | 19182.000 | +3357.000 B/row (+21.21%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | elapsedUs | 453.666 | 433.833 | -19.833 us/row (-4.37%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | transientBytes | 19507.000 | 24591.000 | +5084.000 B/row (+26.06%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | elapsedUs | 462.458 | 427.708 | -34.750 us/row (-7.51%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | transientBytes | 20973.000 | 24410.000 | +3437.000 B/row (+16.39%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | elapsedUs | 463.334 | 457.667 | -5.667 us/row (-1.22%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | transientBytes | 19479.000 | 24563.000 | +5084.000 B/row (+26.10%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | elapsedUs | 449.583 | 432.000 | -17.583 us/row (-3.91%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | transientBytes | 19507.000 | 24591.000 | +5084.000 B/row (+26.06%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | elapsedUs | 447.125 | 458.916 | +11.791 us/row (+2.64%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | transientBytes | 20945.000 | 24382.000 | +3437.000 B/row (+16.41%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | elapsedUs | 453.416 | 428.583 | -24.833 us/row (-5.48%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | transientBytes | 20973.000 | 24410.000 | +3437.000 B/row (+16.39%) | 9 | larger |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 131.667 | 133.250 | +1.583 us/row (+1.20%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1560.000 | 1560.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 8508.000 | 8556.000 | +48.000 B/row (+0.56%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 127.125 | 130.291 | +3.166 us/row (+2.49%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1560.000 | 1560.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 8980.000 | 9020.000 | +40.000 B/row (+0.45%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 161.375 | 165.709 | +4.334 us/row (+2.69%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2232.000 | 2232.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10365.000 | 10413.000 | +48.000 B/row (+0.46%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 159.459 | 166.083 | +6.624 us/row (+4.15%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2232.000 | 2232.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 10729.000 | 10769.000 | +40.000 B/row (+0.37%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 208.542 | 206.333 | -2.209 us/row (-1.06%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3128.000 | 3128.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 13778.000 | 13754.000 | -24.000 B/row (-0.17%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 209.292 | 207.833 | -1.459 us/row (-0.70%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3128.000 | 3128.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 13936.000 | 13912.000 | -24.000 B/row (-0.17%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 106.917 | 108.167 | +1.250 us/row (+1.17%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1048.000 | 1048.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7457.000 | 7457.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 103.500 | 108.000 | +4.500 us/row (+4.35%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1048.000 | 1048.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 7631.000 | 7671.000 | +40.000 B/row (+0.52%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 408.416 | 424.667 | +16.251 us/row (+3.98%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8520.000 | 8520.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27424.000 | 27472.000 | +48.000 B/row (+0.18%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 413.542 | 411.083 | -2.459 us/row (-0.59%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8520.000 | 8520.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 27787.000 | 27827.000 | +40.000 B/row (+0.14%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 185.458 | 188.500 | +3.042 us/row (+1.64%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 2952.000 | 2952.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 11968.000 | 12016.000 | +48.000 B/row (+0.40%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 185.209 | 187.708 | +2.499 us/row (+1.35%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 2952.000 | 2952.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 12380.000 | 12420.000 | +40.000 B/row (+0.32%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 167.542 | 174.041 | +6.499 us/row (+3.88%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1560.000 | 1560.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8361.000 | 8409.000 | +48.000 B/row (+0.57%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 173.500 | 171.000 | -2.500 us/row (-1.44%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1560.000 | 1560.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 8817.000 | 8857.000 | +40.000 B/row (+0.45%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 205.417 | 205.208 | -0.209 us/row (-0.10%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2400.000 | 2400.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11559.000 | 11607.000 | +48.000 B/row (+0.42%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 201.667 | 206.375 | +4.708 us/row (+2.33%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2400.000 | 2400.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 12072.000 | 12112.000 | +40.000 B/row (+0.33%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 497.417 | 497.291 | -0.126 us/row (-0.03%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23799.000 | 23847.000 | +48.000 B/row (+0.20%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 496.875 | 504.125 | +7.250 us/row (+1.46%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 25416.000 | 25456.000 | +40.000 B/row (+0.16%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | elapsedUs | 449.834 | 469.833 | +19.999 us/row (+4.45%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | transientBytes | 20765.000 | 20813.000 | +48.000 B/row (+0.23%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | elapsedUs | 506.833 | 515.875 | +9.042 us/row (+1.78%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | transientBytes | 20973.000 | 21021.000 | +48.000 B/row (+0.23%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | elapsedUs | 447.541 | 453.666 | +6.125 us/row (+1.37%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | transientBytes | 21782.000 | 21822.000 | +40.000 B/row (+0.18%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | elapsedUs | 498.459 | 513.375 | +14.916 us/row (+2.99%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | transientBytes | 21990.000 | 22030.000 | +40.000 B/row (+0.18%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | elapsedUs | 506.625 | 518.125 | +11.500 us/row (+2.27%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | transientBytes | 44211.000 | 44259.000 | +48.000 B/row (+0.11%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | elapsedUs | 654.042 | 662.458 | +8.416 us/row (+1.29%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | retainedBytes | 15376.000 | 15376.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | transientBytes | 53827.000 | 53875.000 | +48.000 B/row (+0.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | elapsedUs | 505.875 | 517.750 | +11.875 us/row (+2.35%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | transientBytes | 47108.000 | 47148.000 | +40.000 B/row (+0.08%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | elapsedUs | 653.000 | 657.750 | +4.750 us/row (+0.73%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | retainedBytes | 15376.000 | 15376.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | transientBytes | 56724.000 | 56764.000 | +40.000 B/row (+0.07%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | elapsedUs | 557.958 | 573.083 | +15.125 us/row (+2.71%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | transientBytes | 32946.000 | 32994.000 | +48.000 B/row (+0.15%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | elapsedUs | 788.292 | 781.000 | -7.292 us/row (-0.93%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | transientBytes | 39290.000 | 39338.000 | +48.000 B/row (+0.12%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | elapsedUs | 564.792 | 576.250 | +11.458 us/row (+2.03%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | transientBytes | 34435.000 | 34475.000 | +40.000 B/row (+0.12%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | elapsedUs | 774.792 | 787.042 | +12.250 us/row (+1.58%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | transientBytes | 40779.000 | 40819.000 | +40.000 B/row (+0.10%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | elapsedUs | 972.667 | 960.292 | -12.375 us/row (-1.27%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | transientBytes | 35821.000 | 35869.000 | +48.000 B/row (+0.13%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | elapsedUs | 1747.542 | 1692.000 | -55.542 us/row (-3.18%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | retainedBytes | 29008.000 | 29008.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | transientBytes | 59161.000 | 59209.000 | +48.000 B/row (+0.08%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | elapsedUs | 958.958 | 957.666 | -1.292 us/row (-0.13%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | transientBytes | 37438.000 | 37478.000 | +40.000 B/row (+0.11%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | elapsedUs | 1685.667 | 1709.417 | +23.750 us/row (+1.41%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | retainedBytes | 29008.000 | 29008.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | transientBytes | 60778.000 | 60818.000 | +40.000 B/row (+0.07%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | elapsedUs | 830.500 | 826.875 | -3.625 us/row (-0.44%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | retainedBytes | 10368.000 | 10368.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | transientBytes | 30501.000 | 30549.000 | +48.000 B/row (+0.16%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | elapsedUs | 1190.792 | 1181.000 | -9.792 us/row (-0.82%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | retainedBytes | 10576.000 | 10576.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | transientBytes | 30709.000 | 30757.000 | +48.000 B/row (+0.16%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | elapsedUs | 816.458 | 830.292 | +13.834 us/row (+1.69%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | retainedBytes | 10368.000 | 10368.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | transientBytes | 31606.000 | 31646.000 | +40.000 B/row (+0.13%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | elapsedUs | 1173.875 | 1187.917 | +14.042 us/row (+1.20%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | retainedBytes | 10576.000 | 10576.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | transientBytes | 31814.000 | 31854.000 | +40.000 B/row (+0.13%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | elapsedUs | 513.208 | 508.167 | -5.041 us/row (-0.98%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | transientBytes | 21237.000 | 21285.000 | +48.000 B/row (+0.23%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | elapsedUs | 591.583 | 597.625 | +6.042 us/row (+1.02%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | transientBytes | 21445.000 | 21493.000 | +48.000 B/row (+0.22%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | elapsedUs | 512.583 | 510.125 | -2.458 us/row (-0.48%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | transientBytes | 22342.000 | 22382.000 | +40.000 B/row (+0.18%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | elapsedUs | 584.583 | 594.375 | +9.792 us/row (+1.68%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | transientBytes | 22550.000 | 22590.000 | +40.000 B/row (+0.18%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | elapsedUs | 458.584 | 469.625 | +11.041 us/row (+2.41%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | transientBytes | 21990.000 | 22038.000 | +48.000 B/row (+0.22%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | elapsedUs | 599.625 | 592.250 | -7.375 us/row (-1.23%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | retainedBytes | 12096.000 | 12096.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | transientBytes | 28286.000 | 28334.000 | +48.000 B/row (+0.17%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | elapsedUs | 462.792 | 472.000 | +9.208 us/row (+1.99%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | transientBytes | 23246.000 | 23286.000 | +40.000 B/row (+0.17%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | elapsedUs | 594.875 | 588.833 | -6.042 us/row (-1.02%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | retainedBytes | 12096.000 | 12096.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | transientBytes | 29542.000 | 29582.000 | +40.000 B/row (+0.14%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | elapsedUs | 487.417 | 495.667 | +8.250 us/row (+1.69%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | transientBytes | 22970.000 | 23018.000 | +48.000 B/row (+0.21%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | elapsedUs | 618.875 | 618.750 | -0.125 us/row (-0.02%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | transientBytes | 29322.000 | 29370.000 | +48.000 B/row (+0.16%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | elapsedUs | 477.958 | 484.333 | +6.375 us/row (+1.33%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | transientBytes | 24422.000 | 24462.000 | +40.000 B/row (+0.16%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | elapsedUs | 618.125 | 619.333 | +1.208 us/row (+0.20%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | transientBytes | 30774.000 | 30814.000 | +40.000 B/row (+0.13%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | elapsedUs | 614.500 | 618.500 | +4.000 us/row (+0.65%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | transientBytes | 24004.000 | 24052.000 | +48.000 B/row (+0.20%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | elapsedUs | 629.125 | 614.083 | -15.042 us/row (-2.39%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | transientBytes | 25621.000 | 25661.000 | +40.000 B/row (+0.16%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | elapsedUs | 622.292 | 627.000 | +4.708 us/row (+0.76%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | transientBytes | 35506.000 | 35554.000 | +48.000 B/row (+0.14%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | elapsedUs | 857.917 | 867.250 | +9.333 us/row (+1.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | transientBytes | 41850.000 | 41898.000 | +48.000 B/row (+0.11%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | elapsedUs | 613.208 | 622.417 | +9.209 us/row (+1.50%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | transientBytes | 37315.000 | 37355.000 | +40.000 B/row (+0.11%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | elapsedUs | 865.084 | 866.542 | +1.458 us/row (+0.17%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | transientBytes | 43659.000 | 43699.000 | +40.000 B/row (+0.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | elapsedUs | 720.625 | 713.250 | -7.375 us/row (-1.02%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | transientBytes | 41655.000 | 41703.000 | +48.000 B/row (+0.12%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | elapsedUs | 1072.042 | 1080.375 | +8.333 us/row (+0.78%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | retainedBytes | 15184.000 | 15184.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | transientBytes | 51435.000 | 51483.000 | +48.000 B/row (+0.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | elapsedUs | 707.084 | 706.583 | -0.501 us/row (-0.07%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | transientBytes | 44232.000 | 44272.000 | +40.000 B/row (+0.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | elapsedUs | 1081.375 | 1080.334 | -1.041 us/row (-0.10%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | retainedBytes | 15184.000 | 15184.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | transientBytes | 54012.000 | 54052.000 | +40.000 B/row (+0.07%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | elapsedUs | 819.708 | 816.500 | -3.208 us/row (-0.39%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | transientBytes | 46378.000 | 46426.000 | +48.000 B/row (+0.10%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | elapsedUs | 1132.959 | 1144.166 | +11.207 us/row (+0.99%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | retainedBytes | 26704.000 | 26704.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | transientBytes | 67322.000 | 67370.000 | +48.000 B/row (+0.07%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | elapsedUs | 816.125 | 809.333 | -6.792 us/row (-0.83%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | transientBytes | 49531.000 | 49571.000 | +40.000 B/row (+0.08%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | elapsedUs | 1139.709 | 1144.875 | +5.166 us/row (+0.45%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | retainedBytes | 26704.000 | 26704.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | transientBytes | 70475.000 | 70515.000 | +40.000 B/row (+0.06%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 132.291 | 134.584 | +2.293 us/row (+1.73%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 1872.000 | 1872.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 7829.000 | 7805.000 | -24.000 B/row (-0.31%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 122.833 | 127.083 | +4.250 us/row (+3.46%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 1904.000 | 1904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 8841.000 | 8817.000 | -24.000 B/row (-0.27%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 144.375 | 151.625 | +7.250 us/row (+5.02%) | 9 | slower |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 1872.000 | 1872.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 8849.000 | 8713.000 | -136.000 B/row (-1.54%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 134.750 | 136.458 | +1.708 us/row (+1.27%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 1904.000 | 1904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 9861.000 | 9725.000 | -136.000 B/row (-1.38%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.columns.wire | elapsedUs | 199.250 | 203.208 | +3.958 us/row (+1.99%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-patch.columns.wire | retainedBytes | 2464.000 | 2464.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-patch.columns.wire | transientBytes | 12788.000 | 12788.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.document.wire | elapsedUs | 235.125 | 233.875 | -1.250 us/row (-0.53%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-patch.document.wire | retainedBytes | 2464.000 | 2464.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-patch.document.wire | transientBytes | 15215.000 | 15215.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.typed | elapsedUs | 229.584 | 220.500 | -9.084 us/row (-3.96%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-replace.columns.typed | retainedBytes | 2432.000 | 2432.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-replace.columns.typed | transientBytes | 12648.000 | 12648.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.wire | elapsedUs | 201.959 | 200.708 | -1.251 us/row (-0.62%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-replace.columns.wire | retainedBytes | 2464.000 | 2464.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-replace.columns.wire | transientBytes | 12784.000 | 12784.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.typed | elapsedUs | 249.334 | 249.792 | +0.458 us/row (+0.18%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-replace.document.typed | retainedBytes | 2432.000 | 2432.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-replace.document.typed | transientBytes | 15076.000 | 15076.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.wire | elapsedUs | 232.667 | 233.500 | +0.833 us/row (+0.36%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-replace.document.wire | retainedBytes | 2464.000 | 2464.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-replace.document.wire | transientBytes | 15211.000 | 15211.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 190.917 | 195.292 | +4.375 us/row (+2.29%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 1592.000 | 1592.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 10555.000 | 11066.000 | +511.000 B/row (+4.84%) | 9 | larger |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 175.375 | 187.250 | +11.875 us/row (+6.77%) | 9 | slower |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 1624.000 | 1624.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 11307.000 | 11818.000 | +511.000 B/row (+4.52%) | 9 | larger |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 196.709 | 202.708 | +5.999 us/row (+3.05%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 1592.000 | 1592.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 11556.000 | 12132.000 | +576.000 B/row (+4.98%) | 9 | larger |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 192.250 | 194.625 | +2.375 us/row (+1.24%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 1624.000 | 1624.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 12132.000 | 12708.000 | +576.000 B/row (+4.75%) | 9 | larger |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 137.709 | 135.000 | -2.709 us/row (-1.97%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1784.000 | 1784.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 10451.000 | 10587.000 | +136.000 B/row (+1.30%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 132.459 | 136.083 | +3.624 us/row (+2.74%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1992.000 | 1992.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 10899.000 | 11035.000 | +136.000 B/row (+1.25%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 133.250 | 145.250 | +12.000 us/row (+9.01%) | 9 | slower |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 1784.000 | 1784.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 10326.000 | 10342.000 | +16.000 B/row (+0.15%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 133.708 | 138.625 | +4.917 us/row (+3.68%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 1992.000 | 1992.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 10750.000 | 10766.000 | +16.000 B/row (+0.15%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | elapsedUs | 338.125 | 343.625 | +5.500 us/row (+1.63%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | retainedBytes | 2056.000 | 2056.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | transientBytes | 18653.000 | 18325.000 | -328.000 B/row (-1.76%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | elapsedUs | 344.291 | 345.042 | +0.751 us/row (+0.22%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-patch.document.wire | retainedBytes | 2056.000 | 2056.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-patch.document.wire | transientBytes | 19142.000 | 18814.000 | -328.000 B/row (-1.71%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | elapsedUs | 340.917 | 348.583 | +7.666 us/row (+2.25%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | transientBytes | 18625.000 | 18297.000 | -328.000 B/row (-1.76%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | elapsedUs | 324.459 | 334.833 | +10.374 us/row (+3.20%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | retainedBytes | 2056.000 | 2056.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | transientBytes | 18653.000 | 18325.000 | -328.000 B/row (-1.76%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | elapsedUs | 346.125 | 366.792 | +20.667 us/row (+5.97%) | 9 | slower |
| 3.14 | keyed-write | txtime.target-replace.document.typed | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.typed | transientBytes | 19114.000 | 18786.000 | -328.000 B/row (-1.72%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | elapsedUs | 330.916 | 343.250 | +12.334 us/row (+3.73%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.wire | retainedBytes | 2056.000 | 2056.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.wire | transientBytes | 19142.000 | 18814.000 | -328.000 B/row (-1.71%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 33.833 | 34.125 | +0.292 us/row (+0.86%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 4010.000 | 4010.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 28.208 | 27.750 | -0.458 us/row (-1.62%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 3742.000 | 3742.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 34.541 | 34.167 | -0.374 us/row (-1.08%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 4012.000 | 4012.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 28.083 | 28.333 | +0.250 us/row (+0.89%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 3745.000 | 3745.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3023.916 | 3005.750 | -18.166 us (-0.60%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared | retainedBytes | 439024.000 | 439024.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 445848.000 | 445848.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | 292.500 | 295.583 | +3.083 us (+1.05%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | 24504.000 | 24504.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared.family | transientBytes | 28648.000 | 28648.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 17.683 | 17.707 | +0.025 us/row (+0.14%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 989.094 | 989.156 | +0.062 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 1872.203 | 1872.203 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 18.547 | 18.230 | -0.317 us/row (-1.71%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1990.719 | 1990.781 | +0.062 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2317.531 | 2317.531 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 21.870 | 21.729 | -0.141 us/row (-0.64%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1149.375 | 1149.625 | +0.250 B/row (+0.02%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2360.000 | 2360.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 22.158 | 22.277 | +0.120 us/row (+0.54%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2155.875 | 2156.125 | +0.250 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 2705.500 | 2705.500 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 37.547 | 37.911 | +0.364 us/row (+0.97%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1798.500 | 1799.500 | +1.000 B/row (+0.06%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 3918.000 | 3918.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 38.016 | 39.984 | +1.969 us/row (+5.18%) | 9 | slower |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2824.500 | 2825.500 | +1.000 B/row (+0.04%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 4170.000 | 4170.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | elapsedUs | 101.766 | 99.927 | -1.839 us/row (-1.81%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | retainedBytes | 3222.500 | 3223.500 | +1.000 B/row (+0.03%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | transientBytes | 16310.000 | 16310.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | elapsedUs | 100.792 | 102.510 | +1.719 us/row (+1.71%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | retainedBytes | 16698.500 | 16699.500 | +1.000 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | transientBytes | 18017.000 | 18017.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | elapsedUs | 286.214 | 286.938 | +0.724 us/row (+0.25%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | retainedBytes | 13022.500 | 13023.500 | +1.000 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | transientBytes | 32027.125 | 32027.125 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | elapsedUs | 288.635 | 288.010 | -0.625 us/row (-0.22%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | retainedBytes | 40514.500 | 40515.500 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | transientBytes | 41966.125 | 41966.125 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | elapsedUs | 335.849 | 334.240 | -1.609 us/row (-0.48%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | retainedBytes | 9622.500 | 9623.500 | +1.000 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | transientBytes | 27278.000 | 27278.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | elapsedUs | 332.339 | 335.177 | +2.839 us/row (+0.85%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | retainedBytes | 32890.500 | 32891.500 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | transientBytes | 34361.000 | 34361.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | elapsedUs | 664.948 | 650.281 | -14.667 us/row (-2.21%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | retainedBytes | 27222.500 | 27223.500 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | transientBytes | 32109.000 | 32109.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | elapsedUs | 662.182 | 647.266 | -14.917 us/row (-2.25%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | retainedBytes | 50874.500 | 50875.500 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | transientBytes | 52530.750 | 52530.750 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | elapsedUs | 532.552 | 534.203 | +1.651 us/row (+0.31%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | retainedBytes | 8022.500 | 8023.500 | +1.000 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | transientBytes | 21716.000 | 21716.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | elapsedUs | 538.484 | 534.734 | -3.750 us/row (-0.70%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | retainedBytes | 26106.500 | 26107.500 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | transientBytes | 27455.000 | 27455.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | elapsedUs | 230.114 | 230.786 | +0.672 us/row (+0.29%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | retainedBytes | 7830.500 | 7831.500 | +1.000 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | transientBytes | 20939.000 | 20939.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | elapsedUs | 232.536 | 228.875 | -3.661 us/row (-1.57%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | retainedBytes | 21306.500 | 21307.500 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | transientBytes | 22646.000 | 22646.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | elapsedUs | 142.771 | 145.036 | +2.266 us/row (+1.59%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | retainedBytes | 9622.000 | 9623.000 | +1.000 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | transientBytes | 22719.500 | 22719.500 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | elapsedUs | 145.042 | 142.656 | -2.385 us/row (-1.64%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | retainedBytes | 23098.000 | 23099.000 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | transientBytes | 24426.500 | 24426.500 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | elapsedUs | 149.854 | 153.552 | +3.698 us/row (+2.47%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | retainedBytes | 10006.500 | 10007.500 | +1.000 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | transientBytes | 23108.500 | 23108.500 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | elapsedUs | 149.526 | 149.427 | -0.099 us/row (-0.07%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | retainedBytes | 23482.500 | 23483.500 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | transientBytes | 24815.500 | 24815.500 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | elapsedUs | 130.792 | 132.870 | +2.078 us/row (+1.59%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | retainedBytes | 13398.500 | 13399.500 | +1.000 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | transientBytes | 26485.750 | 26485.750 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | elapsedUs | 132.740 | 133.359 | +0.620 us/row (+0.47%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | retainedBytes | 26874.500 | 26875.500 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | transientBytes | 28192.750 | 28192.750 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | elapsedUs | 435.354 | 420.453 | -14.901 us/row (-3.42%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | retainedBytes | 9622.500 | 9623.500 | +1.000 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | transientBytes | 28246.000 | 28246.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | elapsedUs | 425.198 | 432.594 | +7.396 us/row (+1.74%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | retainedBytes | 33850.500 | 33851.500 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | transientBytes | 35329.000 | 35329.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | elapsedUs | 634.412 | 615.943 | -18.469 us/row (-2.91%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | retainedBytes | 12822.500 | 12823.500 | +1.000 B/row (+0.01%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | transientBytes | 31095.750 | 31095.750 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | elapsedUs | 626.781 | 626.625 | -0.156 us/row (-0.02%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | retainedBytes | 39354.500 | 39355.500 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | transientBytes | 40851.750 | 40851.750 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | elapsedUs | 377.953 | 377.214 | -0.740 us/row (-0.20%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | retainedBytes | 24817.000 | 24818.000 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | transientBytes | 34671.500 | 34671.500 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | elapsedUs | 386.536 | 378.057 | -8.479 us/row (-2.19%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | retainedBytes | 53077.000 | 53078.000 | +1.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | transientBytes | 54522.500 | 54522.500 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.columns | elapsedUs | 122.569 | 121.750 | -0.819 us/row (-0.67%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.columns | retainedBytes | 1619.809 | 1630.730 | +10.922 B/row (+0.67%) | 1 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.columns | transientBytes | 1816.523 | 1828.242 | +11.719 B/row (+0.65%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.document | elapsedUs | 114.291 | 114.083 | -0.208 us/row (-0.18%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.document | retainedBytes | 1824.039 | 1835.742 | +11.703 B/row (+0.64%) | 1 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.document | transientBytes | 2421.711 | 2432.805 | +11.094 B/row (+0.46%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.unchanged.objects-128.document | elapsedUs | 44.846 | 45.966 | +1.120 us/row (+2.50%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.unchanged.objects-128.document | retainedBytes | 146.734 | 158.828 | +12.094 B/row (+8.24%) | 1 | larger |
| 3.14 | predicate-flush | predicate-flush.unchanged.objects-128.document | transientBytes | 1392.062 | 1402.594 | +10.531 B/row (+0.76%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.wide.history-128.document | elapsedUs | 66.598 | 66.522 | -0.076 us/row (-0.11%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.wide.history-128.document | retainedBytes | 1358.481 | 1357.101 | -1.380 B/row (-0.10%) | 1 | within noise |
| 3.14 | predicate-flush | predicate-flush.wide.history-128.document | transientBytes | 6475.233 | 6475.078 | -0.155 B/row (-0.00%) | 9 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | elapsedUs | 61.916 | 61.958 | +0.042 us/row (+0.07%) | 9 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | retainedBytes | 9356.000 | 9364.000 | +8.000 B/row (+0.09%) | 1 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | transientBytes | 8774.000 | 8774.000 | +0.000 B/row (+0.00%) | 9 | within noise |

Deltas are advisory and never ratchet the Budget Contract.
