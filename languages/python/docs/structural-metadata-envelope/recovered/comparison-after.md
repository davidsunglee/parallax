# Python cost report comparison

Timing deltas within 5% and byte deltas within 3% are read as noise; count deltas are exact. A cell present on one side alone, or whose unit differs, is not compared.

## instance-state

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| - | - | cpython-3.13 | aggregate.bare.after | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.before | 6384.000 | 6384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.reduction | 0.617 | 0.617 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.before | 7200.000 | 7200.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.reduction | 0.547 | 0.547 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.398 | 3.340 | -0.058 ratio (-1.71%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.398 | 3.340 | -0.058 ratio (-1.71%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.425 | 3.313 | -0.112 ratio (-3.27%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 1.068 | 0.522 | -0.546 ratio (-51.16%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.likeForLike | 1.023 | 0.500 | -0.523 ratio (-51.14%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 2.790 | 1.549 | -1.240 ratio (-44.45%) | 0 | smaller |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.223 | 2.184 | -0.039 ratio (-1.75%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.223 | 2.184 | -0.039 ratio (-1.75%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.245 | 2.209 | -0.035 ratio (-1.57%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 18871.582 | 1471.432 | -17400.150 ns (-92.20%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 17478.835 | 6919.735 | -10559.100 ns (-60.41%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.dumpNs | 6237.312 | 5770.104 | -467.208 ns (-7.49%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 7754.000 | 4770.000 | -2984.000 B (-38.48%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.readNs | 88.292 | 83.312 | -4.979 ns (-5.64%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 691.459 | 425.885 | -265.574 ns (-38.41%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 6690.000 | 3706.000 | -2984.000 B (-44.60%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 691.459 | 425.885 | -265.574 ns (-38.41%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | -126.869 | 105.925 | +232.794 ns (-183.49%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 14641.494 | 10317.575 | -4323.919 ns (-29.53%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2513.083 | 2373.458 | -139.625 ns (-5.56%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 5184.000 | 4960.000 | -224.000 B (-4.32%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.readNs | 28.658 | 25.200 | -3.458 ns (-12.07%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2392.000 | 2168.000 | -224.000 B (-9.36%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 301.811 | 417.600 | +115.790 ns (+38.36%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 9662.669 | 6057.817 | -3604.852 ns (-37.31%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2578.646 | 2379.062 | -199.584 ns (-7.74%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 27.921 | 26.533 | -1.388 ns (-4.97%) | 0 | smaller |
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
| - | - | cpython-3.13/nullable | compact.callNs | 14391.654 | 1309.339 | -13082.315 ns (-90.90%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 5486.429 | 2307.494 | -3178.935 ns (-57.94%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1952.437 | 1830.562 | -121.875 ns (-6.24%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 5320.000 | 3464.000 | -1856.000 B (-34.89%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.readNs | 81.460 | 74.656 | -6.804 ns (-8.35%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 199.359 | 233.641 | +34.281 ns (+17.20%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.transientBytes | 4856.000 | 3000.000 | -1856.000 B (-38.22%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 199.359 | 233.641 | +34.281 ns (+17.20%) | 0 | larger |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 39.779 | 265.614 | +225.836 ns (+567.73%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5679.992 | 5215.677 | -464.315 ns (-8.17%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 914.042 | 855.125 | -58.917 ns (-6.45%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 22.362 | 22.127 | -0.235 ns (-1.05%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 196.598 | 165.896 | -30.703 ns (-15.62%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1274.006 | 1191.208 | -82.798 ns (-6.50%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 874.583 | 860.687 | -13.896 ns (-1.59%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 22.196 | 22.060 | -0.135 ns (-0.61%) | 0 | within noise |
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
| - | - | cpython-3.13/partial | compact.callNs | 14267.177 | 1358.350 | -12908.827 ns (-90.48%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 4981.469 | 2144.337 | -2837.131 ns (-56.95%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.dumpNs | 1965.562 | 1857.750 | -107.812 ns (-5.49%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 5264.000 | 3432.000 | -1832.000 B (-34.80%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.readNs | 82.337 | 74.935 | -7.402 ns (-8.99%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 244.266 | 218.860 | -25.406 ns (-10.40%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.transientBytes | 4832.000 | 3000.000 | -1832.000 B (-37.91%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 244.266 | 218.860 | -25.406 ns (-10.40%) | 0 | smaller |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 233.269 | 187.077 | -46.192 ns (-19.80%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5336.315 | 4991.819 | -344.496 ns (-6.46%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.dumpNs | 919.854 | 891.167 | -28.687 ns (-3.12%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 23.354 | 24.321 | +0.967 ns (+4.14%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 191.050 | 191.492 | +0.442 ns (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 988.950 | 945.946 | -43.004 ns (-4.35%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 937.917 | 868.479 | -69.438 ns (-7.40%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 25.221 | 22.933 | -2.287 ns (-9.07%) | 0 | smaller |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 32657.117 | 1346.071 | -31311.046 ns (-95.88%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 4887.196 | 2218.367 | -2668.829 ns (-54.61%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1737.041 | 1588.438 | -148.604 ns (-8.56%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 7832.000 | 3408.000 | -4424.000 B (-56.49%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.readNs | 85.277 | 80.107 | -5.170 ns (-6.06%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 276.815 | 234.066 | -42.749 ns (-15.44%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 7424.000 | 3000.000 | -4424.000 B (-59.59%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 276.815 | 234.066 | -42.749 ns (-15.44%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 63.748 | 138.725 | +74.977 ns (+117.61%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4305.190 | 4085.067 | -220.123 ns (-5.11%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 831.104 | 786.792 | -44.312 ns (-5.33%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 25.569 | 23.863 | -1.705 ns (-6.67%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 178.725 | 196.121 | +17.396 ns (+9.73%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1108.629 | 1057.004 | -51.625 ns (-4.66%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 811.500 | 774.416 | -37.083 ns (-4.57%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 25.229 | 24.283 | -0.946 ns (-3.75%) | 0 | smaller |
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
| - | - | cpython-3.13/shallow | compact.callNs | 11920.544 | 1392.777 | -10527.767 ns (-88.32%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 3999.519 | 2077.452 | -1922.067 ns (-48.06%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1484.938 | 1399.542 | -85.396 ns (-5.75%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 5216.000 | 3384.000 | -1832.000 B (-35.12%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.readNs | 96.542 | 88.635 | -7.906 ns (-8.19%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 83.619 | 209.616 | +125.997 ns (+150.68%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.transientBytes | 4832.000 | 3000.000 | -1832.000 B (-37.91%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 83.619 | 209.616 | +125.997 ns (+150.68%) | 0 | larger |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 195.321 | 147.133 | -48.187 ns (-24.67%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2795.221 | 2716.804 | -78.417 ns (-2.81%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 759.250 | 715.209 | -44.041 ns (-5.80%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 28.802 | 25.276 | -3.526 ns (-12.24%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 203.525 | 214.562 | +11.037 ns (+5.42%) | 0 | larger |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 799.933 | 785.979 | -13.954 ns (-1.74%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 707.333 | 718.188 | +10.855 ns (+1.53%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 26.792 | 26.338 | -0.453 ns (-1.69%) | 0 | within noise |
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
| - | - | cpython-3.13/warmed | compact.callNs | 12265.302 | 1586.575 | -10678.727 ns (-87.06%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 6552.990 | 4130.592 | -2422.398 ns (-36.97%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1990.291 | 1737.125 | -253.166 ns (-12.72%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 5400.000 | 3384.000 | -2016.000 B (-37.33%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.readNs | 104.578 | 87.688 | -16.891 ns (-16.15%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 0.895 | 240.703 | +239.808 ns (+26807.41%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.transientBytes | 4594.000 | 2578.000 | -2016.000 B (-43.88%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 0.895 | 240.703 | +239.808 ns (+26807.41%) | 0 | larger |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 169.190 | 153.585 | -15.604 ns (-9.22%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 4079.935 | 3772.644 | -307.292 ns (-7.53%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 763.730 | 707.937 | -55.792 ns (-7.31%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 28.505 | 25.859 | -2.646 ns (-9.28%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 144.296 | 169.441 | +25.146 ns (+17.43%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1796.704 | 1701.954 | -94.750 ns (-5.27%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 759.500 | 704.771 | -54.729 ns (-7.21%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 27.323 | 26.630 | -0.693 ns (-2.53%) | 0 | within noise |
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
| - | - | cpython-3.13/wide | compact.callNs | 16785.929 | 1364.521 | -15421.408 ns (-91.87%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 7172.842 | 2637.167 | -4535.675 ns (-63.23%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.dumpNs | 2678.417 | 2417.041 | -261.375 ns (-9.76%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 5680.000 | 3512.000 | -2168.000 B (-38.17%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.readNs | 86.197 | 82.273 | -3.923 ns (-4.55%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 299.291 | 196.700 | -102.591 ns (-34.28%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.transientBytes | 5168.000 | 3000.000 | -2168.000 B (-41.95%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 299.291 | 196.700 | -102.591 ns (-34.28%) | 0 | smaller |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 139.269 | 30.806 | -108.463 ns (-77.88%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 8455.481 | 7771.485 | -683.996 ns (-8.09%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1286.146 | 1184.459 | -101.687 ns (-7.91%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 24.316 | 24.100 | -0.216 ns (-0.89%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 111.317 | 219.250 | +107.933 ns (+96.96%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1941.371 | 1775.417 | -165.954 ns (-8.55%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1242.855 | 1126.312 | -116.542 ns (-9.38%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 24.501 | 23.921 | -0.581 ns (-2.37%) | 0 | within noise |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.247 | 3.320 | +0.073 ratio (+2.25%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.247 | 3.320 | +0.073 ratio (+2.25%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.098 | 3.284 | +0.186 ratio (+5.99%) | 0 | larger |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 1.088 | 0.508 | -0.580 ratio (-53.32%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.likeForLike | 1.015 | 0.488 | -0.527 ratio (-51.88%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 2.746 | 1.473 | -1.273 ratio (-46.35%) | 0 | smaller |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.087 | 2.151 | +0.064 ratio (+3.08%) | 0 | larger |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.087 | 2.151 | +0.064 ratio (+3.08%) | 0 | larger |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.074 | 2.186 | +0.113 ratio (+5.44%) | 0 | larger |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 24692.729 | 1597.398 | -23095.331 ns (-93.53%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 20878.667 | 6653.790 | -14224.877 ns (-68.13%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.dumpNs | 7870.292 | 6027.395 | -1842.897 ns (-23.42%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 8002.000 | 5034.000 | -2968.000 B (-37.09%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.readNs | 114.287 | 85.679 | -28.608 ns (-25.03%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 564.031 | 317.822 | -246.210 ns (-43.65%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 6770.000 | 3802.000 | -2968.000 B (-43.84%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 564.031 | 317.822 | -246.210 ns (-43.65%) | 0 | smaller |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 401.642 | 97.054 | -304.588 ns (-75.84%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 17835.650 | 10885.092 | -6950.558 ns (-38.97%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 3424.896 | 2543.729 | -881.167 ns (-25.73%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5440.000 | 5184.000 | -256.000 B (-4.71%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.readNs | 35.383 | 26.342 | -9.042 ns (-25.55%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2520.000 | 2264.000 | -256.000 B (-10.16%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 411.300 | 238.071 | -173.229 ns (-42.12%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 11723.471 | 6299.804 | -5423.667 ns (-46.26%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 3369.500 | 2465.104 | -904.396 ns (-26.84%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4696.000 | 4744.000 | +48.000 B (+1.02%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 35.863 | 25.688 | -10.175 ns (-28.37%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.retainedBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.transientBytes | 1488.000 | 1536.000 | +48.000 B (+3.23%) | 0 | larger |
| - | - | cpython-3.14/nested | ordinary.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | vsLegacy.bareReduction | 0.606 | 0.606 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | vsLegacy.retainedReduction | 0.578 | 0.578 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | vsOrdinary.bareReduction | 0.658 | 0.658 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | vsOrdinary.retainedReduction | 0.616 | 0.616 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | warmups | 200.000 | 200.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.bareBytes | 360.000 | 360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.callNs | 17801.646 | 1387.052 | -16414.594 ns (-92.21%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 6787.021 | 2320.427 | -4466.594 ns (-65.81%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.dumpNs | 2161.021 | 1813.438 | -347.583 ns (-16.08%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 5760.000 | 3672.000 | -2088.000 B (-36.25%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.readNs | 91.058 | 78.273 | -12.785 ns (-14.04%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 970.944 | 233.380 | -737.564 ns (-75.96%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 5264.000 | 3176.000 | -2088.000 B (-39.67%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 970.944 | 233.380 | -737.564 ns (-75.96%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 2.873 | 136.987 | +134.114 ns (+4667.94%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 6864.460 | 5262.117 | -1602.344 ns (-23.34%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 1234.771 | 888.250 | -346.521 ns (-28.06%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 31.771 | 24.467 | -7.304 ns (-22.99%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 224.621 | 198.346 | -26.275 ns (-11.70%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1625.567 | 1237.029 | -388.537 ns (-23.90%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 1228.667 | 897.979 | -330.688 ns (-26.91%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 33.969 | 24.223 | -9.746 ns (-28.69%) | 0 | smaller |
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
| - | - | cpython-3.14/partial | compact.callNs | 15459.554 | 1426.656 | -14032.898 ns (-90.77%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 5175.196 | 2156.552 | -3018.644 ns (-58.33%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.dumpNs | 1994.979 | 1857.896 | -137.083 ns (-6.87%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 5720.000 | 3576.000 | -2144.000 B (-37.48%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.readNs | 85.102 | 79.108 | -5.994 ns (-7.04%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 436.468 | 214.278 | -222.191 ns (-50.91%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 5256.000 | 3112.000 | -2144.000 B (-40.79%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 436.468 | 214.278 | -222.191 ns (-50.91%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 297.675 | 181.619 | -116.057 ns (-38.99%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 5521.471 | 4941.298 | -580.173 ns (-10.51%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 1041.166 | 901.000 | -140.166 ns (-13.46%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 26.198 | 22.660 | -3.538 ns (-13.50%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 224.871 | 230.394 | +5.523 ns (+2.46%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 1092.233 | 1001.648 | -90.585 ns (-8.29%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 1040.062 | 899.250 | -140.812 ns (-13.54%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 28.698 | 24.969 | -3.729 ns (-12.99%) | 0 | smaller |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 33101.823 | 1421.756 | -31680.067 ns (-95.70%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 4952.302 | 2213.744 | -2738.558 ns (-55.30%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1813.291 | 1695.812 | -117.479 ns (-6.48%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 8008.000 | 3552.000 | -4456.000 B (-55.64%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.readNs | 88.384 | 86.920 | -1.464 ns (-1.66%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 261.167 | 219.298 | -41.868 ns (-16.03%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 7568.000 | 3112.000 | -4456.000 B (-58.88%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 261.167 | 219.298 | -41.868 ns (-16.03%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 227.552 | 208.482 | -19.071 ns (-8.38%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4130.990 | 4029.248 | -101.742 ns (-2.46%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 871.625 | 824.750 | -46.875 ns (-5.38%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 27.449 | 27.179 | -0.271 ns (-0.99%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 237.894 | 197.971 | -39.923 ns (-16.78%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1161.690 | 1119.071 | -42.619 ns (-3.67%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 870.417 | 826.666 | -43.750 ns (-5.03%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 27.048 | 26.559 | -0.488 ns (-1.80%) | 0 | within noise |
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
| - | - | cpython-3.14/shallow | compact.callNs | 15580.568 | 1442.716 | -14137.852 ns (-90.74%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 5538.515 | 2091.679 | -3446.835 ns (-62.23%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1977.833 | 1402.125 | -575.708 ns (-29.11%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 5624.000 | 3528.000 | -2096.000 B (-37.27%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.readNs | 126.552 | 88.974 | -37.578 ns (-29.69%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 362.157 | 217.524 | -144.634 ns (-39.94%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 5208.000 | 3112.000 | -2096.000 B (-40.25%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 362.157 | 217.524 | -144.634 ns (-39.94%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 299.025 | 203.252 | -95.773 ns (-32.03%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 3599.121 | 2762.873 | -836.248 ns (-23.23%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 973.437 | 731.792 | -241.646 ns (-24.82%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 35.609 | 27.057 | -8.552 ns (-24.02%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 275.798 | 208.529 | -67.269 ns (-24.39%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 1083.598 | 819.763 | -263.835 ns (-24.35%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 971.354 | 719.104 | -252.250 ns (-25.97%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 37.057 | 27.661 | -9.396 ns (-25.36%) | 0 | smaller |
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
| - | - | cpython-3.14/warmed | compact.callNs | 12499.865 | 1519.006 | -10980.858 ns (-87.85%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 6534.948 | 4263.015 | -2271.933 ns (-34.77%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1912.042 | 1785.625 | -126.417 ns (-6.61%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 5808.000 | 3528.000 | -2280.000 B (-39.26%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.readNs | 95.068 | 88.958 | -6.109 ns (-6.43%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 338.304 | 268.272 | -70.031 ns (-20.70%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.transientBytes | 4970.000 | 2690.000 | -2280.000 B (-45.88%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 338.304 | 268.272 | -70.031 ns (-20.70%) | 0 | smaller |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 21.692 | 132.360 | +110.669 ns (+510.18%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 4204.829 | 3897.015 | -307.815 ns (-7.32%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 811.916 | 751.042 | -60.874 ns (-7.50%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 30.213 | 28.438 | -1.776 ns (-5.88%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 209.983 | 205.705 | -4.278 ns (-2.04%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1870.975 | 1755.837 | -115.138 ns (-6.15%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 834.208 | 731.875 | -102.333 ns (-12.27%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 30.953 | 30.641 | -0.313 ns (-1.01%) | 0 | within noise |
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
| - | - | cpython-3.14/wide | compact.callNs | 20412.692 | 1485.202 | -18927.490 ns (-92.72%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 9127.433 | 2531.902 | -6595.531 ns (-72.26%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.dumpNs | 3182.479 | 2403.625 | -778.854 ns (-24.47%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 6000.000 | 3720.000 | -2280.000 B (-38.00%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.readNs | 112.039 | 82.836 | -29.203 ns (-26.07%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 887.816 | 219.275 | -668.542 ns (-75.30%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.transientBytes | 5456.000 | 3176.000 | -2280.000 B (-41.79%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 887.816 | 219.275 | -668.542 ns (-75.30%) | 0 | smaller |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 154.294 | 220.702 | +66.408 ns (+43.04%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 10254.477 | 7487.965 | -2766.512 ns (-26.98%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1559.542 | 1177.687 | -381.854 ns (-24.49%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 33.746 | 23.443 | -10.303 ns (-30.53%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 374.873 | 253.521 | -121.352 ns (-32.37%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 2415.940 | 1719.229 | -696.710 ns (-28.84%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1682.854 | 1144.000 | -538.854 ns (-32.02%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 36.668 | 23.717 | -12.951 ns (-35.32%) | 0 | smaller |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.308 | 3.263 | -0.045 us/event (-1.35%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 4.007 | 3.726 | -0.281 us/event (-7.02%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.226 | 0.271 | +0.045 ratio (+19.66%) | 0 | larger |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.021 | 0.021 | +0.000 ratio (+0.28%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.066 | 0.068 | +0.003 ratio (+3.95%) | 0 | larger |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.005 | 0.004 | -0.000 ratio (-1.00%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.152 | 0.170 | +0.018 ratio (+11.84%) | 0 | larger |
| - | - | Safe logging alone, at INFO | observed.p50 | 501.167 | 428.584 | -72.583 us (-14.48%) | 0 | faster |
| - | - | Safe logging alone, at INFO | observed.p95 | 531.167 | 445.500 | -85.667 us (-16.13%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 92.625 | 91.375 | -1.250 us (-1.35%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 112.208 | 104.334 | -7.874 us (-7.02%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.227 | 0.271 | +0.044 ratio (+19.38%) | 0 | larger |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.275 | 0.309 | +0.034 ratio (+12.44%) | 0 | larger |
| - | - | Safe logging alone, at INFO | plain.p50 | 408.959 | 337.167 | -71.792 us (-17.55%) | 0 | faster |
| - | - | Safe logging alone, at INFO | plain.p95 | 439.167 | 350.958 | -88.209 us (-20.09%) | 0 | faster |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.225 | 0.271 | +0.046 ratio (+20.25%) | 0 | larger |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.209 | 0.269 | +0.060 ratio (+28.59%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.377 | 2.341 | -0.036 us/event (-1.50%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 3.141 | 2.832 | -0.310 us/event (-9.85%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.163 | 0.195 | +0.032 ratio (+19.79%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.015 | 0.015 | +0.000 ratio (+0.15%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.047 | 0.049 | +0.002 ratio (+3.86%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | -0.000 ratio (-1.15%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.109 | 0.122 | +0.013 ratio (+11.85%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | observed.p50 | 475.125 | 401.917 | -73.208 us (-15.41%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | observed.p95 | 508.375 | 420.750 | -87.625 us (-17.24%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 66.543 | 65.542 | -1.001 us (-1.50%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 87.959 | 79.291 | -8.668 us (-9.85%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.164 | 0.195 | +0.031 ratio (+19.09%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.214 | 0.235 | +0.021 ratio (+9.73%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | plain.p50 | 408.958 | 336.250 | -72.708 us (-17.78%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | plain.p95 | 435.458 | 350.958 | -84.500 us (-19.40%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.162 | 0.195 | +0.033 ratio (+20.70%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.167 | 0.199 | +0.031 ratio (+18.76%) | 0 | larger |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 4.185 | 3.990 | -0.195 us/event (-4.66%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.966 | 4.973 | +0.007 us/event (+0.15%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.271 | 0.330 | +0.058 ratio (+21.56%) | 0 | larger |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.026 | 0.026 | -0.001 ratio (-2.61%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.082 | 0.083 | +0.002 ratio (+1.98%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.006 | 0.005 | -0.000 ratio (-4.22%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.185 | 0.207 | +0.022 ratio (+11.83%) | 0 | larger |
| - | - | fan-out of three, tracing every root | observed.p50 | 550.041 | 450.750 | -99.291 us (-18.05%) | 0 | faster |
| - | - | fan-out of three, tracing every root | observed.p95 | 582.375 | 479.333 | -103.042 us (-17.69%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 117.167 | 111.708 | -5.459 us (-4.66%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 139.042 | 139.250 | +0.208 us (+0.15%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.273 | 0.330 | +0.057 ratio (+20.89%) | 0 | larger |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.324 | 0.406 | +0.082 ratio (+25.29%) | 0 | larger |
| - | - | fan-out of three, tracing every root | plain.p50 | 432.167 | 338.958 | -93.209 us (-21.57%) | 0 | faster |
| - | - | fan-out of three, tracing every root | plain.p95 | 460.167 | 352.375 | -107.792 us (-23.42%) | 0 | faster |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.273 | 0.330 | +0.057 ratio (+20.92%) | 0 | larger |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.266 | 0.360 | +0.095 ratio (+35.67%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 4.116 | 3.807 | -0.310 us/event (-7.52%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 5.153 | 4.613 | -0.540 us/event (-10.48%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.263 | 0.314 | +0.051 ratio (+19.53%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.026 | 0.025 | -0.001 ratio (-5.41%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.080 | 0.080 | -0.001 ratio (-0.67%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.006 | 0.005 | -0.000 ratio (-7.07%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.181 | 0.198 | +0.017 ratio (+9.49%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 554.125 | 445.584 | -108.541 us (-19.59%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 597.583 | 473.917 | -123.666 us (-20.69%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 115.250 | 106.583 | -8.667 us (-7.52%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 144.291 | 129.166 | -15.125 us (-10.48%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.265 | 0.315 | +0.050 ratio (+18.80%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.330 | 0.377 | +0.046 ratio (+14.03%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 438.208 | 339.042 | -99.166 us (-22.63%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 462.417 | 353.916 | -108.501 us (-23.46%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.265 | 0.314 | +0.050 ratio (+18.80%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.292 | 0.339 | +0.047 ratio (+16.00%) | 0 | larger |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.501 | 1.435 | -0.067 us/event (-4.46%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 2.237 | 1.998 | -0.238 us/event (-10.65%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.104 | 0.120 | +0.016 ratio (+15.04%) | 0 | larger |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.010 | 0.009 | -0.000 ratio (-2.95%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.030 | 0.030 | +0.000 ratio (+0.45%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-4.14%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.070 | 0.075 | +0.005 ratio (+7.76%) | 0 | larger |
| - | - | one Handler that keeps nothing | observed.p50 | 446.542 | 376.375 | -70.167 us (-15.71%) | 0 | faster |
| - | - | one Handler that keeps nothing | observed.p95 | 478.250 | 396.459 | -81.791 us (-17.10%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 42.041 | 40.167 | -1.874 us (-4.46%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 62.625 | 55.958 | -6.667 us (-10.65%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.104 | 0.120 | +0.016 ratio (+15.04%) | 0 | larger |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.156 | 0.166 | +0.010 ratio (+6.66%) | 0 | larger |
| - | - | one Handler that keeps nothing | plain.p50 | 404.708 | 336.125 | -68.583 us (-16.95%) | 0 | faster |
| - | - | one Handler that keeps nothing | plain.p95 | 433.250 | 355.125 | -78.125 us (-18.03%) | 0 | faster |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.103 | 0.120 | +0.016 ratio (+15.85%) | 0 | larger |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.104 | 0.116 | +0.013 ratio (+12.06%) | 0 | larger |
| - | - | workload | events | 28.000 | 28.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | workload | statements | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |

## snapshot-delivery

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | | | | | missing on base |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | | | | | missing on base |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 466.314 | 434.381 | -31.934 KiB (-6.85%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 313.757 | 295.456 | -18.301 KiB (-5.83%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.589 | 0.557 | -0.033 ms (-5.55%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 1.002 | 0.810 | -0.192 ms (-19.17%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 6.405 | 5.037 | -1.368 ms (-21.36%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 29634.753 | 39189.752 | +9554.999 roots/s (+32.24%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 6.948 | 5.550 | -1.399 ms (-20.13%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 28618.445 | 36620.533 | +8002.088 roots/s (+27.96%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 9.328 | 8.106 | -1.222 ms (-13.10%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 21608.580 | 25150.773 | +3542.193 roots/s (+16.39%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 279.798 | 231.412 | -48.386 KiB (-17.29%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.406 | 45.315 | +2.909 KiB (+6.86%) | 6 | larger |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 101.862 | 85.505 | -16.357 KiB (-16.06%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 20.794 | 10.883 | -9.911 KiB (-47.66%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1324.136 | 1289.925 | -34.211 KiB (-2.58%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.957 | 521.973 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.742 | 0.728 | -0.014 ms (-1.89%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.304 | 1.043 | -0.261 ms (-19.98%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 10.349 | 8.686 | -1.662 ms (-16.06%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 19481.468 | 23203.202 | +3721.734 roots/s (+19.10%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 11.242 | 9.410 | -1.832 ms (-16.30%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 17979.884 | 21264.154 | +3284.270 roots/s (+18.27%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 14.188 | 12.187 | -2.002 ms (-14.11%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 13776.674 | 16571.096 | +2794.422 roots/s (+20.28%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 730.601 | 705.499 | -25.102 KiB (-3.44%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 35.688 | 31.946 | -3.742 KiB (-10.49%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 207.229 | 199.487 | -7.742 KiB (-3.74%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.772 | 3.491 | -0.281 KiB (-7.46%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1745.881 | 1717.600 | -28.281 KiB (-1.62%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.726 | 869.690 | -0.035 KiB (-0.00%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.890 | 0.878 | -0.012 ms (-1.39%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.568 | 2.208 | -0.361 ms (-14.04%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 27.760 | 23.411 | -4.348 ms (-15.66%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7235.410 | 8490.962 | +1255.552 roots/s (+17.35%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 28.160 | 24.175 | -3.985 ms (-14.15%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 7092.681 | 8296.388 | +1203.708 roots/s (+16.97%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 31.429 | 27.044 | -4.385 ms (-13.95%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6451.084 | 7383.502 | +932.418 roots/s (+14.45%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1164.776 | 1143.415 | -21.361 KiB (-1.83%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 51.764 | 57.243 | +5.479 KiB (+10.59%) | 6 | larger |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 314.458 | 307.840 | -6.618 KiB (-2.10%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 14.881 | 6.164 | -8.717 KiB (-58.58%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1324.800 | 1280.452 | -44.348 KiB (-3.35%) | 3 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 544.988 | 545.004 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 1.053 | 0.848 | -0.205 ms (-19.45%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.944 | 1.513 | -0.431 ms (-22.17%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 17.778 | 16.584 | -1.194 ms (-6.71%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 10899.282 | 12235.066 | +1335.784 roots/s (+12.26%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 18.119 | 16.216 | -1.903 ms (-10.50%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11205.214 | 12351.938 | +1146.724 roots/s (+10.23%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 20.693 | 19.307 | -1.386 ms (-6.70%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 9422.925 | 10478.221 | +1055.297 roots/s (+11.20%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1159.917 | 1139.675 | -20.242 KiB (-1.75%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 45.501 | 40.712 | -4.789 KiB (-10.53%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 320.151 | 313.190 | -6.961 KiB (-2.17%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.093 | 3.812 | -0.281 KiB (-6.87%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 320.560 | 302.880 | -17.680 KiB (-5.52%) | 3 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.927 | 171.809 | -0.118 KiB (-0.07%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.503 | 0.490 | -0.012 ms (-2.44%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.751 | 0.725 | -0.026 ms (-3.46%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.943 | 5.342 | -0.601 ms (-10.12%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 33750.050 | 36814.338 | +3064.287 roots/s (+9.08%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 6.536 | 5.921 | -0.615 ms (-9.41%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 31093.720 | 33828.784 | +2735.064 roots/s (+8.80%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 9.011 | 8.434 | -0.576 ms (-6.40%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 23247.140 | 24077.167 | +830.028 roots/s (+3.57%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 197.614 | 193.528 | -4.086 KiB (-2.07%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 29.255 | 27.891 | -1.364 KiB (-4.66%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 70.800 | 69.677 | -1.123 KiB (-1.59%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 4.384 | 1.921 | -2.463 KiB (-56.18%) | 6 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 8.857 | 6.222 | -2.635 us/projection (-29.75%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 112576.953 | 161803.707 | +49226.754 projections/s (+43.73%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.527 | 43.348 | -0.180 KiB (-0.41%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 38.371 | 47.183 | +8.812 KiB (+22.96%) | 3 | larger |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 579.062 | 566.688 | -12.375 B/projection (-2.14%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 117.375 | 126.875 | +9.500 B/projection (+8.09%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 11.585 | 7.398 | -4.187 us/projection (-36.14%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 83072.003 | 133425.897 | +50353.893 projections/s (+60.61%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 48.465 | 47.434 | -1.031 KiB (-2.13%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 52.425 | 61.369 | +8.944 KiB (+17.06%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 594.062 | 581.688 | -12.375 B/projection (-2.08%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 181.375 | 177.250 | -4.125 B/projection (-2.27%) | 3 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 11.025 | 8.701 | -2.325 ms (-21.08%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18221.091 | 22735.778 | +4514.687 roots/s (+24.78%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 12.187 | 9.740 | -2.446 ms (-20.07%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 17067.092 | 20701.077 | +3633.985 roots/s (+21.29%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 19.115 | 16.881 | -2.234 ms (-11.69%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10839.986 | 12089.919 | +1249.933 roots/s (+11.53%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 18.921 | 16.878 | -2.043 ms (-10.80%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10269.950 | 11744.872 | +1474.922 roots/s (+14.36%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 40.715 | 32.358 | -8.357 us/root (-20.53%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 109.926 | 99.004 | -10.922 KiB (-9.94%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.836 | 50.852 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 39.986 | 34.210 | -5.776 us/root (-14.45%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 109.887 | 103.316 | -6.570 KiB (-5.98%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.836 | 50.852 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 64.849 | 47.181 | -17.668 us/root (-27.24%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 158.391 | 147.043 | -11.348 KiB (-7.16%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.961 | 87.977 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 60.378 | 48.129 | -12.249 us/root (-20.29%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 158.352 | 150.992 | -7.359 KiB (-4.65%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.961 | 87.977 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 86.342 | 65.573 | -20.770 us/root (-24.05%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 231.688 | 218.461 | -13.227 KiB (-5.71%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.461 | 137.477 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 86.714 | 66.971 | -19.742 us/root (-22.77%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 230.594 | 221.883 | -8.711 KiB (-3.78%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.461 | 137.477 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 28.583 | 24.328 | -4.255 us/root (-14.89%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 67.684 | 62.293 | -5.391 KiB (-7.96%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.086 | 24.102 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 29.099 | 24.643 | -4.456 us/root (-15.31%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 73.395 | 68.605 | -4.789 KiB (-6.53%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.086 | 24.102 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 210.102 | 152.691 | -57.410 us/root (-27.32%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 635.336 | 625.758 | -9.578 KiB (-1.51%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.086 | 428.102 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 203.781 | 151.609 | -52.172 us/root (-25.60%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 635.074 | 629.699 | -5.375 KiB (-0.85%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.086 | 428.102 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 77.548 | 57.185 | -20.363 us/root (-26.26%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 205.840 | 195.082 | -10.758 KiB (-5.23%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.086 | 125.102 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 72.871 | 56.809 | -16.062 us/root (-22.04%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 204.754 | 198.129 | -6.625 KiB (-3.24%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.086 | 125.102 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 85.674 | 46.348 | -39.327 us/root (-45.90%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 139.610 | 128.688 | -10.922 KiB (-7.82%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.930 | 35.945 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 86.104 | 47.410 | -38.694 us/root (-44.94%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 139.571 | 133.001 | -6.570 KiB (-4.71%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.930 | 35.945 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 69.785 | 55.465 | -14.320 us/root (-20.52%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 220.773 | 219.008 | -1.766 KiB (-0.80%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.711 | 136.727 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 69.517 | 56.281 | -13.236 us/root (-19.04%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 224.289 | 222.836 | -1.453 KiB (-0.65%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.711 | 136.727 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 185.600 | 143.681 | -41.919 us/root (-22.59%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 763.344 | 761.578 | -1.766 KiB (-0.23%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.211 | 480.227 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 184.986 | 145.512 | -39.474 us/root (-21.34%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 766.859 | 765.406 | -1.453 KiB (-0.19%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.211 | 480.227 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | | | | | missing on base |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | | | | | missing on base |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | | | | | missing on base |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | | | | | missing on base |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | | | | | missing on base |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | | | | | missing on base |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | | | | | missing on base |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | | | | | missing on base |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | | | | | missing on base |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 111.834 | 89.500 | -22.334 us (-19.97%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 22.851 | 20.526 | -2.324 KiB (-10.17%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.796 | 13.761 | -1.035 KiB (-7.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 113.667 | 89.542 | -24.125 us (-21.22%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 22.811 | 20.432 | -2.379 KiB (-10.43%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 14.943 | 13.916 | -1.027 KiB (-6.87%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 113.292 | 87.875 | -25.417 us (-22.43%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 22.851 | 20.526 | -2.324 KiB (-10.17%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.796 | 13.761 | -1.035 KiB (-7.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 108.041 | 90.208 | -17.833 us (-16.51%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 22.811 | 20.432 | -2.379 KiB (-10.43%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 14.943 | 13.916 | -1.027 KiB (-6.87%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 113.708 | 90.666 | -23.042 us (-20.26%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 22.852 | 20.527 | -2.324 KiB (-10.17%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.797 | 13.762 | -1.035 KiB (-7.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 113.125 | 91.292 | -21.833 us (-19.30%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 22.812 | 20.433 | -2.379 KiB (-10.43%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 14.944 | 13.917 | -1.027 KiB (-6.87%) | 3 | smaller |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | | | | | missing on base |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | | | | | missing on base |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | | | | | missing on base |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | | | | | missing on base |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | | | | | missing on base |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | | | | | missing on base |
| 3.13 | result-held-metadata | control-held | large.closed.retainedKiB | | | | | missing on base |
| 3.13 | result-held-metadata | control-held | large.shared.retainedKiB | | | | | missing on base |
| 3.13 | result-held-metadata | control-held | small.closed.retainedKiB | | | | | missing on base |
| 3.13 | result-held-metadata | control-held | small.shared.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | | | | | missing on base |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | | | | | missing on base |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 428.647 | 386.686 | -41.962 KiB (-9.79%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 315.032 | 299.688 | -15.344 KiB (-4.87%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.629 | 0.523 | -0.106 ms (-16.86%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.999 | 0.811 | -0.188 ms (-18.85%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 6.401 | 5.163 | -1.238 ms (-19.34%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 30791.140 | 39521.786 | +8730.646 roots/s (+28.35%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 7.006 | 5.715 | -1.291 ms (-18.43%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 26565.569 | 35831.320 | +9265.751 roots/s (+34.88%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 9.283 | 8.106 | -1.176 ms (-12.67%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 21629.609 | 24774.963 | +3145.354 roots/s (+14.54%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 283.894 | 214.543 | -69.351 KiB (-24.43%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 41.839 | 40.480 | -1.358 KiB (-3.25%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 97.434 | 77.941 | -19.492 KiB (-20.01%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 11.091 | 15.609 | +4.519 KiB (+40.74%) | 6 | larger |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1259.475 | 1224.021 | -35.453 KiB (-2.81%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.363 | 531.383 | +0.020 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.745 | 0.743 | -0.001 ms (-0.16%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.242 | 1.116 | -0.126 ms (-10.13%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 10.320 | 8.673 | -1.647 ms (-15.96%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 19245.961 | 22885.586 | +3639.626 roots/s (+18.91%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 11.378 | 9.525 | -1.854 ms (-16.29%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 17819.290 | 21040.913 | +3221.623 roots/s (+18.08%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 13.934 | 12.411 | -1.523 ms (-10.93%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 14376.939 | 15829.411 | +1452.472 roots/s (+10.10%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 693.486 | 667.924 | -25.562 KiB (-3.69%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 38.004 | 34.473 | -3.531 KiB (-9.29%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 199.057 | 191.596 | -7.461 KiB (-3.75%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.897 | 3.597 | -0.301 KiB (-7.72%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1799.189 | 1770.636 | -28.554 KiB (-1.59%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.792 | 883.759 | -0.033 KiB (-0.00%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.917 | 0.856 | -0.061 ms (-6.63%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.602 | 2.203 | -0.399 ms (-15.33%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 27.572 | 23.307 | -4.265 ms (-15.47%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7310.543 | 8507.848 | +1197.305 roots/s (+16.38%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 28.458 | 24.139 | -4.319 ms (-15.18%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 6855.086 | 8232.344 | +1377.258 roots/s (+20.09%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 31.617 | 27.603 | -4.014 ms (-12.70%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6371.118 | 7312.481 | +941.363 roots/s (+14.78%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1199.479 | 1177.754 | -21.726 KiB (-1.81%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 52.436 | 58.687 | +6.251 KiB (+11.92%) | 6 | larger |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 323.017 | 317.093 | -5.924 KiB (-1.83%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 14.800 | 6.336 | -8.464 KiB (-57.19%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1393.275 | 1347.291 | -45.984 KiB (-3.30%) | 3 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.398 | 554.414 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.932 | 0.857 | -0.074 ms (-7.98%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.808 | 1.610 | -0.198 ms (-10.97%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 18.021 | 16.680 | -1.341 ms (-7.44%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 11214.115 | 11941.249 | +727.134 roots/s (+6.48%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 18.141 | 17.392 | -0.749 ms (-4.13%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11213.145 | 12470.026 | +1256.881 roots/s (+11.21%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 21.074 | 19.528 | -1.546 ms (-7.34%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 9434.964 | 10288.308 | +853.345 roots/s (+9.04%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1166.908 | 1145.486 | -21.422 KiB (-1.84%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 48.164 | 43.727 | -4.438 KiB (-9.21%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 314.291 | 307.869 | -6.422 KiB (-2.04%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.218 | 3.948 | -0.270 KiB (-6.39%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 298.886 | 278.097 | -20.789 KiB (-6.96%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 175.188 | 174.946 | -0.241 KiB (-0.14%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.484 | 0.491 | +0.008 ms (+1.62%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.791 | 0.722 | -0.069 ms (-8.72%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 5.941 | 5.518 | -0.423 ms (-7.13%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 33274.643 | 36853.622 | +3578.979 roots/s (+10.76%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 6.452 | 5.947 | -0.505 ms (-7.83%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 30586.301 | 33536.413 | +2950.112 roots/s (+9.65%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 8.753 | 8.635 | -0.118 ms (-1.35%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 22743.749 | 23533.565 | +789.816 roots/s (+3.47%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 205.014 | 200.928 | -4.086 KiB (-1.99%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 32.738 | 28.921 | -3.817 KiB (-11.66%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 68.316 | 67.291 | -1.025 KiB (-1.50%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 7.323 | 1.944 | -5.379 KiB (-73.45%) | 6 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 9.527 | 6.143 | -3.384 us/projection (-35.52%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 103364.857 | 164736.163 | +61371.306 projections/s (+59.37%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.730 | 45.496 | -0.234 KiB (-0.51%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 42.299 | 51.560 | +9.261 KiB (+21.89%) | 3 | larger |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 604.438 | 599.672 | -4.766 B/projection (-0.79%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 127.250 | 128.266 | +1.016 B/projection (+0.80%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 13.040 | 7.661 | -5.379 us/projection (-41.25%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 77220.921 | 131788.931 | +54568.010 projections/s (+70.66%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 50.730 | 49.652 | -1.078 KiB (-2.13%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 57.438 | 66.832 | +9.394 KiB (+16.35%) | 3 | larger |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 620.438 | 615.672 | -4.766 B/projection (-0.77%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 191.250 | 178.766 | -12.484 B/projection (-6.53%) | 3 | smaller |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 10.662 | 8.821 | -1.841 ms (-17.27%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18814.012 | 22435.044 | +3621.032 roots/s (+19.25%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 11.854 | 9.798 | -2.057 ms (-17.35%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 16940.479 | 20345.880 | +3405.401 roots/s (+20.10%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 18.564 | 16.921 | -1.643 ms (-8.85%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10724.244 | 11830.032 | +1105.788 roots/s (+10.31%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 19.102 | 17.183 | -1.919 ms (-10.05%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10481.036 | 11518.111 | +1037.075 roots/s (+9.89%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-boolean | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-boolean | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-boolean | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-boolean | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-boolean | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-boolean | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-bytes | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-bytes | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-bytes | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-bytes | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-bytes | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-bytes | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-date | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-date | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-date | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-date | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-date | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-date | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-decimal | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-decimal | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-decimal | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-decimal | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-decimal | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-decimal | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float32 | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float32 | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float32 | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float32 | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float32 | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float32 | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float64 | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float64 | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float64 | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float64 | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float64 | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-float64 | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int32 | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int32 | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int32 | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int32 | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int32 | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int32 | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int64 | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int64 | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int64 | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int64 | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int64 | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-int64 | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-time | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-time | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-time | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-time | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-time | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-time | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-timestamp | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-timestamp | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-timestamp | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-uuid | columns.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-uuid | columns.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-uuid | columns.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-uuid | document.elapsedUsPerRoot | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-uuid | document.peakKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | leaf-uuid | document.retainedKiB | | | | | missing on base |
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 42.305 | 32.935 | -9.370 us/root (-22.15%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 107.686 | 97.325 | -10.360 KiB (-9.62%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.094 | 51.109 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 43.870 | 33.327 | -10.543 us/root (-24.03%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 107.646 | 101.036 | -6.610 KiB (-6.14%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.094 | 51.109 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 65.863 | 49.228 | -16.635 us/root (-25.26%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 159.933 | 148.214 | -11.719 KiB (-7.33%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.219 | 88.234 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 64.232 | 50.056 | -14.176 us/root (-22.07%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 158.776 | 151.401 | -7.375 KiB (-4.64%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.219 | 88.234 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 94.495 | 68.637 | -25.858 us/root (-27.36%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 236.351 | 223.218 | -13.133 KiB (-5.56%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.719 | 137.734 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 101.875 | 69.491 | -32.384 us/root (-31.79%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 235.710 | 227.249 | -8.461 KiB (-3.59%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.719 | 137.734 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 30.083 | 24.827 | -5.257 us/root (-17.47%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 66.598 | 61.062 | -5.535 KiB (-8.31%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.344 | 24.359 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 28.160 | 25.079 | -3.081 us/root (-10.94%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 72.309 | 67.422 | -4.887 KiB (-6.76%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.344 | 24.359 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 253.326 | 155.384 | -97.941 us/root (-38.66%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 639.807 | 629.829 | -9.978 KiB (-1.56%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.344 | 428.359 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 208.587 | 157.099 | -51.488 us/root (-24.68%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 639.416 | 633.739 | -5.677 KiB (-0.89%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.344 | 428.359 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 72.326 | 58.341 | -13.984 us/root (-19.34%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 208.990 | 198.134 | -10.856 KiB (-5.19%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.344 | 125.359 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 72.182 | 59.613 | -12.569 us/root (-17.41%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 208.279 | 201.552 | -6.728 KiB (-3.23%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.344 | 125.359 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 88.043 | 47.898 | -40.145 us/root (-45.60%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 137.534 | 127.213 | -10.321 KiB (-7.50%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.188 | 36.203 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 84.397 | 50.958 | -33.439 us/root (-39.62%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 137.495 | 130.924 | -6.571 KiB (-4.78%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.188 | 36.203 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 66.646 | 56.552 | -10.094 us/root (-15.15%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 224.299 | 222.470 | -1.829 KiB (-0.82%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.969 | 136.984 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 85.613 | 56.302 | -29.311 us/root (-34.24%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 227.814 | 226.376 | -1.438 KiB (-0.63%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.969 | 136.984 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 201.048 | 148.523 | -52.525 us/root (-26.13%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 767.150 | 765.188 | -1.962 KiB (-0.26%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.469 | 480.484 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 194.021 | 147.060 | -46.961 us/root (-24.20%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 770.666 | 769.095 | -1.571 KiB (-0.20%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.469 | 480.484 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | | | | | missing on base |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | | | | | missing on base |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | | | | | missing on base |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | | | | | missing on base |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | | | | | missing on base |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | | | | | missing on base |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | | | | | missing on base |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | | | | | missing on base |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | | | | | missing on base |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 116.584 | 91.583 | -25.001 us (-21.44%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 23.821 | 21.005 | -2.816 KiB (-11.82%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 16.188 | 14.981 | -1.207 KiB (-7.46%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 112.666 | 93.292 | -19.374 us (-17.20%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 23.977 | 21.168 | -2.809 KiB (-11.71%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 16.344 | 15.145 | -1.199 KiB (-7.34%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 116.709 | 91.458 | -25.251 us (-21.64%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 23.821 | 21.005 | -2.816 KiB (-11.82%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 16.188 | 14.981 | -1.207 KiB (-7.46%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 116.500 | 93.875 | -22.625 us (-19.42%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 23.977 | 21.164 | -2.812 KiB (-11.73%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 16.344 | 15.145 | -1.199 KiB (-7.34%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 110.292 | 91.875 | -18.417 us (-16.70%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 23.822 | 21.006 | -2.816 KiB (-11.82%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 16.189 | 14.982 | -1.207 KiB (-7.46%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 117.500 | 93.000 | -24.500 us (-20.85%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 23.978 | 21.169 | -2.809 KiB (-11.71%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 16.345 | 15.146 | -1.199 KiB (-7.34%) | 3 | smaller |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | | | | | missing on base |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | | | | | missing on base |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | | | | | missing on base |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | | | | | missing on base |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | | | | | missing on base |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | | | | | missing on base |
| 3.14 | result-held-metadata | control-held | large.closed.retainedKiB | | | | | missing on base |
| 3.14 | result-held-metadata | control-held | large.shared.retainedKiB | | | | | missing on base |
| 3.14 | result-held-metadata | control-held | small.closed.retainedKiB | | | | | missing on base |
| 3.14 | result-held-metadata | control-held | small.shared.retainedKiB | | | | | missing on base |

## write-lowering

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 211.333 | 210.416 | -0.917 us/row (-0.43%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 3536.000 | 1432.000 | -2104.000 B/row (-59.50%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 14602.000 | 10958.000 | -3644.000 B/row (-24.96%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 224.583 | 212.083 | -12.500 us/row (-5.57%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 3586.000 | 1432.000 | -2154.000 B/row (-60.07%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 14602.000 | 11214.000 | -3388.000 B/row (-23.20%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 284.750 | 315.250 | +30.500 us/row (+10.71%) | 9 | slower |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 3536.000 | 1432.000 | -2104.000 B/row (-59.50%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 14602.000 | 9056.000 | -5546.000 B/row (-37.98%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 266.500 | 289.541 | +23.041 us/row (+8.65%) | 9 | slower |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 3486.000 | 1432.000 | -2054.000 B/row (-58.92%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 14552.000 | 9301.000 | -5251.000 B/row (-36.08%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 321.666 | 357.667 | +36.001 us/row (+11.19%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 4426.000 | 1712.000 | -2714.000 B/row (-61.32%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 15442.000 | 12666.000 | -2776.000 B/row (-17.98%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 304.917 | 339.000 | +34.083 us/row (+11.18%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 4326.000 | 1712.000 | -2614.000 B/row (-60.43%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 15442.000 | 13442.000 | -2000.000 B/row (-12.95%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 726.292 | 936.833 | +210.541 us/row (+28.99%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 7736.000 | 2832.000 | -4904.000 B/row (-63.39%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 25739.000 | 20923.000 | -4816.000 B/row (-18.71%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 648.833 | 860.292 | +211.459 us/row (+32.59%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 7736.000 | 2832.000 | -4904.000 B/row (-63.39%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23874.000 | 23982.000 | +108.000 B/row (+0.45%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 283.416 | 287.250 | +3.834 us/row (+1.35%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 5646.000 | 2160.000 | -3486.000 B/row (-61.74%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15866.000 | 15746.000 | -120.000 B/row (-0.76%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 277.250 | 282.958 | +5.708 us/row (+2.06%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5642.000 | 2390.000 | -3252.000 B/row (-57.64%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15748.000 | 16988.000 | +1240.000 B/row (+7.87%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 287.625 | 283.625 | -4.000 us/row (-1.39%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 5696.000 | 2160.000 | -3536.000 B/row (-62.08%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15075.000 | 16031.000 | +956.000 B/row (+6.34%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 266.791 | 276.875 | +10.084 us/row (+3.78%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5592.000 | 2491.000 | -3101.000 B/row (-55.45%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 14922.000 | 16914.000 | +1992.000 B/row (+13.35%) | 9 | larger |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 178.458 | 111.708 | -66.750 us/row (-37.40%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 2472.000 | 1648.000 | -824.000 B/row (-33.33%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 14690.000 | 8580.000 | -6110.000 B/row (-41.59%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 179.250 | 112.125 | -67.125 us/row (-37.45%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 2422.000 | 1648.000 | -774.000 B/row (-31.96%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 14690.000 | 8852.000 | -5838.000 B/row (-39.74%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 217.667 | 149.750 | -67.917 us/row (-31.20%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 3194.000 | 2320.000 | -874.000 B/row (-27.36%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 15426.000 | 10341.000 | -5085.000 B/row (-32.96%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 213.000 | 145.459 | -67.541 us/row (-31.71%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 3194.000 | 2320.000 | -874.000 B/row (-27.36%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 15426.000 | 10497.000 | -4929.000 B/row (-31.95%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 265.917 | 194.375 | -71.542 us/row (-26.90%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 4040.000 | 3216.000 | -824.000 B/row (-20.40%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 16746.000 | 13466.000 | -3280.000 B/row (-19.59%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 280.167 | 194.375 | -85.792 us/row (-30.62%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 4040.000 | 3216.000 | -824.000 B/row (-20.40%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 16746.000 | 13552.000 | -3194.000 B/row (-19.07%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 152.417 | 90.125 | -62.292 us/row (-40.87%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1968.000 | 1144.000 | -824.000 B/row (-41.87%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 14186.000 | 7425.000 | -6761.000 B/row (-47.66%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 145.583 | 87.125 | -58.458 us/row (-40.15%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 2018.000 | 1144.000 | -874.000 B/row (-43.31%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 14186.000 | 7447.000 | -6739.000 B/row (-47.50%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 530.750 | 420.833 | -109.917 us/row (-20.71%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 9432.000 | 8608.000 | -824.000 B/row (-8.74%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27242.000 | 27376.000 | +134.000 B/row (+0.49%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 524.375 | 418.167 | -106.208 us/row (-20.25%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 9432.000 | 8608.000 | -824.000 B/row (-8.74%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 27429.000 | 27539.000 | +110.000 B/row (+0.40%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 265.208 | 175.125 | -90.083 us/row (-33.97%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3914.000 | 3040.000 | -874.000 B/row (-22.33%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 16082.000 | 11920.000 | -4162.000 B/row (-25.88%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 260.708 | 173.167 | -87.541 us/row (-33.58%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3914.000 | 3040.000 | -874.000 B/row (-22.33%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 16082.000 | 12219.000 | -3863.000 B/row (-24.02%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 239.000 | 159.750 | -79.250 us/row (-33.16%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 2522.000 | 1648.000 | -874.000 B/row (-34.66%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 14690.000 | 8350.000 | -6340.000 B/row (-43.16%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 236.875 | 156.042 | -80.833 us/row (-34.12%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 2472.000 | 1648.000 | -824.000 B/row (-33.33%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 14690.000 | 8619.000 | -6071.000 B/row (-41.33%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 266.250 | 210.708 | -55.542 us/row (-20.86%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 3312.000 | 2488.000 | -824.000 B/row (-24.88%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 15530.000 | 11360.000 | -4170.000 B/row (-26.85%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 266.041 | 190.833 | -75.208 us/row (-28.27%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 3362.000 | 2488.000 | -874.000 B/row (-26.00%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 15530.000 | 11640.000 | -3890.000 B/row (-25.05%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 642.875 | 517.416 | -125.459 us/row (-19.52%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 6672.000 | 5848.000 | -824.000 B/row (-12.35%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23321.000 | 23567.000 | +246.000 B/row (+1.05%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 647.584 | 515.958 | -131.626 us/row (-20.33%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 6722.000 | 5848.000 | -874.000 B/row (-13.00%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 24874.000 | 24984.000 | +110.000 B/row (+0.44%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 171.750 | 156.291 | -15.459 us/row (-9.00%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 3024.000 | 1968.000 | -1056.000 B/row (-34.92%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 15138.000 | 9139.000 | -5999.000 B/row (-39.63%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 154.458 | 142.458 | -12.000 us/row (-7.77%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 2824.000 | 2000.000 | -824.000 B/row (-29.18%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 14938.000 | 9459.000 | -5479.000 B/row (-36.68%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 177.250 | 161.750 | -15.500 us/row (-8.74%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 2974.000 | 1968.000 | -1006.000 B/row (-33.83%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 15138.000 | 9927.000 | -5211.000 B/row (-34.42%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 149.042 | 148.167 | -0.875 us/row (-0.59%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 2824.000 | 2000.000 | -824.000 B/row (-29.18%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 14938.000 | 10247.000 | -4691.000 B/row (-31.40%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 204.542 | 193.125 | -11.417 us/row (-5.58%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 3710.000 | 2110.000 | -1600.000 B/row (-43.13%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 14826.000 | 11309.000 | -3517.000 B/row (-23.72%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 186.875 | 177.250 | -9.625 us/row (-5.15%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3610.000 | 2192.000 | -1418.000 B/row (-39.28%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 14626.000 | 11589.000 | -3037.000 B/row (-20.76%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 224.083 | 202.459 | -21.624 us/row (-9.65%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 3710.000 | 2160.000 | -1550.000 B/row (-41.78%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 14826.000 | 11760.000 | -3066.000 B/row (-20.68%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 187.959 | 191.667 | +3.708 us/row (+1.97%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 3610.000 | 2192.000 | -1418.000 B/row (-39.28%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 14626.000 | 12192.000 | -2434.000 B/row (-16.64%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 168.750 | 116.541 | -52.209 us/row (-30.94%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 2744.000 | 1872.000 | -872.000 B/row (-31.78%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 15042.000 | 10210.000 | -4832.000 B/row (-32.12%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 157.167 | 119.375 | -37.792 us/row (-24.05%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2612.000 | 1872.000 | -740.000 B/row (-28.33%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 14810.000 | 10394.000 | -4416.000 B/row (-29.82%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 176.166 | 114.625 | -61.541 us/row (-34.93%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 2744.000 | 1872.000 | -872.000 B/row (-31.78%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 15042.000 | 10242.000 | -4800.000 B/row (-31.91%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 149.834 | 117.834 | -32.000 us/row (-21.36%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 2612.000 | 1872.000 | -740.000 B/row (-28.33%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 14810.000 | 10362.000 | -4448.000 B/row (-30.03%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 206.542 | 87.083 | -119.459 us/row (-57.84%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 3810.000 | 32.000 | -3778.000 B/row (-99.16%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 14826.000 | 7168.000 | -7658.000 B/row (-51.65%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 178.875 | 72.292 | -106.583 us/row (-59.59%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 3560.000 | 32.000 | -3528.000 B/row (-99.10%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 14626.000 | 7184.000 | -7442.000 B/row (-50.88%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 211.209 | 87.542 | -123.667 us/row (-58.55%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 3760.000 | 32.000 | -3728.000 B/row (-99.15%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 14826.000 | 7168.000 | -7658.000 B/row (-51.65%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 185.292 | 73.750 | -111.542 us/row (-60.20%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3510.000 | 32.000 | -3478.000 B/row (-99.09%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 14626.000 | 7184.000 | -7442.000 B/row (-50.88%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3738.167 | 3374.875 | -363.292 us (-9.72%) | 9 | faster |
| 3.13 | model-preparation | model.prepared | retainedBytes | 415992.000 | 426776.000 | +10784.000 B (+2.59%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 436760.000 | 438904.000 | +2144.000 B (+0.49%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | | | | | missing on base |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | | | | | missing on base |
| 3.13 | model-preparation | model.prepared.family | transientBytes | | | | | missing on base |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 107.878 | 24.915 | -82.963 us/row (-76.90%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1583.117 | 913.414 | -669.703 B/row (-42.30%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3677.125 | 2006.625 | -1670.500 B/row (-45.43%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 104.444 | 25.822 | -78.622 us/row (-75.28%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2767.531 | 1914.680 | -852.852 B/row (-30.82%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5831.492 | 2473.766 | -3357.727 B/row (-57.58%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 111.323 | 29.440 | -81.883 us/row (-73.55%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1738.469 | 1057.594 | -680.875 B/row (-39.17%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4206.812 | 2668.031 | -1538.781 B/row (-36.58%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 110.220 | 31.432 | -78.788 us/row (-71.48%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2921.812 | 2048.969 | -872.844 B/row (-29.87%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6271.688 | 3024.812 | -3246.875 B/row (-51.77%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 125.089 | 49.818 | -75.271 us/row (-60.17%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2368.000 | 1528.000 | -840.000 B/row (-35.47%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 5907.625 | 4690.375 | -1217.250 B/row (-20.60%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 134.464 | 49.557 | -84.906 us/row (-63.14%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3568.125 | 2615.375 | -952.750 B/row (-26.70%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 7988.000 | 4926.250 | -3061.750 B/row (-38.33%) | 9 | smaller |
| 3.13 | wire-insert-response | response.insert.family.wire | elapsedUs | | | | | missing on base |
| 3.13 | wire-insert-response | response.insert.family.wire | retainedBytes | | | | | missing on base |
| 3.13 | wire-insert-response | response.insert.family.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 248.000 | 235.292 | -12.708 us/row (-5.12%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 3632.000 | 1440.000 | -2192.000 B/row (-60.35%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 15066.000 | 11126.000 | -3940.000 B/row (-26.15%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 242.583 | 239.167 | -3.416 us/row (-1.41%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 3632.000 | 1440.000 | -2192.000 B/row (-60.35%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 15066.000 | 11646.000 | -3420.000 B/row (-22.70%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 324.250 | 361.333 | +37.083 us/row (+11.44%) | 9 | slower |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 3682.000 | 1440.000 | -2242.000 B/row (-60.89%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 15066.000 | 9320.000 | -5746.000 B/row (-38.14%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 309.833 | 321.875 | +12.042 us/row (+3.89%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 3632.000 | 1440.000 | -2192.000 B/row (-60.35%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 15066.000 | 9741.000 | -5325.000 B/row (-35.34%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 345.583 | 385.167 | +39.584 us/row (+11.45%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 4422.000 | 1720.000 | -2702.000 B/row (-61.10%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 15970.000 | 13026.000 | -2944.000 B/row (-18.43%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 339.375 | 370.000 | +30.625 us/row (+9.02%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 4422.000 | 1720.000 | -2702.000 B/row (-61.10%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 15970.000 | 13946.000 | -2024.000 B/row (-12.67%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 753.250 | 995.667 | +242.417 us/row (+32.18%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 7832.000 | 2840.000 | -4992.000 B/row (-63.74%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 26259.000 | 23717.000 | -2542.000 B/row (-9.68%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 712.292 | 920.042 | +207.750 us/row (+29.17%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 7932.000 | 2840.000 | -5092.000 B/row (-64.20%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 24604.000 | 26934.000 | +2330.000 B/row (+9.47%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 314.959 | 318.209 | +3.250 us/row (+1.03%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 6008.000 | 2326.000 | -3682.000 B/row (-61.28%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15890.000 | 15538.000 | -352.000 B/row (-2.22%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 295.542 | 318.084 | +22.542 us/row (+7.63%) | 9 | slower |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5746.000 | 2207.000 | -3539.000 B/row (-61.59%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15702.000 | 16694.000 | +992.000 B/row (+6.32%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 331.333 | 311.750 | -19.583 us/row (-5.91%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 5908.000 | 2226.000 | -3682.000 B/row (-62.32%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15440.000 | 15907.000 | +467.000 B/row (+3.02%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 300.166 | 311.458 | +11.292 us/row (+3.76%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5696.000 | 2304.000 | -3392.000 B/row (-59.55%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 15370.000 | 17166.000 | +1796.000 B/row (+11.69%) | 9 | larger |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 191.459 | 130.291 | -61.168 us/row (-31.95%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 2528.000 | 1704.000 | -824.000 B/row (-32.59%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 15186.000 | 9116.000 | -6070.000 B/row (-39.97%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 191.916 | 130.208 | -61.708 us/row (-32.15%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 2528.000 | 1704.000 | -824.000 B/row (-32.59%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 15186.000 | 9516.000 | -5670.000 B/row (-37.34%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 234.458 | 165.709 | -68.749 us/row (-29.32%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 3200.000 | 2376.000 | -824.000 B/row (-25.75%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 15858.000 | 10973.000 | -4885.000 B/row (-30.80%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 234.709 | 168.000 | -66.709 us/row (-28.42%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 3200.000 | 2376.000 | -824.000 B/row (-25.75%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 15858.000 | 11257.000 | -4601.000 B/row (-29.01%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 301.584 | 213.709 | -87.875 us/row (-29.14%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 4096.000 | 3272.000 | -824.000 B/row (-20.12%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 17234.000 | 14186.000 | -3048.000 B/row (-17.69%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 295.167 | 215.375 | -79.792 us/row (-27.03%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 4096.000 | 3272.000 | -824.000 B/row (-20.12%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 17234.000 | 14360.000 | -2874.000 B/row (-16.68%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 166.458 | 109.000 | -57.458 us/row (-34.52%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 2016.000 | 1192.000 | -824.000 B/row (-40.87%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 14674.000 | 7961.000 | -6713.000 B/row (-45.75%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 165.458 | 107.959 | -57.499 us/row (-34.75%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1966.000 | 1192.000 | -774.000 B/row (-39.37%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 14674.000 | 8047.000 | -6627.000 B/row (-45.16%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 557.666 | 448.250 | -109.416 us/row (-19.62%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 9488.000 | 8664.000 | -824.000 B/row (-8.68%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27746.000 | 27944.000 | +198.000 B/row (+0.71%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 578.167 | 447.458 | -130.709 us/row (-22.61%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 9488.000 | 8664.000 | -824.000 B/row (-8.68%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 27925.000 | 28171.000 | +246.000 B/row (+0.88%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 268.583 | 197.250 | -71.333 us/row (-26.56%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3920.000 | 3096.000 | -824.000 B/row (-21.02%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 16578.000 | 12488.000 | -4090.000 B/row (-24.67%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 264.167 | 193.458 | -70.709 us/row (-26.77%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3920.000 | 3096.000 | -824.000 B/row (-21.02%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 16578.000 | 12883.000 | -3695.000 B/row (-22.29%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 277.917 | 181.000 | -96.917 us/row (-34.87%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 2528.000 | 1704.000 | -824.000 B/row (-32.59%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 15186.000 | 8918.000 | -6268.000 B/row (-41.27%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 274.292 | 179.875 | -94.417 us/row (-34.42%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 2528.000 | 1704.000 | -824.000 B/row (-32.59%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 15186.000 | 9315.000 | -5871.000 B/row (-38.66%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 301.833 | 212.000 | -89.833 us/row (-29.76%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 3368.000 | 2544.000 | -824.000 B/row (-24.47%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 16090.000 | 11960.000 | -4130.000 B/row (-25.67%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 290.458 | 214.250 | -76.208 us/row (-26.24%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 3368.000 | 2544.000 | -824.000 B/row (-24.47%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 16090.000 | 12336.000 | -3754.000 B/row (-23.33%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 689.041 | 550.917 | -138.124 us/row (-20.05%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 6678.000 | 5904.000 | -774.000 B/row (-11.59%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23817.000 | 24135.000 | +318.000 B/row (+1.34%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 708.292 | 552.667 | -155.625 us/row (-21.97%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 6728.000 | 5904.000 | -824.000 B/row (-12.25%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 25434.000 | 25680.000 | +246.000 B/row (+0.97%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.boolean.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.bytes.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.date.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.decimal.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float32.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.float64.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int32.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.int64.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.string.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.time.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.timestamp.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.columns.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.typed | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.typed | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.typed | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.applyPatches | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.detachJsonContainer | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.occurrenceShape | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.wire | elapsedUs | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.wire | retainedBytes | | | | | missing on base |
| 3.14 | keyed-write | leaf.uuid.document.wire | transientBytes | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 190.333 | 180.667 | -9.666 us/row (-5.08%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 3062.000 | 2064.000 | -998.000 B/row (-32.59%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 15666.000 | 9683.000 | -5983.000 B/row (-38.19%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 166.708 | 170.250 | +3.542 us/row (+2.12%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 2854.000 | 2024.000 | -830.000 B/row (-29.08%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 15406.000 | 10163.000 | -5243.000 B/row (-34.03%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 196.667 | 188.208 | -8.459 us/row (-4.30%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 3112.000 | 1992.000 | -1120.000 B/row (-35.99%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 15666.000 | 10535.000 | -5131.000 B/row (-32.75%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 173.333 | 173.750 | +0.417 us/row (+0.24%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 2904.000 | 2024.000 | -880.000 B/row (-30.30%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 15406.000 | 11015.000 | -4391.000 B/row (-28.50%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 222.250 | 221.959 | -0.291 us/row (-0.13%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 3906.000 | 2176.000 | -1730.000 B/row (-44.29%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 15290.000 | 11589.000 | -3701.000 B/row (-24.21%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 205.208 | 204.125 | -1.083 us/row (-0.53%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3548.000 | 2208.000 | -1340.000 B/row (-37.77%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 15030.000 | 12039.000 | -2991.000 B/row (-19.90%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 239.292 | 236.667 | -2.625 us/row (-1.10%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 3856.000 | 2176.000 | -1680.000 B/row (-43.57%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 15290.000 | 12040.000 | -3250.000 B/row (-21.26%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 212.458 | 229.042 | +16.584 us/row (+7.81%) | 9 | slower |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 3698.000 | 2208.000 | -1490.000 B/row (-40.29%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 15030.000 | 12628.000 | -2402.000 B/row (-15.98%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 192.958 | 134.875 | -58.083 us/row (-30.10%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 2900.000 | 1928.000 | -972.000 B/row (-33.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 15554.000 | 10650.000 | -4904.000 B/row (-31.53%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 170.125 | 139.000 | -31.125 us/row (-18.30%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2560.000 | 1928.000 | -632.000 B/row (-24.69%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 15266.000 | 10762.000 | -4504.000 B/row (-29.50%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 192.667 | 133.958 | -58.709 us/row (-30.47%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 2900.000 | 1928.000 | -972.000 B/row (-33.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 15554.000 | 10794.000 | -4760.000 B/row (-30.60%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 168.917 | 136.042 | -32.875 us/row (-19.46%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 2660.000 | 1928.000 | -732.000 B/row (-27.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 15266.000 | 10898.000 | -4368.000 B/row (-28.61%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 224.667 | 97.417 | -127.250 us/row (-56.64%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 3856.000 | 32.000 | -3824.000 B/row (-99.17%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 15290.000 | 7744.000 | -7546.000 B/row (-49.35%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 202.459 | 84.625 | -117.834 us/row (-58.20%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 3748.000 | 32.000 | -3716.000 B/row (-99.15%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 15030.000 | 7856.000 | -7174.000 B/row (-47.73%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 223.916 | 97.834 | -126.082 us/row (-56.31%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 3806.000 | 32.000 | -3774.000 B/row (-99.16%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 15290.000 | 7744.000 | -7546.000 B/row (-49.35%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 201.917 | 84.042 | -117.875 us/row (-58.38%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3698.000 | 32.000 | -3666.000 B/row (-99.13%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 15030.000 | 7856.000 | -7174.000 B/row (-47.73%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3673.291 | 3321.958 | -351.333 us (-9.56%) | 9 | faster |
| 3.14 | model-preparation | model.prepared | retainedBytes | 427016.000 | 438440.000 | +11424.000 B (+2.68%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 435016.000 | 444984.000 | +9968.000 B (+2.29%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | | | | | missing on base |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | | | | | missing on base |
| 3.14 | model-preparation | model.prepared.family | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 100.807 | 24.938 | -75.870 us/row (-75.26%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1616.133 | 997.680 | -618.453 B/row (-38.27%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3675.094 | 2046.617 | -1628.477 B/row (-44.31%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 109.202 | 25.788 | -83.414 us/row (-76.39%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2808.484 | 1995.680 | -812.805 B/row (-28.94%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5837.680 | 2432.477 | -3405.203 B/row (-58.33%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 110.827 | 29.803 | -81.023 us/row (-73.11%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1810.688 | 1141.531 | -669.156 B/row (-36.96%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4231.000 | 2709.031 | -1521.969 B/row (-35.97%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 119.014 | 30.316 | -88.698 us/row (-74.53%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 3008.031 | 2149.625 | -858.406 B/row (-28.54%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6331.812 | 3035.250 | -3296.562 B/row (-52.06%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 131.417 | 49.339 | -82.078 us/row (-62.46%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2552.000 | 1717.875 | -834.125 B/row (-32.69%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 6091.375 | 4875.625 | -1215.750 B/row (-19.96%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 136.656 | 50.938 | -85.719 us/row (-62.73%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3788.750 | 2823.500 | -965.250 B/row (-25.48%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 8209.750 | 5111.125 | -3098.625 B/row (-37.74%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | elapsedUs | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | retainedBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | transientBytes | | | | | missing on base |
| 3.14 | wire-insert-response | response.insert.family.wire | elapsedUs | | | | | missing on base |
| 3.14 | wire-insert-response | response.insert.family.wire | retainedBytes | | | | | missing on base |
| 3.14 | wire-insert-response | response.insert.family.wire | transientBytes | | | | | missing on base |

Deltas are advisory and never ratchet the Budget Contract.
