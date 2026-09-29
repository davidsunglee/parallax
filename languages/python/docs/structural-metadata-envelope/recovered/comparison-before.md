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
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.437 | 3.340 | -0.097 ratio (-2.82%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.437 | 3.340 | -0.097 ratio (-2.82%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.445 | 3.313 | -0.132 ratio (-3.83%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 0.739 | 0.522 | -0.218 ratio (-29.44%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.likeForLike | 0.709 | 0.500 | -0.209 ratio (-29.52%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 2.371 | 1.549 | -0.821 ratio (-34.64%) | 0 | smaller |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.211 | 2.184 | -0.027 ratio (-1.22%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.211 | 2.184 | -0.027 ratio (-1.22%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.222 | 2.209 | -0.013 ratio (-0.57%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 25245.917 | 1471.432 | -23774.485 ns (-94.17%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 11927.437 | 6919.735 | -5007.702 ns (-41.98%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.dumpNs | 7137.104 | 5770.104 | -1367.000 ns (-19.15%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 9092.000 | 4770.000 | -4322.000 B (-47.54%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.readNs | 102.513 | 83.312 | -19.200 ns (-18.73%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 473.936 | 425.885 | -48.051 ns (-10.14%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 8028.000 | 3706.000 | -4322.000 B (-53.84%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 473.936 | 425.885 | -48.051 ns (-10.14%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | -51.098 | 105.925 | +157.023 ns (-307.30%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 11445.431 | 10317.575 | -1127.856 ns (-9.85%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2870.354 | 2373.458 | -496.895 ns (-17.31%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 4960.000 | 4960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.readNs | 30.329 | 25.200 | -5.129 ns (-16.91%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2168.000 | 2168.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 336.871 | 417.600 | +80.729 ns (+23.96%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 5897.650 | 6057.817 | +160.167 ns (+2.72%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2936.708 | 2379.062 | -557.646 ns (-18.99%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 30.471 | 26.533 | -3.937 ns (-12.92%) | 0 | smaller |
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
| - | - | cpython-3.13/nullable | compact.callNs | 13496.825 | 1309.339 | -12187.486 ns (-90.30%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 3742.404 | 2307.494 | -1434.910 ns (-38.34%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.dumpNs | 2157.854 | 1830.562 | -327.292 ns (-15.17%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 5768.000 | 3464.000 | -2304.000 B (-39.94%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.readNs | 90.271 | 74.656 | -15.615 ns (-17.30%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 242.359 | 233.641 | -8.718 ns (-3.60%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.transientBytes | 5304.000 | 3000.000 | -2304.000 B (-43.44%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 242.359 | 233.641 | -8.718 ns (-3.60%) | 0 | smaller |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 244.194 | 265.614 | +21.420 ns (+8.77%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 6299.098 | 5215.677 | -1083.421 ns (-17.20%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 1045.459 | 855.125 | -190.334 ns (-18.21%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 26.917 | 22.127 | -4.790 ns (-17.79%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 231.783 | 165.896 | -65.887 ns (-28.43%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1481.175 | 1191.208 | -289.967 ns (-19.58%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 1041.521 | 860.687 | -180.833 ns (-17.36%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 26.990 | 22.060 | -4.929 ns (-18.26%) | 0 | smaller |
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
| - | - | cpython-3.13/partial | compact.callNs | 12705.281 | 1358.350 | -11346.931 ns (-89.31%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 3207.740 | 2144.337 | -1063.402 ns (-33.15%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.dumpNs | 2111.979 | 1857.750 | -254.229 ns (-12.04%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 5856.000 | 3432.000 | -2424.000 B (-41.39%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.readNs | 87.129 | 74.935 | -12.194 ns (-14.00%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 323.083 | 218.860 | -104.223 ns (-32.26%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.transientBytes | 5424.000 | 3000.000 | -2424.000 B (-44.69%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 323.083 | 218.860 | -104.223 ns (-32.26%) | 0 | smaller |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 208.846 | 187.077 | -21.769 ns (-10.42%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5763.279 | 4991.819 | -771.460 ns (-13.39%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.dumpNs | 1045.813 | 891.167 | -154.646 ns (-14.79%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 25.813 | 24.321 | -1.492 ns (-5.78%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 229.827 | 191.492 | -38.335 ns (-16.68%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 1128.985 | 945.946 | -183.040 ns (-16.21%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 1015.041 | 868.479 | -146.562 ns (-14.44%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 25.302 | 22.933 | -2.369 ns (-9.36%) | 0 | smaller |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 28863.865 | 1346.071 | -27517.794 ns (-95.34%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 3578.260 | 2218.367 | -1359.894 ns (-38.00%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1921.208 | 1588.438 | -332.770 ns (-17.32%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 8960.000 | 3408.000 | -5552.000 B (-61.96%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.readNs | 93.244 | 80.107 | -13.137 ns (-14.09%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 386.689 | 234.066 | -152.623 ns (-39.47%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 8552.000 | 3000.000 | -5552.000 B (-64.92%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 386.689 | 234.066 | -152.623 ns (-39.47%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 274.933 | 138.725 | -136.208 ns (-49.54%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4701.879 | 4085.067 | -616.812 ns (-13.12%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 938.541 | 786.792 | -151.749 ns (-16.17%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 27.958 | 23.863 | -4.095 ns (-14.65%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 235.950 | 196.121 | -39.829 ns (-16.88%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1248.321 | 1057.004 | -191.317 ns (-15.33%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 918.437 | 774.416 | -144.021 ns (-15.68%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 27.092 | 24.283 | -2.810 ns (-10.37%) | 0 | smaller |
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
| - | - | cpython-3.13/shallow | compact.callNs | 10711.742 | 1392.777 | -9318.965 ns (-87.00%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 2940.675 | 2077.452 | -863.223 ns (-29.35%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1620.646 | 1399.542 | -221.104 ns (-13.64%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 5632.000 | 3384.000 | -2248.000 B (-39.91%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.readNs | 102.734 | 88.635 | -14.099 ns (-13.72%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 186.003 | 209.616 | +23.613 ns (+12.70%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.transientBytes | 5248.000 | 3000.000 | -2248.000 B (-42.84%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 186.003 | 209.616 | +23.613 ns (+12.70%) | 0 | larger |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 281.900 | 147.133 | -134.767 ns (-47.81%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 3049.954 | 2716.804 | -333.150 ns (-10.92%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 804.000 | 715.209 | -88.792 ns (-11.04%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 29.792 | 25.276 | -4.516 ns (-15.16%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 218.183 | 214.562 | -3.621 ns (-1.66%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 864.233 | 785.979 | -78.254 ns (-9.05%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 801.563 | 718.188 | -83.375 ns (-10.40%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 30.062 | 26.338 | -3.724 ns (-12.39%) | 0 | smaller |
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
| - | - | cpython-3.13/warmed | compact.callNs | 11830.179 | 1586.575 | -10243.604 ns (-86.59%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 5462.821 | 4130.592 | -1332.229 ns (-24.39%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.dumpNs | 2039.750 | 1737.125 | -302.625 ns (-14.84%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 5816.000 | 3384.000 | -2432.000 B (-41.82%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.readNs | 101.755 | 87.688 | -14.068 ns (-13.82%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | -99.547 | 240.703 | +340.249 ns (-341.80%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.transientBytes | 5010.000 | 2578.000 | -2432.000 B (-48.54%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 0.000 | 240.703 | +240.703 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 194.696 | 153.585 | -41.111 ns (-21.12%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 4395.429 | 3772.644 | -622.785 ns (-14.17%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 853.375 | 707.937 | -145.438 ns (-17.04%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 30.781 | 25.859 | -4.922 ns (-15.99%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 245.131 | 169.441 | -75.690 ns (-30.88%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1970.952 | 1701.954 | -268.998 ns (-13.65%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 838.937 | 704.771 | -134.166 ns (-15.99%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 30.677 | 26.630 | -4.047 ns (-13.19%) | 0 | smaller |
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
| - | - | cpython-3.13/wide | compact.callNs | 14688.787 | 1364.521 | -13324.266 ns (-90.71%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 4443.171 | 2637.167 | -1806.004 ns (-40.65%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.dumpNs | 2910.521 | 2417.041 | -493.479 ns (-16.96%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 6320.000 | 3512.000 | -2808.000 B (-44.43%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.readNs | 98.698 | 82.273 | -16.425 ns (-16.64%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 86.635 | 196.700 | +110.065 ns (+127.04%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.transientBytes | 5808.000 | 3000.000 | -2808.000 B (-48.35%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 86.635 | 196.700 | +110.065 ns (+127.04%) | 0 | larger |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | -138.439 | 30.806 | +169.245 ns (-122.25%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 9112.585 | 7771.485 | -1341.100 ns (-14.72%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1373.792 | 1184.459 | -189.333 ns (-13.78%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 26.379 | 24.100 | -2.279 ns (-8.64%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 215.811 | 219.250 | +3.439 ns (+1.59%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1966.773 | 1775.417 | -191.356 ns (-9.73%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1323.667 | 1126.312 | -197.354 ns (-14.91%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 26.879 | 23.921 | -2.958 ns (-11.01%) | 0 | smaller |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.134 | 3.320 | +0.186 ratio (+5.93%) | 0 | larger |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.134 | 3.320 | +0.186 ratio (+5.93%) | 0 | larger |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.159 | 3.284 | +0.125 ratio (+3.94%) | 0 | larger |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 0.814 | 0.508 | -0.306 ratio (-37.58%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.likeForLike | 0.781 | 0.488 | -0.293 ratio (-37.46%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 2.490 | 1.473 | -1.016 ratio (-40.83%) | 0 | smaller |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.138 | 2.151 | +0.013 ratio (+0.62%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.138 | 2.151 | +0.013 ratio (+0.62%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.189 | 2.186 | -0.003 ratio (-0.12%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 26602.598 | 1597.398 | -25005.200 ns (-94.00%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 15020.798 | 6653.790 | -8367.008 ns (-55.70%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.dumpNs | 8641.333 | 6027.395 | -2613.938 ns (-30.25%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 9396.000 | 5034.000 | -4362.000 B (-46.42%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.readNs | 120.837 | 85.679 | -35.158 ns (-29.10%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | -269.557 | 317.822 | +587.378 ns (-217.91%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 8164.000 | 3802.000 | -4362.000 B (-53.43%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 0.000 | 317.822 | +317.822 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | -105.009 | 97.054 | +202.063 ns (-192.43%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 12425.592 | 10885.092 | -1540.500 ns (-12.40%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 3392.271 | 2543.729 | -848.542 ns (-25.01%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5184.000 | 5184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.readNs | 36.262 | 26.342 | -9.921 ns (-27.36%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2264.000 | 2264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 370.583 | 238.071 | -132.512 ns (-35.76%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 6564.979 | 6299.804 | -265.175 ns (-4.04%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 3228.354 | 2465.104 | -763.250 ns (-23.64%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4744.000 | 4744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 33.767 | 25.688 | -8.079 ns (-23.93%) | 0 | smaller |
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
| - | - | cpython-3.14/nullable | compact.callNs | 18101.698 | 1387.052 | -16714.645 ns (-92.34%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 4844.365 | 2320.427 | -2523.938 ns (-52.10%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.dumpNs | 2435.146 | 1813.438 | -621.708 ns (-25.53%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 6296.000 | 3672.000 | -2624.000 B (-41.68%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.readNs | 103.467 | 78.273 | -25.194 ns (-24.35%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 556.920 | 233.380 | -323.539 ns (-58.09%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 5800.000 | 3176.000 | -2624.000 B (-45.24%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 556.920 | 233.380 | -323.539 ns (-58.09%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 310.979 | 136.987 | -173.992 ns (-55.95%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 7840.104 | 5262.117 | -2577.987 ns (-32.88%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 1386.104 | 888.250 | -497.854 ns (-35.92%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 38.050 | 24.467 | -13.583 ns (-35.70%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 356.925 | 198.346 | -158.579 ns (-44.43%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1924.825 | 1237.029 | -687.796 ns (-35.73%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 1403.063 | 897.979 | -505.084 ns (-36.00%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 37.535 | 24.223 | -13.313 ns (-35.47%) | 0 | smaller |
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
| - | - | cpython-3.14/partial | compact.callNs | 13892.875 | 1426.656 | -12466.219 ns (-89.73%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 3238.250 | 2156.552 | -1081.698 ns (-33.40%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.dumpNs | 2127.188 | 1857.896 | -269.292 ns (-12.66%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 6320.000 | 3576.000 | -2744.000 B (-43.42%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.readNs | 90.888 | 79.108 | -11.779 ns (-12.96%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 296.376 | 214.278 | -82.098 ns (-27.70%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 5856.000 | 3112.000 | -2744.000 B (-46.86%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 296.376 | 214.278 | -82.098 ns (-27.70%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 346.745 | 181.619 | -165.127 ns (-47.62%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 5943.275 | 4941.298 | -1001.977 ns (-16.86%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 1142.937 | 901.000 | -241.937 ns (-21.17%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 30.971 | 22.660 | -8.310 ns (-26.83%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 254.527 | 230.394 | -24.133 ns (-9.48%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 1204.723 | 1001.648 | -203.075 ns (-16.86%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 1118.958 | 899.250 | -219.708 ns (-19.64%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 31.790 | 24.969 | -6.821 ns (-21.46%) | 0 | smaller |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 29780.252 | 1421.756 | -28358.496 ns (-95.23%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 3659.227 | 2213.744 | -1445.483 ns (-39.50%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1917.604 | 1695.812 | -221.792 ns (-11.57%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 9176.000 | 3552.000 | -5624.000 B (-61.29%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.readNs | 96.372 | 86.920 | -9.452 ns (-9.81%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 412.436 | 219.298 | -193.138 ns (-46.83%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 8736.000 | 3112.000 | -5624.000 B (-64.38%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 412.436 | 219.298 | -193.138 ns (-46.83%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 281.438 | 208.482 | -72.956 ns (-25.92%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4532.896 | 4029.248 | -503.648 ns (-11.11%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 975.584 | 824.750 | -150.834 ns (-15.46%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 30.045 | 27.179 | -2.866 ns (-9.54%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 209.410 | 197.971 | -11.440 ns (-5.46%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1242.277 | 1119.071 | -123.206 ns (-9.92%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 951.146 | 826.666 | -124.480 ns (-13.09%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 30.018 | 26.559 | -3.458 ns (-11.52%) | 0 | smaller |
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
| - | - | cpython-3.14/shallow | compact.callNs | 11737.550 | 1442.716 | -10294.834 ns (-87.71%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 3513.033 | 2091.679 | -1421.354 ns (-40.46%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1743.104 | 1402.125 | -340.979 ns (-19.56%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 6048.000 | 3528.000 | -2520.000 B (-41.67%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.readNs | 109.797 | 88.974 | -20.823 ns (-18.97%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 510.573 | 217.524 | -293.050 ns (-57.40%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 5632.000 | 3112.000 | -2520.000 B (-44.74%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 510.573 | 217.524 | -293.050 ns (-57.40%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 505.237 | 203.252 | -301.985 ns (-59.77%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 3212.804 | 2762.873 | -449.931 ns (-14.00%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 865.187 | 731.792 | -133.396 ns (-15.42%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 31.974 | 27.057 | -4.917 ns (-15.38%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 191.435 | 208.529 | +17.094 ns (+8.93%) | 0 | larger |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 1001.794 | 819.763 | -182.031 ns (-18.17%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 904.916 | 719.104 | -185.812 ns (-20.53%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 32.886 | 27.661 | -5.224 ns (-15.89%) | 0 | smaller |
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
| - | - | cpython-3.14/warmed | compact.callNs | 11840.606 | 1519.006 | -10321.600 ns (-87.17%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 6115.727 | 4263.015 | -1852.713 ns (-30.29%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 2201.770 | 1785.625 | -416.145 ns (-18.90%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 6232.000 | 3528.000 | -2704.000 B (-43.39%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.readNs | 117.271 | 88.958 | -28.312 ns (-24.14%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 374.343 | 268.272 | -106.071 ns (-28.34%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.transientBytes | 5394.000 | 2690.000 | -2704.000 B (-50.13%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 374.343 | 268.272 | -106.071 ns (-28.34%) | 0 | smaller |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 59.194 | 132.360 | +73.167 ns (+123.61%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 4651.035 | 3897.015 | -754.021 ns (-16.21%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 953.188 | 751.042 | -202.146 ns (-21.21%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 34.422 | 28.438 | -5.984 ns (-17.39%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 217.869 | 205.705 | -12.165 ns (-5.58%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 2045.298 | 1755.837 | -289.460 ns (-14.15%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 871.084 | 731.875 | -139.209 ns (-15.98%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 31.937 | 30.641 | -1.297 ns (-4.06%) | 0 | smaller |
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
| - | - | cpython-3.14/wide | compact.callNs | 16279.285 | 1485.202 | -14794.084 ns (-90.88%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 4543.027 | 2531.902 | -2011.125 ns (-44.27%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.dumpNs | 2845.917 | 2403.625 | -442.292 ns (-15.54%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 6736.000 | 3720.000 | -3016.000 B (-44.77%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.readNs | 97.708 | 82.836 | -14.872 ns (-15.22%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 24.472 | 219.275 | +194.802 ns (+796.01%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.transientBytes | 6192.000 | 3176.000 | -3016.000 B (-48.71%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 24.472 | 219.275 | +194.802 ns (+796.01%) | 0 | larger |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 175.358 | 220.702 | +45.344 ns (+25.86%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 8827.829 | 7487.965 | -1339.865 ns (-15.18%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1458.396 | 1177.687 | -280.708 ns (-19.25%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 30.237 | 23.443 | -6.794 ns (-22.47%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 253.979 | 253.521 | -0.459 ns (-0.18%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 2047.104 | 1719.229 | -327.875 ns (-16.02%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1397.500 | 1144.000 | -253.500 ns (-18.14%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 29.974 | 23.717 | -6.256 ns (-20.87%) | 0 | smaller |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 4.296 | 3.263 | -1.033 us/event (-24.04%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 4.859 | 3.726 | -1.132 us/event (-23.31%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.242 | 0.271 | +0.029 ratio (+11.86%) | 0 | larger |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.027 | 0.021 | -0.006 ratio (-21.25%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.080 | 0.068 | -0.012 ratio (-14.99%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.006 | 0.004 | -0.001 ratio (-23.44%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.173 | 0.170 | -0.003 ratio (-1.51%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p50 | 615.583 | 428.584 | -186.999 us (-30.38%) | 0 | faster |
| - | - | Safe logging alone, at INFO | observed.p95 | 663.875 | 445.500 | -218.375 us (-32.89%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 120.292 | 91.375 | -28.917 us (-24.04%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 136.042 | 104.334 | -31.708 us (-23.31%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.241 | 0.271 | +0.030 ratio (+12.60%) | 0 | larger |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.293 | 0.309 | +0.016 ratio (+5.58%) | 0 | larger |
| - | - | Safe logging alone, at INFO | plain.p50 | 496.500 | 337.167 | -159.333 us (-32.09%) | 0 | faster |
| - | - | Safe logging alone, at INFO | plain.p95 | 534.917 | 350.958 | -183.959 us (-34.39%) | 0 | faster |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.240 | 0.271 | +0.031 ratio (+13.05%) | 0 | larger |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.241 | 0.269 | +0.028 ratio (+11.74%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.717 | 2.341 | -0.376 us/event (-13.85%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 3.667 | 2.832 | -0.835 us/event (-22.77%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.173 | 0.195 | +0.022 ratio (+12.85%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.017 | 0.015 | -0.002 ratio (-11.78%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.053 | 0.049 | -0.004 ratio (-7.13%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.004 | 0.003 | -0.000 ratio (-13.41%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.119 | 0.122 | +0.003 ratio (+2.89%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p50 | 517.167 | 401.917 | -115.250 us (-22.28%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | observed.p95 | 562.625 | 420.750 | -141.875 us (-25.22%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 76.083 | 65.542 | -10.541 us (-13.85%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 102.667 | 79.291 | -23.376 us (-22.77%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.172 | 0.195 | +0.022 ratio (+13.03%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.232 | 0.235 | +0.003 ratio (+1.21%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | plain.p50 | 440.500 | 336.250 | -104.250 us (-23.67%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | plain.p95 | 479.500 | 350.958 | -128.542 us (-26.81%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.174 | 0.195 | +0.021 ratio (+12.21%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.173 | 0.199 | +0.026 ratio (+14.71%) | 0 | larger |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 4.586 | 3.990 | -0.597 us/event (-13.01%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 5.567 | 4.973 | -0.594 us/event (-10.67%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.291 | 0.330 | +0.039 ratio (+13.38%) | 0 | larger |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.029 | 0.026 | -0.003 ratio (-10.95%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.089 | 0.083 | -0.006 ratio (-6.33%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.006 | 0.005 | -0.001 ratio (-12.57%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.200 | 0.207 | +0.007 ratio (+3.59%) | 0 | larger |
| - | - | fan-out of three, tracing every root | observed.p50 | 570.834 | 450.750 | -120.084 us (-21.04%) | 0 | faster |
| - | - | fan-out of three, tracing every root | observed.p95 | 620.875 | 479.333 | -141.542 us (-22.80%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 128.417 | 111.708 | -16.709 us (-13.01%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 155.875 | 139.250 | -16.625 us (-10.67%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.292 | 0.330 | +0.038 ratio (+13.06%) | 0 | larger |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.351 | 0.406 | +0.056 ratio (+15.83%) | 0 | larger |
| - | - | fan-out of three, tracing every root | plain.p50 | 441.792 | 338.958 | -102.834 us (-23.28%) | 0 | faster |
| - | - | fan-out of three, tracing every root | plain.p95 | 481.125 | 352.375 | -128.750 us (-26.76%) | 0 | faster |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.292 | 0.330 | +0.038 ratio (+12.91%) | 0 | larger |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.290 | 0.360 | +0.070 ratio (+24.04%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 5.051 | 3.807 | -1.244 us/event (-24.63%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 6.737 | 4.613 | -2.124 us/event (-31.52%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.284 | 0.314 | +0.031 ratio (+10.77%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.031 | 0.025 | -0.007 ratio (-21.87%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.094 | 0.080 | -0.015 ratio (-15.67%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.007 | 0.005 | -0.002 ratio (-24.04%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.203 | 0.198 | -0.005 ratio (-2.37%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 652.167 | 445.584 | -206.583 us (-31.68%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 833.500 | 473.917 | -359.583 us (-43.14%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 141.417 | 106.583 | -34.834 us (-24.63%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 188.625 | 129.166 | -59.459 us (-31.52%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.277 | 0.315 | +0.037 ratio (+13.50%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.340 | 0.377 | +0.037 ratio (+10.79%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 498.292 | 339.042 | -159.250 us (-31.96%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 651.750 | 353.916 | -297.834 us (-45.70%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.309 | 0.314 | +0.005 ratio (+1.76%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.279 | 0.339 | +0.060 ratio (+21.59%) | 0 | larger |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.658 | 1.435 | -0.223 us/event (-13.46%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 2.543 | 1.998 | -0.545 us/event (-21.42%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.110 | 0.120 | +0.010 ratio (+9.09%) | 0 | larger |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.010 | 0.009 | -0.001 ratio (-11.72%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.033 | 0.030 | -0.003 ratio (-7.79%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-13.09%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.074 | 0.075 | +0.001 ratio (+0.67%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p50 | 471.084 | 376.375 | -94.709 us (-20.10%) | 0 | faster |
| - | - | one Handler that keeps nothing | observed.p95 | 506.000 | 396.459 | -109.541 us (-21.65%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 46.416 | 40.167 | -6.249 us (-13.46%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 71.208 | 55.958 | -15.250 us (-21.42%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.109 | 0.120 | +0.010 ratio (+9.46%) | 0 | larger |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.168 | 0.166 | -0.002 ratio (-0.92%) | 0 | within noise |
| - | - | one Handler that keeps nothing | plain.p50 | 423.708 | 336.125 | -87.583 us (-20.67%) | 0 | faster |
| - | - | one Handler that keeps nothing | plain.p95 | 453.125 | 355.125 | -98.000 us (-21.63%) | 0 | faster |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.112 | 0.120 | +0.008 ratio (+7.10%) | 0 | larger |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.117 | 0.116 | -0.000 ratio (-0.25%) | 0 | within noise |
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
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 426.537 | 434.381 | +7.844 KiB (+1.84%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 298.957 | 295.456 | -3.501 KiB (-1.17%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.583 | 0.557 | -0.027 ms (-4.59%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 1.008 | 0.810 | -0.198 ms (-19.67%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 5.214 | 5.037 | -0.177 ms (-3.40%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 37042.758 | 39189.752 | +2146.994 roots/s (+5.80%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 6.262 | 5.550 | -0.712 ms (-11.38%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 31324.434 | 36620.533 | +5296.098 roots/s (+16.91%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 8.114 | 8.106 | -0.008 ms (-0.10%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 24294.695 | 25150.773 | +856.078 roots/s (+3.52%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 251.070 | 231.412 | -19.658 KiB (-7.83%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.150 | 45.315 | +3.165 KiB (+7.51%) | 6 | larger |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 94.190 | 85.505 | -8.686 KiB (-9.22%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 16.165 | 10.883 | -5.282 KiB (-32.68%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1324.136 | 1289.925 | -34.211 KiB (-2.58%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.957 | 521.973 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.841 | 0.728 | -0.113 ms (-13.39%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.268 | 1.043 | -0.224 ms (-17.69%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 8.562 | 8.686 | +0.124 ms (+1.45%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23301.762 | 23203.202 | -98.560 roots/s (-0.42%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 9.401 | 9.410 | +0.008 ms (+0.09%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 20916.400 | 21264.154 | +347.754 roots/s (+1.66%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 12.906 | 12.187 | -0.719 ms (-5.57%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 15932.394 | 16571.096 | +638.701 roots/s (+4.01%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 730.147 | 705.499 | -24.648 KiB (-3.38%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 34.997 | 31.946 | -3.051 KiB (-8.72%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 206.714 | 199.487 | -7.227 KiB (-3.50%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.772 | 3.491 | -0.281 KiB (-7.46%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1745.775 | 1717.600 | -28.176 KiB (-1.61%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.726 | 869.690 | -0.035 KiB (-0.00%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.861 | 0.878 | +0.017 ms (+1.98%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.453 | 2.208 | -0.246 ms (-10.02%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 28.371 | 23.411 | -4.960 ms (-17.48%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 5116.136 | 8490.962 | +3374.825 roots/s (+65.96%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 24.732 | 24.175 | -0.557 ms (-2.25%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8202.296 | 8296.388 | +94.093 roots/s (+1.15%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 32.931 | 27.044 | -5.888 ms (-17.88%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6391.444 | 7383.502 | +992.059 roots/s (+15.52%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1164.876 | 1143.415 | -21.461 KiB (-1.84%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 50.735 | 57.243 | +6.508 KiB (+12.83%) | 6 | larger |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 314.293 | 307.840 | -6.453 KiB (-2.05%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 17.063 | 6.164 | -10.899 KiB (-63.88%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1324.800 | 1280.452 | -44.348 KiB (-3.35%) | 3 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 544.988 | 545.004 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.984 | 0.848 | -0.136 ms (-13.78%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.866 | 1.513 | -0.353 ms (-18.93%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 13.912 | 16.584 | +2.672 ms (+19.20%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 14368.203 | 12235.066 | -2133.137 roots/s (-14.85%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 14.917 | 16.216 | +1.299 ms (+8.71%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12940.761 | 12351.938 | -588.823 roots/s (-4.55%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 17.626 | 19.307 | +1.682 ms (+9.54%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 11059.322 | 10478.221 | -581.100 roots/s (-5.25%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1159.917 | 1139.675 | -20.242 KiB (-1.75%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 44.810 | 40.712 | -4.098 KiB (-9.14%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 320.151 | 313.190 | -6.961 KiB (-2.17%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.093 | 3.812 | -0.281 KiB (-6.87%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 310.761 | 302.880 | -7.881 KiB (-2.54%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.980 | 171.809 | -0.172 KiB (-0.10%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.499 | 0.490 | -0.008 ms (-1.65%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.865 | 0.725 | -0.140 ms (-16.18%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 4.594 | 5.342 | +0.748 ms (+16.28%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 43727.001 | 36814.338 | -6912.664 roots/s (-15.81%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 5.988 | 5.921 | -0.067 ms (-1.12%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 31714.569 | 33828.784 | +2114.215 roots/s (+6.67%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 7.341 | 8.434 | +1.093 ms (+14.89%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 25166.993 | 24077.167 | -1089.825 roots/s (-4.33%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 197.614 | 193.528 | -4.086 KiB (-2.07%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 28.290 | 27.891 | -0.399 KiB (-1.41%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 70.444 | 69.677 | -0.768 KiB (-1.09%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 10.010 | 1.921 | -8.089 KiB (-80.81%) | 6 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.635 | 6.222 | -0.413 us/projection (-6.23%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 152139.720 | 161803.707 | +9663.987 projections/s (+6.35%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.527 | 43.348 | -0.180 KiB (-0.41%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 37.434 | 47.183 | +9.749 KiB (+26.04%) | 3 | larger |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 579.062 | 566.688 | -12.375 B/projection (-2.14%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 117.375 | 126.875 | +9.500 B/projection (+8.09%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.363 | 7.398 | +0.035 us/projection (+0.48%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 137191.837 | 133425.897 | -3765.940 projections/s (-2.75%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 48.465 | 47.434 | -1.031 KiB (-2.13%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 60.448 | 61.369 | +0.921 KiB (+1.52%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 594.062 | 581.688 | -12.375 B/projection (-2.08%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 181.375 | 177.250 | -4.125 B/projection (-2.27%) | 3 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 9.053 | 8.701 | -0.352 ms (-3.89%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 22594.933 | 22735.778 | +140.845 roots/s (+0.62%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.886 | 9.740 | -0.145 ms (-1.47%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20052.220 | 20701.077 | +648.857 roots/s (+3.24%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 17.468 | 16.881 | -0.587 ms (-3.36%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 11362.991 | 12089.919 | +726.928 roots/s (+6.40%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 17.727 | 16.878 | -0.848 ms (-4.78%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10877.447 | 11744.872 | +867.425 roots/s (+7.97%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 33.479 | 32.358 | -1.121 us/root (-3.35%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 108.699 | 99.004 | -9.695 KiB (-8.92%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.836 | 50.852 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 33.026 | 34.210 | +1.184 us/root (+3.58%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 108.699 | 103.316 | -5.383 KiB (-4.95%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.836 | 50.852 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 55.221 | 47.181 | -8.040 us/root (-14.56%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 154.324 | 147.043 | -7.281 KiB (-4.72%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.961 | 87.977 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 54.467 | 48.129 | -6.339 us/root (-11.64%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 153.719 | 150.992 | -2.727 KiB (-1.77%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.961 | 87.977 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 90.431 | 65.573 | -24.858 us/root (-27.49%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 222.836 | 218.461 | -4.375 KiB (-1.96%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.461 | 137.477 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 95.168 | 66.971 | -28.197 us/root (-29.63%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 220.781 | 221.883 | +1.102 KiB (+0.50%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.461 | 137.477 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 23.328 | 24.328 | +1.000 us/root (+4.29%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 67.207 | 62.293 | -4.914 KiB (-7.31%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.086 | 24.102 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 23.785 | 24.643 | +0.858 us/root (+3.61%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 72.957 | 68.605 | -4.352 KiB (-5.96%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.086 | 24.102 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 166.695 | 152.691 | -14.004 us/root (-8.40%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 636.223 | 625.758 | -10.465 KiB (-1.64%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.086 | 428.102 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 159.789 | 151.609 | -8.180 us/root (-5.12%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 633.832 | 629.699 | -4.133 KiB (-0.65%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.086 | 428.102 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 59.622 | 57.185 | -2.437 us/root (-4.09%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 204.992 | 195.082 | -9.910 KiB (-4.83%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.086 | 125.102 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 58.559 | 56.809 | -1.750 us/root (-2.99%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 203.543 | 198.129 | -5.414 KiB (-2.66%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.086 | 125.102 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 50.396 | 46.348 | -4.048 us/root (-8.03%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 138.954 | 128.688 | -10.266 KiB (-7.39%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.930 | 35.945 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 46.914 | 47.410 | +0.496 us/root (+1.06%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 138.954 | 133.001 | -5.953 KiB (-4.28%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.930 | 35.945 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 59.332 | 55.465 | -3.867 us/root (-6.52%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 220.514 | 219.008 | -1.506 KiB (-0.68%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.711 | 136.727 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 58.617 | 56.281 | -2.336 us/root (-3.99%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 223.922 | 222.836 | -1.086 KiB (-0.48%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.711 | 136.727 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 156.977 | 143.681 | -13.296 us/root (-8.47%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 766.938 | 761.578 | -5.359 KiB (-0.70%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.211 | 480.227 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 159.293 | 145.512 | -13.781 us/root (-8.65%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 770.367 | 765.406 | -4.961 KiB (-0.64%) | 3 | within noise |
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
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 120.500 | 89.500 | -31.000 us (-25.73%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 22.546 | 20.526 | -2.020 KiB (-8.96%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.554 | 13.761 | -0.793 KiB (-5.45%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 122.292 | 89.542 | -32.750 us (-26.78%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 23.014 | 20.432 | -2.582 KiB (-11.22%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 15.334 | 13.916 | -1.418 KiB (-9.25%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 138.333 | 87.875 | -50.458 us (-36.48%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 22.546 | 20.526 | -2.020 KiB (-8.96%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.554 | 13.761 | -0.793 KiB (-5.45%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 156.250 | 90.208 | -66.042 us (-42.27%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 23.014 | 20.432 | -2.582 KiB (-11.22%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 15.334 | 13.916 | -1.418 KiB (-9.25%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 169.083 | 90.666 | -78.417 us (-46.38%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 22.547 | 20.527 | -2.020 KiB (-8.96%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.555 | 13.762 | -0.793 KiB (-5.45%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 132.916 | 91.292 | -41.624 us (-31.32%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 23.015 | 20.433 | -2.582 KiB (-11.22%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 15.335 | 13.917 | -1.418 KiB (-9.25%) | 3 | smaller |
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
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 398.742 | 386.686 | -12.057 KiB (-3.02%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 304.437 | 299.688 | -4.748 KiB (-1.56%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.607 | 0.523 | -0.085 ms (-13.94%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 1.007 | 0.811 | -0.196 ms (-19.49%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 5.161 | 5.163 | +0.002 ms (+0.04%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 37734.959 | 39521.786 | +1786.827 roots/s (+4.74%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 6.406 | 5.715 | -0.691 ms (-10.79%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 30923.252 | 35831.320 | +4908.068 roots/s (+15.87%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 8.516 | 8.106 | -0.410 ms (-4.81%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 22713.291 | 24774.963 | +2061.672 roots/s (+9.08%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 238.784 | 214.543 | -24.241 KiB (-10.15%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.356 | 40.480 | -1.876 KiB (-4.43%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 86.590 | 77.941 | -8.648 KiB (-9.99%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 15.571 | 15.609 | +0.038 KiB (+0.24%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1259.475 | 1224.021 | -35.453 KiB (-2.81%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.363 | 531.383 | +0.020 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.713 | 0.743 | +0.031 ms (+4.30%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.184 | 1.116 | -0.067 ms (-5.70%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 8.689 | 8.673 | -0.017 ms (-0.19%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23019.595 | 22885.586 | -134.009 roots/s (-0.58%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 9.467 | 9.525 | +0.058 ms (+0.61%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 20547.507 | 21040.913 | +493.406 roots/s (+2.40%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 12.101 | 12.411 | +0.311 ms (+2.57%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 16343.485 | 15829.411 | -514.074 roots/s (-3.15%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 693.096 | 667.924 | -25.172 KiB (-3.63%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 37.148 | 34.473 | -2.676 KiB (-7.20%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 198.666 | 191.596 | -7.070 KiB (-3.56%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.897 | 3.597 | -0.301 KiB (-7.72%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1799.175 | 1770.636 | -28.539 KiB (-1.59%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.741 | 883.759 | +0.018 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.957 | 0.856 | -0.101 ms (-10.53%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.658 | 2.203 | -0.455 ms (-17.13%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 25.821 | 23.307 | -2.515 ms (-9.74%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7481.390 | 8507.848 | +1026.458 roots/s (+13.72%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 28.592 | 24.139 | -4.453 ms (-15.57%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 7268.840 | 8232.344 | +963.504 roots/s (+13.26%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 32.988 | 27.603 | -5.385 ms (-16.32%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 5950.005 | 7312.481 | +1362.476 roots/s (+22.90%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1199.475 | 1177.754 | -21.721 KiB (-1.81%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 52.239 | 58.687 | +6.447 KiB (+12.34%) | 6 | larger |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 323.182 | 317.093 | -6.089 KiB (-1.88%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 15.179 | 6.336 | -8.843 KiB (-58.26%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1393.275 | 1347.291 | -45.984 KiB (-3.30%) | 3 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.398 | 554.414 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.980 | 0.857 | -0.123 ms (-12.57%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.940 | 1.610 | -0.331 ms (-17.04%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 14.108 | 16.680 | +2.572 ms (+18.23%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 12953.438 | 11941.249 | -1012.189 roots/s (-7.81%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 20.988 | 17.392 | -3.596 ms (-17.13%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11205.319 | 12470.026 | +1264.707 roots/s (+11.29%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 22.796 | 19.528 | -3.268 ms (-14.34%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 7230.211 | 10288.308 | +3058.097 roots/s (+42.30%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1166.908 | 1145.486 | -21.422 KiB (-1.84%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 47.309 | 43.727 | -3.582 KiB (-7.57%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 314.291 | 307.869 | -6.422 KiB (-2.04%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.218 | 3.948 | -0.270 KiB (-6.39%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 298.886 | 278.097 | -20.789 KiB (-6.96%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 175.188 | 174.946 | -0.241 KiB (-0.14%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.517 | 0.491 | -0.026 ms (-5.01%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.887 | 0.722 | -0.165 ms (-18.60%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 6.712 | 5.518 | -1.194 ms (-17.79%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 32432.436 | 36853.622 | +4421.186 roots/s (+13.63%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 6.818 | 5.947 | -0.871 ms (-12.78%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 30927.236 | 33536.413 | +2609.177 roots/s (+8.44%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 9.659 | 8.635 | -1.024 ms (-10.60%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 20596.349 | 23533.565 | +2937.216 roots/s (+14.26%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 205.014 | 200.928 | -4.086 KiB (-1.99%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 30.565 | 28.921 | -1.645 KiB (-5.38%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 69.479 | 67.291 | -2.188 KiB (-3.15%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 7.343 | 1.944 | -5.398 KiB (-73.52%) | 6 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.229 | 6.143 | -0.087 us/projection (-1.39%) | 9 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 161599.444 | 164736.163 | +3136.719 projections/s (+1.94%) | 9 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.777 | 45.496 | -0.281 KiB (-0.61%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 41.361 | 51.560 | +10.198 KiB (+24.66%) | 3 | larger |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 604.438 | 599.672 | -4.766 B/projection (-0.79%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 128.000 | 128.266 | +0.266 B/projection (+0.21%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.105 | 7.661 | +0.557 us/projection (+7.83%) | 9 | slower |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 142883.605 | 131788.931 | -11094.673 projections/s (-7.76%) | 9 | slower |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 50.777 | 49.652 | -1.125 KiB (-2.22%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 65.587 | 66.832 | +1.245 KiB (+1.90%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 620.438 | 615.672 | -4.766 B/projection (-0.77%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 192.000 | 178.766 | -13.234 B/projection (-6.89%) | 3 | smaller |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 10.737 | 8.821 | -1.916 ms (-17.84%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18664.914 | 22435.044 | +3770.130 roots/s (+20.20%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 12.119 | 9.798 | -2.321 ms (-19.15%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 16592.633 | 20345.880 | +3753.247 roots/s (+22.62%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 17.319 | 16.921 | -0.398 ms (-2.30%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10544.537 | 11830.032 | +1285.495 roots/s (+12.19%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 18.911 | 17.183 | -1.728 ms (-9.14%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10101.945 | 11518.111 | +1416.166 roots/s (+14.02%) | 9 | faster |
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
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 31.577 | 32.935 | +1.358 us/root (+4.30%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 106.210 | 97.325 | -8.885 KiB (-8.37%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.094 | 51.109 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 31.960 | 33.327 | +1.367 us/root (+4.28%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 106.104 | 101.036 | -5.068 KiB (-4.78%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.094 | 51.109 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 54.811 | 49.228 | -5.583 us/root (-10.19%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 155.085 | 148.214 | -6.871 KiB (-4.43%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.219 | 88.234 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 57.217 | 50.056 | -7.161 us/root (-12.52%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 153.554 | 151.401 | -2.152 KiB (-1.40%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.219 | 88.234 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 93.339 | 68.637 | -24.702 us/root (-26.46%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 225.687 | 223.218 | -2.469 KiB (-1.09%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.719 | 137.734 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 92.501 | 69.491 | -23.010 us/root (-24.88%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 223.640 | 227.249 | +3.609 KiB (+1.61%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.719 | 137.734 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 23.755 | 24.827 | +1.072 us/root (+4.51%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 65.831 | 61.062 | -4.769 KiB (-7.24%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.344 | 24.359 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 23.191 | 25.079 | +1.888 us/root (+8.14%) | 9 | slower |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 71.503 | 67.422 | -4.081 KiB (-5.71%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.344 | 24.359 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 160.184 | 155.384 | -4.799 us/root (-3.00%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 640.226 | 629.829 | -10.396 KiB (-1.62%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.344 | 428.359 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 159.904 | 157.099 | -2.805 us/root (-1.75%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 637.882 | 633.739 | -4.143 KiB (-0.65%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.344 | 428.359 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 55.896 | 58.341 | +2.445 us/root (+4.37%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 208.030 | 198.134 | -9.896 KiB (-4.76%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.344 | 125.359 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 58.379 | 59.613 | +1.234 us/root (+2.11%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 206.784 | 201.552 | -5.232 KiB (-2.53%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.344 | 125.359 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 48.012 | 47.898 | -0.113 us/root (-0.24%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 136.445 | 127.213 | -9.232 KiB (-6.77%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.188 | 36.203 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 46.010 | 50.958 | +4.948 us/root (+10.75%) | 9 | slower |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 136.367 | 130.924 | -5.443 KiB (-3.99%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.188 | 36.203 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 58.874 | 56.552 | -2.322 us/root (-3.94%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 223.864 | 222.470 | -1.395 KiB (-0.62%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.969 | 136.984 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 57.958 | 56.302 | -1.656 us/root (-2.86%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 227.163 | 226.376 | -0.787 KiB (-0.35%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.969 | 136.984 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 160.504 | 148.523 | -11.980 us/root (-7.46%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 770.265 | 765.188 | -5.076 KiB (-0.66%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.469 | 480.484 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 161.281 | 147.060 | -14.221 us/root (-8.82%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 773.616 | 769.095 | -4.521 KiB (-0.58%) | 3 | within noise |
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
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 125.125 | 91.583 | -33.542 us (-26.81%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 23.571 | 21.005 | -2.566 KiB (-10.89%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 15.938 | 14.981 | -0.957 KiB (-6.00%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 119.458 | 93.292 | -26.166 us (-21.90%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 24.398 | 21.168 | -3.230 KiB (-13.24%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 16.750 | 15.145 | -1.605 KiB (-9.58%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 118.166 | 91.458 | -26.708 us (-22.60%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 23.571 | 21.005 | -2.566 KiB (-10.89%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 15.938 | 14.981 | -0.957 KiB (-6.00%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 114.792 | 93.875 | -20.917 us (-18.22%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 24.398 | 21.164 | -3.234 KiB (-13.26%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 16.750 | 15.145 | -1.605 KiB (-9.58%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 118.084 | 91.875 | -26.209 us (-22.20%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 23.572 | 21.006 | -2.566 KiB (-10.89%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 15.939 | 14.982 | -0.957 KiB (-6.00%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 114.792 | 93.000 | -21.792 us (-18.98%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 24.399 | 21.169 | -3.230 KiB (-13.24%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 16.751 | 15.146 | -1.605 KiB (-9.58%) | 3 | smaller |
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
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 238.583 | 210.416 | -28.167 us/row (-11.81%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 4226.000 | 1432.000 | -2794.000 B/row (-66.11%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 16122.000 | 10958.000 | -5164.000 B/row (-32.03%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 33.000 | 0.000 | -33.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 244.791 | 212.083 | -32.708 us/row (-13.36%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 4226.000 | 1432.000 | -2794.000 B/row (-66.11%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 16122.000 | 11214.000 | -4908.000 B/row (-30.44%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 281.708 | 315.250 | +33.542 us/row (+11.91%) | 9 | slower |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 4226.000 | 1432.000 | -2794.000 B/row (-66.11%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 16002.000 | 9056.000 | -6946.000 B/row (-43.41%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 15.000 | 0.000 | -15.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 291.167 | 289.541 | -1.626 us/row (-0.56%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 4176.000 | 1432.000 | -2744.000 B/row (-65.71%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 16002.000 | 9301.000 | -6701.000 B/row (-41.88%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 310.625 | 357.667 | +47.042 us/row (+15.14%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 5856.000 | 1712.000 | -4144.000 B/row (-70.77%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 17802.000 | 12666.000 | -5136.000 B/row (-28.85%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 105.000 | 0.000 | -105.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 333.458 | 339.000 | +5.542 us/row (+1.66%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 5806.000 | 1712.000 | -4094.000 B/row (-70.51%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 17802.000 | 13442.000 | -4360.000 B/row (-24.49%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 650.541 | 936.833 | +286.292 us/row (+44.01%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 12626.000 | 2832.000 | -9794.000 B/row (-77.57%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 31483.000 | 20923.000 | -10560.000 B/row (-33.54%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 393.000 | 0.000 | -393.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 697.833 | 860.292 | +162.459 us/row (+23.28%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 12576.000 | 2832.000 | -9744.000 B/row (-77.48%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 33140.000 | 23982.000 | -9158.000 B/row (-27.63%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 328.166 | 287.250 | -40.916 us/row (-12.47%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 6620.000 | 2160.000 | -4460.000 B/row (-67.37%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 17612.000 | 15746.000 | -1866.000 B/row (-10.60%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 332.375 | 282.958 | -49.417 us/row (-14.87%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5642.000 | 2390.000 | -3252.000 B/row (-57.64%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16656.000 | 16988.000 | +332.000 B/row (+1.99%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 343.042 | 283.625 | -59.417 us/row (-17.32%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 6570.000 | 2160.000 | -4410.000 B/row (-67.12%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 18709.000 | 16031.000 | -2678.000 B/row (-14.31%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 349.125 | 276.875 | -72.250 us/row (-20.69%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5592.000 | 2491.000 | -3101.000 B/row (-55.45%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 17703.000 | 16914.000 | -789.000 B/row (-4.46%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 205.291 | 111.708 | -93.583 us/row (-45.59%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 3162.000 | 1648.000 | -1514.000 B/row (-47.88%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 16338.000 | 8580.000 | -7758.000 B/row (-47.48%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 208.500 | 112.125 | -96.375 us/row (-46.22%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 3112.000 | 1648.000 | -1464.000 B/row (-47.04%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 16338.000 | 8852.000 | -7486.000 B/row (-45.82%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 30.000 | 0.000 | -30.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 253.125 | 149.750 | -103.375 us/row (-40.84%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 4336.000 | 2320.000 | -2016.000 B/row (-46.49%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 18730.000 | 10341.000 | -8389.000 B/row (-44.79%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 61.000 | 0.000 | -61.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 260.333 | 145.459 | -114.874 us/row (-44.13%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 4336.000 | 2320.000 | -2016.000 B/row (-46.49%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 18730.000 | 10497.000 | -8233.000 B/row (-43.96%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 140.000 | 0.000 | -140.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 330.584 | 194.375 | -136.209 us/row (-41.20%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 6018.000 | 3216.000 | -2802.000 B/row (-46.56%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 22682.000 | 13466.000 | -9216.000 B/row (-40.63%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 191.000 | 0.000 | -191.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 341.667 | 194.375 | -147.292 us/row (-43.11%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 6018.000 | 3216.000 | -2802.000 B/row (-46.56%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 22682.000 | 13552.000 | -9130.000 B/row (-40.25%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 166.542 | 90.125 | -76.417 us/row (-45.88%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 2208.000 | 1144.000 | -1064.000 B/row (-48.19%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 15314.000 | 7425.000 | -7889.000 B/row (-51.51%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 177.750 | 87.125 | -90.625 us/row (-50.98%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 2258.000 | 1144.000 | -1114.000 B/row (-49.34%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 15314.000 | 7447.000 | -7867.000 B/row (-51.37%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 561.209 | 420.833 | -140.376 us/row (-25.01%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 15816.000 | 8608.000 | -7208.000 B/row (-45.57%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 38074.000 | 27376.000 | -10698.000 B/row (-28.10%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 166.000 | 0.000 | -166.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 588.166 | 418.167 | -169.999 us/row (-28.90%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 15816.000 | 8608.000 | -7208.000 B/row (-45.57%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 38637.000 | 27539.000 | -11098.000 B/row (-28.72%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 277.167 | 175.125 | -102.042 us/row (-36.82%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 5640.000 | 3040.000 | -2600.000 B/row (-46.10%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 18866.000 | 11920.000 | -6946.000 B/row (-36.82%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 46.000 | 0.000 | -46.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 291.042 | 173.167 | -117.875 us/row (-40.50%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 5640.000 | 3040.000 | -2600.000 B/row (-46.10%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 18866.000 | 12219.000 | -6647.000 B/row (-35.23%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 235.875 | 159.750 | -76.125 us/row (-32.27%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 3062.000 | 1648.000 | -1414.000 B/row (-46.18%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 16218.000 | 8350.000 | -7868.000 B/row (-48.51%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 7.000 | 0.000 | -7.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 239.917 | 156.042 | -83.875 us/row (-34.96%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 3112.000 | 1648.000 | -1464.000 B/row (-47.04%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 16218.000 | 8619.000 | -7599.000 B/row (-46.86%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 264.959 | 210.708 | -54.251 us/row (-20.48%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 4742.000 | 2488.000 | -2254.000 B/row (-47.53%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 18018.000 | 11360.000 | -6658.000 B/row (-36.95%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 52.000 | 0.000 | -52.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 273.209 | 190.833 | -82.376 us/row (-30.15%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 4792.000 | 2488.000 | -2304.000 B/row (-48.08%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 18018.000 | 11640.000 | -6378.000 B/row (-35.40%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 592.167 | 517.416 | -74.751 us/row (-12.62%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 11512.000 | 5848.000 | -5664.000 B/row (-49.20%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 29130.000 | 23567.000 | -5563.000 B/row (-19.10%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 196.000 | 0.000 | -196.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 619.084 | 515.958 | -103.126 us/row (-16.66%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 11562.000 | 5848.000 | -5714.000 B/row (-49.42%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 30234.000 | 24984.000 | -5250.000 B/row (-17.36%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 182.167 | 156.291 | -25.876 us/row (-14.20%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 3898.000 | 1968.000 | -1930.000 B/row (-49.51%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 17098.000 | 9139.000 | -7959.000 B/row (-46.55%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 173.708 | 142.458 | -31.250 us/row (-17.99%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 2874.000 | 2000.000 | -874.000 B/row (-30.41%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 16026.000 | 9459.000 | -6567.000 B/row (-40.98%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 198.917 | 161.750 | -37.167 us/row (-18.68%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 3848.000 | 1968.000 | -1880.000 B/row (-48.86%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 17098.000 | 9927.000 | -7171.000 B/row (-41.94%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 193.417 | 148.167 | -45.250 us/row (-23.40%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 2874.000 | 2000.000 | -874.000 B/row (-30.41%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 16026.000 | 10247.000 | -5779.000 B/row (-36.06%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 219.875 | 193.125 | -26.750 us/row (-12.17%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 4584.000 | 2110.000 | -2474.000 B/row (-53.97%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 16594.000 | 11309.000 | -5285.000 B/row (-31.85%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 200.417 | 177.250 | -23.167 us/row (-11.56%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3560.000 | 2192.000 | -1368.000 B/row (-38.43%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 15522.000 | 11589.000 | -3933.000 B/row (-25.34%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 256.292 | 202.459 | -53.833 us/row (-21.00%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 4634.000 | 2160.000 | -2474.000 B/row (-53.39%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 16594.000 | 11760.000 | -4834.000 B/row (-29.13%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 222.084 | 191.667 | -30.417 us/row (-13.70%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 3510.000 | 2192.000 | -1318.000 B/row (-37.55%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 15522.000 | 12192.000 | -3330.000 B/row (-21.45%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 193.167 | 116.541 | -76.626 us/row (-39.67%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 3618.000 | 1872.000 | -1746.000 B/row (-48.26%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 17370.000 | 10210.000 | -7160.000 B/row (-41.22%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 173.208 | 119.375 | -53.833 us/row (-31.08%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2612.000 | 1872.000 | -740.000 B/row (-28.33%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 16266.000 | 10394.000 | -5872.000 B/row (-36.10%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 218.791 | 114.625 | -104.166 us/row (-47.61%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 3618.000 | 1872.000 | -1746.000 B/row (-48.26%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 17370.000 | 10242.000 | -7128.000 B/row (-41.04%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 185.875 | 117.834 | -68.041 us/row (-36.61%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 2612.000 | 1872.000 | -740.000 B/row (-28.33%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 16266.000 | 10362.000 | -5904.000 B/row (-36.30%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 222.250 | 87.083 | -135.167 us/row (-60.82%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 4634.000 | 32.000 | -4602.000 B/row (-99.31%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 16594.000 | 7168.000 | -9426.000 B/row (-56.80%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 204.750 | 72.292 | -132.458 us/row (-64.69%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 3610.000 | 32.000 | -3578.000 B/row (-99.11%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 15522.000 | 7184.000 | -8338.000 B/row (-53.72%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 1.000 | 0.000 | -1.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 234.708 | 87.542 | -147.166 us/row (-62.70%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 4634.000 | 32.000 | -4602.000 B/row (-99.31%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 16594.000 | 7168.000 | -9426.000 B/row (-56.80%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 1.000 | 0.000 | -1.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 213.875 | 73.750 | -140.125 us/row (-65.52%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3560.000 | 32.000 | -3528.000 B/row (-99.10%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 15522.000 | 7184.000 | -8338.000 B/row (-53.72%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared | elapsedUs | 4482.250 | 3374.875 | -1107.375 us (-24.71%) | 9 | faster |
| 3.13 | model-preparation | model.prepared | retainedBytes | 635624.000 | 426776.000 | -208848.000 B (-32.86%) | 1 | smaller |
| 3.13 | model-preparation | model.prepared | transientBytes | 652472.000 | 438904.000 | -213568.000 B (-32.73%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | | | | | missing on base |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | | | | | missing on base |
| 3.13 | model-preparation | model.prepared.family | transientBytes | | | | | missing on base |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 49.213 | 24.915 | -24.298 us/row (-49.37%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1580.859 | 913.414 | -667.445 B/row (-42.22%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3530.195 | 2006.625 | -1523.570 B/row (-43.16%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 51.689 | 25.822 | -25.868 us/row (-50.04%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2765.086 | 1914.680 | -850.406 B/row (-30.76%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5686.656 | 2473.766 | -3212.891 B/row (-56.50%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 56.865 | 29.440 | -27.424 us/row (-48.23%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1744.781 | 1057.594 | -687.188 B/row (-39.39%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4061.438 | 2668.031 | -1393.406 B/row (-34.31%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 57.225 | 31.432 | -25.793 us/row (-45.07%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2931.656 | 2048.969 | -882.688 B/row (-30.11%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6223.688 | 3024.812 | -3198.875 B/row (-51.40%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 147.760 | 49.818 | -97.943 us/row (-66.28%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2372.625 | 1528.000 | -844.625 B/row (-35.60%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 5920.375 | 4690.375 | -1230.000 B/row (-20.78%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 77.740 | 49.557 | -28.182 us/row (-36.25%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3601.000 | 2615.375 | -985.625 B/row (-27.37%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 7948.000 | 4926.250 | -3021.750 B/row (-38.02%) | 9 | smaller |
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
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 337.084 | 235.292 | -101.792 us/row (-30.20%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 4272.000 | 1440.000 | -2832.000 B/row (-66.29%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 16498.000 | 11126.000 | -5372.000 B/row (-32.56%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 33.000 | 0.000 | -33.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 361.584 | 239.167 | -122.417 us/row (-33.86%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 4372.000 | 1440.000 | -2932.000 B/row (-67.06%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 16498.000 | 11646.000 | -4852.000 B/row (-29.41%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 411.250 | 361.333 | -49.917 us/row (-12.14%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 4322.000 | 1440.000 | -2882.000 B/row (-66.68%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 16378.000 | 9320.000 | -7058.000 B/row (-43.09%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 15.000 | 0.000 | -15.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 433.041 | 321.875 | -111.166 us/row (-25.67%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 4372.000 | 1440.000 | -2932.000 B/row (-67.06%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 16378.000 | 9741.000 | -6637.000 B/row (-40.52%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 447.625 | 385.167 | -62.458 us/row (-13.95%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 6002.000 | 1720.000 | -4282.000 B/row (-71.34%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 18178.000 | 13026.000 | -5152.000 B/row (-28.34%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 105.000 | 0.000 | -105.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 479.125 | 370.000 | -109.125 us/row (-22.78%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 6002.000 | 1720.000 | -4282.000 B/row (-71.34%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 18178.000 | 13946.000 | -4232.000 B/row (-23.28%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 872.916 | 995.667 | +122.751 us/row (+14.06%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 12772.000 | 2840.000 | -9932.000 B/row (-77.76%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 31835.000 | 23717.000 | -8118.000 B/row (-25.50%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 393.000 | 0.000 | -393.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 916.042 | 920.042 | +4.000 us/row (+0.44%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 12722.000 | 2840.000 | -9882.000 B/row (-77.68%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 33692.000 | 26934.000 | -6758.000 B/row (-20.06%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 366.125 | 318.209 | -47.916 us/row (-13.09%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 6632.000 | 2326.000 | -4306.000 B/row (-64.93%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 17212.000 | 15538.000 | -1674.000 B/row (-9.73%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 345.625 | 318.084 | -27.541 us/row (-7.97%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5746.000 | 2207.000 | -3539.000 B/row (-61.59%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16274.000 | 16694.000 | +420.000 B/row (+2.58%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 367.333 | 311.750 | -55.583 us/row (-15.13%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 6832.000 | 2226.000 | -4606.000 B/row (-67.42%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 18031.000 | 15907.000 | -2124.000 B/row (-11.78%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 363.541 | 311.458 | -52.083 us/row (-14.33%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5746.000 | 2304.000 | -3442.000 B/row (-59.90%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 17323.000 | 17166.000 | -157.000 B/row (-0.91%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 206.292 | 130.291 | -76.001 us/row (-36.84%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 3218.000 | 1704.000 | -1514.000 B/row (-47.05%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 16802.000 | 9116.000 | -7686.000 B/row (-45.74%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 211.083 | 130.208 | -80.875 us/row (-38.31%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 3168.000 | 1704.000 | -1464.000 B/row (-46.21%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 16802.000 | 9516.000 | -7286.000 B/row (-43.36%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 30.000 | 0.000 | -30.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 241.125 | 165.709 | -75.416 us/row (-31.28%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 4442.000 | 2376.000 | -2066.000 B/row (-46.51%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 19290.000 | 10973.000 | -8317.000 B/row (-43.12%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 61.000 | 0.000 | -61.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 258.792 | 168.000 | -90.792 us/row (-35.08%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 4392.000 | 2376.000 | -2016.000 B/row (-45.90%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 19290.000 | 11257.000 | -8033.000 B/row (-41.64%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 140.000 | 0.000 | -140.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 316.375 | 213.709 | -102.666 us/row (-32.45%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 6024.000 | 3272.000 | -2752.000 B/row (-45.68%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 23386.000 | 14186.000 | -9200.000 B/row (-39.34%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 191.000 | 0.000 | -191.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 326.667 | 215.375 | -111.292 us/row (-34.07%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 6024.000 | 3272.000 | -2752.000 B/row (-45.68%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 23386.000 | 14360.000 | -9026.000 B/row (-38.60%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 183.792 | 109.000 | -74.792 us/row (-40.69%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 2256.000 | 1192.000 | -1064.000 B/row (-47.16%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 15770.000 | 7961.000 | -7809.000 B/row (-49.52%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 178.209 | 107.959 | -70.250 us/row (-39.42%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 2256.000 | 1192.000 | -1064.000 B/row (-47.16%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 15770.000 | 8047.000 | -7723.000 B/row (-48.97%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 631.500 | 448.250 | -183.250 us/row (-29.02%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 15822.000 | 8664.000 | -7158.000 B/row (-45.24%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 38426.000 | 27944.000 | -10482.000 B/row (-27.28%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 166.000 | 0.000 | -166.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 732.334 | 447.458 | -284.876 us/row (-38.90%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 15872.000 | 8664.000 | -7208.000 B/row (-45.41%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 38989.000 | 28171.000 | -10818.000 B/row (-27.75%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 308.250 | 197.250 | -111.000 us/row (-36.01%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 5646.000 | 3096.000 | -2550.000 B/row (-45.16%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 19330.000 | 12488.000 | -6842.000 B/row (-35.40%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 46.000 | 0.000 | -46.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 339.666 | 193.458 | -146.208 us/row (-43.04%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 5696.000 | 3096.000 | -2600.000 B/row (-45.65%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 19330.000 | 12883.000 | -6447.000 B/row (-33.35%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 350.875 | 181.000 | -169.875 us/row (-48.41%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 3168.000 | 1704.000 | -1464.000 B/row (-46.21%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 16682.000 | 8918.000 | -7764.000 B/row (-46.54%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 7.000 | 0.000 | -7.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 321.750 | 179.875 | -141.875 us/row (-44.09%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 3118.000 | 1704.000 | -1414.000 B/row (-45.35%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 16682.000 | 9315.000 | -7367.000 B/row (-44.16%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 367.583 | 212.000 | -155.583 us/row (-42.33%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 4898.000 | 2544.000 | -2354.000 B/row (-48.06%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 18482.000 | 11960.000 | -6522.000 B/row (-35.29%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 52.000 | 0.000 | -52.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 396.834 | 214.250 | -182.584 us/row (-46.01%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 4848.000 | 2544.000 | -2304.000 B/row (-47.52%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 18482.000 | 12336.000 | -6146.000 B/row (-33.25%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 812.125 | 550.917 | -261.208 us/row (-32.16%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 11518.000 | 5904.000 | -5614.000 B/row (-48.74%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 29466.000 | 24135.000 | -5331.000 B/row (-18.09%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 196.000 | 0.000 | -196.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 804.792 | 552.667 | -252.125 us/row (-31.33%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 11618.000 | 5904.000 | -5714.000 B/row (-49.18%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 30586.000 | 25680.000 | -4906.000 B/row (-16.04%) | 9 | smaller |
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
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 206.458 | 180.667 | -25.791 us/row (-12.49%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 3986.000 | 2064.000 | -1922.000 B/row (-48.22%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 17658.000 | 9683.000 | -7975.000 B/row (-45.16%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 187.667 | 170.250 | -17.417 us/row (-9.28%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 2954.000 | 2024.000 | -930.000 B/row (-31.48%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 16622.000 | 10163.000 | -6459.000 B/row (-38.86%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 215.417 | 188.208 | -27.209 us/row (-12.63%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 3936.000 | 1992.000 | -1944.000 B/row (-49.39%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 17658.000 | 10535.000 | -7123.000 B/row (-40.34%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 212.375 | 173.750 | -38.625 us/row (-18.19%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 2954.000 | 2024.000 | -930.000 B/row (-31.48%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 16622.000 | 11015.000 | -5607.000 B/row (-33.73%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 241.417 | 221.959 | -19.458 us/row (-8.06%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 4780.000 | 2176.000 | -2604.000 B/row (-54.48%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 16970.000 | 11589.000 | -5381.000 B/row (-31.71%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 220.208 | 204.125 | -16.083 us/row (-7.30%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3748.000 | 2208.000 | -1540.000 B/row (-41.09%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 15934.000 | 12039.000 | -3895.000 B/row (-24.44%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 258.250 | 236.667 | -21.583 us/row (-8.36%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 4730.000 | 2176.000 | -2554.000 B/row (-54.00%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 16970.000 | 12040.000 | -4930.000 B/row (-29.05%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 249.375 | 229.042 | -20.333 us/row (-8.15%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 3648.000 | 2208.000 | -1440.000 B/row (-39.47%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 15934.000 | 12628.000 | -3306.000 B/row (-20.75%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 206.500 | 134.875 | -71.625 us/row (-34.69%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 3674.000 | 1928.000 | -1746.000 B/row (-47.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 17882.000 | 10650.000 | -7232.000 B/row (-40.44%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 193.458 | 139.000 | -54.458 us/row (-28.15%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2660.000 | 1928.000 | -732.000 B/row (-27.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 16818.000 | 10762.000 | -6056.000 B/row (-36.01%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 219.750 | 133.958 | -85.792 us/row (-39.04%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 3674.000 | 1928.000 | -1746.000 B/row (-47.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 17882.000 | 10794.000 | -7088.000 B/row (-39.64%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 196.792 | 136.042 | -60.750 us/row (-30.87%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 2610.000 | 1928.000 | -682.000 B/row (-26.13%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 16818.000 | 10898.000 | -5920.000 B/row (-35.20%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 242.584 | 97.417 | -145.167 us/row (-59.84%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 4780.000 | 32.000 | -4748.000 B/row (-99.33%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 16970.000 | 7744.000 | -9226.000 B/row (-54.37%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 229.125 | 84.625 | -144.500 us/row (-63.07%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 3748.000 | 32.000 | -3716.000 B/row (-99.15%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 15934.000 | 7856.000 | -8078.000 B/row (-50.70%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 1.000 | 0.000 | -1.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 254.917 | 97.834 | -157.083 us/row (-61.62%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 4780.000 | 32.000 | -4748.000 B/row (-99.33%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 16970.000 | 7744.000 | -9226.000 B/row (-54.37%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 1.000 | 0.000 | -1.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 230.834 | 84.042 | -146.792 us/row (-63.59%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3698.000 | 32.000 | -3666.000 B/row (-99.13%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 15934.000 | 7856.000 | -8078.000 B/row (-50.70%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared | elapsedUs | 6119.166 | 3321.958 | -2797.208 us (-45.71%) | 9 | faster |
| 3.14 | model-preparation | model.prepared | retainedBytes | 649080.000 | 438440.000 | -210640.000 B (-32.45%) | 1 | smaller |
| 3.14 | model-preparation | model.prepared | transientBytes | 655608.000 | 444984.000 | -210624.000 B (-32.13%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | | | | | missing on base |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | | | | | missing on base |
| 3.14 | model-preparation | model.prepared.family | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 66.841 | 24.938 | -41.904 us/row (-62.69%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1618.188 | 997.680 | -620.508 B/row (-38.35%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3680.914 | 2046.617 | -1634.297 B/row (-44.40%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 60.566 | 25.788 | -34.779 us/row (-57.42%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2810.047 | 1995.680 | -814.367 B/row (-28.98%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5852.656 | 2432.477 | -3420.180 B/row (-58.44%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 73.352 | 29.803 | -43.548 us/row (-59.37%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1806.812 | 1141.531 | -665.281 B/row (-36.82%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4227.344 | 2709.031 | -1518.312 B/row (-35.92%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 71.617 | 30.316 | -41.301 us/row (-57.67%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 3000.219 | 2149.625 | -850.594 B/row (-28.35%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6414.844 | 3035.250 | -3379.594 B/row (-52.68%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 114.922 | 49.339 | -65.583 us/row (-57.07%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2572.375 | 1717.875 | -854.500 B/row (-33.22%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 6239.125 | 4875.625 | -1363.500 B/row (-21.85%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 98.667 | 50.938 | -47.729 us/row (-48.37%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3802.875 | 2823.500 | -979.375 B/row (-25.75%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 8226.125 | 5111.125 | -3115.000 B/row (-37.87%) | 9 | smaller |
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
