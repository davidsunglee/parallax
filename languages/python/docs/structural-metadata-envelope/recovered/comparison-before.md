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
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.437 | 3.498 | +0.061 ratio (+1.77%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.437 | 3.498 | +0.061 ratio (+1.77%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.445 | 3.386 | -0.059 ratio (-1.72%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 0.739 | 0.800 | +0.061 ratio (+8.21%) | 0 | larger |
| - | - | cpython-3.13 | operation.construction.likeForLike | 0.709 | 0.773 | +0.063 ratio (+8.92%) | 0 | larger |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 2.371 | 2.377 | +0.006 ratio (+0.26%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.211 | 2.198 | -0.013 ratio (-0.57%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.211 | 2.198 | -0.013 ratio (-0.57%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.222 | 2.173 | -0.049 ratio (-2.20%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 25245.917 | 14777.158 | -10468.759 ns (-41.47%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 11927.437 | 11622.404 | -305.033 ns (-2.56%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.dumpNs | 7137.104 | 5724.958 | -1412.146 ns (-19.79%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 9092.000 | 7324.000 | -1768.000 B (-19.45%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.readNs | 102.513 | 86.783 | -15.729 ns (-15.34%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 473.936 | 171.580 | -302.356 ns (-63.80%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 8028.000 | 6260.000 | -1768.000 B (-22.02%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 473.936 | 171.580 | -302.356 ns (-63.80%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | -51.098 | 93.640 | +144.737 ns (-283.26%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 11445.431 | 10428.985 | -1016.446 ns (-8.88%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2870.354 | 2437.084 | -433.270 ns (-15.09%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 4960.000 | 4960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.readNs | 30.329 | 25.504 | -4.825 ns (-15.91%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2168.000 | 2168.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 336.871 | 376.206 | +39.335 ns (+11.68%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 5897.650 | 6092.273 | +194.623 ns (+3.30%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2936.708 | 2420.354 | -516.354 ns (-17.58%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 30.471 | 26.046 | -4.425 ns (-14.52%) | 0 | smaller |
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
| - | - | cpython-3.13/nullable | compact.callNs | 13496.825 | 9527.265 | -3969.561 ns (-29.41%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 3742.404 | 3480.173 | -262.231 ns (-7.01%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.dumpNs | 2157.854 | 1922.062 | -235.792 ns (-10.93%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 5768.000 | 5176.000 | -592.000 B (-10.26%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.readNs | 90.271 | 76.269 | -14.002 ns (-15.51%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 242.359 | 210.977 | -31.382 ns (-12.95%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.transientBytes | 5304.000 | 4712.000 | -592.000 B (-11.16%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 242.359 | 210.977 | -31.382 ns (-12.95%) | 0 | smaller |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 244.194 | 118.025 | -126.169 ns (-51.67%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 6299.098 | 5373.829 | -925.269 ns (-14.69%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 1045.459 | 877.563 | -167.896 ns (-16.06%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 26.917 | 21.458 | -5.458 ns (-20.28%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 231.783 | 179.496 | -52.287 ns (-22.56%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1481.175 | 1244.213 | -236.963 ns (-16.00%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 1041.521 | 1102.583 | +61.063 ns (+5.86%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 26.990 | 25.200 | -1.790 ns (-6.63%) | 0 | smaller |
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
| - | - | cpython-3.13/partial | compact.callNs | 12705.281 | 9665.981 | -3039.300 ns (-23.92%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 3207.740 | 2973.915 | -233.825 ns (-7.29%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.dumpNs | 2111.979 | 1868.979 | -243.000 ns (-11.51%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 5856.000 | 5264.000 | -592.000 B (-10.11%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.readNs | 87.129 | 74.387 | -12.742 ns (-14.62%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 323.083 | 237.060 | -86.023 ns (-26.63%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.transientBytes | 5424.000 | 4832.000 | -592.000 B (-10.91%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 323.083 | 237.060 | -86.023 ns (-26.63%) | 0 | smaller |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 208.846 | 136.539 | -72.307 ns (-34.62%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5763.279 | 5052.627 | -710.652 ns (-12.33%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.dumpNs | 1045.813 | 898.125 | -147.688 ns (-14.12%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 25.813 | 23.052 | -2.760 ns (-10.69%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 229.827 | 202.850 | -26.977 ns (-11.74%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 1128.985 | 964.337 | -164.648 ns (-14.58%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 1015.041 | 894.187 | -120.854 ns (-11.91%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 25.302 | 22.765 | -2.537 ns (-10.03%) | 0 | smaller |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 28863.865 | 22314.075 | -6549.790 ns (-22.69%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 3578.260 | 3398.196 | -180.065 ns (-5.03%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1921.208 | 1772.084 | -149.124 ns (-7.76%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 8960.000 | 7520.000 | -1440.000 B (-16.07%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.readNs | 93.244 | 81.179 | -12.066 ns (-12.94%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 386.689 | 308.901 | -77.788 ns (-20.12%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 8552.000 | 7112.000 | -1440.000 B (-16.84%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 386.689 | 308.901 | -77.788 ns (-20.12%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 274.933 | 128.490 | -146.444 ns (-53.27%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4701.879 | 4115.156 | -586.723 ns (-12.48%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 938.541 | 795.792 | -142.750 ns (-15.21%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 27.958 | 24.792 | -3.167 ns (-11.33%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 235.950 | 180.009 | -55.941 ns (-23.71%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1248.321 | 1119.596 | -128.725 ns (-10.31%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 918.437 | 787.625 | -130.813 ns (-14.24%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 27.092 | 22.729 | -4.363 ns (-16.10%) | 0 | smaller |
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
| - | - | cpython-3.13/shallow | compact.callNs | 10711.742 | 8958.996 | -1752.746 ns (-16.36%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 2940.675 | 2868.483 | -72.192 ns (-2.45%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1620.646 | 1397.146 | -223.500 ns (-13.79%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 5632.000 | 5216.000 | -416.000 B (-7.39%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.readNs | 102.734 | 92.588 | -10.146 ns (-9.88%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 186.003 | 196.270 | +10.267 ns (+5.52%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.transientBytes | 5248.000 | 4832.000 | -416.000 B (-7.93%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 186.003 | 196.270 | +10.267 ns (+5.52%) | 0 | larger |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 281.900 | 125.062 | -156.838 ns (-55.64%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 3049.954 | 2740.479 | -309.475 ns (-10.15%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 804.000 | 702.354 | -101.646 ns (-12.64%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 29.792 | 25.109 | -4.682 ns (-15.72%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 218.183 | 192.098 | -26.085 ns (-11.96%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 864.233 | 792.506 | -71.727 ns (-8.30%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 801.563 | 701.209 | -100.354 ns (-12.52%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 30.062 | 26.828 | -3.234 ns (-10.76%) | 0 | smaller |
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
| - | - | cpython-3.13/warmed | compact.callNs | 11830.179 | 9197.081 | -2633.098 ns (-22.26%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 5462.821 | 5153.294 | -309.527 ns (-5.67%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.dumpNs | 2039.750 | 1828.209 | -211.541 ns (-10.37%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 5816.000 | 5400.000 | -416.000 B (-7.15%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.readNs | 101.755 | 87.812 | -13.943 ns (-13.70%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | -99.547 | 391.452 | +490.998 ns (-493.23%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.transientBytes | 5010.000 | 4594.000 | -416.000 B (-8.30%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 0.000 | 391.452 | +391.452 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 194.696 | 82.915 | -111.781 ns (-57.41%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 4395.429 | 3782.773 | -612.656 ns (-13.94%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 853.375 | 702.771 | -150.604 ns (-17.65%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 30.781 | 26.422 | -4.359 ns (-14.16%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 245.131 | 156.575 | -88.556 ns (-36.13%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1970.952 | 1747.633 | -223.319 ns (-11.33%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 838.937 | 705.479 | -133.458 ns (-15.91%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 30.677 | 26.250 | -4.427 ns (-14.43%) | 0 | smaller |
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
| - | - | cpython-3.13/wide | compact.callNs | 14688.787 | 10708.390 | -3980.398 ns (-27.10%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 4443.171 | 4090.923 | -352.248 ns (-7.93%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.dumpNs | 2910.521 | 2642.042 | -268.479 ns (-9.22%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 6320.000 | 5400.000 | -920.000 B (-14.56%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.readNs | 98.698 | 83.880 | -14.818 ns (-15.01%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 86.635 | 128.496 | +41.861 ns (+48.32%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.transientBytes | 5808.000 | 4888.000 | -920.000 B (-15.84%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 86.635 | 128.496 | +41.861 ns (+48.32%) | 0 | larger |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | -138.439 | 110.098 | +248.537 ns (-179.53%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 9112.585 | 7841.652 | -1270.933 ns (-13.95%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1373.792 | 1261.479 | -112.312 ns (-8.18%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 26.379 | 21.630 | -4.749 ns (-18.00%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 215.811 | 202.273 | -13.538 ns (-6.27%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1966.773 | 1750.519 | -216.254 ns (-11.00%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1323.667 | 1146.938 | -176.729 ns (-13.35%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 26.879 | 22.667 | -4.212 ns (-15.67%) | 0 | smaller |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.134 | 3.377 | +0.243 ratio (+7.74%) | 0 | larger |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.134 | 3.377 | +0.243 ratio (+7.74%) | 0 | larger |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.159 | 3.088 | -0.071 ratio (-2.24%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 0.814 | 0.815 | +0.001 ratio (+0.14%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.likeForLike | 0.781 | 0.786 | +0.005 ratio (+0.62%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 2.490 | 2.376 | -0.113 ratio (-4.55%) | 0 | smaller |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.138 | 2.177 | +0.039 ratio (+1.85%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.138 | 2.177 | +0.039 ratio (+1.85%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.189 | 2.164 | -0.025 ratio (-1.15%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 26602.598 | 15222.202 | -11380.396 ns (-42.78%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 15020.798 | 12139.381 | -2881.417 ns (-19.18%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.dumpNs | 8641.333 | 6552.125 | -2089.208 ns (-24.18%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 9396.000 | 7564.000 | -1832.000 B (-19.50%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.readNs | 120.837 | 96.796 | -24.042 ns (-19.90%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | -269.557 | -234.385 | +35.172 ns (-13.05%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 8164.000 | 6332.000 | -1832.000 B (-22.44%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | -105.009 | -69.916 | +35.092 ns (-33.42%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 12425.592 | 11102.250 | -1323.342 ns (-10.65%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 3392.271 | 2581.417 | -810.854 ns (-23.90%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5184.000 | 5184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.readNs | 36.262 | 27.417 | -8.846 ns (-24.39%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2264.000 | 2264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 370.583 | 123.196 | -247.387 ns (-66.76%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 6564.979 | 6543.263 | -21.717 ns (-0.33%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 3228.354 | 2545.208 | -683.146 ns (-21.16%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4744.000 | 4744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 33.767 | 27.667 | -6.100 ns (-18.07%) | 0 | smaller |
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
| - | - | cpython-3.14/nullable | compact.callNs | 18101.698 | 10298.500 | -7803.198 ns (-43.11%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 4844.365 | 3568.542 | -1275.823 ns (-26.34%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.dumpNs | 2435.146 | 1960.042 | -475.104 ns (-19.51%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 6296.000 | 5696.000 | -600.000 B (-9.53%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.readNs | 103.467 | 83.185 | -20.281 ns (-19.60%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 556.920 | 100.587 | -456.332 ns (-81.94%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 5800.000 | 5200.000 | -600.000 B (-10.34%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 556.920 | 100.587 | -456.332 ns (-81.94%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 310.979 | 173.679 | -137.301 ns (-44.15%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 7840.104 | 5253.717 | -2586.387 ns (-32.99%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 1386.104 | 915.791 | -470.312 ns (-33.93%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 38.050 | 22.846 | -15.204 ns (-39.96%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 356.925 | 184.760 | -172.165 ns (-48.24%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1924.825 | 1260.885 | -663.940 ns (-34.49%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 1403.063 | 1138.604 | -264.459 ns (-18.85%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 37.535 | 33.750 | -3.785 ns (-10.08%) | 0 | smaller |
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
| - | - | cpython-3.14/partial | compact.callNs | 13892.875 | 10168.341 | -3724.534 ns (-26.81%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 3238.250 | 3113.950 | -124.300 ns (-3.84%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.dumpNs | 2127.188 | 1852.000 | -275.188 ns (-12.94%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 6320.000 | 5720.000 | -600.000 B (-9.49%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.readNs | 90.888 | 78.540 | -12.348 ns (-13.59%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 296.376 | 294.580 | -1.795 ns (-0.61%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.transientBytes | 5856.000 | 5256.000 | -600.000 B (-10.25%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 296.376 | 294.580 | -1.795 ns (-0.61%) | 0 | within noise |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 346.745 | 84.077 | -262.668 ns (-75.75%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 5943.275 | 5099.069 | -844.206 ns (-14.20%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 1142.937 | 1085.834 | -57.104 ns (-5.00%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 30.971 | 24.935 | -6.035 ns (-19.49%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 254.527 | 196.935 | -57.592 ns (-22.63%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 1204.723 | 987.065 | -217.658 ns (-18.07%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 1118.958 | 950.729 | -168.229 ns (-15.03%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 31.790 | 27.067 | -4.723 ns (-14.86%) | 0 | smaller |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 29780.252 | 23613.098 | -6167.155 ns (-20.71%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 3659.227 | 3412.652 | -246.575 ns (-6.74%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1917.604 | 1662.667 | -254.938 ns (-13.29%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 9176.000 | 7704.000 | -1472.000 B (-16.04%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.readNs | 96.372 | 79.774 | -16.598 ns (-17.22%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 412.436 | 292.350 | -120.086 ns (-29.12%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 8736.000 | 7264.000 | -1472.000 B (-16.85%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 412.436 | 292.350 | -120.086 ns (-29.12%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 281.438 | 150.219 | -131.219 ns (-46.62%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4532.896 | 4066.240 | -466.656 ns (-10.29%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 975.584 | 854.604 | -120.980 ns (-12.40%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 30.045 | 25.914 | -4.131 ns (-13.75%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 209.410 | 186.102 | -23.308 ns (-11.13%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1242.277 | 1107.356 | -134.921 ns (-10.86%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 951.146 | 838.646 | -112.501 ns (-11.83%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 30.018 | 26.753 | -3.265 ns (-10.88%) | 0 | smaller |
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
| - | - | cpython-3.14/shallow | compact.callNs | 11737.550 | 8969.521 | -2768.029 ns (-23.58%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 3513.033 | 3043.062 | -469.971 ns (-13.38%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1743.104 | 1492.916 | -250.188 ns (-14.35%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 6048.000 | 5624.000 | -424.000 B (-7.01%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.readNs | 109.797 | 92.547 | -17.250 ns (-15.71%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 510.573 | 306.412 | -204.161 ns (-39.99%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 5632.000 | 5208.000 | -424.000 B (-7.53%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 510.573 | 306.412 | -204.161 ns (-39.99%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 505.237 | 223.750 | -281.488 ns (-55.71%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 3212.804 | 2760.458 | -452.346 ns (-14.08%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 865.187 | 741.313 | -123.875 ns (-14.32%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 31.974 | 28.953 | -3.021 ns (-9.45%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 191.435 | 187.842 | -3.594 ns (-1.88%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 1001.794 | 824.096 | -177.698 ns (-17.74%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 904.916 | 754.458 | -150.458 ns (-16.63%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 32.886 | 28.922 | -3.964 ns (-12.05%) | 0 | smaller |
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
| - | - | cpython-3.14/warmed | compact.callNs | 11840.606 | 8962.490 | -2878.117 ns (-24.31%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 6115.727 | 5915.885 | -199.842 ns (-3.27%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 2201.770 | 2094.229 | -107.542 ns (-4.88%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 6232.000 | 5808.000 | -424.000 B (-6.80%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.readNs | 117.271 | 107.630 | -9.641 ns (-8.22%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 374.343 | 661.790 | +287.447 ns (+76.79%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.transientBytes | 5394.000 | 4970.000 | -424.000 B (-7.86%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 374.343 | 661.790 | +287.447 ns (+76.79%) | 0 | larger |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 59.194 | 375.556 | +316.363 ns (+534.45%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 4651.035 | 3983.402 | -667.633 ns (-14.35%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 953.188 | 766.208 | -186.980 ns (-19.62%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 34.422 | 30.526 | -3.896 ns (-11.32%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 217.869 | 176.504 | -41.365 ns (-18.99%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 2045.298 | 1836.517 | -208.781 ns (-10.21%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 871.084 | 1077.000 | +205.916 ns (+23.64%) | 0 | larger |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 31.937 | 33.865 | +1.927 ns (+6.03%) | 0 | larger |
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
| - | - | cpython-3.14/wide | compact.callNs | 16279.285 | 10975.812 | -5303.473 ns (-32.58%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 4543.027 | 4338.250 | -204.777 ns (-4.51%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.dumpNs | 2845.917 | 2609.854 | -236.063 ns (-8.29%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 6736.000 | 5808.000 | -928.000 B (-13.78%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.readNs | 97.708 | 90.297 | -7.411 ns (-7.59%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 24.472 | 354.789 | +330.317 ns (+1349.75%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.transientBytes | 6192.000 | 5264.000 | -928.000 B (-14.99%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 24.472 | 354.789 | +330.317 ns (+1349.75%) | 0 | larger |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 175.358 | -218.048 | -393.406 ns (-224.34%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 8827.829 | 8057.402 | -770.427 ns (-8.73%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1458.396 | 1229.583 | -228.813 ns (-15.69%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 30.237 | 24.273 | -5.964 ns (-19.72%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 253.979 | 252.198 | -1.781 ns (-0.70%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 2047.104 | 1739.865 | -307.240 ns (-15.01%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1397.500 | 1226.188 | -171.313 ns (-12.26%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 29.974 | 24.595 | -5.379 ns (-17.95%) | 0 | smaller |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 4.296 | 3.235 | -1.061 us/event (-24.70%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 4.859 | 3.994 | -0.865 us/event (-17.80%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.242 | 0.241 | -0.001 ratio (-0.34%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.027 | 0.021 | -0.006 ratio (-22.61%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.080 | 0.066 | -0.015 ratio (-18.05%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.006 | 0.004 | -0.001 ratio (-24.25%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.173 | 0.157 | -0.015 ratio (-8.81%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | observed.p50 | 615.583 | 466.042 | -149.541 us (-24.29%) | 0 | faster |
| - | - | Safe logging alone, at INFO | observed.p95 | 663.875 | 488.541 | -175.334 us (-26.41%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 120.292 | 90.583 | -29.709 us (-24.70%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 136.042 | 111.833 | -24.209 us (-17.80%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.241 | 0.242 | +0.001 ratio (+0.60%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.293 | 0.299 | +0.007 ratio (+2.26%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | plain.p50 | 496.500 | 375.167 | -121.333 us (-24.44%) | 0 | faster |
| - | - | Safe logging alone, at INFO | plain.p95 | 534.917 | 400.042 | -134.875 us (-25.21%) | 0 | faster |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.240 | 0.242 | +0.002 ratio (+0.99%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.241 | 0.221 | -0.020 ratio (-8.24%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.717 | 2.317 | -0.400 us/event (-14.73%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 3.667 | 3.153 | -0.513 us/event (-14.00%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.173 | 0.173 | +0.001 ratio (+0.44%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.017 | 0.015 | -0.002 ratio (-13.43%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.053 | 0.047 | -0.006 ratio (-10.60%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.004 | 0.003 | -0.001 ratio (-14.45%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.119 | 0.113 | -0.006 ratio (-4.85%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | observed.p50 | 517.167 | 439.083 | -78.084 us (-15.10%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | observed.p95 | 562.625 | 461.916 | -100.709 us (-17.90%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 76.083 | 64.875 | -11.208 us (-14.73%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 102.667 | 88.292 | -14.375 us (-14.00%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.172 | 0.174 | +0.002 ratio (+0.90%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.232 | 0.237 | +0.005 ratio (+2.02%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | plain.p50 | 440.500 | 373.958 | -66.542 us (-15.11%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | plain.p95 | 479.500 | 394.000 | -85.500 us (-17.83%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.174 | 0.174 | +0.000 ratio (+0.06%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.173 | 0.172 | -0.001 ratio (-0.57%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 4.586 | 3.938 | -0.649 us/event (-14.15%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 5.567 | 4.853 | -0.714 us/event (-12.83%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.291 | 0.293 | +0.003 ratio (+0.93%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.029 | 0.025 | -0.004 ratio (-12.85%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.089 | 0.080 | -0.009 ratio (-10.03%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.006 | 0.005 | -0.001 ratio (-13.87%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.200 | 0.191 | -0.009 ratio (-4.31%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | observed.p50 | 570.834 | 486.209 | -84.625 us (-14.82%) | 0 | faster |
| - | - | fan-out of three, tracing every root | observed.p95 | 620.875 | 512.417 | -108.458 us (-17.47%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 128.417 | 110.250 | -18.167 us (-14.15%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 155.875 | 135.875 | -20.000 us (-12.83%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.292 | 0.295 | +0.003 ratio (+1.03%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.351 | 0.364 | +0.013 ratio (+3.63%) | 0 | larger |
| - | - | fan-out of three, tracing every root | plain.p50 | 441.792 | 375.791 | -66.001 us (-14.94%) | 0 | faster |
| - | - | fan-out of three, tracing every root | plain.p95 | 481.125 | 397.042 | -84.083 us (-17.48%) | 0 | faster |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.292 | 0.294 | +0.002 ratio (+0.60%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.290 | 0.291 | +0.000 ratio (+0.04%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 5.051 | 3.757 | -1.293 us/event (-25.60%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 6.737 | 4.885 | -1.851 us/event (-27.48%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.284 | 0.280 | -0.004 ratio (-1.33%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.031 | 0.024 | -0.007 ratio (-23.52%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.094 | 0.076 | -0.018 ratio (-18.98%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.007 | 0.005 | -0.002 ratio (-25.16%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.203 | 0.183 | -0.020 ratio (-9.76%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 652.167 | 481.125 | -171.042 us (-26.23%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 833.500 | 512.375 | -321.125 us (-38.53%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 141.417 | 105.208 | -36.209 us (-25.60%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 188.625 | 136.792 | -51.833 us (-27.48%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.277 | 0.281 | +0.004 ratio (+1.30%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.340 | 0.365 | +0.025 ratio (+7.35%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 498.292 | 375.708 | -122.584 us (-24.60%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 651.750 | 393.917 | -257.833 us (-39.56%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.309 | 0.281 | -0.028 ratio (-9.14%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.279 | 0.301 | +0.022 ratio (+7.84%) | 0 | larger |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.658 | 1.469 | -0.189 us/event (-11.40%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 2.543 | 2.216 | -0.327 us/event (-12.87%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.110 | 0.110 | +0.000 ratio (+0.32%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.010 | 0.009 | -0.001 ratio (-10.40%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.033 | 0.030 | -0.003 ratio (-8.21%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-11.18%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.074 | 0.072 | -0.003 ratio (-3.76%) | 0 | smaller |
| - | - | one Handler that keeps nothing | observed.p50 | 471.084 | 415.500 | -55.584 us (-11.80%) | 0 | faster |
| - | - | one Handler that keeps nothing | observed.p95 | 506.000 | 436.959 | -69.041 us (-13.64%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 46.416 | 41.125 | -5.291 us (-11.40%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 71.208 | 62.042 | -9.166 us (-12.87%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.109 | 0.111 | +0.001 ratio (+1.00%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.168 | 0.166 | -0.002 ratio (-1.35%) | 0 | within noise |
| - | - | one Handler that keeps nothing | plain.p50 | 423.708 | 374.208 | -49.500 us (-11.68%) | 0 | faster |
| - | - | one Handler that keeps nothing | plain.p95 | 453.125 | 393.584 | -59.541 us (-13.14%) | 0 | faster |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.112 | 0.110 | -0.001 ratio (-1.31%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.117 | 0.110 | -0.006 ratio (-5.56%) | 0 | smaller |
| - | - | workload | events | 28.000 | 28.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | workload | statements | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |

## snapshot-delivery

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 426.537 | 468.576 | +42.039 KiB (+9.86%) | 3 | larger |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 298.957 | 315.021 | +16.063 KiB (+5.37%) | 3 | larger |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.583 | 0.568 | -0.016 ms (-2.67%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 1.008 | 0.978 | -0.030 ms (-2.99%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 5.214 | 5.678 | +0.464 ms (+8.90%) | 9 | slower |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 37042.758 | 35397.446 | -1645.312 roots/s (-4.44%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 6.262 | 6.376 | +0.114 ms (+1.82%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 31324.434 | 31691.327 | +366.892 roots/s (+1.17%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 8.114 | 8.444 | +0.330 ms (+4.06%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 24294.695 | 23280.177 | -1014.518 roots/s (-4.18%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 251.070 | 281.954 | +30.884 KiB (+12.30%) | 6 | larger |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.150 | 42.740 | +0.590 KiB (+1.40%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 94.190 | 104.854 | +10.663 KiB (+11.32%) | 6 | larger |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 16.165 | 16.886 | +0.721 KiB (+4.46%) | 6 | larger |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1324.136 | 1324.464 | +0.328 KiB (+0.02%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.957 | 521.957 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.841 | 0.778 | -0.063 ms (-7.47%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.268 | 1.215 | -0.053 ms (-4.15%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 8.562 | 8.732 | +0.170 ms (+1.98%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23301.762 | 23082.140 | -219.622 roots/s (-0.94%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 9.401 | 9.587 | +0.186 ms (+1.98%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 20916.400 | 20600.150 | -316.249 roots/s (-1.51%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 12.906 | 12.649 | -0.257 ms (-1.99%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 15932.394 | 14924.909 | -1007.486 roots/s (-6.32%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 730.147 | 730.593 | +0.445 KiB (+0.06%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 34.997 | 35.087 | +0.090 KiB (+0.26%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 206.714 | 207.159 | +0.445 KiB (+0.22%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.772 | 3.772 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1745.775 | 1745.881 | +0.105 KiB (+0.01%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.726 | 869.626 | -0.100 KiB (-0.01%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.861 | 0.804 | -0.057 ms (-6.63%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.453 | 2.371 | -0.083 ms (-3.37%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 28.371 | 23.718 | -4.653 ms (-16.40%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 5116.136 | 8421.526 | +3305.389 roots/s (+64.61%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 24.732 | 24.473 | -0.259 ms (-1.05%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8202.296 | 8063.798 | -138.498 roots/s (-1.69%) | 9 | within noise |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 32.931 | 27.233 | -5.698 ms (-17.30%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6391.444 | 7234.222 | +842.778 roots/s (+13.19%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1164.876 | 1164.776 | -0.100 KiB (-0.01%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 50.735 | 49.731 | -1.004 KiB (-1.98%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 314.293 | 314.157 | -0.136 KiB (-0.04%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 17.063 | 16.848 | -0.216 KiB (-1.26%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1324.800 | 1324.800 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 544.988 | 544.988 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.984 | 0.878 | -0.105 ms (-10.71%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.866 | 1.766 | -0.100 ms (-5.34%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 13.912 | 16.296 | +2.384 ms (+17.13%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 14368.203 | 12320.329 | -2047.874 roots/s (-14.25%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 14.917 | 16.189 | +1.272 ms (+8.52%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12940.761 | 12236.376 | -704.384 roots/s (-5.44%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 17.626 | 19.468 | +1.842 ms (+10.45%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 11059.322 | 10338.567 | -720.755 roots/s (-6.52%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1159.917 | 1160.909 | +0.992 KiB (+0.09%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 44.810 | 44.899 | +0.090 KiB (+0.20%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 320.151 | 321.144 | +0.992 KiB (+0.31%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.093 | 4.093 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 310.761 | 320.313 | +9.553 KiB (+3.07%) | 3 | larger |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.980 | 172.379 | +0.398 KiB (+0.23%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.499 | 0.472 | -0.027 ms (-5.36%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.865 | 0.708 | -0.158 ms (-18.23%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 4.594 | 5.213 | +0.619 ms (+13.47%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 43727.001 | 38074.388 | -5652.614 roots/s (-12.93%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 5.988 | 5.667 | -0.321 ms (-5.36%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 31714.569 | 35339.073 | +3624.504 roots/s (+11.43%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 7.341 | 7.875 | +0.534 ms (+7.28%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 25166.993 | 25572.861 | +405.868 roots/s (+1.61%) | 9 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 197.614 | 197.614 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 28.290 | 29.038 | +0.748 KiB (+2.64%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 70.444 | 70.830 | +0.386 KiB (+0.55%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 10.010 | 5.556 | -4.454 KiB (-44.50%) | 6 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.635 | 5.997 | -0.638 us/projection (-9.62%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 152139.720 | 167703.887 | +15564.167 projections/s (+10.23%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.527 | 43.527 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 37.434 | 38.371 | +0.938 KiB (+2.50%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 579.062 | 579.062 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 117.375 | 117.375 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.363 | 7.104 | -0.259 us/projection (-3.52%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 137191.837 | 141189.657 | +3997.820 projections/s (+2.91%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 48.465 | 48.465 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 60.448 | 52.425 | -8.023 KiB (-13.27%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 594.062 | 594.062 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 181.375 | 181.375 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 9.053 | 8.398 | -0.655 ms (-7.23%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 22594.933 | 23560.134 | +965.201 roots/s (+4.27%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.886 | 9.400 | -0.486 ms (-4.92%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20052.220 | 21182.422 | +1130.202 roots/s (+5.64%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 17.468 | 15.457 | -2.012 ms (-11.52%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 11362.991 | 12723.759 | +1360.768 roots/s (+11.98%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 17.727 | 16.009 | -1.717 ms (-9.69%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10877.447 | 12217.471 | +1340.024 roots/s (+12.32%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 33.479 | 31.716 | -1.763 us/root (-5.27%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 108.699 | 109.652 | +0.953 KiB (+0.88%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.836 | 50.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 33.026 | 32.242 | -0.784 us/root (-2.37%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 108.699 | 109.613 | +0.914 KiB (+0.84%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.836 | 50.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 55.221 | 46.020 | -9.202 us/root (-16.66%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 154.324 | 156.906 | +2.582 KiB (+1.67%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.961 | 87.961 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 54.467 | 47.258 | -7.210 us/root (-13.24%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 153.719 | 156.867 | +3.148 KiB (+2.05%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.961 | 87.961 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 90.431 | 65.780 | -24.651 us/root (-27.26%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 222.836 | 228.453 | +5.617 KiB (+2.52%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.461 | 137.461 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 95.168 | 66.091 | -29.077 us/root (-30.55%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 220.781 | 227.359 | +6.578 KiB (+2.98%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.461 | 137.461 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 23.328 | 23.462 | +0.134 us/root (+0.57%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 67.207 | 67.371 | +0.164 KiB (+0.24%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.086 | 24.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 23.785 | 23.598 | -0.188 us/root (-0.79%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 72.957 | 73.082 | +0.125 KiB (+0.17%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.086 | 24.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 166.695 | 145.263 | -21.432 us/root (-12.86%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 636.223 | 634.883 | -1.340 KiB (-0.21%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.086 | 428.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 159.789 | 147.342 | -12.447 us/root (-7.79%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 633.832 | 634.684 | +0.852 KiB (+0.13%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.086 | 428.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 59.622 | 55.022 | -4.600 us/root (-7.72%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 204.992 | 205.566 | +0.574 KiB (+0.28%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.086 | 125.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 58.559 | 57.133 | -1.426 us/root (-2.43%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 203.543 | 204.363 | +0.820 KiB (+0.40%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.086 | 125.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 50.396 | 45.361 | -5.035 us/root (-9.99%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 138.954 | 139.337 | +0.383 KiB (+0.28%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.930 | 35.930 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 46.914 | 43.863 | -3.051 us/root (-6.50%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 138.954 | 139.298 | +0.344 KiB (+0.25%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.930 | 35.930 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 59.332 | 51.397 | -7.935 us/root (-13.37%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 220.514 | 220.287 | -0.227 KiB (-0.10%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.711 | 136.711 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 58.617 | 51.958 | -6.659 us/root (-11.36%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 223.922 | 223.852 | -0.070 KiB (-0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.711 | 136.711 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 156.977 | 131.534 | -25.443 us/root (-16.21%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 766.938 | 762.844 | -4.094 KiB (-0.53%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.211 | 480.211 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 159.293 | 132.538 | -26.755 us/root (-16.80%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 770.367 | 766.422 | -3.945 KiB (-0.51%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.211 | 480.211 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 120.500 | 99.750 | -20.750 us (-17.22%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 22.546 | 22.804 | +0.258 KiB (+1.14%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.554 | 14.796 | +0.242 KiB (+1.66%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 122.292 | 102.708 | -19.584 us (-16.01%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 23.014 | 22.764 | -0.250 KiB (-1.09%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 15.334 | 14.943 | -0.391 KiB (-2.55%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 138.333 | 100.625 | -37.708 us (-27.26%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 22.546 | 22.804 | +0.258 KiB (+1.14%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.554 | 14.796 | +0.242 KiB (+1.66%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 156.250 | 100.166 | -56.084 us (-35.89%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 23.014 | 22.764 | -0.250 KiB (-1.09%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 15.334 | 14.943 | -0.391 KiB (-2.55%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 169.083 | 99.125 | -69.958 us (-41.37%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 22.547 | 22.805 | +0.258 KiB (+1.14%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.555 | 14.797 | +0.242 KiB (+1.66%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 132.916 | 103.875 | -29.041 us (-21.85%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 23.015 | 22.765 | -0.250 KiB (-1.09%) | 3 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 15.335 | 14.944 | -0.391 KiB (-2.55%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 398.742 | 426.749 | +28.007 KiB (+7.02%) | 3 | larger |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 304.437 | 316.630 | +12.193 KiB (+4.01%) | 3 | larger |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.607 | 0.560 | -0.048 ms (-7.84%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 1.007 | 0.972 | -0.035 ms (-3.47%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 5.161 | 5.729 | +0.568 ms (+11.01%) | 9 | slower |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 37734.959 | 35032.656 | -2702.303 roots/s (-7.16%) | 9 | slower |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 6.406 | 6.241 | -0.165 ms (-2.58%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 30923.252 | 31237.188 | +313.936 roots/s (+1.02%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 8.516 | 8.557 | +0.041 ms (+0.48%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 22713.291 | 23559.324 | +846.032 roots/s (+3.72%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 238.784 | 285.334 | +46.550 KiB (+19.49%) | 6 | larger |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.356 | 45.211 | +2.854 KiB (+6.74%) | 6 | larger |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 86.590 | 98.086 | +11.496 KiB (+13.28%) | 6 | larger |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 15.571 | 16.024 | +0.453 KiB (+2.91%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1259.475 | 1259.803 | +0.328 KiB (+0.03%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.363 | 531.363 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.713 | 0.743 | +0.031 ms (+4.31%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.184 | 1.181 | -0.002 ms (-0.19%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 8.689 | 8.959 | +0.269 ms (+3.10%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23019.595 | 22243.230 | -776.366 roots/s (-3.37%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 9.467 | 9.733 | +0.266 ms (+2.81%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 20547.507 | 20382.945 | -164.562 roots/s (-0.80%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 12.101 | 12.444 | +0.343 ms (+2.84%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 16343.485 | 16232.997 | -110.488 roots/s (-0.68%) | 9 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 693.096 | 693.541 | +0.445 KiB (+0.06%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 37.148 | 37.324 | +0.176 KiB (+0.47%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 198.666 | 199.111 | +0.445 KiB (+0.22%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.897 | 3.897 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1799.175 | 1799.294 | +0.119 KiB (+0.01%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.741 | 883.694 | -0.047 KiB (-0.01%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.957 | 0.862 | -0.095 ms (-9.93%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.658 | 2.415 | -0.243 ms (-9.16%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 25.821 | 23.561 | -2.260 ms (-8.75%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7481.390 | 8514.443 | +1033.053 roots/s (+13.81%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 28.592 | 24.452 | -4.140 ms (-14.48%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 7268.840 | 8209.787 | +940.948 roots/s (+12.94%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 32.988 | 27.322 | -5.666 ms (-17.17%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 5950.005 | 7227.446 | +1277.441 roots/s (+21.47%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1199.475 | 1199.475 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 52.239 | 52.401 | +0.162 KiB (+0.31%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 323.182 | 322.774 | -0.407 KiB (-0.13%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 15.179 | 16.836 | +1.657 KiB (+10.92%) | 6 | larger |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1393.275 | 1393.275 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.398 | 554.398 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.980 | 0.916 | -0.065 ms (-6.62%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.940 | 1.821 | -0.119 ms (-6.13%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 14.108 | 16.606 | +2.498 ms (+17.70%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 12953.438 | 12122.314 | -831.123 roots/s (-6.42%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 20.988 | 16.698 | -4.290 ms (-20.44%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11205.319 | 11925.644 | +720.325 roots/s (+6.43%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 22.796 | 19.624 | -3.173 ms (-13.92%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 7230.211 | 10061.606 | +2831.395 roots/s (+39.16%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1166.908 | 1167.979 | +1.070 KiB (+0.09%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 47.309 | 47.484 | +0.176 KiB (+0.37%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 314.291 | 315.361 | +1.070 KiB (+0.34%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.218 | 4.218 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 298.886 | 298.837 | -0.049 KiB (-0.02%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 175.188 | 175.617 | +0.430 KiB (+0.25%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.517 | 0.484 | -0.033 ms (-6.40%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.887 | 0.742 | -0.145 ms (-16.34%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 6.712 | 5.259 | -1.453 ms (-21.65%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 32432.436 | 37953.062 | +5520.626 roots/s (+17.02%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 6.818 | 5.928 | -0.890 ms (-13.05%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 30927.236 | 33919.628 | +2992.393 roots/s (+9.68%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 9.659 | 8.191 | -1.468 ms (-15.20%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 20596.349 | 24394.334 | +3797.985 roots/s (+18.44%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 205.014 | 205.014 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 30.565 | 31.138 | +0.572 KiB (+1.87%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 69.479 | 68.561 | -0.918 KiB (-1.32%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 7.343 | 8.206 | +0.863 KiB (+11.76%) | 6 | larger |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.229 | 5.854 | -0.375 us/projection (-6.02%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 161599.444 | 172448.608 | +10849.164 projections/s (+6.71%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.777 | 45.777 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 41.361 | 42.299 | +0.938 KiB (+2.27%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 604.438 | 604.438 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 128.000 | 128.000 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.105 | 7.508 | +0.403 us/projection (+5.67%) | 9 | slower |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 142883.605 | 138992.051 | -3891.554 projections/s (-2.72%) | 9 | within noise |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 50.777 | 50.777 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 65.587 | 57.438 | -8.148 KiB (-12.42%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 620.438 | 620.438 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 192.000 | 192.000 | +0.000 B/projection (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 10.737 | 9.165 | -1.573 ms (-14.65%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18664.914 | 22019.964 | +3355.050 roots/s (+17.98%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 12.119 | 10.316 | -1.802 ms (-14.87%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 16592.633 | 20707.149 | +4114.516 roots/s (+24.80%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 17.319 | 15.757 | -1.562 ms (-9.02%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10544.537 | 12466.691 | +1922.153 roots/s (+18.23%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 18.911 | 16.468 | -2.443 ms (-12.92%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10101.945 | 12318.337 | +2216.392 roots/s (+21.94%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 31.577 | 31.342 | -0.234 us/root (-0.74%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 106.210 | 107.177 | +0.967 KiB (+0.91%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.094 | 51.094 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 31.960 | 32.346 | +0.387 us/root (+1.21%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 106.104 | 107.138 | +1.033 KiB (+0.97%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.094 | 51.094 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 54.811 | 47.318 | -7.493 us/root (-13.67%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 155.085 | 157.374 | +2.289 KiB (+1.48%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.219 | 88.219 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 57.217 | 47.816 | -9.401 us/root (-16.43%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 153.554 | 156.218 | +2.664 KiB (+1.73%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.219 | 88.219 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 93.339 | 66.991 | -26.348 us/root (-28.23%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 225.687 | 230.897 | +5.211 KiB (+2.31%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.719 | 137.719 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 92.501 | 67.174 | -25.327 us/root (-27.38%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 223.640 | 230.257 | +6.617 KiB (+2.96%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.719 | 137.719 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 23.755 | 23.326 | -0.430 us/root (-1.81%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 65.831 | 66.044 | +0.213 KiB (+0.32%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.344 | 24.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 23.191 | 23.878 | +0.686 us/root (+2.96%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 71.503 | 71.755 | +0.252 KiB (+0.35%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.344 | 24.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 160.184 | 152.033 | -8.151 us/root (-5.09%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 640.226 | 639.118 | -1.107 KiB (-0.17%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.344 | 428.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 159.904 | 166.337 | +6.434 us/root (+4.02%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 637.882 | 638.907 | +1.025 KiB (+0.16%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.344 | 428.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 55.896 | 55.171 | -0.725 us/root (-1.30%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 208.030 | 208.481 | +0.451 KiB (+0.22%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.344 | 125.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 58.379 | 55.934 | -2.445 us/root (-4.19%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 206.784 | 207.653 | +0.869 KiB (+0.42%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.344 | 125.344 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 48.012 | 44.904 | -3.108 us/root (-6.47%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 136.445 | 137.064 | +0.619 KiB (+0.45%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.188 | 36.188 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 46.010 | 44.868 | -1.142 us/root (-2.48%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 136.367 | 137.025 | +0.658 KiB (+0.48%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.188 | 36.188 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 58.874 | 52.633 | -6.241 us/root (-10.60%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 223.864 | 223.509 | -0.355 KiB (-0.16%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.969 | 136.969 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 57.958 | 53.063 | -4.896 us/root (-8.45%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 227.163 | 227.087 | -0.076 KiB (-0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.969 | 136.969 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 160.504 | 140.238 | -20.266 us/root (-12.63%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 770.265 | 766.399 | -3.865 KiB (-0.50%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.469 | 480.469 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 161.281 | 138.883 | -22.398 us/root (-13.89%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 773.616 | 769.978 | -3.639 KiB (-0.47%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.469 | 480.469 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 125.125 | 105.208 | -19.917 us (-15.92%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 23.571 | 23.821 | +0.250 KiB (+1.06%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 15.938 | 16.188 | +0.250 KiB (+1.57%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 119.458 | 108.875 | -10.583 us (-8.86%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 24.398 | 23.977 | -0.422 KiB (-1.73%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 16.750 | 16.344 | -0.406 KiB (-2.43%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 118.166 | 107.167 | -10.999 us (-9.31%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 23.571 | 23.821 | +0.250 KiB (+1.06%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 15.938 | 16.188 | +0.250 KiB (+1.57%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 114.792 | 106.500 | -8.292 us (-7.22%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 24.398 | 23.977 | -0.422 KiB (-1.73%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 16.750 | 16.344 | -0.406 KiB (-2.43%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 118.084 | 104.917 | -13.167 us (-11.15%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 23.572 | 23.822 | +0.250 KiB (+1.06%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 15.939 | 16.189 | +0.250 KiB (+1.57%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 114.792 | 106.292 | -8.500 us (-7.40%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 24.399 | 23.978 | -0.422 KiB (-1.73%) | 3 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 16.751 | 16.345 | -0.406 KiB (-2.43%) | 3 | within noise |

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
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 238.583 | 198.708 | -39.875 us/row (-16.71%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 4226.000 | 3536.000 | -690.000 B/row (-16.33%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 16122.000 | 14602.000 | -1520.000 B/row (-9.43%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 33.000 | 0.000 | -33.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 244.791 | 201.791 | -43.000 us/row (-17.57%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 4226.000 | 3586.000 | -640.000 B/row (-15.14%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 16122.000 | 14602.000 | -1520.000 B/row (-9.43%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 281.708 | 248.208 | -33.500 us/row (-11.89%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 4226.000 | 3636.000 | -590.000 B/row (-13.96%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 16002.000 | 14602.000 | -1400.000 B/row (-8.75%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 15.000 | 0.000 | -15.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 291.167 | 253.875 | -37.292 us/row (-12.81%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 4176.000 | 3586.000 | -590.000 B/row (-14.13%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 16002.000 | 14602.000 | -1400.000 B/row (-8.75%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 310.625 | 289.000 | -21.625 us/row (-6.96%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 5856.000 | 4326.000 | -1530.000 B/row (-26.13%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 17802.000 | 15442.000 | -2360.000 B/row (-13.26%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 105.000 | 0.000 | -105.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 333.458 | 279.708 | -53.750 us/row (-16.12%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 5806.000 | 4426.000 | -1380.000 B/row (-23.77%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 17802.000 | 15442.000 | -2360.000 B/row (-13.26%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 650.541 | 650.459 | -0.082 us/row (-0.01%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 12626.000 | 7836.000 | -4790.000 B/row (-37.94%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 31483.000 | 25739.000 | -5744.000 B/row (-18.24%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 393.000 | 0.000 | -393.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 697.833 | 598.000 | -99.833 us/row (-14.31%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 12576.000 | 7836.000 | -4740.000 B/row (-37.69%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 33140.000 | 23892.000 | -9248.000 B/row (-27.91%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 328.166 | 274.416 | -53.750 us/row (-16.38%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 6620.000 | 5596.000 | -1024.000 B/row (-15.47%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 17612.000 | 15866.000 | -1746.000 B/row (-9.91%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 332.375 | 251.166 | -81.209 us/row (-24.43%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5642.000 | 5542.000 | -100.000 B/row (-1.77%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16656.000 | 15816.000 | -840.000 B/row (-5.04%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 343.042 | 270.375 | -72.667 us/row (-21.18%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 6570.000 | 5796.000 | -774.000 B/row (-11.78%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 18709.000 | 15026.000 | -3683.000 B/row (-19.69%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 349.125 | 255.208 | -93.917 us/row (-26.90%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5592.000 | 5542.000 | -50.000 B/row (-0.89%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 17703.000 | 14922.000 | -2781.000 B/row (-15.71%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 205.291 | 161.458 | -43.833 us/row (-21.35%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 3162.000 | 2472.000 | -690.000 B/row (-21.82%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 16338.000 | 14690.000 | -1648.000 B/row (-10.09%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 208.500 | 160.500 | -48.000 us/row (-23.02%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 3112.000 | 2422.000 | -690.000 B/row (-22.17%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 16338.000 | 14690.000 | -1648.000 B/row (-10.09%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 30.000 | 0.000 | -30.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 253.125 | 202.709 | -50.416 us/row (-19.92%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 4336.000 | 3144.000 | -1192.000 B/row (-27.49%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 18730.000 | 15426.000 | -3304.000 B/row (-17.64%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 61.000 | 0.000 | -61.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 260.333 | 202.208 | -58.125 us/row (-22.33%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 4336.000 | 3144.000 | -1192.000 B/row (-27.49%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 18730.000 | 15426.000 | -3304.000 B/row (-17.64%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 140.000 | 0.000 | -140.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 330.584 | 251.875 | -78.709 us/row (-23.81%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 6018.000 | 4040.000 | -1978.000 B/row (-32.87%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 22682.000 | 16746.000 | -5936.000 B/row (-26.17%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 191.000 | 0.000 | -191.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 341.667 | 257.584 | -84.083 us/row (-24.61%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 6018.000 | 4090.000 | -1928.000 B/row (-32.04%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 22682.000 | 16746.000 | -5936.000 B/row (-26.17%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 166.542 | 137.375 | -29.167 us/row (-17.51%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 2208.000 | 2018.000 | -190.000 B/row (-8.61%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 15314.000 | 14186.000 | -1128.000 B/row (-7.37%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 177.750 | 135.709 | -42.041 us/row (-23.65%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 2258.000 | 1968.000 | -290.000 B/row (-12.84%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 15314.000 | 14186.000 | -1128.000 B/row (-7.37%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 561.209 | 497.083 | -64.126 us/row (-11.43%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 15816.000 | 9482.000 | -6334.000 B/row (-40.05%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 38074.000 | 27242.000 | -10832.000 B/row (-28.45%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 166.000 | 0.000 | -166.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 588.166 | 500.541 | -87.625 us/row (-14.90%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 15816.000 | 9482.000 | -6334.000 B/row (-40.05%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 38637.000 | 27421.000 | -11216.000 B/row (-29.03%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 277.167 | 229.750 | -47.417 us/row (-17.11%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 5640.000 | 3864.000 | -1776.000 B/row (-31.49%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 18866.000 | 16082.000 | -2784.000 B/row (-14.76%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 46.000 | 0.000 | -46.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 291.042 | 232.416 | -58.626 us/row (-20.14%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 5640.000 | 3864.000 | -1776.000 B/row (-31.49%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 18866.000 | 16082.000 | -2784.000 B/row (-14.76%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 235.875 | 207.416 | -28.459 us/row (-12.07%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 3062.000 | 2472.000 | -590.000 B/row (-19.27%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 16218.000 | 14690.000 | -1528.000 B/row (-9.42%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 7.000 | 0.000 | -7.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 239.917 | 207.125 | -32.792 us/row (-13.67%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 3112.000 | 2522.000 | -590.000 B/row (-18.96%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 16218.000 | 14690.000 | -1528.000 B/row (-9.42%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 264.959 | 251.417 | -13.542 us/row (-5.11%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 4742.000 | 3362.000 | -1380.000 B/row (-29.10%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 18018.000 | 15530.000 | -2488.000 B/row (-13.81%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 52.000 | 0.000 | -52.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 273.209 | 258.416 | -14.793 us/row (-5.41%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 4792.000 | 3312.000 | -1480.000 B/row (-30.88%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 18018.000 | 15530.000 | -2488.000 B/row (-13.81%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 592.167 | 617.583 | +25.416 us/row (+4.29%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 11512.000 | 6722.000 | -4790.000 B/row (-41.61%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 29130.000 | 23321.000 | -5809.000 B/row (-19.94%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 196.000 | 0.000 | -196.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 619.084 | 621.083 | +1.999 us/row (+0.32%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 11562.000 | 6722.000 | -4840.000 B/row (-41.86%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 30234.000 | 24874.000 | -5360.000 B/row (-17.73%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 182.167 | 167.209 | -14.958 us/row (-8.21%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 3898.000 | 3024.000 | -874.000 B/row (-22.42%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 17098.000 | 15138.000 | -1960.000 B/row (-11.46%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 173.708 | 136.084 | -37.624 us/row (-21.66%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 2874.000 | 2824.000 | -50.000 B/row (-1.74%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 16026.000 | 14938.000 | -1088.000 B/row (-6.79%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 198.917 | 162.250 | -36.667 us/row (-18.43%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 3848.000 | 3024.000 | -824.000 B/row (-21.41%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 17098.000 | 15138.000 | -1960.000 B/row (-11.46%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 193.417 | 141.000 | -52.417 us/row (-27.10%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 2874.000 | 2824.000 | -50.000 B/row (-1.74%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 16026.000 | 14938.000 | -1088.000 B/row (-6.79%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 219.875 | 202.917 | -16.958 us/row (-7.71%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 4584.000 | 3810.000 | -774.000 B/row (-16.88%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 16594.000 | 14826.000 | -1768.000 B/row (-10.65%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 200.417 | 186.458 | -13.959 us/row (-6.96%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3560.000 | 3560.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 15522.000 | 14626.000 | -896.000 B/row (-5.77%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 256.292 | 198.875 | -57.417 us/row (-22.40%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 4634.000 | 3760.000 | -874.000 B/row (-18.86%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 16594.000 | 14826.000 | -1768.000 B/row (-10.65%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 222.084 | 174.750 | -47.334 us/row (-21.31%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 3510.000 | 3660.000 | +150.000 B/row (+4.27%) | 1 | larger |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 15522.000 | 14626.000 | -896.000 B/row (-5.77%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 193.167 | 165.750 | -27.417 us/row (-14.19%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 3618.000 | 2744.000 | -874.000 B/row (-24.16%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 17370.000 | 15042.000 | -2328.000 B/row (-13.40%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 173.208 | 153.250 | -19.958 us/row (-11.52%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2612.000 | 2462.000 | -150.000 B/row (-5.74%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 16266.000 | 14810.000 | -1456.000 B/row (-8.95%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 218.791 | 160.875 | -57.916 us/row (-26.47%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 3618.000 | 2744.000 | -874.000 B/row (-24.16%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 17370.000 | 15042.000 | -2328.000 B/row (-13.40%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 185.875 | 142.250 | -43.625 us/row (-23.47%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 2612.000 | 2512.000 | -100.000 B/row (-3.83%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 16266.000 | 14810.000 | -1456.000 B/row (-8.95%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 222.250 | 202.125 | -20.125 us/row (-9.06%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 4634.000 | 3810.000 | -824.000 B/row (-17.78%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 16594.000 | 14826.000 | -1768.000 B/row (-10.65%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 204.750 | 173.209 | -31.541 us/row (-15.40%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 3610.000 | 3660.000 | +50.000 B/row (+1.39%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 15522.000 | 14626.000 | -896.000 B/row (-5.77%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 1.000 | 0.000 | -1.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 234.708 | 185.584 | -49.124 us/row (-20.93%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 4634.000 | 3810.000 | -824.000 B/row (-17.78%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 16594.000 | 14826.000 | -1768.000 B/row (-10.65%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 1.000 | 0.000 | -1.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 213.875 | 166.416 | -47.459 us/row (-22.19%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3560.000 | 3660.000 | +100.000 B/row (+2.81%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 15522.000 | 14626.000 | -896.000 B/row (-5.77%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared | elapsedUs | 4482.250 | 3395.584 | -1086.666 us (-24.24%) | 9 | faster |
| 3.13 | model-preparation | model.prepared | retainedBytes | 635624.000 | 415992.000 | -219632.000 B (-34.55%) | 1 | smaller |
| 3.13 | model-preparation | model.prepared | transientBytes | 652472.000 | 436144.000 | -216328.000 B (-33.16%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 49.213 | 36.302 | -12.911 us/row (-26.24%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1580.859 | 1582.422 | +1.562 B/row (+0.10%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3530.195 | 3493.977 | -36.219 B/row (-1.03%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 51.689 | 40.805 | -10.884 us/row (-21.06%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2765.086 | 2772.320 | +7.234 B/row (+0.26%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5686.656 | 5643.945 | -42.711 B/row (-0.75%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 56.865 | 42.090 | -14.775 us/row (-25.98%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1744.781 | 1767.406 | +22.625 B/row (+1.30%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4061.438 | 3987.688 | -73.750 B/row (-1.82%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 57.225 | 45.301 | -11.925 us/row (-20.84%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2931.656 | 2933.562 | +1.906 B/row (+0.07%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6223.688 | 6077.969 | -145.719 B/row (-2.34%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 147.760 | 60.536 | -87.224 us/row (-59.03%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2372.625 | 2386.750 | +14.125 B/row (+0.60%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 5920.375 | 5629.125 | -291.250 B/row (-4.92%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 77.740 | 63.172 | -14.568 us/row (-18.74%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3601.000 | 3601.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 7948.000 | 7722.625 | -225.375 B/row (-2.84%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 337.084 | 232.375 | -104.709 us/row (-31.06%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 4272.000 | 3632.000 | -640.000 B/row (-14.98%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 16498.000 | 15066.000 | -1432.000 B/row (-8.68%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 33.000 | 0.000 | -33.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 361.584 | 263.292 | -98.292 us/row (-27.18%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 4372.000 | 3582.000 | -790.000 B/row (-18.07%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 16498.000 | 15066.000 | -1432.000 B/row (-8.68%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 411.250 | 286.250 | -125.000 us/row (-30.40%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 4322.000 | 3582.000 | -740.000 B/row (-17.12%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 16378.000 | 15066.000 | -1312.000 B/row (-8.01%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 15.000 | 0.000 | -15.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 433.041 | 290.750 | -142.291 us/row (-32.86%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 4372.000 | 3682.000 | -690.000 B/row (-15.78%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 16378.000 | 15066.000 | -1312.000 B/row (-8.01%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 447.625 | 341.917 | -105.708 us/row (-23.62%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 6002.000 | 4472.000 | -1530.000 B/row (-25.49%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 18178.000 | 15970.000 | -2208.000 B/row (-12.15%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 105.000 | 0.000 | -105.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 479.125 | 323.208 | -155.917 us/row (-32.54%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 6002.000 | 4522.000 | -1480.000 B/row (-24.66%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 18178.000 | 15970.000 | -2208.000 B/row (-12.15%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 872.916 | 733.000 | -139.916 us/row (-16.03%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 12772.000 | 7882.000 | -4890.000 B/row (-38.29%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 31835.000 | 26209.000 | -5626.000 B/row (-17.67%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 393.000 | 0.000 | -393.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 916.042 | 665.250 | -250.792 us/row (-27.38%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 12722.000 | 7782.000 | -4940.000 B/row (-38.83%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 33692.000 | 24570.000 | -9122.000 B/row (-27.07%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 366.125 | 296.375 | -69.750 us/row (-19.05%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 6632.000 | 5958.000 | -674.000 B/row (-10.16%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 17212.000 | 15674.000 | -1538.000 B/row (-8.94%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 345.625 | 280.166 | -65.459 us/row (-18.94%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5746.000 | 5646.000 | -100.000 B/row (-1.74%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16274.000 | 15636.000 | -638.000 B/row (-3.92%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 367.333 | 313.334 | -53.999 us/row (-14.70%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 6832.000 | 5808.000 | -1024.000 B/row (-14.99%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 18031.000 | 15390.000 | -2641.000 B/row (-14.65%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 44.000 | 0.000 | -44.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 363.541 | 290.750 | -72.791 us/row (-20.02%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5746.000 | 5646.000 | -100.000 B/row (-1.74%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 17323.000 | 15370.000 | -1953.000 B/row (-11.27%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 206.292 | 194.625 | -11.667 us/row (-5.66%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 3218.000 | 2528.000 | -690.000 B/row (-21.44%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 16802.000 | 15186.000 | -1616.000 B/row (-9.62%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 211.083 | 190.042 | -21.041 us/row (-9.97%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 3168.000 | 2528.000 | -640.000 B/row (-20.20%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 16802.000 | 15186.000 | -1616.000 B/row (-9.62%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 30.000 | 0.000 | -30.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 241.125 | 238.583 | -2.542 us/row (-1.05%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 4442.000 | 3200.000 | -1242.000 B/row (-27.96%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 19290.000 | 15858.000 | -3432.000 B/row (-17.79%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 61.000 | 0.000 | -61.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 258.792 | 228.500 | -30.292 us/row (-11.71%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 4392.000 | 3200.000 | -1192.000 B/row (-27.14%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 19290.000 | 15858.000 | -3432.000 B/row (-17.79%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 140.000 | 0.000 | -140.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 316.375 | 287.083 | -29.292 us/row (-9.26%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 6024.000 | 4046.000 | -1978.000 B/row (-32.84%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 23386.000 | 17234.000 | -6152.000 B/row (-26.31%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 191.000 | 0.000 | -191.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 326.667 | 293.000 | -33.667 us/row (-10.31%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 6024.000 | 4096.000 | -1928.000 B/row (-32.01%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 23386.000 | 17234.000 | -6152.000 B/row (-26.31%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 183.792 | 163.042 | -20.750 us/row (-11.29%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 2256.000 | 2016.000 | -240.000 B/row (-10.64%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 15770.000 | 14674.000 | -1096.000 B/row (-6.95%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 6.000 | 0.000 | -6.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 178.209 | 160.541 | -17.668 us/row (-9.91%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 2256.000 | 2016.000 | -240.000 B/row (-10.64%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 15770.000 | 14674.000 | -1096.000 B/row (-6.95%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 631.500 | 541.333 | -90.167 us/row (-14.28%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 15822.000 | 9488.000 | -6334.000 B/row (-40.03%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 38426.000 | 27746.000 | -10680.000 B/row (-27.79%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 166.000 | 0.000 | -166.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 732.334 | 534.125 | -198.209 us/row (-27.07%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 15872.000 | 9538.000 | -6334.000 B/row (-39.91%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 38989.000 | 27925.000 | -11064.000 B/row (-28.38%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 308.250 | 258.500 | -49.750 us/row (-16.14%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 5646.000 | 3970.000 | -1676.000 B/row (-29.68%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 19330.000 | 16578.000 | -2752.000 B/row (-14.24%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 46.000 | 0.000 | -46.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 339.666 | 259.167 | -80.499 us/row (-23.70%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 5696.000 | 3920.000 | -1776.000 B/row (-31.18%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 19330.000 | 16578.000 | -2752.000 B/row (-14.24%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 350.875 | 246.792 | -104.083 us/row (-29.66%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 3168.000 | 2578.000 | -590.000 B/row (-18.62%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 16682.000 | 15186.000 | -1496.000 B/row (-8.97%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 7.000 | 0.000 | -7.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 321.750 | 244.500 | -77.250 us/row (-24.01%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 3118.000 | 2528.000 | -590.000 B/row (-18.92%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 16682.000 | 15186.000 | -1496.000 B/row (-8.97%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 367.583 | 285.583 | -82.000 us/row (-22.31%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 4898.000 | 3368.000 | -1530.000 B/row (-31.24%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 18482.000 | 16090.000 | -2392.000 B/row (-12.94%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 52.000 | 0.000 | -52.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 396.834 | 313.458 | -83.376 us/row (-21.01%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 4848.000 | 3418.000 | -1430.000 B/row (-29.50%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 18482.000 | 16090.000 | -2392.000 B/row (-12.94%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 812.125 | 715.125 | -97.000 us/row (-11.94%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 11518.000 | 6678.000 | -4840.000 B/row (-42.02%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 29466.000 | 23817.000 | -5649.000 B/row (-19.17%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 196.000 | 0.000 | -196.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 804.792 | 694.875 | -109.917 us/row (-13.66%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 11618.000 | 6728.000 | -4890.000 B/row (-42.09%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 30586.000 | 25434.000 | -5152.000 B/row (-16.84%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 206.458 | 179.750 | -26.708 us/row (-12.94%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 3986.000 | 3112.000 | -874.000 B/row (-21.93%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 17658.000 | 15666.000 | -1992.000 B/row (-11.28%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 187.667 | 162.750 | -24.917 us/row (-13.28%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 2954.000 | 2904.000 | -50.000 B/row (-1.69%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 16622.000 | 15406.000 | -1216.000 B/row (-7.32%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 215.417 | 192.833 | -22.584 us/row (-10.48%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 3936.000 | 3162.000 | -774.000 B/row (-19.66%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 17658.000 | 15666.000 | -1992.000 B/row (-11.28%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 212.375 | 167.625 | -44.750 us/row (-21.07%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 2954.000 | 2954.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 16622.000 | 15406.000 | -1216.000 B/row (-7.32%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 241.417 | 214.791 | -26.626 us/row (-11.03%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 4780.000 | 3906.000 | -874.000 B/row (-18.28%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 16970.000 | 15290.000 | -1680.000 B/row (-9.90%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 220.208 | 190.375 | -29.833 us/row (-13.55%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3748.000 | 3648.000 | -100.000 B/row (-2.67%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 15934.000 | 15030.000 | -904.000 B/row (-5.67%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 258.250 | 229.250 | -29.000 us/row (-11.23%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 4730.000 | 3806.000 | -924.000 B/row (-19.53%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 16970.000 | 15290.000 | -1680.000 B/row (-9.90%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 22.000 | 0.000 | -22.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 249.375 | 210.958 | -38.417 us/row (-15.41%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 3648.000 | 3698.000 | +50.000 B/row (+1.37%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 15934.000 | 15030.000 | -904.000 B/row (-5.67%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 206.500 | 188.959 | -17.541 us/row (-8.49%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 3674.000 | 2850.000 | -824.000 B/row (-22.43%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 17882.000 | 15554.000 | -2328.000 B/row (-13.02%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 193.458 | 161.459 | -31.999 us/row (-16.54%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2660.000 | 2660.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 16818.000 | 15266.000 | -1552.000 B/row (-9.23%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 219.750 | 186.167 | -33.583 us/row (-15.28%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 3674.000 | 2850.000 | -824.000 B/row (-22.43%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 17882.000 | 15554.000 | -2328.000 B/row (-13.02%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 11.000 | 0.000 | -11.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 196.792 | 166.959 | -29.833 us/row (-15.16%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 2610.000 | 2560.000 | -50.000 B/row (-1.92%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 16818.000 | 15266.000 | -1552.000 B/row (-9.23%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 242.584 | 216.750 | -25.834 us/row (-10.65%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 4780.000 | 3906.000 | -874.000 B/row (-18.28%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 16970.000 | 15290.000 | -1680.000 B/row (-9.90%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 2.000 | 0.000 | -2.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 229.125 | 195.958 | -33.167 us/row (-14.48%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 3748.000 | 3698.000 | -50.000 B/row (-1.33%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 15934.000 | 15030.000 | -904.000 B/row (-5.67%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 1.000 | 0.000 | -1.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 254.917 | 216.750 | -38.167 us/row (-14.97%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 4780.000 | 3856.000 | -924.000 B/row (-19.33%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 16970.000 | 15290.000 | -1680.000 B/row (-9.90%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 1.000 | 0.000 | -1.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 16.000 | 0.000 | -16.000 calls/row (-100.00%) | 1 | changed |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.entityShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.shapeOfDeclaration | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 230.834 | 200.041 | -30.793 us/row (-13.34%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3698.000 | 3648.000 | -50.000 B/row (-1.35%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 15934.000 | 15030.000 | -904.000 B/row (-5.67%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared | elapsedUs | 6119.166 | 3373.584 | -2745.582 us (-44.87%) | 9 | faster |
| 3.14 | model-preparation | model.prepared | retainedBytes | 649080.000 | 427016.000 | -222064.000 B (-34.21%) | 1 | smaller |
| 3.14 | model-preparation | model.prepared | transientBytes | 655608.000 | 434456.000 | -221152.000 B (-33.73%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 66.841 | 36.691 | -30.150 us/row (-45.11%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1618.188 | 1623.453 | +5.266 B/row (+0.33%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3680.914 | 3313.727 | -367.188 B/row (-9.98%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 60.566 | 40.415 | -20.152 us/row (-33.27%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2810.047 | 2813.562 | +3.516 B/row (+0.13%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5852.656 | 5459.586 | -393.070 B/row (-6.72%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 73.352 | 40.651 | -32.701 us/row (-44.58%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1806.812 | 1809.125 | +2.312 B/row (+0.13%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4227.344 | 3856.219 | -371.125 B/row (-8.78%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 71.617 | 43.988 | -27.629 us/row (-38.58%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 3000.219 | 3012.312 | +12.094 B/row (+0.40%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6414.844 | 5952.312 | -462.531 B/row (-7.21%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 114.922 | 60.511 | -54.411 us/row (-47.35%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2572.375 | 2570.750 | -1.625 B/row (-0.06%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 6239.125 | 5590.375 | -648.750 B/row (-10.40%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 98.667 | 63.104 | -35.562 us/row (-36.04%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3802.875 | 3780.875 | -22.000 B/row (-0.58%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 8226.125 | 7752.250 | -473.875 B/row (-5.76%) | 9 | smaller |

Deltas are advisory and never ratchet the Budget Contract.
