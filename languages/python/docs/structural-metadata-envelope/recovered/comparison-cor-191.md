# Python cost report comparison

Timing deltas within 5% and byte deltas within 3% are read as noise; count deltas are exact. A cell present on one side alone, or whose unit differs, is not compared.

- The base capture is amended: 364 re-measured readings changed after the run its provenance names, recorded in the adjustment of conditions.json.

## feature-boundary

The feature-boundary envelope is unavailable on one side.

## instance-state

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| - | - | cpython-3.13 | aggregate.bare.after | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.before | 6384.000 | 6384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.reduction | 0.617 | 0.617 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.before | 7200.000 | 7200.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.reduction | 0.547 | 0.547 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.340 | 3.409 | +0.069 ratio (+2.06%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.340 | 3.409 | +0.069 ratio (+2.06%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.313 | 3.427 | +0.114 ratio (+3.44%) | 0 | larger |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 0.522 | 0.507 | -0.014 ratio (-2.76%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.likeForLike | 0.500 | 0.487 | -0.013 ratio (-2.66%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 1.549 | 1.554 | +0.005 ratio (+0.29%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.184 | 2.191 | +0.007 ratio (+0.34%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.184 | 2.191 | +0.007 ratio (+0.34%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.209 | 2.214 | +0.004 ratio (+0.19%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 1471.432 | 1410.723 | -60.709 ns (-4.13%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 6919.735 | 7011.965 | +92.229 ns (+1.33%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.directWireNs | 10597.250 | 11085.645 | +488.395 ns (+4.61%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.dumpNs | 5770.104 | 6097.709 | +327.605 ns (+5.68%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 4770.000 | 4770.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionNs | 14270.875 | 14932.812 | +661.937 ns (+4.64%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | 7560.000 | 7776.000 | +216.000 B (+2.86%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | 1240.000 | 1240.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | 12258.998 | 12500.438 | +241.440 ns (+1.97%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | 6320.000 | 6536.000 | +216.000 B (+3.42%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.readNs | 83.312 | 86.679 | +3.367 ns (+4.04%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 425.885 | 535.942 | +110.057 ns (+25.84%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.transientBytes | 3706.000 | 3706.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 425.885 | 535.942 | +110.057 ns (+25.84%) | 0 | larger |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | 105.925 | 96.925 | -9.000 ns (-8.50%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 10317.575 | 10448.825 | +131.250 ns (+1.27%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2373.458 | 2521.063 | +147.604 ns (+6.22%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 4960.000 | 4960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.readNs | 25.200 | 25.350 | +0.150 ns (+0.60%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2168.000 | 2168.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 417.600 | 502.717 | +85.116 ns (+20.38%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 6057.817 | 6085.971 | +28.154 ns (+0.46%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2379.062 | 2508.375 | +129.313 ns (+5.44%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 26.533 | 25.067 | -1.467 ns (-5.53%) | 0 | smaller |
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
| - | - | cpython-3.13/nullable | compact.callNs | 1309.339 | 1396.802 | +87.463 ns (+6.68%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 2307.494 | 2331.510 | +24.017 ns (+1.04%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.directWireNs | 5579.396 | 5975.146 | +395.750 ns (+7.09%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1830.562 | 1813.042 | -17.521 ns (-0.96%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionNs | 7539.375 | 7988.229 | +448.854 ns (+5.95%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | 2504.000 | 2624.000 | +120.000 B (+4.79%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | 6016.996 | 6315.694 | +298.698 ns (+4.96%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | 2032.000 | 2152.000 | +120.000 B (+5.91%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.readNs | 74.656 | 74.375 | -0.281 ns (-0.38%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 233.641 | 200.953 | -32.688 ns (-13.99%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 233.641 | 200.953 | -32.688 ns (-13.99%) | 0 | smaller |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 265.614 | 301.983 | +36.369 ns (+13.69%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5215.677 | 5533.454 | +317.777 ns (+6.09%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 855.125 | 913.229 | +58.104 ns (+6.79%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 22.127 | 23.212 | +1.085 ns (+4.91%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 165.896 | 204.381 | +38.486 ns (+23.20%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1191.208 | 1209.931 | +18.723 ns (+1.57%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 860.687 | 852.625 | -8.062 ns (-0.94%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 22.060 | 22.242 | +0.181 ns (+0.82%) | 0 | within noise |
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
| - | - | cpython-3.13/partial | compact.callNs | 1358.350 | 1317.304 | -41.046 ns (-3.02%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 2144.337 | 2151.987 | +7.650 ns (+0.36%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.directWireNs | 4991.438 | 5437.667 | +446.229 ns (+8.94%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.dumpNs | 1857.750 | 1847.688 | -10.062 ns (-0.54%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 3432.000 | 3432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionNs | 6969.125 | 7397.417 | +428.292 ns (+6.15%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | 2416.000 | 2536.000 | +120.000 B (+4.97%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | 5394.842 | 5497.235 | +102.394 ns (+1.90%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | 2032.000 | 2152.000 | +120.000 B (+5.91%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.readNs | 74.935 | 75.960 | +1.025 ns (+1.37%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 218.860 | 173.646 | -45.214 ns (-20.66%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 218.860 | 173.646 | -45.214 ns (-20.66%) | 0 | smaller |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 187.077 | 127.858 | -59.219 ns (-31.65%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 4991.819 | 5183.433 | +191.615 ns (+3.84%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.dumpNs | 891.167 | 869.604 | -21.563 ns (-2.42%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 24.321 | 22.721 | -1.600 ns (-6.58%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 191.492 | 210.785 | +19.294 ns (+10.08%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 945.946 | 933.715 | -12.231 ns (-1.29%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 868.479 | 907.145 | +38.666 ns (+4.45%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 22.933 | 22.556 | -0.377 ns (-1.64%) | 0 | within noise |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 1346.071 | 1355.612 | +9.542 ns (+0.71%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 2218.367 | 2190.137 | -28.229 ns (-1.27%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | 5783.750 | 5987.979 | +204.229 ns (+3.53%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1588.438 | 1679.479 | +91.042 ns (+5.73%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 3408.000 | 3408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | 7628.708 | 8023.250 | +394.542 ns (+5.17%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | 2776.000 | 2896.000 | +120.000 B (+4.32%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | 5820.625 | 6001.806 | +181.181 ns (+3.11%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | 2304.000 | 2424.000 | +120.000 B (+5.21%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.readNs | 80.107 | 78.479 | -1.628 ns (-2.03%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 234.066 | 209.193 | -24.873 ns (-10.63%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 234.066 | 209.193 | -24.873 ns (-10.63%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 138.725 | 167.016 | +28.291 ns (+20.39%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4085.067 | 4179.817 | +94.750 ns (+2.32%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 786.792 | 793.584 | +6.792 ns (+0.86%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 23.863 | 23.777 | -0.086 ns (-0.36%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 196.121 | 227.492 | +31.371 ns (+16.00%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1057.004 | 1038.342 | -18.663 ns (-1.77%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 774.416 | 774.875 | +0.458 ns (+0.06%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 24.283 | 23.390 | -0.893 ns (-3.68%) | 0 | smaller |
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
| - | - | cpython-3.13/shallow | compact.callNs | 1392.777 | 1333.829 | -58.948 ns (-4.23%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 2077.452 | 2043.483 | -33.969 ns (-1.64%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.directWireNs | 7265.021 | 7259.500 | -5.521 ns (-0.08%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1399.542 | 1413.125 | +13.584 ns (+0.97%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 3384.000 | 3384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionNs | 8747.937 | 9173.458 | +425.520 ns (+4.86%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | 3358.000 | 3414.000 | +56.000 B (+1.67%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | 430.000 | 430.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | 5370.629 | 5487.448 | +116.819 ns (+2.18%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | 2928.000 | 2984.000 | +56.000 B (+1.91%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.readNs | 88.635 | 88.286 | -0.349 ns (-0.39%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 209.616 | 195.927 | -13.689 ns (-6.53%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 209.616 | 195.927 | -13.689 ns (-6.53%) | 0 | smaller |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 147.133 | 165.016 | +17.883 ns (+12.15%) | 0 | larger |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2716.804 | 2763.192 | +46.388 ns (+1.71%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 715.209 | 710.375 | -4.834 ns (-0.68%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 25.276 | 25.328 | +0.052 ns (+0.21%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 214.562 | 208.808 | -5.754 ns (-2.68%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 785.979 | 790.692 | +4.712 ns (+0.60%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 718.188 | 726.854 | +8.667 ns (+1.21%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 26.338 | 26.464 | +0.125 ns (+0.48%) | 0 | within noise |
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
| - | - | cpython-3.13/warmed | compact.callNs | 1586.575 | 1671.787 | +85.212 ns (+5.37%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 4130.592 | 4069.796 | -60.796 ns (-1.47%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1737.125 | 1706.167 | -30.958 ns (-1.78%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 3384.000 | 3384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.readNs | 87.688 | 91.458 | +3.771 ns (+4.30%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 240.703 | 204.991 | -35.712 ns (-14.84%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.transientBytes | 2578.000 | 2578.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 240.703 | 204.991 | -35.712 ns (-14.84%) | 0 | smaller |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 153.585 | 86.840 | -66.746 ns (-43.46%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 3772.644 | 3875.160 | +102.517 ns (+2.72%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 707.937 | 722.750 | +14.813 ns (+2.09%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 25.859 | 26.641 | +0.781 ns (+3.02%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 169.441 | 215.877 | +46.436 ns (+27.41%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1701.954 | 1734.748 | +32.794 ns (+1.93%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 704.771 | 703.813 | -0.958 ns (-0.14%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 26.630 | 26.005 | -0.625 ns (-2.35%) | 0 | within noise |
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
| - | - | cpython-3.13/wide | compact.callNs | 1364.521 | 1422.117 | +57.596 ns (+4.22%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 2637.167 | 2603.821 | -33.346 ns (-1.26%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.directWireNs | 6880.459 | 7135.791 | +255.333 ns (+3.71%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.dumpNs | 2417.041 | 2478.062 | +61.021 ns (+2.52%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 3512.000 | 3512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionNs | 9253.855 | 10080.583 | +826.729 ns (+8.93%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | 3240.000 | 3360.000 | +120.000 B (+3.70%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | 664.000 | 664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | 7309.587 | 7613.271 | +303.683 ns (+4.15%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | 2576.000 | 2696.000 | +120.000 B (+4.66%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.readNs | 82.273 | 78.932 | -3.341 ns (-4.06%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 196.700 | 206.955 | +10.256 ns (+5.21%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 196.700 | 206.955 | +10.256 ns (+5.21%) | 0 | larger |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 30.806 | 345.452 | +314.646 ns (+1021.38%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 7771.485 | 8043.423 | +271.937 ns (+3.50%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1184.459 | 1188.021 | +3.562 ns (+0.30%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 24.100 | 21.224 | -2.876 ns (-11.93%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 219.250 | 233.750 | +14.500 ns (+6.61%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1775.417 | 1738.271 | -37.146 ns (-2.09%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1126.312 | 1155.209 | +28.896 ns (+2.57%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 23.921 | 21.143 | -2.777 ns (-11.61%) | 0 | smaller |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.320 | 3.126 | -0.194 ratio (-5.84%) | 0 | smaller |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.320 | 3.126 | -0.194 ratio (-5.84%) | 0 | smaller |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.284 | 3.021 | -0.263 ratio (-8.00%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 0.508 | 0.520 | +0.012 ratio (+2.28%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.likeForLike | 0.488 | 0.499 | +0.011 ratio (+2.27%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 1.473 | 1.483 | +0.010 ratio (+0.67%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.151 | 2.124 | -0.027 ratio (-1.24%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.151 | 2.124 | -0.027 ratio (-1.24%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.186 | 2.147 | -0.040 ratio (-1.81%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 1597.398 | 1468.871 | -128.527 ns (-8.05%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 6653.790 | 5910.171 | -743.619 ns (-11.18%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.directWireNs | 11388.479 | 10302.500 | -1085.979 ns (-9.54%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.dumpNs | 6027.395 | 5495.396 | -532.000 ns (-8.83%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 5034.000 | 5034.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionNs | 15389.229 | 13822.146 | -1567.083 ns (-10.18%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | 8450.000 | 8674.000 | +224.000 B (+2.65%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | 1248.000 | 1248.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | 13335.406 | 11937.692 | -1397.715 ns (-10.48%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | 7202.000 | 7426.000 | +224.000 B (+3.11%) | 0 | larger |
| - | - | cpython-3.14/nested | compact.readNs | 85.679 | 77.979 | -7.700 ns (-8.99%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 317.822 | 247.412 | -70.410 ns (-22.15%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 3802.000 | 3802.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 317.822 | 247.412 | -70.410 ns (-22.15%) | 0 | smaller |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 97.054 | 26.427 | -70.627 ns (-72.77%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 10885.092 | 9416.740 | -1468.352 ns (-13.49%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 2543.729 | 2403.354 | -140.375 ns (-5.52%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5184.000 | 5184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.readNs | 26.342 | 25.242 | -1.100 ns (-4.18%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2264.000 | 2264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 238.071 | 216.900 | -21.171 ns (-8.89%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 6299.804 | 5636.683 | -663.121 ns (-10.53%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 2465.104 | 2394.604 | -70.500 ns (-2.86%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4744.000 | 4744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 25.688 | 25.071 | -0.617 ns (-2.40%) | 0 | within noise |
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
| - | - | cpython-3.14/nullable | compact.callNs | 1387.052 | 1351.073 | -35.980 ns (-2.59%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 2320.427 | 2023.802 | -296.625 ns (-12.78%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.directWireNs | 5765.604 | 5302.729 | -462.875 ns (-8.03%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.dumpNs | 1813.438 | 1630.646 | -182.792 ns (-10.08%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 3672.000 | 3672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionNs | 8073.063 | 7344.813 | -728.250 ns (-9.02%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | 2736.000 | 2864.000 | +128.000 B (+4.68%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | 480.000 | 480.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | 6529.865 | 5750.821 | -779.044 ns (-11.93%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | 2256.000 | 2384.000 | +128.000 B (+5.67%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.readNs | 78.273 | 69.081 | -9.192 ns (-11.74%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 233.380 | 159.800 | -73.580 ns (-31.53%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 233.380 | 159.800 | -73.580 ns (-31.53%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 136.987 | 163.588 | +26.600 ns (+19.42%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 5262.117 | 4512.037 | -750.079 ns (-14.25%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 888.250 | 811.146 | -77.104 ns (-8.68%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 24.467 | 21.065 | -3.402 ns (-13.90%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 198.346 | 185.135 | -13.211 ns (-6.66%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1237.029 | 1058.781 | -178.248 ns (-14.41%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 897.979 | 789.417 | -108.562 ns (-12.09%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 24.223 | 22.044 | -2.179 ns (-9.00%) | 0 | smaller |
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
| - | - | cpython-3.14/partial | compact.callNs | 1426.656 | 1366.290 | -60.366 ns (-4.23%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 2156.552 | 1944.565 | -211.988 ns (-9.83%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.directWireNs | 5136.313 | 4868.708 | -267.604 ns (-5.21%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.dumpNs | 1857.896 | 1653.771 | -204.125 ns (-10.99%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 3576.000 | 3576.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionNs | 7203.854 | 6512.958 | -690.896 ns (-9.59%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | 2616.000 | 2744.000 | +128.000 B (+4.89%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | 392.000 | 392.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | 5734.333 | 5148.663 | -585.671 ns (-10.21%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | 2224.000 | 2352.000 | +128.000 B (+5.76%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.readNs | 79.108 | 68.660 | -10.448 ns (-13.21%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 214.278 | 194.108 | -20.170 ns (-9.41%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 214.278 | 194.108 | -20.170 ns (-9.41%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 181.619 | 212.635 | +31.017 ns (+17.08%) | 0 | larger |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 4941.298 | 4319.135 | -622.163 ns (-12.59%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 901.000 | 797.208 | -103.792 ns (-11.52%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 22.660 | 22.775 | +0.115 ns (+0.51%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 230.394 | 189.004 | -41.390 ns (-17.96%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 1001.648 | 862.725 | -138.923 ns (-13.87%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 899.250 | 793.875 | -105.375 ns (-11.72%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 24.969 | 26.887 | +1.919 ns (+7.68%) | 0 | larger |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 1421.756 | 1235.654 | -186.102 ns (-13.09%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 2213.744 | 1969.346 | -244.398 ns (-11.04%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | 5840.730 | 5333.458 | -507.271 ns (-8.69%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1695.812 | 1510.292 | -185.521 ns (-10.94%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 3552.000 | 3552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | 8177.750 | 7020.312 | -1157.438 ns (-14.15%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | 2984.000 | 3112.000 | +128.000 B (+4.29%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | 480.000 | 480.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | 6253.440 | 5488.313 | -765.127 ns (-12.24%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | 2504.000 | 2632.000 | +128.000 B (+5.11%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.readNs | 86.920 | 71.958 | -14.961 ns (-17.21%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 219.298 | 216.673 | -2.625 ns (-1.20%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 219.298 | 216.673 | -2.625 ns (-1.20%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 208.482 | 232.298 | +23.816 ns (+11.42%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4029.248 | 3539.848 | -489.400 ns (-12.15%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 824.750 | 730.417 | -94.333 ns (-11.44%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 27.179 | 25.461 | -1.717 ns (-6.32%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 197.971 | 170.596 | -27.375 ns (-13.83%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1119.071 | 1002.362 | -116.708 ns (-10.43%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 826.666 | 721.813 | -104.854 ns (-12.68%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 26.559 | 26.170 | -0.390 ns (-1.47%) | 0 | within noise |
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
| - | - | cpython-3.14/shallow | compact.callNs | 1442.716 | 1273.392 | -169.324 ns (-11.74%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 2091.679 | 1868.462 | -223.217 ns (-10.67%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.directWireNs | 7253.563 | 6603.791 | -649.771 ns (-8.96%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1402.125 | 1262.792 | -139.333 ns (-9.94%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 3528.000 | 3528.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionNs | 9067.604 | 8118.708 | -948.896 ns (-10.46%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | 3662.000 | 3718.000 | +56.000 B (+1.53%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | 438.000 | 438.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | 5764.892 | 5077.021 | -687.871 ns (-11.93%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | 3224.000 | 3280.000 | +56.000 B (+1.74%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.readNs | 88.974 | 81.974 | -7.000 ns (-7.87%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 217.524 | 196.959 | -20.564 ns (-9.45%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 217.524 | 196.959 | -20.564 ns (-9.45%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 203.252 | 235.032 | +31.780 ns (+15.64%) | 0 | larger |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 2762.873 | 2381.885 | -380.988 ns (-13.79%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 731.792 | 673.792 | -58.000 ns (-7.93%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 27.057 | 25.979 | -1.078 ns (-3.98%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 208.529 | 191.004 | -17.525 ns (-8.40%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 819.763 | 735.413 | -84.350 ns (-10.29%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 719.104 | 661.063 | -58.041 ns (-8.07%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 27.661 | 24.990 | -2.672 ns (-9.66%) | 0 | smaller |
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
| - | - | cpython-3.14/warmed | compact.callNs | 1519.006 | 1539.671 | +20.664 ns (+1.36%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 4263.015 | 3775.954 | -487.060 ns (-11.43%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1785.625 | 1563.000 | -222.625 ns (-12.47%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 3528.000 | 3528.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.readNs | 88.958 | 79.734 | -9.224 ns (-10.37%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 268.272 | 194.362 | -73.911 ns (-27.55%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.transientBytes | 2690.000 | 2690.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 268.272 | 194.362 | -73.911 ns (-27.55%) | 0 | smaller |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 132.360 | 110.521 | -21.840 ns (-16.50%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 3897.015 | 3511.792 | -385.223 ns (-9.89%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 751.042 | 669.730 | -81.312 ns (-10.83%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 28.438 | 25.375 | -3.062 ns (-10.77%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 205.705 | 191.004 | -14.701 ns (-7.15%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1755.837 | 1627.413 | -128.425 ns (-7.31%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 731.875 | 669.355 | -62.520 ns (-8.54%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 30.641 | 25.141 | -5.500 ns (-17.95%) | 0 | smaller |
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
| - | - | cpython-3.14/wide | compact.callNs | 1485.202 | 1309.342 | -175.860 ns (-11.84%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 2531.902 | 2280.512 | -251.390 ns (-9.93%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.directWireNs | 7024.791 | 6449.917 | -574.874 ns (-8.18%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.dumpNs | 2403.625 | 2165.958 | -237.667 ns (-9.89%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 3720.000 | 3720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionNs | 9818.000 | 8579.396 | -1238.604 ns (-12.62%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | 3488.000 | 3616.000 | +128.000 B (+3.67%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | 7855.685 | 6926.806 | -928.879 ns (-11.82%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | 2816.000 | 2944.000 | +128.000 B (+4.55%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.readNs | 82.836 | 76.122 | -6.714 ns (-8.10%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 219.275 | 225.760 | +6.485 ns (+2.96%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 219.275 | 225.760 | +6.485 ns (+2.96%) | 0 | within noise |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 220.702 | 357.871 | +137.169 ns (+62.15%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 7487.965 | 6615.900 | -872.065 ns (-11.65%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1177.687 | 1042.396 | -135.291 ns (-11.49%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 23.443 | 22.087 | -1.355 ns (-5.78%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 253.521 | 175.394 | -78.127 ns (-30.82%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 1719.229 | 1490.127 | -229.102 ns (-13.33%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1144.000 | 1029.625 | -114.375 ns (-10.00%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 23.717 | 22.402 | -1.315 ns (-5.54%) | 0 | smaller |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.263 | 3.123 | -0.140 us/event (-4.29%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 3.726 | 3.798 | +0.071 us/event (+1.92%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.271 | 0.264 | -0.007 ratio (-2.74%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.021 | 0.020 | -0.001 ratio (-4.17%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.068 | 0.066 | -0.003 ratio (-3.90%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.004 | 0.004 | -0.000 ratio (-4.26%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.170 | 0.164 | -0.006 ratio (-3.32%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | observed.p50 | 428.584 | 419.375 | -9.209 us (-2.15%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p95 | 445.500 | 444.000 | -1.500 us (-0.34%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 91.375 | 87.458 | -3.917 us (-4.29%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 104.334 | 106.333 | +1.999 us (+1.92%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.271 | 0.264 | -0.007 ratio (-2.52%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.309 | 0.320 | +0.011 ratio (+3.48%) | 0 | larger |
| - | - | Safe logging alone, at INFO | plain.p50 | 337.167 | 331.792 | -5.375 us (-1.59%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | plain.p95 | 350.958 | 351.834 | +0.876 us (+0.25%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.271 | 0.264 | -0.007 ratio (-2.64%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.269 | 0.262 | -0.007 ratio (-2.76%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.341 | 2.228 | -0.113 us/event (-4.83%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 2.832 | 2.905 | +0.073 us/event (+2.58%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.195 | 0.189 | -0.006 ratio (-3.15%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.015 | 0.014 | -0.001 ratio (-4.70%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.049 | 0.047 | -0.002 ratio (-4.41%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | -0.000 ratio (-4.80%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.122 | 0.118 | -0.005 ratio (-3.79%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | observed.p50 | 401.917 | 392.916 | -9.001 us (-2.24%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p95 | 420.750 | 416.834 | -3.916 us (-0.93%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 65.542 | 62.375 | -3.167 us (-4.83%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 79.291 | 81.333 | +2.042 us (+2.58%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.195 | 0.189 | -0.006 ratio (-3.16%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.235 | 0.245 | +0.010 ratio (+4.12%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | plain.p50 | 336.250 | 330.416 | -5.834 us (-1.74%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | plain.p95 | 350.958 | 350.667 | -0.291 us (-0.08%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.195 | 0.189 | -0.006 ratio (-3.14%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.199 | 0.189 | -0.010 ratio (-5.12%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 3.990 | 3.759 | -0.231 us/event (-5.78%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.973 | 4.436 | -0.537 us/event (-10.80%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.330 | 0.317 | -0.013 ratio (-3.95%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.026 | 0.024 | -0.001 ratio (-5.64%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.083 | 0.079 | -0.004 ratio (-5.32%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-5.75%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.207 | 0.198 | -0.010 ratio (-4.64%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | observed.p50 | 450.750 | 438.208 | -12.542 us (-2.78%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | observed.p95 | 479.333 | 464.875 | -14.458 us (-3.02%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 111.708 | 105.250 | -6.458 us (-5.78%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 139.250 | 124.209 | -15.041 us (-10.80%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.330 | 0.316 | -0.013 ratio (-4.06%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.406 | 0.370 | -0.036 ratio (-8.93%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | plain.p50 | 338.958 | 332.500 | -6.458 us (-1.91%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | plain.p95 | 352.375 | 353.750 | +1.375 us (+0.39%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.330 | 0.318 | -0.012 ratio (-3.61%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.360 | 0.314 | -0.046 ratio (-12.81%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 3.807 | 3.624 | -0.183 us/event (-4.81%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 4.613 | 4.362 | -0.251 us/event (-5.45%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.314 | 0.305 | -0.009 ratio (-2.92%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.025 | 0.023 | -0.001 ratio (-4.66%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.080 | 0.076 | -0.003 ratio (-4.34%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-4.78%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.198 | 0.191 | -0.007 ratio (-3.63%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 445.584 | 433.792 | -11.792 us (-2.65%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 473.917 | 462.000 | -11.917 us (-2.51%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 106.583 | 101.459 | -5.124 us (-4.81%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 129.166 | 122.125 | -7.041 us (-5.45%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.315 | 0.305 | -0.010 ratio (-3.11%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.377 | 0.364 | -0.013 ratio (-3.47%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 339.042 | 332.458 | -6.584 us (-1.94%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 353.916 | 353.291 | -0.625 us (-0.18%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.314 | 0.305 | -0.009 ratio (-3.00%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.339 | 0.308 | -0.031 ratio (-9.25%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.435 | 1.406 | -0.028 us/event (-1.97%) | 0 | within noise |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 1.998 | 2.115 | +0.116 us/event (+5.81%) | 0 | larger |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.120 | 0.119 | -0.000 ratio (-0.09%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.009 | 0.009 | -0.000 ratio (-1.83%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.030 | 0.030 | -0.000 ratio (-1.50%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-1.94%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.075 | 0.074 | -0.001 ratio (-0.80%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p50 | 376.375 | 369.083 | -7.292 us (-1.94%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p95 | 396.459 | 397.000 | +0.541 us (+0.14%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 40.167 | 39.376 | -0.791 us (-1.97%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 55.958 | 59.209 | +3.251 us (+5.81%) | 0 | slower |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.120 | 0.120 | -0.000 ratio (-0.11%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.166 | 0.178 | +0.011 ratio (+6.73%) | 0 | larger |
| - | - | one Handler that keeps nothing | plain.p50 | 336.125 | 329.792 | -6.333 us (-1.88%) | 0 | within noise |
| - | - | one Handler that keeps nothing | plain.p95 | 355.125 | 352.917 | -2.208 us (-0.62%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.120 | 0.119 | -0.001 ratio (-0.51%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.116 | 0.125 | +0.009 ratio (+7.32%) | 0 | larger |
| - | - | workload | events | 28.000 | 28.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | workload | statements | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |

## snapshot-delivery

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 10118.791 | 9698.917 | -419.874 us (-4.15%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1450.010 | 1392.861 | -57.148 KiB (-3.94%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 693.328 | 693.328 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 100875.375 | 103783.333 | +2907.958 us (+2.88%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 12653.846 | 12652.338 | -1.508 KiB (-0.01%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 6931.836 | 6931.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 20897.416 | 16089.125 | -4808.291 us (-23.01%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 445.783 | 391.807 | -53.977 KiB (-12.11%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.458 | 3.458 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 117012.542 | 107103.833 | -9908.709 us (-8.47%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 822.721 | 775.244 | -47.477 KiB (-5.77%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.489 | 3.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8355.667 | 8075.041 | -280.626 us (-3.36%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1250.123 | 1192.139 | -57.984 KiB (-4.64%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 477.848 | 477.848 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 83704.458 | 80762.000 | -2942.458 us (-3.52%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11112.811 | 11110.373 | -2.438 KiB (-0.02%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4775.730 | 4775.730 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 19543.125 | 14978.000 | -4565.125 us (-23.36%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 392.021 | 332.436 | -59.586 KiB (-15.20%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.524 | 2.524 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 101946.125 | 94236.041 | -7710.084 us (-7.56%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 821.428 | 774.357 | -47.070 KiB (-5.73%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.556 | 2.556 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 18218.583 | 17812.959 | -405.624 us (-2.23%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1352.424 | 1298.314 | -54.109 KiB (-4.00%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 708.953 | 708.953 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 181144.667 | 178113.708 | -3030.959 us (-1.67%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12299.947 | 12084.102 | -215.846 KiB (-1.75%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7088.086 | 7088.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 28165.292 | 23765.541 | -4399.751 us (-15.62%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 568.674 | 507.689 | -60.984 KiB (-10.72%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.536 | 3.536 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 191903.042 | 182061.500 | -9841.542 us (-5.13%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 985.643 | 874.955 | -110.688 KiB (-11.23%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.567 | 3.567 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 16167.042 | 15864.833 | -302.209 us (-1.87%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1199.549 | 1208.674 | +9.125 KiB (+0.76%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 501.285 | 501.285 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 160817.625 | 158121.541 | -2696.084 us (-1.68%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12300.377 | 12084.531 | -215.846 KiB (-1.75%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5010.105 | 5010.105 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 26131.958 | 21930.041 | -4201.917 us (-16.08%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 533.678 | 474.014 | -59.664 KiB (-11.18%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.642 | 2.642 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 171902.042 | 163540.166 | -8361.876 us (-4.86%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 982.014 | 871.240 | -110.773 KiB (-11.28%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.673 | 2.673 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6047.917 | 5928.542 | -119.375 us (-1.97%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 476.559 | 456.371 | -20.188 KiB (-4.24%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 227.253 | 227.253 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 845.875 | 842.750 | -3.125 us (-0.37%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 72.854 | 69.370 | -3.484 KiB (-4.78%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 28.146 | 28.146 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4493.291 | 4431.584 | -61.707 us (-1.37%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 410.364 | 390.489 | -19.875 KiB (-4.84%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 186.823 | 186.823 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 671.333 | 657.125 | -14.208 us (-2.12%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 65.379 | 62.152 | -3.227 KiB (-4.94%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.200 | 23.200 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8757.458 | 8591.417 | -166.041 us (-1.90%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 606.505 | 580.786 | -25.719 KiB (-4.24%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 293.815 | 293.815 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1242.166 | 1193.917 | -48.249 us (-3.88%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 92.004 | 86.676 | -5.328 KiB (-5.79%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 36.802 | 36.802 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6888.417 | 6743.958 | -144.459 us (-2.10%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 550.426 | 524.941 | -25.484 KiB (-4.63%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 257.698 | 257.698 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 995.458 | 1001.208 | +5.750 us (+0.58%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 86.378 | 81.229 | -5.148 KiB (-5.96%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.388 | 32.388 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10797.917 | 10797.708 | -0.209 us (-0.00%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 765.693 | 725.670 | -40.023 KiB (-5.23%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 384.511 | 384.511 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1607.625 | 1485.500 | -122.125 us (-7.60%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 113.556 | 105.743 | -7.812 KiB (-6.88%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 48.544 | 48.544 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8466.167 | 8425.250 | -40.917 us (-0.48%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 703.224 | 664.742 | -38.481 KiB (-5.47%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 333.909 | 333.909 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1262.500 | 1236.042 | -26.458 us (-2.10%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 106.775 | 99.369 | -7.406 KiB (-6.94%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.247 | 42.247 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 434.381 | 420.996 | -13.385 KiB (-3.08%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 295.456 | 297.176 | +1.720 KiB (+0.58%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.557 | 0.404 | -0.152 ms (-27.33%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.810 | 0.644 | -0.165 ms (-20.40%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 5.037 | 4.702 | -0.335 ms (-6.66%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 39189.752 | 41835.166 | +2645.414 roots/s (+6.75%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 5.550 | 5.521 | -0.028 ms (-0.51%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 36620.533 | 39126.180 | +2505.647 roots/s (+6.84%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 8.106 | 7.383 | -0.723 ms (-8.92%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 25150.773 | 26522.121 | +1371.349 roots/s (+5.45%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 231.412 | 219.224 | -12.188 KiB (-5.27%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 45.315 | 44.738 | -0.577 KiB (-1.27%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 85.505 | 80.877 | -4.628 KiB (-5.41%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 10.883 | 10.950 | +0.067 KiB (+0.62%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1289.925 | 1232.261 | -57.664 KiB (-4.47%) | 3 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.973 | 521.973 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.728 | 0.669 | -0.060 ms (-8.20%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.043 | 1.095 | +0.052 ms (+4.98%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 8.686 | 8.562 | -0.124 ms (-1.43%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23203.202 | 23464.883 | +261.681 roots/s (+1.13%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 9.410 | 9.210 | -0.200 ms (-2.12%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 21264.154 | 21969.674 | +705.520 roots/s (+3.32%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 12.187 | 11.890 | -0.297 ms (-2.44%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 16571.096 | 16446.692 | -124.404 roots/s (-0.75%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 705.499 | 667.897 | -37.602 KiB (-5.33%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 31.946 | 29.220 | -2.727 KiB (-8.53%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 199.487 | 188.167 | -11.320 KiB (-5.67%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.491 | 5.002 | +1.511 KiB (+43.27%) | 6 | larger |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1717.600 | 1586.600 | -131.000 KiB (-7.63%) | 3 | smaller |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.690 | 869.645 | -0.046 KiB (-0.01%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.878 | 0.827 | -0.051 ms (-5.78%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.208 | 2.010 | -0.198 ms (-8.96%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 23.411 | 24.528 | +1.117 ms (+4.77%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 8490.962 | 8276.547 | -214.415 roots/s (-2.53%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 24.175 | 24.768 | +0.593 ms (+2.45%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8296.388 | 4285.806 | -4010.582 roots/s (-48.34%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 27.044 | 26.212 | -0.832 ms (-3.08%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 7383.502 | 7103.954 | -279.548 roots/s (-3.79%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1143.415 | 1038.502 | -104.913 KiB (-9.18%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 57.243 | 57.180 | -0.063 KiB (-0.11%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 307.840 | 290.226 | -17.614 KiB (-5.72%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 6.164 | 7.715 | +1.551 KiB (+25.16%) | 6 | larger |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1280.452 | 1289.960 | +9.508 KiB (+0.74%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 545.004 | 545.004 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.848 | 0.817 | -0.031 ms (-3.69%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.513 | 1.505 | -0.007 ms (-0.49%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 16.584 | 16.068 | -0.516 ms (-3.11%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 12235.066 | 12382.304 | +147.238 roots/s (+1.20%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 16.216 | 15.987 | -0.230 ms (-1.42%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12351.938 | 12533.160 | +181.222 roots/s (+1.47%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 19.307 | 19.309 | +0.002 ms (+0.01%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10478.221 | 10585.605 | +107.383 roots/s (+1.02%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1139.675 | 1132.808 | -6.867 KiB (-0.60%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 40.712 | 38.103 | -2.609 KiB (-6.41%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 313.190 | 302.128 | -11.062 KiB (-3.53%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 3.812 | 5.627 | +1.815 KiB (+47.63%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 302.880 | 292.653 | -10.227 KiB (-3.38%) | 3 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.809 | 171.863 | +0.055 KiB (+0.03%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.490 | 0.469 | -0.021 ms (-4.31%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.725 | 0.656 | -0.069 ms (-9.48%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.342 | 5.041 | -0.301 ms (-5.63%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 36814.338 | 38832.441 | +2018.103 roots/s (+5.48%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 5.921 | 5.543 | -0.378 ms (-6.39%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 33828.784 | 36056.338 | +2227.554 roots/s (+6.58%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 8.434 | 7.790 | -0.644 ms (-7.64%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 24077.167 | 25027.245 | +950.078 roots/s (+3.95%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 193.528 | 177.098 | -16.431 KiB (-8.49%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 27.891 | 32.916 | +5.025 KiB (+18.02%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 69.677 | 68.241 | -1.436 KiB (-2.06%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 1.921 | 3.137 | +1.216 KiB (+63.29%) | 6 | larger |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.222 | 4.667 | -1.555 us/projection (-24.99%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 161803.707 | 216124.980 | +54321.273 projections/s (+33.57%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.348 | 35.895 | -7.453 KiB (-17.19%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 47.183 | 41.653 | -5.529 KiB (-11.72%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 566.688 | 434.312 | -132.375 B/projection (-23.36%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 126.875 | 140.000 | +13.125 B/projection (+10.34%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.398 | 5.863 | -1.535 us/projection (-20.74%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 133425.897 | 173637.952 | +40212.055 projections/s (+30.14%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 47.434 | 39.090 | -8.344 KiB (-17.59%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 61.369 | 56.621 | -4.748 KiB (-7.74%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 581.688 | 434.312 | -147.375 B/projection (-25.34%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 177.250 | 191.125 | +13.875 B/projection (+7.83%) | 3 | larger |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.701 | 8.672 | -0.029 ms (-0.33%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 22735.778 | 23259.194 | +523.416 roots/s (+2.30%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.740 | 9.412 | -0.328 ms (-3.37%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20701.077 | 21571.094 | +870.017 roots/s (+4.20%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.881 | 41.159 | +24.277 ms (+143.81%) | 9 | slower |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 12089.919 | 11292.948 | -796.971 roots/s (-6.59%) | 9 | slower |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 16.878 | 18.319 | +1.440 ms (+8.53%) | 9 | slower |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 11744.872 | 11340.306 | -404.566 roots/s (-3.44%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 32.358 | 31.158 | -1.200 us/root (-3.71%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 99.004 | 96.629 | -2.375 KiB (-2.40%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.852 | 50.852 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 34.210 | 31.879 | -2.331 us/root (-6.81%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 103.316 | 101.980 | -1.336 KiB (-1.29%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.852 | 50.852 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 47.181 | 45.652 | -1.529 us/root (-3.24%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 147.043 | 144.445 | -2.598 KiB (-1.77%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.977 | 87.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 48.129 | 46.732 | -1.397 us/root (-2.90%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 150.992 | 149.680 | -1.312 KiB (-0.87%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.977 | 87.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 65.573 | 66.025 | +0.452 us/root (+0.69%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 218.461 | 215.234 | -3.227 KiB (-1.48%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.477 | 137.477 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 66.971 | 66.078 | -0.893 us/root (-1.33%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 221.883 | 218.836 | -3.047 KiB (-1.37%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.477 | 137.477 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 24.328 | 22.723 | -1.605 us/root (-6.60%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 62.293 | 60.105 | -2.188 KiB (-3.51%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.102 | 24.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 24.643 | 23.576 | -1.068 us/root (-4.33%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 68.605 | 67.457 | -1.148 KiB (-1.67%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.102 | 24.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 152.691 | 151.103 | -1.589 us/root (-1.04%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 625.758 | 621.332 | -4.426 KiB (-0.71%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.102 | 428.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 151.609 | 151.561 | -0.048 us/root (-0.03%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 629.699 | 626.340 | -3.359 KiB (-0.53%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.102 | 428.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 57.185 | 55.909 | -1.276 us/root (-2.23%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 195.082 | 191.219 | -3.863 KiB (-1.98%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.102 | 125.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 56.809 | 56.190 | -0.618 us/root (-1.09%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 198.129 | 194.910 | -3.219 KiB (-1.62%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.102 | 125.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 46.348 | 46.861 | +0.513 us/root (+1.11%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 128.688 | 126.313 | -2.375 KiB (-1.85%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.945 | 35.945 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 47.410 | 47.641 | +0.230 us/root (+0.49%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 133.001 | 131.665 | -1.336 KiB (-1.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.945 | 35.945 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 55.465 | 72.888 | +17.423 us/root (+31.41%) | 9 | slower |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 219.008 | 214.492 | -4.516 KiB (-2.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.727 | 136.727 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 56.281 | 55.242 | -1.039 us/root (-1.85%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 222.836 | 219.359 | -3.477 KiB (-1.56%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.727 | 136.727 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 143.681 | 149.339 | +5.658 us/root (+3.94%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 761.578 | 757.062 | -4.516 KiB (-0.59%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.227 | 480.227 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 145.512 | 148.568 | +3.056 us/root (+2.10%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 765.406 | 761.930 | -3.477 KiB (-0.45%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.227 | 480.227 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 253.125 | 231.917 | -21.208 us (-8.38%) | 9 | faster |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 37.383 | 28.543 | -8.840 KiB (-23.65%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 28.672 | 21.832 | -6.840 KiB (-23.86%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 366.959 | 348.042 | -18.917 us (-5.16%) | 9 | faster |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 50.452 | 38.530 | -11.922 KiB (-23.63%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 40.022 | 30.405 | -9.617 KiB (-24.03%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 488.292 | 457.208 | -31.084 us (-6.37%) | 9 | faster |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 62.865 | 47.896 | -14.969 KiB (-23.81%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 50.850 | 38.455 | -12.395 KiB (-24.37%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 89.500 | 82.541 | -6.959 us (-7.78%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 20.526 | 17.167 | -3.359 KiB (-16.37%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 13.761 | 10.972 | -2.789 KiB (-20.27%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 89.542 | 83.375 | -6.167 us (-6.89%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 20.432 | 17.182 | -3.250 KiB (-15.91%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 13.916 | 11.236 | -2.680 KiB (-19.26%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 87.875 | 80.709 | -7.166 us (-8.15%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 20.526 | 17.167 | -3.359 KiB (-16.37%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 13.761 | 10.968 | -2.793 KiB (-20.30%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 90.208 | 82.750 | -7.458 us (-8.27%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 20.432 | 17.182 | -3.250 KiB (-15.91%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 13.916 | 11.236 | -2.680 KiB (-19.26%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 90.666 | 80.000 | -10.666 us (-11.76%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 20.527 | 17.168 | -3.359 KiB (-16.37%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 13.762 | 10.973 | -2.789 KiB (-20.27%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 91.292 | 84.542 | -6.750 us (-7.39%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 20.433 | 17.183 | -3.250 KiB (-15.91%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 13.917 | 11.237 | -2.680 KiB (-19.25%) | 3 | smaller |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 11.333 | 2.209 | -9.124 us (-80.51%) | 9 | faster |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 15.625 | 2.708 | -12.917 us (-82.67%) | 9 | faster |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 19.958 | 3.292 | -16.666 us (-83.51%) | 9 | faster |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.closed.retainedKiB | 71.484 | 71.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.shared.retainedKiB | 50.789 | 50.789 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | small.closed.retainedKiB | 118.438 | 118.438 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | small.shared.retainedKiB | 111.070 | 111.070 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 10078.291 | 8914.417 | -1163.874 us (-11.55%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1353.777 | 1351.897 | -1.880 KiB (-0.14%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 741.773 | 741.773 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 102325.083 | 97788.625 | -4536.458 us (-4.43%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 13108.117 | 13106.237 | -1.880 KiB (-0.01%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 7416.219 | 7416.219 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 22166.000 | 17405.500 | -4760.500 us (-21.48%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 176.418 | 172.350 | -4.068 KiB (-2.31%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.700 | 3.700 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 118863.334 | 105757.334 | -13106.000 us (-11.03%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 181.324 | 178.662 | -2.662 KiB (-1.47%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.731 | 3.731 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8574.208 | 7921.500 | -652.708 us (-7.61%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1183.411 | 1180.812 | -2.599 KiB (-0.22%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 487.230 | 487.230 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 84907.166 | 84425.083 | -482.083 us (-0.57%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11348.603 | 11346.004 | -2.599 KiB (-0.02%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4869.488 | 4869.488 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 20663.500 | 16612.708 | -4050.792 us (-19.60%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 178.630 | 176.319 | -2.311 KiB (-1.29%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.571 | 2.571 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 104313.167 | 92222.542 | -12090.625 us (-11.59%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 180.536 | 178.226 | -2.311 KiB (-1.28%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.603 | 2.603 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 18634.375 | 17078.541 | -1555.834 us (-8.35%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1297.602 | 1297.487 | -0.114 KiB (-0.01%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 758.961 | 758.961 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 186578.541 | 171858.750 | -14719.791 us (-7.89%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12963.753 | 12747.543 | -216.210 KiB (-1.67%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7588.094 | 7588.094 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 30258.750 | 23676.250 | -6582.500 us (-21.75%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 283.668 | 281.568 | -2.100 KiB (-0.74%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.786 | 3.786 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 196406.625 | 175303.541 | -21103.084 us (-10.74%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 287.590 | 286.896 | -0.693 KiB (-0.24%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.817 | 3.817 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 16756.292 | 15070.917 | -1685.375 us (-10.06%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1265.931 | 1274.736 | +8.806 KiB (+0.70%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 510.668 | 510.668 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 164455.250 | 158078.542 | -6376.708 us (-3.88%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12964.446 | 12748.236 | -216.210 KiB (-1.67%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5103.863 | 5103.863 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 27902.750 | 21963.875 | -5938.875 us (-21.28%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 282.653 | 281.983 | -0.670 KiB (-0.24%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.688 | 2.688 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 179903.500 | 156043.208 | -23860.292 us (-13.26%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 284.216 | 283.546 | -0.670 KiB (-0.24%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.720 | 2.720 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6034.583 | 6652.167 | +617.584 us (+10.23%) | 9 | slower |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 402.667 | 402.662 | -0.005 KiB (-0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 245.097 | 245.097 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 870.084 | 899.292 | +29.208 us (+3.36%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 70.104 | 69.286 | -0.817 KiB (-1.17%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 34.177 | 34.177 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4499.875 | 4076.250 | -423.625 us (-9.41%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 360.000 | 360.378 | +0.378 KiB (+0.10%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 190.003 | 190.003 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 693.583 | 622.042 | -71.541 us (-10.31%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 61.960 | 61.471 | -0.489 KiB (-0.79%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.606 | 23.606 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8947.042 | 8128.584 | -818.458 us (-9.15%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 531.295 | 531.056 | -0.239 KiB (-0.05%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 317.237 | 317.237 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1324.541 | 1156.041 | -168.500 us (-12.72%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 86.798 | 86.559 | -0.239 KiB (-0.28%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 42.489 | 42.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6811.833 | 6187.709 | -624.124 us (-9.16%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 496.995 | 497.139 | +0.144 KiB (+0.03%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 261.722 | 261.722 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 1031.750 | 915.334 | -116.416 us (-11.28%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 81.553 | 81.329 | -0.224 KiB (-0.27%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.903 | 32.903 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 11008.375 | 10120.000 | -888.375 us (-8.07%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 686.104 | 686.044 | -0.060 KiB (-0.01%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 415.769 | 415.769 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1576.167 | 1418.375 | -157.792 us (-10.01%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 106.569 | 105.635 | -0.935 KiB (-0.88%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 54.958 | 54.958 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8692.333 | 7834.375 | -857.958 us (-9.87%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 638.780 | 639.041 | +0.261 KiB (+0.04%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 339.104 | 339.104 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1307.042 | 1150.167 | -156.875 us (-12.00%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 100.372 | 99.258 | -1.114 KiB (-1.11%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.911 | 42.911 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 386.686 | 379.533 | -7.152 KiB (-1.85%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 299.688 | 290.361 | -9.327 KiB (-3.11%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.523 | 0.497 | -0.026 ms (-4.90%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.811 | 0.672 | -0.139 ms (-17.10%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 5.163 | 4.354 | -0.809 ms (-15.66%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 39521.786 | 45704.717 | +6182.930 roots/s (+15.64%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 5.715 | 4.989 | -0.726 ms (-12.70%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 35831.320 | 40878.896 | +5047.577 roots/s (+14.09%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 8.106 | 7.195 | -0.911 ms (-11.24%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 24774.963 | 27860.974 | +3086.011 roots/s (+12.46%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 214.543 | 196.382 | -18.161 KiB (-8.47%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 40.480 | 41.003 | +0.522 KiB (+1.29%) | 6 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 77.941 | 73.391 | -4.551 KiB (-5.84%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 15.609 | 13.382 | -2.228 KiB (-14.27%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1224.021 | 1221.868 | -2.153 KiB (-0.18%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.383 | 531.383 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.743 | 0.692 | -0.051 ms (-6.86%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.116 | 1.033 | -0.083 ms (-7.44%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 8.673 | 7.763 | -0.910 ms (-10.49%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 22885.586 | 25919.608 | +3034.022 roots/s (+13.26%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 9.525 | 8.596 | -0.929 ms (-9.75%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 21040.913 | 23447.802 | +2406.889 roots/s (+11.44%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 12.411 | 11.350 | -1.062 ms (-8.55%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 15829.411 | 17592.212 | +1762.801 roots/s (+11.14%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 667.924 | 665.918 | -2.006 KiB (-0.30%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 34.473 | 31.732 | -2.740 KiB (-7.95%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 191.596 | 188.973 | -2.623 KiB (-1.37%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.597 | 5.107 | +1.511 KiB (+42.00%) | 6 | larger |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1770.636 | 1629.948 | -140.688 KiB (-7.95%) | 3 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.759 | 883.808 | +0.049 KiB (+0.01%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.856 | 0.801 | -0.055 ms (-6.47%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.203 | 1.910 | -0.293 ms (-13.30%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 23.307 | 20.263 | -3.044 ms (-13.06%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 8507.848 | 9808.169 | +1300.321 roots/s (+15.28%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 24.139 | 21.165 | -2.974 ms (-12.32%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8232.344 | 9382.330 | +1149.986 roots/s (+13.97%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 27.603 | 23.969 | -3.633 ms (-13.16%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 7312.481 | 8361.859 | +1049.379 roots/s (+14.35%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1177.754 | 1066.283 | -111.471 KiB (-9.46%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 58.687 | 53.752 | -4.935 KiB (-8.41%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 317.093 | 297.457 | -19.636 KiB (-6.19%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 6.336 | 7.949 | +1.613 KiB (+25.46%) | 6 | larger |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1347.291 | 1356.667 | +9.376 KiB (+0.70%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.414 | 554.414 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.857 | 0.843 | -0.015 ms (-1.69%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.610 | 1.428 | -0.182 ms (-11.29%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 16.680 | 14.849 | -1.831 ms (-10.98%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 11941.249 | 13457.479 | +1516.230 roots/s (+12.70%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 17.392 | 14.628 | -2.764 ms (-15.89%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12470.026 | 13452.726 | +982.700 roots/s (+7.88%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 19.528 | 18.029 | -1.499 ms (-7.68%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10288.308 | 11218.597 | +930.288 roots/s (+9.04%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1145.486 | 1145.230 | -0.256 KiB (-0.02%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 43.727 | 41.182 | -2.545 KiB (-5.82%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 307.869 | 307.629 | -0.240 KiB (-0.08%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 3.948 | 5.764 | +1.815 KiB (+45.98%) | 6 | larger |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 278.097 | 253.656 | -24.440 KiB (-8.79%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 174.946 | 174.895 | -0.052 KiB (-0.03%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.491 | 0.466 | -0.026 ms (-5.29%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.722 | 0.619 | -0.103 ms (-14.20%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 5.518 | 4.736 | -0.782 ms (-14.16%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 36853.622 | 38246.710 | +1393.088 roots/s (+3.78%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 5.947 | 5.402 | -0.545 ms (-9.16%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 33536.413 | 37572.211 | +4035.798 roots/s (+12.03%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 8.635 | 7.783 | -0.852 ms (-9.87%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 23533.565 | 25095.677 | +1562.112 roots/s (+6.64%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 200.928 | 183.117 | -17.811 KiB (-8.86%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 28.921 | 28.152 | -0.769 KiB (-2.66%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 67.291 | 64.733 | -2.558 KiB (-3.80%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 1.944 | 3.064 | +1.120 KiB (+57.61%) | 6 | larger |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.143 | 4.280 | -1.863 us/projection (-30.32%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 164736.163 | 231743.784 | +67007.621 projections/s (+40.68%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.496 | 37.535 | -7.961 KiB (-17.50%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 51.560 | 45.827 | -5.732 KiB (-11.12%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 599.672 | 460.703 | -138.969 B/projection (-23.17%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 128.266 | 139.859 | +11.594 B/projection (+9.04%) | 3 | larger |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.661 | 5.381 | -2.281 us/projection (-29.77%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 131788.931 | 187545.799 | +55756.868 projections/s (+42.31%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 49.652 | 40.730 | -8.922 KiB (-17.97%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 66.832 | 61.998 | -4.834 KiB (-7.23%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 615.672 | 460.703 | -154.969 B/projection (-25.17%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 178.766 | 190.984 | +12.219 B/projection (+6.84%) | 3 | larger |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.821 | 7.782 | -1.039 ms (-11.78%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 22435.044 | 25748.171 | +3313.127 roots/s (+14.77%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.798 | 8.596 | -1.202 ms (-12.27%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20345.880 | 23220.152 | +2874.272 roots/s (+14.13%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.921 | 15.248 | -1.673 ms (-9.89%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 11830.032 | 13162.839 | +1332.807 roots/s (+11.27%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 17.183 | 15.156 | -2.027 ms (-11.80%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 11518.111 | 13153.027 | +1634.916 roots/s (+14.19%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-boolean | columns.elapsedUsPerRoot | 110.827 | 103.724 | -7.103 us/root (-6.41%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-boolean | columns.peakKiB | 447.188 | 442.059 | -5.130 KiB (-1.15%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.retainedKiB | 162.484 | 162.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.elapsedUsPerRoot | 112.803 | 103.405 | -9.398 us/root (-8.33%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-boolean | document.peakKiB | 451.212 | 447.270 | -3.942 KiB (-0.87%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.retainedKiB | 162.484 | 162.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.elapsedUsPerRoot | 399.061 | 354.185 | -44.876 us/root (-11.25%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-bytes | columns.peakKiB | 954.355 | 952.093 | -2.263 KiB (-0.24%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.retainedKiB | 313.047 | 313.047 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.elapsedUsPerRoot | 403.560 | 358.415 | -45.145 us/root (-11.19%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-bytes | document.peakKiB | 958.113 | 955.663 | -2.450 KiB (-0.26%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.retainedKiB | 313.047 | 313.047 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.elapsedUsPerRoot | 427.151 | 385.973 | -41.178 us/root (-9.64%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-date | columns.peakKiB | 773.853 | 770.371 | -3.481 KiB (-0.45%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.retainedKiB | 192.965 | 192.965 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.elapsedUsPerRoot | 429.876 | 384.467 | -45.409 us/root (-10.56%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-date | document.peakKiB | 777.649 | 774.168 | -3.481 KiB (-0.45%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.retainedKiB | 192.965 | 192.965 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.elapsedUsPerRoot | 935.033 | 847.417 | -87.616 us/root (-9.37%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-decimal | columns.peakKiB | 1300.483 | 1298.807 | -1.677 KiB (-0.13%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.retainedKiB | 271.797 | 271.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.elapsedUsPerRoot | 938.210 | 862.768 | -75.441 us/root (-8.04%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-decimal | document.peakKiB | 1304.312 | 1302.635 | -1.677 KiB (-0.13%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.retainedKiB | 271.797 | 271.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.elapsedUsPerRoot | 811.590 | 751.283 | -60.307 us/root (-7.43%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float32 | columns.peakKiB | 691.443 | 689.181 | -2.263 KiB (-0.33%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.elapsedUsPerRoot | 811.738 | 741.904 | -69.835 us/root (-8.60%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float32 | document.peakKiB | 695.201 | 692.751 | -2.450 KiB (-0.35%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.elapsedUsPerRoot | 322.350 | 280.573 | -41.777 us/root (-12.96%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float64 | columns.peakKiB | 657.537 | 655.274 | -2.263 KiB (-0.34%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.elapsedUsPerRoot | 318.831 | 280.940 | -37.891 us/root (-11.88%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float64 | document.peakKiB | 661.295 | 658.845 | -2.450 KiB (-0.37%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.elapsedUsPerRoot | 159.543 | 144.564 | -14.979 us/root (-9.39%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int32 | columns.peakKiB | 639.337 | 634.207 | -5.130 KiB (-0.80%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.retainedKiB | 354.480 | 354.480 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.elapsedUsPerRoot | 158.440 | 145.108 | -13.332 us/root (-8.41%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int32 | document.peakKiB | 643.360 | 639.418 | -3.942 KiB (-0.61%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.retainedKiB | 354.480 | 354.480 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.elapsedUsPerRoot | 165.767 | 150.009 | -15.758 us/root (-9.51%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int64 | columns.peakKiB | 651.306 | 646.176 | -5.130 KiB (-0.79%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.retainedKiB | 366.484 | 366.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.elapsedUsPerRoot | 164.014 | 149.950 | -14.064 us/root (-8.57%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int64 | document.peakKiB | 655.329 | 651.387 | -3.942 KiB (-0.60%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.retainedKiB | 366.484 | 366.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.elapsedUsPerRoot | 567.331 | 504.777 | -62.553 us/root (-11.03%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-time | columns.peakKiB | 829.834 | 827.571 | -2.263 KiB (-0.27%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.retainedKiB | 277.984 | 277.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.elapsedUsPerRoot | 570.586 | 510.993 | -59.592 us/root (-10.44%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-time | document.peakKiB | 833.592 | 831.142 | -2.450 KiB (-0.29%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.retainedKiB | 277.984 | 277.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.elapsedUsPerRoot | 1007.112 | 753.665 | -253.447 us/root (-25.17%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.peakKiB | 933.672 | 936.304 | +2.632 KiB (+0.28%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.retainedKiB | 302.832 | 303.467 | +0.635 KiB (+0.21%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.elapsedUsPerRoot | 1002.125 | 762.375 | -239.750 us/root (-23.92%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-timestamp | document.peakKiB | 937.430 | 937.481 | +0.052 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.retainedKiB | 303.223 | 303.564 | +0.342 KiB (+0.11%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.elapsedUsPerRoot | 572.010 | 515.780 | -56.230 us/root (-9.83%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-uuid | columns.peakKiB | 1279.028 | 1277.242 | -1.786 KiB (-0.14%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.retainedKiB | 321.297 | 321.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.elapsedUsPerRoot | 575.331 | 511.044 | -64.287 us/root (-11.17%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-uuid | document.peakKiB | 1282.856 | 1281.070 | -1.786 KiB (-0.14%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.retainedKiB | 321.297 | 321.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 32.935 | 28.849 | -4.086 us/root (-12.41%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 97.325 | 95.539 | -1.786 KiB (-1.84%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.109 | 51.109 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 33.327 | 29.180 | -4.147 us/root (-12.44%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 101.036 | 99.250 | -1.786 KiB (-1.77%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.109 | 51.109 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 49.228 | 43.197 | -6.031 us/root (-12.25%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 148.214 | 145.752 | -2.462 KiB (-1.66%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.234 | 88.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 50.056 | 42.566 | -7.490 us/root (-14.96%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 151.401 | 149.158 | -2.243 KiB (-1.48%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.234 | 88.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 68.637 | 60.350 | -8.286 us/root (-12.07%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 223.218 | 220.354 | -2.864 KiB (-1.28%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.734 | 137.734 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 69.491 | 60.478 | -9.013 us/root (-12.97%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 227.249 | 224.174 | -3.075 KiB (-1.35%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.734 | 137.734 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 24.827 | 20.944 | -3.883 us/root (-15.64%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 61.062 | 58.370 | -2.692 KiB (-4.41%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.359 | 24.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 25.079 | 21.388 | -3.691 us/root (-14.72%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 67.422 | 65.917 | -1.505 KiB (-2.23%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.359 | 24.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 155.384 | 140.773 | -14.611 us/root (-9.40%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 629.829 | 624.949 | -4.880 KiB (-0.77%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.359 | 428.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 157.099 | 141.229 | -15.870 us/root (-10.10%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 633.739 | 629.922 | -3.817 KiB (-0.60%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.359 | 428.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 58.341 | 52.576 | -5.766 us/root (-9.88%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 198.134 | 193.785 | -4.349 KiB (-2.19%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.359 | 125.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 59.613 | 52.224 | -7.389 us/root (-12.40%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 201.552 | 197.992 | -3.560 KiB (-1.77%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.359 | 125.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 47.898 | 44.882 | -3.017 us/root (-6.30%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 127.213 | 125.427 | -1.786 KiB (-1.40%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.203 | 36.203 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 50.958 | 45.529 | -5.430 us/root (-10.66%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 130.924 | 129.138 | -1.786 KiB (-1.36%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.203 | 36.203 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 56.552 | 50.009 | -6.543 us/root (-11.57%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 222.470 | 217.340 | -5.130 KiB (-2.31%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.984 | 136.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 56.302 | 50.155 | -6.147 us/root (-10.92%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 226.376 | 222.434 | -3.942 KiB (-1.74%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.984 | 136.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 148.523 | 133.833 | -14.690 us/root (-9.89%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 765.188 | 760.059 | -5.130 KiB (-0.67%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.484 | 480.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 147.060 | 132.728 | -14.332 us/root (-9.75%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 769.095 | 765.152 | -3.942 KiB (-0.51%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.484 | 480.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 258.583 | 224.250 | -34.333 us (-13.28%) | 9 | faster |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 37.547 | 28.824 | -8.723 KiB (-23.23%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 29.992 | 22.754 | -7.238 KiB (-24.13%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 379.709 | 330.125 | -49.584 us (-13.06%) | 9 | faster |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 50.483 | 38.890 | -11.594 KiB (-22.97%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 41.921 | 31.702 | -10.219 KiB (-24.38%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 498.875 | 431.042 | -67.833 us (-13.60%) | 9 | faster |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 62.709 | 47.736 | -14.973 KiB (-23.88%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 53.326 | 40.123 | -13.203 KiB (-24.76%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 91.583 | 82.917 | -8.666 us (-9.46%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 21.005 | 17.204 | -3.801 KiB (-18.09%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.981 | 11.880 | -3.102 KiB (-20.70%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 93.292 | 85.417 | -7.875 us (-8.44%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 21.168 | 17.348 | -3.820 KiB (-18.05%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 15.145 | 12.168 | -2.977 KiB (-19.65%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 91.458 | 77.292 | -14.166 us (-15.49%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 21.005 | 17.204 | -3.801 KiB (-18.09%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.981 | 11.880 | -3.102 KiB (-20.70%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 93.875 | 78.166 | -15.709 us (-16.73%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 21.164 | 17.352 | -3.812 KiB (-18.01%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 15.145 | 12.168 | -2.977 KiB (-19.65%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 91.875 | 78.750 | -13.125 us (-14.29%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 21.006 | 17.205 | -3.801 KiB (-18.09%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.982 | 11.877 | -3.105 KiB (-20.73%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 93.000 | 82.292 | -10.708 us (-11.51%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 21.169 | 17.353 | -3.816 KiB (-18.03%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 15.146 | 12.169 | -2.977 KiB (-19.65%) | 3 | smaller |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 15.166 | 1.917 | -13.249 us (-87.36%) | 9 | faster |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 20.959 | 2.250 | -18.709 us (-89.26%) | 9 | faster |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 26.959 | 2.792 | -24.167 us (-89.64%) | 9 | faster |
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
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 210.416 | 177.250 | -33.166 us/row (-15.76%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 1432.000 | 848.000 | -584.000 B/row (-40.78%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 10866.000 | 9036.000 | -1830.000 B/row (-16.84%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 212.083 | 183.834 | -28.249 us/row (-13.32%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 1432.000 | 848.000 | -584.000 B/row (-40.78%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 11114.000 | 10013.000 | -1101.000 B/row (-9.91%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 315.250 | 224.833 | -90.417 us/row (-28.68%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 1432.000 | 848.000 | -584.000 B/row (-40.78%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 8956.000 | 7410.000 | -1546.000 B/row (-17.26%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 289.541 | 200.500 | -89.041 us/row (-30.75%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 1432.000 | 848.000 | -584.000 B/row (-40.78%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 9201.000 | 8131.000 | -1070.000 B/row (-11.63%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 357.667 | 232.167 | -125.500 us/row (-35.09%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1712.000 | 1128.000 | -584.000 B/row (-34.11%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 12574.000 | 11800.000 | -774.000 B/row (-6.16%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 339.000 | 214.000 | -125.000 us/row (-36.87%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1712.000 | 1128.000 | -584.000 B/row (-34.11%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13350.000 | 12858.000 | -492.000 B/row (-3.69%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 936.833 | 445.250 | -491.583 us/row (-52.47%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2832.000 | 2248.000 | -584.000 B/row (-20.62%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 20857.000 | 20116.000 | -741.000 B/row (-3.55%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 860.292 | 363.125 | -497.167 us/row (-57.79%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2832.000 | 2248.000 | -584.000 B/row (-20.62%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23890.000 | 23398.000 | -492.000 B/row (-2.06%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 287.250 | 280.916 | -6.334 us/row (-2.21%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 2160.000 | 1624.000 | -536.000 B/row (-24.81%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15296.000 | 18643.000 | +3347.000 B/row (+21.88%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 282.958 | 256.542 | -26.416 us/row (-9.34%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 2288.000 | 1656.000 | -632.000 B/row (-27.62%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16140.000 | 19119.000 | +2979.000 B/row (+18.46%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 283.625 | 269.416 | -14.209 us/row (-5.01%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 2160.000 | 1624.000 | -536.000 B/row (-24.81%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15481.000 | 17838.000 | +2357.000 B/row (+15.23%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 276.875 | 254.042 | -22.833 us/row (-8.25%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 2288.000 | 1656.000 | -632.000 B/row (-27.62%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 16221.000 | 18314.000 | +2093.000 B/row (+12.90%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 111.708 | 124.000 | +12.292 us/row (+11.00%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1648.000 | 1544.000 | -104.000 B/row (-6.31%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 8580.000 | 7892.000 | -688.000 B/row (-8.02%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 112.125 | 124.000 | +11.875 us/row (+10.59%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1648.000 | 1544.000 | -104.000 B/row (-6.31%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 8852.000 | 8292.000 | -560.000 B/row (-6.33%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 149.750 | 160.042 | +10.292 us/row (+6.87%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2320.000 | 2216.000 | -104.000 B/row (-4.48%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10341.000 | 9653.000 | -688.000 B/row (-6.65%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 145.459 | 157.541 | +12.082 us/row (+8.31%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2320.000 | 2216.000 | -104.000 B/row (-4.48%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 10497.000 | 9937.000 | -560.000 B/row (-5.33%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 194.375 | 208.459 | +14.084 us/row (+7.25%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3216.000 | 3112.000 | -104.000 B/row (-3.23%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 13466.000 | 12882.000 | -584.000 B/row (-4.34%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 194.375 | 209.583 | +15.208 us/row (+7.82%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3216.000 | 3112.000 | -104.000 B/row (-3.23%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 13552.000 | 12992.000 | -560.000 B/row (-4.13%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 90.125 | 96.833 | +6.708 us/row (+7.44%) | 9 | slower |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1144.000 | 1040.000 | -104.000 B/row (-9.09%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7425.000 | 6857.000 | -568.000 B/row (-7.65%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 87.125 | 100.125 | +13.000 us/row (+14.92%) | 9 | slower |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1144.000 | 1040.000 | -104.000 B/row (-9.09%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 7447.000 | 7007.000 | -440.000 B/row (-5.91%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 420.833 | 439.625 | +18.792 us/row (+4.47%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8608.000 | 8504.000 | -104.000 B/row (-1.21%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27376.000 | 26816.000 | -560.000 B/row (-2.05%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 418.167 | 434.334 | +16.167 us/row (+3.87%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8608.000 | 8504.000 | -104.000 B/row (-1.21%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 27539.000 | 27107.000 | -432.000 B/row (-1.57%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 175.125 | 185.833 | +10.708 us/row (+6.11%) | 9 | slower |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3040.000 | 2936.000 | -104.000 B/row (-3.42%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 11920.000 | 11360.000 | -560.000 B/row (-4.70%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 173.167 | 184.541 | +11.374 us/row (+6.57%) | 9 | slower |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3040.000 | 2936.000 | -104.000 B/row (-3.42%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 12219.000 | 11684.000 | -535.000 B/row (-4.38%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 159.750 | 167.667 | +7.917 us/row (+4.96%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1648.000 | 1544.000 | -104.000 B/row (-6.31%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8350.000 | 7705.000 | -645.000 B/row (-7.72%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 156.042 | 166.083 | +10.041 us/row (+6.43%) | 9 | slower |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1648.000 | 1544.000 | -104.000 B/row (-6.31%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 8619.000 | 8089.000 | -530.000 B/row (-6.15%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 210.708 | 205.625 | -5.083 us/row (-2.41%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2488.000 | 2384.000 | -104.000 B/row (-4.18%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11360.000 | 10887.000 | -473.000 B/row (-4.16%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 190.833 | 204.084 | +13.251 us/row (+6.94%) | 9 | slower |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2488.000 | 2384.000 | -104.000 B/row (-4.18%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 11640.000 | 11328.000 | -312.000 B/row (-2.68%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 517.416 | 536.792 | +19.376 us/row (+3.74%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5848.000 | 5744.000 | -104.000 B/row (-1.78%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23567.000 | 23127.000 | -440.000 B/row (-1.87%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 515.958 | 533.833 | +17.875 us/row (+3.46%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5848.000 | 5744.000 | -104.000 B/row (-1.78%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 24984.000 | 24672.000 | -312.000 B/row (-1.25%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 156.291 | 127.375 | -28.916 us/row (-18.50%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 1968.000 | 1832.000 | -136.000 B/row (-6.91%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 9139.000 | 7245.000 | -1894.000 B/row (-20.72%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 142.458 | 117.209 | -25.249 us/row (-17.72%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 2000.000 | 1864.000 | -136.000 B/row (-6.80%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 9459.000 | 8109.000 | -1350.000 B/row (-14.27%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 161.750 | 136.958 | -24.792 us/row (-15.33%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 1968.000 | 1832.000 | -136.000 B/row (-6.91%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 9927.000 | 8169.000 | -1758.000 B/row (-17.71%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 148.167 | 124.750 | -23.417 us/row (-15.80%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 2000.000 | 1864.000 | -136.000 B/row (-6.80%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 10247.000 | 9033.000 | -1214.000 B/row (-11.85%) | 9 | smaller |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.columns.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.columns.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.columns.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.document.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.document.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-patch.document.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.typed | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.typed | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.typed | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.columns.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.typed | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.typed | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.typed | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | plain.target-replace.document.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 193.125 | 186.250 | -6.875 us/row (-3.56%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 2160.000 | 1576.000 | -584.000 B/row (-27.04%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 11217.000 | 10314.000 | -903.000 B/row (-8.05%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 177.250 | 180.750 | +3.500 us/row (+1.97%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 2192.000 | 1608.000 | -584.000 B/row (-26.64%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 11517.000 | 10918.000 | -599.000 B/row (-5.20%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 202.459 | 203.958 | +1.499 us/row (+0.74%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 2160.000 | 1576.000 | -584.000 B/row (-27.04%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 11668.000 | 11508.000 | -160.000 B/row (-1.37%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 191.667 | 188.125 | -3.542 us/row (-1.85%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 2192.000 | 1608.000 | -584.000 B/row (-26.64%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 12096.000 | 11872.000 | -224.000 B/row (-1.85%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 116.541 | 124.792 | +8.251 us/row (+7.08%) | 9 | slower |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1872.000 | 1768.000 | -104.000 B/row (-5.56%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 10118.000 | 9851.000 | -267.000 B/row (-2.64%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 119.375 | 125.250 | +5.875 us/row (+4.92%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1872.000 | 1960.000 | +88.000 B/row (+4.70%) | 1 | larger |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 10302.000 | 10211.000 | -91.000 B/row (-0.88%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 114.625 | 123.250 | +8.625 us/row (+7.52%) | 9 | slower |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 1872.000 | 1768.000 | -104.000 B/row (-5.56%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 10142.000 | 9574.000 | -568.000 B/row (-5.60%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 117.834 | 127.292 | +9.458 us/row (+8.03%) | 9 | slower |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 1872.000 | 1960.000 | +88.000 B/row (+4.70%) | 1 | larger |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 10262.000 | 9974.000 | -288.000 B/row (-2.81%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.document.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.document.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-patch.document.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.typed | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.typed | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.typed | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.applyPatches | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.wire | elapsedUs | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.wire | retainedBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.target-replace.document.wire | transientBytes | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 87.083 | 31.834 | -55.249 us/row (-63.44%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 7168.000 | 3642.000 | -3526.000 B/row (-49.19%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 72.292 | 27.000 | -45.292 us/row (-62.65%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 7184.000 | 3590.000 | -3594.000 B/row (-50.03%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 87.542 | 32.459 | -55.083 us/row (-62.92%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 7168.000 | 3644.000 | -3524.000 B/row (-49.16%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 73.750 | 26.875 | -46.875 us/row (-63.56%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 7184.000 | 3593.000 | -3591.000 B/row (-49.99%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3374.875 | 3354.667 | -20.208 us (-0.60%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | retainedBytes | 426776.000 | 427360.000 | +584.000 B (+0.14%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 438904.000 | 439696.000 | +792.000 B (+0.18%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | 303.791 | 302.709 | -1.082 us (-0.36%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | 23472.000 | 24056.000 | +584.000 B (+2.49%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared.family | transientBytes | 27536.000 | 28416.000 | +880.000 B (+3.20%) | 9 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 24.915 | 19.936 | -4.979 us/row (-19.99%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 911.875 | 915.500 | +3.625 B/row (+0.40%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 2003.484 | 1822.250 | -181.234 B/row (-9.05%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 25.822 | 20.653 | -5.169 us/row (-20.02%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1913.375 | 1917.000 | +3.625 B/row (+0.19%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2469.828 | 2222.328 | -247.500 B/row (-10.02%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 29.440 | 24.969 | -4.471 us/row (-15.19%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1032.500 | 1047.000 | +14.500 B/row (+1.40%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2650.812 | 2266.375 | -384.438 B/row (-14.50%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 31.432 | 26.461 | -4.971 us/row (-15.82%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2038.500 | 2053.000 | +14.500 B/row (+0.71%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 3010.688 | 2588.688 | -422.000 B/row (-14.02%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 49.818 | 40.896 | -8.922 us/row (-17.91%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1523.000 | 1581.000 | +58.000 B/row (+3.81%) | 1 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 4640.250 | 3734.500 | -905.750 B/row (-19.52%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 49.557 | 42.021 | -7.537 us/row (-15.21%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2547.000 | 2605.000 | +58.000 B/row (+2.28%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 4862.750 | 3966.750 | -896.000 B/row (-18.43%) | 9 | smaller |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.columns | elapsedUs | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.columns | retainedBytes | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.columns | transientBytes | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.document | elapsedUs | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.document | retainedBytes | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.reaching.objects-128.document | transientBytes | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.unchanged.objects-128.document | elapsedUs | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.unchanged.objects-128.document | retainedBytes | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.unchanged.objects-128.document | transientBytes | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.wide.history-128.document | elapsedUs | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.wide.history-128.document | retainedBytes | | | | | missing on base |
| 3.13 | predicate-flush | predicate-flush.wide.history-128.document | transientBytes | | | | | missing on base |
| 3.13 | wire-insert-response | response.insert.family.wire | elapsedUs | 63.292 | 63.542 | +0.250 us/row (+0.39%) | 9 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | retainedBytes | 7528.000 | 8184.000 | +656.000 B/row (+8.71%) | 1 | larger |
| 3.13 | wire-insert-response | response.insert.family.wire | transientBytes | 7616.000 | 7696.000 | +80.000 B/row (+1.05%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 235.292 | 184.708 | -50.584 us/row (-21.50%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 1440.000 | 856.000 | -584.000 B/row (-40.56%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 11034.000 | 9716.000 | -1318.000 B/row (-11.94%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 239.167 | 195.875 | -43.292 us/row (-18.10%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 1440.000 | 856.000 | -584.000 B/row (-40.56%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 11554.000 | 10853.000 | -701.000 B/row (-6.07%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 361.333 | 222.167 | -139.166 us/row (-38.51%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 1440.000 | 856.000 | -584.000 B/row (-40.56%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 9220.000 | 8130.000 | -1090.000 B/row (-11.82%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 321.875 | 207.709 | -114.166 us/row (-35.47%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 1440.000 | 856.000 | -584.000 B/row (-40.56%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 9649.000 | 8987.000 | -662.000 B/row (-6.86%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 385.167 | 233.250 | -151.917 us/row (-39.44%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1720.000 | 1136.000 | -584.000 B/row (-33.95%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 12926.000 | 12592.000 | -334.000 B/row (-2.58%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 370.000 | 215.875 | -154.125 us/row (-41.66%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1720.000 | 1136.000 | -584.000 B/row (-33.95%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13854.000 | 13786.000 | -68.000 B/row (-0.49%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 995.667 | 429.291 | -566.376 us/row (-56.88%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2840.000 | 2256.000 | -584.000 B/row (-20.56%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 23617.000 | 20852.000 | -2765.000 B/row (-11.71%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 920.042 | 348.041 | -572.001 us/row (-62.17%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2840.000 | 2256.000 | -584.000 B/row (-20.56%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 26834.000 | 24270.000 | -2564.000 B/row (-9.56%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 318.209 | 277.958 | -40.251 us/row (-12.65%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 2176.000 | 1640.000 | -536.000 B/row (-24.63%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 14896.000 | 19483.000 | +4587.000 B/row (+30.79%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 318.084 | 263.250 | -54.834 us/row (-17.24%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 2304.000 | 1672.000 | -632.000 B/row (-27.43%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16004.000 | 20123.000 | +4119.000 B/row (+25.74%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 311.750 | 274.041 | -37.709 us/row (-12.10%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 2176.000 | 1640.000 | -536.000 B/row (-24.63%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15217.000 | 18542.000 | +3325.000 B/row (+21.85%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 311.458 | 254.625 | -56.833 us/row (-18.25%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 2304.000 | 1672.000 | -632.000 B/row (-27.43%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 16325.000 | 19182.000 | +2857.000 B/row (+17.50%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 130.291 | 133.250 | +2.959 us/row (+2.27%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1704.000 | 1560.000 | -144.000 B/row (-8.45%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 9116.000 | 8556.000 | -560.000 B/row (-6.14%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 130.208 | 130.291 | +0.083 us/row (+0.06%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1704.000 | 1560.000 | -144.000 B/row (-8.45%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 9516.000 | 9020.000 | -496.000 B/row (-5.21%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 165.709 | 165.709 | +0.000 us/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2376.000 | 2232.000 | -144.000 B/row (-6.06%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10973.000 | 10413.000 | -560.000 B/row (-5.10%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 168.000 | 166.083 | -1.917 us/row (-1.14%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2376.000 | 2232.000 | -144.000 B/row (-6.06%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 11257.000 | 10769.000 | -488.000 B/row (-4.34%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 213.709 | 206.333 | -7.376 us/row (-3.45%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3272.000 | 3128.000 | -144.000 B/row (-4.40%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 14186.000 | 13754.000 | -432.000 B/row (-3.05%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 215.375 | 207.833 | -7.542 us/row (-3.50%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3272.000 | 3128.000 | -144.000 B/row (-4.40%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 14360.000 | 13912.000 | -448.000 B/row (-3.12%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 109.000 | 108.167 | -0.833 us/row (-0.76%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1192.000 | 1048.000 | -144.000 B/row (-12.08%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7961.000 | 7457.000 | -504.000 B/row (-6.33%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 107.959 | 108.000 | +0.041 us/row (+0.04%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1192.000 | 1048.000 | -144.000 B/row (-12.08%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 8047.000 | 7671.000 | -376.000 B/row (-4.67%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 448.250 | 424.667 | -23.583 us/row (-5.26%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8664.000 | 8520.000 | -144.000 B/row (-1.66%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27944.000 | 27472.000 | -472.000 B/row (-1.69%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 447.458 | 411.083 | -36.375 us/row (-8.13%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8664.000 | 8520.000 | -144.000 B/row (-1.66%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 28171.000 | 27827.000 | -344.000 B/row (-1.22%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 197.250 | 188.500 | -8.750 us/row (-4.44%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3096.000 | 2952.000 | -144.000 B/row (-4.65%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 12488.000 | 12016.000 | -472.000 B/row (-3.78%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 193.458 | 187.708 | -5.750 us/row (-2.97%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3096.000 | 2952.000 | -144.000 B/row (-4.65%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 12883.000 | 12420.000 | -463.000 B/row (-3.59%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 181.000 | 174.041 | -6.959 us/row (-3.84%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1704.000 | 1560.000 | -144.000 B/row (-8.45%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8918.000 | 8409.000 | -509.000 B/row (-5.71%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 179.875 | 171.000 | -8.875 us/row (-4.93%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1704.000 | 1560.000 | -144.000 B/row (-8.45%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 9315.000 | 8857.000 | -458.000 B/row (-4.92%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 212.000 | 205.208 | -6.792 us/row (-3.20%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2544.000 | 2400.000 | -144.000 B/row (-5.66%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11960.000 | 11607.000 | -353.000 B/row (-2.95%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 214.250 | 206.375 | -7.875 us/row (-3.68%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2544.000 | 2400.000 | -144.000 B/row (-5.66%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 12336.000 | 12112.000 | -224.000 B/row (-1.82%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 550.917 | 497.291 | -53.626 us/row (-9.73%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 24135.000 | 23847.000 | -288.000 B/row (-1.19%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 552.667 | 504.125 | -48.542 us/row (-8.78%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 25680.000 | 25456.000 | -224.000 B/row (-0.87%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | elapsedUs | 486.917 | 469.833 | -17.084 us/row (-3.51%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | transientBytes | 21101.000 | 20813.000 | -288.000 B/row (-1.36%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | elapsedUs | 555.333 | 515.875 | -39.458 us/row (-7.11%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.columns.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | transientBytes | 21197.000 | 21021.000 | -176.000 B/row (-0.83%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | elapsedUs | 489.708 | 453.666 | -36.042 us/row (-7.36%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | transientBytes | 22046.000 | 21822.000 | -224.000 B/row (-1.02%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | elapsedUs | 547.875 | 513.375 | -34.500 us/row (-6.30%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.document.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | transientBytes | 22142.000 | 22030.000 | -112.000 B/row (-0.51%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | elapsedUs | 566.333 | 518.125 | -48.208 us/row (-8.51%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | transientBytes | 44547.000 | 44259.000 | -288.000 B/row (-0.65%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | elapsedUs | 736.291 | 662.458 | -73.833 us/row (-10.03%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.columns.wire | retainedBytes | 15312.000 | 15376.000 | +64.000 B/row (+0.42%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | transientBytes | 54051.000 | 53875.000 | -176.000 B/row (-0.33%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | elapsedUs | 559.542 | 517.750 | -41.792 us/row (-7.47%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | transientBytes | 47372.000 | 47148.000 | -224.000 B/row (-0.47%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | elapsedUs | 727.417 | 657.750 | -69.667 us/row (-9.58%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.document.wire | retainedBytes | 15312.000 | 15376.000 | +64.000 B/row (+0.42%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | transientBytes | 56876.000 | 56764.000 | -112.000 B/row (-0.20%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | elapsedUs | 622.833 | 573.083 | -49.750 us/row (-7.99%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | transientBytes | 33282.000 | 32994.000 | -288.000 B/row (-0.87%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | elapsedUs | 855.584 | 781.000 | -74.584 us/row (-8.72%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.columns.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | transientBytes | 39514.000 | 39338.000 | -176.000 B/row (-0.45%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | elapsedUs | 630.834 | 576.250 | -54.584 us/row (-8.65%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | transientBytes | 34699.000 | 34475.000 | -224.000 B/row (-0.65%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | elapsedUs | 842.583 | 787.042 | -55.541 us/row (-6.59%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.document.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | transientBytes | 40931.000 | 40819.000 | -112.000 B/row (-0.27%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | elapsedUs | 1075.208 | 960.292 | -114.916 us/row (-10.69%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | transientBytes | 36141.000 | 35869.000 | -272.000 B/row (-0.75%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | elapsedUs | 1894.208 | 1692.000 | -202.208 us/row (-10.68%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.columns.wire | retainedBytes | 28944.000 | 29008.000 | +64.000 B/row (+0.22%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | transientBytes | 59337.000 | 59209.000 | -128.000 B/row (-0.22%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | elapsedUs | 1056.458 | 957.666 | -98.792 us/row (-9.35%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | transientBytes | 37686.000 | 37478.000 | -208.000 B/row (-0.55%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | elapsedUs | 1878.375 | 1709.417 | -168.958 us/row (-8.99%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.document.wire | retainedBytes | 28944.000 | 29008.000 | +64.000 B/row (+0.22%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | transientBytes | 60818.000 | 60818.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | elapsedUs | 1021.792 | 826.875 | -194.917 us/row (-19.08%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.columns.typed | retainedBytes | 10512.000 | 10368.000 | -144.000 B/row (-1.37%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | transientBytes | 30837.000 | 30549.000 | -288.000 B/row (-0.93%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | elapsedUs | 1517.958 | 1181.000 | -336.958 us/row (-22.20%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.columns.wire | retainedBytes | 10512.000 | 10576.000 | +64.000 B/row (+0.61%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | transientBytes | 30997.000 | 30757.000 | -240.000 B/row (-0.77%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | elapsedUs | 892.792 | 830.292 | -62.500 us/row (-7.00%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.document.typed | retainedBytes | 10512.000 | 10368.000 | -144.000 B/row (-1.37%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | transientBytes | 31870.000 | 31646.000 | -224.000 B/row (-0.70%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | elapsedUs | 1302.333 | 1187.917 | -114.416 us/row (-8.79%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.document.wire | retainedBytes | 10512.000 | 10576.000 | +64.000 B/row (+0.61%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | transientBytes | 31966.000 | 31854.000 | -112.000 B/row (-0.35%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | elapsedUs | 578.334 | 508.167 | -70.167 us/row (-12.13%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | transientBytes | 21573.000 | 21285.000 | -288.000 B/row (-1.34%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | elapsedUs | 677.500 | 597.625 | -79.875 us/row (-11.79%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.columns.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | transientBytes | 21669.000 | 21493.000 | -176.000 B/row (-0.81%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | elapsedUs | 569.167 | 510.125 | -59.042 us/row (-10.37%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | transientBytes | 22606.000 | 22382.000 | -224.000 B/row (-0.99%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | elapsedUs | 656.500 | 594.375 | -62.125 us/row (-9.46%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.document.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | transientBytes | 22702.000 | 22590.000 | -112.000 B/row (-0.49%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | elapsedUs | 509.958 | 469.625 | -40.333 us/row (-7.91%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | transientBytes | 22326.000 | 22038.000 | -288.000 B/row (-1.29%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | elapsedUs | 644.708 | 592.250 | -52.458 us/row (-8.14%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.columns.wire | retainedBytes | 12032.000 | 12096.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | transientBytes | 28510.000 | 28334.000 | -176.000 B/row (-0.62%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | elapsedUs | 510.041 | 472.000 | -38.041 us/row (-7.46%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | transientBytes | 23510.000 | 23286.000 | -224.000 B/row (-0.95%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | elapsedUs | 651.375 | 588.833 | -62.542 us/row (-9.60%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.document.wire | retainedBytes | 12032.000 | 12096.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | transientBytes | 29694.000 | 29582.000 | -112.000 B/row (-0.38%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | elapsedUs | 531.625 | 495.667 | -35.958 us/row (-6.76%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | transientBytes | 23306.000 | 23018.000 | -288.000 B/row (-1.24%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | elapsedUs | 678.250 | 618.750 | -59.500 us/row (-8.77%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.columns.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | transientBytes | 29546.000 | 29370.000 | -176.000 B/row (-0.60%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | elapsedUs | 540.000 | 484.333 | -55.667 us/row (-10.31%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | transientBytes | 24686.000 | 24462.000 | -224.000 B/row (-0.91%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | elapsedUs | 703.417 | 619.333 | -84.084 us/row (-11.95%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.document.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | transientBytes | 30926.000 | 30814.000 | -112.000 B/row (-0.36%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | elapsedUs | 673.458 | 618.500 | -54.958 us/row (-8.16%) | 9 | faster |
| 3.14 | keyed-write | leaf.string.columns.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | transientBytes | 24228.000 | 24052.000 | -176.000 B/row (-0.73%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | elapsedUs | 672.125 | 614.083 | -58.042 us/row (-8.64%) | 9 | faster |
| 3.14 | keyed-write | leaf.string.document.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | transientBytes | 25773.000 | 25661.000 | -112.000 B/row (-0.43%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | elapsedUs | 678.625 | 627.000 | -51.625 us/row (-7.61%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | transientBytes | 35842.000 | 35554.000 | -288.000 B/row (-0.80%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | elapsedUs | 945.166 | 867.250 | -77.916 us/row (-8.24%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.columns.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | transientBytes | 42138.000 | 41898.000 | -240.000 B/row (-0.57%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | elapsedUs | 683.708 | 622.417 | -61.291 us/row (-8.96%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | transientBytes | 37579.000 | 37355.000 | -224.000 B/row (-0.60%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | elapsedUs | 935.250 | 866.542 | -68.708 us/row (-7.35%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.document.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | transientBytes | 43811.000 | 43699.000 | -112.000 B/row (-0.26%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | elapsedUs | 957.542 | 713.250 | -244.292 us/row (-25.51%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | transientBytes | 41991.000 | 41703.000 | -288.000 B/row (-0.69%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | elapsedUs | 1443.750 | 1080.375 | -363.375 us/row (-25.17%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | retainedBytes | 15120.000 | 15184.000 | +64.000 B/row (+0.42%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | transientBytes | 51611.000 | 51483.000 | -128.000 B/row (-0.25%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | elapsedUs | 942.875 | 706.583 | -236.292 us/row (-25.06%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | transientBytes | 44496.000 | 44272.000 | -224.000 B/row (-0.50%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | elapsedUs | 1452.667 | 1080.334 | -372.333 us/row (-25.63%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.document.wire | retainedBytes | 15120.000 | 15184.000 | +64.000 B/row (+0.42%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | transientBytes | 54052.000 | 54052.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | elapsedUs | 913.000 | 816.500 | -96.500 us/row (-10.57%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | transientBytes | 46714.000 | 46426.000 | -288.000 B/row (-0.62%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | elapsedUs | 1264.291 | 1144.166 | -120.125 us/row (-9.50%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.columns.wire | retainedBytes | 26640.000 | 26704.000 | +64.000 B/row (+0.24%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | transientBytes | 67610.000 | 67370.000 | -240.000 B/row (-0.35%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | elapsedUs | 917.083 | 809.333 | -107.750 us/row (-11.75%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | transientBytes | 49795.000 | 49571.000 | -224.000 B/row (-0.45%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | elapsedUs | 1266.167 | 1144.875 | -121.292 us/row (-9.58%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.document.wire | retainedBytes | 26640.000 | 26704.000 | +64.000 B/row (+0.24%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | transientBytes | 70627.000 | 70515.000 | -112.000 B/row (-0.16%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 180.667 | 134.584 | -46.083 us/row (-25.51%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 2064.000 | 1872.000 | -192.000 B/row (-9.30%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 9683.000 | 7805.000 | -1878.000 B/row (-19.39%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 170.250 | 127.083 | -43.167 us/row (-25.36%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 2024.000 | 1904.000 | -120.000 B/row (-5.93%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 10163.000 | 8817.000 | -1346.000 B/row (-13.24%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 188.208 | 151.625 | -36.583 us/row (-19.44%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 1992.000 | 1872.000 | -120.000 B/row (-6.02%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 10535.000 | 8713.000 | -1822.000 B/row (-17.29%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 173.750 | 136.458 | -37.292 us/row (-21.46%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 2024.000 | 1904.000 | -120.000 B/row (-5.93%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 11015.000 | 9725.000 | -1290.000 B/row (-11.71%) | 9 | smaller |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-patch.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.target-replace.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 221.959 | 195.292 | -26.667 us/row (-12.01%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 2176.000 | 1592.000 | -584.000 B/row (-26.84%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 11489.000 | 11066.000 | -423.000 B/row (-3.68%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 204.125 | 187.250 | -16.875 us/row (-8.27%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 2208.000 | 1624.000 | -584.000 B/row (-26.45%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 11949.000 | 11818.000 | -131.000 B/row (-1.10%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 236.667 | 202.708 | -33.959 us/row (-14.35%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 2176.000 | 1592.000 | -584.000 B/row (-26.84%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 11948.000 | 12132.000 | +184.000 B/row (+1.54%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 229.042 | 194.625 | -34.417 us/row (-15.03%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 2208.000 | 1624.000 | -584.000 B/row (-26.45%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 12536.000 | 12708.000 | +172.000 B/row (+1.37%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 134.875 | 135.000 | +0.125 us/row (+0.09%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1928.000 | 1784.000 | -144.000 B/row (-7.47%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 10550.000 | 10587.000 | +37.000 B/row (+0.35%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 139.000 | 136.083 | -2.917 us/row (-2.10%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1928.000 | 1992.000 | +64.000 B/row (+3.32%) | 1 | larger |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 10670.000 | 11035.000 | +365.000 B/row (+3.42%) | 9 | larger |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 133.958 | 145.250 | +11.292 us/row (+8.43%) | 9 | slower |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 1928.000 | 1784.000 | -144.000 B/row (-7.47%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 10702.000 | 10342.000 | -360.000 B/row (-3.36%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 136.042 | 138.625 | +2.583 us/row (+1.90%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 1928.000 | 1992.000 | +64.000 B/row (+3.32%) | 1 | larger |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 10798.000 | 10766.000 | -32.000 B/row (-0.30%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-patch.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.target-replace.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 97.417 | 34.125 | -63.292 us/row (-64.97%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 7744.000 | 4010.000 | -3734.000 B/row (-48.22%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 84.625 | 27.750 | -56.875 us/row (-67.21%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 7856.000 | 3742.000 | -4114.000 B/row (-52.37%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 97.834 | 34.167 | -63.667 us/row (-65.08%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 7744.000 | 4012.000 | -3732.000 B/row (-48.19%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 84.042 | 28.333 | -55.709 us/row (-66.29%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 7856.000 | 3745.000 | -4111.000 B/row (-52.33%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3321.958 | 3005.750 | -316.208 us (-9.52%) | 9 | faster |
| 3.14 | model-preparation | model.prepared | retainedBytes | 438440.000 | 439024.000 | +584.000 B (+0.13%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 444984.000 | 445848.000 | +864.000 B (+0.19%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | 311.625 | 295.583 | -16.042 us (-5.15%) | 9 | faster |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | 23920.000 | 24504.000 | +584.000 B (+2.44%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared.family | transientBytes | 27688.000 | 28648.000 | +960.000 B (+3.47%) | 9 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 24.938 | 17.707 | -7.230 us/row (-28.99%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 985.594 | 989.156 | +3.562 B/row (+0.36%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 2050.805 | 1872.203 | -178.602 B/row (-8.71%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 25.788 | 18.230 | -7.558 us/row (-29.31%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1987.219 | 1990.781 | +3.562 B/row (+0.18%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2436.273 | 2317.531 | -118.742 B/row (-4.87%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 29.803 | 21.729 | -8.074 us/row (-27.09%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1135.375 | 1149.625 | +14.250 B/row (+1.26%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2696.094 | 2360.000 | -336.094 B/row (-12.47%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 30.316 | 22.277 | -8.039 us/row (-26.52%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2141.875 | 2156.125 | +14.250 B/row (+0.67%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 3022.219 | 2705.500 | -316.719 B/row (-10.48%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 49.339 | 37.911 | -11.427 us/row (-23.16%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1742.500 | 1799.500 | +57.000 B/row (+3.27%) | 1 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 4822.375 | 3918.000 | -904.375 B/row (-18.75%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 50.938 | 39.984 | -10.953 us/row (-21.50%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2768.500 | 2825.500 | +57.000 B/row (+2.06%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 5052.875 | 4170.000 | -882.875 B/row (-17.47%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | elapsedUs | 118.818 | 99.927 | -18.891 us/row (-15.90%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | retainedBytes | 3166.500 | 3223.500 | +57.000 B/row (+1.80%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | transientBytes | 17259.375 | 16310.000 | -949.375 B/row (-5.50%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | elapsedUs | 117.375 | 102.510 | -14.865 us/row (-12.66%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | retainedBytes | 16642.500 | 16699.500 | +57.000 B/row (+0.34%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | transientBytes | 19092.625 | 18017.000 | -1075.625 B/row (-5.63%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | elapsedUs | 331.250 | 286.938 | -44.312 us/row (-13.38%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | retainedBytes | 12966.500 | 13023.500 | +57.000 B/row (+0.44%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | transientBytes | 32976.000 | 32027.125 | -948.875 B/row (-2.88%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | elapsedUs | 329.901 | 288.010 | -41.891 us/row (-12.70%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | retainedBytes | 40458.500 | 40515.500 | +57.000 B/row (+0.14%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | transientBytes | 43064.250 | 41966.125 | -1098.125 B/row (-2.55%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | elapsedUs | 389.057 | 334.240 | -54.818 us/row (-14.09%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | retainedBytes | 9566.500 | 9623.500 | +57.000 B/row (+0.60%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | transientBytes | 28226.625 | 27278.000 | -948.625 B/row (-3.36%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | elapsedUs | 377.651 | 335.177 | -42.474 us/row (-11.25%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | retainedBytes | 32834.500 | 32891.500 | +57.000 B/row (+0.17%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | transientBytes | 35442.875 | 34361.000 | -1081.875 B/row (-3.05%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | elapsedUs | 722.505 | 650.281 | -72.224 us/row (-10.00%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | retainedBytes | 27166.500 | 27223.500 | +57.000 B/row (+0.21%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | transientBytes | 33197.375 | 32109.000 | -1088.375 B/row (-3.28%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | elapsedUs | 733.615 | 647.266 | -86.349 us/row (-11.77%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | retainedBytes | 50818.500 | 50875.500 | +57.000 B/row (+0.11%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | transientBytes | 53602.375 | 52530.750 | -1071.625 B/row (-2.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | elapsedUs | 588.302 | 534.203 | -54.099 us/row (-9.20%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | retainedBytes | 7966.500 | 8023.500 | +57.000 B/row (+0.72%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | transientBytes | 22665.375 | 21716.000 | -949.375 B/row (-4.19%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | elapsedUs | 602.010 | 534.734 | -67.276 us/row (-11.18%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | retainedBytes | 26050.500 | 26107.500 | +57.000 B/row (+0.22%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | transientBytes | 28537.625 | 27455.000 | -1082.625 B/row (-3.79%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | elapsedUs | 270.812 | 230.786 | -40.026 us/row (-14.78%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | retainedBytes | 7774.500 | 7831.500 | +57.000 B/row (+0.73%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | transientBytes | 21888.375 | 20939.000 | -949.375 B/row (-4.34%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | elapsedUs | 267.339 | 228.875 | -38.464 us/row (-14.39%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | retainedBytes | 21250.500 | 21307.500 | +57.000 B/row (+0.27%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | transientBytes | 23728.625 | 22646.000 | -1082.625 B/row (-4.56%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | elapsedUs | 167.781 | 145.036 | -22.745 us/row (-13.56%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | retainedBytes | 9566.000 | 9623.000 | +57.000 B/row (+0.60%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | transientBytes | 23668.375 | 22719.500 | -948.875 B/row (-4.01%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | elapsedUs | 168.359 | 142.656 | -25.703 us/row (-15.27%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | retainedBytes | 23042.000 | 23099.000 | +57.000 B/row (+0.25%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | transientBytes | 25508.625 | 24426.500 | -1082.125 B/row (-4.24%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | elapsedUs | 171.906 | 153.552 | -18.354 us/row (-10.68%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | retainedBytes | 9950.500 | 10007.500 | +57.000 B/row (+0.57%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | transientBytes | 24057.375 | 23108.500 | -948.875 B/row (-3.94%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | elapsedUs | 182.224 | 149.427 | -32.797 us/row (-18.00%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | retainedBytes | 23426.500 | 23483.500 | +57.000 B/row (+0.24%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | transientBytes | 25897.625 | 24815.500 | -1082.125 B/row (-4.18%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | elapsedUs | 153.182 | 132.870 | -20.313 us/row (-13.26%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | retainedBytes | 13342.500 | 13399.500 | +57.000 B/row (+0.43%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | transientBytes | 27434.875 | 26485.750 | -949.125 B/row (-3.46%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | elapsedUs | 154.651 | 133.359 | -21.292 us/row (-13.77%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | retainedBytes | 26818.500 | 26875.500 | +57.000 B/row (+0.21%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | transientBytes | 29284.125 | 28192.750 | -1091.375 B/row (-3.73%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | elapsedUs | 479.099 | 420.453 | -58.646 us/row (-12.24%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | retainedBytes | 9566.500 | 9623.500 | +57.000 B/row (+0.60%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | transientBytes | 29194.625 | 28246.000 | -948.625 B/row (-3.25%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | elapsedUs | 482.990 | 432.594 | -50.396 us/row (-10.43%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | retainedBytes | 33794.500 | 33851.500 | +57.000 B/row (+0.17%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | transientBytes | 36410.875 | 35329.000 | -1081.875 B/row (-2.97%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | elapsedUs | 819.667 | 615.943 | -203.724 us/row (-24.85%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | retainedBytes | 12766.500 | 12823.500 | +57.000 B/row (+0.45%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | transientBytes | 32030.625 | 31095.750 | -934.875 B/row (-2.92%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | elapsedUs | 808.391 | 626.625 | -181.766 us/row (-22.48%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | retainedBytes | 39298.500 | 39355.500 | +57.000 B/row (+0.15%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | transientBytes | 41934.875 | 40851.750 | -1083.125 B/row (-2.58%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | elapsedUs | 433.552 | 377.214 | -56.339 us/row (-12.99%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | retainedBytes | 24761.000 | 24818.000 | +57.000 B/row (+0.23%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | transientBytes | 35620.125 | 34671.500 | -948.625 B/row (-2.66%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | elapsedUs | 435.786 | 378.057 | -57.729 us/row (-13.25%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | retainedBytes | 53021.000 | 53078.000 | +57.000 B/row (+0.11%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | transientBytes | 55604.375 | 54522.500 | -1081.875 B/row (-1.95%) | 9 | within noise |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.reaching.objects-128.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.unchanged.objects-128.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.unchanged.objects-128.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.unchanged.objects-128.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.wide.history-128.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.wide.history-128.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-flush | predicate-flush.wide.history-128.document | transientBytes | | | | | missing on base |
| 3.14 | wire-insert-response | response.insert.family.wire | elapsedUs | 64.750 | 61.958 | -2.792 us/row (-4.31%) | 9 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | retainedBytes | 8748.000 | 9364.000 | +616.000 B/row (+7.04%) | 1 | larger |
| 3.14 | wire-insert-response | response.insert.family.wire | transientBytes | 8718.000 | 8774.000 | +56.000 B/row (+0.64%) | 9 | within noise |

Deltas are advisory and never ratchet the Budget Contract.
