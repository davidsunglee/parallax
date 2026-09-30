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
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.437 | 3.491 | +0.054 ratio (+1.56%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.437 | 3.491 | +0.054 ratio (+1.56%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.445 | 3.402 | -0.043 ratio (-1.25%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 0.739 | 0.509 | -0.230 ratio (-31.15%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.likeForLike | 0.709 | 0.490 | -0.220 ratio (-30.97%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 2.371 | 1.536 | -0.835 ratio (-35.22%) | 0 | smaller |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.211 | 2.146 | -0.065 ratio (-2.95%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.211 | 2.146 | -0.065 ratio (-2.95%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.222 | 2.157 | -0.065 ratio (-2.91%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 25245.917 | 1510.108 | -23735.809 ns (-94.02%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 11927.437 | 6811.038 | -5116.400 ns (-42.90%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.dumpNs | 7137.104 | 5916.395 | -1220.709 ns (-17.10%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 9092.000 | 4770.000 | -4322.000 B (-47.54%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.readNs | 102.513 | 85.100 | -17.413 ns (-16.99%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 473.936 | 343.561 | -130.375 ns (-27.51%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 8028.000 | 3706.000 | -4322.000 B (-53.84%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 473.936 | 343.561 | -130.375 ns (-27.51%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | -51.098 | 93.333 | +144.431 ns (-282.66%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 11445.431 | 10265.000 | -1180.431 ns (-10.31%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2870.354 | 2526.896 | -343.458 ns (-11.97%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 4960.000 | 4960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.readNs | 30.329 | 25.196 | -5.133 ns (-16.93%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2168.000 | 2168.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 336.871 | 281.133 | -55.738 ns (-16.55%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 5897.650 | 6079.742 | +182.092 ns (+3.09%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2936.708 | 2531.125 | -405.583 ns (-13.81%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 30.471 | 26.296 | -4.175 ns (-13.70%) | 0 | smaller |
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
| - | - | cpython-3.13/nullable | compact.callNs | 13496.825 | 1361.179 | -12135.646 ns (-89.91%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 3742.404 | 2298.321 | -1444.083 ns (-38.59%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.dumpNs | 2157.854 | 1803.146 | -354.708 ns (-16.44%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 5768.000 | 3464.000 | -2304.000 B (-39.94%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.readNs | 90.271 | 75.127 | -15.144 ns (-16.78%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 242.359 | 211.975 | -30.384 ns (-12.54%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.transientBytes | 5304.000 | 3000.000 | -2304.000 B (-43.44%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 242.359 | 211.975 | -30.384 ns (-12.54%) | 0 | smaller |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 244.194 | 261.804 | +17.610 ns (+7.21%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 6299.098 | 5431.612 | -867.485 ns (-13.77%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 1045.459 | 868.333 | -177.126 ns (-16.94%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 26.917 | 20.717 | -6.200 ns (-23.03%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 231.783 | 214.400 | -17.383 ns (-7.50%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1481.175 | 1208.683 | -272.492 ns (-18.40%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 1041.521 | 861.354 | -180.166 ns (-17.30%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 26.990 | 21.413 | -5.577 ns (-20.66%) | 0 | smaller |
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
| - | - | cpython-3.13/partial | compact.callNs | 12705.281 | 1345.192 | -11360.089 ns (-89.41%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 3207.740 | 2149.287 | -1058.452 ns (-33.00%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.dumpNs | 2111.979 | 1831.895 | -280.084 ns (-13.26%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 5856.000 | 3432.000 | -2424.000 B (-41.39%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.readNs | 87.129 | 75.433 | -11.696 ns (-13.42%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 323.083 | 213.566 | -109.517 ns (-33.90%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.transientBytes | 5424.000 | 3000.000 | -2424.000 B (-44.69%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 323.083 | 213.566 | -109.517 ns (-33.90%) | 0 | smaller |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 208.846 | 264.500 | +55.654 ns (+26.65%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5763.279 | 5074.187 | -689.092 ns (-11.96%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.dumpNs | 1045.813 | 867.417 | -178.396 ns (-17.06%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 25.813 | 21.052 | -4.760 ns (-18.44%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 229.827 | 203.019 | -26.808 ns (-11.66%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 1128.985 | 951.440 | -177.546 ns (-15.73%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 1015.041 | 886.667 | -128.375 ns (-12.65%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 25.302 | 21.596 | -3.706 ns (-14.65%) | 0 | smaller |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 28863.865 | 1284.673 | -27579.191 ns (-95.55%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 3578.260 | 2229.744 | -1348.517 ns (-37.69%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1921.208 | 1591.000 | -330.208 ns (-17.19%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 8960.000 | 3408.000 | -5552.000 B (-61.96%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.readNs | 93.244 | 80.211 | -13.033 ns (-13.98%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 386.689 | 214.131 | -172.558 ns (-44.62%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 8552.000 | 3000.000 | -5552.000 B (-64.92%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 386.689 | 214.131 | -172.558 ns (-44.62%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 274.933 | 150.506 | -124.427 ns (-45.26%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4701.879 | 4170.160 | -531.719 ns (-11.31%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 938.541 | 794.625 | -143.916 ns (-15.33%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 27.958 | 23.931 | -4.027 ns (-14.40%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 235.950 | 190.210 | -45.740 ns (-19.39%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1248.321 | 1046.144 | -202.177 ns (-16.20%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 918.437 | 769.125 | -149.312 ns (-16.26%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 27.092 | 24.164 | -2.929 ns (-10.81%) | 0 | smaller |
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
| - | - | cpython-3.13/shallow | compact.callNs | 10711.742 | 1333.219 | -9378.523 ns (-87.55%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 2940.675 | 2054.344 | -886.331 ns (-30.14%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1620.646 | 1354.375 | -266.271 ns (-16.43%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 5632.000 | 3384.000 | -2248.000 B (-39.91%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.readNs | 102.734 | 88.714 | -14.021 ns (-13.65%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 186.003 | 204.991 | +18.988 ns (+10.21%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.transientBytes | 5248.000 | 3000.000 | -2248.000 B (-42.84%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 186.003 | 204.991 | +18.988 ns (+10.21%) | 0 | larger |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 281.900 | 188.856 | -93.044 ns (-33.01%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 3049.954 | 2789.769 | -260.185 ns (-8.53%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 804.000 | 700.834 | -103.167 ns (-12.83%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 29.792 | 25.375 | -4.417 ns (-14.83%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 218.183 | 175.575 | -42.608 ns (-19.53%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 864.233 | 781.092 | -83.142 ns (-9.62%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 801.563 | 714.250 | -87.313 ns (-10.89%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 30.062 | 25.943 | -4.120 ns (-13.70%) | 0 | smaller |
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
| - | - | cpython-3.13/warmed | compact.callNs | 11830.179 | 1586.002 | -10244.177 ns (-86.59%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 5462.821 | 4176.831 | -1285.990 ns (-23.54%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.dumpNs | 2039.750 | 1718.479 | -321.270 ns (-15.75%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 5816.000 | 3384.000 | -2432.000 B (-41.82%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.readNs | 101.755 | 91.828 | -9.927 ns (-9.76%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | -99.547 | 245.993 | +345.539 ns (-347.11%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.transientBytes | 5010.000 | 2578.000 | -2432.000 B (-48.54%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 0.000 | 245.993 | +245.993 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 194.696 | 85.595 | -109.100 ns (-56.04%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 4395.429 | 3910.550 | -484.879 ns (-11.03%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 853.375 | 711.521 | -141.854 ns (-16.62%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 30.781 | 25.302 | -5.479 ns (-17.80%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 245.131 | 190.673 | -54.458 ns (-22.22%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1970.952 | 1759.035 | -211.917 ns (-10.75%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 838.937 | 716.437 | -122.500 ns (-14.60%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 30.677 | 25.870 | -4.807 ns (-15.67%) | 0 | smaller |
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
| - | - | cpython-3.13/wide | compact.callNs | 14688.787 | 1382.158 | -13306.629 ns (-90.59%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 4443.171 | 2612.904 | -1830.267 ns (-41.19%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.dumpNs | 2910.521 | 2407.542 | -502.979 ns (-17.28%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 6320.000 | 3512.000 | -2808.000 B (-44.43%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.readNs | 98.698 | 79.258 | -19.440 ns (-19.70%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 86.635 | 216.351 | +129.716 ns (+149.73%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.transientBytes | 5808.000 | 3000.000 | -2808.000 B (-48.35%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 86.635 | 216.351 | +129.716 ns (+149.73%) | 0 | larger |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | -138.439 | 210.731 | +349.170 ns (-252.22%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 9112.585 | 7945.623 | -1166.962 ns (-12.81%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1373.792 | 1187.958 | -185.833 ns (-13.53%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 26.379 | 22.345 | -4.034 ns (-15.29%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 215.811 | 167.508 | -48.302 ns (-22.38%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1966.773 | 1754.929 | -211.844 ns (-10.77%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1323.667 | 1145.666 | -178.000 ns (-13.45%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 26.879 | 22.819 | -4.060 ns (-15.10%) | 0 | smaller |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.134 | 3.170 | +0.036 ratio (+1.15%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.134 | 3.170 | +0.036 ratio (+1.15%) | 0 | within noise |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.159 | 3.132 | -0.027 ratio (-0.87%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 0.814 | 0.493 | -0.321 ratio (-39.45%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.likeForLike | 0.781 | 0.474 | -0.307 ratio (-39.25%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 2.490 | 1.478 | -1.011 ratio (-40.62%) | 0 | smaller |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.138 | 2.148 | +0.010 ratio (+0.46%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.138 | 2.148 | +0.010 ratio (+0.46%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.189 | 2.156 | -0.033 ratio (-1.52%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 26602.598 | 1612.133 | -24990.465 ns (-93.94%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 15020.798 | 6584.346 | -8436.452 ns (-56.17%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.dumpNs | 8641.333 | 6112.042 | -2529.291 ns (-29.27%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 9396.000 | 5034.000 | -4362.000 B (-46.42%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.readNs | 120.837 | 85.400 | -35.437 ns (-29.33%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | -269.557 | 299.568 | +569.124 ns (-211.13%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 8164.000 | 3802.000 | -4362.000 B (-53.43%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 0.000 | 299.568 | +299.568 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | -105.009 | 286.002 | +391.011 ns (-372.36%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 12425.592 | 11036.498 | -1389.094 ns (-11.18%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 3392.271 | 2614.709 | -777.562 ns (-22.92%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5184.000 | 5184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.readNs | 36.262 | 26.550 | -9.712 ns (-26.78%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2264.000 | 2264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 370.583 | 237.058 | -133.525 ns (-36.03%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 6564.979 | 6220.192 | -344.788 ns (-5.25%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 3228.354 | 2616.834 | -611.521 ns (-18.94%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4744.000 | 4744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 33.767 | 26.600 | -7.167 ns (-21.22%) | 0 | smaller |
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
| - | - | cpython-3.14/nullable | compact.callNs | 18101.698 | 1495.450 | -16606.248 ns (-91.74%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 4844.365 | 2282.300 | -2562.065 ns (-52.89%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.dumpNs | 2435.146 | 1866.854 | -568.291 ns (-23.34%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 6296.000 | 3672.000 | -2624.000 B (-41.68%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.readNs | 103.467 | 78.090 | -25.377 ns (-24.53%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 556.920 | 207.017 | -349.903 ns (-62.83%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 5800.000 | 3176.000 | -2624.000 B (-45.24%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 556.920 | 207.017 | -349.903 ns (-62.83%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 310.979 | 228.417 | -82.563 ns (-26.55%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 7840.104 | 5485.271 | -2354.833 ns (-30.04%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 1386.104 | 919.938 | -466.166 ns (-33.63%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 38.050 | 23.906 | -14.144 ns (-37.17%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 356.925 | 199.567 | -157.358 ns (-44.09%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1924.825 | 1269.329 | -655.496 ns (-34.05%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 1403.063 | 902.437 | -500.625 ns (-35.68%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 37.535 | 25.490 | -12.046 ns (-32.09%) | 0 | smaller |
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
| - | - | cpython-3.14/partial | compact.callNs | 13892.875 | 1393.679 | -12499.196 ns (-89.97%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 3238.250 | 2160.925 | -1077.325 ns (-33.27%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.dumpNs | 2127.188 | 1856.479 | -270.709 ns (-12.73%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 6320.000 | 3576.000 | -2744.000 B (-43.42%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.readNs | 90.888 | 78.333 | -12.554 ns (-13.81%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 296.376 | 225.827 | -70.549 ns (-23.80%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 5856.000 | 3112.000 | -2744.000 B (-46.86%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 296.376 | 225.827 | -70.549 ns (-23.80%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 346.745 | 203.819 | -142.927 ns (-41.22%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 5943.275 | 5016.285 | -926.990 ns (-15.60%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 1142.937 | 906.021 | -236.916 ns (-20.73%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 30.971 | 23.579 | -7.392 ns (-23.87%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 254.527 | 207.912 | -46.615 ns (-18.31%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 1204.723 | 956.233 | -248.490 ns (-20.63%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 1118.958 | 886.021 | -232.937 ns (-20.82%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 31.790 | 24.787 | -7.002 ns (-22.03%) | 0 | smaller |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 29780.252 | 1412.710 | -28367.542 ns (-95.26%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 3659.227 | 2200.894 | -1458.333 ns (-39.85%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1917.604 | 1663.354 | -254.250 ns (-13.26%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 9176.000 | 3552.000 | -5624.000 B (-61.29%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.readNs | 96.372 | 80.229 | -16.143 ns (-16.75%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 412.436 | 229.962 | -182.474 ns (-44.24%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 8736.000 | 3112.000 | -5624.000 B (-64.38%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 412.436 | 229.962 | -182.474 ns (-44.24%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 281.438 | 208.190 | -73.248 ns (-26.03%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4532.896 | 4026.873 | -506.023 ns (-11.16%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 975.584 | 800.416 | -175.167 ns (-17.96%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 30.045 | 26.458 | -3.586 ns (-11.94%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 209.410 | 189.569 | -19.842 ns (-9.48%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1242.277 | 1095.723 | -146.554 ns (-11.80%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 951.146 | 799.375 | -151.771 ns (-15.96%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 30.018 | 25.988 | -4.030 ns (-13.42%) | 0 | smaller |
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
| - | - | cpython-3.14/shallow | compact.callNs | 11737.550 | 1412.962 | -10324.588 ns (-87.96%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 3513.033 | 2106.996 | -1406.037 ns (-40.02%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1743.104 | 1423.708 | -319.396 ns (-18.32%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 6048.000 | 3528.000 | -2520.000 B (-41.67%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.readNs | 109.797 | 87.552 | -22.245 ns (-20.26%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 510.573 | 211.997 | -298.576 ns (-58.48%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 5632.000 | 3112.000 | -2520.000 B (-44.74%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 510.573 | 211.997 | -298.576 ns (-58.48%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 505.237 | 180.077 | -325.160 ns (-64.36%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 3212.804 | 2839.360 | -373.444 ns (-11.62%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 865.187 | 735.291 | -129.896 ns (-15.01%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 31.974 | 28.766 | -3.208 ns (-10.03%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 191.435 | 204.050 | +12.614 ns (+6.59%) | 0 | larger |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 1001.794 | 810.783 | -191.010 ns (-19.07%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 904.916 | 744.417 | -160.500 ns (-17.74%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 32.886 | 28.047 | -4.839 ns (-14.71%) | 0 | smaller |
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
| - | - | cpython-3.14/warmed | compact.callNs | 11840.606 | 1688.460 | -10152.146 ns (-85.74%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 6115.727 | 4229.227 | -1886.500 ns (-30.85%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 2201.770 | 1742.666 | -459.104 ns (-20.85%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 6232.000 | 3528.000 | -2704.000 B (-43.39%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.readNs | 117.271 | 89.443 | -27.828 ns (-23.73%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 374.343 | 233.228 | -141.116 ns (-37.70%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.transientBytes | 5394.000 | 2690.000 | -2704.000 B (-50.13%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 374.343 | 233.228 | -141.116 ns (-37.70%) | 0 | smaller |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 59.194 | 145.202 | +86.009 ns (+145.30%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 4651.035 | 3949.131 | -701.904 ns (-15.09%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 953.188 | 734.000 | -219.188 ns (-23.00%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 34.422 | 28.370 | -6.052 ns (-17.58%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 217.869 | 211.746 | -6.123 ns (-2.81%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 2045.298 | 1787.546 | -257.752 ns (-12.60%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 871.084 | 722.416 | -148.667 ns (-17.07%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 31.937 | 28.609 | -3.328 ns (-10.42%) | 0 | smaller |
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
| - | - | cpython-3.14/wide | compact.callNs | 16279.285 | 1450.754 | -14828.531 ns (-91.09%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 4543.027 | 2547.913 | -1995.115 ns (-43.92%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.dumpNs | 2845.917 | 2421.084 | -424.834 ns (-14.93%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 6736.000 | 3720.000 | -3016.000 B (-44.77%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.readNs | 97.708 | 80.668 | -17.040 ns (-17.44%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 24.472 | 227.277 | +202.805 ns (+828.71%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.transientBytes | 6192.000 | 3176.000 | -3016.000 B (-48.71%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 24.472 | 227.277 | +202.805 ns (+828.71%) | 0 | larger |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 175.358 | 204.417 | +29.058 ns (+16.57%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 8827.829 | 7885.833 | -941.996 ns (-10.67%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1458.396 | 1168.229 | -290.167 ns (-19.90%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 30.237 | 25.401 | -4.836 ns (-15.99%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 253.979 | 171.269 | -82.710 ns (-32.57%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 2047.104 | 1745.148 | -301.956 ns (-14.75%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1397.500 | 1168.230 | -229.271 ns (-16.41%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 29.974 | 25.645 | -4.329 ns (-14.44%) | 0 | smaller |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 4.296 | 3.299 | -0.997 us/event (-23.21%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 4.859 | 3.698 | -1.161 us/event (-23.89%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.242 | 0.271 | +0.029 ratio (+11.87%) | 0 | larger |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.027 | 0.021 | -0.005 ratio (-20.45%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.080 | 0.069 | -0.011 ratio (-14.29%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.006 | 0.005 | -0.001 ratio (-22.62%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.173 | 0.171 | -0.002 ratio (-1.10%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p50 | 615.583 | 433.208 | -182.375 us (-29.63%) | 0 | faster |
| - | - | Safe logging alone, at INFO | observed.p95 | 663.875 | 444.875 | -219.000 us (-32.99%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 120.292 | 92.375 | -27.917 us (-23.21%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 136.042 | 103.542 | -32.500 us (-23.89%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.241 | 0.271 | +0.031 ratio (+12.69%) | 0 | larger |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.293 | 0.304 | +0.011 ratio (+3.92%) | 0 | larger |
| - | - | Safe logging alone, at INFO | plain.p50 | 496.500 | 340.833 | -155.667 us (-31.35%) | 0 | faster |
| - | - | Safe logging alone, at INFO | plain.p95 | 534.917 | 349.416 | -185.501 us (-34.68%) | 0 | faster |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.240 | 0.271 | +0.031 ratio (+13.00%) | 0 | larger |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.241 | 0.273 | +0.032 ratio (+13.32%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.717 | 2.375 | -0.342 us/event (-12.60%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 3.667 | 2.696 | -0.970 us/event (-26.46%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.173 | 0.196 | +0.023 ratio (+13.30%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.017 | 0.015 | -0.002 ratio (-10.57%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.053 | 0.050 | -0.003 ratio (-6.03%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.004 | 0.003 | -0.000 ratio (-12.16%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.119 | 0.123 | +0.004 ratio (+3.70%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | observed.p50 | 517.167 | 406.375 | -110.792 us (-21.42%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | observed.p95 | 562.625 | 417.791 | -144.834 us (-25.74%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 76.083 | 66.500 | -9.583 us (-12.60%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 102.667 | 75.500 | -27.167 us (-26.46%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.172 | 0.196 | +0.023 ratio (+13.43%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.232 | 0.221 | -0.011 ratio (-4.87%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | plain.p50 | 440.500 | 339.833 | -100.667 us (-22.85%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | plain.p95 | 479.500 | 348.750 | -130.750 us (-27.27%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.174 | 0.196 | +0.022 ratio (+12.50%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.173 | 0.198 | +0.025 ratio (+14.20%) | 0 | larger |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 4.586 | 3.988 | -0.598 us/event (-13.04%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 5.567 | 4.429 | -1.138 us/event (-20.45%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.291 | 0.327 | +0.037 ratio (+12.60%) | 0 | larger |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.029 | 0.026 | -0.003 ratio (-11.03%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.089 | 0.083 | -0.006 ratio (-6.52%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.006 | 0.005 | -0.001 ratio (-12.61%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.200 | 0.206 | +0.006 ratio (+3.13%) | 0 | larger |
| - | - | fan-out of three, tracing every root | observed.p50 | 570.834 | 453.000 | -117.834 us (-20.64%) | 0 | faster |
| - | - | fan-out of three, tracing every root | observed.p95 | 620.875 | 466.417 | -154.458 us (-24.88%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 128.417 | 111.667 | -16.750 us (-13.04%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 155.875 | 124.000 | -31.875 us (-20.45%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.292 | 0.327 | +0.036 ratio (+12.26%) | 0 | larger |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.351 | 0.365 | +0.014 ratio (+3.96%) | 0 | larger |
| - | - | fan-out of three, tracing every root | plain.p50 | 441.792 | 341.166 | -100.626 us (-22.78%) | 0 | faster |
| - | - | fan-out of three, tracing every root | plain.p95 | 481.125 | 347.708 | -133.417 us (-27.73%) | 0 | faster |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.292 | 0.328 | +0.036 ratio (+12.23%) | 0 | larger |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.290 | 0.341 | +0.051 ratio (+17.54%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 5.051 | 3.830 | -1.220 us/event (-24.16%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 6.737 | 4.476 | -2.260 us/event (-33.55%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.284 | 0.314 | +0.030 ratio (+10.63%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.031 | 0.025 | -0.007 ratio (-21.42%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.094 | 0.080 | -0.014 ratio (-15.30%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.007 | 0.005 | -0.002 ratio (-23.58%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.203 | 0.198 | -0.004 ratio (-2.22%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 652.167 | 448.459 | -203.708 us (-31.24%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 833.500 | 471.625 | -361.875 us (-43.42%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 141.417 | 107.250 | -34.167 us (-24.16%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 188.625 | 125.334 | -63.291 us (-33.55%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.277 | 0.315 | +0.037 ratio (+13.35%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.340 | 0.364 | +0.024 ratio (+7.13%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 498.292 | 341.583 | -156.709 us (-31.45%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 651.750 | 348.166 | -303.584 us (-46.58%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.309 | 0.313 | +0.004 ratio (+1.32%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.279 | 0.355 | +0.076 ratio (+27.16%) | 0 | larger |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.658 | 1.442 | -0.216 us/event (-13.01%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 2.543 | 1.757 | -0.786 us/event (-30.90%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.110 | 0.119 | +0.009 ratio (+8.60%) | 0 | larger |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.010 | 0.009 | -0.001 ratio (-11.32%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.033 | 0.030 | -0.002 ratio (-7.54%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-12.65%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.074 | 0.075 | +0.000 ratio (+0.59%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p50 | 471.084 | 379.959 | -91.125 us (-19.34%) | 0 | faster |
| - | - | one Handler that keeps nothing | observed.p95 | 506.000 | 389.875 | -116.125 us (-22.95%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 46.416 | 40.375 | -6.041 us (-13.01%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 71.208 | 49.208 | -22.000 us (-30.90%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.109 | 0.119 | +0.010 ratio (+8.80%) | 0 | larger |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.168 | 0.145 | -0.023 ratio (-13.76%) | 0 | smaller |
| - | - | one Handler that keeps nothing | plain.p50 | 423.708 | 339.375 | -84.333 us (-19.90%) | 0 | faster |
| - | - | one Handler that keeps nothing | plain.p95 | 453.125 | 347.291 | -105.834 us (-23.36%) | 0 | faster |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.112 | 0.120 | +0.008 ratio (+6.95%) | 0 | larger |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.117 | 0.123 | +0.006 ratio (+5.08%) | 0 | larger |
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
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 426.537 | 433.007 | +6.470 KiB (+1.52%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 298.957 | 295.412 | -3.545 KiB (-1.19%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.583 | 0.501 | -0.082 ms (-14.05%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 1.008 | 0.736 | -0.272 ms (-27.00%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 5.214 | 5.085 | -0.129 ms (-2.48%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 37042.758 | 39309.466 | +2266.708 roots/s (+6.12%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 6.262 | 5.561 | -0.701 ms (-11.19%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 31324.434 | 36340.511 | +5016.076 roots/s (+16.01%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 8.114 | 7.376 | -0.738 ms (-9.09%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 24294.695 | 24922.507 | +627.812 roots/s (+2.58%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 251.070 | 232.833 | -18.237 KiB (-7.26%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.150 | 43.103 | +0.952 KiB (+2.26%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 94.190 | 86.093 | -8.098 KiB (-8.60%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 16.165 | 12.164 | -4.001 KiB (-24.75%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1324.136 | 1289.925 | -34.211 KiB (-2.58%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.957 | 521.973 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.841 | 0.673 | -0.168 ms (-19.94%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.268 | 1.086 | -0.182 ms (-14.33%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 8.562 | 8.610 | +0.048 ms (+0.56%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23301.762 | 23401.622 | +99.861 roots/s (+0.43%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 9.401 | 9.393 | -0.009 ms (-0.09%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 20916.400 | 21562.663 | +646.264 roots/s (+3.09%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 12.906 | 12.608 | -0.298 ms (-2.31%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 15932.394 | 16483.969 | +551.575 roots/s (+3.46%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 730.147 | 705.499 | -24.648 KiB (-3.38%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 34.997 | 31.946 | -3.051 KiB (-8.72%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 206.714 | 199.487 | -7.227 KiB (-3.50%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.772 | 3.491 | -0.281 KiB (-7.46%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1745.775 | 1717.554 | -28.222 KiB (-1.62%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.726 | 869.741 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.861 | 0.837 | -0.023 ms (-2.72%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.453 | 2.165 | -0.289 ms (-11.77%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 28.371 | 23.432 | -4.939 ms (-17.41%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 5116.136 | 8618.554 | +3502.417 roots/s (+68.46%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 24.732 | 23.894 | -0.838 ms (-3.39%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8202.296 | 8302.401 | +100.105 roots/s (+1.22%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 32.931 | 26.905 | -6.026 ms (-18.30%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6391.444 | 7409.225 | +1017.782 roots/s (+15.92%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1164.876 | 1143.466 | -21.410 KiB (-1.84%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 50.735 | 60.523 | +9.788 KiB (+19.29%) | 6 | larger |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 314.293 | 307.846 | -6.447 KiB (-2.05%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 17.063 | 6.146 | -10.918 KiB (-63.98%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1324.800 | 1280.452 | -44.348 KiB (-3.35%) | 3 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 544.988 | 545.004 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.984 | 0.879 | -0.104 ms (-10.62%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.866 | 1.544 | -0.322 ms (-17.25%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 13.912 | 16.227 | +2.314 ms (+16.63%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 14368.203 | 11783.768 | -2584.435 roots/s (-17.99%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 14.917 | 15.961 | +1.045 ms (+7.00%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12940.761 | 12528.973 | -411.787 roots/s (-3.18%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 17.626 | 19.033 | +1.408 ms (+7.99%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 11059.322 | 10524.862 | -534.460 roots/s (-4.83%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1159.917 | 1139.675 | -20.242 KiB (-1.75%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 44.810 | 40.712 | -4.098 KiB (-9.14%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 320.151 | 313.190 | -6.961 KiB (-2.17%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.093 | 3.812 | -0.281 KiB (-6.87%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 310.761 | 302.834 | -7.927 KiB (-2.55%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.980 | 171.809 | -0.172 KiB (-0.10%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.499 | 0.400 | -0.098 ms (-19.70%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.865 | 0.649 | -0.216 ms (-24.94%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 4.594 | 5.244 | +0.650 ms (+14.14%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 43727.001 | 37934.166 | -5792.835 roots/s (-13.25%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 5.988 | 5.654 | -0.335 ms (-5.59%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 31714.569 | 34824.246 | +3109.677 roots/s (+9.81%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 7.341 | 7.850 | +0.509 ms (+6.94%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 25166.993 | 25260.499 | +93.506 roots/s (+0.37%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 197.614 | 193.528 | -4.086 KiB (-2.07%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 28.290 | 35.106 | +6.816 KiB (+24.09%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 70.444 | 69.660 | -0.784 KiB (-1.11%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 10.010 | 1.926 | -8.084 KiB (-80.76%) | 6 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.635 | 6.345 | -0.290 us/projection (-4.38%) | 9 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 152139.720 | 163143.780 | +11004.060 projections/s (+7.23%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.527 | 43.348 | -0.180 KiB (-0.41%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 37.434 | 47.183 | +9.749 KiB (+26.04%) | 3 | larger |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 579.062 | 566.688 | -12.375 B/projection (-2.14%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 117.375 | 126.875 | +9.500 B/projection (+8.09%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.363 | 7.347 | -0.016 us/projection (-0.21%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 137191.837 | 136618.440 | -573.396 projections/s (-0.42%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 48.465 | 47.434 | -1.031 KiB (-2.13%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 60.448 | 61.369 | +0.921 KiB (+1.52%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 594.062 | 581.688 | -12.375 B/projection (-2.08%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 181.375 | 177.250 | -4.125 B/projection (-2.27%) | 3 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 9.053 | 8.678 | -0.375 ms (-4.14%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 22594.933 | 23049.109 | +454.176 roots/s (+2.01%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.886 | 9.614 | -0.272 ms (-2.75%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20052.220 | 20635.397 | +583.177 roots/s (+2.91%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 17.468 | 16.535 | -0.933 ms (-5.34%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 11362.991 | 12126.296 | +763.305 roots/s (+6.72%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 17.727 | 16.678 | -1.048 ms (-5.91%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10877.447 | 11932.343 | +1054.896 roots/s (+9.70%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 33.479 | 32.525 | -0.954 us/root (-2.85%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 108.699 | 99.004 | -9.695 KiB (-8.92%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.836 | 50.852 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 33.026 | 32.776 | -0.250 us/root (-0.76%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 108.699 | 103.316 | -5.383 KiB (-4.95%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.836 | 50.852 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 55.221 | 47.617 | -7.604 us/root (-13.77%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 154.324 | 147.043 | -7.281 KiB (-4.72%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.961 | 87.977 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 54.467 | 47.147 | -7.320 us/root (-13.44%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 153.719 | 150.992 | -2.727 KiB (-1.77%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.961 | 87.977 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 90.431 | 65.646 | -24.785 us/root (-27.41%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 222.836 | 218.461 | -4.375 KiB (-1.96%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.461 | 137.477 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 95.168 | 67.285 | -27.883 us/root (-29.30%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 220.781 | 221.883 | +1.102 KiB (+0.50%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.461 | 137.477 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 23.328 | 24.202 | +0.874 us/root (+3.75%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 67.207 | 62.293 | -4.914 KiB (-7.31%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.086 | 24.102 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 23.785 | 24.853 | +1.068 us/root (+4.49%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 72.957 | 68.605 | -4.352 KiB (-5.96%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.086 | 24.102 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 166.695 | 152.355 | -14.340 us/root (-8.60%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 636.223 | 625.758 | -10.465 KiB (-1.64%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.086 | 428.102 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 159.789 | 151.146 | -8.643 us/root (-5.41%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 633.832 | 629.699 | -4.133 KiB (-0.65%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.086 | 428.102 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 59.622 | 56.049 | -3.573 us/root (-5.99%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 204.992 | 195.082 | -9.910 KiB (-4.83%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.086 | 125.102 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 58.559 | 56.990 | -1.569 us/root (-2.68%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 203.543 | 198.129 | -5.414 KiB (-2.66%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.086 | 125.102 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 50.396 | 47.100 | -3.296 us/root (-6.54%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 138.954 | 128.688 | -10.266 KiB (-7.39%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.930 | 35.945 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 46.914 | 47.395 | +0.480 us/root (+1.02%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 138.954 | 133.001 | -5.953 KiB (-4.28%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.930 | 35.945 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 59.332 | 55.443 | -3.889 us/root (-6.56%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 220.514 | 219.008 | -1.506 KiB (-0.68%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.711 | 136.727 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 58.617 | 54.898 | -3.719 us/root (-6.34%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 223.922 | 222.836 | -1.086 KiB (-0.48%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.711 | 136.727 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 156.977 | 144.585 | -12.392 us/root (-7.89%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 766.938 | 761.578 | -5.359 KiB (-0.70%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.211 | 480.227 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 159.293 | 143.919 | -15.374 us/root (-9.65%) | 9 | faster |
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
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 120.500 | 90.541 | -29.959 us (-24.86%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 22.546 | 20.526 | -2.020 KiB (-8.96%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.554 | 13.761 | -0.793 KiB (-5.45%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 122.292 | 91.917 | -30.375 us (-24.84%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 23.014 | 20.428 | -2.586 KiB (-11.24%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 15.334 | 13.912 | -1.422 KiB (-9.27%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 138.333 | 90.875 | -47.458 us (-34.31%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 22.546 | 20.526 | -2.020 KiB (-8.96%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.554 | 13.761 | -0.793 KiB (-5.45%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 156.250 | 91.875 | -64.375 us (-41.20%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 23.014 | 20.432 | -2.582 KiB (-11.22%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 15.334 | 13.916 | -1.418 KiB (-9.25%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 169.083 | 91.166 | -77.917 us (-46.08%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 22.547 | 20.527 | -2.020 KiB (-8.96%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.555 | 13.762 | -0.793 KiB (-5.45%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 132.916 | 91.916 | -41.000 us (-30.85%) | 9 | faster |
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
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 398.742 | 395.411 | -3.331 KiB (-0.84%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 304.437 | 298.570 | -5.866 KiB (-1.93%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.607 | 0.530 | -0.078 ms (-12.83%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 1.007 | 0.765 | -0.242 ms (-24.04%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 5.161 | 5.138 | -0.023 ms (-0.45%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 37734.959 | 37022.756 | -712.203 roots/s (-1.89%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 6.406 | 5.619 | -0.787 ms (-12.29%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 30923.252 | 36076.663 | +5153.411 roots/s (+16.67%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 8.516 | 8.085 | -0.431 ms (-5.06%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 22713.291 | 25413.500 | +2700.209 roots/s (+11.89%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 238.784 | 214.200 | -24.584 KiB (-10.30%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.356 | 43.921 | +1.564 KiB (+3.69%) | 6 | larger |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 86.590 | 76.287 | -10.303 KiB (-11.90%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 15.571 | 12.428 | -3.144 KiB (-20.19%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1259.475 | 1224.021 | -35.453 KiB (-2.81%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.363 | 531.383 | +0.020 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.713 | 0.667 | -0.046 ms (-6.48%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.184 | 0.994 | -0.189 ms (-15.99%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 8.689 | 8.815 | +0.126 ms (+1.45%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23019.595 | 22775.152 | -244.443 roots/s (-1.06%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 9.467 | 9.254 | -0.213 ms (-2.25%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 20547.507 | 21608.773 | +1061.266 roots/s (+5.16%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 12.101 | 11.920 | -0.181 ms (-1.50%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 16343.485 | 17235.311 | +891.826 roots/s (+5.46%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 693.096 | 667.924 | -25.172 KiB (-3.63%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 37.148 | 34.473 | -2.676 KiB (-7.20%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 198.666 | 191.596 | -7.070 KiB (-3.56%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.897 | 3.597 | -0.301 KiB (-7.72%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1799.175 | 1770.685 | -28.490 KiB (-1.58%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.741 | 883.711 | -0.030 KiB (-0.00%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.957 | 0.799 | -0.158 ms (-16.47%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.658 | 2.199 | -0.459 ms (-17.27%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 25.821 | 23.432 | -2.389 ms (-9.25%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7481.390 | 8510.126 | +1028.735 roots/s (+13.75%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 28.592 | 24.274 | -4.317 ms (-15.10%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 7268.840 | 8211.445 | +942.605 roots/s (+12.97%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 32.988 | 27.605 | -5.383 ms (-16.32%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 5950.005 | 7359.852 | +1409.847 roots/s (+23.69%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1199.475 | 1177.861 | -21.613 KiB (-1.80%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 52.239 | 59.062 | +6.822 KiB (+13.06%) | 6 | larger |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 323.182 | 317.229 | -5.953 KiB (-1.84%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 15.179 | 6.274 | -8.904 KiB (-58.66%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1393.275 | 1347.291 | -45.984 KiB (-3.30%) | 3 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.398 | 554.414 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.980 | 0.727 | -0.253 ms (-25.83%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.940 | 1.515 | -0.425 ms (-21.89%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 14.108 | 17.473 | +3.365 ms (+23.85%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 12953.438 | 11458.555 | -1494.883 roots/s (-11.54%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 20.988 | 16.913 | -4.075 ms (-19.42%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11205.319 | 11767.042 | +561.723 roots/s (+5.01%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 22.796 | 19.365 | -3.432 ms (-15.05%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 7230.211 | 10242.666 | +3012.455 roots/s (+41.66%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1166.908 | 1145.486 | -21.422 KiB (-1.84%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 47.309 | 43.727 | -3.582 KiB (-7.57%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 314.291 | 307.869 | -6.422 KiB (-2.04%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.218 | 3.948 | -0.270 KiB (-6.39%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 298.886 | 278.097 | -20.789 KiB (-6.96%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 175.188 | 175.000 | -0.188 KiB (-0.11%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.517 | 0.526 | +0.008 ms (+1.63%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.887 | 0.776 | -0.111 ms (-12.54%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 6.712 | 5.423 | -1.289 ms (-19.20%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 32432.436 | 34188.034 | +1755.598 roots/s (+5.41%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 6.818 | 6.576 | -0.243 ms (-3.56%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 30927.236 | 31431.917 | +504.681 roots/s (+1.63%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 9.659 | 9.395 | -0.264 ms (-2.73%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 20596.349 | 21728.306 | +1131.958 roots/s (+5.50%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 205.014 | 200.928 | -4.086 KiB (-1.99%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 30.565 | 31.434 | +0.868 KiB (+2.84%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 69.479 | 67.442 | -2.036 KiB (-2.93%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 7.343 | 1.998 | -5.345 KiB (-72.79%) | 6 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.229 | 6.167 | -0.062 us/projection (-0.99%) | 9 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 161599.444 | 163543.580 | +1944.137 projections/s (+1.20%) | 9 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.777 | 45.496 | -0.281 KiB (-0.61%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 41.361 | 51.560 | +10.198 KiB (+24.66%) | 3 | larger |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 604.438 | 599.672 | -4.766 B/projection (-0.79%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 128.000 | 128.266 | +0.266 B/projection (+0.21%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.105 | 7.609 | +0.505 us/projection (+7.10%) | 9 | slower |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 142883.605 | 132129.034 | -10754.570 projections/s (-7.53%) | 9 | slower |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 50.777 | 49.652 | -1.125 KiB (-2.22%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 65.587 | 66.832 | +1.245 KiB (+1.90%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 620.438 | 615.672 | -4.766 B/projection (-0.77%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 192.000 | 178.766 | -13.234 B/projection (-6.89%) | 3 | smaller |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 10.737 | 9.370 | -1.367 ms (-12.73%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18664.914 | 21259.443 | +2594.530 roots/s (+13.90%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 12.119 | 10.511 | -1.608 ms (-13.26%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 16592.633 | 18977.883 | +2385.250 roots/s (+14.38%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 17.319 | 16.850 | -0.469 ms (-2.71%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10544.537 | 11857.385 | +1312.848 roots/s (+12.45%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 18.911 | 17.084 | -1.826 ms (-9.66%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10101.945 | 11708.516 | +1606.571 roots/s (+15.90%) | 9 | faster |
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
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 31.577 | 32.863 | +1.286 us/root (+4.07%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 106.210 | 97.325 | -8.885 KiB (-8.37%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.094 | 51.109 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 31.960 | 33.620 | +1.660 us/root (+5.19%) | 9 | slower |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 106.104 | 101.036 | -5.068 KiB (-4.78%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.094 | 51.109 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 54.811 | 47.891 | -6.921 us/root (-12.63%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 155.085 | 148.214 | -6.871 KiB (-4.43%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.219 | 88.234 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 57.217 | 48.647 | -8.570 us/root (-14.98%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 153.554 | 151.401 | -2.152 KiB (-1.40%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.219 | 88.234 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 93.339 | 68.923 | -24.415 us/root (-26.16%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 225.687 | 223.218 | -2.469 KiB (-1.09%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.719 | 137.734 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 92.501 | 68.695 | -23.806 us/root (-25.74%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 223.640 | 227.249 | +3.609 KiB (+1.61%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.719 | 137.734 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 23.755 | 24.316 | +0.561 us/root (+2.36%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 65.831 | 61.062 | -4.769 KiB (-7.24%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.344 | 24.359 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 23.191 | 24.865 | +1.673 us/root (+7.21%) | 9 | slower |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 71.503 | 67.422 | -4.081 KiB (-5.71%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.344 | 24.359 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 160.184 | 154.587 | -5.596 us/root (-3.49%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 640.226 | 629.829 | -10.396 KiB (-1.62%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.344 | 428.359 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 159.904 | 155.785 | -4.118 us/root (-2.58%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 637.882 | 633.739 | -4.143 KiB (-0.65%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.344 | 428.359 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 55.896 | 58.184 | +2.288 us/root (+4.09%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 208.030 | 198.134 | -9.896 KiB (-4.76%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.344 | 125.359 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 58.379 | 58.388 | +0.009 us/root (+0.02%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 206.784 | 201.552 | -5.232 KiB (-2.53%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.344 | 125.359 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 48.012 | 48.576 | +0.564 us/root (+1.17%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 136.445 | 127.213 | -9.232 KiB (-6.77%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.188 | 36.203 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 46.010 | 48.583 | +2.573 us/root (+5.59%) | 9 | slower |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 136.367 | 130.924 | -5.443 KiB (-3.99%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.188 | 36.203 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 58.874 | 55.711 | -3.163 us/root (-5.37%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 223.864 | 222.470 | -1.395 KiB (-0.62%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.969 | 136.984 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 57.958 | 56.578 | -1.380 us/root (-2.38%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 227.163 | 226.376 | -0.787 KiB (-0.35%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.969 | 136.984 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 160.504 | 145.680 | -14.824 us/root (-9.24%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 770.265 | 765.188 | -5.076 KiB (-0.66%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.469 | 480.484 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 161.281 | 147.206 | -14.076 us/root (-8.73%) | 9 | faster |
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
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 125.125 | 92.208 | -32.917 us (-26.31%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 23.571 | 21.005 | -2.566 KiB (-10.89%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 15.938 | 14.981 | -0.957 KiB (-6.00%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 119.458 | 93.792 | -25.666 us (-21.49%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 24.398 | 21.168 | -3.230 KiB (-13.24%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 16.750 | 15.145 | -1.605 KiB (-9.58%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 118.166 | 90.833 | -27.333 us (-23.13%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 23.571 | 21.005 | -2.566 KiB (-10.89%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 15.938 | 14.981 | -0.957 KiB (-6.00%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 114.792 | 93.042 | -21.750 us (-18.95%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 24.398 | 21.168 | -3.230 KiB (-13.24%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 16.750 | 15.145 | -1.605 KiB (-9.58%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 118.084 | 92.041 | -26.043 us (-22.05%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 23.572 | 21.006 | -2.566 KiB (-10.89%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 15.939 | 14.982 | -0.957 KiB (-6.00%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 114.792 | 93.333 | -21.459 us (-18.69%) | 9 | faster |
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
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 238.583 | 212.333 | -26.250 us/row (-11.00%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 4226.000 | 1432.000 | -2794.000 B/row (-66.11%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 16122.000 | 10866.000 | -5256.000 B/row (-32.60%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 33.000 | 0.000 | -33.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 244.791 | 212.667 | -32.124 us/row (-13.12%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 4226.000 | 1432.000 | -2794.000 B/row (-66.11%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 16122.000 | 11114.000 | -5008.000 B/row (-31.06%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 281.708 | 312.500 | +30.792 us/row (+10.93%) | 9 | slower |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 4226.000 | 1432.000 | -2794.000 B/row (-66.11%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 16002.000 | 8956.000 | -7046.000 B/row (-44.03%) | 9 | smaller |
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
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 16002.000 | 9201.000 | -6801.000 B/row (-42.50%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 310.625 | 353.417 | +42.792 us/row (+13.78%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 5856.000 | 1712.000 | -4144.000 B/row (-70.77%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 17802.000 | 12574.000 | -5228.000 B/row (-29.37%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 105.000 | 0.000 | -105.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 333.458 | 341.417 | +7.959 us/row (+2.39%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 5806.000 | 1712.000 | -4094.000 B/row (-70.51%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 17802.000 | 13350.000 | -4452.000 B/row (-25.01%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 650.541 | 945.166 | +294.625 us/row (+45.29%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 12626.000 | 2832.000 | -9794.000 B/row (-77.57%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 31483.000 | 20857.000 | -10626.000 B/row (-33.75%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 393.000 | 0.000 | -393.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 697.833 | 865.041 | +167.208 us/row (+23.96%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 12576.000 | 2832.000 | -9744.000 B/row (-77.48%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 33140.000 | 23890.000 | -9250.000 B/row (-27.91%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 328.166 | 286.959 | -41.207 us/row (-12.56%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 6620.000 | 2160.000 | -4460.000 B/row (-67.37%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 17612.000 | 15296.000 | -2316.000 B/row (-13.15%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 332.375 | 277.166 | -55.209 us/row (-16.61%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5642.000 | 2288.000 | -3354.000 B/row (-59.45%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16656.000 | 16140.000 | -516.000 B/row (-3.10%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 343.042 | 279.333 | -63.709 us/row (-18.57%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 6570.000 | 2160.000 | -4410.000 B/row (-67.12%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 18709.000 | 15481.000 | -3228.000 B/row (-17.25%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 349.125 | 270.083 | -79.042 us/row (-22.64%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5592.000 | 2288.000 | -3304.000 B/row (-59.08%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 17703.000 | 16221.000 | -1482.000 B/row (-8.37%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 205.291 | 110.459 | -94.832 us/row (-46.19%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 208.500 | 110.375 | -98.125 us/row (-47.06%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 253.125 | 145.542 | -107.583 us/row (-42.50%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 260.333 | 146.500 | -113.833 us/row (-43.73%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 330.584 | 193.167 | -137.417 us/row (-41.57%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 341.667 | 191.750 | -149.917 us/row (-43.88%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 166.542 | 88.667 | -77.875 us/row (-46.76%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 177.750 | 86.792 | -90.958 us/row (-51.17%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 561.209 | 414.292 | -146.917 us/row (-26.18%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 588.166 | 412.250 | -175.916 us/row (-29.91%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 277.167 | 171.333 | -105.834 us/row (-38.18%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 291.042 | 173.208 | -117.834 us/row (-40.49%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 235.875 | 156.708 | -79.167 us/row (-33.56%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 239.917 | 153.625 | -86.292 us/row (-35.97%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 264.959 | 191.084 | -73.875 us/row (-27.88%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 273.209 | 190.208 | -83.001 us/row (-30.38%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 592.167 | 514.542 | -77.625 us/row (-13.11%) | 9 | faster |
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
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 619.084 | 516.792 | -102.292 us/row (-16.52%) | 9 | faster |
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
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 182.167 | 156.209 | -25.958 us/row (-14.25%) | 9 | faster |
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
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 173.708 | 141.000 | -32.708 us/row (-18.83%) | 9 | faster |
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
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 198.917 | 163.792 | -35.125 us/row (-17.66%) | 9 | faster |
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
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 193.417 | 146.042 | -47.375 us/row (-24.49%) | 9 | faster |
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
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 219.875 | 192.000 | -27.875 us/row (-12.68%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 4584.000 | 2160.000 | -2424.000 B/row (-52.88%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 16594.000 | 11217.000 | -5377.000 B/row (-32.40%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 200.417 | 180.833 | -19.584 us/row (-9.77%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3560.000 | 2192.000 | -1368.000 B/row (-38.43%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 15522.000 | 11517.000 | -4005.000 B/row (-25.80%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 256.292 | 201.958 | -54.334 us/row (-21.20%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 4634.000 | 2160.000 | -2474.000 B/row (-53.39%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 16594.000 | 11668.000 | -4926.000 B/row (-29.69%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 222.084 | 187.958 | -34.126 us/row (-15.37%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 3510.000 | 2192.000 | -1318.000 B/row (-37.55%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 15522.000 | 12096.000 | -3426.000 B/row (-22.07%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 193.167 | 113.167 | -80.000 us/row (-41.41%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 3618.000 | 1872.000 | -1746.000 B/row (-48.26%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 17370.000 | 10118.000 | -7252.000 B/row (-41.75%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 173.208 | 116.292 | -56.916 us/row (-32.86%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2612.000 | 1872.000 | -740.000 B/row (-28.33%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 16266.000 | 10302.000 | -5964.000 B/row (-36.67%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 218.791 | 111.458 | -107.333 us/row (-49.06%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 3618.000 | 1872.000 | -1746.000 B/row (-48.26%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 17370.000 | 10142.000 | -7228.000 B/row (-41.61%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 185.875 | 114.083 | -71.792 us/row (-38.62%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 2612.000 | 1872.000 | -740.000 B/row (-28.33%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 16266.000 | 10262.000 | -6004.000 B/row (-36.91%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 222.250 | 85.833 | -136.417 us/row (-61.38%) | 9 | faster |
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
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 204.750 | 72.584 | -132.166 us/row (-64.55%) | 9 | faster |
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
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 234.708 | 86.542 | -148.166 us/row (-63.13%) | 9 | faster |
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
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 213.875 | 73.417 | -140.458 us/row (-65.67%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3560.000 | 32.000 | -3528.000 B/row (-99.10%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 15522.000 | 7184.000 | -8338.000 B/row (-53.72%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared | elapsedUs | 4482.250 | 3301.625 | -1180.625 us (-26.34%) | 9 | faster |
| 3.13 | model-preparation | model.prepared | retainedBytes | 635624.000 | 426776.000 | -208848.000 B (-32.86%) | 1 | smaller |
| 3.13 | model-preparation | model.prepared | transientBytes | 652472.000 | 438904.000 | -213568.000 B (-32.73%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | | | | | missing on base |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | | | | | missing on base |
| 3.13 | model-preparation | model.prepared.family | transientBytes | | | | | missing on base |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 49.213 | 24.610 | -24.604 us/row (-49.99%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1580.859 | 911.875 | -668.984 B/row (-42.32%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3530.195 | 2003.484 | -1526.711 B/row (-43.25%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 51.689 | 25.523 | -26.166 us/row (-50.62%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2765.086 | 1913.375 | -851.711 B/row (-30.80%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5686.656 | 2469.828 | -3216.828 B/row (-56.57%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 56.865 | 29.146 | -27.719 us/row (-48.75%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1744.781 | 1032.500 | -712.281 B/row (-40.82%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4061.438 | 2650.812 | -1410.625 B/row (-34.73%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 57.225 | 30.404 | -26.822 us/row (-46.87%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2931.656 | 2038.500 | -893.156 B/row (-30.47%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6223.688 | 3010.688 | -3213.000 B/row (-51.63%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 147.760 | 48.323 | -99.437 us/row (-67.30%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2372.625 | 1523.000 | -849.625 B/row (-35.81%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 5920.375 | 4640.250 | -1280.125 B/row (-21.62%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 77.740 | 49.375 | -28.365 us/row (-36.49%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3601.000 | 2547.000 | -1054.000 B/row (-29.27%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 7948.000 | 4862.750 | -3085.250 B/row (-38.82%) | 9 | smaller |
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
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 337.084 | 234.500 | -102.584 us/row (-30.43%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 4272.000 | 1440.000 | -2832.000 B/row (-66.29%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 16498.000 | 11034.000 | -5464.000 B/row (-33.12%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 33.000 | 0.000 | -33.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 361.584 | 237.375 | -124.209 us/row (-34.35%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 4372.000 | 1440.000 | -2932.000 B/row (-67.06%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 16498.000 | 11554.000 | -4944.000 B/row (-29.97%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 411.250 | 342.750 | -68.500 us/row (-16.66%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 4322.000 | 1440.000 | -2882.000 B/row (-66.68%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 16378.000 | 9220.000 | -7158.000 B/row (-43.70%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 15.000 | 0.000 | -15.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 433.041 | 318.208 | -114.833 us/row (-26.52%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 4372.000 | 1440.000 | -2932.000 B/row (-67.06%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 16378.000 | 9649.000 | -6729.000 B/row (-41.09%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 447.625 | 383.334 | -64.291 us/row (-14.36%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 6002.000 | 1720.000 | -4282.000 B/row (-71.34%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 18178.000 | 12926.000 | -5252.000 B/row (-28.89%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 105.000 | 0.000 | -105.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 479.125 | 372.500 | -106.625 us/row (-22.25%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 6002.000 | 1720.000 | -4282.000 B/row (-71.34%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 18178.000 | 13854.000 | -4324.000 B/row (-23.79%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 872.916 | 998.333 | +125.417 us/row (+14.37%) | 9 | slower |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 12772.000 | 2840.000 | -9932.000 B/row (-77.76%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 31835.000 | 23617.000 | -8218.000 B/row (-25.81%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 393.000 | 0.000 | -393.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 916.042 | 912.750 | -3.292 us/row (-0.36%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 12722.000 | 2840.000 | -9882.000 B/row (-77.68%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 33692.000 | 26834.000 | -6858.000 B/row (-20.35%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 366.125 | 313.792 | -52.333 us/row (-14.29%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 6632.000 | 2176.000 | -4456.000 B/row (-67.19%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 17212.000 | 14896.000 | -2316.000 B/row (-13.46%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 345.625 | 308.417 | -37.208 us/row (-10.77%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5746.000 | 2304.000 | -3442.000 B/row (-59.90%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16274.000 | 16004.000 | -270.000 B/row (-1.66%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 367.333 | 310.083 | -57.250 us/row (-15.59%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 6832.000 | 2176.000 | -4656.000 B/row (-68.15%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 18031.000 | 15217.000 | -2814.000 B/row (-15.61%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 363.541 | 298.583 | -64.958 us/row (-17.87%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5746.000 | 2304.000 | -3442.000 B/row (-59.90%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 17323.000 | 16325.000 | -998.000 B/row (-5.76%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 206.292 | 130.458 | -75.834 us/row (-36.76%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 211.083 | 130.458 | -80.625 us/row (-38.20%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 241.125 | 170.875 | -70.250 us/row (-29.13%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 258.792 | 167.416 | -91.376 us/row (-35.31%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 316.375 | 218.500 | -97.875 us/row (-30.94%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 326.667 | 214.416 | -112.251 us/row (-34.36%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 183.792 | 108.375 | -75.417 us/row (-41.03%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 178.209 | 106.084 | -72.125 us/row (-40.47%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 631.500 | 440.500 | -191.000 us/row (-30.25%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 732.334 | 442.667 | -289.667 us/row (-39.55%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 308.250 | 192.458 | -115.792 us/row (-37.56%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 339.666 | 193.459 | -146.207 us/row (-43.04%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 350.875 | 181.917 | -168.958 us/row (-48.15%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 321.750 | 180.708 | -141.042 us/row (-43.84%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 367.583 | 217.875 | -149.708 us/row (-40.73%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 396.834 | 214.084 | -182.750 us/row (-46.05%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 812.125 | 553.375 | -258.750 us/row (-31.86%) | 9 | faster |
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
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 804.792 | 553.584 | -251.208 us/row (-31.21%) | 9 | faster |
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
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 206.458 | 179.750 | -26.708 us/row (-12.94%) | 9 | faster |
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
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 187.667 | 172.791 | -14.876 us/row (-7.93%) | 9 | faster |
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
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 215.417 | 186.791 | -28.626 us/row (-13.29%) | 9 | faster |
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
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 212.375 | 171.708 | -40.667 us/row (-19.15%) | 9 | faster |
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
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 241.417 | 219.458 | -21.959 us/row (-9.10%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 4780.000 | 2176.000 | -2604.000 B/row (-54.48%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 16970.000 | 11489.000 | -5481.000 B/row (-32.30%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 220.208 | 202.875 | -17.333 us/row (-7.87%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3748.000 | 2208.000 | -1540.000 B/row (-41.09%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 15934.000 | 11949.000 | -3985.000 B/row (-25.01%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 258.250 | 230.125 | -28.125 us/row (-10.89%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 4730.000 | 2176.000 | -2554.000 B/row (-54.00%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 16970.000 | 11948.000 | -5022.000 B/row (-29.59%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 249.375 | 219.500 | -29.875 us/row (-11.98%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 3648.000 | 2208.000 | -1440.000 B/row (-39.47%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 15934.000 | 12536.000 | -3398.000 B/row (-21.33%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 206.500 | 136.459 | -70.041 us/row (-33.92%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 3674.000 | 1928.000 | -1746.000 B/row (-47.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 17882.000 | 10550.000 | -7332.000 B/row (-41.00%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 193.458 | 137.000 | -56.458 us/row (-29.18%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2660.000 | 1928.000 | -732.000 B/row (-27.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 16818.000 | 10670.000 | -6148.000 B/row (-36.56%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 219.750 | 132.084 | -87.666 us/row (-39.89%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 3674.000 | 1928.000 | -1746.000 B/row (-47.52%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 17882.000 | 10702.000 | -7180.000 B/row (-40.15%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 196.792 | 137.750 | -59.042 us/row (-30.00%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 2610.000 | 1928.000 | -682.000 B/row (-26.13%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 16818.000 | 10798.000 | -6020.000 B/row (-35.79%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 242.584 | 97.125 | -145.459 us/row (-59.96%) | 9 | faster |
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
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 229.125 | 82.834 | -146.291 us/row (-63.85%) | 9 | faster |
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
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 254.917 | 97.042 | -157.875 us/row (-61.93%) | 9 | faster |
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
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 230.834 | 83.250 | -147.584 us/row (-63.94%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3698.000 | 32.000 | -3666.000 B/row (-99.13%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 15934.000 | 7856.000 | -8078.000 B/row (-50.70%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared | elapsedUs | 6119.166 | 3316.333 | -2802.833 us (-45.80%) | 9 | faster |
| 3.14 | model-preparation | model.prepared | retainedBytes | 649080.000 | 438440.000 | -210640.000 B (-32.45%) | 1 | smaller |
| 3.14 | model-preparation | model.prepared | transientBytes | 655608.000 | 444984.000 | -210624.000 B (-32.13%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | | | | | missing on base |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | | | | | missing on base |
| 3.14 | model-preparation | model.prepared.family | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 66.841 | 24.527 | -42.314 us/row (-63.31%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1618.188 | 985.594 | -632.594 B/row (-39.09%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3680.914 | 2050.805 | -1630.109 B/row (-44.29%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 60.566 | 25.059 | -35.508 us/row (-58.63%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2810.047 | 1987.219 | -822.828 B/row (-29.28%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5852.656 | 2436.273 | -3416.383 B/row (-58.37%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 73.352 | 29.635 | -43.716 us/row (-59.60%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1806.812 | 1135.375 | -671.438 B/row (-37.16%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4227.344 | 2696.094 | -1531.250 B/row (-36.22%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 71.617 | 29.749 | -41.868 us/row (-58.46%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 3000.219 | 2141.875 | -858.344 B/row (-28.61%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6414.844 | 3022.219 | -3392.625 B/row (-52.89%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 114.922 | 49.297 | -65.625 us/row (-57.10%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2572.375 | 1742.500 | -829.875 B/row (-32.26%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 6239.125 | 4822.375 | -1416.750 B/row (-22.71%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 98.667 | 51.656 | -47.010 us/row (-47.65%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3802.875 | 2768.500 | -1034.375 B/row (-27.20%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 8226.125 | 5052.875 | -3173.250 B/row (-38.58%) | 9 | smaller |
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
