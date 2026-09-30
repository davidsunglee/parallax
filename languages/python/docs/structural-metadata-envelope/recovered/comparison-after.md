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
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.398 | 3.491 | +0.093 ratio (+2.72%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.398 | 3.491 | +0.093 ratio (+2.72%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.425 | 3.402 | -0.023 ratio (-0.67%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 1.068 | 0.509 | -0.559 ratio (-52.34%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.likeForLike | 1.023 | 0.490 | -0.534 ratio (-52.15%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 2.790 | 1.536 | -1.254 ratio (-44.95%) | 0 | smaller |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.223 | 2.146 | -0.077 ratio (-3.46%) | 0 | smaller |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.223 | 2.146 | -0.077 ratio (-3.46%) | 0 | smaller |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.245 | 2.157 | -0.087 ratio (-3.88%) | 0 | smaller |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 18871.582 | 1510.108 | -17361.474 ns (-92.00%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 17478.835 | 6811.038 | -10667.798 ns (-61.03%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.dumpNs | 6237.312 | 5916.395 | -320.917 ns (-5.15%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 7754.000 | 4770.000 | -2984.000 B (-38.48%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.readNs | 88.292 | 85.100 | -3.192 ns (-3.61%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 691.459 | 343.561 | -347.899 ns (-50.31%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 6690.000 | 3706.000 | -2984.000 B (-44.60%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 691.459 | 343.561 | -347.899 ns (-50.31%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | -126.869 | 93.333 | +220.202 ns (-173.57%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 14641.494 | 10265.000 | -4376.494 ns (-29.89%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2513.083 | 2526.896 | +13.813 ns (+0.55%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 5184.000 | 4960.000 | -224.000 B (-4.32%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.readNs | 28.658 | 25.196 | -3.462 ns (-12.08%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2392.000 | 2168.000 | -224.000 B (-9.36%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 301.811 | 281.133 | -20.677 ns (-6.85%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 9662.669 | 6079.742 | -3582.927 ns (-37.08%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2578.646 | 2531.125 | -47.521 ns (-1.84%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 27.921 | 26.296 | -1.625 ns (-5.82%) | 0 | smaller |
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
| - | - | cpython-3.13/nullable | compact.callNs | 14391.654 | 1361.179 | -13030.475 ns (-90.54%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 5486.429 | 2298.321 | -3188.108 ns (-58.11%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1952.437 | 1803.146 | -149.291 ns (-7.65%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 5320.000 | 3464.000 | -1856.000 B (-34.89%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.readNs | 81.460 | 75.127 | -6.333 ns (-7.77%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 199.359 | 211.975 | +12.616 ns (+6.33%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.transientBytes | 4856.000 | 3000.000 | -1856.000 B (-38.22%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 199.359 | 211.975 | +12.616 ns (+6.33%) | 0 | larger |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 39.779 | 261.804 | +222.025 ns (+558.15%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5679.992 | 5431.612 | -248.379 ns (-4.37%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 914.042 | 868.333 | -45.709 ns (-5.00%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 22.362 | 20.717 | -1.646 ns (-7.36%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 196.598 | 214.400 | +17.802 ns (+9.05%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1274.006 | 1208.683 | -65.323 ns (-5.13%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 874.583 | 861.354 | -13.229 ns (-1.51%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 22.196 | 21.413 | -0.783 ns (-3.53%) | 0 | smaller |
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
| - | - | cpython-3.13/partial | compact.callNs | 14267.177 | 1345.192 | -12921.985 ns (-90.57%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 4981.469 | 2149.287 | -2832.181 ns (-56.85%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.dumpNs | 1965.562 | 1831.895 | -133.667 ns (-6.80%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 5264.000 | 3432.000 | -1832.000 B (-34.80%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.readNs | 82.337 | 75.433 | -6.904 ns (-8.39%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 244.266 | 213.566 | -30.701 ns (-12.57%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.transientBytes | 4832.000 | 3000.000 | -1832.000 B (-37.91%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 244.266 | 213.566 | -30.701 ns (-12.57%) | 0 | smaller |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 233.269 | 264.500 | +31.231 ns (+13.39%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5336.315 | 5074.187 | -262.127 ns (-4.91%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.dumpNs | 919.854 | 867.417 | -52.437 ns (-5.70%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 23.354 | 21.052 | -2.302 ns (-9.86%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 191.050 | 203.019 | +11.969 ns (+6.26%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 988.950 | 951.440 | -37.510 ns (-3.79%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 937.917 | 886.667 | -51.250 ns (-5.46%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 25.221 | 21.596 | -3.625 ns (-14.37%) | 0 | smaller |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 32657.117 | 1284.673 | -31372.443 ns (-96.07%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 4887.196 | 2229.744 | -2657.452 ns (-54.38%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1737.041 | 1591.000 | -146.041 ns (-8.41%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 7832.000 | 3408.000 | -4424.000 B (-56.49%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.readNs | 85.277 | 80.211 | -5.065 ns (-5.94%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 276.815 | 214.131 | -62.683 ns (-22.64%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 7424.000 | 3000.000 | -4424.000 B (-59.59%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 276.815 | 214.131 | -62.683 ns (-22.64%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 63.748 | 150.506 | +86.758 ns (+136.10%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4305.190 | 4170.160 | -135.029 ns (-3.14%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 831.104 | 794.625 | -36.479 ns (-4.39%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 25.569 | 23.931 | -1.637 ns (-6.40%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 178.725 | 190.210 | +11.485 ns (+6.43%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1108.629 | 1046.144 | -62.485 ns (-5.64%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 811.500 | 769.125 | -42.375 ns (-5.22%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 25.229 | 24.164 | -1.066 ns (-4.22%) | 0 | smaller |
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
| - | - | cpython-3.13/shallow | compact.callNs | 11920.544 | 1333.219 | -10587.325 ns (-88.82%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 3999.519 | 2054.344 | -1945.175 ns (-48.64%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1484.938 | 1354.375 | -130.562 ns (-8.79%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 5216.000 | 3384.000 | -1832.000 B (-35.12%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.readNs | 96.542 | 88.714 | -7.828 ns (-8.11%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 83.619 | 204.991 | +121.372 ns (+145.15%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.transientBytes | 4832.000 | 3000.000 | -1832.000 B (-37.91%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 83.619 | 204.991 | +121.372 ns (+145.15%) | 0 | larger |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 195.321 | 188.856 | -6.464 ns (-3.31%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2795.221 | 2789.769 | -5.452 ns (-0.20%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 759.250 | 700.834 | -58.416 ns (-7.69%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 28.802 | 25.375 | -3.427 ns (-11.90%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 203.525 | 175.575 | -27.950 ns (-13.73%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 799.933 | 781.092 | -18.842 ns (-2.36%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 707.333 | 714.250 | +6.917 ns (+0.98%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 26.792 | 25.943 | -0.849 ns (-3.17%) | 0 | smaller |
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
| - | - | cpython-3.13/warmed | compact.callNs | 12265.302 | 1586.002 | -10679.300 ns (-87.07%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 6552.990 | 4176.831 | -2376.158 ns (-36.26%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1990.291 | 1718.479 | -271.812 ns (-13.66%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 5400.000 | 3384.000 | -2016.000 B (-37.33%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.readNs | 104.578 | 91.828 | -12.750 ns (-12.19%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 0.895 | 245.993 | +245.098 ns (+27398.76%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.transientBytes | 4594.000 | 2578.000 | -2016.000 B (-43.88%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 0.895 | 245.993 | +245.098 ns (+27398.76%) | 0 | larger |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 169.190 | 85.595 | -83.594 ns (-49.41%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 4079.935 | 3910.550 | -169.385 ns (-4.15%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 763.730 | 711.521 | -52.209 ns (-6.84%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 28.505 | 25.302 | -3.203 ns (-11.24%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 144.296 | 190.673 | +46.377 ns (+32.14%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1796.704 | 1759.035 | -37.669 ns (-2.10%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 759.500 | 716.437 | -43.063 ns (-5.67%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 27.323 | 25.870 | -1.453 ns (-5.32%) | 0 | smaller |
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
| - | - | cpython-3.13/wide | compact.callNs | 16785.929 | 1382.158 | -15403.771 ns (-91.77%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 7172.842 | 2612.904 | -4559.938 ns (-63.57%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.dumpNs | 2678.417 | 2407.542 | -270.875 ns (-10.11%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 5680.000 | 3512.000 | -2168.000 B (-38.17%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.readNs | 86.197 | 79.258 | -6.939 ns (-8.05%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 299.291 | 216.351 | -82.940 ns (-27.71%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.transientBytes | 5168.000 | 3000.000 | -2168.000 B (-41.95%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 299.291 | 216.351 | -82.940 ns (-27.71%) | 0 | smaller |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 139.269 | 210.731 | +71.462 ns (+51.31%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 8455.481 | 7945.623 | -509.858 ns (-6.03%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1286.146 | 1187.958 | -98.187 ns (-7.63%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 24.316 | 22.345 | -1.971 ns (-8.11%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 111.317 | 167.508 | +56.192 ns (+50.48%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1941.371 | 1754.929 | -186.442 ns (-9.60%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1242.855 | 1145.666 | -97.188 ns (-7.82%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 24.501 | 22.819 | -1.682 ns (-6.87%) | 0 | smaller |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.247 | 3.170 | -0.077 ratio (-2.37%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.247 | 3.170 | -0.077 ratio (-2.37%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.098 | 3.132 | +0.034 ratio (+1.09%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 1.088 | 0.493 | -0.595 ratio (-54.72%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.likeForLike | 1.015 | 0.474 | -0.540 ratio (-53.25%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 2.746 | 1.478 | -1.268 ratio (-46.17%) | 0 | smaller |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.087 | 2.148 | +0.061 ratio (+2.92%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.087 | 2.148 | +0.061 ratio (+2.92%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.074 | 2.156 | +0.082 ratio (+3.97%) | 0 | larger |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 24692.729 | 1612.133 | -23080.596 ns (-93.47%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 20878.667 | 6584.346 | -14294.321 ns (-68.46%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.dumpNs | 7870.292 | 6112.042 | -1758.250 ns (-22.34%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 8002.000 | 5034.000 | -2968.000 B (-37.09%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.readNs | 114.287 | 85.400 | -28.887 ns (-25.28%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 564.031 | 299.568 | -264.464 ns (-46.89%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 6770.000 | 3802.000 | -2968.000 B (-43.84%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 564.031 | 299.568 | -264.464 ns (-46.89%) | 0 | smaller |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 401.642 | 286.002 | -115.640 ns (-28.79%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 17835.650 | 11036.498 | -6799.152 ns (-38.12%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 3424.896 | 2614.709 | -810.187 ns (-23.66%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5440.000 | 5184.000 | -256.000 B (-4.71%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.readNs | 35.383 | 26.550 | -8.833 ns (-24.96%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2520.000 | 2264.000 | -256.000 B (-10.16%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 411.300 | 237.058 | -174.241 ns (-42.36%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 11723.471 | 6220.192 | -5503.279 ns (-46.94%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 3369.500 | 2616.834 | -752.666 ns (-22.34%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4696.000 | 4744.000 | +48.000 B (+1.02%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 35.863 | 26.600 | -9.263 ns (-25.83%) | 0 | smaller |
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
| - | - | cpython-3.14/nullable | compact.callNs | 17801.646 | 1495.450 | -16306.196 ns (-91.60%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 6787.021 | 2282.300 | -4504.721 ns (-66.37%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.dumpNs | 2161.021 | 1866.854 | -294.167 ns (-13.61%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 5760.000 | 3672.000 | -2088.000 B (-36.25%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.readNs | 91.058 | 78.090 | -12.969 ns (-14.24%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 970.944 | 207.017 | -763.928 ns (-78.68%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 5264.000 | 3176.000 | -2088.000 B (-39.67%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 970.944 | 207.017 | -763.928 ns (-78.68%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 2.873 | 228.417 | +225.544 ns (+7850.21%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 6864.460 | 5485.271 | -1379.190 ns (-20.09%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 1234.771 | 919.938 | -314.833 ns (-25.50%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 31.771 | 23.906 | -7.865 ns (-24.75%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 224.621 | 199.567 | -25.054 ns (-11.15%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1625.567 | 1269.329 | -356.238 ns (-21.91%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 1228.667 | 902.437 | -326.230 ns (-26.55%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 33.969 | 25.490 | -8.479 ns (-24.96%) | 0 | smaller |
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
| - | - | cpython-3.14/partial | compact.callNs | 15459.554 | 1393.679 | -14065.875 ns (-90.98%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 5175.196 | 2160.925 | -3014.271 ns (-58.24%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.dumpNs | 1994.979 | 1856.479 | -138.500 ns (-6.94%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 5720.000 | 3576.000 | -2144.000 B (-37.48%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.readNs | 85.102 | 78.333 | -6.769 ns (-7.95%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 436.468 | 225.827 | -210.642 ns (-48.26%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 5256.000 | 3112.000 | -2144.000 B (-40.79%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 436.468 | 225.827 | -210.642 ns (-48.26%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 297.675 | 203.819 | -93.857 ns (-31.53%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 5521.471 | 5016.285 | -505.185 ns (-9.15%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 1041.166 | 906.021 | -135.145 ns (-12.98%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 26.198 | 23.579 | -2.619 ns (-10.00%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 224.871 | 207.912 | -16.959 ns (-7.54%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 1092.233 | 956.233 | -136.000 ns (-12.45%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 1040.062 | 886.021 | -154.041 ns (-14.81%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 28.698 | 24.787 | -3.910 ns (-13.63%) | 0 | smaller |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 33101.823 | 1412.710 | -31689.113 ns (-95.73%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 4952.302 | 2200.894 | -2751.408 ns (-55.56%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1813.291 | 1663.354 | -149.937 ns (-8.27%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 8008.000 | 3552.000 | -4456.000 B (-55.64%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.readNs | 88.384 | 80.229 | -8.155 ns (-9.23%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 261.167 | 229.962 | -31.204 ns (-11.95%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 7568.000 | 3112.000 | -4456.000 B (-58.88%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 261.167 | 229.962 | -31.204 ns (-11.95%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 227.552 | 208.190 | -19.363 ns (-8.51%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4130.990 | 4026.873 | -104.117 ns (-2.52%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 871.625 | 800.416 | -71.208 ns (-8.17%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 27.449 | 26.458 | -0.991 ns (-3.61%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 237.894 | 189.569 | -48.325 ns (-20.31%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1161.690 | 1095.723 | -65.967 ns (-5.68%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 870.417 | 799.375 | -71.042 ns (-8.16%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 27.048 | 25.988 | -1.059 ns (-3.92%) | 0 | smaller |
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
| - | - | cpython-3.14/shallow | compact.callNs | 15580.568 | 1412.962 | -14167.606 ns (-90.93%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 5538.515 | 2106.996 | -3431.519 ns (-61.96%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1977.833 | 1423.708 | -554.125 ns (-28.02%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 5624.000 | 3528.000 | -2096.000 B (-37.27%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.readNs | 126.552 | 87.552 | -39.000 ns (-30.82%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 362.157 | 211.997 | -150.160 ns (-41.46%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 5208.000 | 3112.000 | -2096.000 B (-40.25%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 362.157 | 211.997 | -150.160 ns (-41.46%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 299.025 | 180.077 | -118.948 ns (-39.78%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 3599.121 | 2839.360 | -759.760 ns (-21.11%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 973.437 | 735.291 | -238.146 ns (-24.46%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 35.609 | 28.766 | -6.844 ns (-19.22%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 275.798 | 204.050 | -71.748 ns (-26.01%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 1083.598 | 810.783 | -272.815 ns (-25.18%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 971.354 | 744.417 | -226.938 ns (-23.36%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 37.057 | 28.047 | -9.010 ns (-24.31%) | 0 | smaller |
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
| - | - | cpython-3.14/warmed | compact.callNs | 12499.865 | 1688.460 | -10811.404 ns (-86.49%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 6534.948 | 4229.227 | -2305.721 ns (-35.28%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1912.042 | 1742.666 | -169.375 ns (-8.86%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 5808.000 | 3528.000 | -2280.000 B (-39.26%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.readNs | 95.068 | 89.443 | -5.625 ns (-5.92%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 338.304 | 233.228 | -105.076 ns (-31.06%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.transientBytes | 4970.000 | 2690.000 | -2280.000 B (-45.88%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 338.304 | 233.228 | -105.076 ns (-31.06%) | 0 | smaller |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 21.692 | 145.202 | +123.510 ns (+569.39%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 4204.829 | 3949.131 | -255.698 ns (-6.08%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 811.916 | 734.000 | -77.916 ns (-9.60%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 30.213 | 28.370 | -1.844 ns (-6.10%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 209.983 | 211.746 | +1.763 ns (+0.84%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1870.975 | 1787.546 | -83.429 ns (-4.46%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 834.208 | 722.416 | -111.792 ns (-13.40%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 30.953 | 28.609 | -2.344 ns (-7.57%) | 0 | smaller |
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
| - | - | cpython-3.14/wide | compact.callNs | 20412.692 | 1450.754 | -18961.938 ns (-92.89%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 9127.433 | 2547.913 | -6579.521 ns (-72.09%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.dumpNs | 3182.479 | 2421.084 | -761.396 ns (-23.92%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 6000.000 | 3720.000 | -2280.000 B (-38.00%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.readNs | 112.039 | 80.668 | -31.371 ns (-28.00%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 887.816 | 227.277 | -660.539 ns (-74.40%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.transientBytes | 5456.000 | 3176.000 | -2280.000 B (-41.79%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 887.816 | 227.277 | -660.539 ns (-74.40%) | 0 | smaller |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 154.294 | 204.417 | +50.123 ns (+32.49%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 10254.477 | 7885.833 | -2368.644 ns (-23.10%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1559.542 | 1168.229 | -391.313 ns (-25.09%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 33.746 | 25.401 | -8.345 ns (-24.73%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 374.873 | 171.269 | -203.604 ns (-54.31%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 2415.940 | 1745.148 | -670.792 ns (-27.77%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1682.854 | 1168.230 | -514.624 ns (-30.58%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 36.668 | 25.645 | -11.023 ns (-30.06%) | 0 | smaller |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.308 | 3.299 | -0.009 us/event (-0.27%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 4.007 | 3.698 | -0.309 us/event (-7.72%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.226 | 0.271 | +0.045 ratio (+19.66%) | 0 | larger |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.021 | 0.021 | +0.000 ratio (+1.30%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.066 | 0.069 | +0.003 ratio (+4.80%) | 0 | larger |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.005 | 0.005 | +0.000 ratio (+0.06%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.152 | 0.171 | +0.019 ratio (+12.29%) | 0 | larger |
| - | - | Safe logging alone, at INFO | observed.p50 | 501.167 | 433.208 | -67.959 us (-13.56%) | 0 | faster |
| - | - | Safe logging alone, at INFO | observed.p95 | 531.167 | 444.875 | -86.292 us (-16.25%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 92.625 | 92.375 | -0.250 us (-0.27%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 112.208 | 103.542 | -8.666 us (-7.72%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.227 | 0.271 | +0.044 ratio (+19.49%) | 0 | larger |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.275 | 0.304 | +0.029 ratio (+10.68%) | 0 | larger |
| - | - | Safe logging alone, at INFO | plain.p50 | 408.959 | 340.833 | -68.126 us (-16.66%) | 0 | faster |
| - | - | Safe logging alone, at INFO | plain.p95 | 439.167 | 349.416 | -89.751 us (-20.44%) | 0 | faster |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.225 | 0.271 | +0.046 ratio (+20.21%) | 0 | larger |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.209 | 0.273 | +0.064 ratio (+30.41%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.377 | 2.375 | -0.002 us/event (-0.06%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 3.141 | 2.696 | -0.445 us/event (-14.16%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.163 | 0.196 | +0.033 ratio (+20.26%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.015 | 0.015 | +0.000 ratio (+1.53%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.047 | 0.050 | +0.002 ratio (+5.09%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | +0.000 ratio (+0.28%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.109 | 0.123 | +0.014 ratio (+12.73%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | observed.p50 | 475.125 | 406.375 | -68.750 us (-14.47%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | observed.p95 | 508.375 | 417.791 | -90.584 us (-17.82%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 66.543 | 66.500 | -0.043 us (-0.06%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 87.959 | 75.500 | -12.459 us (-14.16%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.164 | 0.196 | +0.032 ratio (+19.51%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.214 | 0.221 | +0.007 ratio (+3.14%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | plain.p50 | 408.958 | 339.833 | -69.125 us (-16.90%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | plain.p95 | 435.458 | 348.750 | -86.708 us (-19.91%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.162 | 0.196 | +0.034 ratio (+21.02%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.167 | 0.198 | +0.031 ratio (+18.23%) | 0 | larger |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 4.185 | 3.988 | -0.196 us/event (-4.69%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.966 | 4.429 | -0.537 us/event (-10.82%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.271 | 0.327 | +0.056 ratio (+20.73%) | 0 | larger |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.026 | 0.026 | -0.001 ratio (-2.70%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.082 | 0.083 | +0.001 ratio (+1.77%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.006 | 0.005 | -0.000 ratio (-4.27%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.185 | 0.206 | +0.021 ratio (+11.33%) | 0 | larger |
| - | - | fan-out of three, tracing every root | observed.p50 | 550.041 | 453.000 | -97.041 us (-17.64%) | 0 | faster |
| - | - | fan-out of three, tracing every root | observed.p95 | 582.375 | 466.417 | -115.958 us (-19.91%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 117.167 | 111.667 | -5.500 us (-4.69%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 139.042 | 124.000 | -15.042 us (-10.82%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.273 | 0.327 | +0.055 ratio (+20.04%) | 0 | larger |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.324 | 0.365 | +0.040 ratio (+12.45%) | 0 | larger |
| - | - | fan-out of three, tracing every root | plain.p50 | 432.167 | 341.166 | -91.001 us (-21.06%) | 0 | faster |
| - | - | fan-out of three, tracing every root | plain.p95 | 460.167 | 347.708 | -112.459 us (-24.44%) | 0 | faster |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.273 | 0.328 | +0.055 ratio (+20.18%) | 0 | larger |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.266 | 0.341 | +0.076 ratio (+28.55%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 4.116 | 3.830 | -0.286 us/event (-6.94%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 5.153 | 4.476 | -0.677 us/event (-13.14%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.263 | 0.314 | +0.051 ratio (+19.38%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.026 | 0.025 | -0.001 ratio (-4.87%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.080 | 0.080 | -0.000 ratio (-0.24%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.006 | 0.005 | -0.000 ratio (-6.50%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.181 | 0.198 | +0.017 ratio (+9.66%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 554.125 | 448.459 | -105.666 us (-19.07%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 597.583 | 471.625 | -125.958 us (-21.08%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 115.250 | 107.250 | -8.000 us (-6.94%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 144.291 | 125.334 | -18.957 us (-13.14%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.265 | 0.315 | +0.049 ratio (+18.64%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.330 | 0.364 | +0.034 ratio (+10.26%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 438.208 | 341.583 | -96.625 us (-22.05%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 462.417 | 348.166 | -114.251 us (-24.71%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.265 | 0.313 | +0.048 ratio (+18.28%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.292 | 0.355 | +0.062 ratio (+21.31%) | 0 | larger |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.501 | 1.442 | -0.059 us/event (-3.96%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 2.237 | 1.757 | -0.479 us/event (-21.42%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.104 | 0.119 | +0.015 ratio (+14.53%) | 0 | larger |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.010 | 0.009 | -0.000 ratio (-2.52%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.030 | 0.030 | +0.000 ratio (+0.72%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-3.65%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.070 | 0.075 | +0.005 ratio (+7.67%) | 0 | larger |
| - | - | one Handler that keeps nothing | observed.p50 | 446.542 | 379.959 | -66.583 us (-14.91%) | 0 | faster |
| - | - | one Handler that keeps nothing | observed.p95 | 478.250 | 389.875 | -88.375 us (-18.48%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 42.041 | 40.375 | -1.666 us (-3.96%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 62.625 | 49.208 | -13.417 us (-21.42%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.104 | 0.119 | +0.015 ratio (+14.35%) | 0 | larger |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.156 | 0.145 | -0.011 ratio (-7.17%) | 0 | smaller |
| - | - | one Handler that keeps nothing | plain.p50 | 404.708 | 339.375 | -65.333 us (-16.14%) | 0 | faster |
| - | - | one Handler that keeps nothing | plain.p95 | 433.250 | 347.291 | -85.959 us (-19.84%) | 0 | faster |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.103 | 0.120 | +0.016 ratio (+15.69%) | 0 | larger |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.104 | 0.123 | +0.019 ratio (+18.05%) | 0 | larger |
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
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 466.314 | 433.007 | -33.308 KiB (-7.14%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 313.757 | 295.412 | -18.345 KiB (-5.85%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.589 | 0.501 | -0.088 ms (-14.92%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 1.002 | 0.736 | -0.266 ms (-26.54%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 6.405 | 5.085 | -1.320 ms (-20.60%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 29634.753 | 39309.466 | +9674.713 roots/s (+32.65%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 6.948 | 5.561 | -1.387 ms (-19.97%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 28618.445 | 36340.511 | +7722.066 roots/s (+26.98%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 9.328 | 7.376 | -1.952 ms (-20.92%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 21608.580 | 24922.507 | +3313.927 roots/s (+15.34%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 279.798 | 232.833 | -46.965 KiB (-16.79%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.406 | 43.103 | +0.696 KiB (+1.64%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 101.862 | 86.093 | -15.770 KiB (-15.48%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 20.794 | 12.164 | -8.630 KiB (-41.50%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1324.136 | 1289.925 | -34.211 KiB (-2.58%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.957 | 521.973 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.742 | 0.673 | -0.069 ms (-9.31%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.304 | 1.086 | -0.218 ms (-16.71%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 10.349 | 8.610 | -1.739 ms (-16.80%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 19481.468 | 23401.622 | +3920.155 roots/s (+20.12%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 11.242 | 9.393 | -1.849 ms (-16.45%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 17979.884 | 21562.663 | +3582.779 roots/s (+19.93%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 14.188 | 12.608 | -1.581 ms (-11.14%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 13776.674 | 16483.969 | +2707.295 roots/s (+19.65%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 730.601 | 705.499 | -25.102 KiB (-3.44%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 35.688 | 31.946 | -3.742 KiB (-10.49%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 207.229 | 199.487 | -7.742 KiB (-3.74%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.772 | 3.491 | -0.281 KiB (-7.46%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1745.881 | 1717.554 | -28.327 KiB (-1.62%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.726 | 869.741 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.890 | 0.837 | -0.053 ms (-5.94%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.568 | 2.165 | -0.404 ms (-15.72%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 27.760 | 23.432 | -4.327 ms (-15.59%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7235.410 | 8618.554 | +1383.144 roots/s (+19.12%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 28.160 | 23.894 | -4.265 ms (-15.15%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 7092.681 | 8302.401 | +1209.720 roots/s (+17.06%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 31.429 | 26.905 | -4.524 ms (-14.39%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6451.084 | 7409.225 | +958.141 roots/s (+14.85%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1164.776 | 1143.466 | -21.311 KiB (-1.83%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 51.764 | 60.523 | +8.760 KiB (+16.92%) | 6 | larger |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 314.458 | 307.846 | -6.612 KiB (-2.10%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 14.881 | 6.146 | -8.735 KiB (-58.70%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1324.800 | 1280.452 | -44.348 KiB (-3.35%) | 3 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 544.988 | 545.004 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 1.053 | 0.879 | -0.174 ms (-16.48%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.944 | 1.544 | -0.400 ms (-20.56%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 17.778 | 16.227 | -1.551 ms (-8.72%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 10899.282 | 11783.768 | +884.486 roots/s (+8.12%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 18.119 | 15.961 | -2.158 ms (-11.91%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11205.214 | 12528.973 | +1323.759 roots/s (+11.81%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 20.693 | 19.033 | -1.659 ms (-8.02%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 9422.925 | 10524.862 | +1101.937 roots/s (+11.69%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1159.917 | 1139.675 | -20.242 KiB (-1.75%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 45.501 | 40.712 | -4.789 KiB (-10.53%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 320.151 | 313.190 | -6.961 KiB (-2.17%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.093 | 3.812 | -0.281 KiB (-6.87%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 320.560 | 302.834 | -17.726 KiB (-5.53%) | 3 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.927 | 171.809 | -0.118 KiB (-0.07%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.503 | 0.400 | -0.102 ms (-20.34%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.751 | 0.649 | -0.102 ms (-13.55%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.943 | 5.244 | -0.699 ms (-11.77%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 33750.050 | 37934.166 | +4184.115 roots/s (+12.40%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 6.536 | 5.654 | -0.883 ms (-13.50%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 31093.720 | 34824.246 | +3730.526 roots/s (+12.00%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 9.011 | 7.850 | -1.160 ms (-12.88%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 23247.140 | 25260.499 | +2013.359 roots/s (+8.66%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 197.614 | 193.528 | -4.086 KiB (-2.07%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 29.255 | 35.106 | +5.852 KiB (+20.00%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 70.800 | 69.660 | -1.140 KiB (-1.61%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 4.384 | 1.926 | -2.458 KiB (-56.07%) | 6 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 8.857 | 6.345 | -2.512 us/projection (-28.36%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 112576.953 | 163143.780 | +50566.828 projections/s (+44.92%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.527 | 43.348 | -0.180 KiB (-0.41%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 38.371 | 47.183 | +8.812 KiB (+22.96%) | 3 | larger |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 579.062 | 566.688 | -12.375 B/projection (-2.14%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 117.375 | 126.875 | +9.500 B/projection (+8.09%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 11.585 | 7.347 | -4.238 us/projection (-36.58%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 83072.003 | 136618.440 | +53546.437 projections/s (+64.46%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 48.465 | 47.434 | -1.031 KiB (-2.13%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 52.425 | 61.369 | +8.944 KiB (+17.06%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 594.062 | 581.688 | -12.375 B/projection (-2.08%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 181.375 | 177.250 | -4.125 B/projection (-2.27%) | 3 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 11.025 | 8.678 | -2.347 ms (-21.29%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18221.091 | 23049.109 | +4828.018 roots/s (+26.50%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 12.187 | 9.614 | -2.573 ms (-21.11%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 17067.092 | 20635.397 | +3568.305 roots/s (+20.91%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 19.115 | 16.535 | -2.580 ms (-13.50%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10839.986 | 12126.296 | +1286.309 roots/s (+11.87%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 18.921 | 16.678 | -2.243 ms (-11.85%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10269.950 | 11932.343 | +1662.393 roots/s (+16.19%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 40.715 | 32.525 | -8.190 us/root (-20.12%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 109.926 | 99.004 | -10.922 KiB (-9.94%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.836 | 50.852 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 39.986 | 32.776 | -7.210 us/root (-18.03%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 109.887 | 103.316 | -6.570 KiB (-5.98%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.836 | 50.852 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 64.849 | 47.617 | -17.232 us/root (-26.57%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 158.391 | 147.043 | -11.348 KiB (-7.16%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.961 | 87.977 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 60.378 | 47.147 | -13.230 us/root (-21.91%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 158.352 | 150.992 | -7.359 KiB (-4.65%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.961 | 87.977 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 86.342 | 65.646 | -20.697 us/root (-23.97%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 231.688 | 218.461 | -13.227 KiB (-5.71%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.461 | 137.477 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 86.714 | 67.285 | -19.428 us/root (-22.41%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 230.594 | 221.883 | -8.711 KiB (-3.78%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.461 | 137.477 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 28.583 | 24.202 | -4.381 us/root (-15.33%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 67.684 | 62.293 | -5.391 KiB (-7.96%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.086 | 24.102 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 29.099 | 24.853 | -4.246 us/root (-14.59%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 73.395 | 68.605 | -4.789 KiB (-6.53%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.086 | 24.102 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 210.102 | 152.355 | -57.746 us/root (-27.48%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 635.336 | 625.758 | -9.578 KiB (-1.51%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.086 | 428.102 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 203.781 | 151.146 | -52.635 us/root (-25.83%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 635.074 | 629.699 | -5.375 KiB (-0.85%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.086 | 428.102 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 77.548 | 56.049 | -21.499 us/root (-27.72%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 205.840 | 195.082 | -10.758 KiB (-5.23%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.086 | 125.102 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 72.871 | 56.990 | -15.882 us/root (-21.79%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 204.754 | 198.129 | -6.625 KiB (-3.24%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.086 | 125.102 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 85.674 | 47.100 | -38.574 us/root (-45.02%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 139.610 | 128.688 | -10.922 KiB (-7.82%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.930 | 35.945 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 86.104 | 47.395 | -38.710 us/root (-44.96%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 139.571 | 133.001 | -6.570 KiB (-4.71%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.930 | 35.945 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 69.785 | 55.443 | -14.342 us/root (-20.55%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 220.773 | 219.008 | -1.766 KiB (-0.80%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.711 | 136.727 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 69.517 | 54.898 | -14.619 us/root (-21.03%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 224.289 | 222.836 | -1.453 KiB (-0.65%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.711 | 136.727 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 185.600 | 144.585 | -41.016 us/root (-22.10%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 763.344 | 761.578 | -1.766 KiB (-0.23%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.211 | 480.227 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 184.986 | 143.919 | -41.066 us/root (-22.20%) | 9 | faster |
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
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 111.834 | 90.541 | -21.293 us (-19.04%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 22.851 | 20.526 | -2.324 KiB (-10.17%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.796 | 13.761 | -1.035 KiB (-7.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 113.667 | 91.917 | -21.750 us (-19.13%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 22.811 | 20.428 | -2.383 KiB (-10.45%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 14.943 | 13.912 | -1.031 KiB (-6.90%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 113.292 | 90.875 | -22.417 us (-19.79%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 22.851 | 20.526 | -2.324 KiB (-10.17%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.796 | 13.761 | -1.035 KiB (-7.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 108.041 | 91.875 | -16.166 us (-14.96%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 22.811 | 20.432 | -2.379 KiB (-10.43%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 14.943 | 13.916 | -1.027 KiB (-6.87%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 113.708 | 91.166 | -22.542 us (-19.82%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 22.852 | 20.527 | -2.324 KiB (-10.17%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.797 | 13.762 | -1.035 KiB (-7.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 113.125 | 91.916 | -21.209 us (-18.75%) | 9 | faster |
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
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 428.647 | 395.411 | -33.236 KiB (-7.75%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 315.032 | 298.570 | -16.462 KiB (-5.23%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.629 | 0.530 | -0.099 ms (-15.79%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.999 | 0.765 | -0.234 ms (-23.43%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 6.401 | 5.138 | -1.263 ms (-19.73%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 30791.140 | 37022.756 | +6231.616 roots/s (+20.24%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 7.006 | 5.619 | -1.387 ms (-19.80%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 26565.569 | 36076.663 | +9511.094 roots/s (+35.80%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 9.283 | 8.085 | -1.197 ms (-12.90%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 21629.609 | 25413.500 | +3783.891 roots/s (+17.49%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 283.894 | 214.200 | -69.693 KiB (-24.55%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 41.839 | 43.921 | +2.082 KiB (+4.98%) | 6 | larger |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 97.434 | 76.287 | -21.146 KiB (-21.70%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 11.091 | 12.428 | +1.337 KiB (+12.05%) | 6 | larger |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1259.475 | 1224.021 | -35.453 KiB (-2.81%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.363 | 531.383 | +0.020 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.745 | 0.667 | -0.078 ms (-10.49%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.242 | 0.994 | -0.248 ms (-19.94%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 10.320 | 8.815 | -1.505 ms (-14.58%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 19245.961 | 22775.152 | +3529.192 roots/s (+18.34%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 11.378 | 9.254 | -2.124 ms (-18.67%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 17819.290 | 21608.773 | +3789.484 roots/s (+21.27%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 13.934 | 11.920 | -2.015 ms (-14.46%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 14376.939 | 17235.311 | +2858.372 roots/s (+19.88%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 693.486 | 667.924 | -25.562 KiB (-3.69%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 38.004 | 34.473 | -3.531 KiB (-9.29%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 199.057 | 191.596 | -7.461 KiB (-3.75%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.897 | 3.597 | -0.301 KiB (-7.72%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1799.189 | 1770.685 | -28.505 KiB (-1.58%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.792 | 883.711 | -0.081 KiB (-0.01%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.917 | 0.799 | -0.118 ms (-12.83%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.602 | 2.199 | -0.402 ms (-15.47%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 27.572 | 23.432 | -4.140 ms (-15.01%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7310.543 | 8510.126 | +1199.583 roots/s (+16.41%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 28.458 | 24.274 | -4.183 ms (-14.70%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 6855.086 | 8211.445 | +1356.358 roots/s (+19.79%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 31.617 | 27.605 | -4.012 ms (-12.69%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6371.118 | 7359.852 | +988.735 roots/s (+15.52%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1199.479 | 1177.861 | -21.618 KiB (-1.80%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 52.436 | 59.062 | +6.626 KiB (+12.64%) | 6 | larger |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 323.017 | 317.229 | -5.788 KiB (-1.79%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 14.800 | 6.274 | -8.525 KiB (-57.60%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1393.275 | 1347.291 | -45.984 KiB (-3.30%) | 3 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.398 | 554.414 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.932 | 0.727 | -0.204 ms (-21.93%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.808 | 1.515 | -0.292 ms (-16.17%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 18.021 | 17.473 | -0.548 ms (-3.04%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 11214.115 | 11458.555 | +244.440 roots/s (+2.18%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 18.141 | 16.913 | -1.228 ms (-6.77%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11213.145 | 11767.042 | +553.897 roots/s (+4.94%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 21.074 | 19.365 | -1.710 ms (-8.11%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 9434.964 | 10242.666 | +807.703 roots/s (+8.56%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1166.908 | 1145.486 | -21.422 KiB (-1.84%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 48.164 | 43.727 | -4.438 KiB (-9.21%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 314.291 | 307.869 | -6.422 KiB (-2.04%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.218 | 3.948 | -0.270 KiB (-6.39%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 298.886 | 278.097 | -20.789 KiB (-6.96%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 175.188 | 175.000 | -0.188 KiB (-0.11%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.484 | 0.526 | +0.042 ms (+8.72%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.791 | 0.776 | -0.015 ms (-1.93%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 5.941 | 5.423 | -0.518 ms (-8.72%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 33274.643 | 34188.034 | +913.391 roots/s (+2.75%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 6.452 | 6.576 | +0.123 ms (+1.91%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 30586.301 | 31431.917 | +845.616 roots/s (+2.76%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 8.753 | 9.395 | +0.642 ms (+7.33%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 22743.749 | 21728.306 | -1015.442 roots/s (-4.46%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 205.014 | 200.928 | -4.086 KiB (-1.99%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 32.738 | 31.434 | -1.305 KiB (-3.99%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 68.316 | 67.442 | -0.874 KiB (-1.28%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 7.323 | 1.998 | -5.325 KiB (-72.72%) | 6 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 9.527 | 6.167 | -3.359 us/projection (-35.26%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 103364.857 | 163543.580 | +60178.723 projections/s (+58.22%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.730 | 45.496 | -0.234 KiB (-0.51%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 42.299 | 51.560 | +9.261 KiB (+21.89%) | 3 | larger |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 604.438 | 599.672 | -4.766 B/projection (-0.79%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 127.250 | 128.266 | +1.016 B/projection (+0.80%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 13.040 | 7.609 | -5.431 us/projection (-41.65%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 77220.921 | 132129.034 | +54908.113 projections/s (+71.11%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 50.730 | 49.652 | -1.078 KiB (-2.13%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 57.438 | 66.832 | +9.394 KiB (+16.35%) | 3 | larger |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 620.438 | 615.672 | -4.766 B/projection (-0.77%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 191.250 | 178.766 | -12.484 B/projection (-6.53%) | 3 | smaller |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 10.662 | 9.370 | -1.292 ms (-12.12%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18814.012 | 21259.443 | +2445.432 roots/s (+13.00%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 11.854 | 10.511 | -1.343 ms (-11.33%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 16940.479 | 18977.883 | +2037.405 roots/s (+12.03%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 18.564 | 16.850 | -1.714 ms (-9.23%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10724.244 | 11857.385 | +1133.141 roots/s (+10.57%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 19.102 | 17.084 | -2.018 ms (-10.56%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10481.036 | 11708.516 | +1227.480 roots/s (+11.71%) | 9 | faster |
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
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 42.305 | 32.863 | -9.441 us/root (-22.32%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 107.686 | 97.325 | -10.360 KiB (-9.62%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.094 | 51.109 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 43.870 | 33.620 | -10.250 us/root (-23.36%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 107.646 | 101.036 | -6.610 KiB (-6.14%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.094 | 51.109 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 65.863 | 47.891 | -17.973 us/root (-27.29%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 159.933 | 148.214 | -11.719 KiB (-7.33%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.219 | 88.234 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 64.232 | 48.647 | -15.585 us/root (-24.26%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 158.776 | 151.401 | -7.375 KiB (-4.64%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.219 | 88.234 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 94.495 | 68.923 | -25.572 us/root (-27.06%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 236.351 | 223.218 | -13.133 KiB (-5.56%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.719 | 137.734 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 101.875 | 68.695 | -33.180 us/root (-32.57%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 235.710 | 227.249 | -8.461 KiB (-3.59%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.719 | 137.734 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 30.083 | 24.316 | -5.767 us/root (-19.17%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 66.598 | 61.062 | -5.535 KiB (-8.31%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.344 | 24.359 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 28.160 | 24.865 | -3.296 us/root (-11.70%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 72.309 | 67.422 | -4.887 KiB (-6.76%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.344 | 24.359 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 253.326 | 154.587 | -98.738 us/root (-38.98%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 639.807 | 629.829 | -9.978 KiB (-1.56%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.344 | 428.359 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 208.587 | 155.785 | -52.802 us/root (-25.31%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 639.416 | 633.739 | -5.677 KiB (-0.89%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.344 | 428.359 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 72.326 | 58.184 | -14.142 us/root (-19.55%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 208.990 | 198.134 | -10.856 KiB (-5.19%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.344 | 125.359 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 72.182 | 58.388 | -13.794 us/root (-19.11%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 208.279 | 201.552 | -6.728 KiB (-3.23%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.344 | 125.359 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 88.043 | 48.576 | -39.467 us/root (-44.83%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 137.534 | 127.213 | -10.321 KiB (-7.50%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.188 | 36.203 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 84.397 | 48.583 | -35.814 us/root (-42.43%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 137.495 | 130.924 | -6.571 KiB (-4.78%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.188 | 36.203 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 66.646 | 55.711 | -10.935 us/root (-16.41%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 224.299 | 222.470 | -1.829 KiB (-0.82%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.969 | 136.984 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 85.613 | 56.578 | -29.035 us/root (-33.91%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 227.814 | 226.376 | -1.438 KiB (-0.63%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.969 | 136.984 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 201.048 | 145.680 | -55.368 us/root (-27.54%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 767.150 | 765.188 | -1.962 KiB (-0.26%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.469 | 480.484 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 194.021 | 147.206 | -46.815 us/root (-24.13%) | 9 | faster |
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
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 116.584 | 92.208 | -24.376 us (-20.91%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 23.821 | 21.005 | -2.816 KiB (-11.82%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 16.188 | 14.981 | -1.207 KiB (-7.46%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 112.666 | 93.792 | -18.874 us (-16.75%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 23.977 | 21.168 | -2.809 KiB (-11.71%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 16.344 | 15.145 | -1.199 KiB (-7.34%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 116.709 | 90.833 | -25.876 us (-22.17%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 23.821 | 21.005 | -2.816 KiB (-11.82%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 16.188 | 14.981 | -1.207 KiB (-7.46%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 116.500 | 93.042 | -23.458 us (-20.14%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 23.977 | 21.168 | -2.809 KiB (-11.71%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 16.344 | 15.145 | -1.199 KiB (-7.34%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 110.292 | 92.041 | -18.251 us (-16.55%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 23.822 | 21.006 | -2.816 KiB (-11.82%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 16.189 | 14.982 | -1.207 KiB (-7.46%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 117.500 | 93.333 | -24.167 us (-20.57%) | 9 | faster |
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
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 211.333 | 212.333 | +1.000 us/row (+0.47%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 3536.000 | 1432.000 | -2104.000 B/row (-59.50%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 14602.000 | 10866.000 | -3736.000 B/row (-25.59%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 224.583 | 212.667 | -11.916 us/row (-5.31%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 3586.000 | 1432.000 | -2154.000 B/row (-60.07%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 14602.000 | 11114.000 | -3488.000 B/row (-23.89%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 284.750 | 312.500 | +27.750 us/row (+9.75%) | 9 | slower |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 3536.000 | 1432.000 | -2104.000 B/row (-59.50%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 14602.000 | 8956.000 | -5646.000 B/row (-38.67%) | 9 | smaller |
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
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 14552.000 | 9201.000 | -5351.000 B/row (-36.77%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 321.666 | 353.417 | +31.751 us/row (+9.87%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 4426.000 | 1712.000 | -2714.000 B/row (-61.32%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 15442.000 | 12574.000 | -2868.000 B/row (-18.57%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 304.917 | 341.417 | +36.500 us/row (+11.97%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 4326.000 | 1712.000 | -2614.000 B/row (-60.43%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 15442.000 | 13350.000 | -2092.000 B/row (-13.55%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 726.292 | 945.166 | +218.874 us/row (+30.14%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 7736.000 | 2832.000 | -4904.000 B/row (-63.39%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 25739.000 | 20857.000 | -4882.000 B/row (-18.97%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 648.833 | 865.041 | +216.208 us/row (+33.32%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 7736.000 | 2832.000 | -4904.000 B/row (-63.39%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23874.000 | 23890.000 | +16.000 B/row (+0.07%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 283.416 | 286.959 | +3.543 us/row (+1.25%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 5646.000 | 2160.000 | -3486.000 B/row (-61.74%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15866.000 | 15296.000 | -570.000 B/row (-3.59%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 277.250 | 277.166 | -0.084 us/row (-0.03%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5642.000 | 2288.000 | -3354.000 B/row (-59.45%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15748.000 | 16140.000 | +392.000 B/row (+2.49%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 287.625 | 279.333 | -8.292 us/row (-2.88%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 5696.000 | 2160.000 | -3536.000 B/row (-62.08%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15075.000 | 15481.000 | +406.000 B/row (+2.69%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 266.791 | 270.083 | +3.292 us/row (+1.23%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5592.000 | 2288.000 | -3304.000 B/row (-59.08%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 14922.000 | 16221.000 | +1299.000 B/row (+8.71%) | 9 | larger |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 178.458 | 110.459 | -67.999 us/row (-38.10%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 179.250 | 110.375 | -68.875 us/row (-38.42%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 217.667 | 145.542 | -72.125 us/row (-33.14%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 213.000 | 146.500 | -66.500 us/row (-31.22%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 265.917 | 193.167 | -72.750 us/row (-27.36%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 280.167 | 191.750 | -88.417 us/row (-31.56%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 152.417 | 88.667 | -63.750 us/row (-41.83%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 145.583 | 86.792 | -58.791 us/row (-40.38%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 530.750 | 414.292 | -116.458 us/row (-21.94%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 524.375 | 412.250 | -112.125 us/row (-21.38%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 265.208 | 171.333 | -93.875 us/row (-35.40%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 260.708 | 173.208 | -87.500 us/row (-33.56%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 239.000 | 156.708 | -82.292 us/row (-34.43%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 236.875 | 153.625 | -83.250 us/row (-35.15%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 266.250 | 191.084 | -75.166 us/row (-28.23%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 266.041 | 190.208 | -75.833 us/row (-28.50%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 642.875 | 514.542 | -128.333 us/row (-19.96%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 647.584 | 516.792 | -130.792 us/row (-20.20%) | 9 | faster |
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
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 171.750 | 156.209 | -15.541 us/row (-9.05%) | 9 | faster |
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
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 154.458 | 141.000 | -13.458 us/row (-8.71%) | 9 | faster |
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
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 177.250 | 163.792 | -13.458 us/row (-7.59%) | 9 | faster |
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
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 149.042 | 146.042 | -3.000 us/row (-2.01%) | 9 | within noise |
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
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 204.542 | 192.000 | -12.542 us/row (-6.13%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 3710.000 | 2160.000 | -1550.000 B/row (-41.78%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 14826.000 | 11217.000 | -3609.000 B/row (-24.34%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 186.875 | 180.833 | -6.042 us/row (-3.23%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3610.000 | 2192.000 | -1418.000 B/row (-39.28%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 14626.000 | 11517.000 | -3109.000 B/row (-21.26%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 224.083 | 201.958 | -22.125 us/row (-9.87%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 3710.000 | 2160.000 | -1550.000 B/row (-41.78%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 14826.000 | 11668.000 | -3158.000 B/row (-21.30%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 187.959 | 187.958 | -0.001 us/row (-0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 3610.000 | 2192.000 | -1418.000 B/row (-39.28%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 14626.000 | 12096.000 | -2530.000 B/row (-17.30%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 168.750 | 113.167 | -55.583 us/row (-32.94%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 2744.000 | 1872.000 | -872.000 B/row (-31.78%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 15042.000 | 10118.000 | -4924.000 B/row (-32.74%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 157.167 | 116.292 | -40.875 us/row (-26.01%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2612.000 | 1872.000 | -740.000 B/row (-28.33%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 14810.000 | 10302.000 | -4508.000 B/row (-30.44%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 176.166 | 111.458 | -64.708 us/row (-36.73%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 2744.000 | 1872.000 | -872.000 B/row (-31.78%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 15042.000 | 10142.000 | -4900.000 B/row (-32.58%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 149.834 | 114.083 | -35.751 us/row (-23.86%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 2612.000 | 1872.000 | -740.000 B/row (-28.33%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 14810.000 | 10262.000 | -4548.000 B/row (-30.71%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 206.542 | 85.833 | -120.709 us/row (-58.44%) | 9 | faster |
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
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 178.875 | 72.584 | -106.291 us/row (-59.42%) | 9 | faster |
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
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 211.209 | 86.542 | -124.667 us/row (-59.03%) | 9 | faster |
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
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 185.292 | 73.417 | -111.875 us/row (-60.38%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3510.000 | 32.000 | -3478.000 B/row (-99.09%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 14626.000 | 7184.000 | -7442.000 B/row (-50.88%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3738.167 | 3301.625 | -436.542 us (-11.68%) | 9 | faster |
| 3.13 | model-preparation | model.prepared | retainedBytes | 415992.000 | 426776.000 | +10784.000 B (+2.59%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 436760.000 | 438904.000 | +2144.000 B (+0.49%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | | | | | missing on base |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | | | | | missing on base |
| 3.13 | model-preparation | model.prepared.family | transientBytes | | | | | missing on base |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 107.878 | 24.610 | -83.268 us/row (-77.19%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1583.117 | 911.875 | -671.242 B/row (-42.40%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3677.125 | 2003.484 | -1673.641 B/row (-45.51%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 104.444 | 25.523 | -78.921 us/row (-75.56%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2767.531 | 1913.375 | -854.156 B/row (-30.86%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5831.492 | 2469.828 | -3361.664 B/row (-57.65%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 111.323 | 29.146 | -82.177 us/row (-73.82%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1738.469 | 1032.500 | -705.969 B/row (-40.61%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4206.812 | 2650.812 | -1556.000 B/row (-36.99%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 110.220 | 30.404 | -79.816 us/row (-72.42%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2921.812 | 2038.500 | -883.312 B/row (-30.23%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6271.688 | 3010.688 | -3261.000 B/row (-52.00%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 125.089 | 48.323 | -76.766 us/row (-61.37%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2368.000 | 1523.000 | -845.000 B/row (-35.68%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 5907.625 | 4640.250 | -1267.375 B/row (-21.45%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 134.464 | 49.375 | -85.089 us/row (-63.28%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3568.125 | 2547.000 | -1021.125 B/row (-28.62%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 7988.000 | 4862.750 | -3125.250 B/row (-39.12%) | 9 | smaller |
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
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 248.000 | 234.500 | -13.500 us/row (-5.44%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 3632.000 | 1440.000 | -2192.000 B/row (-60.35%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 15066.000 | 11034.000 | -4032.000 B/row (-26.76%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 242.583 | 237.375 | -5.208 us/row (-2.15%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 3632.000 | 1440.000 | -2192.000 B/row (-60.35%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 15066.000 | 11554.000 | -3512.000 B/row (-23.31%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 324.250 | 342.750 | +18.500 us/row (+5.71%) | 9 | slower |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 3682.000 | 1440.000 | -2242.000 B/row (-60.89%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 15066.000 | 9220.000 | -5846.000 B/row (-38.80%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 309.833 | 318.208 | +8.375 us/row (+2.70%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 3632.000 | 1440.000 | -2192.000 B/row (-60.35%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 15066.000 | 9649.000 | -5417.000 B/row (-35.96%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 345.583 | 383.334 | +37.751 us/row (+10.92%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 4422.000 | 1720.000 | -2702.000 B/row (-61.10%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 15970.000 | 12926.000 | -3044.000 B/row (-19.06%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 339.375 | 372.500 | +33.125 us/row (+9.76%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 4422.000 | 1720.000 | -2702.000 B/row (-61.10%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 15970.000 | 13854.000 | -2116.000 B/row (-13.25%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 753.250 | 998.333 | +245.083 us/row (+32.54%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 7832.000 | 2840.000 | -4992.000 B/row (-63.74%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 26259.000 | 23617.000 | -2642.000 B/row (-10.06%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 712.292 | 912.750 | +200.458 us/row (+28.14%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 7932.000 | 2840.000 | -5092.000 B/row (-64.20%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 24604.000 | 26834.000 | +2230.000 B/row (+9.06%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 314.959 | 313.792 | -1.167 us/row (-0.37%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 6008.000 | 2176.000 | -3832.000 B/row (-63.78%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15890.000 | 14896.000 | -994.000 B/row (-6.26%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 295.542 | 308.417 | +12.875 us/row (+4.36%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5746.000 | 2304.000 | -3442.000 B/row (-59.90%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15702.000 | 16004.000 | +302.000 B/row (+1.92%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 331.333 | 310.083 | -21.250 us/row (-6.41%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 5908.000 | 2176.000 | -3732.000 B/row (-63.17%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15440.000 | 15217.000 | -223.000 B/row (-1.44%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 300.166 | 298.583 | -1.583 us/row (-0.53%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5696.000 | 2304.000 | -3392.000 B/row (-59.55%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 15370.000 | 16325.000 | +955.000 B/row (+6.21%) | 9 | larger |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 191.459 | 130.458 | -61.001 us/row (-31.86%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 191.916 | 130.458 | -61.458 us/row (-32.02%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 234.458 | 170.875 | -63.583 us/row (-27.12%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 234.709 | 167.416 | -67.293 us/row (-28.67%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 301.584 | 218.500 | -83.084 us/row (-27.55%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 295.167 | 214.416 | -80.751 us/row (-27.36%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 166.458 | 108.375 | -58.083 us/row (-34.89%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 165.458 | 106.084 | -59.374 us/row (-35.88%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 557.666 | 440.500 | -117.166 us/row (-21.01%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 578.167 | 442.667 | -135.500 us/row (-23.44%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 268.583 | 192.458 | -76.125 us/row (-28.34%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 264.167 | 193.459 | -70.708 us/row (-26.77%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 277.917 | 181.917 | -96.000 us/row (-34.54%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 274.292 | 180.708 | -93.584 us/row (-34.12%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 301.833 | 217.875 | -83.958 us/row (-27.82%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 290.458 | 214.084 | -76.374 us/row (-26.29%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 689.041 | 553.375 | -135.666 us/row (-19.69%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 708.292 | 553.584 | -154.708 us/row (-21.84%) | 9 | faster |
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
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 190.333 | 179.750 | -10.583 us/row (-5.56%) | 9 | faster |
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
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 166.708 | 172.791 | +6.083 us/row (+3.65%) | 9 | within noise |
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
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 196.667 | 186.791 | -9.876 us/row (-5.02%) | 9 | faster |
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
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 173.333 | 171.708 | -1.625 us/row (-0.94%) | 9 | within noise |
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
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 222.250 | 219.458 | -2.792 us/row (-1.26%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 3906.000 | 2176.000 | -1730.000 B/row (-44.29%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 15290.000 | 11489.000 | -3801.000 B/row (-24.86%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 205.208 | 202.875 | -2.333 us/row (-1.14%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3548.000 | 2208.000 | -1340.000 B/row (-37.77%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 15030.000 | 11949.000 | -3081.000 B/row (-20.50%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 239.292 | 230.125 | -9.167 us/row (-3.83%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 3856.000 | 2176.000 | -1680.000 B/row (-43.57%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 15290.000 | 11948.000 | -3342.000 B/row (-21.86%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 212.458 | 219.500 | +7.042 us/row (+3.31%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 3698.000 | 2208.000 | -1490.000 B/row (-40.29%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 15030.000 | 12536.000 | -2494.000 B/row (-16.59%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 192.958 | 136.459 | -56.499 us/row (-29.28%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 2900.000 | 1928.000 | -972.000 B/row (-33.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 15554.000 | 10550.000 | -5004.000 B/row (-32.17%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 170.125 | 137.000 | -33.125 us/row (-19.47%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2560.000 | 1928.000 | -632.000 B/row (-24.69%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 15266.000 | 10670.000 | -4596.000 B/row (-30.11%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 192.667 | 132.084 | -60.583 us/row (-31.44%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 2900.000 | 1928.000 | -972.000 B/row (-33.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 15554.000 | 10702.000 | -4852.000 B/row (-31.19%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 168.917 | 137.750 | -31.167 us/row (-18.45%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 2660.000 | 1928.000 | -732.000 B/row (-27.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 15266.000 | 10798.000 | -4468.000 B/row (-29.27%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 224.667 | 97.125 | -127.542 us/row (-56.77%) | 9 | faster |
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
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 202.459 | 82.834 | -119.625 us/row (-59.09%) | 9 | faster |
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
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 223.916 | 97.042 | -126.874 us/row (-56.66%) | 9 | faster |
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
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 201.917 | 83.250 | -118.667 us/row (-58.77%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3698.000 | 32.000 | -3666.000 B/row (-99.13%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 15030.000 | 7856.000 | -7174.000 B/row (-47.73%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3673.291 | 3316.333 | -356.958 us (-9.72%) | 9 | faster |
| 3.14 | model-preparation | model.prepared | retainedBytes | 427016.000 | 438440.000 | +11424.000 B (+2.68%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 435016.000 | 444984.000 | +9968.000 B (+2.29%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | | | | | missing on base |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | | | | | missing on base |
| 3.14 | model-preparation | model.prepared.family | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 100.807 | 24.527 | -76.280 us/row (-75.67%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1616.133 | 985.594 | -630.539 B/row (-39.02%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3675.094 | 2050.805 | -1624.289 B/row (-44.20%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 109.202 | 25.059 | -84.144 us/row (-77.05%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2808.484 | 1987.219 | -821.266 B/row (-29.24%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5837.680 | 2436.273 | -3401.406 B/row (-58.27%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 110.827 | 29.635 | -81.191 us/row (-73.26%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1810.688 | 1135.375 | -675.312 B/row (-37.30%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4231.000 | 2696.094 | -1534.906 B/row (-36.28%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 119.014 | 29.749 | -89.266 us/row (-75.00%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 3008.031 | 2141.875 | -866.156 B/row (-28.79%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6331.812 | 3022.219 | -3309.594 B/row (-52.27%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 131.417 | 49.297 | -82.120 us/row (-62.49%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2552.000 | 1742.500 | -809.500 B/row (-31.72%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 6091.375 | 4822.375 | -1269.000 B/row (-20.83%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 136.656 | 51.656 | -85.000 us/row (-62.20%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3788.750 | 2768.500 | -1020.250 B/row (-26.93%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 8209.750 | 5052.875 | -3156.875 B/row (-38.45%) | 9 | smaller |
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
