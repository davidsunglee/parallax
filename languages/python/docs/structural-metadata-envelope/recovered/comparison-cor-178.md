# Python cost report comparison

Timing deltas within 5% and byte deltas within 3% are read as noise; count deltas are exact. A cell present on one side alone, or whose unit differs, is not compared.

- The base capture is amended: 364 re-measured readings changed after the run its provenance names, recorded in the adjustment of conditions.json.

## instance-state

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| - | - | cpython-3.13 | aggregate.bare.after | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.before | 6384.000 | 6384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.reduction | 0.617 | 0.617 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.before | 7200.000 | 7200.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.reduction | 0.547 | 0.547 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.340 | 3.491 | +0.151 ratio (+4.51%) | 0 | larger |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.340 | 3.491 | +0.151 ratio (+4.51%) | 0 | larger |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.313 | 3.402 | +0.089 ratio (+2.68%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 0.522 | 0.509 | -0.013 ratio (-2.42%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.likeForLike | 0.500 | 0.490 | -0.010 ratio (-2.05%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 1.549 | 1.536 | -0.014 ratio (-0.89%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.184 | 2.146 | -0.038 ratio (-1.74%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.184 | 2.146 | -0.038 ratio (-1.74%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.209 | 2.157 | -0.052 ratio (-2.35%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 1471.432 | 1510.108 | +38.676 ns (+2.63%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 6919.735 | 6811.038 | -108.698 ns (-1.57%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.directWireNs | 10597.250 | 10584.791 | -12.459 ns (-0.12%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.dumpNs | 5770.104 | 5916.395 | +146.291 ns (+2.54%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 4770.000 | 4770.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionNs | 14270.875 | 14179.750 | -91.125 ns (-0.64%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | 7560.000 | 7560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | 1240.000 | 1240.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | 12258.998 | 12181.296 | -77.702 ns (-0.63%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | 6320.000 | 6320.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.readNs | 83.312 | 85.100 | +1.788 ns (+2.15%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 425.885 | 343.561 | -82.324 ns (-19.33%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 3706.000 | 3706.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 425.885 | 343.561 | -82.324 ns (-19.33%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | 105.925 | 93.333 | -12.592 ns (-11.89%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 10317.575 | 10265.000 | -52.575 ns (-0.51%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2373.458 | 2526.896 | +153.438 ns (+6.46%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 4960.000 | 4960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.readNs | 25.200 | 25.196 | -0.004 ns (-0.02%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2168.000 | 2168.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 417.600 | 281.133 | -136.467 ns (-32.68%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 6057.817 | 6079.742 | +21.925 ns (+0.36%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2379.062 | 2531.125 | +152.063 ns (+6.39%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 26.533 | 26.296 | -0.238 ns (-0.90%) | 0 | within noise |
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
| - | - | cpython-3.13/nullable | compact.callNs | 1309.339 | 1361.179 | +51.840 ns (+3.96%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 2307.494 | 2298.321 | -9.173 ns (-0.40%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.directWireNs | 5579.396 | 5515.459 | -63.937 ns (-1.15%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1830.562 | 1803.146 | -27.416 ns (-1.50%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionNs | 7539.375 | 7853.875 | +314.500 ns (+4.17%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | 2504.000 | 2504.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | 6016.996 | 6005.642 | -11.354 ns (-0.19%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | 2032.000 | 2032.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.readNs | 74.656 | 75.127 | +0.471 ns (+0.63%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 233.641 | 211.975 | -21.665 ns (-9.27%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 233.641 | 211.975 | -21.665 ns (-9.27%) | 0 | smaller |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 265.614 | 261.804 | -3.810 ns (-1.43%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5215.677 | 5431.612 | +215.935 ns (+4.14%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 855.125 | 868.333 | +13.208 ns (+1.54%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 22.127 | 20.717 | -1.410 ns (-6.37%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 165.896 | 214.400 | +48.505 ns (+29.24%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1191.208 | 1208.683 | +17.475 ns (+1.47%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 860.687 | 861.354 | +0.667 ns (+0.08%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 22.060 | 21.413 | -0.648 ns (-2.94%) | 0 | within noise |
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
| - | - | cpython-3.13/partial | compact.callNs | 1358.350 | 1345.192 | -13.158 ns (-0.97%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 2144.337 | 2149.287 | +4.950 ns (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.directWireNs | 4991.438 | 5017.396 | +25.958 ns (+0.52%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.dumpNs | 1857.750 | 1831.895 | -25.855 ns (-1.39%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 3432.000 | 3432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionNs | 6969.125 | 6946.229 | -22.896 ns (-0.33%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | 2416.000 | 2416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | 5394.842 | 5357.465 | -37.377 ns (-0.69%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | 2032.000 | 2032.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.readNs | 74.935 | 75.433 | +0.498 ns (+0.66%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 218.860 | 213.566 | -5.294 ns (-2.42%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 218.860 | 213.566 | -5.294 ns (-2.42%) | 0 | within noise |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 187.077 | 264.500 | +77.423 ns (+41.39%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 4991.819 | 5074.187 | +82.369 ns (+1.65%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.dumpNs | 891.167 | 867.417 | -23.750 ns (-2.67%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 24.321 | 21.052 | -3.269 ns (-13.44%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 191.492 | 203.019 | +11.527 ns (+6.02%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 945.946 | 951.440 | +5.494 ns (+0.58%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 868.479 | 886.667 | +18.188 ns (+2.09%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 22.933 | 21.596 | -1.337 ns (-5.83%) | 0 | smaller |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 1346.071 | 1284.673 | -61.398 ns (-4.56%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 2218.367 | 2229.744 | +11.377 ns (+0.51%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | 5783.750 | 5794.813 | +11.063 ns (+0.19%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1588.438 | 1591.000 | +2.562 ns (+0.16%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 3408.000 | 3408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | 7628.708 | 7573.729 | -54.979 ns (-0.72%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | 2776.000 | 2776.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | 5820.625 | 5794.523 | -26.102 ns (-0.45%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | 2304.000 | 2304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.readNs | 80.107 | 80.211 | +0.104 ns (+0.13%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 234.066 | 214.131 | -19.935 ns (-8.52%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 234.066 | 214.131 | -19.935 ns (-8.52%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 138.725 | 150.506 | +11.781 ns (+8.49%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4085.067 | 4170.160 | +85.094 ns (+2.08%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 786.792 | 794.625 | +7.833 ns (+1.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 23.863 | 23.931 | +0.068 ns (+0.29%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 196.121 | 190.210 | -5.911 ns (-3.01%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1057.004 | 1046.144 | -10.860 ns (-1.03%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 774.416 | 769.125 | -5.291 ns (-0.68%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 24.283 | 24.164 | -0.119 ns (-0.49%) | 0 | within noise |
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
| - | - | cpython-3.13/shallow | compact.callNs | 1392.777 | 1333.219 | -59.558 ns (-4.28%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 2077.452 | 2054.344 | -23.108 ns (-1.11%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.directWireNs | 7265.021 | 6941.729 | -323.292 ns (-4.45%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1399.542 | 1354.375 | -45.167 ns (-3.23%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 3384.000 | 3384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionNs | 8747.937 | 8690.083 | -57.855 ns (-0.66%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | 3358.000 | 3358.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | 430.000 | 430.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | 5370.629 | 5279.383 | -91.246 ns (-1.70%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | 2928.000 | 2928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.readNs | 88.635 | 88.714 | +0.078 ns (+0.09%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 209.616 | 204.991 | -4.625 ns (-2.21%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 209.616 | 204.991 | -4.625 ns (-2.21%) | 0 | within noise |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 147.133 | 188.856 | +41.723 ns (+28.36%) | 0 | larger |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2716.804 | 2789.769 | +72.965 ns (+2.69%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 715.209 | 700.834 | -14.375 ns (-2.01%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 25.276 | 25.375 | +0.099 ns (+0.39%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 214.562 | 175.575 | -38.987 ns (-18.17%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 785.979 | 781.092 | -4.888 ns (-0.62%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 718.188 | 714.250 | -3.938 ns (-0.55%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 26.338 | 25.943 | -0.396 ns (-1.50%) | 0 | within noise |
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
| - | - | cpython-3.13/warmed | compact.callNs | 1586.575 | 1586.002 | -0.573 ns (-0.04%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 4130.592 | 4176.831 | +46.240 ns (+1.12%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1737.125 | 1718.479 | -18.645 ns (-1.07%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 3384.000 | 3384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.readNs | 87.688 | 91.828 | +4.141 ns (+4.72%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 240.703 | 245.993 | +5.290 ns (+2.20%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.transientBytes | 2578.000 | 2578.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 240.703 | 245.993 | +5.290 ns (+2.20%) | 0 | within noise |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 153.585 | 85.595 | -67.990 ns (-44.27%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 3772.644 | 3910.550 | +137.906 ns (+3.66%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 707.937 | 711.521 | +3.584 ns (+0.51%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 25.859 | 25.302 | -0.557 ns (-2.16%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 169.441 | 190.673 | +21.232 ns (+12.53%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1701.954 | 1759.035 | +57.081 ns (+3.35%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 704.771 | 716.437 | +11.666 ns (+1.66%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 26.630 | 25.870 | -0.761 ns (-2.86%) | 0 | within noise |
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
| - | - | cpython-3.13/wide | compact.callNs | 1364.521 | 1382.158 | +17.638 ns (+1.29%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 2637.167 | 2612.904 | -24.263 ns (-0.92%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.directWireNs | 6880.459 | 6881.542 | +1.083 ns (+0.02%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.dumpNs | 2417.041 | 2407.542 | -9.500 ns (-0.39%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 3512.000 | 3512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionNs | 9253.855 | 9286.730 | +32.875 ns (+0.36%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | 3240.000 | 3240.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | 664.000 | 664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | 7309.587 | 7323.435 | +13.848 ns (+0.19%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | 2576.000 | 2576.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.readNs | 82.273 | 79.258 | -3.016 ns (-3.67%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 196.700 | 216.351 | +19.651 ns (+9.99%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 196.700 | 216.351 | +19.651 ns (+9.99%) | 0 | larger |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 30.806 | 210.731 | +179.925 ns (+584.06%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 7771.485 | 7945.623 | +174.138 ns (+2.24%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1184.459 | 1187.958 | +3.500 ns (+0.30%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 24.100 | 22.345 | -1.755 ns (-7.28%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 219.250 | 167.508 | -51.742 ns (-23.60%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1775.417 | 1754.929 | -20.487 ns (-1.15%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1126.312 | 1145.666 | +19.354 ns (+1.72%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 23.921 | 22.819 | -1.102 ns (-4.61%) | 0 | smaller |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.320 | 3.170 | -0.150 ratio (-4.51%) | 0 | smaller |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.320 | 3.170 | -0.150 ratio (-4.51%) | 0 | smaller |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.284 | 3.132 | -0.152 ratio (-4.63%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 0.508 | 0.493 | -0.015 ratio (-3.00%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.likeForLike | 0.488 | 0.474 | -0.014 ratio (-2.85%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 1.473 | 1.478 | +0.005 ratio (+0.34%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.151 | 2.148 | -0.003 ratio (-0.15%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.151 | 2.148 | -0.003 ratio (-0.15%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.186 | 2.156 | -0.031 ratio (-1.40%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 1597.398 | 1612.133 | +14.735 ns (+0.92%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 6653.790 | 6584.346 | -69.444 ns (-1.04%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.directWireNs | 11388.479 | 11369.937 | -18.541 ns (-0.16%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.dumpNs | 6027.395 | 6112.042 | +84.647 ns (+1.40%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 5034.000 | 5034.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionNs | 15389.229 | 15238.083 | -151.146 ns (-0.98%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | 8450.000 | 8450.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | 1248.000 | 1248.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | 13335.406 | 13305.879 | -29.527 ns (-0.22%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | 7202.000 | 7202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.readNs | 85.679 | 85.400 | -0.279 ns (-0.33%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 317.822 | 299.568 | -18.254 ns (-5.74%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 3802.000 | 3802.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 317.822 | 299.568 | -18.254 ns (-5.74%) | 0 | smaller |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 97.054 | 286.002 | +188.948 ns (+194.68%) | 0 | larger |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 10885.092 | 11036.498 | +151.406 ns (+1.39%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.dumpNs | 2543.729 | 2614.709 | +70.979 ns (+2.79%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5184.000 | 5184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.readNs | 26.342 | 26.550 | +0.208 ns (+0.79%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2264.000 | 2264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 238.071 | 237.058 | -1.012 ns (-0.43%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 6299.804 | 6220.192 | -79.613 ns (-1.26%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 2465.104 | 2616.834 | +151.730 ns (+6.16%) | 0 | larger |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4744.000 | 4744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 25.688 | 26.600 | +0.912 ns (+3.55%) | 0 | larger |
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
| - | - | cpython-3.14/nullable | compact.callNs | 1387.052 | 1495.450 | +108.398 ns (+7.81%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 2320.427 | 2282.300 | -38.127 ns (-1.64%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.directWireNs | 5765.604 | 5842.479 | +76.875 ns (+1.33%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.dumpNs | 1813.438 | 1866.854 | +53.417 ns (+2.95%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 3672.000 | 3672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionNs | 8073.063 | 8009.479 | -63.583 ns (-0.79%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | 2736.000 | 2736.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | 480.000 | 480.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | 6529.865 | 6510.885 | -18.979 ns (-0.29%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | 2256.000 | 2256.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.readNs | 78.273 | 78.090 | -0.183 ns (-0.23%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 233.380 | 207.017 | -26.364 ns (-11.30%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 233.380 | 207.017 | -26.364 ns (-11.30%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 136.987 | 228.417 | +91.429 ns (+66.74%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 5262.117 | 5485.271 | +223.154 ns (+4.24%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 888.250 | 919.938 | +31.688 ns (+3.57%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 24.467 | 23.906 | -0.560 ns (-2.29%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 198.346 | 199.567 | +1.221 ns (+0.62%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1237.029 | 1269.329 | +32.300 ns (+2.61%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 897.979 | 902.437 | +4.458 ns (+0.50%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 24.223 | 25.490 | +1.267 ns (+5.23%) | 0 | larger |
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
| - | - | cpython-3.14/partial | compact.callNs | 1426.656 | 1393.679 | -32.977 ns (-2.31%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 2156.552 | 2160.925 | +4.373 ns (+0.20%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.directWireNs | 5136.313 | 5146.896 | +10.583 ns (+0.21%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.dumpNs | 1857.896 | 1856.479 | -1.417 ns (-0.08%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 3576.000 | 3576.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionNs | 7203.854 | 7238.375 | +34.521 ns (+0.48%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | 2616.000 | 2616.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | 392.000 | 392.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | 5734.333 | 5729.500 | -4.833 ns (-0.08%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | 2224.000 | 2224.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.readNs | 79.108 | 78.333 | -0.775 ns (-0.98%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 214.278 | 225.827 | +11.549 ns (+5.39%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 214.278 | 225.827 | +11.549 ns (+5.39%) | 0 | larger |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 181.619 | 203.819 | +22.200 ns (+12.22%) | 0 | larger |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 4941.298 | 5016.285 | +74.987 ns (+1.52%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.dumpNs | 901.000 | 906.021 | +5.021 ns (+0.56%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 22.660 | 23.579 | +0.919 ns (+4.05%) | 0 | larger |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 230.394 | 207.912 | -22.482 ns (-9.76%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 1001.648 | 956.233 | -45.415 ns (-4.53%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 899.250 | 886.021 | -13.229 ns (-1.47%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 24.969 | 24.787 | -0.181 ns (-0.73%) | 0 | within noise |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 1421.756 | 1412.710 | -9.046 ns (-0.64%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 2213.744 | 2200.894 | -12.850 ns (-0.58%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | 5840.730 | 5838.000 | -2.729 ns (-0.05%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1695.812 | 1663.354 | -32.458 ns (-1.91%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 3552.000 | 3552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | 8177.750 | 7873.729 | -304.021 ns (-3.72%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | 2984.000 | 2984.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | 480.000 | 480.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | 6253.440 | 6209.098 | -44.342 ns (-0.71%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | 2504.000 | 2504.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.readNs | 86.920 | 80.229 | -6.691 ns (-7.70%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 219.298 | 229.962 | +10.664 ns (+4.86%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 219.298 | 229.962 | +10.664 ns (+4.86%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 208.482 | 208.190 | -0.292 ns (-0.14%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4029.248 | 4026.873 | -2.375 ns (-0.06%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 824.750 | 800.416 | -24.333 ns (-2.95%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 27.179 | 26.458 | -0.720 ns (-2.65%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 197.971 | 189.569 | -8.402 ns (-4.24%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1119.071 | 1095.723 | -23.348 ns (-2.09%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 826.666 | 799.375 | -27.291 ns (-3.30%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 26.559 | 25.988 | -0.571 ns (-2.15%) | 0 | within noise |
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
| - | - | cpython-3.14/shallow | compact.callNs | 1442.716 | 1412.962 | -29.754 ns (-2.06%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 2091.679 | 2106.996 | +15.317 ns (+0.73%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.directWireNs | 7253.563 | 7209.312 | -44.250 ns (-0.61%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1402.125 | 1423.708 | +21.583 ns (+1.54%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 3528.000 | 3528.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionNs | 9067.604 | 9139.458 | +71.854 ns (+0.79%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | 3662.000 | 3662.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | 438.000 | 438.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | 5764.892 | 5694.348 | -70.544 ns (-1.22%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | 3224.000 | 3224.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.readNs | 88.974 | 87.552 | -1.422 ns (-1.60%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 217.524 | 211.997 | -5.526 ns (-2.54%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 217.524 | 211.997 | -5.526 ns (-2.54%) | 0 | within noise |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 203.252 | 180.077 | -23.175 ns (-11.40%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 2762.873 | 2839.360 | +76.487 ns (+2.77%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 731.792 | 735.291 | +3.500 ns (+0.48%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 27.057 | 28.766 | +1.708 ns (+6.31%) | 0 | larger |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 208.529 | 204.050 | -4.480 ns (-2.15%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 819.763 | 810.783 | -8.979 ns (-1.10%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 719.104 | 744.417 | +25.312 ns (+3.52%) | 0 | larger |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 27.661 | 28.047 | +0.385 ns (+1.39%) | 0 | within noise |
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
| - | - | cpython-3.14/warmed | compact.callNs | 1519.006 | 1688.460 | +169.454 ns (+11.16%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 4263.015 | 4229.227 | -33.788 ns (-0.79%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1785.625 | 1742.666 | -42.958 ns (-2.41%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 3528.000 | 3528.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.readNs | 88.958 | 89.443 | +0.484 ns (+0.54%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 268.272 | 233.228 | -35.045 ns (-13.06%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.transientBytes | 2690.000 | 2690.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 268.272 | 233.228 | -35.045 ns (-13.06%) | 0 | smaller |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 132.360 | 145.202 | +12.842 ns (+9.70%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 3897.015 | 3949.131 | +52.117 ns (+1.34%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 751.042 | 734.000 | -17.042 ns (-2.27%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 28.438 | 28.370 | -0.068 ns (-0.24%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 205.705 | 211.746 | +6.041 ns (+2.94%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1755.837 | 1787.546 | +31.708 ns (+1.81%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 731.875 | 722.416 | -9.459 ns (-1.29%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 30.641 | 28.609 | -2.031 ns (-6.63%) | 0 | smaller |
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
| - | - | cpython-3.14/wide | compact.callNs | 1485.202 | 1450.754 | -34.448 ns (-2.32%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 2531.902 | 2547.913 | +16.010 ns (+0.63%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.directWireNs | 7024.791 | 6998.604 | -26.187 ns (-0.37%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.dumpNs | 2403.625 | 2421.084 | +17.459 ns (+0.73%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 3720.000 | 3720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionNs | 9818.000 | 9612.125 | -205.875 ns (-2.10%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | 3488.000 | 3488.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | 7855.685 | 7785.492 | -70.194 ns (-0.89%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | 2816.000 | 2816.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.readNs | 82.836 | 80.668 | -2.168 ns (-2.62%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 219.275 | 227.277 | +8.003 ns (+3.65%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 219.275 | 227.277 | +8.003 ns (+3.65%) | 0 | larger |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 220.702 | 204.417 | -16.285 ns (-7.38%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 7487.965 | 7885.833 | +397.869 ns (+5.31%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1177.687 | 1168.229 | -9.458 ns (-0.80%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 23.443 | 25.401 | +1.958 ns (+8.35%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 253.521 | 171.269 | -82.252 ns (-32.44%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 1719.229 | 1745.148 | +25.919 ns (+1.51%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1144.000 | 1168.230 | +24.229 ns (+2.12%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 23.717 | 25.645 | +1.927 ns (+8.13%) | 0 | larger |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.263 | 3.299 | +0.036 us/event (+1.09%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 3.726 | 3.698 | -0.028 us/event (-0.76%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.271 | 0.271 | +0.000 ratio (+0.01%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.021 | 0.021 | +0.000 ratio (+1.01%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.068 | 0.069 | +0.001 ratio (+0.82%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.004 | 0.005 | +0.000 ratio (+1.08%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.170 | 0.171 | +0.001 ratio (+0.41%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p50 | 428.584 | 433.208 | +4.624 us (+1.08%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p95 | 445.500 | 444.875 | -0.625 us (-0.14%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 91.375 | 92.375 | +1.000 us (+1.09%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 104.334 | 103.542 | -0.792 us (-0.76%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.271 | 0.271 | +0.000 ratio (+0.08%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.309 | 0.304 | -0.005 ratio (-1.57%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | plain.p50 | 337.167 | 340.833 | +3.666 us (+1.09%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | plain.p95 | 350.958 | 349.416 | -1.542 us (-0.44%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.271 | 0.271 | -0.000 ratio (-0.04%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.269 | 0.273 | +0.004 ratio (+1.42%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.341 | 2.375 | +0.034 us/event (+1.46%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 2.832 | 2.696 | -0.135 us/event (-4.78%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.195 | 0.196 | +0.001 ratio (+0.39%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.015 | 0.015 | +0.000 ratio (+1.38%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.049 | 0.050 | +0.001 ratio (+1.19%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | +0.000 ratio (+1.44%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.122 | 0.123 | +0.001 ratio (+0.79%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p50 | 401.917 | 406.375 | +4.458 us (+1.11%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p95 | 420.750 | 417.791 | -2.959 us (-0.70%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 65.542 | 66.500 | +0.958 us (+1.46%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 79.291 | 75.500 | -3.791 us (-4.78%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.195 | 0.196 | +0.001 ratio (+0.35%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.235 | 0.221 | -0.014 ratio (-6.01%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | plain.p50 | 336.250 | 339.833 | +3.583 us (+1.07%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | plain.p95 | 350.958 | 348.750 | -2.208 us (-0.63%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.195 | 0.196 | +0.001 ratio (+0.26%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.199 | 0.198 | -0.001 ratio (-0.45%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 3.990 | 3.988 | -0.001 us/event (-0.04%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.973 | 4.429 | -0.545 us/event (-10.95%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.330 | 0.327 | -0.002 ratio (-0.68%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.026 | 0.026 | -0.000 ratio (-0.09%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.083 | 0.083 | -0.000 ratio (-0.20%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-0.05%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.207 | 0.206 | -0.001 ratio (-0.44%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | observed.p50 | 450.750 | 453.000 | +2.250 us (+0.50%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | observed.p95 | 479.333 | 466.417 | -12.916 us (-2.69%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 111.708 | 111.667 | -0.041 us (-0.04%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 139.250 | 124.000 | -15.250 us (-10.95%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.330 | 0.327 | -0.002 ratio (-0.71%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.406 | 0.365 | -0.042 ratio (-10.25%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | plain.p50 | 338.958 | 341.166 | +2.208 us (+0.65%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | plain.p95 | 352.375 | 347.708 | -4.667 us (-1.32%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.330 | 0.328 | -0.002 ratio (-0.61%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.360 | 0.341 | -0.019 ratio (-5.24%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 3.807 | 3.830 | +0.024 us/event (+0.63%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 4.613 | 4.476 | -0.137 us/event (-2.97%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.314 | 0.314 | -0.000 ratio (-0.12%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.025 | 0.025 | +0.000 ratio (+0.57%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.080 | 0.080 | +0.000 ratio (+0.44%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.005 | 0.005 | +0.000 ratio (+0.61%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.198 | 0.198 | +0.000 ratio (+0.15%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 445.584 | 448.459 | +2.875 us (+0.65%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 473.917 | 471.625 | -2.292 us (-0.48%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 106.583 | 107.250 | +0.667 us (+0.63%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 129.166 | 125.334 | -3.832 us (-2.97%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.315 | 0.315 | -0.000 ratio (-0.13%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.377 | 0.364 | -0.012 ratio (-3.31%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 339.042 | 341.583 | +2.541 us (+0.75%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 353.916 | 348.166 | -5.750 us (-1.62%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.314 | 0.313 | -0.001 ratio (-0.43%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.339 | 0.355 | +0.016 ratio (+4.58%) | 0 | larger |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.435 | 1.442 | +0.007 us/event (+0.52%) | 0 | within noise |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 1.998 | 1.757 | -0.241 us/event (-12.06%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.120 | 0.119 | -0.001 ratio (-0.44%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.009 | 0.009 | +0.000 ratio (+0.44%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.030 | 0.030 | +0.000 ratio (+0.27%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | +0.000 ratio (+0.50%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.075 | 0.075 | -0.000 ratio (-0.09%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p50 | 376.375 | 379.959 | +3.584 us (+0.95%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p95 | 396.459 | 389.875 | -6.584 us (-1.66%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 40.167 | 40.375 | +0.208 us (+0.52%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 55.958 | 49.208 | -6.750 us (-12.06%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.120 | 0.119 | -0.001 ratio (-0.60%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.166 | 0.145 | -0.022 ratio (-12.97%) | 0 | smaller |
| - | - | one Handler that keeps nothing | plain.p50 | 336.125 | 339.375 | +3.250 us (+0.97%) | 0 | within noise |
| - | - | one Handler that keeps nothing | plain.p95 | 355.125 | 347.291 | -7.834 us (-2.21%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.120 | 0.120 | -0.000 ratio (-0.14%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.116 | 0.123 | +0.006 ratio (+5.35%) | 0 | larger |
| - | - | workload | events | 28.000 | 28.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | workload | statements | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |

## snapshot-delivery

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 10118.791 | 10138.708 | +19.917 us (+0.20%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1450.010 | 1450.010 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 693.328 | 693.328 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 100875.375 | 108094.083 | +7218.708 us (+7.16%) | 9 | slower |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 12653.846 | 12653.846 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 6931.836 | 6931.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 20897.416 | 16391.250 | -4506.166 us (-21.56%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 445.783 | 445.783 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.458 | 3.458 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 117012.542 | 112916.791 | -4095.751 us (-3.50%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 822.721 | 822.721 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.489 | 3.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8355.667 | 8400.375 | +44.708 us (+0.54%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1250.123 | 1250.123 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 477.848 | 477.848 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 83704.458 | 82689.917 | -1014.541 us (-1.21%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11112.811 | 11112.811 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4775.730 | 4775.730 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 19543.125 | 14724.625 | -4818.500 us (-24.66%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 392.021 | 392.021 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.524 | 2.524 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 101946.125 | 97425.000 | -4521.125 us (-4.43%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 821.428 | 821.428 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.556 | 2.556 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 18218.583 | 18118.292 | -100.291 us (-0.55%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1352.424 | 1352.424 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 708.953 | 708.953 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 181144.667 | 181561.375 | +416.708 us (+0.23%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12299.947 | 12299.947 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7088.086 | 7088.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 28165.292 | 23970.166 | -4195.126 us (-14.89%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 568.674 | 568.674 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.536 | 3.536 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 191903.042 | 184055.375 | -7847.667 us (-4.09%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 985.643 | 985.643 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.567 | 3.567 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 16167.042 | 16157.750 | -9.292 us (-0.06%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1199.549 | 1199.549 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 501.285 | 501.285 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 160817.625 | 157777.041 | -3040.584 us (-1.89%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12300.377 | 12300.377 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5010.105 | 5010.105 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 26131.958 | 21807.291 | -4324.667 us (-16.55%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 533.678 | 533.678 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.642 | 2.642 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 171902.042 | 166378.958 | -5523.084 us (-3.21%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 982.014 | 982.014 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.673 | 2.673 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6047.917 | 6079.666 | +31.749 us (+0.52%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 476.559 | 476.559 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 227.253 | 227.253 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 845.875 | 842.167 | -3.708 us (-0.44%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 72.854 | 72.854 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 28.146 | 28.146 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4493.291 | 4487.167 | -6.124 us (-0.14%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 410.364 | 410.364 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 186.823 | 186.823 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 671.333 | 668.125 | -3.208 us (-0.48%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 65.379 | 65.379 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.200 | 23.200 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8757.458 | 8657.667 | -99.791 us (-1.14%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 606.505 | 606.505 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 293.815 | 293.815 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1242.166 | 1229.625 | -12.541 us (-1.01%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 92.004 | 92.004 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 36.802 | 36.802 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6888.417 | 6805.541 | -82.876 us (-1.20%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 550.426 | 550.426 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 257.698 | 257.698 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 995.458 | 1009.125 | +13.667 us (+1.37%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 86.378 | 86.378 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.388 | 32.388 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10797.917 | 10743.458 | -54.459 us (-0.50%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 765.693 | 765.693 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 384.511 | 384.511 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1607.625 | 1517.166 | -90.459 us (-5.63%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 113.556 | 113.556 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 48.544 | 48.544 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8466.167 | 8440.291 | -25.876 us (-0.31%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 703.224 | 703.224 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 333.909 | 333.909 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1262.500 | 1257.042 | -5.458 us (-0.43%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 106.775 | 106.775 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.247 | 42.247 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 434.381 | 433.007 | -1.374 KiB (-0.32%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 295.456 | 295.412 | -0.044 KiB (-0.01%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.557 | 0.501 | -0.055 ms (-9.92%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.810 | 0.736 | -0.074 ms (-9.12%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 5.037 | 5.085 | +0.048 ms (+0.96%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 39189.752 | 39309.466 | +119.714 roots/s (+0.31%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 5.550 | 5.561 | +0.011 ms (+0.20%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 36620.533 | 36340.511 | -280.022 roots/s (-0.76%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 8.106 | 7.376 | -0.730 ms (-9.00%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 25150.773 | 24922.507 | -228.266 roots/s (-0.91%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 231.412 | 232.833 | +1.421 KiB (+0.61%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 45.315 | 43.103 | -2.213 KiB (-4.88%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 85.505 | 86.093 | +0.588 KiB (+0.69%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 10.883 | 12.164 | +1.281 KiB (+11.77%) | 6 | larger |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1289.925 | 1289.925 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.973 | 521.973 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.728 | 0.673 | -0.055 ms (-7.57%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.043 | 1.086 | +0.043 ms (+4.08%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 8.686 | 8.610 | -0.076 ms (-0.88%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23203.202 | 23401.622 | +198.420 roots/s (+0.86%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 9.410 | 9.393 | -0.017 ms (-0.18%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 21264.154 | 21562.663 | +298.510 roots/s (+1.40%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 12.187 | 12.608 | +0.421 ms (+3.45%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 16571.096 | 16483.969 | -87.126 roots/s (-0.53%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 705.499 | 705.499 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 31.946 | 31.946 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 199.487 | 199.487 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.491 | 3.491 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1717.600 | 1717.554 | -0.046 KiB (-0.00%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.690 | 869.741 | +0.051 KiB (+0.01%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.878 | 0.837 | -0.040 ms (-4.61%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.208 | 2.165 | -0.043 ms (-1.95%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 23.411 | 23.432 | +0.021 ms (+0.09%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 8490.962 | 8618.554 | +127.592 roots/s (+1.50%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 24.175 | 23.894 | -0.281 ms (-1.16%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8296.388 | 8302.401 | +6.013 roots/s (+0.07%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 27.044 | 26.905 | -0.139 ms (-0.51%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 7383.502 | 7409.225 | +25.723 roots/s (+0.35%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1143.415 | 1143.466 | +0.051 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 57.243 | 60.523 | +3.280 KiB (+5.73%) | 6 | larger |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 307.840 | 307.846 | +0.006 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 6.164 | 6.146 | -0.019 KiB (-0.30%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1280.452 | 1280.452 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 545.004 | 545.004 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.848 | 0.879 | +0.031 ms (+3.68%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.513 | 1.544 | +0.031 ms (+2.07%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 16.584 | 16.227 | -0.357 ms (-2.16%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 12235.066 | 11783.768 | -451.298 roots/s (-3.69%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 16.216 | 15.961 | -0.255 ms (-1.57%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12351.938 | 12528.973 | +177.035 roots/s (+1.43%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 19.307 | 19.033 | -0.274 ms (-1.42%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10478.221 | 10524.862 | +46.640 roots/s (+0.45%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1139.675 | 1139.675 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 40.712 | 40.712 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 313.190 | 313.190 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 3.812 | 3.812 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 302.880 | 302.834 | -0.046 KiB (-0.02%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.809 | 171.809 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.490 | 0.400 | -0.090 ms (-18.35%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.725 | 0.649 | -0.076 ms (-10.45%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.342 | 5.244 | -0.098 ms (-1.84%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 36814.338 | 37934.166 | +1119.828 roots/s (+3.04%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 5.921 | 5.654 | -0.268 ms (-4.52%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 33828.784 | 34824.246 | +995.462 roots/s (+2.94%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 8.434 | 7.850 | -0.584 ms (-6.92%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 24077.167 | 25260.499 | +1183.332 roots/s (+4.91%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 193.528 | 193.528 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 27.891 | 35.106 | +7.216 KiB (+25.87%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 69.677 | 69.660 | -0.017 KiB (-0.02%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 1.921 | 1.926 | +0.005 KiB (+0.25%) | 6 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.222 | 6.345 | +0.123 us/projection (+1.98%) | 9 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 161803.707 | 163143.780 | +1340.073 projections/s (+0.83%) | 9 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.348 | 43.348 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 47.183 | 47.183 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 566.688 | 566.688 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 126.875 | 126.875 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.398 | 7.347 | -0.051 us/projection (-0.69%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 133425.897 | 136618.440 | +3192.544 projections/s (+2.39%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 47.434 | 47.434 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 61.369 | 61.369 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 581.688 | 581.688 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 177.250 | 177.250 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.701 | 8.678 | -0.023 ms (-0.26%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 22735.778 | 23049.109 | +313.331 roots/s (+1.38%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.740 | 9.614 | -0.127 ms (-1.30%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20701.077 | 20635.397 | -65.680 roots/s (-0.32%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.881 | 16.535 | -0.346 ms (-2.05%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 12089.919 | 12126.296 | +36.377 roots/s (+0.30%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 16.878 | 16.678 | -0.200 ms (-1.19%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 11744.872 | 11932.343 | +187.471 roots/s (+1.60%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 32.358 | 32.525 | +0.167 us/root (+0.52%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 99.004 | 99.004 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.852 | 50.852 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 34.210 | 32.776 | -1.434 us/root (-4.19%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 103.316 | 103.316 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.852 | 50.852 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 47.181 | 47.617 | +0.436 us/root (+0.92%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 147.043 | 147.043 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.977 | 87.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 48.129 | 47.147 | -0.982 us/root (-2.04%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 150.992 | 150.992 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.977 | 87.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 65.573 | 65.646 | +0.073 us/root (+0.11%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 218.461 | 218.461 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.477 | 137.477 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 66.971 | 67.285 | +0.314 us/root (+0.47%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 221.883 | 221.883 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.477 | 137.477 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 24.328 | 24.202 | -0.126 us/root (-0.52%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 62.293 | 62.293 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.102 | 24.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 24.643 | 24.853 | +0.210 us/root (+0.85%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 68.605 | 68.605 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.102 | 24.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 152.691 | 152.355 | -0.336 us/root (-0.22%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 625.758 | 625.758 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.102 | 428.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 151.609 | 151.146 | -0.464 us/root (-0.31%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 629.699 | 629.699 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.102 | 428.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 57.185 | 56.049 | -1.135 us/root (-1.99%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 195.082 | 195.082 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.102 | 125.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 56.809 | 56.990 | +0.181 us/root (+0.32%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 198.129 | 198.129 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.102 | 125.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 46.348 | 47.100 | +0.753 us/root (+1.62%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 128.688 | 128.688 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.945 | 35.945 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 47.410 | 47.395 | -0.016 us/root (-0.03%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 133.001 | 133.001 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.945 | 35.945 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 55.465 | 55.443 | -0.022 us/root (-0.04%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 219.008 | 219.008 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.727 | 136.727 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 56.281 | 54.898 | -1.383 us/root (-2.46%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 222.836 | 222.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.727 | 136.727 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 143.681 | 144.585 | +0.904 us/root (+0.63%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 761.578 | 761.578 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.227 | 480.227 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 145.512 | 143.919 | -1.592 us/root (-1.09%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 765.406 | 765.406 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.227 | 480.227 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 253.125 | 249.625 | -3.500 us (-1.38%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 37.383 | 37.383 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 28.672 | 28.672 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 366.959 | 374.958 | +7.999 us (+2.18%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 50.452 | 50.452 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 40.022 | 40.022 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 488.292 | 486.208 | -2.084 us (-0.43%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 62.865 | 62.865 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 50.850 | 50.850 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 89.500 | 90.541 | +1.041 us (+1.16%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 20.526 | 20.526 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 13.761 | 13.761 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 89.542 | 91.917 | +2.375 us (+2.65%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 20.432 | 20.428 | -0.004 KiB (-0.02%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 13.916 | 13.912 | -0.004 KiB (-0.03%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 87.875 | 90.875 | +3.000 us (+3.41%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 20.526 | 20.526 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 13.761 | 13.761 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 90.208 | 91.875 | +1.667 us (+1.85%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 20.432 | 20.432 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 13.916 | 13.916 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 90.666 | 91.166 | +0.500 us (+0.55%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 20.527 | 20.527 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 13.762 | 13.762 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 91.292 | 91.916 | +0.624 us (+0.68%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 20.433 | 20.433 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 13.917 | 13.917 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 11.333 | 11.583 | +0.250 us (+2.21%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 15.625 | 16.042 | +0.417 us (+2.67%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 19.958 | 20.125 | +0.167 us (+0.84%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.closed.retainedKiB | 71.484 | 71.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.shared.retainedKiB | 50.789 | 50.789 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | small.closed.retainedKiB | 118.438 | 118.438 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | small.shared.retainedKiB | 111.070 | 111.070 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 10078.291 | 10004.125 | -74.166 us (-0.74%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1353.777 | 1353.777 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 741.773 | 741.773 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 102325.083 | 101223.208 | -1101.875 us (-1.08%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 13108.117 | 13108.117 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 7416.219 | 7416.219 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 22166.000 | 17346.250 | -4819.750 us (-21.74%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 176.418 | 176.418 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.700 | 3.700 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 118863.334 | 113887.958 | -4975.376 us (-4.19%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 181.324 | 181.324 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.731 | 3.731 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8574.208 | 8462.625 | -111.583 us (-1.30%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1183.411 | 1183.411 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 487.230 | 487.230 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 84907.166 | 84571.125 | -336.041 us (-0.40%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11348.603 | 11348.603 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4869.488 | 4869.488 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 20663.500 | 15562.208 | -5101.292 us (-24.69%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 178.630 | 178.630 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.571 | 2.571 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 104313.167 | 99169.875 | -5143.292 us (-4.93%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 180.536 | 180.536 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.603 | 2.603 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 18634.375 | 18556.083 | -78.292 us (-0.42%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1297.602 | 1297.602 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 758.961 | 758.961 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 186578.541 | 207415.542 | +20837.001 us (+11.17%) | 9 | slower |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12963.753 | 12963.753 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7588.094 | 7588.094 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 30258.750 | 24813.625 | -5445.125 us (-18.00%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 283.668 | 283.668 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.786 | 3.786 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 196406.625 | 190624.875 | -5781.750 us (-2.94%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 287.590 | 287.590 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.817 | 3.817 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 16756.292 | 16610.000 | -146.292 us (-0.87%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1265.931 | 1265.931 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 510.668 | 510.668 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 164455.250 | 162377.625 | -2077.625 us (-1.26%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12964.446 | 12964.446 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5103.863 | 5103.863 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 27902.750 | 23036.500 | -4866.250 us (-17.44%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 282.653 | 282.653 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.688 | 2.688 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 179903.500 | 182174.500 | +2271.000 us (+1.26%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 284.216 | 284.216 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.720 | 2.720 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6034.583 | 6005.834 | -28.749 us (-0.48%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 402.667 | 402.667 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 245.097 | 245.097 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 870.084 | 872.750 | +2.666 us (+0.31%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 70.104 | 70.104 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 34.177 | 34.177 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4499.875 | 4434.542 | -65.333 us (-1.45%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 360.000 | 360.000 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 190.003 | 190.003 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 693.583 | 686.625 | -6.958 us (-1.00%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 61.960 | 61.960 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.606 | 23.606 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8947.042 | 9140.709 | +193.667 us (+2.16%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 531.295 | 531.295 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 317.237 | 317.237 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1324.541 | 1257.083 | -67.458 us (-5.09%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 86.798 | 86.798 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 42.489 | 42.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6811.833 | 6693.625 | -118.208 us (-1.74%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 496.995 | 496.995 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 261.722 | 261.722 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 1031.750 | 1022.334 | -9.416 us (-0.91%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 81.553 | 81.553 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.903 | 32.903 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 11008.375 | 10976.500 | -31.875 us (-0.29%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 686.104 | 686.104 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 415.769 | 415.769 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1576.167 | 1571.542 | -4.625 us (-0.29%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 106.569 | 106.569 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 54.958 | 54.958 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8692.333 | 8555.167 | -137.166 us (-1.58%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 638.780 | 638.780 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 339.104 | 339.104 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1307.042 | 1277.084 | -29.958 us (-2.29%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 100.372 | 100.372 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.911 | 42.911 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 386.686 | 395.411 | +8.726 KiB (+2.26%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 299.688 | 298.570 | -1.118 KiB (-0.37%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.523 | 0.530 | +0.007 ms (+1.29%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.811 | 0.765 | -0.046 ms (-5.64%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 5.163 | 5.138 | -0.025 ms (-0.49%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 39521.786 | 37022.756 | -2499.031 roots/s (-6.32%) | 9 | slower |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 5.715 | 5.619 | -0.096 ms (-1.68%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 35831.320 | 36076.663 | +245.343 roots/s (+0.68%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 8.106 | 8.085 | -0.021 ms (-0.26%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 24774.963 | 25413.500 | +638.537 roots/s (+2.58%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 214.543 | 214.200 | -0.343 KiB (-0.16%) | 6 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 40.480 | 43.921 | +3.440 KiB (+8.50%) | 6 | larger |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 77.941 | 76.287 | -1.654 KiB (-2.12%) | 6 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 15.609 | 12.428 | -3.182 KiB (-20.38%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1224.021 | 1224.021 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.383 | 531.383 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.743 | 0.667 | -0.077 ms (-10.34%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.116 | 0.994 | -0.122 ms (-10.92%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 8.673 | 8.815 | +0.143 ms (+1.64%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 22885.586 | 22775.152 | -110.434 roots/s (-0.48%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 9.525 | 9.254 | -0.271 ms (-2.84%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 21040.913 | 21608.773 | +567.860 roots/s (+2.70%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 12.411 | 11.920 | -0.492 ms (-3.96%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 15829.411 | 17235.311 | +1405.900 roots/s (+8.88%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 667.924 | 667.924 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 34.473 | 34.473 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 191.596 | 191.596 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.597 | 3.597 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1770.636 | 1770.685 | +0.049 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.759 | 883.711 | -0.048 KiB (-0.01%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.856 | 0.799 | -0.057 ms (-6.64%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.203 | 2.199 | -0.004 ms (-0.16%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 23.307 | 23.432 | +0.126 ms (+0.54%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 8507.848 | 8510.126 | +2.278 roots/s (+0.03%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 24.139 | 24.274 | +0.135 ms (+0.56%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8232.344 | 8211.445 | -20.899 roots/s (-0.25%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 27.603 | 27.605 | +0.002 ms (+0.01%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 7312.481 | 7359.852 | +47.372 roots/s (+0.65%) | 9 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1177.754 | 1177.861 | +0.107 KiB (+0.01%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 58.687 | 59.062 | +0.375 KiB (+0.64%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 317.093 | 317.229 | +0.136 KiB (+0.04%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 6.336 | 6.274 | -0.062 KiB (-0.97%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1347.291 | 1347.291 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.414 | 554.414 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.857 | 0.727 | -0.130 ms (-15.16%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.610 | 1.515 | -0.094 ms (-5.84%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 16.680 | 17.473 | +0.794 ms (+4.76%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 11941.249 | 11458.555 | -482.694 roots/s (-4.04%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 17.392 | 16.913 | -0.479 ms (-2.76%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12470.026 | 11767.042 | -702.984 roots/s (-5.64%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 19.528 | 19.365 | -0.163 ms (-0.84%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10288.308 | 10242.666 | -45.642 roots/s (-0.44%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1145.486 | 1145.486 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 43.727 | 43.727 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 307.869 | 307.869 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 3.948 | 3.948 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 278.097 | 278.097 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 174.946 | 175.000 | +0.054 KiB (+0.03%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.491 | 0.526 | +0.034 ms (+6.99%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.722 | 0.776 | +0.054 ms (+7.44%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 5.518 | 5.423 | -0.095 ms (-1.72%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 36853.622 | 34188.034 | -2665.588 roots/s (-7.23%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 5.947 | 6.576 | +0.628 ms (+10.56%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 33536.413 | 31431.917 | -2104.496 roots/s (-6.28%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 8.635 | 9.395 | +0.760 ms (+8.80%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 23533.565 | 21728.306 | -1805.258 roots/s (-7.67%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 200.928 | 200.928 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 28.921 | 31.434 | +2.513 KiB (+8.69%) | 6 | larger |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 67.291 | 67.442 | +0.151 KiB (+0.22%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 1.944 | 1.998 | +0.054 KiB (+2.76%) | 6 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.143 | 6.167 | +0.025 us/projection (+0.40%) | 9 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 164736.163 | 163543.580 | -1192.582 projections/s (-0.72%) | 9 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.496 | 45.496 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 51.560 | 51.560 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 599.672 | 599.672 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 128.266 | 128.266 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.661 | 7.609 | -0.052 us/projection (-0.68%) | 9 | within noise |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 131788.931 | 132129.034 | +340.103 projections/s (+0.26%) | 9 | within noise |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 49.652 | 49.652 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 66.832 | 66.832 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 615.672 | 615.672 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 178.766 | 178.766 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.821 | 9.370 | +0.549 ms (+6.22%) | 9 | slower |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 22435.044 | 21259.443 | -1175.600 roots/s (-5.24%) | 9 | slower |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.798 | 10.511 | +0.714 ms (+7.28%) | 9 | slower |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20345.880 | 18977.883 | -1367.996 roots/s (-6.72%) | 9 | slower |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.921 | 16.850 | -0.071 ms (-0.42%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 11830.032 | 11857.385 | +27.353 roots/s (+0.23%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 17.183 | 17.084 | -0.099 ms (-0.57%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 11518.111 | 11708.516 | +190.405 roots/s (+1.65%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.elapsedUsPerRoot | 110.827 | 110.372 | -0.454 us/root (-0.41%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.peakKiB | 447.188 | 447.188 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.retainedKiB | 162.484 | 162.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.elapsedUsPerRoot | 112.803 | 111.878 | -0.926 us/root (-0.82%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.peakKiB | 451.212 | 451.212 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.retainedKiB | 162.484 | 162.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.elapsedUsPerRoot | 399.061 | 398.772 | -0.289 us/root (-0.07%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.peakKiB | 954.355 | 954.355 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.retainedKiB | 313.047 | 313.047 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.elapsedUsPerRoot | 403.560 | 433.339 | +29.779 us/root (+7.38%) | 9 | slower |
| 3.14 | provider-free-delivery | leaf-bytes | document.peakKiB | 958.113 | 958.113 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.retainedKiB | 313.047 | 313.047 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.elapsedUsPerRoot | 427.151 | 428.729 | +1.578 us/root (+0.37%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.peakKiB | 773.853 | 773.853 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.retainedKiB | 192.965 | 192.965 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.elapsedUsPerRoot | 429.876 | 425.526 | -4.350 us/root (-1.01%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.peakKiB | 777.649 | 777.649 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.retainedKiB | 192.965 | 192.965 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.elapsedUsPerRoot | 935.033 | 1055.738 | +120.706 us/root (+12.91%) | 9 | slower |
| 3.14 | provider-free-delivery | leaf-decimal | columns.peakKiB | 1300.483 | 1300.483 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.retainedKiB | 271.797 | 271.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.elapsedUsPerRoot | 938.210 | 936.435 | -1.775 us/root (-0.19%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.peakKiB | 1304.312 | 1304.312 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.retainedKiB | 271.797 | 271.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.elapsedUsPerRoot | 811.590 | 808.819 | -2.771 us/root (-0.34%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.peakKiB | 691.443 | 691.443 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.elapsedUsPerRoot | 811.738 | 812.609 | +0.871 us/root (+0.11%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.peakKiB | 695.201 | 695.201 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.elapsedUsPerRoot | 322.350 | 317.669 | -4.681 us/root (-1.45%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.peakKiB | 657.537 | 657.537 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.elapsedUsPerRoot | 318.831 | 319.878 | +1.047 us/root (+0.33%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.peakKiB | 661.295 | 661.295 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.elapsedUsPerRoot | 159.543 | 156.155 | -3.388 us/root (-2.12%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.peakKiB | 639.337 | 639.337 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.retainedKiB | 354.480 | 354.480 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.elapsedUsPerRoot | 158.440 | 156.876 | -1.564 us/root (-0.99%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.peakKiB | 643.360 | 643.360 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.retainedKiB | 354.480 | 354.480 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.elapsedUsPerRoot | 165.767 | 165.079 | -0.687 us/root (-0.41%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.peakKiB | 651.306 | 651.306 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.retainedKiB | 366.484 | 366.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.elapsedUsPerRoot | 164.014 | 164.833 | +0.819 us/root (+0.50%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.peakKiB | 655.329 | 655.329 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.retainedKiB | 366.484 | 366.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.elapsedUsPerRoot | 567.331 | 566.598 | -0.733 us/root (-0.13%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.peakKiB | 829.834 | 829.834 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.retainedKiB | 277.984 | 277.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.elapsedUsPerRoot | 570.586 | 566.158 | -4.428 us/root (-0.78%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.peakKiB | 833.592 | 833.592 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.retainedKiB | 277.984 | 277.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.elapsedUsPerRoot | 1007.112 | 841.789 | -165.323 us/root (-16.42%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.peakKiB | 933.672 | 956.719 | +23.047 KiB (+2.47%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.retainedKiB | 302.832 | 302.979 | +0.146 KiB (+0.05%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.elapsedUsPerRoot | 1002.125 | 847.491 | -154.634 us/root (-15.43%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-timestamp | document.peakKiB | 937.430 | 960.525 | +23.096 KiB (+2.46%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.retainedKiB | 303.223 | 303.027 | -0.195 KiB (-0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.elapsedUsPerRoot | 572.010 | 577.779 | +5.768 us/root (+1.01%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.peakKiB | 1279.028 | 1279.028 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.retainedKiB | 321.297 | 321.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.elapsedUsPerRoot | 575.331 | 576.022 | +0.691 us/root (+0.12%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.peakKiB | 1282.856 | 1282.856 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.retainedKiB | 321.297 | 321.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 32.935 | 32.863 | -0.072 us/root (-0.22%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 97.325 | 97.325 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.109 | 51.109 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 33.327 | 33.620 | +0.293 us/root (+0.88%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 101.036 | 101.036 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.109 | 51.109 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 49.228 | 47.891 | -1.337 us/root (-2.72%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 148.214 | 148.214 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.234 | 88.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 50.056 | 48.647 | -1.409 us/root (-2.81%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 151.401 | 151.401 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.234 | 88.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 68.637 | 68.923 | +0.286 us/root (+0.42%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 223.218 | 223.218 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.734 | 137.734 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 69.491 | 68.695 | -0.796 us/root (-1.14%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 227.249 | 227.249 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.734 | 137.734 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 24.827 | 24.316 | -0.510 us/root (-2.06%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 61.062 | 61.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.359 | 24.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 25.079 | 24.865 | -0.215 us/root (-0.86%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 67.422 | 67.422 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.359 | 24.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 155.384 | 154.587 | -0.797 us/root (-0.51%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 629.829 | 629.829 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.359 | 428.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 157.099 | 155.785 | -1.314 us/root (-0.84%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 633.739 | 633.739 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.359 | 428.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 58.341 | 58.184 | -0.158 us/root (-0.27%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 198.134 | 198.134 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.359 | 125.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 59.613 | 58.388 | -1.225 us/root (-2.06%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 201.552 | 201.552 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.359 | 125.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 47.898 | 48.576 | +0.677 us/root (+1.41%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 127.213 | 127.213 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.203 | 36.203 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 50.958 | 48.583 | -2.375 us/root (-4.66%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 130.924 | 130.924 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.203 | 36.203 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 56.552 | 55.711 | -0.841 us/root (-1.49%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 222.470 | 222.470 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.984 | 136.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 56.302 | 56.578 | +0.276 us/root (+0.49%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 226.376 | 226.376 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.984 | 136.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 148.523 | 145.680 | -2.844 us/root (-1.91%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 765.188 | 765.188 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.484 | 480.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 147.060 | 147.206 | +0.146 us/root (+0.10%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 769.095 | 769.095 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.484 | 480.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 258.583 | 257.250 | -1.333 us (-0.52%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 37.547 | 37.547 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 29.992 | 29.992 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 379.709 | 377.792 | -1.917 us (-0.50%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 50.483 | 50.483 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 41.921 | 41.921 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 498.875 | 499.584 | +0.709 us (+0.14%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 62.709 | 62.709 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 53.326 | 53.326 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 91.583 | 92.208 | +0.625 us (+0.68%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 21.005 | 21.005 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.981 | 14.981 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 93.292 | 93.792 | +0.500 us (+0.54%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 21.168 | 21.168 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 15.145 | 15.145 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 91.458 | 90.833 | -0.625 us (-0.68%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 21.005 | 21.005 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.981 | 14.981 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 93.875 | 93.042 | -0.833 us (-0.89%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 21.164 | 21.168 | +0.004 KiB (+0.02%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 15.145 | 15.145 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 91.875 | 92.041 | +0.166 us (+0.18%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 21.006 | 21.006 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.982 | 14.982 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 93.000 | 93.333 | +0.333 us (+0.36%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 21.169 | 21.169 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 15.146 | 15.146 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 15.166 | 15.250 | +0.084 us (+0.55%) | 9 | within noise |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 20.959 | 21.000 | +0.041 us (+0.20%) | 9 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 26.959 | 26.792 | -0.167 us (-0.62%) | 9 | within noise |
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
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 210.416 | 212.333 | +1.917 us/row (+0.91%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 1432.000 | 1432.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 10866.000 | 10866.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 212.083 | 212.667 | +0.584 us/row (+0.28%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 1432.000 | 1432.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 11114.000 | 11114.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 315.250 | 312.500 | -2.750 us/row (-0.87%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 1432.000 | 1432.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 8956.000 | 8956.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 289.541 | 289.541 | +0.000 us/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 1432.000 | 1432.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 9201.000 | 9201.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 357.667 | 353.417 | -4.250 us/row (-1.19%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1712.000 | 1712.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 12574.000 | 12574.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 339.000 | 341.417 | +2.417 us/row (+0.71%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1712.000 | 1712.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13350.000 | 13350.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 936.833 | 945.166 | +8.333 us/row (+0.89%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2832.000 | 2832.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 20857.000 | 20857.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 860.292 | 865.041 | +4.749 us/row (+0.55%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2832.000 | 2832.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23890.000 | 23890.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 287.250 | 286.959 | -0.291 us/row (-0.10%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 2160.000 | 2160.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15296.000 | 15296.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 282.958 | 277.166 | -5.792 us/row (-2.05%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 2288.000 | 2288.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16140.000 | 16140.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 283.625 | 279.333 | -4.292 us/row (-1.51%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 2160.000 | 2160.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15481.000 | 15481.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 276.875 | 270.083 | -6.792 us/row (-2.45%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 2288.000 | 2288.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 16221.000 | 16221.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 111.708 | 110.459 | -1.249 us/row (-1.12%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1648.000 | 1648.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 8580.000 | 8580.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 112.125 | 110.375 | -1.750 us/row (-1.56%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1648.000 | 1648.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 8852.000 | 8852.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 149.750 | 145.542 | -4.208 us/row (-2.81%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2320.000 | 2320.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10341.000 | 10341.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 145.459 | 146.500 | +1.041 us/row (+0.72%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2320.000 | 2320.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 10497.000 | 10497.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 194.375 | 193.167 | -1.208 us/row (-0.62%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3216.000 | 3216.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 13466.000 | 13466.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 194.375 | 191.750 | -2.625 us/row (-1.35%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3216.000 | 3216.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 13552.000 | 13552.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 90.125 | 88.667 | -1.458 us/row (-1.62%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1144.000 | 1144.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7425.000 | 7425.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 87.125 | 86.792 | -0.333 us/row (-0.38%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1144.000 | 1144.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 7447.000 | 7447.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 420.833 | 414.292 | -6.541 us/row (-1.55%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8608.000 | 8608.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27376.000 | 27376.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 418.167 | 412.250 | -5.917 us/row (-1.41%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8608.000 | 8608.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 27539.000 | 27539.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 175.125 | 171.333 | -3.792 us/row (-2.17%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3040.000 | 3040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 11920.000 | 11920.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 173.167 | 173.208 | +0.041 us/row (+0.02%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3040.000 | 3040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 12219.000 | 12219.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 159.750 | 156.708 | -3.042 us/row (-1.90%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1648.000 | 1648.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8350.000 | 8350.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 156.042 | 153.625 | -2.417 us/row (-1.55%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1648.000 | 1648.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 8619.000 | 8619.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 210.708 | 191.084 | -19.624 us/row (-9.31%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2488.000 | 2488.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11360.000 | 11360.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 190.833 | 190.208 | -0.625 us/row (-0.33%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2488.000 | 2488.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 11640.000 | 11640.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 517.416 | 514.542 | -2.874 us/row (-0.56%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5848.000 | 5848.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23567.000 | 23567.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 515.958 | 516.792 | +0.834 us/row (+0.16%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5848.000 | 5848.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 24984.000 | 24984.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 156.291 | 156.209 | -0.082 us/row (-0.05%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 1968.000 | 1968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 9139.000 | 9139.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 142.458 | 141.000 | -1.458 us/row (-1.02%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 2000.000 | 2000.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 9459.000 | 9459.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 161.750 | 163.792 | +2.042 us/row (+1.26%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 1968.000 | 1968.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 9927.000 | 9927.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 148.167 | 146.042 | -2.125 us/row (-1.43%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 2000.000 | 2000.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 10247.000 | 10247.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 193.125 | 192.000 | -1.125 us/row (-0.58%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 2160.000 | 2160.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 11217.000 | 11217.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 177.250 | 180.833 | +3.583 us/row (+2.02%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 2192.000 | 2192.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 11517.000 | 11517.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 202.459 | 201.958 | -0.501 us/row (-0.25%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 2160.000 | 2160.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 11668.000 | 11668.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 191.667 | 187.958 | -3.709 us/row (-1.94%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 2192.000 | 2192.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 12096.000 | 12096.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 116.541 | 113.167 | -3.374 us/row (-2.90%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1872.000 | 1872.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 10118.000 | 10118.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 119.375 | 116.292 | -3.083 us/row (-2.58%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1872.000 | 1872.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 10302.000 | 10302.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 114.625 | 111.458 | -3.167 us/row (-2.76%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 1872.000 | 1872.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 10142.000 | 10142.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 117.834 | 114.083 | -3.751 us/row (-3.18%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 1872.000 | 1872.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 10262.000 | 10262.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 87.083 | 85.833 | -1.250 us/row (-1.44%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 7168.000 | 7168.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 72.292 | 72.584 | +0.292 us/row (+0.40%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 7184.000 | 7184.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 87.542 | 86.542 | -1.000 us/row (-1.14%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 7168.000 | 7168.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 73.750 | 73.417 | -0.333 us/row (-0.45%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 7184.000 | 7184.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3374.875 | 3301.625 | -73.250 us (-2.17%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | retainedBytes | 426776.000 | 426776.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 438904.000 | 438904.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | 303.791 | 304.833 | +1.042 us (+0.34%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | 23472.000 | 23472.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared.family | transientBytes | 27536.000 | 27536.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 24.915 | 24.610 | -0.305 us/row (-1.23%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 911.875 | 911.875 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 2003.484 | 2003.484 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 25.822 | 25.523 | -0.299 us/row (-1.16%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1913.375 | 1913.375 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2469.828 | 2469.828 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 29.440 | 29.146 | -0.294 us/row (-1.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1032.500 | 1032.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2650.812 | 2650.812 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 31.432 | 30.404 | -1.029 us/row (-3.27%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2038.500 | 2038.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 3010.688 | 3010.688 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 49.818 | 48.323 | -1.495 us/row (-3.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1523.000 | 1523.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 4640.250 | 4640.250 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 49.557 | 49.375 | -0.182 us/row (-0.37%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2547.000 | 2547.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 4862.750 | 4862.750 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | elapsedUs | 63.292 | 61.708 | -1.584 us/row (-2.50%) | 9 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | retainedBytes | 7528.000 | 7528.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | transientBytes | 7616.000 | 7616.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 235.292 | 234.500 | -0.792 us/row (-0.34%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 1440.000 | 1440.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 11034.000 | 11034.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 239.167 | 237.375 | -1.792 us/row (-0.75%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 1440.000 | 1440.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 11554.000 | 11554.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 361.333 | 342.750 | -18.583 us/row (-5.14%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 1440.000 | 1440.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 9220.000 | 9220.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 321.875 | 318.208 | -3.667 us/row (-1.14%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 1440.000 | 1440.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 9649.000 | 9649.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 385.167 | 383.334 | -1.833 us/row (-0.48%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1720.000 | 1720.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 12926.000 | 12926.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 370.000 | 372.500 | +2.500 us/row (+0.68%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1720.000 | 1720.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13854.000 | 13854.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 995.667 | 998.333 | +2.666 us/row (+0.27%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2840.000 | 2840.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 23617.000 | 23617.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 920.042 | 912.750 | -7.292 us/row (-0.79%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2840.000 | 2840.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 26834.000 | 26834.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 318.209 | 313.792 | -4.417 us/row (-1.39%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 2176.000 | 2176.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 14896.000 | 14896.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 318.084 | 308.417 | -9.667 us/row (-3.04%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 2304.000 | 2304.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16004.000 | 16004.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 311.750 | 310.083 | -1.667 us/row (-0.53%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 2176.000 | 2176.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15217.000 | 15217.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 311.458 | 298.583 | -12.875 us/row (-4.13%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 2304.000 | 2304.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 16325.000 | 16325.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 130.291 | 130.458 | +0.167 us/row (+0.13%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1704.000 | 1704.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 9116.000 | 9116.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 130.208 | 130.458 | +0.250 us/row (+0.19%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1704.000 | 1704.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 9516.000 | 9516.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 165.709 | 170.875 | +5.166 us/row (+3.12%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2376.000 | 2376.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10973.000 | 10973.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 168.000 | 167.416 | -0.584 us/row (-0.35%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2376.000 | 2376.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 11257.000 | 11257.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 213.709 | 218.500 | +4.791 us/row (+2.24%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3272.000 | 3272.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 14186.000 | 14186.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 215.375 | 214.416 | -0.959 us/row (-0.45%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3272.000 | 3272.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 14360.000 | 14360.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 109.000 | 108.375 | -0.625 us/row (-0.57%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1192.000 | 1192.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7961.000 | 7961.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 107.959 | 106.084 | -1.875 us/row (-1.74%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1192.000 | 1192.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 8047.000 | 8047.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 448.250 | 440.500 | -7.750 us/row (-1.73%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8664.000 | 8664.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27944.000 | 27944.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 447.458 | 442.667 | -4.791 us/row (-1.07%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8664.000 | 8664.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 28171.000 | 28171.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 197.250 | 192.458 | -4.792 us/row (-2.43%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3096.000 | 3096.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 12488.000 | 12488.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 193.458 | 193.459 | +0.001 us/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3096.000 | 3096.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 12883.000 | 12883.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 181.000 | 181.917 | +0.917 us/row (+0.51%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1704.000 | 1704.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8918.000 | 8918.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 179.875 | 180.708 | +0.833 us/row (+0.46%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1704.000 | 1704.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 9315.000 | 9315.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 212.000 | 217.875 | +5.875 us/row (+2.77%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2544.000 | 2544.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11960.000 | 11960.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 214.250 | 214.084 | -0.166 us/row (-0.08%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2544.000 | 2544.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 12336.000 | 12336.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 550.917 | 553.375 | +2.458 us/row (+0.45%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 24135.000 | 24135.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 552.667 | 553.584 | +0.917 us/row (+0.17%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 25680.000 | 25680.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | elapsedUs | 486.917 | 486.666 | -0.251 us/row (-0.05%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | transientBytes | 21101.000 | 21101.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | elapsedUs | 555.333 | 551.000 | -4.333 us/row (-0.78%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | transientBytes | 21197.000 | 21197.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | elapsedUs | 489.708 | 487.084 | -2.624 us/row (-0.54%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | transientBytes | 22046.000 | 22046.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | elapsedUs | 547.875 | 554.625 | +6.750 us/row (+1.23%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | transientBytes | 22142.000 | 22142.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | elapsedUs | 566.333 | 561.750 | -4.583 us/row (-0.81%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | transientBytes | 44547.000 | 44547.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | elapsedUs | 736.291 | 726.500 | -9.791 us/row (-1.33%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | retainedBytes | 15312.000 | 15312.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | transientBytes | 54051.000 | 54051.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | elapsedUs | 559.542 | 570.083 | +10.541 us/row (+1.88%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | transientBytes | 47372.000 | 47372.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | elapsedUs | 727.417 | 726.333 | -1.084 us/row (-0.15%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | retainedBytes | 15312.000 | 15312.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | transientBytes | 56876.000 | 56876.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | elapsedUs | 622.833 | 627.875 | +5.042 us/row (+0.81%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | transientBytes | 33282.000 | 33282.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | elapsedUs | 855.584 | 851.583 | -4.001 us/row (-0.47%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | retainedBytes | 12048.000 | 12048.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | transientBytes | 39514.000 | 39514.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | elapsedUs | 630.834 | 626.083 | -4.751 us/row (-0.75%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | transientBytes | 34699.000 | 34699.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | elapsedUs | 842.583 | 857.708 | +15.125 us/row (+1.80%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | retainedBytes | 12048.000 | 12048.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | transientBytes | 40931.000 | 40931.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | elapsedUs | 1075.208 | 1038.125 | -37.083 us/row (-3.45%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | transientBytes | 36141.000 | 36141.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | elapsedUs | 1894.208 | 1858.834 | -35.374 us/row (-1.87%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | retainedBytes | 28944.000 | 28944.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | transientBytes | 59337.000 | 59337.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | elapsedUs | 1056.458 | 1040.875 | -15.583 us/row (-1.48%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | transientBytes | 37686.000 | 37686.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | elapsedUs | 1878.375 | 1864.625 | -13.750 us/row (-0.73%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | retainedBytes | 28944.000 | 28944.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | transientBytes | 60818.000 | 60818.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | elapsedUs | 1021.792 | 893.833 | -127.959 us/row (-12.52%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.columns.typed | retainedBytes | 10512.000 | 10512.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | transientBytes | 30837.000 | 30837.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | elapsedUs | 1517.958 | 1279.500 | -238.458 us/row (-15.71%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.columns.wire | retainedBytes | 10512.000 | 10512.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | transientBytes | 30997.000 | 30997.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | elapsedUs | 892.792 | 900.416 | +7.624 us/row (+0.85%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | retainedBytes | 10512.000 | 10512.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | transientBytes | 31870.000 | 31870.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | elapsedUs | 1302.333 | 1287.000 | -15.333 us/row (-1.18%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | retainedBytes | 10512.000 | 10512.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | transientBytes | 31966.000 | 31966.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | elapsedUs | 578.334 | 566.583 | -11.751 us/row (-2.03%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | transientBytes | 21573.000 | 21573.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | elapsedUs | 677.500 | 651.834 | -25.666 us/row (-3.79%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | transientBytes | 21669.000 | 21669.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | elapsedUs | 569.167 | 559.125 | -10.042 us/row (-1.76%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | transientBytes | 22606.000 | 22606.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | elapsedUs | 656.500 | 653.834 | -2.666 us/row (-0.41%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | transientBytes | 22702.000 | 22702.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | elapsedUs | 509.958 | 509.334 | -0.624 us/row (-0.12%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | transientBytes | 22326.000 | 22326.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | elapsedUs | 644.708 | 650.959 | +6.251 us/row (+0.97%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | retainedBytes | 12032.000 | 12032.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | transientBytes | 28510.000 | 28510.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | elapsedUs | 510.041 | 508.500 | -1.541 us/row (-0.30%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | transientBytes | 23510.000 | 23510.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | elapsedUs | 651.375 | 650.958 | -0.417 us/row (-0.06%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | retainedBytes | 12032.000 | 12032.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | transientBytes | 29694.000 | 29694.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | elapsedUs | 531.625 | 532.833 | +1.208 us/row (+0.23%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | transientBytes | 23306.000 | 23306.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | elapsedUs | 678.250 | 675.834 | -2.416 us/row (-0.36%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | retainedBytes | 12048.000 | 12048.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | transientBytes | 29546.000 | 29546.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | elapsedUs | 540.000 | 523.000 | -17.000 us/row (-3.15%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | transientBytes | 24686.000 | 24686.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | elapsedUs | 703.417 | 675.667 | -27.750 us/row (-3.95%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | retainedBytes | 12048.000 | 12048.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | transientBytes | 30926.000 | 30926.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | elapsedUs | 673.458 | 678.750 | +5.292 us/row (+0.79%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | transientBytes | 24228.000 | 24228.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | elapsedUs | 672.125 | 669.375 | -2.750 us/row (-0.41%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | transientBytes | 25773.000 | 25773.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | elapsedUs | 678.625 | 675.291 | -3.334 us/row (-0.49%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | transientBytes | 35842.000 | 35842.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | elapsedUs | 945.166 | 928.958 | -16.208 us/row (-1.71%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | retainedBytes | 12048.000 | 12048.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | transientBytes | 42138.000 | 42138.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | elapsedUs | 683.708 | 687.250 | +3.542 us/row (+0.52%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | transientBytes | 37579.000 | 37579.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | elapsedUs | 935.250 | 935.667 | +0.417 us/row (+0.04%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | retainedBytes | 12048.000 | 12048.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | transientBytes | 43811.000 | 43811.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | elapsedUs | 957.542 | 790.125 | -167.417 us/row (-17.48%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | transientBytes | 41991.000 | 41991.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | elapsedUs | 1443.750 | 1180.625 | -263.125 us/row (-18.23%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | retainedBytes | 15120.000 | 15120.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | transientBytes | 51611.000 | 51611.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | elapsedUs | 942.875 | 783.000 | -159.875 us/row (-16.96%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | transientBytes | 44496.000 | 44496.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | elapsedUs | 1452.667 | 1189.708 | -262.959 us/row (-18.10%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.document.wire | retainedBytes | 15120.000 | 15120.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | transientBytes | 54052.000 | 54052.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | elapsedUs | 913.000 | 911.375 | -1.625 us/row (-0.18%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | transientBytes | 46714.000 | 46714.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | elapsedUs | 1264.291 | 1270.542 | +6.251 us/row (+0.49%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | retainedBytes | 26640.000 | 26640.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | transientBytes | 67610.000 | 67610.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | elapsedUs | 917.083 | 906.167 | -10.916 us/row (-1.19%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | retainedBytes | 5904.000 | 5904.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | transientBytes | 49795.000 | 49795.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | elapsedUs | 1266.167 | 1269.875 | +3.708 us/row (+0.29%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | retainedBytes | 26640.000 | 26640.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | transientBytes | 70627.000 | 70627.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 180.667 | 179.750 | -0.917 us/row (-0.51%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 2064.000 | 2064.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 9683.000 | 9683.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 170.250 | 172.791 | +2.541 us/row (+1.49%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 10163.000 | 10163.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 188.208 | 186.791 | -1.417 us/row (-0.75%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 1992.000 | 1992.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 10535.000 | 10535.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 173.750 | 171.708 | -2.042 us/row (-1.18%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 2024.000 | 2024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 11015.000 | 11015.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 221.959 | 219.458 | -2.501 us/row (-1.13%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 2176.000 | 2176.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 11489.000 | 11489.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 204.125 | 202.875 | -1.250 us/row (-0.61%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 2208.000 | 2208.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 11949.000 | 11949.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 236.667 | 230.125 | -6.542 us/row (-2.76%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 2176.000 | 2176.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 11948.000 | 11948.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 229.042 | 219.500 | -9.542 us/row (-4.17%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 2208.000 | 2208.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 12536.000 | 12536.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 134.875 | 136.459 | +1.584 us/row (+1.17%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1928.000 | 1928.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 10550.000 | 10550.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 139.000 | 137.000 | -2.000 us/row (-1.44%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1928.000 | 1928.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 10670.000 | 10670.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 133.958 | 132.084 | -1.874 us/row (-1.40%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 1928.000 | 1928.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 10702.000 | 10702.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 136.042 | 137.750 | +1.708 us/row (+1.26%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 1928.000 | 1928.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 10798.000 | 10798.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 97.417 | 97.125 | -0.292 us/row (-0.30%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 7744.000 | 7744.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 84.625 | 82.834 | -1.791 us/row (-2.12%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 7856.000 | 7856.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 97.834 | 97.042 | -0.792 us/row (-0.81%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 7744.000 | 7744.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 84.042 | 83.250 | -0.792 us/row (-0.94%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 7856.000 | 7856.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3321.958 | 3316.333 | -5.625 us (-0.17%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared | retainedBytes | 438440.000 | 438440.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 444984.000 | 444984.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | 311.625 | 313.208 | +1.583 us (+0.51%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | 23920.000 | 23920.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared.family | transientBytes | 27688.000 | 27688.000 | +0.000 B (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 24.938 | 24.527 | -0.410 us/row (-1.65%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 985.594 | 985.594 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 2050.805 | 2050.805 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 25.788 | 25.059 | -0.729 us/row (-2.83%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1987.219 | 1987.219 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2436.273 | 2436.273 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 29.803 | 29.635 | -0.168 us/row (-0.56%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1135.375 | 1135.375 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2696.094 | 2696.094 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 30.316 | 29.749 | -0.568 us/row (-1.87%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2141.875 | 2141.875 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 3022.219 | 3022.219 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 49.339 | 49.297 | -0.042 us/row (-0.08%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1742.500 | 1742.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 4822.375 | 4822.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 50.938 | 51.656 | +0.719 us/row (+1.41%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2768.500 | 2768.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 5052.875 | 5052.875 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | elapsedUs | 118.818 | 116.854 | -1.964 us/row (-1.65%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | retainedBytes | 3166.500 | 3166.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | transientBytes | 17259.375 | 17259.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | elapsedUs | 117.375 | 116.344 | -1.031 us/row (-0.88%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | retainedBytes | 16642.500 | 16642.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | transientBytes | 19092.625 | 19092.625 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | elapsedUs | 331.250 | 328.193 | -3.057 us/row (-0.92%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | retainedBytes | 12966.500 | 12966.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | transientBytes | 32976.000 | 32976.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | elapsedUs | 329.901 | 323.781 | -6.120 us/row (-1.86%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | retainedBytes | 40458.500 | 40458.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | transientBytes | 43064.250 | 43064.250 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | elapsedUs | 389.057 | 376.760 | -12.297 us/row (-3.16%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | retainedBytes | 9566.500 | 9566.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | transientBytes | 28226.625 | 28226.625 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | elapsedUs | 377.651 | 374.734 | -2.917 us/row (-0.77%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | retainedBytes | 32834.500 | 32834.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | transientBytes | 35442.875 | 35442.875 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | elapsedUs | 722.505 | 727.167 | +4.661 us/row (+0.65%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | retainedBytes | 27166.500 | 27166.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | transientBytes | 33197.375 | 33197.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | elapsedUs | 733.615 | 723.906 | -9.708 us/row (-1.32%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | retainedBytes | 50818.500 | 50818.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | transientBytes | 53602.375 | 53602.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | elapsedUs | 588.302 | 596.948 | +8.646 us/row (+1.47%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | retainedBytes | 7966.500 | 7966.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | transientBytes | 22665.375 | 22665.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | elapsedUs | 602.010 | 593.438 | -8.573 us/row (-1.42%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | retainedBytes | 26050.500 | 26050.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | transientBytes | 28537.625 | 28537.625 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | elapsedUs | 270.812 | 270.953 | +0.141 us/row (+0.05%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | retainedBytes | 7774.500 | 7774.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | transientBytes | 21888.375 | 21888.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | elapsedUs | 267.339 | 269.849 | +2.510 us/row (+0.94%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | retainedBytes | 21250.500 | 21250.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | transientBytes | 23728.625 | 23728.625 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | elapsedUs | 167.781 | 167.995 | +0.214 us/row (+0.13%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | retainedBytes | 9566.000 | 9566.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | transientBytes | 23668.375 | 23668.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | elapsedUs | 168.359 | 164.484 | -3.875 us/row (-2.30%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | retainedBytes | 23042.000 | 23042.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | transientBytes | 25508.625 | 25508.625 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | elapsedUs | 171.906 | 173.974 | +2.068 us/row (+1.20%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | retainedBytes | 9950.500 | 9950.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | transientBytes | 24057.375 | 24057.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | elapsedUs | 182.224 | 172.458 | -9.766 us/row (-5.36%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | retainedBytes | 23426.500 | 23426.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | transientBytes | 25897.625 | 25897.625 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | elapsedUs | 153.182 | 154.141 | +0.958 us/row (+0.63%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | retainedBytes | 13342.500 | 13342.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | transientBytes | 27434.875 | 27434.875 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | elapsedUs | 154.651 | 152.604 | -2.047 us/row (-1.32%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | retainedBytes | 26818.500 | 26818.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | transientBytes | 29284.125 | 29284.125 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | elapsedUs | 479.099 | 483.812 | +4.714 us/row (+0.98%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | retainedBytes | 9566.500 | 9566.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | transientBytes | 29194.625 | 29194.625 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | elapsedUs | 482.990 | 481.630 | -1.359 us/row (-0.28%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | retainedBytes | 33794.500 | 33794.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | transientBytes | 36410.875 | 36410.875 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | elapsedUs | 819.667 | 694.406 | -125.260 us/row (-15.28%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | retainedBytes | 12766.500 | 12766.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | transientBytes | 32030.625 | 32030.625 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | elapsedUs | 808.391 | 709.208 | -99.182 us/row (-12.27%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | retainedBytes | 39298.500 | 39298.500 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | transientBytes | 41934.875 | 41934.875 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | elapsedUs | 433.552 | 431.104 | -2.448 us/row (-0.56%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | retainedBytes | 24761.000 | 24761.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | transientBytes | 35620.125 | 35620.125 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | elapsedUs | 435.786 | 428.849 | -6.938 us/row (-1.59%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | retainedBytes | 53021.000 | 53021.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | transientBytes | 55604.375 | 55604.375 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | elapsedUs | 64.750 | 63.917 | -0.833 us/row (-1.29%) | 9 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | retainedBytes | 8748.000 | 8748.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | transientBytes | 8718.000 | 8718.000 | +0.000 B/row (+0.00%) | 9 | within noise |

Deltas are advisory and never ratchet the Budget Contract.
