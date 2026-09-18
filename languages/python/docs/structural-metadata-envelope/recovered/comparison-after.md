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
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.398 | 3.498 | +0.100 ratio (+2.93%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.398 | 3.498 | +0.100 ratio (+2.93%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.425 | 3.386 | -0.039 ratio (-1.15%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 1.068 | 0.800 | -0.268 ratio (-25.10%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.likeForLike | 1.023 | 0.773 | -0.251 ratio (-24.50%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 2.790 | 2.377 | -0.413 ratio (-14.80%) | 0 | smaller |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.223 | 2.198 | -0.024 ratio (-1.10%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.223 | 2.198 | -0.024 ratio (-1.10%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.245 | 2.173 | -0.071 ratio (-3.18%) | 0 | smaller |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 18871.582 | 14777.158 | -4094.423 ns (-21.70%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 17478.835 | 11622.404 | -5856.431 ns (-33.51%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.dumpNs | 6237.312 | 5724.958 | -512.354 ns (-8.21%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 7754.000 | 7324.000 | -430.000 B (-5.55%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.readNs | 88.292 | 86.783 | -1.508 ns (-1.71%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 691.459 | 171.580 | -519.879 ns (-75.19%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 6690.000 | 6260.000 | -430.000 B (-6.43%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 691.459 | 171.580 | -519.879 ns (-75.19%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | -126.869 | 93.640 | +220.508 ns (-173.81%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 14641.494 | 10428.985 | -4212.508 ns (-28.77%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2513.083 | 2437.084 | -76.000 ns (-3.02%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 5184.000 | 4960.000 | -224.000 B (-4.32%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.readNs | 28.658 | 25.504 | -3.154 ns (-11.01%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2392.000 | 2168.000 | -224.000 B (-9.36%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 301.811 | 376.206 | +74.395 ns (+24.65%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 9662.669 | 6092.273 | -3570.396 ns (-36.95%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2578.646 | 2420.354 | -158.292 ns (-6.14%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 27.921 | 26.046 | -1.875 ns (-6.72%) | 0 | smaller |
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
| - | - | cpython-3.13/nullable | compact.callNs | 14391.654 | 9527.265 | -4864.390 ns (-33.80%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 5486.429 | 3480.173 | -2006.256 ns (-36.57%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1952.437 | 1922.062 | -30.375 ns (-1.56%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 5320.000 | 5176.000 | -144.000 B (-2.71%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.readNs | 81.460 | 76.269 | -5.192 ns (-6.37%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 199.359 | 210.977 | +11.618 ns (+5.83%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.transientBytes | 4856.000 | 4712.000 | -144.000 B (-2.97%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 199.359 | 210.977 | +11.618 ns (+5.83%) | 0 | larger |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 39.779 | 118.025 | +78.246 ns (+196.70%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5679.992 | 5373.829 | -306.163 ns (-5.39%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 914.042 | 877.563 | -36.479 ns (-3.99%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 22.362 | 21.458 | -0.904 ns (-4.04%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 196.598 | 179.496 | -17.102 ns (-8.70%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1274.006 | 1244.213 | -29.794 ns (-2.34%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 874.583 | 1102.583 | +228.000 ns (+26.07%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 22.196 | 25.200 | +3.004 ns (+13.53%) | 0 | larger |
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
| - | - | cpython-3.13/partial | compact.callNs | 14267.177 | 9665.981 | -4601.195 ns (-32.25%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 4981.469 | 2973.915 | -2007.554 ns (-40.30%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.dumpNs | 1965.562 | 1868.979 | -96.583 ns (-4.91%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 5264.000 | 5264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.readNs | 82.337 | 74.387 | -7.950 ns (-9.66%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 244.266 | 237.060 | -7.206 ns (-2.95%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.transientBytes | 4832.000 | 4832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 244.266 | 237.060 | -7.206 ns (-2.95%) | 0 | within noise |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 233.269 | 136.539 | -96.730 ns (-41.47%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5336.315 | 5052.627 | -283.687 ns (-5.32%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.dumpNs | 919.854 | 898.125 | -21.729 ns (-2.36%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 23.354 | 23.052 | -0.302 ns (-1.29%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 191.050 | 202.850 | +11.800 ns (+6.18%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 988.950 | 964.337 | -24.613 ns (-2.49%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 937.917 | 894.187 | -43.729 ns (-4.66%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 25.221 | 22.765 | -2.456 ns (-9.74%) | 0 | smaller |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 32657.117 | 22314.075 | -10343.042 ns (-31.67%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 4887.196 | 3398.196 | -1489.000 ns (-30.47%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1737.041 | 1772.084 | +35.042 ns (+2.02%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 7832.000 | 7520.000 | -312.000 B (-3.98%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.readNs | 85.277 | 81.179 | -4.098 ns (-4.81%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 276.815 | 308.901 | +32.087 ns (+11.59%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 7424.000 | 7112.000 | -312.000 B (-4.20%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 276.815 | 308.901 | +32.087 ns (+11.59%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 63.748 | 128.490 | +64.742 ns (+101.56%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4305.190 | 4115.156 | -190.033 ns (-4.41%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 831.104 | 795.792 | -35.313 ns (-4.25%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 25.569 | 24.792 | -0.777 ns (-3.04%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 178.725 | 180.009 | +1.284 ns (+0.72%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1108.629 | 1119.596 | +10.967 ns (+0.99%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 811.500 | 787.625 | -23.875 ns (-2.94%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 25.229 | 22.729 | -2.500 ns (-9.91%) | 0 | smaller |
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
| - | - | cpython-3.13/shallow | compact.callNs | 11920.544 | 8958.996 | -2961.548 ns (-24.84%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 3999.519 | 2868.483 | -1131.035 ns (-28.28%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1484.938 | 1397.146 | -87.792 ns (-5.91%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 5216.000 | 5216.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.readNs | 96.542 | 92.588 | -3.953 ns (-4.09%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 83.619 | 196.270 | +112.651 ns (+134.72%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.transientBytes | 4832.000 | 4832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 83.619 | 196.270 | +112.651 ns (+134.72%) | 0 | larger |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 195.321 | 125.062 | -70.258 ns (-35.97%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2795.221 | 2740.479 | -54.742 ns (-1.96%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 759.250 | 702.354 | -56.896 ns (-7.49%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 28.802 | 25.109 | -3.693 ns (-12.82%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 203.525 | 192.098 | -11.427 ns (-5.61%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 799.933 | 792.506 | -7.427 ns (-0.93%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 707.333 | 701.209 | -6.124 ns (-0.87%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 26.792 | 26.828 | +0.037 ns (+0.14%) | 0 | within noise |
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
| - | - | cpython-3.13/warmed | compact.callNs | 12265.302 | 9197.081 | -3068.221 ns (-25.02%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 6552.990 | 5153.294 | -1399.696 ns (-21.36%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1990.291 | 1828.209 | -162.083 ns (-8.14%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 5400.000 | 5400.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.readNs | 104.578 | 87.812 | -16.766 ns (-16.03%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 0.895 | 391.452 | +390.557 ns (+43659.19%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.transientBytes | 4594.000 | 4594.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 0.895 | 391.452 | +390.557 ns (+43659.19%) | 0 | larger |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 169.190 | 82.915 | -86.275 ns (-50.99%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 4079.935 | 3782.773 | -297.163 ns (-7.28%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 763.730 | 702.771 | -60.958 ns (-7.98%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 28.505 | 26.422 | -2.083 ns (-7.31%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 144.296 | 156.575 | +12.279 ns (+8.51%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1796.704 | 1747.633 | -49.071 ns (-2.73%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 759.500 | 705.479 | -54.021 ns (-7.11%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 27.323 | 26.250 | -1.073 ns (-3.93%) | 0 | smaller |
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
| - | - | cpython-3.13/wide | compact.callNs | 16785.929 | 10708.390 | -6077.540 ns (-36.21%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 7172.842 | 4090.923 | -3081.919 ns (-42.97%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.dumpNs | 2678.417 | 2642.042 | -36.375 ns (-1.36%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 5680.000 | 5400.000 | -280.000 B (-4.93%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.readNs | 86.197 | 83.880 | -2.316 ns (-2.69%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 299.291 | 128.496 | -170.795 ns (-57.07%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.transientBytes | 5168.000 | 4888.000 | -280.000 B (-5.42%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 299.291 | 128.496 | -170.795 ns (-57.07%) | 0 | smaller |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 139.269 | 110.098 | -29.171 ns (-20.95%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 8455.481 | 7841.652 | -613.829 ns (-7.26%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1286.146 | 1261.479 | -24.667 ns (-1.92%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 24.316 | 21.630 | -2.686 ns (-11.05%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 111.317 | 202.273 | +90.956 ns (+81.71%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1941.371 | 1750.519 | -190.852 ns (-9.83%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1242.855 | 1146.938 | -95.917 ns (-7.72%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 24.501 | 22.667 | -1.835 ns (-7.49%) | 0 | smaller |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.247 | 3.377 | +0.130 ratio (+3.99%) | 0 | larger |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.247 | 3.377 | +0.130 ratio (+3.99%) | 0 | larger |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.098 | 3.088 | -0.010 ratio (-0.32%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 1.088 | 0.815 | -0.273 ratio (-25.11%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.likeForLike | 1.015 | 0.786 | -0.229 ratio (-22.57%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 2.746 | 2.376 | -0.370 ratio (-13.47%) | 0 | smaller |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.087 | 2.177 | +0.091 ratio (+4.34%) | 0 | larger |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.087 | 2.177 | +0.091 ratio (+4.34%) | 0 | larger |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.074 | 2.164 | +0.090 ratio (+4.36%) | 0 | larger |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 24692.729 | 15222.202 | -9470.526 ns (-38.35%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 20878.667 | 12139.381 | -8739.286 ns (-41.86%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.dumpNs | 7870.292 | 6552.125 | -1318.167 ns (-16.75%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 8002.000 | 7564.000 | -438.000 B (-5.47%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.readNs | 114.287 | 96.796 | -17.492 ns (-15.30%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 564.031 | -234.385 | -798.416 ns (-141.56%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 6770.000 | 6332.000 | -438.000 B (-6.47%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 564.031 | 0.000 | -564.031 ns (-100.00%) | 0 | smaller |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 401.642 | -69.916 | -471.559 ns (-117.41%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 17835.650 | 11102.250 | -6733.400 ns (-37.75%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 3424.896 | 2581.417 | -843.479 ns (-24.63%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5440.000 | 5184.000 | -256.000 B (-4.71%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.readNs | 35.383 | 27.417 | -7.967 ns (-22.52%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2520.000 | 2264.000 | -256.000 B (-10.16%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 411.300 | 123.196 | -288.104 ns (-70.05%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 11723.471 | 6543.263 | -5180.208 ns (-44.19%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 3369.500 | 2545.208 | -824.291 ns (-24.46%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4696.000 | 4744.000 | +48.000 B (+1.02%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 35.863 | 27.667 | -8.196 ns (-22.85%) | 0 | smaller |
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
| - | - | cpython-3.14/nullable | compact.callNs | 17801.646 | 10298.500 | -7503.146 ns (-42.15%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 6787.021 | 3568.542 | -3218.479 ns (-47.42%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.dumpNs | 2161.021 | 1960.042 | -200.979 ns (-9.30%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 5760.000 | 5696.000 | -64.000 B (-1.11%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.readNs | 91.058 | 83.185 | -7.873 ns (-8.65%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 970.944 | 100.587 | -870.357 ns (-89.64%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 5264.000 | 5200.000 | -64.000 B (-1.22%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 970.944 | 100.587 | -870.357 ns (-89.64%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 2.873 | 173.679 | +170.806 ns (+5945.02%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 6864.460 | 5253.717 | -1610.744 ns (-23.46%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 1234.771 | 915.791 | -318.979 ns (-25.83%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 31.771 | 22.846 | -8.925 ns (-28.09%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 224.621 | 184.760 | -39.861 ns (-17.75%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1625.567 | 1260.885 | -364.681 ns (-22.43%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 1228.667 | 1138.604 | -90.063 ns (-7.33%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 33.969 | 33.750 | -0.219 ns (-0.64%) | 0 | within noise |
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
| - | - | cpython-3.14/partial | compact.callNs | 15459.554 | 10168.341 | -5291.213 ns (-34.23%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 5175.196 | 3113.950 | -2061.246 ns (-39.83%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.dumpNs | 1994.979 | 1852.000 | -142.979 ns (-7.17%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 5720.000 | 5720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.readNs | 85.102 | 78.540 | -6.563 ns (-7.71%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 436.468 | 294.580 | -141.888 ns (-32.51%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 5256.000 | 5256.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 436.468 | 294.580 | -141.888 ns (-32.51%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 297.675 | 84.077 | -213.598 ns (-71.76%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 5521.471 | 5099.069 | -422.402 ns (-7.65%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 1041.166 | 1085.834 | +44.667 ns (+4.29%) | 0 | larger |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 26.198 | 24.935 | -1.263 ns (-4.82%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 224.871 | 196.935 | -27.936 ns (-12.42%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 1092.233 | 987.065 | -105.169 ns (-9.63%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 1040.062 | 950.729 | -89.333 ns (-8.59%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 28.698 | 27.067 | -1.631 ns (-5.68%) | 0 | smaller |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 33101.823 | 23613.098 | -9488.725 ns (-28.67%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 4952.302 | 3412.652 | -1539.650 ns (-31.09%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1813.291 | 1662.667 | -150.625 ns (-8.31%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 8008.000 | 7704.000 | -304.000 B (-3.80%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.readNs | 88.384 | 79.774 | -8.610 ns (-9.74%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 261.167 | 292.350 | +31.183 ns (+11.94%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 7568.000 | 7264.000 | -304.000 B (-4.02%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 261.167 | 292.350 | +31.183 ns (+11.94%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 227.552 | 150.219 | -77.334 ns (-33.98%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4130.990 | 4066.240 | -64.750 ns (-1.57%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 871.625 | 854.604 | -17.021 ns (-1.95%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 27.449 | 25.914 | -1.536 ns (-5.59%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 237.894 | 186.102 | -51.792 ns (-21.77%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1161.690 | 1107.356 | -54.333 ns (-4.68%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 870.417 | 838.646 | -31.771 ns (-3.65%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 27.048 | 26.753 | -0.295 ns (-1.09%) | 0 | within noise |
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
| - | - | cpython-3.14/shallow | compact.callNs | 15580.568 | 8969.521 | -6611.047 ns (-42.43%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 5538.515 | 3043.062 | -2495.452 ns (-45.06%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1977.833 | 1492.916 | -484.916 ns (-24.52%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 5624.000 | 5624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.readNs | 126.552 | 92.547 | -34.005 ns (-26.87%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 362.157 | 306.412 | -55.745 ns (-15.39%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 5208.000 | 5208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 362.157 | 306.412 | -55.745 ns (-15.39%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 299.025 | 223.750 | -75.275 ns (-25.17%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 3599.121 | 2760.458 | -838.662 ns (-23.30%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 973.437 | 741.313 | -232.125 ns (-23.85%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 35.609 | 28.953 | -6.656 ns (-18.69%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 275.798 | 187.842 | -87.956 ns (-31.89%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 1083.598 | 824.096 | -259.502 ns (-23.95%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 971.354 | 754.458 | -216.896 ns (-22.33%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 37.057 | 28.922 | -8.135 ns (-21.95%) | 0 | smaller |
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
| - | - | cpython-3.14/warmed | compact.callNs | 12499.865 | 8962.490 | -3537.375 ns (-28.30%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 6534.948 | 5915.885 | -619.063 ns (-9.47%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1912.042 | 2094.229 | +182.187 ns (+9.53%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 5808.000 | 5808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.readNs | 95.068 | 107.630 | +12.563 ns (+13.21%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 338.304 | 661.790 | +323.486 ns (+95.62%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.transientBytes | 4970.000 | 4970.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 338.304 | 661.790 | +323.486 ns (+95.62%) | 0 | larger |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 21.692 | 375.556 | +353.865 ns (+1631.32%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 4204.829 | 3983.402 | -221.427 ns (-5.27%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 811.916 | 766.208 | -45.708 ns (-5.63%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 30.213 | 30.526 | +0.313 ns (+1.03%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 209.983 | 176.504 | -33.479 ns (-15.94%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1870.975 | 1836.517 | -34.458 ns (-1.84%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 834.208 | 1077.000 | +242.792 ns (+29.10%) | 0 | larger |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 30.953 | 33.865 | +2.911 ns (+9.41%) | 0 | larger |
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
| - | - | cpython-3.14/wide | compact.callNs | 20412.692 | 10975.812 | -9436.879 ns (-46.23%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 9127.433 | 4338.250 | -4789.183 ns (-52.47%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.dumpNs | 3182.479 | 2609.854 | -572.625 ns (-17.99%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 6000.000 | 5808.000 | -192.000 B (-3.20%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.readNs | 112.039 | 90.297 | -21.742 ns (-19.41%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 887.816 | 354.789 | -533.027 ns (-60.04%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.transientBytes | 5456.000 | 5264.000 | -192.000 B (-3.52%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 887.816 | 354.789 | -533.027 ns (-60.04%) | 0 | smaller |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 154.294 | -218.048 | -372.341 ns (-241.32%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 10254.477 | 8057.402 | -2197.075 ns (-21.43%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1559.542 | 1229.583 | -329.959 ns (-21.16%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 33.746 | 24.273 | -9.473 ns (-28.07%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 374.873 | 252.198 | -122.675 ns (-32.72%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 2415.940 | 1739.865 | -676.075 ns (-27.98%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1682.854 | 1226.188 | -456.666 ns (-27.14%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 36.668 | 24.595 | -12.073 ns (-32.92%) | 0 | smaller |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.308 | 3.235 | -0.073 us/event (-2.20%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 4.007 | 3.994 | -0.013 us/event (-0.33%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.226 | 0.241 | +0.015 ratio (+6.60%) | 0 | larger |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.021 | 0.021 | -0.000 ratio (-1.45%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.066 | 0.066 | +0.000 ratio (+0.20%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.005 | 0.004 | -0.000 ratio (-2.04%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.152 | 0.157 | +0.005 ratio (+3.54%) | 0 | larger |
| - | - | Safe logging alone, at INFO | observed.p50 | 501.167 | 466.042 | -35.125 us (-7.01%) | 0 | faster |
| - | - | Safe logging alone, at INFO | observed.p95 | 531.167 | 488.541 | -42.626 us (-8.02%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 92.625 | 90.583 | -2.042 us (-2.20%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 112.208 | 111.833 | -0.375 us (-0.33%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.227 | 0.242 | +0.015 ratio (+6.67%) | 0 | larger |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.275 | 0.299 | +0.025 ratio (+8.91%) | 0 | larger |
| - | - | Safe logging alone, at INFO | plain.p50 | 408.959 | 375.167 | -33.792 us (-8.26%) | 0 | faster |
| - | - | Safe logging alone, at INFO | plain.p95 | 439.167 | 400.042 | -39.125 us (-8.91%) | 0 | faster |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.225 | 0.242 | +0.017 ratio (+7.43%) | 0 | larger |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.209 | 0.221 | +0.012 ratio (+5.60%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.377 | 2.317 | -0.060 us/event (-2.51%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 3.141 | 3.153 | +0.012 us/event (+0.38%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.163 | 0.173 | +0.011 ratio (+6.62%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.015 | 0.015 | -0.000 ratio (-1.73%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.047 | 0.047 | -0.000 ratio (-0.02%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | -0.000 ratio (-2.34%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.109 | 0.113 | +0.004 ratio (+3.44%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | observed.p50 | 475.125 | 439.083 | -36.042 us (-7.59%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | observed.p95 | 508.375 | 461.916 | -46.459 us (-9.14%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 66.543 | 64.875 | -1.668 us (-2.51%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 87.959 | 88.292 | +0.333 us (+0.38%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.164 | 0.174 | +0.010 ratio (+6.31%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.214 | 0.237 | +0.023 ratio (+10.61%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | plain.p50 | 408.958 | 373.958 | -35.000 us (-8.56%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | plain.p95 | 435.458 | 394.000 | -41.458 us (-9.52%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.162 | 0.174 | +0.012 ratio (+7.64%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.167 | 0.172 | +0.005 ratio (+2.94%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 4.185 | 3.938 | -0.247 us/event (-5.90%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.966 | 4.853 | -0.113 us/event (-2.28%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.271 | 0.293 | +0.022 ratio (+8.21%) | 0 | larger |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.026 | 0.025 | -0.001 ratio (-4.69%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.082 | 0.080 | -0.002 ratio (-2.05%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.006 | 0.005 | -0.000 ratio (-5.64%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.185 | 0.191 | +0.006 ratio (+3.31%) | 0 | larger |
| - | - | fan-out of three, tracing every root | observed.p50 | 550.041 | 486.209 | -63.832 us (-11.60%) | 0 | faster |
| - | - | fan-out of three, tracing every root | observed.p95 | 582.375 | 512.417 | -69.958 us (-12.01%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 117.167 | 110.250 | -6.917 us (-5.90%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 139.042 | 135.875 | -3.167 us (-2.28%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.273 | 0.295 | +0.022 ratio (+8.03%) | 0 | larger |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.324 | 0.364 | +0.039 ratio (+12.09%) | 0 | larger |
| - | - | fan-out of three, tracing every root | plain.p50 | 432.167 | 375.791 | -56.376 us (-13.04%) | 0 | faster |
| - | - | fan-out of three, tracing every root | plain.p95 | 460.167 | 397.042 | -63.125 us (-13.72%) | 0 | faster |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.273 | 0.294 | +0.021 ratio (+7.73%) | 0 | larger |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.266 | 0.291 | +0.025 ratio (+9.42%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 4.116 | 3.757 | -0.359 us/event (-8.71%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 5.153 | 4.885 | -0.268 us/event (-5.20%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.263 | 0.280 | +0.017 ratio (+6.47%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.026 | 0.024 | -0.002 ratio (-7.41%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.080 | 0.076 | -0.004 ratio (-4.57%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.006 | 0.005 | -0.000 ratio (-8.43%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.181 | 0.183 | +0.002 ratio (+1.20%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 554.125 | 481.125 | -73.000 us (-13.17%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 597.583 | 512.375 | -85.208 us (-14.26%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 115.250 | 105.208 | -10.042 us (-8.71%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 144.291 | 136.792 | -7.499 us (-5.20%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.265 | 0.281 | +0.016 ratio (+6.03%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.330 | 0.365 | +0.035 ratio (+10.49%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 438.208 | 375.708 | -62.500 us (-14.26%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 462.417 | 393.917 | -68.500 us (-14.81%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.265 | 0.281 | +0.016 ratio (+6.07%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.292 | 0.301 | +0.008 ratio (+2.88%) | 0 | within noise |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.501 | 1.469 | -0.033 us/event (-2.18%) | 0 | within noise |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 2.237 | 2.216 | -0.021 us/event (-0.93%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.104 | 0.110 | +0.006 ratio (+5.79%) | 0 | larger |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.010 | 0.009 | -0.000 ratio (-1.50%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.030 | 0.030 | -0.000 ratio (-0.01%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-2.03%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.070 | 0.072 | +0.002 ratio (+3.02%) | 0 | larger |
| - | - | one Handler that keeps nothing | observed.p50 | 446.542 | 415.500 | -31.042 us (-6.95%) | 0 | faster |
| - | - | one Handler that keeps nothing | observed.p95 | 478.250 | 436.959 | -41.291 us (-8.63%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 42.041 | 41.125 | -0.916 us (-2.18%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 62.625 | 62.042 | -0.583 us (-0.93%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.104 | 0.111 | +0.006 ratio (+6.15%) | 0 | larger |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.156 | 0.166 | +0.010 ratio (+6.19%) | 0 | larger |
| - | - | one Handler that keeps nothing | plain.p50 | 404.708 | 374.208 | -30.500 us (-7.54%) | 0 | faster |
| - | - | one Handler that keeps nothing | plain.p95 | 433.250 | 393.584 | -39.666 us (-9.16%) | 0 | faster |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.103 | 0.110 | +0.007 ratio (+6.75%) | 0 | larger |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.104 | 0.110 | +0.006 ratio (+6.10%) | 0 | larger |
| - | - | workload | events | 28.000 | 28.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | workload | statements | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |

## snapshot-delivery

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 466.314 | 468.576 | +2.262 KiB (+0.49%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 313.757 | 315.021 | +1.264 KiB (+0.40%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.589 | 0.568 | -0.022 ms (-3.66%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 1.002 | 0.978 | -0.024 ms (-2.39%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 6.405 | 5.678 | -0.726 ms (-11.34%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 29634.753 | 35397.446 | +5762.693 roots/s (+19.45%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 6.948 | 6.376 | -0.573 ms (-8.24%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 28618.445 | 31691.327 | +3072.882 roots/s (+10.74%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 9.328 | 8.444 | -0.884 ms (-9.48%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 21608.580 | 23280.177 | +1671.597 roots/s (+7.74%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 279.798 | 281.954 | +2.156 KiB (+0.77%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.406 | 42.740 | +0.334 KiB (+0.79%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 101.862 | 104.854 | +2.991 KiB (+2.94%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 20.794 | 16.886 | -3.908 KiB (-18.79%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1324.136 | 1324.464 | +0.328 KiB (+0.02%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.957 | 521.957 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.742 | 0.778 | +0.036 ms (+4.82%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.304 | 1.215 | -0.089 ms (-6.82%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 10.349 | 8.732 | -1.617 ms (-15.62%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 19481.468 | 23082.140 | +3600.672 roots/s (+18.48%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 11.242 | 9.587 | -1.654 ms (-14.72%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 17979.884 | 20600.150 | +2620.266 roots/s (+14.57%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 14.188 | 12.649 | -1.539 ms (-10.85%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 13776.674 | 14924.909 | +1148.235 roots/s (+8.33%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 730.601 | 730.593 | -0.008 KiB (-0.00%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 35.688 | 35.087 | -0.602 KiB (-1.69%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 207.229 | 207.159 | -0.070 KiB (-0.03%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.772 | 3.772 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1745.881 | 1745.881 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.726 | 869.626 | -0.100 KiB (-0.01%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.890 | 0.804 | -0.086 ms (-9.72%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.568 | 2.371 | -0.198 ms (-7.70%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 27.760 | 23.718 | -4.041 ms (-14.56%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7235.410 | 8421.526 | +1186.116 roots/s (+16.39%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 28.160 | 24.473 | -3.687 ms (-13.09%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 7092.681 | 8063.798 | +971.117 roots/s (+13.69%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 31.429 | 27.233 | -4.196 ms (-13.35%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6451.084 | 7234.222 | +783.138 roots/s (+12.14%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1164.776 | 1164.776 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 51.764 | 49.731 | -2.032 KiB (-3.93%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 314.458 | 314.157 | -0.301 KiB (-0.10%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 14.881 | 16.848 | +1.967 KiB (+13.22%) | 6 | larger |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1324.800 | 1324.800 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 544.988 | 544.988 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 1.053 | 0.878 | -0.175 ms (-16.58%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.944 | 1.766 | -0.177 ms (-9.13%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 17.778 | 16.296 | -1.481 ms (-8.33%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 10899.282 | 12320.329 | +1421.047 roots/s (+13.04%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 18.119 | 16.189 | -1.931 ms (-10.65%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11205.214 | 12236.376 | +1031.163 roots/s (+9.20%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 20.693 | 19.468 | -1.225 ms (-5.92%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 9422.925 | 10338.567 | +915.642 roots/s (+9.72%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1159.917 | 1160.909 | +0.992 KiB (+0.09%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 45.501 | 44.899 | -0.602 KiB (-1.32%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 320.151 | 321.144 | +0.992 KiB (+0.31%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.093 | 4.093 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 320.560 | 320.313 | -0.246 KiB (-0.08%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.927 | 172.379 | +0.452 KiB (+0.26%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.503 | 0.472 | -0.031 ms (-6.11%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.751 | 0.708 | -0.044 ms (-5.82%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.943 | 5.213 | -0.730 ms (-12.29%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 33750.050 | 38074.388 | +4324.337 roots/s (+12.81%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 6.536 | 5.667 | -0.869 ms (-13.30%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 31093.720 | 35339.073 | +4245.353 roots/s (+13.65%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 9.011 | 7.875 | -1.136 ms (-12.60%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 23247.140 | 25572.861 | +2325.721 roots/s (+10.00%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 197.614 | 197.614 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 29.255 | 29.038 | -0.217 KiB (-0.74%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 70.800 | 70.830 | +0.030 KiB (+0.04%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 4.384 | 5.556 | +1.172 KiB (+26.73%) | 6 | larger |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 8.857 | 5.997 | -2.860 us/projection (-32.29%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 112576.953 | 167703.887 | +55126.934 projections/s (+48.97%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.527 | 43.527 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 38.371 | 38.371 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 579.062 | 579.062 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 117.375 | 117.375 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 11.585 | 7.104 | -4.481 us/projection (-38.68%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 83072.003 | 141189.657 | +58117.653 projections/s (+69.96%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 48.465 | 48.465 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 52.425 | 52.425 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 594.062 | 594.062 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 181.375 | 181.375 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 11.025 | 8.398 | -2.628 ms (-23.83%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18221.091 | 23560.134 | +5339.043 roots/s (+29.30%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 12.187 | 9.400 | -2.787 ms (-22.87%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 17067.092 | 21182.422 | +4115.330 roots/s (+24.11%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 19.115 | 15.457 | -3.658 ms (-19.14%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10839.986 | 12723.759 | +1883.773 roots/s (+17.38%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 18.921 | 16.009 | -2.912 ms (-15.39%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10269.950 | 12217.471 | +1947.521 roots/s (+18.96%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 40.715 | 31.716 | -8.999 us/root (-22.10%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 109.926 | 109.652 | -0.273 KiB (-0.25%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.836 | 50.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 39.986 | 32.242 | -7.743 us/root (-19.37%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 109.887 | 109.613 | -0.273 KiB (-0.25%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.836 | 50.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 64.849 | 46.020 | -18.829 us/root (-29.04%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 158.391 | 156.906 | -1.484 KiB (-0.94%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.961 | 87.961 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 60.378 | 47.258 | -13.120 us/root (-21.73%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 158.352 | 156.867 | -1.484 KiB (-0.94%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.961 | 87.961 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 86.342 | 65.780 | -20.563 us/root (-23.82%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 231.688 | 228.453 | -3.234 KiB (-1.40%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.461 | 137.461 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 86.714 | 66.091 | -20.622 us/root (-23.78%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 230.594 | 227.359 | -3.234 KiB (-1.40%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.461 | 137.461 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 28.583 | 23.462 | -5.121 us/root (-17.92%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 67.684 | 67.371 | -0.312 KiB (-0.46%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.086 | 24.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 29.099 | 23.598 | -5.501 us/root (-18.91%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 73.395 | 73.082 | -0.312 KiB (-0.43%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.086 | 24.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 210.102 | 145.263 | -64.839 us/root (-30.86%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 635.336 | 634.883 | -0.453 KiB (-0.07%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.086 | 428.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 203.781 | 147.342 | -56.439 us/root (-27.70%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 635.074 | 634.684 | -0.391 KiB (-0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.086 | 428.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 77.548 | 55.022 | -22.526 us/root (-29.05%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 205.840 | 205.566 | -0.273 KiB (-0.13%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.086 | 125.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 72.871 | 57.133 | -15.738 us/root (-21.60%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 204.754 | 204.363 | -0.391 KiB (-0.19%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.086 | 125.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 85.674 | 45.361 | -40.314 us/root (-47.05%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 139.610 | 139.337 | -0.273 KiB (-0.20%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.930 | 35.930 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 86.104 | 43.863 | -42.241 us/root (-49.06%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 139.571 | 139.298 | -0.273 KiB (-0.20%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.930 | 35.930 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 69.785 | 51.397 | -18.388 us/root (-26.35%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 220.773 | 220.287 | -0.486 KiB (-0.22%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.711 | 136.711 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 69.517 | 51.958 | -17.559 us/root (-25.26%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 224.289 | 223.852 | -0.438 KiB (-0.20%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.711 | 136.711 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 185.600 | 131.534 | -54.066 us/root (-29.13%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 763.344 | 762.844 | -0.500 KiB (-0.07%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.211 | 480.211 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 184.986 | 132.538 | -52.448 us/root (-28.35%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 766.859 | 766.422 | -0.438 KiB (-0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.211 | 480.211 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 111.834 | 99.750 | -12.084 us (-10.81%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 22.851 | 22.804 | -0.047 KiB (-0.21%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.796 | 14.796 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 113.667 | 102.708 | -10.959 us (-9.64%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 22.811 | 22.764 | -0.047 KiB (-0.21%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 14.943 | 14.943 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 113.292 | 100.625 | -12.667 us (-11.18%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 22.851 | 22.804 | -0.047 KiB (-0.21%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.796 | 14.796 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 108.041 | 100.166 | -7.875 us (-7.29%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 22.811 | 22.764 | -0.047 KiB (-0.21%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 14.943 | 14.943 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 113.708 | 99.125 | -14.583 us (-12.82%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 22.852 | 22.805 | -0.047 KiB (-0.21%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.797 | 14.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 113.125 | 103.875 | -9.250 us (-8.18%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 22.812 | 22.765 | -0.047 KiB (-0.21%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 14.944 | 14.944 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 428.647 | 426.749 | -1.898 KiB (-0.44%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 315.032 | 316.630 | +1.598 KiB (+0.51%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.629 | 0.560 | -0.069 ms (-10.97%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.999 | 0.972 | -0.027 ms (-2.69%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 6.401 | 5.729 | -0.671 ms (-10.49%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 30791.140 | 35032.656 | +4241.516 roots/s (+13.78%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 7.006 | 6.241 | -0.765 ms (-10.92%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 26565.569 | 31237.188 | +4671.619 roots/s (+17.59%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 9.283 | 8.557 | -0.726 ms (-7.82%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 21629.609 | 23559.324 | +1929.714 roots/s (+8.92%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 283.894 | 285.334 | +1.440 KiB (+0.51%) | 6 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 41.839 | 45.211 | +3.372 KiB (+8.06%) | 6 | larger |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 97.434 | 98.086 | +0.652 KiB (+0.67%) | 6 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 11.091 | 16.024 | +4.934 KiB (+44.48%) | 6 | larger |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1259.475 | 1259.803 | +0.328 KiB (+0.03%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.363 | 531.363 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.745 | 0.743 | -0.001 ms (-0.15%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.242 | 1.181 | -0.061 ms (-4.87%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 10.320 | 8.959 | -1.361 ms (-13.19%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 19245.961 | 22243.230 | +2997.269 roots/s (+15.57%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 11.378 | 9.733 | -1.645 ms (-14.46%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 17819.290 | 20382.945 | +2563.655 roots/s (+14.39%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 13.934 | 12.444 | -1.490 ms (-10.70%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 14376.939 | 16232.997 | +1856.058 roots/s (+12.91%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 693.486 | 693.541 | +0.055 KiB (+0.01%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 38.004 | 37.324 | -0.680 KiB (-1.79%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 199.057 | 199.111 | +0.055 KiB (+0.03%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.897 | 3.897 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1799.189 | 1799.294 | +0.104 KiB (+0.01%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.792 | 883.694 | -0.098 KiB (-0.01%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.917 | 0.862 | -0.055 ms (-6.00%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.602 | 2.415 | -0.187 ms (-7.18%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 27.572 | 23.561 | -4.011 ms (-14.55%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7310.543 | 8514.443 | +1203.900 roots/s (+16.47%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 28.458 | 24.452 | -4.005 ms (-14.08%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 6855.086 | 8209.787 | +1354.701 roots/s (+19.76%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 31.617 | 27.322 | -4.295 ms (-13.58%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6371.118 | 7227.446 | +856.329 roots/s (+13.44%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1199.479 | 1199.475 | -0.005 KiB (-0.00%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 52.436 | 52.401 | -0.034 KiB (-0.07%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 323.017 | 322.774 | -0.242 KiB (-0.07%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 14.800 | 16.836 | +2.036 KiB (+13.76%) | 6 | larger |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1393.275 | 1393.275 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.398 | 554.398 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.932 | 0.916 | -0.016 ms (-1.72%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.808 | 1.821 | +0.013 ms (+0.74%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 18.021 | 16.606 | -1.415 ms (-7.85%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 11214.115 | 12122.314 | +908.200 roots/s (+8.10%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 18.141 | 16.698 | -1.443 ms (-7.95%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11213.145 | 11925.644 | +712.499 roots/s (+6.35%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 21.074 | 19.624 | -1.451 ms (-6.88%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 9434.964 | 10061.606 | +626.643 roots/s (+6.64%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1166.908 | 1167.979 | +1.070 KiB (+0.09%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 48.164 | 47.484 | -0.680 KiB (-1.41%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 314.291 | 315.361 | +1.070 KiB (+0.34%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.218 | 4.218 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 298.886 | 298.837 | -0.049 KiB (-0.02%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 175.188 | 175.617 | +0.430 KiB (+0.25%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.484 | 0.484 | +0.001 ms (+0.13%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.791 | 0.742 | -0.049 ms (-6.19%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 5.941 | 5.259 | -0.682 ms (-11.49%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 33274.643 | 37953.062 | +4678.419 roots/s (+14.06%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 6.452 | 5.928 | -0.524 ms (-8.12%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 30586.301 | 33919.628 | +3333.327 roots/s (+10.90%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 8.753 | 8.191 | -0.562 ms (-6.43%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 22743.749 | 24394.334 | +1650.585 roots/s (+7.26%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 205.014 | 205.014 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 32.738 | 31.138 | -1.601 KiB (-4.89%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 68.316 | 68.561 | +0.244 KiB (+0.36%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 7.323 | 8.206 | +0.883 KiB (+12.05%) | 6 | larger |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 9.527 | 5.854 | -3.673 us/projection (-38.55%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 103364.857 | 172448.608 | +69083.750 projections/s (+66.83%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.730 | 45.777 | +0.047 KiB (+0.10%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 42.299 | 42.299 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 604.438 | 604.438 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 127.250 | 128.000 | +0.750 B/projection (+0.59%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 13.040 | 7.508 | -5.533 us/projection (-42.43%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 77220.921 | 138992.051 | +61771.130 projections/s (+79.99%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 50.730 | 50.777 | +0.047 KiB (+0.09%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 57.438 | 57.438 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 620.438 | 620.438 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 191.250 | 192.000 | +0.750 B/projection (+0.39%) | 3 | within noise |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 10.662 | 9.165 | -1.498 ms (-14.05%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18814.012 | 22019.964 | +3205.952 roots/s (+17.04%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 11.854 | 10.316 | -1.538 ms (-12.97%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 16940.479 | 20707.149 | +3766.671 roots/s (+22.23%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 18.564 | 15.757 | -2.807 ms (-15.12%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10724.244 | 12466.691 | +1742.446 roots/s (+16.25%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 19.102 | 16.468 | -2.635 ms (-13.79%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10481.036 | 12318.337 | +1837.301 roots/s (+17.53%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 42.305 | 31.342 | -10.962 us/root (-25.91%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 107.686 | 107.177 | -0.509 KiB (-0.47%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.094 | 51.094 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 43.870 | 32.346 | -11.523 us/root (-26.27%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 107.646 | 107.138 | -0.509 KiB (-0.47%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.094 | 51.094 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 65.863 | 47.318 | -18.546 us/root (-28.16%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 159.933 | 157.374 | -2.559 KiB (-1.60%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.219 | 88.219 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 64.232 | 47.816 | -16.415 us/root (-25.56%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 158.776 | 156.218 | -2.559 KiB (-1.61%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.219 | 88.219 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 94.495 | 66.991 | -27.504 us/root (-29.11%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 236.351 | 230.897 | -5.453 KiB (-2.31%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.719 | 137.719 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 101.875 | 67.174 | -34.701 us/root (-34.06%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 235.710 | 230.257 | -5.453 KiB (-2.31%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.719 | 137.719 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 30.083 | 23.326 | -6.758 us/root (-22.46%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 66.598 | 66.044 | -0.554 KiB (-0.83%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.344 | 24.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 28.160 | 23.878 | -4.283 us/root (-15.21%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 72.309 | 71.755 | -0.554 KiB (-0.77%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.344 | 24.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 253.326 | 152.033 | -101.293 us/root (-39.99%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 639.807 | 639.118 | -0.688 KiB (-0.11%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.344 | 428.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 208.587 | 166.337 | -42.250 us/root (-20.26%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 639.416 | 638.907 | -0.509 KiB (-0.08%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.344 | 428.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 72.326 | 55.171 | -17.155 us/root (-23.72%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 208.990 | 208.481 | -0.509 KiB (-0.24%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.344 | 125.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 72.182 | 55.934 | -16.249 us/root (-22.51%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 208.279 | 207.653 | -0.626 KiB (-0.30%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.344 | 125.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 88.043 | 44.904 | -43.139 us/root (-49.00%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 137.534 | 137.064 | -0.470 KiB (-0.34%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.188 | 36.188 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 84.397 | 44.868 | -39.529 us/root (-46.84%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 137.495 | 137.025 | -0.470 KiB (-0.34%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.188 | 36.188 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 66.646 | 52.633 | -14.013 us/root (-21.03%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 224.299 | 223.509 | -0.790 KiB (-0.35%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.969 | 136.969 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 85.613 | 53.063 | -32.551 us/root (-38.02%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 227.814 | 227.087 | -0.728 KiB (-0.32%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.969 | 136.969 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 201.048 | 140.238 | -60.810 us/root (-30.25%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 767.150 | 766.399 | -0.751 KiB (-0.10%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.469 | 480.469 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 194.021 | 138.883 | -55.138 us/root (-28.42%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 770.666 | 769.978 | -0.688 KiB (-0.09%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.469 | 480.469 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 116.584 | 105.208 | -11.376 us (-9.76%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 23.821 | 23.821 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 16.188 | 16.188 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 112.666 | 108.875 | -3.791 us (-3.36%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 23.977 | 23.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 16.344 | 16.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 116.709 | 107.167 | -9.542 us (-8.18%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 23.821 | 23.821 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 16.188 | 16.188 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 116.500 | 106.500 | -10.000 us (-8.58%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 23.977 | 23.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 16.344 | 16.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 110.292 | 104.917 | -5.375 us (-4.87%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 23.822 | 23.822 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 16.189 | 16.189 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 117.500 | 106.292 | -11.208 us (-9.54%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 23.978 | 23.978 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 16.345 | 16.345 | +0.000 KiB (+0.00%) | 3 | within noise |

## write-lowering

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 211.333 | 198.708 | -12.625 us/row (-5.97%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 3536.000 | 3536.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 14602.000 | 14602.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 224.583 | 201.791 | -22.792 us/row (-10.15%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 3586.000 | 3586.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 14602.000 | 14602.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 284.750 | 248.208 | -36.542 us/row (-12.83%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 3536.000 | 3636.000 | +100.000 B/row (+2.83%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 14602.000 | 14602.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 266.500 | 253.875 | -12.625 us/row (-4.74%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 3486.000 | 3586.000 | +100.000 B/row (+2.87%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 14552.000 | 14602.000 | +50.000 B/row (+0.34%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 321.666 | 289.000 | -32.666 us/row (-10.16%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 4426.000 | 4326.000 | -100.000 B/row (-2.26%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 15442.000 | 15442.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 304.917 | 279.708 | -25.209 us/row (-8.27%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 4326.000 | 4426.000 | +100.000 B/row (+2.31%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 15442.000 | 15442.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 726.292 | 650.459 | -75.833 us/row (-10.44%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 7736.000 | 7836.000 | +100.000 B/row (+1.29%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 25739.000 | 25739.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 648.833 | 598.000 | -50.833 us/row (-7.83%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 7736.000 | 7836.000 | +100.000 B/row (+1.29%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23874.000 | 23892.000 | +18.000 B/row (+0.08%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 283.416 | 274.416 | -9.000 us/row (-3.18%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 5646.000 | 5596.000 | -50.000 B/row (-0.89%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15866.000 | 15866.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 277.250 | 251.166 | -26.084 us/row (-9.41%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5642.000 | 5542.000 | -100.000 B/row (-1.77%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15748.000 | 15816.000 | +68.000 B/row (+0.43%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 287.625 | 270.375 | -17.250 us/row (-6.00%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 5696.000 | 5796.000 | +100.000 B/row (+1.76%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15075.000 | 15026.000 | -49.000 B/row (-0.33%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 266.791 | 255.208 | -11.583 us/row (-4.34%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5592.000 | 5542.000 | -50.000 B/row (-0.89%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 14922.000 | 14922.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 178.458 | 161.458 | -17.000 us/row (-9.53%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 2472.000 | 2472.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 14690.000 | 14690.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 179.250 | 160.500 | -18.750 us/row (-10.46%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 2422.000 | 2422.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 14690.000 | 14690.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 217.667 | 202.709 | -14.958 us/row (-6.87%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 3194.000 | 3144.000 | -50.000 B/row (-1.57%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 15426.000 | 15426.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 213.000 | 202.208 | -10.792 us/row (-5.07%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 3194.000 | 3144.000 | -50.000 B/row (-1.57%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 15426.000 | 15426.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 265.917 | 251.875 | -14.042 us/row (-5.28%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 4040.000 | 4040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 16746.000 | 16746.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 280.167 | 257.584 | -22.583 us/row (-8.06%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 4040.000 | 4090.000 | +50.000 B/row (+1.24%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 16746.000 | 16746.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 152.417 | 137.375 | -15.042 us/row (-9.87%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1968.000 | 2018.000 | +50.000 B/row (+2.54%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 14186.000 | 14186.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 145.583 | 135.709 | -9.874 us/row (-6.78%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 2018.000 | 1968.000 | -50.000 B/row (-2.48%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 14186.000 | 14186.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 530.750 | 497.083 | -33.667 us/row (-6.34%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 9432.000 | 9482.000 | +50.000 B/row (+0.53%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27242.000 | 27242.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 524.375 | 500.541 | -23.834 us/row (-4.55%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 9432.000 | 9482.000 | +50.000 B/row (+0.53%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 27429.000 | 27421.000 | -8.000 B/row (-0.03%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 265.208 | 229.750 | -35.458 us/row (-13.37%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3914.000 | 3864.000 | -50.000 B/row (-1.28%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 16082.000 | 16082.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 260.708 | 232.416 | -28.292 us/row (-10.85%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3914.000 | 3864.000 | -50.000 B/row (-1.28%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 16082.000 | 16082.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 239.000 | 207.416 | -31.584 us/row (-13.22%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 2522.000 | 2472.000 | -50.000 B/row (-1.98%) | 1 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 14690.000 | 14690.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 236.875 | 207.125 | -29.750 us/row (-12.56%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 2472.000 | 2522.000 | +50.000 B/row (+2.02%) | 1 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 14690.000 | 14690.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 266.250 | 251.417 | -14.833 us/row (-5.57%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 3312.000 | 3362.000 | +50.000 B/row (+1.51%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 15530.000 | 15530.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 266.041 | 258.416 | -7.625 us/row (-2.87%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 3362.000 | 3312.000 | -50.000 B/row (-1.49%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 15530.000 | 15530.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 642.875 | 617.583 | -25.292 us/row (-3.93%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 6672.000 | 6722.000 | +50.000 B/row (+0.75%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23321.000 | 23321.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 647.584 | 621.083 | -26.501 us/row (-4.09%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 6722.000 | 6722.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 24874.000 | 24874.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 171.750 | 167.209 | -4.541 us/row (-2.64%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 3024.000 | 3024.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 15138.000 | 15138.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 154.458 | 136.084 | -18.374 us/row (-11.90%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 2824.000 | 2824.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 14938.000 | 14938.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 177.250 | 162.250 | -15.000 us/row (-8.46%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 2974.000 | 3024.000 | +50.000 B/row (+1.68%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 15138.000 | 15138.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 149.042 | 141.000 | -8.042 us/row (-5.40%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 2824.000 | 2824.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 14938.000 | 14938.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 204.542 | 202.917 | -1.625 us/row (-0.79%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 3710.000 | 3810.000 | +100.000 B/row (+2.70%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 14826.000 | 14826.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 186.875 | 186.458 | -0.417 us/row (-0.22%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3610.000 | 3560.000 | -50.000 B/row (-1.39%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 14626.000 | 14626.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 224.083 | 198.875 | -25.208 us/row (-11.25%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 3710.000 | 3760.000 | +50.000 B/row (+1.35%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 14826.000 | 14826.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 187.959 | 174.750 | -13.209 us/row (-7.03%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 3610.000 | 3660.000 | +50.000 B/row (+1.39%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 14626.000 | 14626.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 168.750 | 165.750 | -3.000 us/row (-1.78%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 2744.000 | 2744.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 15042.000 | 15042.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 157.167 | 153.250 | -3.917 us/row (-2.49%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2612.000 | 2462.000 | -150.000 B/row (-5.74%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 14810.000 | 14810.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 176.166 | 160.875 | -15.291 us/row (-8.68%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 2744.000 | 2744.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 15042.000 | 15042.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 149.834 | 142.250 | -7.584 us/row (-5.06%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 2612.000 | 2512.000 | -100.000 B/row (-3.83%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 14810.000 | 14810.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 206.542 | 202.125 | -4.417 us/row (-2.14%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 3810.000 | 3810.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 14826.000 | 14826.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 178.875 | 173.209 | -5.666 us/row (-3.17%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 3560.000 | 3660.000 | +100.000 B/row (+2.81%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 14626.000 | 14626.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 211.209 | 185.584 | -25.625 us/row (-12.13%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 3760.000 | 3810.000 | +50.000 B/row (+1.33%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 14826.000 | 14826.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 185.292 | 166.416 | -18.876 us/row (-10.19%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3510.000 | 3660.000 | +150.000 B/row (+4.27%) | 1 | larger |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 14626.000 | 14626.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3738.167 | 3395.584 | -342.583 us (-9.16%) | 9 | faster |
| 3.13 | model-preparation | model.prepared | retainedBytes | 415992.000 | 415992.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 436760.000 | 436144.000 | -616.000 B (-0.14%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 107.878 | 36.302 | -71.576 us/row (-66.35%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1583.117 | 1582.422 | -0.695 B/row (-0.04%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3677.125 | 3493.977 | -183.148 B/row (-4.98%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 104.444 | 40.805 | -63.639 us/row (-60.93%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2767.531 | 2772.320 | +4.789 B/row (+0.17%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5831.492 | 5643.945 | -187.547 B/row (-3.22%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 111.323 | 42.090 | -69.233 us/row (-62.19%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1738.469 | 1767.406 | +28.938 B/row (+1.66%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4206.812 | 3987.688 | -219.125 B/row (-5.21%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 110.220 | 45.301 | -64.919 us/row (-58.90%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2921.812 | 2933.562 | +11.750 B/row (+0.40%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6271.688 | 6077.969 | -193.719 B/row (-3.09%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 125.089 | 60.536 | -64.552 us/row (-51.61%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2368.000 | 2386.750 | +18.750 B/row (+0.79%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 5907.625 | 5629.125 | -278.500 B/row (-4.71%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 134.464 | 63.172 | -71.292 us/row (-53.02%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3568.125 | 3601.000 | +32.875 B/row (+0.92%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 7988.000 | 7722.625 | -265.375 B/row (-3.32%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 248.000 | 232.375 | -15.625 us/row (-6.30%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 3632.000 | 3632.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 15066.000 | 15066.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 242.583 | 263.292 | +20.709 us/row (+8.54%) | 9 | slower |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 3632.000 | 3582.000 | -50.000 B/row (-1.38%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 15066.000 | 15066.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 324.250 | 286.250 | -38.000 us/row (-11.72%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 3682.000 | 3582.000 | -100.000 B/row (-2.72%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 15066.000 | 15066.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 309.833 | 290.750 | -19.083 us/row (-6.16%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 3632.000 | 3682.000 | +50.000 B/row (+1.38%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 15066.000 | 15066.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 345.583 | 341.917 | -3.666 us/row (-1.06%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 4422.000 | 4472.000 | +50.000 B/row (+1.13%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 15970.000 | 15970.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 339.375 | 323.208 | -16.167 us/row (-4.76%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 4422.000 | 4522.000 | +100.000 B/row (+2.26%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 15970.000 | 15970.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 753.250 | 733.000 | -20.250 us/row (-2.69%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 7832.000 | 7882.000 | +50.000 B/row (+0.64%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 26259.000 | 26209.000 | -50.000 B/row (-0.19%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 712.292 | 665.250 | -47.042 us/row (-6.60%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 7932.000 | 7782.000 | -150.000 B/row (-1.89%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 24604.000 | 24570.000 | -34.000 B/row (-0.14%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 314.959 | 296.375 | -18.584 us/row (-5.90%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 6008.000 | 5958.000 | -50.000 B/row (-0.83%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15890.000 | 15674.000 | -216.000 B/row (-1.36%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 295.542 | 280.166 | -15.376 us/row (-5.20%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5746.000 | 5646.000 | -100.000 B/row (-1.74%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15702.000 | 15636.000 | -66.000 B/row (-0.42%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 331.333 | 313.334 | -17.999 us/row (-5.43%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 5908.000 | 5808.000 | -100.000 B/row (-1.69%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15440.000 | 15390.000 | -50.000 B/row (-0.32%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 300.166 | 290.750 | -9.416 us/row (-3.14%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5696.000 | 5646.000 | -50.000 B/row (-0.88%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 15370.000 | 15370.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 191.459 | 194.625 | +3.166 us/row (+1.65%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 2528.000 | 2528.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 15186.000 | 15186.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 191.916 | 190.042 | -1.874 us/row (-0.98%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 2528.000 | 2528.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 15186.000 | 15186.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 234.458 | 238.583 | +4.125 us/row (+1.76%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 3200.000 | 3200.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 15858.000 | 15858.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 234.709 | 228.500 | -6.209 us/row (-2.65%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 3200.000 | 3200.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 15858.000 | 15858.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 301.584 | 287.083 | -14.501 us/row (-4.81%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 4096.000 | 4046.000 | -50.000 B/row (-1.22%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 17234.000 | 17234.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 295.167 | 293.000 | -2.167 us/row (-0.73%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 4096.000 | 4096.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 17234.000 | 17234.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 166.458 | 163.042 | -3.416 us/row (-2.05%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 2016.000 | 2016.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 14674.000 | 14674.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 165.458 | 160.541 | -4.917 us/row (-2.97%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1966.000 | 2016.000 | +50.000 B/row (+2.54%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 14674.000 | 14674.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 557.666 | 541.333 | -16.333 us/row (-2.93%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 9488.000 | 9488.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27746.000 | 27746.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 578.167 | 534.125 | -44.042 us/row (-7.62%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 9488.000 | 9538.000 | +50.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 27925.000 | 27925.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 268.583 | 258.500 | -10.083 us/row (-3.75%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3920.000 | 3970.000 | +50.000 B/row (+1.28%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 16578.000 | 16578.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 264.167 | 259.167 | -5.000 us/row (-1.89%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3920.000 | 3920.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 16578.000 | 16578.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 277.917 | 246.792 | -31.125 us/row (-11.20%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 2528.000 | 2578.000 | +50.000 B/row (+1.98%) | 1 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 15186.000 | 15186.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 274.292 | 244.500 | -29.792 us/row (-10.86%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 2528.000 | 2528.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 15186.000 | 15186.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 301.833 | 285.583 | -16.250 us/row (-5.38%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 3368.000 | 3368.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 16090.000 | 16090.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 290.458 | 313.458 | +23.000 us/row (+7.92%) | 9 | slower |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 3368.000 | 3418.000 | +50.000 B/row (+1.48%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 16090.000 | 16090.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 689.041 | 715.125 | +26.084 us/row (+3.79%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 6678.000 | 6678.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23817.000 | 23817.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 708.292 | 694.875 | -13.417 us/row (-1.89%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 6728.000 | 6728.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 25434.000 | 25434.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 190.333 | 179.750 | -10.583 us/row (-5.56%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 3062.000 | 3112.000 | +50.000 B/row (+1.63%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 15666.000 | 15666.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 166.708 | 162.750 | -3.958 us/row (-2.37%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 2854.000 | 2904.000 | +50.000 B/row (+1.75%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 15406.000 | 15406.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 196.667 | 192.833 | -3.834 us/row (-1.95%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 3112.000 | 3162.000 | +50.000 B/row (+1.61%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 15666.000 | 15666.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 173.333 | 167.625 | -5.708 us/row (-3.29%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 2904.000 | 2954.000 | +50.000 B/row (+1.72%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 15406.000 | 15406.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 222.250 | 214.791 | -7.459 us/row (-3.36%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 3906.000 | 3906.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 15290.000 | 15290.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 205.208 | 190.375 | -14.833 us/row (-7.23%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3548.000 | 3648.000 | +100.000 B/row (+2.82%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 15030.000 | 15030.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 239.292 | 229.250 | -10.042 us/row (-4.20%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 3856.000 | 3806.000 | -50.000 B/row (-1.30%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 15290.000 | 15290.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 212.458 | 210.958 | -1.500 us/row (-0.71%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 3698.000 | 3698.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 15030.000 | 15030.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 192.958 | 188.959 | -3.999 us/row (-2.07%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 2900.000 | 2850.000 | -50.000 B/row (-1.72%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 15554.000 | 15554.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 170.125 | 161.459 | -8.666 us/row (-5.09%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2560.000 | 2660.000 | +100.000 B/row (+3.91%) | 1 | larger |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 15266.000 | 15266.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 192.667 | 186.167 | -6.500 us/row (-3.37%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 2900.000 | 2850.000 | -50.000 B/row (-1.72%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 15554.000 | 15554.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 168.917 | 166.959 | -1.958 us/row (-1.16%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 2660.000 | 2560.000 | -100.000 B/row (-3.76%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 15266.000 | 15266.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 224.667 | 216.750 | -7.917 us/row (-3.52%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 3856.000 | 3906.000 | +50.000 B/row (+1.30%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 15290.000 | 15290.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 202.459 | 195.958 | -6.501 us/row (-3.21%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 3748.000 | 3698.000 | -50.000 B/row (-1.33%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 15030.000 | 15030.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 223.916 | 216.750 | -7.166 us/row (-3.20%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 3806.000 | 3856.000 | +50.000 B/row (+1.31%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 15290.000 | 15290.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 201.917 | 200.041 | -1.876 us/row (-0.93%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3698.000 | 3648.000 | -50.000 B/row (-1.35%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 15030.000 | 15030.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3673.291 | 3373.584 | -299.707 us (-8.16%) | 9 | faster |
| 3.14 | model-preparation | model.prepared | retainedBytes | 427016.000 | 427016.000 | +0.000 B (+0.00%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 435016.000 | 434456.000 | -560.000 B (-0.13%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 100.807 | 36.691 | -64.116 us/row (-63.60%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1616.133 | 1623.453 | +7.320 B/row (+0.45%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3675.094 | 3313.727 | -361.367 B/row (-9.83%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 109.202 | 40.415 | -68.787 us/row (-62.99%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2808.484 | 2813.562 | +5.078 B/row (+0.18%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5837.680 | 5459.586 | -378.094 B/row (-6.48%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 110.827 | 40.651 | -70.176 us/row (-63.32%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1810.688 | 1809.125 | -1.562 B/row (-0.09%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4231.000 | 3856.219 | -374.781 B/row (-8.86%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 119.014 | 43.988 | -75.026 us/row (-63.04%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 3008.031 | 3012.312 | +4.281 B/row (+0.14%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6331.812 | 5952.312 | -379.500 B/row (-5.99%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 131.417 | 60.511 | -70.906 us/row (-53.96%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2552.000 | 2570.750 | +18.750 B/row (+0.73%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 6091.375 | 5590.375 | -501.000 B/row (-8.22%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 136.656 | 63.104 | -73.552 us/row (-53.82%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3788.750 | 3780.875 | -7.875 B/row (-0.21%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 8209.750 | 7752.250 | -457.500 B/row (-5.57%) | 9 | smaller |

Deltas are advisory and never ratchet the Budget Contract.
