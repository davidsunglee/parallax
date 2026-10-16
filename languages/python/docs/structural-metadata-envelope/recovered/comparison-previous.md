# Python cost report comparison

Timing deltas within 5% and byte deltas within 3% are read as noise; count deltas are exact. A cell present on one side alone, or whose unit differs, is not compared.

## feature-boundary

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | elapsedUs | 0.167 | 0.167 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | retainedBytes | 88.000 | 88.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | elapsedUs | 298.625 | 297.125 | -1.500 us (-0.50%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | peakBytes | 18246.000 | 18246.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | retainedBytes | 16512.000 | 16512.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | elapsedUs | 19.583 | 19.375 | -0.208 us (-1.06%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | peakBytes | 2886.000 | 2886.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | retainedBytes | 1152.000 | 1152.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-0.decode | elapsedUs | 0.209 | 0.209 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-0.decode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-0.decode | retainedBytes | 88.000 | 88.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-128.decode | elapsedUs | 32.000 | 32.000 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-128.decode | peakBytes | 2392.000 | 2392.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-128.decode | retainedBytes | 1152.000 | 1152.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-8.decode | elapsedUs | 2.375 | 2.375 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-8.decode | peakBytes | 704.000 | 704.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.integer.size-8.decode | retainedBytes | 192.000 | 192.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-0.decode | elapsedUs | 0.209 | 0.208 | -0.001 us (-0.48%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-0.decode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-0.decode | retainedBytes | 88.000 | 88.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-128.decode | elapsedUs | 12.333 | 11.625 | -0.708 us (-5.74%) | 9 | faster |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-128.decode | peakBytes | 2280.000 | 2280.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-128.decode | retainedBytes | 1152.000 | 1152.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-8.decode | elapsedUs | 1.042 | 1.000 | -0.042 us (-4.03%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-8.decode | peakBytes | 376.000 | 376.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-decode | scalar-collection.string.size-8.decode | retainedBytes | 192.000 | 192.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | elapsedUs | 0.125 | 0.125 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | elapsedUs | 246.000 | 246.083 | +0.083 us (+0.03%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | peakBytes | 8400.000 | 8400.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | retainedBytes | 6856.000 | 6856.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | elapsedUs | 15.708 | 15.792 | +0.084 us (+0.53%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | peakBytes | 1809.000 | 1809.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-0.encode | elapsedUs | 0.125 | 0.125 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-0.encode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-128.encode | elapsedUs | 48.792 | 48.875 | +0.083 us (+0.17%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-128.encode | peakBytes | 2336.000 | 2336.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-128.encode | retainedBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-8.encode | elapsedUs | 3.334 | 3.292 | -0.042 us (-1.26%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-8.encode | peakBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.integer.size-8.encode | retainedBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-0.encode | elapsedUs | 0.125 | 0.125 | +0.000 us (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-0.encode | peakBytes | 264.000 | 264.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-128.encode | elapsedUs | 66.625 | 64.750 | -1.875 us (-2.81%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-128.encode | peakBytes | 2336.000 | 2336.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-128.encode | retainedBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-8.encode | elapsedUs | 4.458 | 4.334 | -0.124 us (-2.78%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-8.encode | peakBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | scalar-collection-encode | scalar-collection.string.size-8.encode | retainedBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.nested-all.cold-plan | elapsedUs | 101.583 | 111.208 | +9.625 us (+9.48%) | 9 | slower |
| 3.13 | typed-cold-plan | predicate.nested-all.cold-plan | peakBytes | 15147.000 | 16051.000 | +904.000 B (+5.97%) | 9 | larger |
| 3.13 | typed-cold-plan | predicate.nested-all.cold-plan | retainedBytes | 9883.000 | 9891.000 | +8.000 B (+0.08%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | elapsedUs | 108.916 | 137.917 | +29.001 us (+26.63%) | 9 | slower |
| 3.13 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | peakBytes | 14889.000 | 17665.000 | +2776.000 B (+18.64%) | 9 | larger |
| 3.13 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | retainedBytes | 9705.000 | 9784.000 | +79.000 B (+0.81%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.scalar-any.cold-plan | elapsedUs | 94.000 | 97.209 | +3.209 us (+3.41%) | 9 | within noise |
| 3.13 | typed-cold-plan | predicate.scalar-any.cold-plan | peakBytes | 14582.000 | 15542.000 | +960.000 B (+6.58%) | 9 | larger |
| 3.13 | typed-cold-plan | predicate.scalar-any.cold-plan | retainedBytes | 9454.000 | 9462.000 | +8.000 B (+0.08%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.shallow-scalar.cold-plan | elapsedUs | 83.458 | 88.000 | +4.542 us (+5.44%) | 9 | slower |
| 3.13 | typed-cold-plan | predicate.shallow-scalar.cold-plan | peakBytes | 14198.000 | 15162.000 | +964.000 B (+6.79%) | 9 | larger |
| 3.13 | typed-cold-plan | predicate.shallow-scalar.cold-plan | retainedBytes | 8990.000 | 9002.000 | +12.000 B (+0.13%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | elapsedUs | 112.500 | 127.167 | +14.667 us (+13.04%) | 9 | slower |
| 3.13 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | peakBytes | 14741.000 | 16005.000 | +1264.000 B (+8.57%) | 9 | larger |
| 3.13 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | retainedBytes | 9533.000 | 9541.000 | +8.000 B (+0.08%) | 1 | within noise |
| 3.13 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | elapsedUs | 117.541 | 133.375 | +15.834 us (+13.47%) | 9 | slower |
| 3.13 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | peakBytes | 14965.000 | 16917.000 | +1952.000 B (+13.04%) | 9 | larger |
| 3.13 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | retainedBytes | 9461.000 | 9455.000 | -6.000 B (-0.06%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.nested-all.binding | elapsedUs | 9.333 | 9.750 | +0.417 us (+4.47%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.nested-all.binding | peakBytes | 3471.000 | 3471.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.nested-all.binding | retainedBytes | 368.000 | 368.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | elapsedUs | 13.875 | 14.084 | +0.209 us (+1.51%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | peakBytes | 3548.000 | 3548.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | retainedBytes | 424.000 | 424.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.scalar-any.binding | elapsedUs | 7.458 | 7.292 | -0.166 us (-2.23%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.scalar-any.binding | peakBytes | 2998.000 | 2998.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.scalar-any.binding | retainedBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.shallow-scalar.binding | elapsedUs | 6.500 | 6.417 | -0.083 us (-1.28%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.shallow-scalar.binding | peakBytes | 2982.000 | 2982.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.shallow-scalar.binding | retainedBytes | 200.000 | 200.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.subtype-narrowing.binding | elapsedUs | 14.375 | 14.667 | +0.292 us (+2.03%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.subtype-narrowing.binding | peakBytes | 3878.000 | 3878.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.subtype-narrowing.binding | retainedBytes | 424.000 | 424.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | typed-predicate-binding | predicate.two-hop-to-one.binding | elapsedUs | 17.708 | 17.250 | -0.458 us (-2.59%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.two-hop-to-one.binding | peakBytes | 3646.000 | 3646.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | typed-predicate-binding | predicate.two-hop-to-one.binding | retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | elapsedUs | 0.250 | 0.250 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-0.decode | retainedBytes | 96.000 | 96.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | elapsedUs | 270.125 | 269.542 | -0.583 us (-0.22%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | peakBytes | 18438.000 | 18438.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-128.decode | retainedBytes | 16528.000 | 16528.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | elapsedUs | 17.458 | 17.583 | +0.125 us (+0.72%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | peakBytes | 3078.000 | 3078.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.decimal.size-8.decode | retainedBytes | 1168.000 | 1168.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-0.decode | elapsedUs | 0.209 | 0.250 | +0.041 us (+19.62%) | 9 | slower |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-0.decode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-0.decode | retainedBytes | 96.000 | 96.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-128.decode | elapsedUs | 30.416 | 31.125 | +0.709 us (+2.33%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-128.decode | peakBytes | 2504.000 | 2504.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-128.decode | retainedBytes | 1168.000 | 1168.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-8.decode | elapsedUs | 2.250 | 2.208 | -0.042 us (-1.87%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-8.decode | peakBytes | 760.000 | 760.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.integer.size-8.decode | retainedBytes | 208.000 | 208.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-0.decode | elapsedUs | 0.209 | 0.209 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-0.decode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-0.decode | retainedBytes | 96.000 | 96.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-128.decode | elapsedUs | 10.291 | 10.500 | +0.209 us (+2.03%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-128.decode | peakBytes | 2384.000 | 2384.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-128.decode | retainedBytes | 1168.000 | 1168.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-8.decode | elapsedUs | 0.917 | 0.916 | -0.001 us (-0.11%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-8.decode | peakBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-decode | scalar-collection.string.size-8.decode | retainedBytes | 208.000 | 208.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | elapsedUs | 0.125 | 0.167 | +0.042 us (+33.60%) | 9 | slower |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | elapsedUs | 229.459 | 230.958 | +1.499 us (+0.65%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | peakBytes | 8648.000 | 8648.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-128.encode | retainedBytes | 6864.000 | 6864.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | elapsedUs | 14.875 | 14.584 | -0.291 us (-1.96%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | peakBytes | 1969.000 | 1969.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.decimal.size-8.encode | retainedBytes | 504.000 | 504.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-0.encode | elapsedUs | 0.167 | 0.125 | -0.042 us (-25.15%) | 9 | faster |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-0.encode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-128.encode | elapsedUs | 45.208 | 45.500 | +0.292 us (+0.65%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-128.encode | peakBytes | 2440.000 | 2440.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-128.encode | retainedBytes | 1104.000 | 1104.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-8.encode | elapsedUs | 3.042 | 3.125 | +0.083 us (+2.73%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-8.encode | peakBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.integer.size-8.encode | retainedBytes | 144.000 | 144.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-0.encode | elapsedUs | 0.125 | 0.125 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-0.encode | peakBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-0.encode | retainedBytes | 32.000 | 32.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-128.encode | elapsedUs | 56.167 | 55.750 | -0.417 us (-0.74%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-128.encode | peakBytes | 2440.000 | 2440.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-128.encode | retainedBytes | 1104.000 | 1104.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-8.encode | elapsedUs | 3.750 | 3.708 | -0.042 us (-1.12%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-8.encode | peakBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | scalar-collection-encode | scalar-collection.string.size-8.encode | retainedBytes | 144.000 | 144.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.nested-all.cold-plan | elapsedUs | 102.166 | 103.833 | +1.667 us (+1.63%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.nested-all.cold-plan | peakBytes | 15614.000 | 16602.000 | +988.000 B (+6.33%) | 9 | larger |
| 3.14 | typed-cold-plan | predicate.nested-all.cold-plan | retainedBytes | 10782.000 | 10794.000 | +12.000 B (+0.11%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | elapsedUs | 123.959 | 129.000 | +5.041 us (+4.07%) | 9 | within noise |
| 3.14 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | peakBytes | 15432.000 | 18324.000 | +2892.000 B (+18.74%) | 9 | larger |
| 3.14 | typed-cold-plan | predicate.quantifier-through-to-one.cold-plan | retainedBytes | 10600.000 | 10675.000 | +75.000 B (+0.71%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.scalar-any.cold-plan | elapsedUs | 89.333 | 94.958 | +5.625 us (+6.30%) | 9 | slower |
| 3.14 | typed-cold-plan | predicate.scalar-any.cold-plan | peakBytes | 15117.000 | 16157.000 | +1040.000 B (+6.88%) | 9 | larger |
| 3.14 | typed-cold-plan | predicate.scalar-any.cold-plan | retainedBytes | 10341.000 | 10349.000 | +8.000 B (+0.08%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.shallow-scalar.cold-plan | elapsedUs | 80.250 | 84.792 | +4.542 us (+5.66%) | 9 | slower |
| 3.14 | typed-cold-plan | predicate.shallow-scalar.cold-plan | peakBytes | 14641.000 | 15681.000 | +1040.000 B (+7.10%) | 9 | larger |
| 3.14 | typed-cold-plan | predicate.shallow-scalar.cold-plan | retainedBytes | 9865.000 | 9873.000 | +8.000 B (+0.08%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | elapsedUs | 112.166 | 123.833 | +11.667 us (+10.40%) | 9 | slower |
| 3.14 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | peakBytes | 15204.000 | 16556.000 | +1352.000 B (+8.89%) | 9 | larger |
| 3.14 | typed-cold-plan | predicate.subtype-narrowing.cold-plan | retainedBytes | 10428.000 | 10436.000 | +8.000 B (+0.08%) | 1 | within noise |
| 3.14 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | elapsedUs | 115.542 | 124.333 | +8.791 us (+7.61%) | 9 | slower |
| 3.14 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | peakBytes | 15436.000 | 17452.000 | +2016.000 B (+13.06%) | 9 | larger |
| 3.14 | typed-cold-plan | predicate.two-hop-to-one.cold-plan | retainedBytes | 10348.000 | 10342.000 | -6.000 B (-0.06%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.nested-all.binding | elapsedUs | 8.875 | 9.042 | +0.167 us (+1.88%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.nested-all.binding | peakBytes | 4289.000 | 4289.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.nested-all.binding | retainedBytes | 368.000 | 368.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | elapsedUs | 13.500 | 13.500 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | peakBytes | 4007.000 | 4007.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.quantifier-through-to-one.binding | retainedBytes | 424.000 | 424.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.scalar-any.binding | elapsedUs | 7.125 | 7.291 | +0.166 us (+2.33%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.scalar-any.binding | peakBytes | 3800.000 | 3800.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.scalar-any.binding | retainedBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.shallow-scalar.binding | elapsedUs | 6.417 | 6.500 | +0.083 us (+1.29%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.shallow-scalar.binding | peakBytes | 3800.000 | 3800.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.shallow-scalar.binding | retainedBytes | 200.000 | 200.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.subtype-narrowing.binding | elapsedUs | 13.958 | 13.750 | -0.208 us (-1.49%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.subtype-narrowing.binding | peakBytes | 4751.000 | 4751.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.subtype-narrowing.binding | retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | typed-predicate-binding | predicate.two-hop-to-one.binding | elapsedUs | 16.458 | 16.708 | +0.250 us (+1.52%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.two-hop-to-one.binding | peakBytes | 4139.000 | 4139.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | typed-predicate-binding | predicate.two-hop-to-one.binding | retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 1 | within noise |

## instance-state

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| - | - | cpython-3.13 | aggregate.bare.after | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.before | 6384.000 | 6384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.reduction | 0.617 | 0.617 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.after | 3264.000 | 3312.000 | +48.000 B (+1.47%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.before | 7200.000 | 7248.000 | +48.000 B (+0.67%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.reduction | 0.547 | 0.543 | -0.004 ratio (-0.66%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.409 | 3.501 | +0.093 ratio (+2.72%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.409 | 3.501 | +0.093 ratio (+2.72%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.427 | 3.351 | -0.076 ratio (-2.21%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 0.507 | 0.693 | +0.186 ratio (+36.69%) | 0 | larger |
| - | - | cpython-3.13 | operation.construction.likeForLike | 0.487 | 0.661 | +0.175 ratio (+35.93%) | 0 | larger |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 1.554 | 1.550 | -0.004 ratio (-0.24%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.191 | 2.144 | -0.047 ratio (-2.15%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.191 | 2.144 | -0.047 ratio (-2.15%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.214 | 2.146 | -0.067 ratio (-3.04%) | 0 | smaller |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3312.000 | +48.000 B (+1.47%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.584 | -0.006 ratio (-1.02%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 1410.723 | 1657.933 | +247.210 ns (+17.52%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 7011.965 | 7035.358 | +23.394 ns (+0.33%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.directWireNs | 11085.645 | 11389.125 | +303.480 ns (+2.74%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.dumpNs | 6097.709 | 6092.333 | -5.375 ns (-0.09%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.peakBytes | 4770.000 | 4778.000 | +8.000 B (+0.17%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionNs | 14932.812 | 14895.834 | -36.979 ns (-0.25%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | 7776.000 | 7776.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | 1240.000 | 1264.000 | +24.000 B (+1.94%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | 12500.438 | 12707.131 | +206.694 ns (+1.65%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | 6536.000 | 6512.000 | -24.000 B (-0.37%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.readNs | 86.679 | 83.121 | -3.558 ns (-4.11%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1072.000 | +8.000 B (+0.75%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 535.942 | 262.897 | -273.045 ns (-50.95%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 3706.000 | 3706.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 535.942 | 262.897 | -273.045 ns (-50.95%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | 96.925 | 236.550 | +139.625 ns (+144.05%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 10448.825 | 9566.596 | -882.229 ns (-8.44%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2521.063 | 2660.208 | +139.146 ns (+5.52%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.peakBytes | 4960.000 | 4968.000 | +8.000 B (+0.16%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.readNs | 25.350 | 24.712 | -0.637 ns (-2.51%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2800.000 | +8.000 B (+0.29%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2168.000 | 2168.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 502.717 | 208.929 | -293.788 ns (-58.44%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 6085.971 | 6212.592 | +126.621 ns (+2.08%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2508.375 | 2651.458 | +143.083 ns (+5.70%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 25.067 | 25.575 | +0.508 ns (+2.03%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.retainedBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.transientBytes | 1336.000 | 1336.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | vsLegacy.bareReduction | 0.651 | 0.651 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | vsLegacy.retainedReduction | 0.619 | 0.617 | -0.002 ratio (-0.29%) | 0 | within noise |
| - | - | cpython-3.13/nested | vsOrdinary.bareReduction | 0.699 | 0.699 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | vsOrdinary.retainedReduction | 0.655 | 0.652 | -0.003 ratio (-0.40%) | 0 | within noise |
| - | - | cpython-3.13/nested | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.bareBytes | 328.000 | 328.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.callNs | 1396.802 | 1423.679 | +26.877 ns (+1.92%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 2331.510 | 2363.404 | +31.894 ns (+1.37%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.directWireNs | 5975.146 | 6290.750 | +315.604 ns (+5.28%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1813.042 | 1838.208 | +25.166 ns (+1.39%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.peakBytes | 3464.000 | 3472.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionNs | 7988.229 | 8320.437 | +332.209 ns (+4.16%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | 2624.000 | 2624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | 472.000 | 496.000 | +24.000 B (+5.08%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | 6315.694 | 6669.479 | +353.785 ns (+5.60%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | 2152.000 | 2128.000 | -24.000 B (-1.12%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.readNs | 74.375 | 75.912 | +1.538 ns (+2.07%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 472.000 | +8.000 B (+1.72%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 200.953 | 214.640 | +13.687 ns (+6.81%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 200.953 | 214.640 | +13.687 ns (+6.81%) | 0 | larger |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 301.983 | 235.063 | -66.921 ns (-22.16%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5533.454 | 3658.437 | -1875.017 ns (-33.89%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 913.229 | 878.833 | -34.396 ns (-3.77%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1712.000 | +8.000 B (+0.47%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 23.212 | 21.375 | -1.837 ns (-7.92%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 984.000 | +8.000 B (+0.82%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 204.381 | 214.544 | +10.163 ns (+4.97%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1209.931 | 1202.498 | -7.433 ns (-0.61%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 852.625 | 876.625 | +24.000 ns (+2.81%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 22.242 | 22.721 | +0.479 ns (+2.15%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.retainedBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.transientBytes | 1336.000 | 1336.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | vsLegacy.bareReduction | 0.610 | 0.610 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | vsLegacy.retainedReduction | 0.525 | 0.520 | -0.004 ratio (-0.81%) | 0 | within noise |
| - | - | cpython-3.13/nullable | vsOrdinary.bareReduction | 0.717 | 0.717 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | vsOrdinary.retainedReduction | 0.600 | 0.593 | -0.007 ratio (-1.15%) | 0 | within noise |
| - | - | cpython-3.13/nullable | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.bareBytes | 296.000 | 296.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.callNs | 1317.304 | 1376.983 | +59.679 ns (+4.53%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 2151.987 | 2166.746 | +14.758 ns (+0.69%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.directWireNs | 5437.667 | 5572.166 | +134.500 ns (+2.47%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.dumpNs | 1847.688 | 1835.895 | -11.792 ns (-0.64%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.peakBytes | 3432.000 | 3440.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionNs | 7397.417 | 7433.541 | +36.125 ns (+0.49%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | 2536.000 | 2536.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | 384.000 | 408.000 | +24.000 B (+6.25%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | 5497.235 | 5807.571 | +310.335 ns (+5.65%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | 2152.000 | 2128.000 | -24.000 B (-1.12%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.readNs | 75.960 | 75.071 | -0.890 ns (-1.17%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 440.000 | +8.000 B (+1.85%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 173.646 | 201.789 | +28.142 ns (+16.21%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 173.646 | 201.789 | +28.142 ns (+16.21%) | 0 | larger |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 127.858 | 199.579 | +71.721 ns (+56.09%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5183.433 | 3306.504 | -1876.929 ns (-36.21%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.dumpNs | 869.604 | 877.000 | +7.396 ns (+0.85%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1712.000 | +8.000 B (+0.47%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 22.721 | 20.481 | -2.240 ns (-9.86%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 984.000 | +8.000 B (+0.82%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 210.785 | 253.240 | +42.454 ns (+20.14%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 933.715 | 941.406 | +7.692 ns (+0.82%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 907.145 | 870.646 | -36.500 ns (-4.02%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 22.556 | 21.281 | -1.275 ns (-5.65%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.retainedBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.transientBytes | 960.000 | 960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | vsLegacy.bareReduction | 0.648 | 0.648 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | vsLegacy.retainedReduction | 0.557 | 0.553 | -0.005 ratio (-0.81%) | 0 | within noise |
| - | - | cpython-3.13/partial | vsOrdinary.bareReduction | 0.543 | 0.543 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | vsOrdinary.retainedReduction | 0.333 | 0.321 | -0.012 ratio (-3.70%) | 0 | smaller |
| - | - | cpython-3.13/partial | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.bareBytes | 272.000 | 272.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.callNs | 1355.612 | 1309.365 | -46.248 ns (-3.41%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 2190.137 | 2245.323 | +55.185 ns (+2.52%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | 5987.979 | 6360.521 | +372.542 ns (+6.22%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1679.479 | 1685.229 | +5.750 ns (+0.34%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 3408.000 | 3416.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | 8023.250 | 8270.938 | +247.687 ns (+3.09%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | 2896.000 | 2896.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | 472.000 | 496.000 | +24.000 B (+5.08%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | 6001.806 | 6298.952 | +297.146 ns (+4.95%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | 2424.000 | 2400.000 | -24.000 B (-0.99%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.readNs | 78.479 | 78.333 | -0.146 ns (-0.19%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 416.000 | +8.000 B (+1.96%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 209.193 | 216.257 | +7.065 ns (+3.38%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 209.193 | 216.257 | +7.065 ns (+3.38%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 167.016 | 219.892 | +52.876 ns (+31.66%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4179.817 | 2970.150 | -1209.667 ns (-28.94%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 793.584 | 797.792 | +4.208 ns (+0.53%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1312.000 | +8.000 B (+0.61%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 23.777 | 24.012 | +0.235 ns (+0.99%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 792.000 | +8.000 B (+1.02%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 227.492 | 201.398 | -26.094 ns (-11.47%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1038.342 | 1069.602 | +31.260 ns (+3.01%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 774.875 | 850.396 | +75.521 ns (+9.75%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 23.390 | 25.012 | +1.622 ns (+6.93%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.retainedBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.transientBytes | 1288.000 | 1288.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | vsLegacy.bareReduction | 0.580 | 0.580 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | vsLegacy.retainedReduction | 0.480 | 0.475 | -0.005 ratio (-1.01%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | vsOrdinary.bareReduction | 0.766 | 0.766 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | vsOrdinary.retainedReduction | 0.648 | 0.641 | -0.007 ratio (-1.06%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.bareBytes | 248.000 | 248.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.callNs | 1333.829 | 1437.385 | +103.556 ns (+7.76%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 2043.483 | 2107.990 | +64.506 ns (+3.16%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.directWireNs | 7259.500 | 7672.729 | +413.230 ns (+5.69%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1413.125 | 1426.792 | +13.667 ns (+0.97%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.peakBytes | 3384.000 | 3392.000 | +8.000 B (+0.24%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionNs | 9173.458 | 9297.188 | +123.730 ns (+1.35%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | 3414.000 | 3414.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | 430.000 | 454.000 | +24.000 B (+5.58%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | 5487.448 | 5714.146 | +226.698 ns (+4.13%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | 2984.000 | 2960.000 | -24.000 B (-0.80%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.readNs | 88.286 | 88.240 | -0.047 ns (-0.05%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 392.000 | +8.000 B (+2.08%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 195.927 | 188.865 | -7.061 ns (-3.60%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 195.927 | 188.865 | -7.061 ns (-3.60%) | 0 | smaller |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 165.016 | 160.688 | -4.329 ns (-2.62%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2763.192 | 2243.458 | -519.733 ns (-18.81%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 710.375 | 733.021 | +22.646 ns (+3.19%) | 0 | larger |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1112.000 | -90.000 B (-7.49%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.readNs | 25.328 | 25.339 | +0.011 ns (+0.04%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 704.000 | +8.000 B (+1.15%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 408.000 | -98.000 B (-19.37%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 208.808 | 236.404 | +27.596 ns (+13.22%) | 0 | larger |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 790.692 | 770.638 | -20.054 ns (-2.54%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 726.854 | 748.146 | +21.292 ns (+2.93%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 26.464 | 26.021 | -0.443 ns (-1.67%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.retainedBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.transientBytes | 856.000 | 856.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | vsLegacy.bareReduction | 0.557 | 0.557 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | vsLegacy.retainedReduction | 0.448 | 0.443 | -0.005 ratio (-1.14%) | 0 | within noise |
| - | - | cpython-3.13/shallow | vsOrdinary.bareReduction | 0.557 | 0.557 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | vsOrdinary.retainedReduction | 0.314 | 0.300 | -0.014 ratio (-4.55%) | 0 | smaller |
| - | - | cpython-3.13/shallow | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.bareBytes | 670.000 | 670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.callNs | 1671.787 | 1472.227 | -199.560 ns (-11.94%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 4069.796 | 3948.210 | -121.585 ns (-2.99%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1706.167 | 1745.000 | +38.833 ns (+2.28%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.peakBytes | 3384.000 | 3392.000 | +8.000 B (+0.24%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.readNs | 91.458 | 93.292 | +1.833 ns (+2.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 814.000 | +8.000 B (+0.99%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 204.991 | 194.842 | -10.149 ns (-4.95%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.transientBytes | 2578.000 | 2578.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 204.991 | 194.842 | -10.149 ns (-4.95%) | 0 | smaller |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 86.840 | 164.137 | +77.298 ns (+89.01%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 3875.160 | 3055.696 | -819.465 ns (-21.15%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 722.750 | 727.500 | +4.750 ns (+0.66%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1502.000 | +8.000 B (+0.54%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 26.641 | 24.656 | -1.984 ns (-7.45%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1030.000 | +8.000 B (+0.78%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 215.877 | 210.971 | -4.906 ns (-2.27%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1734.748 | 1501.779 | -232.969 ns (-13.43%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 703.813 | 733.292 | +29.479 ns (+4.19%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1736.000 | -26.000 B (-1.48%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 26.005 | 26.542 | +0.537 ns (+2.06%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.retainedBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.transientBytes | 964.000 | 938.000 | -26.000 B (-2.70%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | vsLegacy.bareReduction | 0.244 | 0.244 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | vsLegacy.retainedReduction | 0.211 | 0.210 | -0.002 ratio (-0.78%) | 0 | within noise |
| - | - | cpython-3.13/warmed | vsOrdinary.bareReduction | 0.160 | 0.160 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | vsOrdinary.retainedReduction | -0.010 | -0.020 | -0.010 ratio (+100.00%) | 0 | larger |
| - | - | cpython-3.13/warmed | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.bareBytes | 376.000 | 376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.callNs | 1422.117 | 1419.927 | -2.189 ns (-0.15%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 2603.821 | 2671.219 | +67.398 ns (+2.59%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.directWireNs | 7135.791 | 7375.521 | +239.729 ns (+3.36%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.dumpNs | 2478.062 | 2525.250 | +47.188 ns (+1.90%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.peakBytes | 3512.000 | 3520.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionNs | 10080.583 | 9907.479 | -173.104 ns (-1.72%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | 664.000 | 688.000 | +24.000 B (+3.61%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | 7613.271 | 8153.844 | +540.573 ns (+7.10%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | 2696.000 | 2672.000 | -24.000 B (-0.89%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.readNs | 78.932 | 79.952 | +1.020 ns (+1.29%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 520.000 | +8.000 B (+1.56%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 206.955 | 202.323 | -4.632 ns (-2.24%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 206.955 | 202.323 | -4.632 ns (-2.24%) | 0 | within noise |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 345.452 | 202.687 | -142.765 ns (-41.33%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 8043.423 | 5073.938 | -2969.485 ns (-36.92%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1188.021 | 1237.750 | +49.729 ns (+4.19%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1680.000 | +16.000 B (+0.96%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 21.224 | 21.348 | +0.124 ns (+0.58%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 984.000 | +8.000 B (+0.82%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 696.000 | +8.000 B (+1.16%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 233.750 | 233.592 | -0.158 ns (-0.07%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1738.271 | 1794.283 | +56.012 ns (+3.22%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1155.209 | 1180.063 | +24.854 ns (+2.15%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 21.143 | 22.806 | +1.663 ns (+7.86%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.retainedBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.transientBytes | 2008.000 | 2008.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | vsLegacy.bareReduction | 0.552 | 0.552 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | vsLegacy.retainedReduction | 0.475 | 0.472 | -0.004 ratio (-0.81%) | 0 | within noise |
| - | - | cpython-3.13/wide | vsOrdinary.bareReduction | 0.722 | 0.722 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | vsOrdinary.retainedReduction | 0.621 | 0.615 | -0.006 ratio (-0.95%) | 0 | within noise |
| - | - | cpython-3.13/wide | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.bare.after | 2776.000 | 2776.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.bare.before | 6632.000 | 6632.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.bare.reduction | 0.581 | 0.581 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.retained.after | 3592.000 | 3640.000 | +48.000 B (+1.34%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.retained.before | 7448.000 | 7496.000 | +48.000 B (+0.64%) | 0 | within noise |
| - | - | cpython-3.14 | aggregate.retained.reduction | 0.518 | 0.514 | -0.003 ratio (-0.64%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.126 | 3.143 | +0.017 ratio (+0.55%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.126 | 3.143 | +0.017 ratio (+0.55%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.021 | 3.122 | +0.101 ratio (+3.35%) | 0 | larger |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 0.520 | 0.710 | +0.191 ratio (+36.73%) | 0 | larger |
| - | - | cpython-3.14 | operation.construction.likeForLike | 0.499 | 0.682 | +0.183 ratio (+36.58%) | 0 | larger |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 1.483 | 1.517 | +0.034 ratio (+2.31%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.124 | 2.131 | +0.007 ratio (+0.32%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.124 | 2.131 | +0.007 ratio (+0.32%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.147 | 2.112 | -0.034 ratio (-1.60%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3640.000 | +48.000 B (+1.34%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.557 | -0.006 ratio (-1.04%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 1468.871 | 1606.002 | +137.132 ns (+9.34%) | 0 | larger |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 5910.171 | 5945.165 | +34.994 ns (+0.59%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.directWireNs | 10302.500 | 10652.271 | +349.771 ns (+3.40%) | 0 | larger |
| - | - | cpython-3.14/nested | compact.dumpNs | 5495.396 | 5701.708 | +206.313 ns (+3.75%) | 0 | larger |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/nested | compact.peakBytes | 5034.000 | 5042.000 | +8.000 B (+0.16%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionNs | 13822.146 | 14106.479 | +284.333 ns (+2.06%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | 8674.000 | 8674.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | 1248.000 | 1272.000 | +24.000 B (+1.92%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | 11937.692 | 12201.127 | +263.435 ns (+2.21%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | 7426.000 | 7402.000 | -24.000 B (-0.32%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.readNs | 77.979 | 80.267 | +2.287 ns (+2.93%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1240.000 | +8.000 B (+0.65%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 247.412 | 66.545 | -180.866 ns (-73.10%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 3802.000 | 3802.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 247.412 | 66.545 | -180.866 ns (-73.10%) | 0 | smaller |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 26.427 | 6.767 | -19.660 ns (-74.39%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 9416.740 | 8688.650 | -728.090 ns (-7.73%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 2403.354 | 2501.896 | +98.542 ns (+4.10%) | 0 | larger |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5184.000 | 5192.000 | +8.000 B (+0.15%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.readNs | 25.242 | 25.425 | +0.183 ns (+0.73%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2928.000 | +8.000 B (+0.27%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2264.000 | 2264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 216.900 | 176.602 | -40.298 ns (-18.58%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 5636.683 | 5665.190 | +28.506 ns (+0.51%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 2394.604 | 2531.688 | +137.083 ns (+5.72%) | 0 | larger |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4744.000 | 4744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 25.071 | 24.892 | -0.179 ns (-0.71%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.retainedBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.transientBytes | 1536.000 | 1536.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | vsLegacy.bareReduction | 0.606 | 0.606 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | vsLegacy.retainedReduction | 0.578 | 0.577 | -0.002 ratio (-0.27%) | 0 | within noise |
| - | - | cpython-3.14/nested | vsOrdinary.bareReduction | 0.658 | 0.658 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | vsOrdinary.retainedReduction | 0.616 | 0.613 | -0.002 ratio (-0.40%) | 0 | within noise |
| - | - | cpython-3.14/nested | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.bareBytes | 360.000 | 360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.callNs | 1351.073 | 1307.873 | -43.200 ns (-3.20%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 2023.802 | 2093.960 | +70.158 ns (+3.47%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.directWireNs | 5302.729 | 5675.437 | +372.708 ns (+7.03%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.dumpNs | 1630.646 | 1676.063 | +45.417 ns (+2.79%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.peakBytes | 3672.000 | 3680.000 | +8.000 B (+0.22%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionNs | 7344.813 | 7294.729 | -50.084 ns (-0.68%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | 2864.000 | 2864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | 480.000 | 504.000 | +24.000 B (+5.00%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | 5750.821 | 6038.258 | +287.438 ns (+5.00%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | 2384.000 | 2360.000 | -24.000 B (-1.01%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.readNs | 69.081 | 69.181 | +0.100 ns (+0.14%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 504.000 | +8.000 B (+1.61%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 159.800 | 190.006 | +30.206 ns (+18.90%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 159.800 | 190.006 | +30.206 ns (+18.90%) | 0 | larger |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 163.588 | 213.498 | +49.910 ns (+30.51%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 4512.037 | 3014.981 | -1497.056 ns (-33.18%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 811.146 | 788.063 | -23.083 ns (-2.85%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1840.000 | +8.000 B (+0.44%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 21.065 | 23.160 | +2.096 ns (+9.95%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1008.000 | +8.000 B (+0.80%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 185.135 | 204.390 | +19.254 ns (+10.40%) | 0 | larger |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1058.781 | 1049.569 | -9.212 ns (-0.87%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 789.417 | 822.584 | +33.167 ns (+4.20%) | 0 | larger |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 22.044 | 21.800 | -0.244 ns (-1.11%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.retainedBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.transientBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | vsLegacy.bareReduction | 0.583 | 0.583 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | vsLegacy.retainedReduction | 0.504 | 0.500 | -0.004 ratio (-0.79%) | 0 | within noise |
| - | - | cpython-3.14/nullable | vsOrdinary.bareReduction | 0.696 | 0.696 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | vsOrdinary.retainedReduction | 0.581 | 0.574 | -0.007 ratio (-1.16%) | 0 | within noise |
| - | - | cpython-3.14/nullable | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.bareBytes | 328.000 | 328.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.callNs | 1366.290 | 1206.944 | -159.346 ns (-11.66%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 1944.565 | 2046.431 | +101.867 ns (+5.24%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.directWireNs | 4868.708 | 5084.188 | +215.479 ns (+4.43%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.dumpNs | 1653.771 | 1712.208 | +58.438 ns (+3.53%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.peakBytes | 3576.000 | 3584.000 | +8.000 B (+0.22%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionNs | 6512.958 | 6761.396 | +248.437 ns (+3.81%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | 2744.000 | 2744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | 392.000 | 416.000 | +24.000 B (+6.12%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | 5148.663 | 5411.706 | +263.044 ns (+5.11%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | 2352.000 | 2328.000 | -24.000 B (-1.02%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.readNs | 68.660 | 73.923 | +5.262 ns (+7.66%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 472.000 | +8.000 B (+1.72%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 194.108 | 187.316 | -6.792 ns (-3.50%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 194.108 | 187.316 | -6.792 ns (-3.50%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 212.635 | 184.608 | -28.027 ns (-13.18%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 4319.135 | 2794.704 | -1524.431 ns (-35.29%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 797.208 | 796.291 | -0.916 ns (-0.11%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1840.000 | +8.000 B (+0.44%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 22.775 | 22.923 | +0.148 ns (+0.65%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1008.000 | +8.000 B (+0.80%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 189.004 | 209.879 | +20.875 ns (+11.04%) | 0 | larger |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 862.725 | 853.558 | -9.167 ns (-1.06%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 793.875 | 777.667 | -16.208 ns (-2.04%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 26.887 | 23.823 | -3.065 ns (-11.40%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.retainedBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.transientBytes | 1040.000 | 1040.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | vsLegacy.bareReduction | 0.620 | 0.620 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | vsLegacy.retainedReduction | 0.536 | 0.532 | -0.004 ratio (-0.79%) | 0 | within noise |
| - | - | cpython-3.14/partial | vsOrdinary.bareReduction | 0.512 | 0.512 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | vsOrdinary.retainedReduction | 0.310 | 0.298 | -0.012 ratio (-3.85%) | 0 | smaller |
| - | - | cpython-3.14/partial | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.bareBytes | 304.000 | 304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.callNs | 1235.654 | 1353.358 | +117.704 ns (+9.53%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 1969.346 | 2026.454 | +57.108 ns (+2.90%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | 5333.458 | 5720.188 | +386.729 ns (+7.25%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1510.292 | 1476.271 | -34.021 ns (-2.25%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 3552.000 | 3560.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | 7020.312 | 7240.750 | +220.438 ns (+3.14%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | 480.000 | 504.000 | +24.000 B (+5.00%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | 5488.313 | 5672.975 | +184.662 ns (+3.36%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | 2632.000 | 2608.000 | -24.000 B (-0.91%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.readNs | 71.958 | 71.679 | -0.280 ns (-0.39%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 448.000 | +8.000 B (+1.82%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 216.673 | 186.627 | -30.046 ns (-13.87%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 216.673 | 186.627 | -30.046 ns (-13.87%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 232.298 | 197.914 | -34.383 ns (-14.80%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 3539.848 | 2531.606 | -1008.242 ns (-28.48%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 730.417 | 738.625 | +8.208 ns (+1.12%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1440.000 | +8.000 B (+0.56%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 25.461 | 24.512 | -0.949 ns (-3.73%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 816.000 | +8.000 B (+0.99%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 170.596 | 184.640 | +14.044 ns (+8.23%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1002.362 | 996.235 | -6.127 ns (-0.61%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 721.813 | 746.833 | +25.020 ns (+3.47%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 26.170 | 24.015 | -2.155 ns (-8.23%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.retainedBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.transientBytes | 1368.000 | 1368.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | vsLegacy.bareReduction | 0.548 | 0.548 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | vsLegacy.retainedReduction | 0.455 | 0.451 | -0.004 ratio (-0.98%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | vsOrdinary.bareReduction | 0.743 | 0.743 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | vsOrdinary.retainedReduction | 0.628 | 0.622 | -0.007 ratio (-1.08%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.bareBytes | 280.000 | 280.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.callNs | 1273.392 | 1298.904 | +25.512 ns (+2.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 1868.462 | 1954.783 | +86.321 ns (+4.62%) | 0 | larger |
| - | - | cpython-3.14/shallow | compact.directWireNs | 6603.791 | 7350.750 | +746.959 ns (+11.31%) | 0 | larger |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1262.792 | 1252.959 | -9.833 ns (-0.78%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/shallow | compact.peakBytes | 3528.000 | 3536.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionNs | 8118.708 | 8358.687 | +239.979 ns (+2.96%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | 3718.000 | 3718.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | 438.000 | 462.000 | +24.000 B (+5.48%) | 0 | larger |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | 5077.021 | 5455.567 | +378.546 ns (+7.46%) | 0 | larger |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | 3280.000 | 3256.000 | -24.000 B (-0.73%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.readNs | 81.974 | 83.922 | +1.948 ns (+2.38%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 424.000 | +8.000 B (+1.92%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 196.959 | 180.527 | -16.433 ns (-8.34%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 196.959 | 180.527 | -16.433 ns (-8.34%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 235.032 | 192.596 | -42.436 ns (-18.06%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 2381.885 | 1892.612 | -489.273 ns (-20.54%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 673.792 | 654.666 | -19.125 ns (-2.84%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1232.000 | -90.000 B (-6.81%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.readNs | 25.979 | 25.083 | -0.896 ns (-3.45%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 728.000 | +8.000 B (+1.11%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 504.000 | -98.000 B (-16.28%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 191.004 | 185.558 | -5.446 ns (-2.85%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 735.413 | 736.192 | +0.779 ns (+0.11%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 661.063 | 695.125 | +34.062 ns (+5.15%) | 0 | larger |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 24.990 | 27.812 | +2.823 ns (+11.30%) | 0 | larger |
| - | - | cpython-3.14/shallow | ordinary.retainedBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.transientBytes | 936.000 | 936.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | vsLegacy.bareReduction | 0.521 | 0.521 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | vsLegacy.retainedReduction | 0.422 | 0.418 | -0.005 ratio (-1.10%) | 0 | within noise |
| - | - | cpython-3.14/shallow | vsOrdinary.bareReduction | 0.521 | 0.521 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | vsOrdinary.retainedReduction | 0.288 | 0.274 | -0.014 ratio (-4.76%) | 0 | smaller |
| - | - | cpython-3.14/shallow | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.bareBytes | 702.000 | 702.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.callNs | 1539.671 | 1472.306 | -67.365 ns (-4.38%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 3775.954 | 3633.006 | -142.948 ns (-3.79%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1563.000 | 1603.396 | +40.396 ns (+2.58%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.peakBytes | 3528.000 | 3536.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.readNs | 79.734 | 78.005 | -1.729 ns (-2.17%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 846.000 | +8.000 B (+0.95%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 194.362 | 200.439 | +6.077 ns (+3.13%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.transientBytes | 2690.000 | 2690.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 194.362 | 200.439 | +6.077 ns (+3.13%) | 0 | larger |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 110.521 | 196.929 | +86.408 ns (+78.18%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 3511.792 | 2698.675 | -813.117 ns (-23.15%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 669.730 | 671.333 | +1.604 ns (+0.24%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1678.000 | +8.000 B (+0.48%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 25.375 | 25.000 | -0.375 ns (-1.48%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1054.000 | +8.000 B (+0.76%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 191.004 | 206.552 | +15.548 ns (+8.14%) | 0 | larger |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1627.413 | 1366.677 | -260.735 ns (-16.02%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 669.355 | 668.396 | -0.959 ns (-0.14%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 25.141 | 25.057 | -0.083 ns (-0.33%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.retainedBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.transientBytes | 1050.000 | 1050.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | vsLegacy.bareReduction | 0.229 | 0.229 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | vsLegacy.retainedReduction | 0.199 | 0.197 | -0.002 ratio (-0.76%) | 0 | within noise |
| - | - | cpython-3.14/warmed | vsOrdinary.bareReduction | 0.146 | 0.146 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | vsOrdinary.retainedReduction | -0.019 | -0.029 | -0.010 ratio (+50.00%) | 0 | larger |
| - | - | cpython-3.14/warmed | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.bareBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.callNs | 1309.342 | 1457.496 | +148.154 ns (+11.32%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 2280.512 | 2353.962 | +73.450 ns (+3.22%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.directWireNs | 6449.917 | 6862.854 | +412.937 ns (+6.40%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.dumpNs | 2165.958 | 2225.520 | +59.562 ns (+2.75%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.peakBytes | 3720.000 | 3728.000 | +8.000 B (+0.22%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionNs | 8579.396 | 8923.563 | +344.167 ns (+4.01%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | 3616.000 | 3616.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | 672.000 | 696.000 | +24.000 B (+3.57%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | 6926.806 | 7140.658 | +213.852 ns (+3.09%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | 2944.000 | 2920.000 | -24.000 B (-0.82%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.readNs | 76.122 | 75.225 | -0.897 ns (-1.18%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 552.000 | +8.000 B (+1.47%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 225.760 | 146.377 | -79.383 ns (-35.16%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 225.760 | 146.377 | -79.383 ns (-35.16%) | 0 | smaller |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 357.871 | 111.179 | -246.692 ns (-68.93%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 6615.900 | 4190.029 | -2425.871 ns (-36.67%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1042.396 | 1111.354 | +68.958 ns (+6.62%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1800.000 | +16.000 B (+0.90%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 22.087 | 23.406 | +1.319 ns (+5.97%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1008.000 | +8.000 B (+0.80%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 792.000 | +8.000 B (+1.02%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 175.394 | 187.385 | +11.991 ns (+6.84%) | 0 | larger |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 1490.127 | 1520.990 | +30.863 ns (+2.07%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1029.625 | 1074.896 | +45.271 ns (+4.40%) | 0 | larger |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 22.402 | 23.135 | +0.733 ns (+3.27%) | 0 | larger |
| - | - | cpython-3.14/wide | ordinary.retainedBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.transientBytes | 2088.000 | 2088.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | vsLegacy.bareReduction | 0.528 | 0.528 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | vsLegacy.retainedReduction | 0.456 | 0.452 | -0.004 ratio (-0.79%) | 0 | within noise |
| - | - | cpython-3.14/wide | vsOrdinary.bareReduction | 0.703 | 0.703 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | vsOrdinary.retainedReduction | 0.605 | 0.599 | -0.006 ratio (-0.96%) | 0 | within noise |
| - | - | cpython-3.14/wide | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |

## lifecycle-overhead

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.123 | 3.082 | -0.042 us/event (-1.33%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 3.798 | 3.760 | -0.037 us/event (-0.98%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.264 | 0.261 | -0.003 ratio (-0.96%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.020 | 0.020 | -0.000 ratio (-1.30%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.066 | 0.065 | -0.001 ratio (-1.24%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.004 | 0.004 | -0.000 ratio (-1.33%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.164 | 0.163 | -0.002 ratio (-1.10%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p50 | 419.375 | 416.916 | -2.459 us (-0.59%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p95 | 444.000 | 440.083 | -3.917 us (-0.88%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 87.458 | 86.292 | -1.166 us (-1.33%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 106.333 | 105.292 | -1.041 us (-0.98%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.264 | 0.261 | -0.003 ratio (-1.15%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.320 | 0.319 | -0.001 ratio (-0.37%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | plain.p50 | 331.792 | 330.541 | -1.251 us (-0.38%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | plain.p95 | 351.834 | 347.875 | -3.959 us (-1.13%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.264 | 0.261 | -0.003 ratio (-1.01%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.262 | 0.265 | +0.003 ratio (+1.18%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.228 | 2.222 | -0.006 us/event (-0.27%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 2.905 | 2.787 | -0.118 us/event (-4.05%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.189 | 0.189 | +0.000 ratio (+0.06%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.014 | 0.014 | -0.000 ratio (-0.24%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.047 | 0.047 | -0.000 ratio (-0.19%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | -0.000 ratio (-0.26%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.118 | 0.118 | -0.000 ratio (-0.06%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p50 | 392.916 | 391.667 | -1.249 us (-0.32%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p95 | 416.834 | 411.791 | -5.043 us (-1.21%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 62.375 | 62.208 | -0.167 us (-0.27%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 81.333 | 78.042 | -3.291 us (-4.05%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.189 | 0.189 | +0.000 ratio (+0.09%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.245 | 0.236 | -0.009 ratio (-3.52%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | plain.p50 | 330.416 | 329.333 | -1.083 us (-0.33%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | plain.p95 | 350.667 | 346.250 | -4.417 us (-1.26%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.189 | 0.189 | +0.000 ratio (+0.06%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.189 | 0.189 | +0.001 ratio (+0.32%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 3.759 | 3.732 | -0.027 us/event (-0.71%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.436 | 4.503 | +0.067 us/event (+1.51%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.317 | 0.315 | -0.001 ratio (-0.35%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.024 | 0.024 | -0.000 ratio (-0.69%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.079 | 0.078 | -0.000 ratio (-0.62%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-0.71%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.198 | 0.197 | -0.001 ratio (-0.49%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | observed.p50 | 438.208 | 436.209 | -1.999 us (-0.46%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | observed.p95 | 464.875 | 463.291 | -1.584 us (-0.34%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 105.250 | 104.499 | -0.751 us (-0.71%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 124.209 | 126.083 | +1.874 us (+1.51%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.316 | 0.315 | -0.001 ratio (-0.31%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.370 | 0.378 | +0.008 ratio (+2.03%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | plain.p50 | 332.500 | 331.292 | -1.208 us (-0.36%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | plain.p95 | 353.750 | 351.959 | -1.791 us (-0.51%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.318 | 0.317 | -0.001 ratio (-0.39%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.314 | 0.316 | +0.002 ratio (+0.70%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 3.624 | 3.560 | -0.064 us/event (-1.77%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 4.362 | 4.415 | +0.054 us/event (+1.23%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.305 | 0.301 | -0.004 ratio (-1.22%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.023 | 0.023 | -0.000 ratio (-1.72%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.076 | 0.075 | -0.001 ratio (-1.63%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-1.76%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.191 | 0.188 | -0.003 ratio (-1.43%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 433.792 | 430.583 | -3.209 us (-0.74%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 462.000 | 460.000 | -2.000 us (-0.43%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 101.459 | 99.667 | -1.792 us (-1.77%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 122.125 | 123.625 | +1.500 us (+1.23%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.305 | 0.301 | -0.004 ratio (-1.24%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.364 | 0.374 | +0.010 ratio (+2.84%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 332.458 | 330.625 | -1.833 us (-0.55%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 353.291 | 353.417 | +0.126 us (+0.04%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.305 | 0.302 | -0.002 ratio (-0.81%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.308 | 0.302 | -0.006 ratio (-1.99%) | 0 | within noise |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.406 | 1.390 | -0.016 us/event (-1.17%) | 0 | within noise |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 2.115 | 2.040 | -0.074 us/event (-3.52%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.119 | 0.118 | -0.001 ratio (-1.07%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.009 | 0.009 | -0.000 ratio (-1.16%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.030 | 0.029 | -0.000 ratio (-1.14%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-1.17%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.074 | 0.074 | -0.001 ratio (-1.11%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p50 | 369.083 | 368.500 | -0.583 us (-0.16%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p95 | 397.000 | 392.625 | -4.375 us (-1.10%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 39.376 | 38.916 | -0.460 us (-1.17%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 59.209 | 57.125 | -2.084 us (-3.52%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.120 | 0.118 | -0.002 ratio (-1.29%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.178 | 0.172 | -0.005 ratio (-2.97%) | 0 | within noise |
| - | - | one Handler that keeps nothing | plain.p50 | 329.792 | 329.458 | -0.334 us (-0.10%) | 0 | within noise |
| - | - | one Handler that keeps nothing | plain.p95 | 352.917 | 344.750 | -8.167 us (-2.31%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.119 | 0.119 | -0.001 ratio (-0.53%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.125 | 0.139 | +0.014 ratio (+11.17%) | 0 | larger |
| - | - | workload | events | 28.000 | 28.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | workload | statements | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |

## snapshot-delivery

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 9698.917 | 8714.250 | -984.667 us (-10.15%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1392.861 | 1254.299 | -138.562 KiB (-9.95%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 693.328 | 571.453 | -121.875 KiB (-17.58%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 103783.333 | 87603.625 | -16179.708 us (-15.59%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 12652.338 | 11236.408 | -1415.930 KiB (-11.19%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 6931.836 | 5713.086 | -1218.750 KiB (-17.58%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 16089.125 | 15438.833 | -650.292 us (-4.04%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 391.807 | 368.260 | -23.547 KiB (-6.01%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.458 | 2.849 | -0.609 KiB (-17.62%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 107103.833 | 99425.250 | -7678.583 us (-7.17%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 775.244 | 751.002 | -24.242 KiB (-3.13%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.489 | 2.880 | -0.609 KiB (-17.46%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8075.041 | 7585.416 | -489.625 us (-6.06%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1192.139 | 1071.404 | -120.734 KiB (-10.13%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 477.848 | 374.723 | -103.125 KiB (-21.58%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 80762.000 | 76393.166 | -4368.834 us (-5.41%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11110.373 | 9881.357 | -1229.016 KiB (-11.06%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4775.730 | 3744.480 | -1031.250 KiB (-21.59%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 14978.000 | 14492.500 | -485.500 us (-3.24%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 332.436 | 308.131 | -24.305 KiB (-7.31%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.524 | 2.009 | -0.516 KiB (-20.43%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 94236.041 | 92672.416 | -1563.625 us (-1.66%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 774.357 | 750.037 | -24.320 KiB (-3.14%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.556 | 2.040 | -0.516 KiB (-20.18%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 17812.959 | 16818.708 | -994.251 us (-5.58%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1298.314 | 1190.525 | -107.789 KiB (-8.30%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 708.953 | 587.078 | -121.875 KiB (-17.19%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 178113.708 | 180408.750 | +2295.042 us (+1.29%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12084.102 | 11894.070 | -190.031 KiB (-1.57%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7088.086 | 5869.336 | -1218.750 KiB (-17.19%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 23765.541 | 24739.250 | +973.709 us (+4.10%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 507.689 | 480.854 | -26.836 KiB (-5.29%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.536 | 2.927 | -0.609 KiB (-17.23%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 182061.500 | 177233.291 | -4828.209 us (-2.65%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 874.955 | 848.072 | -26.883 KiB (-3.07%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.567 | 2.958 | -0.609 KiB (-17.08%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 15864.833 | 15095.250 | -769.583 us (-4.85%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1208.674 | 1190.955 | -17.719 KiB (-1.47%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 501.285 | 398.160 | -103.125 KiB (-20.57%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 158121.541 | 160763.000 | +2641.459 us (+1.67%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12084.531 | 11894.500 | -190.031 KiB (-1.57%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5010.105 | 3978.855 | -1031.250 KiB (-20.58%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 21930.041 | 21834.167 | -95.874 us (-0.44%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 474.014 | 447.271 | -26.742 KiB (-5.64%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.642 | 2.126 | -0.516 KiB (-19.52%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 163540.166 | 163284.958 | -255.208 us (-0.16%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 871.240 | 844.389 | -26.852 KiB (-3.08%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.673 | 2.157 | -0.516 KiB (-19.29%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 5928.542 | 5647.958 | -280.584 us (-4.73%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 456.371 | 416.355 | -40.016 KiB (-8.77%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 227.253 | 186.347 | -40.906 KiB (-18.00%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 842.750 | 775.500 | -67.250 us (-7.98%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 69.370 | 63.848 | -5.522 KiB (-7.96%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 28.146 | 22.997 | -5.148 KiB (-18.29%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4431.584 | 4483.416 | +51.832 us (+1.17%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 390.489 | 353.724 | -36.766 KiB (-9.42%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 186.823 | 152.917 | -33.906 KiB (-18.15%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 657.125 | 647.583 | -9.542 us (-1.45%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 62.152 | 57.004 | -5.148 KiB (-8.28%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.200 | 18.911 | -4.289 KiB (-18.49%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8591.417 | 8026.834 | -564.583 us (-6.57%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 580.786 | 533.407 | -47.379 KiB (-8.16%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 293.815 | 242.112 | -51.703 KiB (-17.60%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1193.917 | 1125.000 | -68.917 us (-5.77%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 86.676 | 79.926 | -6.750 KiB (-7.79%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 36.802 | 30.255 | -6.547 KiB (-17.79%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6743.958 | 7094.625 | +350.667 us (+5.20%) | 9 | slower |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 524.941 | 484.859 | -40.082 KiB (-7.64%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 257.698 | 217.042 | -40.656 KiB (-15.78%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 1001.208 | 998.708 | -2.500 us (-0.25%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 81.229 | 75.542 | -5.688 KiB (-7.00%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.388 | 27.224 | -5.164 KiB (-15.94%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10797.708 | 10782.708 | -15.000 us (-0.14%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 725.670 | 665.822 | -59.848 KiB (-8.25%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 384.511 | 317.901 | -66.609 KiB (-17.32%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1485.500 | 1404.792 | -80.708 us (-5.43%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 105.743 | 97.728 | -8.016 KiB (-7.58%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 48.544 | 40.114 | -8.430 KiB (-17.37%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8425.250 | 8197.583 | -227.667 us (-2.70%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 664.742 | 613.082 | -51.660 KiB (-7.77%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 333.909 | 281.347 | -52.562 KiB (-15.74%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1236.042 | 1211.000 | -25.042 us (-2.03%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 99.369 | 92.494 | -6.875 KiB (-6.92%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.247 | 35.591 | -6.656 KiB (-15.76%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 420.996 | 295.050 | -125.946 KiB (-29.92%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 297.176 | 133.645 | -163.531 KiB (-55.03%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.404 | 0.481 | +0.076 ms (+18.83%) | 9 | slower |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.644 | 0.679 | +0.035 ms (+5.41%) | 9 | slower |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 4.702 | 4.293 | -0.409 ms (-8.70%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 41835.166 | 46008.297 | +4173.131 roots/s (+9.98%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 5.521 | 4.856 | -0.665 ms (-12.05%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 39126.180 | 41395.363 | +2269.184 roots/s (+5.80%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 7.383 | 7.035 | -0.348 ms (-4.72%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 26522.121 | 28795.105 | +2272.984 roots/s (+8.57%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 219.224 | 154.026 | -65.197 KiB (-29.74%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 44.738 | 43.581 | -1.157 KiB (-2.59%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 80.877 | 70.605 | -10.271 KiB (-12.70%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 10.950 | 9.012 | -1.938 KiB (-17.70%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1232.261 | 1111.526 | -120.734 KiB (-9.80%) | 3 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.973 | 418.848 | -103.125 KiB (-19.76%) | 3 | smaller |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.669 | 0.705 | +0.037 ms (+5.49%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.095 | 1.089 | -0.007 ms (-0.62%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 8.562 | 7.781 | -0.782 ms (-9.13%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23464.883 | 25008.597 | +1543.714 roots/s (+6.58%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 9.210 | 8.502 | -0.708 ms (-7.69%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 21969.674 | 23076.480 | +1106.806 roots/s (+5.04%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 11.890 | 11.728 | -0.162 ms (-1.36%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 16446.692 | 17564.209 | +1117.517 roots/s (+6.79%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 667.897 | 575.624 | -92.273 KiB (-13.82%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 29.220 | 27.556 | -1.664 KiB (-5.69%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 188.167 | 163.854 | -24.312 KiB (-12.92%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 5.002 | 4.486 | -0.516 KiB (-10.31%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1586.600 | 1504.769 | -81.831 KiB (-5.16%) | 3 | smaller |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.645 | 766.512 | -103.133 KiB (-11.86%) | 3 | smaller |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.827 | 0.829 | +0.002 ms (+0.24%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.010 | 1.838 | -0.172 ms (-8.57%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 24.528 | 20.821 | -3.707 ms (-15.11%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 8276.547 | 9717.681 | +1441.134 roots/s (+17.41%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 24.768 | 21.154 | -3.614 ms (-14.59%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 4285.806 | 9490.949 | +5205.143 roots/s (+121.45%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 26.212 | 23.924 | -2.288 ms (-8.73%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 7103.954 | 8311.631 | +1207.676 roots/s (+17.00%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1038.502 | 915.995 | -122.507 KiB (-11.80%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 57.180 | 53.433 | -3.747 KiB (-6.55%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 290.226 | 258.652 | -31.573 KiB (-10.88%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 7.715 | 7.256 | -0.459 KiB (-5.95%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1289.960 | 1272.241 | -17.719 KiB (-1.37%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 545.004 | 441.879 | -103.125 KiB (-18.92%) | 3 | smaller |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.817 | 0.792 | -0.024 ms (-2.97%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.505 | 1.353 | -0.152 ms (-10.11%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 16.068 | 16.138 | +0.070 ms (+0.44%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 12382.304 | 13017.655 | +635.351 roots/s (+5.13%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 15.987 | 14.679 | -1.308 ms (-8.18%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12533.160 | 13614.704 | +1081.543 roots/s (+8.63%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 19.309 | 17.863 | -1.446 ms (-7.49%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10585.605 | 11132.887 | +547.282 roots/s (+5.17%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1132.808 | 1027.323 | -105.484 KiB (-9.31%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 38.103 | 36.142 | -1.961 KiB (-5.15%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 302.128 | 275.261 | -26.867 KiB (-8.89%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 5.627 | 5.111 | -0.516 KiB (-9.16%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 292.653 | 246.513 | -46.141 KiB (-15.77%) | 3 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.863 | 104.621 | -67.242 KiB (-39.13%) | 3 | smaller |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.469 | 0.454 | -0.015 ms (-3.23%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.656 | 0.620 | -0.037 ms (-5.57%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.041 | 4.675 | -0.366 ms (-7.26%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 38832.441 | 42113.021 | +3280.580 roots/s (+8.45%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 5.543 | 5.192 | -0.351 ms (-6.33%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 36056.338 | 37474.819 | +1418.482 roots/s (+3.93%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 7.790 | 7.451 | -0.339 ms (-4.35%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 25027.245 | 26787.658 | +1760.412 roots/s (+7.03%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 177.098 | 148.924 | -28.174 KiB (-15.91%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 32.916 | 32.499 | -0.417 KiB (-1.27%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 68.241 | 63.119 | -5.122 KiB (-7.51%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 3.137 | 2.805 | -0.332 KiB (-10.59%) | 6 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 4.667 | 4.587 | -0.080 us/projection (-1.72%) | 9 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 216124.980 | 207848.210 | -8276.769 projections/s (-3.83%) | 9 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 35.895 | 35.277 | -0.617 KiB (-1.72%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 41.653 | 41.591 | -0.062 KiB (-0.15%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 434.312 | 402.938 | -31.375 B/projection (-7.22%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 140.000 | 161.500 | +21.500 B/projection (+15.36%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 5.863 | 5.480 | -0.383 us/projection (-6.53%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 173637.952 | 184926.214 | +11288.262 projections/s (+6.50%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 39.090 | 34.973 | -4.117 KiB (-10.53%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 56.621 | 56.559 | -0.062 KiB (-0.11%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 434.312 | 402.938 | -31.375 B/projection (-7.22%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 191.125 | 156.625 | -34.500 B/projection (-18.05%) | 3 | smaller |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.672 | 8.059 | -0.613 ms (-7.07%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 23259.194 | 23580.039 | +320.845 roots/s (+1.38%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.412 | 9.045 | -0.367 ms (-3.90%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 21571.094 | 22185.759 | +614.665 roots/s (+2.85%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 41.159 | 15.588 | -25.571 ms (-62.13%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 11292.948 | 12964.634 | +1671.686 roots/s (+14.80%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 18.319 | 15.658 | -2.660 ms (-14.52%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 11340.306 | 12692.671 | +1352.365 roots/s (+11.93%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 31.158 | 30.451 | -0.707 us/root (-2.27%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 96.629 | 92.527 | -4.102 KiB (-4.24%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.852 | 48.102 | -2.750 KiB (-5.41%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 31.879 | 30.927 | -0.952 us/root (-2.99%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 101.980 | 97.816 | -4.164 KiB (-4.08%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.852 | 48.102 | -2.750 KiB (-5.41%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 45.652 | 45.365 | -0.288 us/root (-0.63%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 144.445 | 140.879 | -3.566 KiB (-2.47%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.977 | 85.227 | -2.750 KiB (-3.13%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 46.732 | 45.284 | -1.448 us/root (-3.10%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 149.680 | 145.562 | -4.117 KiB (-2.75%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.977 | 85.227 | -2.750 KiB (-3.13%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 66.025 | 65.116 | -0.909 us/root (-1.38%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 215.234 | 213.141 | -2.094 KiB (-0.97%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.477 | 134.727 | -2.750 KiB (-2.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 66.078 | 66.570 | +0.492 us/root (+0.74%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 218.836 | 216.805 | -2.031 KiB (-0.93%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.477 | 134.727 | -2.750 KiB (-2.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 22.723 | 22.576 | -0.147 us/root (-0.65%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 60.105 | 56.250 | -3.855 KiB (-6.41%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.102 | 21.352 | -2.750 KiB (-11.41%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 23.576 | 22.458 | -1.117 us/root (-4.74%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 67.457 | 63.391 | -4.066 KiB (-6.03%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.102 | 21.352 | -2.750 KiB (-11.41%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 151.103 | 149.901 | -1.202 us/root (-0.80%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 621.332 | 619.754 | -1.578 KiB (-0.25%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.102 | 425.352 | -2.750 KiB (-0.64%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 151.561 | 152.038 | +0.477 us/root (+0.31%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 626.340 | 624.512 | -1.828 KiB (-0.29%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.102 | 425.352 | -2.750 KiB (-0.64%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 55.909 | 54.430 | -1.479 us/root (-2.65%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 191.219 | 189.039 | -2.180 KiB (-1.14%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.102 | 122.352 | -2.750 KiB (-2.20%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 56.190 | 55.426 | -0.764 us/root (-1.36%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 194.910 | 192.926 | -1.984 KiB (-1.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.102 | 122.352 | -2.750 KiB (-2.20%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 46.861 | 47.905 | +1.044 us/root (+2.23%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 126.313 | 122.391 | -3.923 KiB (-3.11%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.945 | 33.195 | -2.750 KiB (-7.65%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 47.641 | 47.475 | -0.165 us/root (-0.35%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 131.665 | 127.719 | -3.946 KiB (-3.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.945 | 33.195 | -2.750 KiB (-7.65%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 72.888 | 53.928 | -18.960 us/root (-26.01%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 214.492 | 212.914 | -1.578 KiB (-0.74%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.727 | 133.977 | -2.750 KiB (-2.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 55.242 | 53.911 | -1.331 us/root (-2.41%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 219.359 | 217.594 | -1.766 KiB (-0.80%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.727 | 133.977 | -2.750 KiB (-2.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 149.339 | 144.549 | -4.789 us/root (-3.21%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 757.062 | 755.484 | -1.578 KiB (-0.21%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.227 | 477.477 | -2.750 KiB (-0.57%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 148.568 | 154.578 | +6.010 us/root (+4.05%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 761.930 | 760.164 | -1.766 KiB (-0.23%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.227 | 477.477 | -2.750 KiB (-0.57%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 231.917 | 272.500 | +40.583 us (+17.50%) | 9 | slower |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 28.543 | 29.957 | +1.414 KiB (+4.95%) | 3 | larger |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 21.832 | 21.801 | -0.031 KiB (-0.14%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 348.042 | 357.666 | +9.624 us (+2.77%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 38.530 | 39.827 | +1.297 KiB (+3.37%) | 3 | larger |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 30.405 | 30.296 | -0.109 KiB (-0.36%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 457.208 | 464.875 | +7.667 us (+1.68%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 47.896 | 49.057 | +1.160 KiB (+2.42%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 38.455 | 38.268 | -0.188 KiB (-0.49%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 82.541 | 93.708 | +11.167 us (+13.53%) | 9 | slower |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 17.167 | 18.269 | +1.102 KiB (+6.42%) | 3 | larger |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 10.972 | 10.979 | +0.008 KiB (+0.07%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 83.375 | 87.333 | +3.958 us (+4.75%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 17.182 | 18.279 | +1.098 KiB (+6.39%) | 3 | larger |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 11.236 | 11.244 | +0.008 KiB (+0.07%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 80.709 | 84.709 | +4.000 us (+4.96%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 17.167 | 18.269 | +1.102 KiB (+6.42%) | 3 | larger |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 10.968 | 10.979 | +0.012 KiB (+0.11%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 82.750 | 87.916 | +5.166 us (+6.24%) | 9 | slower |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 17.182 | 18.283 | +1.102 KiB (+6.41%) | 3 | larger |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 11.236 | 11.244 | +0.008 KiB (+0.07%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 80.000 | 87.958 | +7.958 us (+9.95%) | 9 | slower |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 17.168 | 18.270 | +1.102 KiB (+6.42%) | 3 | larger |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 10.973 | 10.980 | +0.008 KiB (+0.07%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 84.542 | 87.708 | +3.166 us (+3.74%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 17.183 | 18.284 | +1.102 KiB (+6.41%) | 3 | larger |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 11.237 | 11.245 | +0.008 KiB (+0.07%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 2.209 | 2.291 | +0.082 us (+3.71%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 2.708 | 2.750 | +0.042 us (+1.55%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 3.292 | 3.291 | -0.001 us (-0.03%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.closed.retainedKiB | 71.484 | 68.234 | -3.250 KiB (-4.55%) | 3 | smaller |
| 3.13 | result-held-metadata | control-held | large.shared.retainedKiB | 50.789 | 47.539 | -3.250 KiB (-6.40%) | 3 | smaller |
| 3.13 | result-held-metadata | control-held | small.closed.retainedKiB | 118.438 | 98.938 | -19.500 KiB (-16.46%) | 3 | smaller |
| 3.13 | result-held-metadata | control-held | small.shared.retainedKiB | 111.070 | 91.570 | -19.500 KiB (-17.56%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 8914.417 | 8436.500 | -477.917 us (-5.36%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1351.897 | 1203.014 | -148.884 KiB (-11.01%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 741.773 | 610.523 | -131.250 KiB (-17.69%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 97788.625 | 83852.958 | -13935.667 us (-14.25%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 13106.237 | 11596.275 | -1509.962 KiB (-11.52%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 7416.219 | 6103.719 | -1312.500 KiB (-17.70%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 17405.500 | 16754.167 | -651.333 us (-3.74%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 172.350 | 146.013 | -26.337 KiB (-15.28%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.700 | 3.044 | -0.656 KiB (-17.74%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 105757.334 | 97825.125 | -7932.209 us (-7.50%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 178.662 | 152.325 | -26.337 KiB (-14.74%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.731 | 3.075 | -0.656 KiB (-17.59%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 7921.500 | 7084.417 | -837.083 us (-10.57%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1180.812 | 1049.976 | -130.837 KiB (-11.08%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 487.230 | 374.730 | -112.500 KiB (-23.09%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 84425.083 | 70427.417 | -13997.666 us (-16.58%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11346.004 | 10022.753 | -1323.251 KiB (-11.66%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4869.488 | 3744.488 | -1125.000 KiB (-23.10%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 16612.708 | 14995.083 | -1617.625 us (-9.74%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 176.319 | 149.850 | -26.470 KiB (-15.01%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.571 | 2.009 | -0.562 KiB (-21.88%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 92222.542 | 89648.666 | -2573.876 us (-2.79%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 178.226 | 151.756 | -26.470 KiB (-14.85%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.603 | 2.040 | -0.562 KiB (-21.61%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 17078.541 | 15795.625 | -1282.916 us (-7.51%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1297.487 | 1256.340 | -41.147 KiB (-3.17%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 758.961 | 627.711 | -131.250 KiB (-17.29%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 171858.750 | 158185.458 | -13673.292 us (-7.96%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12747.543 | 12557.527 | -190.016 KiB (-1.49%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7588.094 | 6275.594 | -1312.500 KiB (-17.30%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 23676.250 | 22884.000 | -792.250 us (-3.35%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 281.568 | 252.505 | -29.063 KiB (-10.32%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.786 | 3.130 | -0.656 KiB (-17.33%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 175303.541 | 162607.000 | -12696.541 us (-7.24%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 286.896 | 257.833 | -29.063 KiB (-10.13%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.817 | 3.161 | -0.656 KiB (-17.19%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 15070.917 | 14235.000 | -835.917 us (-5.55%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1274.736 | 1257.033 | -17.703 KiB (-1.39%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 510.668 | 398.168 | -112.500 KiB (-22.03%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 158078.542 | 149873.584 | -8204.958 us (-5.19%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12748.236 | 12558.221 | -190.016 KiB (-1.49%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5103.863 | 3978.863 | -1125.000 KiB (-22.04%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 21963.875 | 22314.375 | +350.500 us (+1.60%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 281.983 | 253.014 | -28.970 KiB (-10.27%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.688 | 2.126 | -0.562 KiB (-20.92%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 156043.208 | 150020.709 | -6022.499 us (-3.86%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 283.546 | 254.514 | -29.032 KiB (-10.24%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.720 | 2.157 | -0.562 KiB (-20.68%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6652.167 | 4990.583 | -1661.584 us (-24.98%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 402.662 | 348.185 | -54.478 KiB (-13.53%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 245.097 | 201.019 | -44.078 KiB (-17.98%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 899.292 | 727.666 | -171.626 us (-19.08%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 69.286 | 61.504 | -7.782 KiB (-11.23%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 34.177 | 28.630 | -5.547 KiB (-16.23%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4076.250 | 3843.917 | -232.333 us (-5.70%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 360.378 | 312.854 | -47.524 KiB (-13.19%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 190.003 | 152.925 | -37.078 KiB (-19.51%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 622.042 | 592.958 | -29.084 us (-4.68%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 61.471 | 54.595 | -6.876 KiB (-11.19%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.606 | 18.919 | -4.688 KiB (-19.86%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8128.584 | 7936.542 | -192.042 us (-2.36%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 531.056 | 469.438 | -61.618 KiB (-11.60%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 317.237 | 261.519 | -55.719 KiB (-17.56%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1156.041 | 1251.667 | +95.626 us (+8.27%) | 9 | slower |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 86.559 | 77.737 | -8.821 KiB (-10.19%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 42.489 | 35.435 | -7.055 KiB (-16.60%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6187.709 | 5901.791 | -285.918 us (-4.62%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 497.139 | 446.466 | -50.673 KiB (-10.19%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 261.722 | 217.050 | -44.672 KiB (-17.07%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 915.334 | 890.125 | -25.209 us (-2.75%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 81.329 | 73.828 | -7.501 KiB (-9.22%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.903 | 27.231 | -5.672 KiB (-17.24%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10120.000 | 9456.292 | -663.708 us (-6.56%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 686.044 | 603.621 | -82.423 KiB (-12.01%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 415.769 | 343.972 | -71.797 KiB (-17.27%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1418.375 | 1354.250 | -64.125 us (-4.52%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 105.635 | 93.884 | -11.751 KiB (-11.12%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 54.958 | 45.872 | -9.086 KiB (-16.53%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 7834.375 | 7446.833 | -387.542 us (-4.95%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 639.041 | 570.142 | -68.899 KiB (-10.78%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 339.104 | 281.354 | -57.750 KiB (-17.03%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1150.167 | 1121.625 | -28.542 us (-2.48%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 99.258 | 89.460 | -9.798 KiB (-9.87%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.911 | 35.599 | -7.312 KiB (-17.04%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 379.533 | 245.376 | -134.157 KiB (-35.35%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 290.361 | 132.455 | -157.906 KiB (-54.38%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.497 | 0.518 | +0.021 ms (+4.16%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.672 | 0.661 | -0.011 ms (-1.64%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 4.354 | 4.084 | -0.271 ms (-6.22%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 45704.717 | 49174.290 | +3469.573 roots/s (+7.59%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 4.989 | 4.529 | -0.460 ms (-9.21%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 40878.896 | 45147.145 | +4268.249 roots/s (+10.44%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 7.195 | 6.645 | -0.550 ms (-7.64%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 27860.974 | 29932.466 | +2071.493 roots/s (+7.44%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 196.382 | 159.319 | -37.062 KiB (-18.87%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 41.003 | 39.667 | -1.336 KiB (-3.26%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 73.391 | 66.470 | -6.921 KiB (-9.43%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 13.382 | 11.367 | -2.015 KiB (-15.06%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1221.868 | 1091.086 | -130.782 KiB (-10.70%) | 3 | smaller |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.383 | 418.883 | -112.500 KiB (-21.17%) | 3 | smaller |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.692 | 0.565 | -0.127 ms (-18.35%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.033 | 0.913 | -0.120 ms (-11.63%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 7.763 | 7.200 | -0.562 ms (-7.24%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 25919.608 | 27757.538 | +1837.930 roots/s (+7.09%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 8.596 | 7.639 | -0.957 ms (-11.13%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 23447.802 | 25732.849 | +2285.047 roots/s (+9.75%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 11.350 | 9.834 | -1.516 ms (-13.35%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 17592.212 | 20051.215 | +2459.003 roots/s (+13.98%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 665.918 | 571.597 | -94.321 KiB (-14.16%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 31.732 | 29.325 | -2.407 KiB (-7.59%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 188.973 | 162.628 | -26.345 KiB (-13.94%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 5.107 | 4.545 | -0.562 KiB (-11.01%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1629.948 | 1477.900 | -152.048 KiB (-9.33%) | 3 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.808 | 771.251 | -112.557 KiB (-12.74%) | 3 | smaller |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.801 | 0.748 | -0.053 ms (-6.59%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 1.910 | 1.789 | -0.120 ms (-6.31%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 20.263 | 19.067 | -1.196 ms (-5.90%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 9808.169 | 10469.194 | +661.025 roots/s (+6.74%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 21.165 | 20.141 | -1.024 ms (-4.84%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 9382.330 | 10092.642 | +710.312 roots/s (+7.57%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 23.969 | 22.780 | -1.190 ms (-4.96%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 8361.859 | 8816.706 | +454.847 roots/s (+5.44%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1066.283 | 944.572 | -121.711 KiB (-11.41%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 53.752 | 54.428 | +0.676 KiB (+1.26%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 297.457 | 265.509 | -31.948 KiB (-10.74%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 7.949 | 7.330 | -0.619 KiB (-7.79%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1356.667 | 1338.964 | -17.703 KiB (-1.30%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.414 | 441.914 | -112.500 KiB (-20.29%) | 3 | smaller |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.843 | 0.858 | +0.015 ms (+1.76%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.428 | 1.443 | +0.015 ms (+1.07%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 14.849 | 14.170 | -0.678 ms (-4.57%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 13457.479 | 14073.976 | +616.498 roots/s (+4.58%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 14.628 | 13.853 | -0.775 ms (-5.30%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 13452.726 | 14385.643 | +932.917 roots/s (+6.93%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 18.029 | 17.265 | -0.764 ms (-4.24%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 11218.597 | 11624.247 | +405.650 roots/s (+3.62%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1145.230 | 1033.448 | -111.782 KiB (-9.76%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 41.182 | 38.556 | -2.626 KiB (-6.38%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 307.629 | 278.679 | -28.950 KiB (-9.41%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 5.764 | 5.201 | -0.562 KiB (-9.76%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 253.656 | 196.410 | -57.246 KiB (-22.57%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 174.895 | 104.688 | -70.207 KiB (-40.14%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.466 | 0.454 | -0.011 ms (-2.39%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.619 | 0.618 | -0.001 ms (-0.15%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 4.736 | 4.404 | -0.333 ms (-7.03%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 38246.710 | 45319.781 | +7073.071 roots/s (+18.49%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 5.402 | 5.067 | -0.335 ms (-6.20%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 37572.211 | 40685.552 | +3113.340 roots/s (+8.29%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 7.783 | 7.349 | -0.434 ms (-5.57%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 25095.677 | 27443.312 | +2347.635 roots/s (+9.35%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 183.117 | 153.020 | -30.098 KiB (-16.44%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 28.152 | 27.016 | -1.137 KiB (-4.04%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 64.733 | 58.934 | -5.800 KiB (-8.96%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 3.064 | 2.863 | -0.201 KiB (-6.56%) | 6 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 4.280 | 4.207 | -0.073 us/projection (-1.70%) | 9 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 231743.784 | 234432.249 | +2688.465 projections/s (+1.16%) | 9 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 37.535 | 36.918 | -0.617 KiB (-1.64%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 45.827 | 45.772 | -0.055 KiB (-0.12%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 460.703 | 419.938 | -40.766 B/projection (-8.85%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 139.859 | 170.750 | +30.891 B/projection (+22.09%) | 3 | larger |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 5.381 | 5.003 | -0.378 us/projection (-7.02%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 187545.799 | 200548.365 | +13002.566 projections/s (+6.93%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 40.730 | 36.613 | -4.117 KiB (-10.11%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 61.998 | 61.943 | -0.055 KiB (-0.09%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 460.703 | 419.938 | -40.766 B/projection (-8.85%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 190.984 | 165.875 | -25.109 B/projection (-13.15%) | 3 | smaller |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 7.782 | 7.387 | -0.395 ms (-5.08%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 25748.171 | 27269.162 | +1520.991 roots/s (+5.91%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 8.596 | 8.121 | -0.475 ms (-5.52%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 23220.152 | 24488.047 | +1267.895 roots/s (+5.46%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 15.248 | 14.426 | -0.822 ms (-5.39%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 13162.839 | 13886.880 | +724.042 roots/s (+5.50%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 15.156 | 14.503 | -0.653 ms (-4.31%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 13153.027 | 13763.875 | +610.847 roots/s (+4.64%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.elapsedUsPerRoot | 103.724 | 103.276 | -0.448 us/root (-0.43%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.peakKiB | 442.059 | 439.901 | -2.157 KiB (-0.49%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.retainedKiB | 162.484 | 159.484 | -3.000 KiB (-1.85%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.elapsedUsPerRoot | 103.405 | 103.137 | -0.268 us/root (-0.26%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.peakKiB | 447.270 | 444.925 | -2.345 KiB (-0.52%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.retainedKiB | 162.484 | 159.484 | -3.000 KiB (-1.85%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.elapsedUsPerRoot | 354.185 | 350.977 | -3.208 us/root (-0.91%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.peakKiB | 952.093 | 947.990 | -4.103 KiB (-0.43%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.retainedKiB | 313.047 | 310.047 | -3.000 KiB (-0.96%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.elapsedUsPerRoot | 358.415 | 354.074 | -4.341 us/root (-1.21%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.peakKiB | 955.663 | 951.490 | -4.173 KiB (-0.44%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.retainedKiB | 313.047 | 310.047 | -3.000 KiB (-0.96%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.elapsedUsPerRoot | 385.973 | 386.794 | +0.822 us/root (+0.21%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.peakKiB | 770.371 | 767.776 | -2.595 KiB (-0.34%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.retainedKiB | 192.965 | 189.965 | -3.000 KiB (-1.55%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.elapsedUsPerRoot | 384.467 | 432.684 | +48.216 us/root (+12.54%) | 9 | slower |
| 3.14 | provider-free-delivery | leaf-date | document.peakKiB | 774.168 | 771.315 | -2.853 KiB (-0.37%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.retainedKiB | 192.965 | 189.965 | -3.000 KiB (-1.55%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.elapsedUsPerRoot | 847.417 | 872.038 | +24.621 us/root (+2.91%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.peakKiB | 1298.807 | 1293.759 | -5.048 KiB (-0.39%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.retainedKiB | 271.797 | 268.797 | -3.000 KiB (-1.10%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.elapsedUsPerRoot | 862.768 | 859.160 | -3.608 us/root (-0.42%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.peakKiB | 1302.635 | 1297.587 | -5.048 KiB (-0.39%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.retainedKiB | 271.797 | 268.797 | -3.000 KiB (-1.10%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.elapsedUsPerRoot | 751.283 | 740.673 | -10.609 us/root (-1.41%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.peakKiB | 689.181 | 685.078 | -4.103 KiB (-0.60%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.retainedKiB | 211.984 | 208.984 | -3.000 KiB (-1.42%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.elapsedUsPerRoot | 741.904 | 744.378 | +2.474 us/root (+0.33%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.peakKiB | 692.751 | 688.578 | -4.173 KiB (-0.60%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.retainedKiB | 211.984 | 208.984 | -3.000 KiB (-1.42%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.elapsedUsPerRoot | 280.573 | 279.826 | -0.747 us/root (-0.27%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.peakKiB | 655.274 | 651.172 | -4.103 KiB (-0.63%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.retainedKiB | 211.984 | 208.984 | -3.000 KiB (-1.42%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.elapsedUsPerRoot | 280.940 | 340.111 | +59.171 us/root (+21.06%) | 9 | slower |
| 3.14 | provider-free-delivery | leaf-float64 | document.peakKiB | 658.845 | 654.672 | -4.173 KiB (-0.63%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.retainedKiB | 211.984 | 208.984 | -3.000 KiB (-1.42%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.elapsedUsPerRoot | 144.564 | 144.773 | +0.210 us/root (+0.15%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.peakKiB | 634.207 | 632.050 | -2.157 KiB (-0.34%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.retainedKiB | 354.480 | 351.480 | -3.000 KiB (-0.85%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.elapsedUsPerRoot | 145.108 | 144.806 | -0.302 us/root (-0.21%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.peakKiB | 639.418 | 637.073 | -2.345 KiB (-0.37%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.retainedKiB | 354.480 | 351.480 | -3.000 KiB (-0.85%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.elapsedUsPerRoot | 150.009 | 150.198 | +0.189 us/root (+0.13%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.peakKiB | 646.176 | 644.019 | -2.157 KiB (-0.33%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.retainedKiB | 366.484 | 363.484 | -3.000 KiB (-0.82%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.elapsedUsPerRoot | 149.950 | 150.216 | +0.266 us/root (+0.18%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.peakKiB | 651.387 | 649.042 | -2.345 KiB (-0.36%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.retainedKiB | 366.484 | 363.484 | -3.000 KiB (-0.82%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.elapsedUsPerRoot | 504.777 | 505.074 | +0.297 us/root (+0.06%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.peakKiB | 827.571 | 823.469 | -4.103 KiB (-0.50%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.retainedKiB | 277.984 | 274.984 | -3.000 KiB (-1.08%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.elapsedUsPerRoot | 510.993 | 508.408 | -2.586 us/root (-0.51%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.peakKiB | 831.142 | 826.969 | -4.173 KiB (-0.50%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.retainedKiB | 277.984 | 274.984 | -3.000 KiB (-1.08%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.elapsedUsPerRoot | 753.665 | 755.023 | +1.358 us/root (+0.18%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.peakKiB | 936.304 | 930.834 | -5.470 KiB (-0.58%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.retainedKiB | 303.467 | 301.736 | -1.730 KiB (-0.57%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.elapsedUsPerRoot | 762.375 | 757.583 | -4.792 us/root (-0.63%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.peakKiB | 937.481 | 931.648 | -5.833 KiB (-0.62%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.retainedKiB | 303.564 | 299.734 | -3.830 KiB (-1.26%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.elapsedUsPerRoot | 515.780 | 528.056 | +12.276 us/root (+2.38%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.peakKiB | 1277.242 | 1272.265 | -4.978 KiB (-0.39%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.retainedKiB | 321.297 | 318.297 | -3.000 KiB (-0.93%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.elapsedUsPerRoot | 511.044 | 547.742 | +36.698 us/root (+7.18%) | 9 | slower |
| 3.14 | provider-free-delivery | leaf-uuid | document.peakKiB | 1281.070 | 1276.022 | -5.048 KiB (-0.39%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.retainedKiB | 321.297 | 318.297 | -3.000 KiB (-0.93%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 28.849 | 28.589 | -0.260 us/root (-0.90%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 95.539 | 90.562 | -4.978 KiB (-5.21%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.109 | 48.109 | -3.000 KiB (-5.87%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 29.180 | 28.482 | -0.698 us/root (-2.39%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 99.250 | 94.202 | -5.048 KiB (-5.09%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.109 | 48.109 | -3.000 KiB (-5.87%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 43.197 | 42.766 | -0.431 us/root (-1.00%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 145.752 | 142.028 | -3.724 KiB (-2.55%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.234 | 85.234 | -3.000 KiB (-3.40%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 42.566 | 42.562 | -0.004 us/root (-0.01%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 149.158 | 145.364 | -3.794 KiB (-2.54%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.234 | 85.234 | -3.000 KiB (-3.40%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 60.350 | 60.348 | -0.003 us/root (-0.00%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 220.354 | 217.618 | -2.735 KiB (-1.24%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.734 | 134.734 | -3.000 KiB (-2.18%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 60.478 | 60.781 | +0.303 us/root (+0.50%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 224.174 | 221.524 | -2.649 KiB (-1.18%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.734 | 134.734 | -3.000 KiB (-2.18%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 20.944 | 20.488 | -0.456 us/root (-2.18%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 58.370 | 53.623 | -4.747 KiB (-8.13%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.359 | 21.359 | -3.000 KiB (-12.32%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 21.388 | 20.398 | -0.990 us/root (-4.63%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 65.917 | 60.990 | -4.927 KiB (-7.47%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.359 | 21.359 | -3.000 KiB (-12.32%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 140.773 | 151.094 | +10.320 us/root (+7.33%) | 9 | slower |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 624.949 | 622.698 | -2.251 KiB (-0.36%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.359 | 425.359 | -3.000 KiB (-0.70%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 141.229 | 140.975 | -0.254 us/root (-0.18%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 629.922 | 627.507 | -2.415 KiB (-0.38%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.359 | 425.359 | -3.000 KiB (-0.70%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 52.576 | 51.773 | -0.802 us/root (-1.53%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 193.785 | 190.972 | -2.813 KiB (-1.45%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.359 | 122.359 | -3.000 KiB (-2.39%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 52.224 | 51.677 | -0.547 us/root (-1.05%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 197.992 | 195.390 | -2.603 KiB (-1.31%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.359 | 122.359 | -3.000 KiB (-2.39%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 44.882 | 44.294 | -0.587 us/root (-1.31%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 125.427 | 120.545 | -4.882 KiB (-3.89%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.203 | 33.203 | -3.000 KiB (-8.29%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 45.529 | 44.324 | -1.204 us/root (-2.65%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 129.138 | 124.225 | -4.913 KiB (-3.80%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.203 | 33.203 | -3.000 KiB (-8.29%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 50.009 | 49.687 | -0.322 us/root (-0.64%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 217.340 | 215.183 | -2.157 KiB (-0.99%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.984 | 133.984 | -3.000 KiB (-2.19%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 50.155 | 49.824 | -0.331 us/root (-0.66%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 222.434 | 220.089 | -2.345 KiB (-1.05%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.984 | 133.984 | -3.000 KiB (-2.19%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 133.833 | 133.557 | -0.276 us/root (-0.21%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 760.059 | 757.901 | -2.157 KiB (-0.28%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.484 | 477.484 | -3.000 KiB (-0.62%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 132.728 | 132.089 | -0.639 us/root (-0.48%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 765.152 | 762.808 | -2.345 KiB (-0.31%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.484 | 477.484 | -3.000 KiB (-0.62%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 224.250 | 232.667 | +8.417 us (+3.75%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 28.824 | 30.238 | +1.414 KiB (+4.91%) | 3 | larger |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 22.754 | 22.730 | -0.023 KiB (-0.10%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 330.125 | 342.417 | +12.292 us (+3.72%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 38.890 | 40.038 | +1.148 KiB (+2.95%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 31.702 | 31.601 | -0.102 KiB (-0.32%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 431.042 | 443.000 | +11.958 us (+2.77%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 47.736 | 48.908 | +1.172 KiB (+2.45%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 40.123 | 39.947 | -0.176 KiB (-0.44%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 82.917 | 81.792 | -1.125 us (-1.36%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 17.204 | 18.310 | +1.105 KiB (+6.43%) | 3 | larger |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 11.880 | 11.888 | +0.008 KiB (+0.07%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 85.417 | 84.666 | -0.751 us (-0.88%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 17.348 | 18.457 | +1.109 KiB (+6.39%) | 3 | larger |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 12.168 | 12.176 | +0.008 KiB (+0.06%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 77.292 | 82.042 | +4.750 us (+6.15%) | 9 | slower |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 17.204 | 18.310 | +1.105 KiB (+6.43%) | 3 | larger |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 11.880 | 11.888 | +0.008 KiB (+0.07%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 78.166 | 85.291 | +7.125 us (+9.12%) | 9 | slower |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 17.352 | 18.457 | +1.105 KiB (+6.37%) | 3 | larger |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 12.168 | 12.176 | +0.008 KiB (+0.06%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 78.750 | 81.333 | +2.583 us (+3.28%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 17.205 | 18.311 | +1.105 KiB (+6.43%) | 3 | larger |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 11.877 | 11.889 | +0.012 KiB (+0.10%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 82.292 | 84.208 | +1.916 us (+2.33%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 17.353 | 18.458 | +1.105 KiB (+6.37%) | 3 | larger |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 12.169 | 12.177 | +0.008 KiB (+0.06%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 1.917 | 1.917 | -0.000 us (-0.00%) | 9 | within noise |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 2.250 | 2.250 | +0.000 us (+0.00%) | 9 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 2.792 | 2.709 | -0.083 us (-2.97%) | 9 | within noise |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | result-held-metadata | control-held | large.closed.retainedKiB | 76.867 | 73.367 | -3.500 KiB (-4.55%) | 3 | smaller |
| 3.14 | result-held-metadata | control-held | large.shared.retainedKiB | 55.297 | 51.797 | -3.500 KiB (-6.33%) | 3 | smaller |
| 3.14 | result-held-metadata | control-held | small.closed.retainedKiB | 126.336 | 105.336 | -21.000 KiB (-16.62%) | 3 | smaller |
| 3.14 | result-held-metadata | control-held | small.shared.retainedKiB | 118.828 | 97.828 | -21.000 KiB (-17.67%) | 3 | smaller |

## write-lowering

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 177.250 | 173.000 | -4.250 us/row (-2.40%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 848.000 | 840.000 | -8.000 B/row (-0.94%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 9036.000 | 9028.000 | -8.000 B/row (-0.09%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 183.834 | 174.833 | -9.001 us/row (-4.90%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 848.000 | 840.000 | -8.000 B/row (-0.94%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 10013.000 | 10005.000 | -8.000 B/row (-0.08%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 224.833 | 220.458 | -4.375 us/row (-1.95%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 848.000 | 840.000 | -8.000 B/row (-0.94%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 7410.000 | 7402.000 | -8.000 B/row (-0.11%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 200.500 | 193.333 | -7.167 us/row (-3.57%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 848.000 | 840.000 | -8.000 B/row (-0.94%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 8131.000 | 8123.000 | -8.000 B/row (-0.10%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 232.167 | 231.292 | -0.875 us/row (-0.38%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1128.000 | 1120.000 | -8.000 B/row (-0.71%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 11800.000 | 11792.000 | -8.000 B/row (-0.07%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 214.000 | 209.708 | -4.292 us/row (-2.01%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1128.000 | 1120.000 | -8.000 B/row (-0.71%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 12858.000 | 12850.000 | -8.000 B/row (-0.06%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 445.250 | 452.292 | +7.042 us/row (+1.58%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2248.000 | 2240.000 | -8.000 B/row (-0.36%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 20116.000 | 20108.000 | -8.000 B/row (-0.04%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 363.125 | 360.750 | -2.375 us/row (-0.65%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2248.000 | 2240.000 | -8.000 B/row (-0.36%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23398.000 | 23390.000 | -8.000 B/row (-0.03%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 280.916 | 261.709 | -19.207 us/row (-6.84%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 1624.000 | 1616.000 | -8.000 B/row (-0.49%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 18643.000 | 18635.000 | -8.000 B/row (-0.04%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 256.542 | 253.083 | -3.459 us/row (-1.35%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 1656.000 | 1648.000 | -8.000 B/row (-0.48%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 19119.000 | 19095.000 | -24.000 B/row (-0.13%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 269.416 | 259.208 | -10.208 us/row (-3.79%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 1624.000 | 1616.000 | -8.000 B/row (-0.49%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 17838.000 | 17830.000 | -8.000 B/row (-0.04%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 254.042 | 251.417 | -2.625 us/row (-1.03%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 1656.000 | 1648.000 | -8.000 B/row (-0.48%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 18314.000 | 18274.000 | -40.000 B/row (-0.22%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | elapsedUs | 431.792 | 432.959 | +1.167 us/row (+0.27%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | transientBytes | 24587.000 | 24587.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | elapsedUs | 418.875 | 419.875 | +1.000 us/row (+0.24%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | transientBytes | 24070.000 | 24070.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | elapsedUs | 458.916 | 442.792 | -16.124 us/row (-3.51%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | retainedBytes | 2040.000 | 2040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | transientBytes | 24555.000 | 24555.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | elapsedUs | 424.583 | 431.583 | +7.000 us/row (+1.65%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | transientBytes | 24587.000 | 24587.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | elapsedUs | 441.459 | 435.375 | -6.084 us/row (-1.38%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | retainedBytes | 2040.000 | 2040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | transientBytes | 24038.000 | 24038.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | elapsedUs | 418.291 | 416.125 | -2.166 us/row (-0.52%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | transientBytes | 24070.000 | 24070.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 124.000 | 124.833 | +0.833 us/row (+0.67%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1544.000 | 1544.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 7892.000 | 7892.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 124.000 | 125.000 | +1.000 us/row (+0.81%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1544.000 | 1544.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 8292.000 | 8292.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 160.042 | 163.000 | +2.958 us/row (+1.85%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2216.000 | 2216.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 9653.000 | 9653.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 157.541 | 159.916 | +2.375 us/row (+1.51%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2216.000 | 2216.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 9937.000 | 9937.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 208.459 | 209.209 | +0.750 us/row (+0.36%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3112.000 | 3112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 12882.000 | 12882.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 209.583 | 211.291 | +1.708 us/row (+0.81%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3112.000 | 3112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 12992.000 | 12992.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 96.833 | 100.292 | +3.459 us/row (+3.57%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1040.000 | 1040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 6857.000 | 6857.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 100.125 | 103.417 | +3.292 us/row (+3.29%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1040.000 | 1040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 7007.000 | 7007.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 439.625 | 436.583 | -3.042 us/row (-0.69%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8504.000 | 8504.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 26816.000 | 26816.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 434.334 | 436.291 | +1.957 us/row (+0.45%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8504.000 | 8504.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 27107.000 | 27107.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 185.833 | 186.708 | +0.875 us/row (+0.47%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 2936.000 | 2936.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 11360.000 | 11360.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 184.541 | 188.666 | +4.125 us/row (+2.24%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 2936.000 | 2936.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 11684.000 | 11684.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 167.667 | 166.291 | -1.376 us/row (-0.82%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1544.000 | 1544.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 7705.000 | 7705.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 166.083 | 169.042 | +2.959 us/row (+1.78%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1544.000 | 1544.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 8089.000 | 8089.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 205.625 | 206.291 | +0.666 us/row (+0.32%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2384.000 | 2384.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 10887.000 | 10887.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 204.084 | 207.416 | +3.332 us/row (+1.63%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2384.000 | 2384.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 11328.000 | 11328.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 536.792 | 536.666 | -0.126 us/row (-0.02%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5744.000 | 5744.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23127.000 | 23127.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 533.833 | 534.708 | +0.875 us/row (+0.16%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5744.000 | 5744.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 24672.000 | 24672.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 127.375 | 128.375 | +1.000 us/row (+0.79%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 1832.000 | 1832.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 7245.000 | 7237.000 | -8.000 B/row (-0.11%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 117.209 | 118.000 | +0.791 us/row (+0.67%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 1864.000 | 1864.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 8109.000 | 8085.000 | -24.000 B/row (-0.30%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 136.958 | 138.167 | +1.209 us/row (+0.88%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 1832.000 | 1832.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 8169.000 | 8161.000 | -8.000 B/row (-0.10%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 124.750 | 126.958 | +2.208 us/row (+1.77%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 1864.000 | 1864.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 9033.000 | 9009.000 | -24.000 B/row (-0.27%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.applyPatches | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.detachJsonContainer | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedMany | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.occurrenceShape | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.columns.wire | elapsedUs | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.columns.wire | retainedBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.columns.wire | transientBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.applyPatches | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.detachJsonContainer | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedMany | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.occurrenceShape | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.document.wire | elapsedUs | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.document.wire | retainedBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-patch.document.wire | transientBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.applyPatches | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.detachJsonContainer | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedMany | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.occurrenceShape | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.typed | elapsedUs | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.typed | retainedBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.typed | transientBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.applyPatches | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.detachJsonContainer | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedMany | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.occurrenceShape | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.wire | elapsedUs | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.wire | retainedBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.columns.wire | transientBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.applyPatches | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.detachJsonContainer | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedMany | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.occurrenceShape | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.typed | elapsedUs | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.typed | retainedBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.typed | transientBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.applyPatches | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.detachJsonContainer | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedMany | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.occurrenceShape | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.wire | elapsedUs | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.wire | retainedBytes | | | | | missing on head |
| 3.13 | keyed-write | plain.target-replace.document.wire | transientBytes | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 186.250 | 181.084 | -5.166 us/row (-2.77%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 1576.000 | 1568.000 | -8.000 B/row (-0.51%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 10314.000 | 10306.000 | -8.000 B/row (-0.08%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 180.750 | 172.791 | -7.959 us/row (-4.40%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 1608.000 | 1600.000 | -8.000 B/row (-0.50%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 10918.000 | 10894.000 | -24.000 B/row (-0.22%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 203.958 | 197.334 | -6.624 us/row (-3.25%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 1576.000 | 1568.000 | -8.000 B/row (-0.51%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 11508.000 | 11500.000 | -8.000 B/row (-0.07%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 188.125 | 183.042 | -5.083 us/row (-2.70%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 1608.000 | 1600.000 | -8.000 B/row (-0.50%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 11872.000 | 11848.000 | -24.000 B/row (-0.20%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 124.792 | 125.291 | +0.499 us/row (+0.40%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1768.000 | 1768.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 9851.000 | 9851.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 125.250 | 126.834 | +1.584 us/row (+1.26%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1960.000 | 1960.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 10211.000 | 10211.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 123.250 | 126.667 | +3.417 us/row (+2.77%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 1768.000 | 1768.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 9574.000 | 9574.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 127.292 | 127.042 | -0.250 us/row (-0.20%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 1960.000 | 1960.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 9974.000 | 9974.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | elapsedUs | 321.459 | 321.833 | +0.374 us/row (+0.12%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | transientBytes | 17711.000 | 17711.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | elapsedUs | 327.167 | 328.416 | +1.249 us/row (+0.38%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.document.wire | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-patch.document.wire | transientBytes | 18312.000 | 18312.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | elapsedUs | 334.333 | 343.916 | +9.583 us/row (+2.87%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | retainedBytes | 1992.000 | 1992.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | transientBytes | 17679.000 | 17679.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | elapsedUs | 324.334 | 324.667 | +0.333 us/row (+0.10%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | transientBytes | 17711.000 | 17711.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | elapsedUs | 341.000 | 345.875 | +4.875 us/row (+1.43%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.typed | retainedBytes | 1992.000 | 1992.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.typed | transientBytes | 18280.000 | 18280.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | elapsedUs | 327.750 | 332.834 | +5.084 us/row (+1.55%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.wire | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.wire | transientBytes | 18312.000 | 18312.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 31.834 | 34.292 | +2.458 us/row (+7.72%) | 9 | slower |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 3642.000 | 3642.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 27.000 | 28.834 | +1.834 us/row (+6.79%) | 9 | slower |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 3590.000 | 3502.000 | -88.000 B/row (-2.45%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 32.459 | 34.084 | +1.625 us/row (+5.01%) | 9 | slower |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 3644.000 | 3644.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 26.875 | 28.958 | +2.083 us/row (+7.75%) | 9 | slower |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 3593.000 | 3505.000 | -88.000 B/row (-2.45%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3354.667 | 3356.791 | +2.124 us (+0.06%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | retainedBytes | 427360.000 | 436748.000 | +9388.000 B (+2.20%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 439696.000 | 449012.000 | +9316.000 B (+2.12%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | 302.709 | 310.167 | +7.458 us (+2.46%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | 24056.000 | 24438.000 | +382.000 B (+1.59%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared.family | transientBytes | 28416.000 | 28798.000 | +382.000 B (+1.34%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 19.936 | 19.848 | -0.087 us/row (-0.44%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 915.500 | 924.125 | +8.625 B/row (+0.94%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 1822.250 | 1823.188 | +0.938 B/row (+0.05%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 20.653 | 20.999 | +0.346 us/row (+1.67%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1917.000 | 1925.625 | +8.625 B/row (+0.45%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2222.328 | 2222.328 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 24.969 | 24.043 | -0.926 us/row (-3.71%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1047.000 | 1081.500 | +34.500 B/row (+3.30%) | 1 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2266.375 | 2266.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 26.461 | 25.003 | -1.458 us/row (-5.51%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2053.000 | 2087.500 | +34.500 B/row (+1.68%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 2588.688 | 2588.688 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 40.896 | 42.750 | +1.854 us/row (+4.53%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1581.000 | 1719.000 | +138.000 B/row (+8.73%) | 1 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 3734.500 | 3734.500 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 42.021 | 42.208 | +0.187 us/row (+0.45%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2605.000 | 2743.000 | +138.000 B/row (+5.30%) | 1 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 3966.750 | 3966.750 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.columns | elapsedUs | 129.738 | 130.943 | +1.205 us/row (+0.93%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.columns | retainedBytes | 1565.762 | 1568.512 | +2.750 B/row (+0.18%) | 1 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.columns | transientBytes | 2204.742 | 2204.742 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.document | elapsedUs | 122.282 | 121.981 | -0.301 us/row (-0.25%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.document | retainedBytes | 1769.188 | 1771.938 | +2.750 B/row (+0.16%) | 1 | within noise |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.document | transientBytes | 2673.516 | 2672.539 | -0.977 B/row (-0.04%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.unchanged.objects-128.document | elapsedUs | 51.361 | 51.316 | -0.044 us/row (-0.09%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.unchanged.objects-128.document | retainedBytes | 148.664 | 152.977 | +4.312 B/row (+2.90%) | 1 | within noise |
| 3.13 | predicate-flush | predicate-flush.unchanged.objects-128.document | transientBytes | 1372.406 | 1372.406 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.wide.history-128.document | elapsedUs | 71.495 | 71.704 | +0.209 us/row (+0.29%) | 9 | within noise |
| 3.13 | predicate-flush | predicate-flush.wide.history-128.document | retainedBytes | 1313.566 | 1320.186 | +6.620 B/row (+0.50%) | 1 | within noise |
| 3.13 | predicate-flush | predicate-flush.wide.history-128.document | transientBytes | 6373.853 | 6376.178 | +2.326 B/row (+0.04%) | 9 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | elapsedUs | 63.542 | 64.584 | +1.042 us/row (+1.64%) | 9 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | retainedBytes | 8184.000 | 9312.000 | +1128.000 B/row (+13.78%) | 1 | larger |
| 3.13 | wire-insert-response | response.insert.family.wire | transientBytes | 7696.000 | 7696.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 184.708 | 189.958 | +5.250 us/row (+2.84%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 856.000 | 848.000 | -8.000 B/row (-0.93%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 9716.000 | 9708.000 | -8.000 B/row (-0.08%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 195.875 | 194.167 | -1.708 us/row (-0.87%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 856.000 | 848.000 | -8.000 B/row (-0.93%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 10853.000 | 10845.000 | -8.000 B/row (-0.07%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 222.167 | 226.833 | +4.666 us/row (+2.10%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 856.000 | 848.000 | -8.000 B/row (-0.93%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 8130.000 | 8122.000 | -8.000 B/row (-0.10%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 207.709 | 202.750 | -4.959 us/row (-2.39%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 856.000 | 848.000 | -8.000 B/row (-0.93%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 8987.000 | 8979.000 | -8.000 B/row (-0.09%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 233.250 | 246.125 | +12.875 us/row (+5.52%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1136.000 | 1128.000 | -8.000 B/row (-0.70%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 12592.000 | 12584.000 | -8.000 B/row (-0.06%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 215.875 | 233.834 | +17.959 us/row (+8.32%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1136.000 | 1128.000 | -8.000 B/row (-0.70%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13786.000 | 13778.000 | -8.000 B/row (-0.06%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 429.291 | 435.750 | +6.459 us/row (+1.50%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2256.000 | 2248.000 | -8.000 B/row (-0.35%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 20852.000 | 20844.000 | -8.000 B/row (-0.04%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 348.041 | 366.750 | +18.709 us/row (+5.38%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2256.000 | 2248.000 | -8.000 B/row (-0.35%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 24270.000 | 24262.000 | -8.000 B/row (-0.03%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 277.958 | 277.000 | -0.958 us/row (-0.34%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 1640.000 | 1632.000 | -8.000 B/row (-0.49%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 19483.000 | 19475.000 | -8.000 B/row (-0.04%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 263.250 | 262.625 | -0.625 us/row (-0.24%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 1672.000 | 1664.000 | -8.000 B/row (-0.48%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 20123.000 | 20099.000 | -24.000 B/row (-0.12%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 274.041 | 274.250 | +0.209 us/row (+0.08%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 1640.000 | 1632.000 | -8.000 B/row (-0.49%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 18542.000 | 18534.000 | -8.000 B/row (-0.04%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 254.625 | 264.084 | +9.459 us/row (+3.71%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 1672.000 | 1664.000 | -8.000 B/row (-0.48%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 19182.000 | 19142.000 | -40.000 B/row (-0.21%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | elapsedUs | 433.833 | 432.167 | -1.666 us/row (-0.38%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | transientBytes | 24591.000 | 24591.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | elapsedUs | 427.708 | 432.125 | +4.417 us/row (+1.03%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | transientBytes | 24410.000 | 24410.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | elapsedUs | 457.667 | 457.875 | +0.208 us/row (+0.05%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | transientBytes | 24563.000 | 24563.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | elapsedUs | 432.000 | 433.000 | +1.000 us/row (+0.23%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | transientBytes | 24591.000 | 24591.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | elapsedUs | 458.916 | 460.000 | +1.084 us/row (+0.24%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | transientBytes | 24382.000 | 24382.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | elapsedUs | 428.583 | 430.084 | +1.501 us/row (+0.35%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | transientBytes | 24410.000 | 24410.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 133.250 | 140.292 | +7.042 us/row (+5.28%) | 9 | slower |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1560.000 | 1560.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 8556.000 | 8556.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 130.291 | 135.250 | +4.959 us/row (+3.81%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1560.000 | 1560.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 9020.000 | 9020.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 165.709 | 168.458 | +2.749 us/row (+1.66%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2232.000 | 2232.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10413.000 | 10413.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 166.083 | 169.709 | +3.626 us/row (+2.18%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2232.000 | 2232.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 10769.000 | 10769.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 206.333 | 210.417 | +4.084 us/row (+1.98%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3128.000 | 3128.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 13754.000 | 13754.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 207.833 | 208.292 | +0.459 us/row (+0.22%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3128.000 | 3128.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 13912.000 | 13912.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 108.167 | 112.084 | +3.917 us/row (+3.62%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1048.000 | 1048.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7457.000 | 7457.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 108.000 | 113.583 | +5.583 us/row (+5.17%) | 9 | slower |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1048.000 | 1048.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 7671.000 | 7671.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 424.667 | 421.333 | -3.334 us/row (-0.79%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8520.000 | 8520.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27472.000 | 27472.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 411.083 | 416.875 | +5.792 us/row (+1.41%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8520.000 | 8520.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 27827.000 | 27827.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 188.500 | 190.375 | +1.875 us/row (+0.99%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 2952.000 | 2952.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 12016.000 | 12016.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 187.708 | 192.500 | +4.792 us/row (+2.55%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 2952.000 | 2952.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 12420.000 | 12420.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 174.041 | 189.583 | +15.542 us/row (+8.93%) | 9 | slower |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1560.000 | 1560.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8409.000 | 8409.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 171.000 | 173.375 | +2.375 us/row (+1.39%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1560.000 | 1560.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 8857.000 | 8857.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 205.208 | 205.875 | +0.667 us/row (+0.33%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2400.000 | 2400.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11607.000 | 11607.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 206.375 | 215.291 | +8.916 us/row (+4.32%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2400.000 | 2400.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 497.291 | 498.750 | +1.459 us/row (+0.29%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23847.000 | 23847.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 504.125 | 516.791 | +12.666 us/row (+2.51%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 25456.000 | 25456.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | elapsedUs | 469.833 | 448.209 | -21.624 us/row (-4.60%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | transientBytes | 20813.000 | 20813.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | elapsedUs | 515.875 | 510.709 | -5.166 us/row (-1.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | transientBytes | 21021.000 | 21021.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | elapsedUs | 453.666 | 457.875 | +4.209 us/row (+0.93%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | transientBytes | 21822.000 | 21822.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | elapsedUs | 513.375 | 507.500 | -5.875 us/row (-1.14%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | transientBytes | 22030.000 | 22030.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | elapsedUs | 518.125 | 508.458 | -9.667 us/row (-1.87%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | transientBytes | 44259.000 | 44259.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | elapsedUs | 662.458 | 684.667 | +22.209 us/row (+3.35%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | retainedBytes | 15376.000 | 15376.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | transientBytes | 53875.000 | 53875.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | elapsedUs | 517.750 | 518.167 | +0.417 us/row (+0.08%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | transientBytes | 47148.000 | 47148.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | elapsedUs | 657.750 | 669.834 | +12.084 us/row (+1.84%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | retainedBytes | 15376.000 | 15376.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | transientBytes | 56764.000 | 56764.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | elapsedUs | 573.083 | 561.250 | -11.833 us/row (-2.06%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | transientBytes | 32994.000 | 32994.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | elapsedUs | 781.000 | 775.417 | -5.583 us/row (-0.71%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | transientBytes | 39338.000 | 39338.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | elapsedUs | 576.250 | 566.208 | -10.042 us/row (-1.74%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | transientBytes | 34475.000 | 34475.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | elapsedUs | 787.042 | 804.375 | +17.333 us/row (+2.20%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | transientBytes | 40819.000 | 40819.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | elapsedUs | 960.292 | 950.333 | -9.959 us/row (-1.04%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | transientBytes | 35869.000 | 35869.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | elapsedUs | 1692.000 | 1689.292 | -2.708 us/row (-0.16%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | retainedBytes | 29008.000 | 29008.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | transientBytes | 59209.000 | 59209.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | elapsedUs | 957.666 | 948.167 | -9.499 us/row (-0.99%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | transientBytes | 37478.000 | 37478.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | elapsedUs | 1709.417 | 1697.959 | -11.458 us/row (-0.67%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | retainedBytes | 29008.000 | 29008.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | transientBytes | 60818.000 | 60818.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | elapsedUs | 826.875 | 829.458 | +2.583 us/row (+0.31%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | retainedBytes | 10368.000 | 10368.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | transientBytes | 30549.000 | 30549.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | elapsedUs | 1181.000 | 1190.500 | +9.500 us/row (+0.80%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | retainedBytes | 10576.000 | 10576.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | transientBytes | 30757.000 | 30757.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | elapsedUs | 830.292 | 837.250 | +6.958 us/row (+0.84%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | retainedBytes | 10368.000 | 10368.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | transientBytes | 31646.000 | 31646.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | elapsedUs | 1187.917 | 1194.583 | +6.666 us/row (+0.56%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | retainedBytes | 10576.000 | 10576.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | transientBytes | 31854.000 | 31854.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | elapsedUs | 508.167 | 515.500 | +7.333 us/row (+1.44%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | transientBytes | 21285.000 | 21285.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | elapsedUs | 597.625 | 585.125 | -12.500 us/row (-2.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | transientBytes | 21493.000 | 21493.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | elapsedUs | 510.125 | 522.542 | +12.417 us/row (+2.43%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | transientBytes | 22382.000 | 22382.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | elapsedUs | 594.375 | 588.750 | -5.625 us/row (-0.95%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | transientBytes | 22590.000 | 22590.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | elapsedUs | 469.625 | 481.916 | +12.291 us/row (+2.62%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | transientBytes | 22038.000 | 22038.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | elapsedUs | 592.250 | 610.875 | +18.625 us/row (+3.14%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | retainedBytes | 12096.000 | 12096.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | transientBytes | 28334.000 | 28334.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | elapsedUs | 472.000 | 471.750 | -0.250 us/row (-0.05%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | transientBytes | 23286.000 | 23286.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | elapsedUs | 588.833 | 627.250 | +38.417 us/row (+6.52%) | 9 | slower |
| 3.14 | keyed-write | leaf.int32.document.wire | retainedBytes | 12096.000 | 12096.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | transientBytes | 29582.000 | 29582.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | elapsedUs | 495.667 | 492.500 | -3.167 us/row (-0.64%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | transientBytes | 23018.000 | 23018.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | elapsedUs | 618.750 | 644.084 | +25.334 us/row (+4.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | transientBytes | 29370.000 | 29370.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | elapsedUs | 484.333 | 487.292 | +2.959 us/row (+0.61%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | transientBytes | 24462.000 | 24462.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | elapsedUs | 619.333 | 623.500 | +4.167 us/row (+0.67%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | transientBytes | 30814.000 | 30814.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | elapsedUs | 618.500 | 627.958 | +9.458 us/row (+1.53%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | transientBytes | 24052.000 | 24052.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | elapsedUs | 614.083 | 616.291 | +2.208 us/row (+0.36%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | retainedBytes | 5968.000 | 5968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | transientBytes | 25661.000 | 25661.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | elapsedUs | 627.000 | 625.625 | -1.375 us/row (-0.22%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | transientBytes | 35554.000 | 35554.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | elapsedUs | 867.250 | 861.000 | -6.250 us/row (-0.72%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | transientBytes | 41898.000 | 41898.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | elapsedUs | 622.417 | 632.541 | +10.124 us/row (+1.63%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | transientBytes | 37355.000 | 37355.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | elapsedUs | 866.542 | 848.458 | -18.084 us/row (-2.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | retainedBytes | 12112.000 | 12112.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | transientBytes | 43699.000 | 43699.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | elapsedUs | 713.250 | 713.834 | +0.584 us/row (+0.08%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | transientBytes | 41703.000 | 41703.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | elapsedUs | 1080.375 | 1090.209 | +9.834 us/row (+0.91%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | retainedBytes | 15184.000 | 15184.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | transientBytes | 51483.000 | 51483.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | elapsedUs | 706.583 | 710.500 | +3.917 us/row (+0.55%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | transientBytes | 44272.000 | 44272.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | elapsedUs | 1080.334 | 1073.791 | -6.543 us/row (-0.61%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | retainedBytes | 15184.000 | 15184.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | transientBytes | 54052.000 | 54052.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | elapsedUs | 816.500 | 820.500 | +4.000 us/row (+0.49%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | transientBytes | 46426.000 | 46426.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | elapsedUs | 1144.166 | 1177.541 | +33.375 us/row (+2.92%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | retainedBytes | 26704.000 | 26704.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | transientBytes | 67370.000 | 67370.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | elapsedUs | 809.333 | 812.250 | +2.917 us/row (+0.36%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | retainedBytes | 5760.000 | 5760.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | transientBytes | 49571.000 | 49571.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | elapsedUs | 1144.875 | 1184.208 | +39.333 us/row (+3.44%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | retainedBytes | 26704.000 | 26704.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | transientBytes | 70515.000 | 70515.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 134.584 | 134.167 | -0.417 us/row (-0.31%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 1872.000 | 1872.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 7805.000 | 7797.000 | -8.000 B/row (-0.10%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 127.083 | 124.250 | -2.833 us/row (-2.23%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 1904.000 | 1904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 8817.000 | 8793.000 | -24.000 B/row (-0.27%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 151.625 | 149.666 | -1.959 us/row (-1.29%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 1872.000 | 1872.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 8713.000 | 8705.000 | -8.000 B/row (-0.09%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 136.458 | 142.833 | +6.375 us/row (+4.67%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 1904.000 | 1904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 9725.000 | 9701.000 | -24.000 B/row (-0.25%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.applyPatches | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.detachJsonContainer | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedMany | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.occurrenceShape | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.columns.wire | elapsedUs | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.columns.wire | retainedBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.columns.wire | transientBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.applyPatches | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.detachJsonContainer | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedMany | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.occurrenceShape | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.document.wire | elapsedUs | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.document.wire | retainedBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-patch.document.wire | transientBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.applyPatches | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.detachJsonContainer | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedMany | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.occurrenceShape | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.typed | elapsedUs | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.typed | retainedBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.typed | transientBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.applyPatches | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.detachJsonContainer | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedMany | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.occurrenceShape | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.wire | elapsedUs | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.wire | retainedBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.columns.wire | transientBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.applyPatches | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.detachJsonContainer | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedMany | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.occurrenceShape | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.typed | elapsedUs | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.typed | retainedBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.typed | transientBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.applyPatches | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.detachJsonContainer | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedMany | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.occurrenceShape | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.wire | elapsedUs | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.wire | retainedBytes | | | | | missing on head |
| 3.14 | keyed-write | plain.target-replace.document.wire | transientBytes | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 195.292 | 196.125 | +0.833 us/row (+0.43%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 1592.000 | 1584.000 | -8.000 B/row (-0.50%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 11066.000 | 11058.000 | -8.000 B/row (-0.07%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 187.250 | 187.041 | -0.209 us/row (-0.11%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 1624.000 | 1616.000 | -8.000 B/row (-0.49%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 11818.000 | 11794.000 | -24.000 B/row (-0.20%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 202.708 | 207.125 | +4.417 us/row (+2.18%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 1592.000 | 1584.000 | -8.000 B/row (-0.50%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 12132.000 | 12124.000 | -8.000 B/row (-0.07%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 194.625 | 206.250 | +11.625 us/row (+5.97%) | 9 | slower |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 1624.000 | 1616.000 | -8.000 B/row (-0.49%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 12708.000 | 12684.000 | -24.000 B/row (-0.19%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 135.000 | 138.167 | +3.167 us/row (+2.35%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1784.000 | 1784.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 10587.000 | 10587.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 136.083 | 144.833 | +8.750 us/row (+6.43%) | 9 | slower |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1992.000 | 1992.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 11035.000 | 11035.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 145.250 | 134.958 | -10.292 us/row (-7.09%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 1784.000 | 1784.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 10342.000 | 10342.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 138.625 | 138.500 | -0.125 us/row (-0.09%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 1992.000 | 1992.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 10766.000 | 10766.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | elapsedUs | 343.625 | 336.167 | -7.458 us/row (-2.17%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | retainedBytes | 2056.000 | 2056.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | transientBytes | 18325.000 | 18373.000 | +48.000 B/row (+0.26%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | elapsedUs | 345.042 | 360.583 | +15.541 us/row (+4.50%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-patch.document.wire | retainedBytes | 2056.000 | 2056.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-patch.document.wire | transientBytes | 18814.000 | 18862.000 | +48.000 B/row (+0.26%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | elapsedUs | 348.583 | 353.542 | +4.959 us/row (+1.42%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | transientBytes | 18297.000 | 18345.000 | +48.000 B/row (+0.26%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | elapsedUs | 334.833 | 337.667 | +2.834 us/row (+0.85%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | retainedBytes | 2056.000 | 2056.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | transientBytes | 18325.000 | 18373.000 | +48.000 B/row (+0.26%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | elapsedUs | 366.792 | 370.084 | +3.292 us/row (+0.90%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.typed | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.typed | transientBytes | 18786.000 | 18834.000 | +48.000 B/row (+0.26%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | elapsedUs | 343.250 | 349.417 | +6.167 us/row (+1.80%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.wire | retainedBytes | 2056.000 | 2056.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.wire | transientBytes | 18814.000 | 18862.000 | +48.000 B/row (+0.26%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 34.125 | 37.041 | +2.916 us/row (+8.55%) | 9 | slower |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 4010.000 | 4010.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 27.750 | 31.084 | +3.334 us/row (+12.01%) | 9 | slower |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 3742.000 | 3646.000 | -96.000 B/row (-2.57%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 34.167 | 36.834 | +2.667 us/row (+7.81%) | 9 | slower |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 4012.000 | 4012.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 28.333 | 31.833 | +3.500 us/row (+12.35%) | 9 | slower |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 3745.000 | 3649.000 | -96.000 B/row (-2.56%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3005.750 | 3076.917 | +71.167 us (+2.37%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared | retainedBytes | 439024.000 | 448988.000 | +9964.000 B (+2.27%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 445848.000 | 455812.000 | +9964.000 B (+2.23%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | 295.583 | 295.250 | -0.333 us (-0.11%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | 24504.000 | 24910.000 | +406.000 B (+1.66%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared.family | transientBytes | 28648.000 | 29054.000 | +406.000 B (+1.42%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 17.707 | 17.566 | -0.141 us/row (-0.80%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 989.156 | 999.508 | +10.352 B/row (+1.05%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 1872.203 | 1873.516 | +1.312 B/row (+0.07%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 18.230 | 18.302 | +0.072 us/row (+0.40%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1990.781 | 2001.133 | +10.352 B/row (+0.52%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2317.531 | 2318.906 | +1.375 B/row (+0.06%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 21.729 | 23.445 | +1.716 us/row (+7.90%) | 9 | slower |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1149.625 | 1191.031 | +41.406 B/row (+3.60%) | 1 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2360.000 | 2361.500 | +1.500 B/row (+0.06%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 22.277 | 22.370 | +0.092 us/row (+0.41%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2156.125 | 2197.531 | +41.406 B/row (+1.92%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 2705.500 | 2711.000 | +5.500 B/row (+0.20%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 37.911 | 38.333 | +0.422 us/row (+1.11%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1799.500 | 1965.125 | +165.625 B/row (+9.20%) | 1 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 3918.000 | 3924.000 | +6.000 B/row (+0.15%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 39.984 | 38.823 | -1.161 us/row (-2.90%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2825.500 | 2991.125 | +165.625 B/row (+5.86%) | 1 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 4170.000 | 4192.000 | +22.000 B/row (+0.53%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | elapsedUs | 99.927 | 101.922 | +1.995 us/row (+2.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | retainedBytes | 3223.500 | 3389.125 | +165.625 B/row (+5.14%) | 1 | larger |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | transientBytes | 16310.000 | 16362.000 | +52.000 B/row (+0.32%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | elapsedUs | 102.510 | 102.292 | -0.219 us/row (-0.21%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | retainedBytes | 16699.500 | 16865.125 | +165.625 B/row (+0.99%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | transientBytes | 18017.000 | 18039.000 | +22.000 B/row (+0.12%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | elapsedUs | 286.938 | 285.281 | -1.656 us/row (-0.58%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | retainedBytes | 13023.500 | 13189.125 | +165.625 B/row (+1.27%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | transientBytes | 32027.125 | 32079.125 | +52.000 B/row (+0.16%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | elapsedUs | 288.010 | 287.661 | -0.349 us/row (-0.12%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | retainedBytes | 40515.500 | 40681.125 | +165.625 B/row (+0.41%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | transientBytes | 41966.125 | 41988.125 | +22.000 B/row (+0.05%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | elapsedUs | 334.240 | 340.698 | +6.458 us/row (+1.93%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | retainedBytes | 9623.500 | 9789.125 | +165.625 B/row (+1.72%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | transientBytes | 27278.000 | 27330.000 | +52.000 B/row (+0.19%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | elapsedUs | 335.177 | 335.958 | +0.781 us/row (+0.23%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | retainedBytes | 32891.500 | 33057.125 | +165.625 B/row (+0.50%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | transientBytes | 34361.000 | 34383.000 | +22.000 B/row (+0.06%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | elapsedUs | 650.281 | 646.719 | -3.562 us/row (-0.55%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | retainedBytes | 27223.500 | 27389.125 | +165.625 B/row (+0.61%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | transientBytes | 32109.000 | 32145.000 | +36.000 B/row (+0.11%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | elapsedUs | 647.266 | 651.781 | +4.516 us/row (+0.70%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | retainedBytes | 50875.500 | 51041.125 | +165.625 B/row (+0.33%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | transientBytes | 52530.750 | 52536.750 | +6.000 B/row (+0.01%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | elapsedUs | 534.203 | 537.375 | +3.172 us/row (+0.59%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | retainedBytes | 8023.500 | 8189.125 | +165.625 B/row (+2.06%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | transientBytes | 21716.000 | 21768.000 | +52.000 B/row (+0.24%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | elapsedUs | 534.734 | 536.443 | +1.708 us/row (+0.32%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | retainedBytes | 26107.500 | 26273.125 | +165.625 B/row (+0.63%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | transientBytes | 27455.000 | 27477.000 | +22.000 B/row (+0.08%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | elapsedUs | 230.786 | 234.177 | +3.391 us/row (+1.47%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | retainedBytes | 7831.500 | 7997.125 | +165.625 B/row (+2.11%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | transientBytes | 20939.000 | 20991.000 | +52.000 B/row (+0.25%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | elapsedUs | 228.875 | 227.349 | -1.526 us/row (-0.67%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | retainedBytes | 21307.500 | 21473.125 | +165.625 B/row (+0.78%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | transientBytes | 22646.000 | 22668.000 | +22.000 B/row (+0.10%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | elapsedUs | 145.036 | 145.776 | +0.740 us/row (+0.51%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | retainedBytes | 9623.000 | 9788.625 | +165.625 B/row (+1.72%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | transientBytes | 22719.500 | 22771.500 | +52.000 B/row (+0.23%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | elapsedUs | 142.656 | 144.026 | +1.370 us/row (+0.96%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | retainedBytes | 23099.000 | 23264.625 | +165.625 B/row (+0.72%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | transientBytes | 24426.500 | 24448.500 | +22.000 B/row (+0.09%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | elapsedUs | 153.552 | 151.583 | -1.969 us/row (-1.28%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | retainedBytes | 10007.500 | 10173.125 | +165.625 B/row (+1.66%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | transientBytes | 23108.500 | 23160.500 | +52.000 B/row (+0.23%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | elapsedUs | 149.427 | 150.573 | +1.146 us/row (+0.77%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | retainedBytes | 23483.500 | 23649.125 | +165.625 B/row (+0.71%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | transientBytes | 24815.500 | 24837.500 | +22.000 B/row (+0.09%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | elapsedUs | 132.870 | 131.375 | -1.495 us/row (-1.12%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | retainedBytes | 13399.500 | 13565.125 | +165.625 B/row (+1.24%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | transientBytes | 26485.750 | 26537.750 | +52.000 B/row (+0.20%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | elapsedUs | 133.359 | 131.708 | -1.651 us/row (-1.24%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | retainedBytes | 26875.500 | 27041.125 | +165.625 B/row (+0.62%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | transientBytes | 28192.750 | 28214.750 | +22.000 B/row (+0.08%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | elapsedUs | 420.453 | 421.750 | +1.297 us/row (+0.31%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | retainedBytes | 9623.500 | 9789.125 | +165.625 B/row (+1.72%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | transientBytes | 28246.000 | 28298.000 | +52.000 B/row (+0.18%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | elapsedUs | 432.594 | 425.516 | -7.078 us/row (-1.64%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | retainedBytes | 33851.500 | 34017.125 | +165.625 B/row (+0.49%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | transientBytes | 35329.000 | 35351.000 | +22.000 B/row (+0.06%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | elapsedUs | 615.943 | 621.297 | +5.354 us/row (+0.87%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | retainedBytes | 12823.500 | 12989.125 | +165.625 B/row (+1.29%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | transientBytes | 31095.750 | 31132.750 | +37.000 B/row (+0.12%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | elapsedUs | 626.625 | 625.463 | -1.162 us/row (-0.19%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | retainedBytes | 39355.500 | 39521.125 | +165.625 B/row (+0.42%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | transientBytes | 40851.750 | 40873.750 | +22.000 B/row (+0.05%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | elapsedUs | 377.214 | 382.693 | +5.479 us/row (+1.45%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | retainedBytes | 24818.000 | 24983.625 | +165.625 B/row (+0.67%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | transientBytes | 34671.500 | 34723.500 | +52.000 B/row (+0.15%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | elapsedUs | 378.057 | 382.854 | +4.797 us/row (+1.27%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | retainedBytes | 53078.000 | 53243.625 | +165.625 B/row (+0.31%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | transientBytes | 54522.500 | 54544.500 | +22.000 B/row (+0.04%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.columns | elapsedUs | 121.750 | 128.439 | +6.689 us/row (+5.49%) | 9 | slower |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.columns | retainedBytes | 1630.730 | 1636.688 | +5.957 B/row (+0.37%) | 1 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.columns | transientBytes | 1828.242 | 1828.438 | +0.195 B/row (+0.01%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.document | elapsedUs | 114.083 | 115.961 | +1.877 us/row (+1.65%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.document | retainedBytes | 1835.742 | 1842.090 | +6.348 B/row (+0.35%) | 1 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.document | transientBytes | 2432.805 | 2433.305 | +0.500 B/row (+0.02%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.unchanged.objects-128.document | elapsedUs | 45.966 | 46.208 | +0.242 us/row (+0.53%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.unchanged.objects-128.document | retainedBytes | 158.828 | 164.004 | +5.176 B/row (+3.26%) | 1 | larger |
| 3.14 | predicate-flush | predicate-flush.unchanged.objects-128.document | transientBytes | 1402.594 | 1403.094 | +0.500 B/row (+0.04%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.wide.history-128.document | elapsedUs | 66.522 | 66.157 | -0.365 us/row (-0.55%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.wide.history-128.document | retainedBytes | 1357.101 | 1367.760 | +10.659 B/row (+0.79%) | 1 | within noise |
| 3.14 | predicate-flush | predicate-flush.wide.history-128.document | transientBytes | 6475.078 | 6474.302 | -0.775 B/row (-0.01%) | 9 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | elapsedUs | 61.958 | 65.167 | +3.209 us/row (+5.18%) | 9 | slower |
| 3.14 | wire-insert-response | response.insert.family.wire | retainedBytes | 9364.000 | 10713.000 | +1349.000 B/row (+14.41%) | 1 | larger |
| 3.14 | wire-insert-response | response.insert.family.wire | transientBytes | 8774.000 | 8774.000 | +0.000 B/row (+0.00%) | 9 | within noise |

Deltas are advisory and never ratchet the Budget Contract.
