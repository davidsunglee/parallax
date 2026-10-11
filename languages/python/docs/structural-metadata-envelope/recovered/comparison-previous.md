# Python cost report comparison

Timing deltas within 5% and byte deltas within 3% are read as noise; count deltas are exact. A cell present on one side alone, or whose unit differs, is not compared.

- The base capture is amended: envelopes re-classified under a later Budget Contract after the run its provenance names, recorded in the adjustment of conditions.json.

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
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.435 | 3.564 | +0.129 ratio (+3.77%) | 0 | larger |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.435 | 3.564 | +0.129 ratio (+3.77%) | 0 | larger |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.304 | 3.461 | +0.157 ratio (+4.77%) | 0 | larger |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 0.506 | 0.500 | -0.006 ratio (-1.20%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.likeForLike | 0.487 | 0.481 | -0.006 ratio (-1.21%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 1.531 | 1.526 | -0.005 ratio (-0.31%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.086 | 2.159 | +0.073 ratio (+3.49%) | 0 | larger |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.086 | 2.159 | +0.073 ratio (+3.49%) | 0 | larger |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.150 | 2.152 | +0.001 ratio (+0.07%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 1511.600 | 1603.317 | +91.717 ns (+6.07%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 6859.150 | 6678.912 | -180.238 ns (-2.63%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.directWireNs | 10529.646 | 11091.854 | +562.208 ns (+5.34%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.dumpNs | 5913.500 | 5957.771 | +44.271 ns (+0.75%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 4770.000 | 4770.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionNs | 14493.708 | 14772.750 | +279.042 ns (+1.93%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | 7560.000 | 7776.000 | +216.000 B (+2.86%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | 1240.000 | 1240.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | 12462.306 | 12558.183 | +95.877 ns (+0.77%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | 6320.000 | 6536.000 | +216.000 B (+3.42%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.readNs | 82.917 | 83.954 | +1.038 ns (+1.25%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 333.533 | 303.673 | -29.860 ns (-8.95%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 3706.000 | 3706.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 333.533 | 303.673 | -29.860 ns (-8.95%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | 301.813 | 300.090 | -1.723 ns (-0.57%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 10196.229 | 10175.285 | -20.944 ns (-0.21%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2733.896 | 2516.229 | -217.667 ns (-7.96%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 4960.000 | 4960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.readNs | 25.267 | 23.367 | -1.900 ns (-7.52%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2168.000 | 2168.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 279.450 | 348.065 | +68.615 ns (+24.55%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 6004.842 | 6011.769 | +6.927 ns (+0.12%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2507.604 | 2602.000 | +94.396 ns (+3.76%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 26.238 | 26.108 | -0.129 ns (-0.49%) | 0 | within noise |
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
| - | - | cpython-3.13/nullable | compact.callNs | 1357.081 | 1419.593 | +62.512 ns (+4.61%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 2309.002 | 2332.177 | +23.175 ns (+1.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.directWireNs | 5603.125 | 5902.916 | +299.791 ns (+5.35%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1804.042 | 1830.229 | +26.188 ns (+1.45%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionNs | 7729.916 | 8431.708 | +701.792 ns (+9.08%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | 2504.000 | 2624.000 | +120.000 B (+4.79%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | 6160.725 | 6344.610 | +183.885 ns (+2.98%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | 2032.000 | 2152.000 | +120.000 B (+5.91%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.readNs | 75.042 | 75.171 | +0.129 ns (+0.17%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 217.895 | 256.748 | +38.853 ns (+17.83%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 217.895 | 256.748 | +38.853 ns (+17.83%) | 0 | larger |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 152.692 | 164.608 | +11.916 ns (+7.80%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5517.350 | 5572.954 | +55.604 ns (+1.01%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 894.145 | 865.250 | -28.895 ns (-3.23%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 20.773 | 20.773 | +0.000 ns (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 205.505 | 189.417 | -16.088 ns (-7.83%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1258.225 | 1208.208 | -50.017 ns (-3.98%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 917.521 | 876.500 | -41.021 ns (-4.47%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 25.175 | 21.829 | -3.346 ns (-13.29%) | 0 | smaller |
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
| - | - | cpython-3.13/partial | compact.callNs | 1350.704 | 1380.836 | +30.131 ns (+2.23%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 2115.358 | 2109.248 | -6.110 ns (-0.29%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.directWireNs | 4997.854 | 5190.917 | +193.063 ns (+3.86%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.dumpNs | 1850.667 | 1851.542 | +0.875 ns (+0.05%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 3432.000 | 3432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionNs | 7016.083 | 7388.542 | +372.459 ns (+5.31%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | 2416.000 | 2536.000 | +120.000 B (+4.97%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | 5503.931 | 5540.529 | +36.598 ns (+0.66%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | 2032.000 | 2152.000 | +120.000 B (+5.91%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.readNs | 75.848 | 75.098 | -0.750 ns (-0.99%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 227.251 | 215.013 | -12.238 ns (-5.39%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 227.251 | 215.013 | -12.238 ns (-5.39%) | 0 | smaller |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 185.791 | 213.956 | +28.165 ns (+15.16%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5140.500 | 5171.190 | +30.690 ns (+0.60%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.dumpNs | 886.312 | 895.500 | +9.188 ns (+1.04%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 22.808 | 21.250 | -1.558 ns (-6.83%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 215.685 | 227.671 | +11.985 ns (+5.56%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 943.794 | 935.121 | -8.673 ns (-0.92%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 905.021 | 904.980 | -0.041 ns (-0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 22.717 | 21.508 | -1.208 ns (-5.32%) | 0 | smaller |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 1349.902 | 1350.062 | +0.161 ns (+0.01%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 2204.452 | 2197.063 | -7.390 ns (-0.34%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | 5720.709 | 5956.479 | +235.771 ns (+4.12%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1648.417 | 1651.750 | +3.333 ns (+0.20%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 3408.000 | 3408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | 7754.458 | 7893.542 | +139.083 ns (+1.79%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | 2776.000 | 2896.000 | +120.000 B (+4.32%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | 5872.456 | 6052.883 | +180.427 ns (+3.07%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | 2304.000 | 2424.000 | +120.000 B (+5.21%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.readNs | 77.402 | 79.036 | +1.634 ns (+2.11%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 197.811 | 234.141 | +36.330 ns (+18.37%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 197.811 | 234.141 | +36.330 ns (+18.37%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 129.542 | 193.075 | +63.533 ns (+49.04%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4221.125 | 4106.717 | -114.408 ns (-2.71%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 809.271 | 789.250 | -20.021 ns (-2.47%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 22.583 | 24.262 | +1.679 ns (+7.43%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 151.420 | 187.292 | +35.871 ns (+23.69%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1106.663 | 1044.042 | -62.621 ns (-5.66%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 816.646 | 788.105 | -28.541 ns (-3.49%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 22.152 | 23.833 | +1.681 ns (+7.59%) | 0 | larger |
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
| - | - | cpython-3.13/shallow | compact.callNs | 1345.796 | 1330.721 | -15.075 ns (-1.12%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 2038.287 | 2058.342 | +20.054 ns (+0.98%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.directWireNs | 7142.750 | 7266.875 | +124.125 ns (+1.74%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1390.520 | 1415.854 | +25.334 ns (+1.82%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 3384.000 | 3384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionNs | 8957.354 | 9027.708 | +70.354 ns (+0.79%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | 3358.000 | 3414.000 | +56.000 B (+1.67%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | 430.000 | 430.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | 5507.196 | 5488.196 | -19.000 ns (-0.35%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | 2928.000 | 2984.000 | +56.000 B (+1.91%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.readNs | 87.662 | 90.969 | +3.307 ns (+3.77%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 213.771 | 209.067 | -4.704 ns (-2.20%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 213.771 | 209.067 | -4.704 ns (-2.20%) | 0 | within noise |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 196.475 | 308.471 | +111.996 ns (+57.00%) | 0 | larger |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2772.858 | 2846.154 | +73.296 ns (+2.64%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 718.354 | 718.854 | +0.500 ns (+0.07%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 25.891 | 24.729 | -1.162 ns (-4.49%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 223.743 | 200.050 | -23.693 ns (-10.59%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 799.090 | 774.992 | -24.098 ns (-3.02%) | 0 | smaller |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 723.145 | 709.937 | -13.208 ns (-1.83%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 25.984 | 25.510 | -0.474 ns (-1.82%) | 0 | within noise |
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
| - | - | cpython-3.13/warmed | compact.callNs | 1765.196 | 1647.935 | -117.261 ns (-6.64%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 4122.992 | 4065.106 | -57.885 ns (-1.40%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1784.438 | 1721.063 | -63.375 ns (-3.55%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 3384.000 | 3384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.readNs | 90.021 | 87.396 | -2.625 ns (-2.92%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 241.403 | 221.827 | -19.576 ns (-8.11%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.transientBytes | 2578.000 | 2578.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 241.403 | 221.827 | -19.576 ns (-8.11%) | 0 | smaller |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 89.135 | 92.415 | +3.280 ns (+3.68%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 3932.156 | 3846.419 | -85.738 ns (-2.18%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 736.375 | 700.250 | -36.125 ns (-4.91%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 25.474 | 24.625 | -0.849 ns (-3.33%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 190.548 | 230.111 | +39.563 ns (+20.76%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1745.244 | 1714.869 | -30.375 ns (-1.74%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 726.042 | 710.208 | -15.833 ns (-2.18%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 25.760 | 25.745 | -0.016 ns (-0.06%) | 0 | within noise |
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
| - | - | cpython-3.13/wide | compact.callNs | 1327.054 | 1427.303 | +100.248 ns (+7.55%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 2608.737 | 2573.740 | -34.998 ns (-1.34%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.directWireNs | 6761.542 | 6990.146 | +228.605 ns (+3.38%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.dumpNs | 2428.646 | 2432.187 | +3.542 ns (+0.15%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 3512.000 | 3512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionNs | 9387.542 | 9614.750 | +227.208 ns (+2.42%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | 3240.000 | 3360.000 | +120.000 B (+3.70%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | 664.000 | 664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | 7442.610 | 7513.615 | +71.004 ns (+0.95%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | 2576.000 | 2696.000 | +120.000 B (+4.66%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.readNs | 79.270 | 79.068 | -0.202 ns (-0.25%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 222.688 | 200.272 | -22.415 ns (-10.07%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 222.688 | 200.272 | -22.415 ns (-10.07%) | 0 | smaller |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 121.927 | 227.723 | +105.795 ns (+86.77%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 7994.156 | 8034.610 | +40.454 ns (+0.51%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1164.791 | 1226.938 | +62.146 ns (+5.34%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 21.880 | 21.214 | -0.667 ns (-3.05%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 197.073 | 250.912 | +53.840 ns (+27.32%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1733.323 | 1787.254 | +53.931 ns (+3.11%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1122.083 | 1153.875 | +31.792 ns (+2.83%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 22.457 | 20.837 | -1.620 ns (-7.21%) | 0 | smaller |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.330 | 3.105 | -0.225 ratio (-6.76%) | 0 | smaller |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.330 | 3.105 | -0.225 ratio (-6.76%) | 0 | smaller |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.337 | 3.030 | -0.307 ratio (-9.21%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 0.496 | 0.514 | +0.018 ratio (+3.63%) | 0 | larger |
| - | - | cpython-3.14 | operation.construction.likeForLike | 0.477 | 0.497 | +0.020 ratio (+4.15%) | 0 | larger |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 1.504 | 1.490 | -0.014 ratio (-0.93%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.110 | 2.141 | +0.032 ratio (+1.51%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.110 | 2.141 | +0.032 ratio (+1.51%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.132 | 2.164 | +0.031 ratio (+1.46%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 1618.333 | 1518.941 | -99.392 ns (-6.14%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 6679.833 | 5885.350 | -794.483 ns (-11.89%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.directWireNs | 11578.167 | 10210.042 | -1368.125 ns (-11.82%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.dumpNs | 6245.375 | 5678.667 | -566.708 ns (-9.07%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 5034.000 | 5034.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionNs | 15489.771 | 13992.250 | -1497.521 ns (-9.67%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | 8450.000 | 8674.000 | +224.000 B (+2.65%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | 1248.000 | 1248.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | 13486.942 | 12042.750 | -1444.192 ns (-10.71%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | 7202.000 | 7426.000 | +224.000 B (+3.11%) | 0 | larger |
| - | - | cpython-3.14/nested | compact.readNs | 90.992 | 78.512 | -12.479 ns (-13.71%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 279.522 | 0.531 | -278.991 ns (-99.81%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 3802.000 | 3802.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 279.522 | 0.531 | -278.991 ns (-99.81%) | 0 | smaller |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 23.081 | 116.306 | +93.225 ns (+403.90%) | 0 | larger |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 10971.815 | 9427.715 | -1544.100 ns (-14.07%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 2678.042 | 2425.125 | -252.917 ns (-9.44%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5184.000 | 5184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.readNs | 27.300 | 25.600 | -1.700 ns (-6.23%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2264.000 | 2264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 167.004 | 201.800 | +34.796 ns (+20.84%) | 0 | larger |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 6292.163 | 5612.637 | -679.525 ns (-10.80%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 2662.625 | 2439.583 | -223.042 ns (-8.38%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4744.000 | 4744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 26.596 | 25.675 | -0.921 ns (-3.46%) | 0 | smaller |
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
| - | - | cpython-3.14/nullable | compact.callNs | 1405.802 | 1326.238 | -79.565 ns (-5.66%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 2294.656 | 2043.054 | -251.602 ns (-10.96%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.directWireNs | 5955.917 | 5364.208 | -591.709 ns (-9.93%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.dumpNs | 1854.187 | 1672.687 | -181.500 ns (-9.79%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 3672.000 | 3672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionNs | 8266.166 | 7258.771 | -1007.396 ns (-12.19%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | 2736.000 | 2864.000 | +128.000 B (+4.68%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | 480.000 | 480.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | 6769.844 | 5818.990 | -950.854 ns (-14.05%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | 2256.000 | 2384.000 | +128.000 B (+5.67%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.readNs | 81.923 | 68.783 | -13.140 ns (-16.04%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 207.943 | 200.102 | -7.841 ns (-3.77%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 207.943 | 200.102 | -7.841 ns (-3.77%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 261.771 | 53.719 | -208.052 ns (-79.48%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 5475.187 | 4599.406 | -875.781 ns (-16.00%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 927.458 | 815.250 | -112.208 ns (-12.10%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 23.733 | 22.629 | -1.104 ns (-4.65%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 206.906 | 195.983 | -10.923 ns (-5.28%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1225.594 | 1080.058 | -145.535 ns (-11.87%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 922.479 | 799.750 | -122.729 ns (-13.30%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 26.615 | 24.204 | -2.410 ns (-9.06%) | 0 | smaller |
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
| - | - | cpython-3.14/partial | compact.callNs | 1416.419 | 1192.175 | -224.243 ns (-15.83%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 2205.498 | 1952.617 | -252.881 ns (-11.47%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.directWireNs | 5284.875 | 4841.938 | -442.937 ns (-8.38%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.dumpNs | 1897.375 | 1600.958 | -296.417 ns (-15.62%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 3576.000 | 3576.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionNs | 7676.062 | 6545.292 | -1130.771 ns (-14.73%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | 2616.000 | 2744.000 | +128.000 B (+4.89%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | 392.000 | 392.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | 5934.242 | 5164.244 | -769.998 ns (-12.98%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | 2224.000 | 2352.000 | +128.000 B (+5.76%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.readNs | 81.215 | 67.829 | -13.385 ns (-16.48%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 234.961 | 215.323 | -19.638 ns (-8.36%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 234.961 | 215.323 | -19.638 ns (-8.36%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 142.048 | 135.635 | -6.413 ns (-4.51%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 5241.952 | 4401.219 | -840.733 ns (-16.04%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 960.770 | 790.875 | -169.896 ns (-17.68%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 26.888 | 22.412 | -4.475 ns (-16.64%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 216.577 | 182.965 | -33.613 ns (-15.52%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 962.444 | 831.848 | -130.596 ns (-13.57%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 916.479 | 796.708 | -119.771 ns (-13.07%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 23.600 | 23.679 | +0.079 ns (+0.34%) | 0 | within noise |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 1400.962 | 1282.458 | -118.504 ns (-8.46%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 2219.975 | 1984.208 | -235.767 ns (-10.62%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | 5872.771 | 5431.688 | -441.083 ns (-7.51%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1659.270 | 1490.021 | -169.249 ns (-10.20%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 3552.000 | 3552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | 7950.395 | 7313.708 | -636.687 ns (-8.01%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | 2984.000 | 3112.000 | +128.000 B (+4.29%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | 480.000 | 480.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | 6306.252 | 5520.283 | -785.969 ns (-12.46%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | 2504.000 | 2632.000 | +128.000 B (+5.11%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.readNs | 86.869 | 71.378 | -15.491 ns (-17.83%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 224.560 | 204.622 | -19.938 ns (-8.88%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 224.560 | 204.622 | -19.938 ns (-8.88%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 222.656 | 98.969 | -123.687 ns (-55.55%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4142.010 | 3523.677 | -618.333 ns (-14.93%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 820.979 | 716.271 | -104.708 ns (-12.75%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 25.818 | 24.119 | -1.699 ns (-6.58%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 273.131 | 206.710 | -66.421 ns (-24.32%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1056.806 | 940.102 | -116.704 ns (-11.04%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 832.500 | 710.271 | -122.229 ns (-14.68%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 27.378 | 23.759 | -3.619 ns (-13.22%) | 0 | smaller |
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
| - | - | cpython-3.14/shallow | compact.callNs | 1352.048 | 1256.644 | -95.404 ns (-7.06%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 2145.535 | 1884.294 | -261.242 ns (-12.18%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.directWireNs | 7203.020 | 6768.541 | -434.479 ns (-6.03%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1421.979 | 1278.916 | -143.063 ns (-10.06%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 3528.000 | 3528.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionNs | 9155.167 | 8189.896 | -965.271 ns (-10.54%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | 3662.000 | 3718.000 | +56.000 B (+1.53%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | 438.000 | 438.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | 5839.987 | 5083.290 | -756.698 ns (-12.96%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | 3224.000 | 3280.000 | +56.000 B (+1.74%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.readNs | 94.490 | 83.370 | -11.120 ns (-11.77%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 234.559 | 214.450 | -20.109 ns (-8.57%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 234.559 | 214.450 | -20.109 ns (-8.57%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 244.502 | 179.175 | -65.328 ns (-26.72%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 2838.352 | 2466.471 | -371.881 ns (-13.10%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 741.521 | 669.500 | -72.021 ns (-9.71%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 27.516 | 25.521 | -1.995 ns (-7.25%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 185.250 | 188.481 | +3.232 ns (+1.74%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 825.583 | 720.956 | -104.627 ns (-12.67%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 743.563 | 663.271 | -80.292 ns (-10.80%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 26.901 | 25.333 | -1.568 ns (-5.83%) | 0 | smaller |
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
| - | - | cpython-3.14/warmed | compact.callNs | 1662.490 | 1475.692 | -186.798 ns (-11.24%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 4272.510 | 3758.496 | -514.015 ns (-12.03%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1775.666 | 1599.000 | -176.667 ns (-9.95%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 3528.000 | 3528.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.readNs | 97.667 | 79.870 | -17.797 ns (-18.22%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 226.794 | 236.104 | +9.310 ns (+4.10%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.transientBytes | 2690.000 | 2690.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 226.794 | 236.104 | +9.310 ns (+4.10%) | 0 | larger |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 200.100 | 108.154 | -91.946 ns (-45.95%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 4087.588 | 3386.367 | -701.221 ns (-17.15%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 736.146 | 694.771 | -41.375 ns (-5.62%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 26.354 | 24.562 | -1.792 ns (-6.80%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 215.577 | 179.994 | -35.583 ns (-16.51%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1856.152 | 1608.527 | -247.625 ns (-13.34%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 738.666 | 674.729 | -63.937 ns (-8.66%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 27.594 | 25.620 | -1.974 ns (-7.15%) | 0 | smaller |
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
| - | - | cpython-3.14/wide | compact.callNs | 1420.681 | 1278.146 | -142.536 ns (-10.03%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 2560.944 | 2281.646 | -279.298 ns (-10.91%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.directWireNs | 7035.646 | 6498.729 | -536.916 ns (-7.63%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.dumpNs | 2318.146 | 2167.521 | -150.625 ns (-6.50%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 3720.000 | 3720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionNs | 9676.063 | 8707.459 | -968.604 ns (-10.01%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | 3488.000 | 3616.000 | +128.000 B (+3.67%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | 7966.462 | 6972.429 | -994.033 ns (-12.48%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | 2816.000 | 2944.000 | +128.000 B (+4.55%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.readNs | 84.440 | 75.320 | -9.120 ns (-10.80%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 223.902 | 204.808 | -19.094 ns (-8.53%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 223.902 | 204.808 | -19.094 ns (-8.53%) | 0 | smaller |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 307.442 | 135.638 | -171.804 ns (-55.88%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 7866.204 | 6796.550 | -1069.654 ns (-13.60%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1169.750 | 1068.688 | -101.062 ns (-8.64%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 24.880 | 23.107 | -1.773 ns (-7.13%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 220.946 | 170.129 | -50.817 ns (-23.00%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 1679.138 | 1575.642 | -103.496 ns (-6.16%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1142.458 | 1009.542 | -132.916 ns (-11.63%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 24.719 | 24.288 | -0.431 ns (-1.74%) | 0 | within noise |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.295 | 3.092 | -0.202 us/event (-6.14%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 3.804 | 3.966 | +0.162 us/event (+4.26%) | 0 | larger |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.257 | 0.268 | +0.011 ratio (+4.29%) | 0 | larger |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.021 | 0.020 | -0.001 ratio (-5.36%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.068 | 0.065 | -0.002 ratio (-3.60%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.005 | 0.004 | -0.000 ratio (-5.98%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.165 | 0.166 | +0.000 ratio (+0.30%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p50 | 451.292 | 409.666 | -41.626 us (-9.22%) | 0 | faster |
| - | - | Safe logging alone, at INFO | observed.p95 | 470.458 | 437.917 | -32.541 us (-6.92%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 92.250 | 86.584 | -5.666 us (-6.14%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 106.500 | 111.042 | +4.542 us (+4.26%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.257 | 0.269 | +0.011 ratio (+4.39%) | 0 | larger |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.298 | 0.339 | +0.041 ratio (+13.61%) | 0 | larger |
| - | - | Safe logging alone, at INFO | plain.p50 | 358.667 | 322.791 | -35.876 us (-10.00%) | 0 | faster |
| - | - | Safe logging alone, at INFO | plain.p95 | 394.917 | 343.250 | -51.667 us (-13.08%) | 0 | faster |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.258 | 0.269 | +0.011 ratio (+4.22%) | 0 | larger |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.191 | 0.276 | +0.085 ratio (+44.18%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.385 | 2.223 | -0.162 us/event (-6.80%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 3.917 | 2.957 | -0.960 us/event (-24.51%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.187 | 0.194 | +0.007 ratio (+3.89%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.015 | 0.014 | -0.001 ratio (-6.01%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.049 | 0.047 | -0.002 ratio (-4.21%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | -0.000 ratio (-6.63%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.120 | 0.120 | -0.000 ratio (-0.22%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p50 | 424.292 | 383.333 | -40.959 us (-9.65%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | observed.p95 | 468.209 | 408.458 | -59.751 us (-12.76%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 66.792 | 62.249 | -4.543 us (-6.80%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 109.666 | 82.791 | -26.875 us (-24.51%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.187 | 0.194 | +0.007 ratio (+3.87%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.307 | 0.258 | -0.049 ratio (-16.09%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | plain.p50 | 357.541 | 320.750 | -36.791 us (-10.29%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | plain.p95 | 372.792 | 345.125 | -27.667 us (-7.42%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.187 | 0.195 | +0.008 ratio (+4.51%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.256 | 0.184 | -0.072 ratio (-28.30%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 3.987 | 3.744 | -0.243 us/event (-6.08%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.929 | 4.629 | -0.299 us/event (-6.07%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.310 | 0.324 | +0.014 ratio (+4.37%) | 0 | larger |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.026 | 0.024 | -0.001 ratio (-5.30%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.082 | 0.079 | -0.003 ratio (-3.53%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-5.92%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.199 | 0.200 | +0.001 ratio (+0.38%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | observed.p50 | 472.084 | 428.791 | -43.293 us (-9.17%) | 0 | faster |
| - | - | fan-out of three, tracing every root | observed.p95 | 500.083 | 456.542 | -43.541 us (-8.71%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 111.625 | 104.833 | -6.792 us (-6.08%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 138.000 | 129.625 | -8.375 us (-6.07%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.310 | 0.323 | +0.013 ratio (+4.15%) | 0 | larger |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.381 | 0.399 | +0.017 ratio (+4.54%) | 0 | larger |
| - | - | fan-out of three, tracing every root | plain.p50 | 359.959 | 323.917 | -36.042 us (-10.01%) | 0 | faster |
| - | - | fan-out of three, tracing every root | plain.p95 | 382.000 | 348.458 | -33.542 us (-8.78%) | 0 | faster |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.311 | 0.324 | +0.012 ratio (+3.94%) | 0 | larger |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.309 | 0.310 | +0.001 ratio (+0.34%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 3.815 | 3.557 | -0.259 us/event (-6.79%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 4.954 | 4.467 | -0.487 us/event (-9.82%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.297 | 0.308 | +0.011 ratio (+3.58%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.025 | 0.023 | -0.001 ratio (-6.01%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.079 | 0.075 | -0.003 ratio (-4.25%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-6.62%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.191 | 0.190 | -0.001 ratio (-0.38%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 466.583 | 423.500 | -43.083 us (-9.23%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 501.333 | 452.542 | -48.791 us (-9.73%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 106.833 | 99.583 | -7.250 us (-6.79%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 138.709 | 125.083 | -13.626 us (-9.82%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.298 | 0.308 | +0.010 ratio (+3.41%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.384 | 0.386 | +0.002 ratio (+0.50%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 359.667 | 323.666 | -36.001 us (-10.01%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 383.250 | 346.167 | -37.083 us (-9.68%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.297 | 0.308 | +0.011 ratio (+3.76%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.308 | 0.307 | -0.001 ratio (-0.26%) | 0 | within noise |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.458 | 1.369 | -0.089 us/event (-6.12%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 1.942 | 2.064 | +0.122 us/event (+6.28%) | 0 | larger |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.114 | 0.119 | +0.005 ratio (+4.67%) | 0 | larger |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.009 | 0.009 | -0.000 ratio (-5.32%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.030 | 0.029 | -0.001 ratio (-3.50%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-5.95%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.073 | 0.074 | +0.000 ratio (+0.52%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p50 | 398.875 | 359.375 | -39.500 us (-9.90%) | 0 | faster |
| - | - | one Handler that keeps nothing | observed.p95 | 415.833 | 383.959 | -31.874 us (-7.67%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 40.833 | 38.333 | -2.500 us (-6.12%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 54.375 | 57.791 | +3.416 us (+6.28%) | 0 | slower |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.114 | 0.120 | +0.005 ratio (+4.59%) | 0 | larger |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.152 | 0.179 | +0.027 ratio (+17.93%) | 0 | larger |
| - | - | one Handler that keeps nothing | plain.p50 | 357.750 | 320.875 | -36.875 us (-10.31%) | 0 | faster |
| - | - | one Handler that keeps nothing | plain.p95 | 395.834 | 341.750 | -54.084 us (-13.66%) | 0 | faster |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.115 | 0.120 | +0.005 ratio (+4.38%) | 0 | larger |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.051 | 0.124 | +0.073 ratio (+144.46%) | 0 | larger |
| - | - | workload | events | 28.000 | 28.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | workload | statements | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |

## snapshot-delivery

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 9772.042 | 9775.333 | +3.291 us (+0.03%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1458.229 | 1392.861 | -65.367 KiB (-4.48%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 693.328 | 693.328 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 96231.000 | 106295.292 | +10064.292 us (+10.46%) | 9 | slower |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 12761.182 | 12652.338 | -108.844 KiB (-0.85%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 6931.836 | 6931.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 16006.083 | 17380.041 | +1373.958 us (+8.58%) | 9 | slower |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 407.869 | 391.807 | -16.062 KiB (-3.94%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.458 | 3.458 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 110287.500 | 110052.458 | -235.042 us (-0.21%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 831.072 | 775.244 | -55.828 KiB (-6.72%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.489 | 3.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8172.875 | 8157.542 | -15.333 us (-0.19%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1257.873 | 1192.139 | -65.734 KiB (-5.23%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 477.848 | 477.848 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 81282.125 | 81701.708 | +419.583 us (+0.52%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11219.584 | 11110.373 | -109.211 KiB (-0.97%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4775.730 | 4775.730 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 14601.833 | 16197.584 | +1595.751 us (+10.93%) | 9 | slower |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 346.607 | 332.436 | -14.172 KiB (-4.09%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.524 | 2.524 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 94919.125 | 96184.458 | +1265.333 us (+1.33%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 829.779 | 774.357 | -55.422 KiB (-6.68%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.556 | 2.556 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 17721.292 | 19093.667 | +1372.375 us (+7.74%) | 9 | slower |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1352.416 | 1298.314 | -54.102 KiB (-4.00%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 708.953 | 708.953 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 176574.792 | 201766.833 | +25192.041 us (+14.27%) | 9 | slower |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12956.229 | 12084.102 | -872.127 KiB (-6.73%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7088.086 | 7088.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 23541.417 | 25681.500 | +2140.083 us (+9.09%) | 9 | slower |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 516.408 | 507.689 | -8.719 KiB (-1.69%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.536 | 3.536 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 181084.333 | 184191.375 | +3107.042 us (+1.72%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 935.533 | 874.955 | -60.578 KiB (-6.48%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.567 | 3.567 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 15614.250 | 16078.166 | +463.916 us (+2.97%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1265.205 | 1208.674 | -56.531 KiB (-4.47%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 501.285 | 501.285 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 153783.958 | 159250.875 | +5466.917 us (+3.55%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12956.658 | 12084.531 | -872.127 KiB (-6.73%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5010.105 | 5010.105 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 21430.959 | 23857.458 | +2426.499 us (+11.32%) | 9 | slower |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 481.248 | 474.014 | -7.234 KiB (-1.50%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.642 | 2.642 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 162065.333 | 170986.792 | +8921.459 us (+5.50%) | 9 | slower |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 931.740 | 871.240 | -60.500 KiB (-6.49%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.673 | 2.673 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6035.667 | 6012.791 | -22.876 us (-0.38%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 471.098 | 456.371 | -14.727 KiB (-3.13%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 227.253 | 227.253 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 836.166 | 825.500 | -10.666 us (-1.28%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 70.972 | 69.370 | -1.602 KiB (-2.26%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 28.146 | 28.146 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4410.500 | 4503.000 | +92.500 us (+2.10%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 405.091 | 390.489 | -14.602 KiB (-3.60%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 186.823 | 186.823 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 668.958 | 695.459 | +26.501 us (+3.96%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 63.684 | 62.152 | -1.531 KiB (-2.40%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.200 | 23.200 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8451.917 | 8639.959 | +188.042 us (+2.22%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 594.528 | 580.786 | -13.742 KiB (-2.31%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 293.815 | 293.815 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1215.791 | 1199.083 | -16.708 us (-1.37%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 88.605 | 86.676 | -1.930 KiB (-2.18%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 36.802 | 36.802 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6664.084 | 6870.000 | +205.916 us (+3.09%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 538.793 | 524.941 | -13.852 KiB (-2.57%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 257.698 | 257.698 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 977.459 | 985.917 | +8.458 us (+0.87%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 83.323 | 81.229 | -2.094 KiB (-2.51%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.388 | 32.388 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10535.208 | 10704.250 | +169.042 us (+1.60%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 743.076 | 725.670 | -17.406 KiB (-2.34%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 384.511 | 384.511 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1548.625 | 1530.708 | -17.917 us (-1.16%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 108.657 | 105.743 | -2.914 KiB (-2.68%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 48.544 | 48.544 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8280.833 | 8473.625 | +192.792 us (+2.33%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 682.031 | 664.742 | -17.289 KiB (-2.53%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 333.909 | 333.909 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1238.041 | 1263.583 | +25.542 us (+2.06%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 102.377 | 99.369 | -3.008 KiB (-2.94%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.247 | 42.247 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 436.927 | 419.222 | -17.705 KiB (-4.05%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 298.581 | 296.780 | -1.801 KiB (-0.60%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.893 | 0.531 | -0.362 ms (-40.51%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.732 | 0.750 | +0.018 ms (+2.42%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 4.812 | 4.865 | +0.053 ms (+1.11%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 35952.632 | 39425.376 | +3472.743 roots/s (+9.66%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 6.146 | 5.332 | -0.814 ms (-13.24%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 29586.162 | 37673.056 | +8086.894 roots/s (+27.33%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 8.764 | 7.433 | -1.331 ms (-15.19%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 21610.718 | 26740.499 | +5129.781 roots/s (+23.74%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 232.728 | 220.542 | -12.186 KiB (-5.24%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 53.406 | 42.114 | -11.292 KiB (-21.14%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 82.885 | 80.071 | -2.813 KiB (-3.39%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 12.408 | 9.824 | -2.584 KiB (-20.82%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1301.722 | 1232.190 | -69.531 KiB (-5.34%) | 3 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.973 | 521.973 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 1.226 | 0.671 | -0.555 ms (-45.27%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 2.166 | 1.010 | -1.156 ms (-53.38%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 11.054 | 8.380 | -2.674 ms (-24.19%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 18563.711 | 23650.215 | +5086.504 roots/s (+27.40%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 12.880 | 9.071 | -3.809 ms (-29.57%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 15495.818 | 21891.119 | +6395.301 roots/s (+41.27%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 20.735 | 11.769 | -8.966 ms (-43.24%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 9733.762 | 16373.255 | +6639.494 roots/s (+68.21%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 709.538 | 667.780 | -41.758 KiB (-5.89%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 31.876 | 29.103 | -2.773 KiB (-8.70%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 198.792 | 188.050 | -10.742 KiB (-5.40%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.491 | 5.002 | +1.511 KiB (+43.27%) | 6 | larger |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1632.014 | 1586.529 | -45.484 KiB (-2.79%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.688 | 869.645 | -0.043 KiB (-0.00%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 1.448 | 0.841 | -0.607 ms (-41.91%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 3.307 | 2.007 | -1.300 ms (-39.31%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 24.942 | 21.958 | -2.984 ms (-11.96%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7953.683 | 9068.324 | +1114.642 roots/s (+14.01%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 27.224 | 22.824 | -4.399 ms (-16.16%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 7421.414 | 8674.924 | +1253.510 roots/s (+16.89%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 35.532 | 25.528 | -10.004 ms (-28.15%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 5578.288 | 7806.427 | +2228.138 roots/s (+39.94%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1093.716 | 1038.378 | -55.338 KiB (-5.06%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 60.242 | 56.446 | -3.796 KiB (-6.30%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 302.795 | 290.467 | -12.328 KiB (-4.07%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 6.259 | 7.666 | +1.407 KiB (+22.48%) | 6 | larger |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1346.202 | 1289.890 | -56.312 KiB (-4.18%) | 3 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 545.004 | 545.004 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 1.802 | 0.855 | -0.947 ms (-52.56%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 2.982 | 1.423 | -1.559 ms (-52.29%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 19.590 | 15.932 | -3.658 ms (-18.67%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 10473.032 | 12452.008 | +1978.976 roots/s (+18.90%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 20.046 | 15.862 | -4.184 ms (-20.87%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 10000.875 | 12625.731 | +2624.856 roots/s (+26.25%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 28.162 | 18.796 | -9.366 ms (-33.26%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 7069.521 | 10654.994 | +3585.473 roots/s (+50.72%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1140.448 | 1132.690 | -7.758 KiB (-0.68%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 40.657 | 37.985 | -2.672 KiB (-6.57%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 304.167 | 302.011 | -2.156 KiB (-0.71%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 3.812 | 5.627 | +1.815 KiB (+47.63%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 303.146 | 292.583 | -10.562 KiB (-3.48%) | 3 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.809 | 171.810 | +0.001 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.845 | 0.476 | -0.369 ms (-43.66%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 1.180 | 0.687 | -0.494 ms (-41.81%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.805 | 5.166 | -0.638 ms (-11.00%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 35458.371 | 39448.051 | +3989.680 roots/s (+11.25%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 7.576 | 5.666 | -1.910 ms (-25.22%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 26872.387 | 36063.653 | +9191.266 roots/s (+34.20%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 12.167 | 7.868 | -4.299 ms (-35.33%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 16494.561 | 24819.796 | +8325.235 roots/s (+50.47%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 183.950 | 177.027 | -6.923 KiB (-3.76%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 27.911 | 31.711 | +3.800 KiB (+13.61%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 69.903 | 68.164 | -1.739 KiB (-2.49%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 1.878 | 3.091 | +1.213 KiB (+64.59%) | 6 | larger |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 4.758 | 4.617 | -0.141 us/projection (-2.97%) | 9 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 209150.326 | 214585.079 | +5434.753 projections/s (+2.60%) | 9 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 40.973 | 35.895 | -5.078 KiB (-12.39%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 43.269 | 41.653 | -1.615 KiB (-3.73%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 489.688 | 434.312 | -55.375 B/projection (-11.31%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 165.875 | 140.000 | -25.875 B/projection (-15.60%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 5.882 | 5.825 | -0.057 us/projection (-0.97%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 168310.303 | 171696.854 | +3386.551 projections/s (+2.01%) | 9 | within noise |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 44.074 | 39.090 | -4.984 KiB (-11.31%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 57.549 | 56.621 | -0.928 KiB (-1.61%) | 3 | within noise |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 489.688 | 434.312 | -55.375 B/projection (-11.31%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 215.500 | 191.125 | -24.375 B/projection (-11.31%) | 3 | smaller |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.423 | 8.459 | +0.037 ms (+0.43%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 23638.332 | 23757.673 | +119.341 roots/s (+0.50%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.472 | 9.352 | -0.120 ms (-1.26%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 21202.163 | 21470.840 | +268.678 roots/s (+1.27%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.077 | 16.446 | +0.369 ms (+2.30%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 12408.808 | 12202.563 | -206.246 roots/s (-1.66%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 16.301 | 16.449 | +0.149 ms (+0.91%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 12217.813 | 12134.389 | -83.424 roots/s (-0.68%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 32.409 | 31.999 | -0.410 us/root (-1.27%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 98.004 | 96.629 | -1.375 KiB (-1.40%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.852 | 50.852 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 31.681 | 31.953 | +0.272 us/root (+0.86%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 101.879 | 101.980 | +0.102 KiB (+0.10%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.852 | 50.852 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 46.023 | 47.949 | +1.926 us/root (+4.18%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 145.523 | 144.445 | -1.078 KiB (-0.74%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.977 | 87.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 46.134 | 47.590 | +1.456 us/root (+3.16%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 149.555 | 149.680 | +0.125 KiB (+0.08%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.977 | 87.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 64.022 | 65.896 | +1.874 us/root (+2.93%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 215.844 | 215.234 | -0.609 KiB (-0.28%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.477 | 137.477 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 66.169 | 66.780 | +0.611 us/root (+0.92%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 218.680 | 218.836 | +0.156 KiB (+0.07%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.477 | 137.477 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 22.737 | 23.018 | +0.281 us/root (+1.24%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 61.480 | 60.105 | -1.375 KiB (-2.24%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.102 | 24.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 23.712 | 23.298 | -0.414 us/root (-1.75%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 67.355 | 67.457 | +0.102 KiB (+0.15%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.102 | 24.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 148.395 | 152.921 | +4.526 us/root (+3.05%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 622.762 | 621.332 | -1.430 KiB (-0.23%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.102 | 428.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 147.612 | 153.298 | +5.686 us/root (+3.85%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 626.293 | 626.340 | +0.047 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.102 | 428.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 56.095 | 56.958 | +0.863 us/root (+1.54%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 192.648 | 191.219 | -1.430 KiB (-0.74%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.102 | 125.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 54.724 | 55.927 | +1.203 us/root (+2.20%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 194.863 | 194.910 | +0.047 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.102 | 125.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 44.643 | 46.251 | +1.608 us/root (+3.60%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 127.688 | 126.313 | -1.375 KiB (-1.08%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.945 | 35.945 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 45.499 | 48.768 | +3.270 us/root (+7.19%) | 9 | slower |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 131.563 | 131.665 | +0.102 KiB (+0.08%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.945 | 35.945 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 54.224 | 54.724 | +0.500 us/root (+0.92%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 215.922 | 214.492 | -1.430 KiB (-0.66%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.727 | 136.727 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 53.339 | 55.294 | +1.956 us/root (+3.67%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 219.312 | 219.359 | +0.047 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.727 | 136.727 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 141.611 | 146.436 | +4.826 us/root (+3.41%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 758.492 | 757.062 | -1.430 KiB (-0.19%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.227 | 480.227 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 143.264 | 146.324 | +3.060 us/root (+2.14%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 761.883 | 761.930 | +0.047 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.227 | 480.227 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 260.709 | 240.291 | -20.418 us (-7.83%) | 9 | faster |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 32.547 | 28.539 | -4.008 KiB (-12.31%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 25.070 | 21.832 | -3.238 KiB (-12.92%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 371.000 | 348.042 | -22.958 us (-6.19%) | 9 | faster |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 44.538 | 38.534 | -6.004 KiB (-13.48%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 35.562 | 30.401 | -5.160 KiB (-14.51%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 491.917 | 454.667 | -37.250 us (-7.57%) | 9 | faster |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 55.873 | 47.896 | -7.977 KiB (-14.28%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 45.529 | 38.455 | -7.074 KiB (-15.54%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 88.875 | 83.834 | -5.041 us (-5.67%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 19.706 | 17.167 | -2.539 KiB (-12.88%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 13.073 | 10.972 | -2.102 KiB (-16.08%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 92.833 | 82.833 | -10.000 us (-10.77%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 19.611 | 17.182 | -2.430 KiB (-12.39%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 13.229 | 11.236 | -1.992 KiB (-15.06%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 87.458 | 82.833 | -4.625 us (-5.29%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 19.706 | 17.167 | -2.539 KiB (-12.88%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 13.073 | 10.972 | -2.102 KiB (-16.08%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 92.708 | 85.458 | -7.250 us (-7.82%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 19.611 | 17.182 | -2.430 KiB (-12.39%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 13.229 | 11.236 | -1.992 KiB (-15.06%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 88.042 | 80.750 | -7.292 us (-8.28%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 19.707 | 17.168 | -2.539 KiB (-12.88%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 13.074 | 10.973 | -2.102 KiB (-16.07%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 89.375 | 83.791 | -5.584 us (-6.25%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 19.612 | 17.183 | -2.430 KiB (-12.39%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 13.229 | 11.237 | -1.992 KiB (-15.06%) | 3 | smaller |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 11.625 | 2.209 | -9.416 us (-81.00%) | 9 | faster |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 15.584 | 2.708 | -12.876 us (-82.62%) | 9 | faster |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 19.875 | 3.291 | -16.584 us (-83.44%) | 9 | faster |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.closed.retainedKiB | 71.484 | 71.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.shared.retainedKiB | 50.789 | 50.789 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | small.closed.retainedKiB | 118.438 | 118.438 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | small.shared.retainedKiB | 111.070 | 111.070 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 10038.375 | 8918.459 | -1119.916 us (-11.16%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1426.754 | 1351.897 | -74.856 KiB (-5.25%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 741.773 | 741.773 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 101349.208 | 92964.000 | -8385.208 us (-8.27%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 13230.781 | 13106.237 | -124.544 KiB (-0.94%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 7416.219 | 7416.219 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 17583.708 | 18155.709 | +572.001 us (+3.25%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 185.645 | 172.350 | -13.295 KiB (-7.16%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.700 | 3.700 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 114362.625 | 106991.917 | -7370.708 us (-6.45%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 190.551 | 178.662 | -11.889 KiB (-6.24%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.731 | 3.731 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8335.084 | 7567.959 | -767.125 us (-9.20%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1256.114 | 1180.812 | -75.302 KiB (-5.99%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 487.230 | 487.230 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 83609.833 | 75964.458 | -7645.375 us (-9.14%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11470.993 | 11346.004 | -124.989 KiB (-1.09%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4869.488 | 4869.488 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 17507.792 | 15543.500 | -1964.292 us (-11.22%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 187.856 | 176.319 | -11.537 KiB (-6.14%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.571 | 2.571 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 98713.167 | 88960.125 | -9753.042 us (-9.88%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 189.763 | 178.226 | -11.537 KiB (-6.08%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.603 | 2.603 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 18504.125 | 16942.375 | -1561.750 us (-8.44%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1359.469 | 1297.487 | -61.981 KiB (-4.56%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 758.961 | 758.961 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 186914.542 | 171206.250 | -15708.292 us (-8.40%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 13713.808 | 12747.543 | -966.265 KiB (-7.05%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7588.094 | 7588.094 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 24974.000 | 24408.125 | -565.875 us (-2.27%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 285.020 | 281.568 | -3.451 KiB (-1.21%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.786 | 3.786 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 189200.791 | 175145.834 | -14054.957 us (-7.43%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 288.941 | 286.896 | -2.045 KiB (-0.71%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.817 | 3.817 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 16172.416 | 15119.875 | -1052.541 us (-6.51%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1340.985 | 1274.736 | -66.249 KiB (-4.94%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 510.668 | 510.668 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 159251.791 | 154248.416 | -5003.375 us (-3.14%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 13714.501 | 12748.236 | -966.265 KiB (-7.05%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5103.863 | 5103.863 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 22943.291 | 22584.834 | -358.457 us (-1.56%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 284.005 | 281.983 | -2.021 KiB (-0.71%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.688 | 2.688 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 169425.917 | 156319.334 | -13106.583 us (-7.74%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 285.567 | 283.546 | -2.021 KiB (-0.71%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.720 | 2.720 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6054.875 | 5600.834 | -454.041 us (-7.50%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 419.644 | 402.662 | -16.981 KiB (-4.05%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 245.097 | 245.097 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 868.958 | 788.834 | -80.124 us (-9.22%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 71.268 | 69.286 | -1.981 KiB (-2.78%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 34.177 | 34.177 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4400.750 | 4049.000 | -351.750 us (-7.99%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 377.164 | 360.378 | -16.786 KiB (-4.45%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 190.003 | 190.003 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 687.208 | 628.042 | -59.166 us (-8.61%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 63.312 | 61.471 | -1.841 KiB (-2.91%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.606 | 23.606 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8834.292 | 8133.333 | -700.959 us (-7.93%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 541.584 | 531.056 | -10.528 KiB (-1.94%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 317.237 | 317.237 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1250.042 | 1143.375 | -106.667 us (-8.53%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 87.712 | 86.559 | -1.153 KiB (-1.31%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 42.489 | 42.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6707.209 | 6235.958 | -471.251 us (-7.03%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 508.909 | 497.139 | -11.771 KiB (-2.31%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 261.722 | 261.722 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 1017.417 | 925.916 | -91.501 us (-8.99%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 82.717 | 81.329 | -1.388 KiB (-1.68%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.903 | 32.903 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10990.208 | 10217.375 | -772.833 us (-7.03%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 700.338 | 686.044 | -14.294 KiB (-2.04%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 415.769 | 415.769 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1558.458 | 1432.791 | -125.667 us (-8.06%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 107.241 | 105.635 | -1.606 KiB (-1.50%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 54.958 | 54.958 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8550.667 | 7817.875 | -732.792 us (-8.57%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 657.265 | 639.041 | -18.224 KiB (-2.77%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 339.104 | 339.104 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1286.375 | 1180.292 | -106.083 us (-8.25%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 101.388 | 99.258 | -2.130 KiB (-2.10%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.911 | 42.911 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 399.661 | 382.197 | -17.464 KiB (-4.37%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 300.279 | 295.975 | -4.305 KiB (-1.43%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.501 | 0.506 | +0.005 ms (+1.01%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.792 | 0.674 | -0.118 ms (-14.88%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 5.085 | 4.480 | -0.604 ms (-11.88%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 40010.331 | 45036.596 | +5026.265 roots/s (+12.56%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 5.653 | 4.870 | -0.783 ms (-13.85%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 35912.826 | 41049.504 | +5136.678 roots/s (+14.30%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 8.115 | 7.375 | -0.740 ms (-9.12%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 25032.072 | 27886.388 | +2854.315 roots/s (+11.40%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 229.209 | 202.710 | -26.499 KiB (-11.56%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.509 | 40.492 | -2.017 KiB (-4.74%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 79.099 | 73.856 | -5.242 KiB (-6.63%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 14.100 | 13.382 | -0.718 KiB (-5.09%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1300.178 | 1221.798 | -78.380 KiB (-6.03%) | 3 | smaller |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.383 | 531.383 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 1.258 | 0.753 | -0.505 ms (-40.12%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 2.204 | 1.071 | -1.133 ms (-51.41%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 10.854 | 7.884 | -2.971 ms (-27.37%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 18282.721 | 25686.995 | +7404.275 roots/s (+40.50%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 13.084 | 8.816 | -4.268 ms (-32.62%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 15533.377 | 23444.941 | +7911.564 roots/s (+50.93%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 21.295 | 11.476 | -9.820 ms (-46.11%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 10337.409 | 17519.463 | +7182.054 roots/s (+69.48%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 713.650 | 665.801 | -47.850 KiB (-6.70%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 34.637 | 31.615 | -3.021 KiB (-8.72%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 201.010 | 188.855 | -12.154 KiB (-6.05%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.597 | 5.107 | +1.511 KiB (+42.00%) | 6 | larger |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1683.489 | 1629.932 | -53.558 KiB (-3.18%) | 3 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.713 | 883.708 | -0.005 KiB (-0.00%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 1.699 | 0.858 | -0.842 ms (-49.52%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 3.303 | 1.895 | -1.408 ms (-42.63%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 25.480 | 20.401 | -5.079 ms (-19.93%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7703.455 | 9722.700 | +2019.245 roots/s (+26.21%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 27.272 | 21.233 | -6.039 ms (-22.14%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 7314.609 | 9319.339 | +2004.730 roots/s (+27.41%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 35.088 | 24.309 | -10.778 ms (-30.72%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 5659.583 | 8334.940 | +2675.356 roots/s (+47.27%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1127.760 | 1066.213 | -61.547 KiB (-5.46%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 54.548 | 53.855 | -0.692 KiB (-1.27%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 311.277 | 297.565 | -13.712 KiB (-4.41%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 6.226 | 7.894 | +1.668 KiB (+26.79%) | 6 | larger |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1422.533 | 1356.597 | -65.937 KiB (-4.64%) | 3 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.414 | 554.414 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 1.786 | 0.758 | -1.028 ms (-57.56%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 2.750 | 1.417 | -1.333 ms (-48.47%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 19.900 | 15.173 | -4.727 ms (-23.75%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 10658.519 | 13112.999 | +2454.480 roots/s (+23.03%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 20.787 | 14.996 | -5.791 ms (-27.86%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 9681.479 | 13444.023 | +3762.543 roots/s (+38.86%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 25.601 | 18.360 | -7.242 ms (-28.29%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 6433.083 | 10986.621 | +4553.538 roots/s (+70.78%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1154.088 | 1145.113 | -8.975 KiB (-0.78%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 43.953 | 41.064 | -2.889 KiB (-6.57%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 309.721 | 307.512 | -2.209 KiB (-0.71%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 3.948 | 5.764 | +1.815 KiB (+45.98%) | 6 | larger |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 265.734 | 253.586 | -12.148 KiB (-4.57%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 175.000 | 174.945 | -0.055 KiB (-0.03%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.804 | 0.487 | -0.318 ms (-39.50%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 1.164 | 0.620 | -0.544 ms (-46.73%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 5.929 | 4.794 | -1.135 ms (-19.14%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 33668.855 | 41491.986 | +7823.131 roots/s (+23.24%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 7.570 | 5.309 | -2.261 ms (-29.87%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 25535.583 | 36602.102 | +11066.519 roots/s (+43.34%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 12.637 | 7.871 | -4.766 ms (-37.72%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 15613.920 | 24941.416 | +9327.496 roots/s (+59.74%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 190.998 | 183.047 | -7.951 KiB (-4.16%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 30.581 | 29.996 | -0.585 KiB (-1.91%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 66.568 | 64.672 | -1.896 KiB (-2.85%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 1.944 | 3.113 | +1.169 KiB (+60.12%) | 6 | larger |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 4.858 | 4.298 | -0.561 us/projection (-11.54%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 207455.416 | 234575.692 | +27120.276 projections/s (+13.07%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.371 | 37.535 | -5.836 KiB (-13.46%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 47.646 | 45.827 | -1.818 KiB (-3.82%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 519.672 | 460.703 | -58.969 B/projection (-11.35%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 174.266 | 139.859 | -34.406 B/projection (-19.74%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 6.230 | 5.531 | -0.700 us/projection (-11.23%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 160384.128 | 188443.106 | +28058.977 projections/s (+17.49%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 46.512 | 40.730 | -5.781 KiB (-12.43%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 63.027 | 61.998 | -1.029 KiB (-1.63%) | 3 | within noise |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 519.672 | 460.703 | -58.969 B/projection (-11.35%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 224.516 | 190.984 | -33.531 B/projection (-14.93%) | 3 | smaller |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.636 | 7.837 | -0.799 ms (-9.26%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 23033.957 | 25432.887 | +2398.930 roots/s (+10.41%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.700 | 8.665 | -1.035 ms (-10.67%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20615.987 | 23142.234 | +2526.247 roots/s (+12.25%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.610 | 15.247 | -1.363 ms (-8.20%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 12053.003 | 13012.891 | +959.888 roots/s (+7.96%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 16.970 | 15.142 | -1.828 ms (-10.77%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 11915.223 | 13107.341 | +1192.118 roots/s (+10.00%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-boolean | columns.elapsedUsPerRoot | 109.316 | 103.258 | -6.059 us/root (-5.54%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-boolean | columns.peakKiB | 443.915 | 442.059 | -1.856 KiB (-0.42%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.retainedKiB | 162.484 | 162.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.elapsedUsPerRoot | 109.526 | 103.043 | -6.483 us/root (-5.92%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-boolean | document.peakKiB | 447.438 | 447.270 | -0.169 KiB (-0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.retainedKiB | 162.484 | 162.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.elapsedUsPerRoot | 396.335 | 354.790 | -41.544 us/root (-10.48%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-bytes | columns.peakKiB | 952.168 | 952.093 | -0.075 KiB (-0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.retainedKiB | 313.047 | 313.047 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.elapsedUsPerRoot | 398.477 | 356.697 | -41.780 us/root (-10.48%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-bytes | document.peakKiB | 955.738 | 955.663 | -0.075 KiB (-0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.retainedKiB | 313.047 | 313.047 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.elapsedUsPerRoot | 421.161 | 390.270 | -30.892 us/root (-7.33%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-date | columns.peakKiB | 770.540 | 770.371 | -0.169 KiB (-0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.retainedKiB | 192.965 | 192.965 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.elapsedUsPerRoot | 466.042 | 383.844 | -82.198 us/root (-17.64%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-date | document.peakKiB | 774.337 | 774.168 | -0.169 KiB (-0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.retainedKiB | 192.965 | 192.965 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.elapsedUsPerRoot | 919.889 | 847.639 | -72.250 us/root (-7.85%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-decimal | columns.peakKiB | 1298.812 | 1298.807 | -0.005 KiB (-0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.retainedKiB | 271.797 | 271.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.elapsedUsPerRoot | 921.395 | 851.977 | -69.418 us/root (-7.53%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-decimal | document.peakKiB | 1302.640 | 1302.635 | -0.005 KiB (-0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.retainedKiB | 271.797 | 271.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.elapsedUsPerRoot | 856.643 | 740.081 | -116.562 us/root (-13.61%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float32 | columns.peakKiB | 689.256 | 689.181 | -0.075 KiB (-0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.elapsedUsPerRoot | 798.594 | 735.777 | -62.816 us/root (-7.87%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float32 | document.peakKiB | 692.826 | 692.751 | -0.075 KiB (-0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.elapsedUsPerRoot | 315.036 | 281.051 | -33.986 us/root (-10.79%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float64 | columns.peakKiB | 655.350 | 655.274 | -0.075 KiB (-0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.elapsedUsPerRoot | 316.471 | 279.565 | -36.906 us/root (-11.66%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float64 | document.peakKiB | 658.920 | 658.845 | -0.075 KiB (-0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.elapsedUsPerRoot | 153.753 | 143.994 | -9.759 us/root (-6.35%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int32 | columns.peakKiB | 636.063 | 634.207 | -1.856 KiB (-0.29%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.retainedKiB | 354.480 | 354.480 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.elapsedUsPerRoot | 154.862 | 144.932 | -9.930 us/root (-6.41%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int32 | document.peakKiB | 639.587 | 639.418 | -0.169 KiB (-0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.retainedKiB | 354.480 | 354.480 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.elapsedUsPerRoot | 159.978 | 153.419 | -6.559 us/root (-4.10%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.peakKiB | 648.032 | 646.176 | -1.856 KiB (-0.29%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.retainedKiB | 366.484 | 366.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.elapsedUsPerRoot | 161.039 | 150.486 | -10.553 us/root (-6.55%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int64 | document.peakKiB | 651.556 | 651.387 | -0.169 KiB (-0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.retainedKiB | 366.484 | 366.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.elapsedUsPerRoot | 560.288 | 508.230 | -52.057 us/root (-9.29%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-time | columns.peakKiB | 827.646 | 827.571 | -0.075 KiB (-0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.retainedKiB | 277.984 | 277.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.elapsedUsPerRoot | 560.087 | 509.371 | -50.716 us/root (-9.06%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-time | document.peakKiB | 831.217 | 831.142 | -0.075 KiB (-0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.retainedKiB | 277.984 | 277.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.elapsedUsPerRoot | 831.596 | 750.003 | -81.594 us/root (-9.81%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.peakKiB | 954.629 | 934.302 | -20.327 KiB (-2.13%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.retainedKiB | 302.881 | 302.832 | -0.049 KiB (-0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.elapsedUsPerRoot | 837.633 | 750.294 | -87.339 us/root (-10.43%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-timestamp | document.peakKiB | 957.174 | 952.618 | -4.556 KiB (-0.48%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.retainedKiB | 302.979 | 303.223 | +0.244 KiB (+0.08%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.elapsedUsPerRoot | 568.125 | 513.401 | -54.724 us/root (-9.63%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-uuid | columns.peakKiB | 1277.356 | 1277.242 | -0.114 KiB (-0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.retainedKiB | 321.297 | 321.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.elapsedUsPerRoot | 584.577 | 514.975 | -69.602 us/root (-11.91%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-uuid | document.peakKiB | 1281.185 | 1281.070 | -0.114 KiB (-0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.retainedKiB | 321.297 | 321.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 31.801 | 29.052 | -2.749 us/root (-8.64%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 95.653 | 95.539 | -0.114 KiB (-0.12%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.109 | 51.109 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 32.689 | 29.730 | -2.958 us/root (-9.05%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 99.364 | 99.250 | -0.114 KiB (-0.11%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.109 | 51.109 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 47.227 | 42.129 | -5.098 us/root (-10.79%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 145.800 | 145.752 | -0.048 KiB (-0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.234 | 88.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 47.710 | 42.582 | -5.128 us/root (-10.75%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 149.038 | 149.158 | +0.120 KiB (+0.08%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.234 | 88.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 67.020 | 61.552 | -5.467 us/root (-8.16%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 220.546 | 220.354 | -0.192 KiB (-0.09%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.734 | 137.734 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 68.369 | 61.171 | -7.198 us/root (-10.53%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 223.866 | 224.174 | +0.308 KiB (+0.14%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.734 | 137.734 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 23.216 | 20.629 | -2.587 us/root (-11.14%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 60.078 | 58.370 | -1.708 KiB (-2.84%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.359 | 24.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 23.648 | 21.906 | -1.742 us/root (-7.37%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 65.938 | 65.917 | -0.021 KiB (-0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.359 | 24.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 153.488 | 141.066 | -12.422 us/root (-8.09%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 626.806 | 624.949 | -1.856 KiB (-0.30%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.359 | 428.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 155.052 | 140.263 | -14.789 us/root (-9.54%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 630.091 | 629.922 | -0.169 KiB (-0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.359 | 428.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 56.141 | 52.771 | -3.370 us/root (-6.00%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 195.532 | 193.785 | -1.747 KiB (-0.89%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.359 | 125.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 56.773 | 52.340 | -4.434 us/root (-7.81%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 198.052 | 197.992 | -0.060 KiB (-0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.359 | 125.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 47.689 | 46.595 | -1.094 us/root (-2.29%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 125.541 | 125.427 | -0.114 KiB (-0.09%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.203 | 36.203 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 48.272 | 45.711 | -2.561 us/root (-5.31%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 129.252 | 129.138 | -0.114 KiB (-0.09%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.203 | 36.203 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 55.055 | 50.191 | -4.863 us/root (-8.83%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 219.196 | 217.340 | -1.856 KiB (-0.85%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.984 | 136.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 55.411 | 51.082 | -4.329 us/root (-7.81%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 222.603 | 222.434 | -0.169 KiB (-0.08%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.984 | 136.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 144.081 | 134.483 | -9.598 us/root (-6.66%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 761.915 | 760.059 | -1.856 KiB (-0.24%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.484 | 480.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 145.944 | 135.000 | -10.944 us/root (-7.50%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 765.321 | 765.152 | -0.169 KiB (-0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.484 | 480.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 254.625 | 226.917 | -27.708 us (-10.88%) | 9 | faster |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 33.055 | 28.824 | -4.230 KiB (-12.80%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 26.398 | 22.754 | -3.645 KiB (-13.81%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 379.333 | 327.500 | -51.833 us (-13.66%) | 9 | faster |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 45.179 | 38.890 | -6.289 KiB (-13.92%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 37.507 | 31.702 | -5.805 KiB (-15.48%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 499.791 | 433.000 | -66.791 us (-13.36%) | 9 | faster |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 56.186 | 47.736 | -8.449 KiB (-15.04%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 48.092 | 40.127 | -7.965 KiB (-16.56%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 91.042 | 77.042 | -14.000 us (-15.38%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 20.060 | 17.204 | -2.855 KiB (-14.23%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.286 | 11.880 | -2.406 KiB (-16.84%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 93.167 | 77.125 | -16.042 us (-17.22%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 20.082 | 17.352 | -2.730 KiB (-13.60%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 14.449 | 12.168 | -2.281 KiB (-15.79%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 91.083 | 77.167 | -13.916 us (-15.28%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 20.060 | 17.204 | -2.855 KiB (-14.23%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.286 | 11.880 | -2.406 KiB (-16.84%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 92.041 | 78.958 | -13.083 us (-14.21%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 20.082 | 17.352 | -2.730 KiB (-13.60%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 14.449 | 12.168 | -2.281 KiB (-15.79%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 91.500 | 74.834 | -16.666 us (-18.21%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 20.061 | 17.205 | -2.855 KiB (-14.23%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.287 | 11.881 | -2.406 KiB (-16.84%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 93.500 | 80.459 | -13.041 us (-13.95%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 20.083 | 17.353 | -2.730 KiB (-13.60%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 14.450 | 12.169 | -2.281 KiB (-15.79%) | 3 | smaller |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 15.459 | 1.917 | -13.542 us (-87.60%) | 9 | faster |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 21.250 | 2.292 | -18.958 us (-89.21%) | 9 | faster |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 27.291 | 2.750 | -24.541 us (-89.92%) | 9 | faster |
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
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 153.000 | 168.292 | +15.292 us/row (+9.99%) | 9 | slower |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 896.000 | 848.000 | -48.000 B/row (-5.36%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 8962.000 | 8594.000 | -368.000 B/row (-4.11%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 163.875 | 169.125 | +5.250 us/row (+3.20%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 896.000 | 848.000 | -48.000 B/row (-5.36%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 9778.000 | 9506.000 | -272.000 B/row (-2.78%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 194.541 | 209.416 | +14.875 us/row (+7.65%) | 9 | slower |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 896.000 | 848.000 | -48.000 B/row (-5.36%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 7052.000 | 6967.000 | -85.000 B/row (-1.21%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 174.750 | 184.375 | +9.625 us/row (+5.51%) | 9 | slower |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 896.000 | 848.000 | -48.000 B/row (-5.36%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 7865.000 | 7623.000 | -242.000 B/row (-3.08%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 208.125 | 224.875 | +16.750 us/row (+8.05%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1176.000 | 1128.000 | -48.000 B/row (-4.08%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 11390.000 | 11357.000 | -33.000 B/row (-0.29%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 194.208 | 209.458 | +15.250 us/row (+7.85%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1176.000 | 1128.000 | -48.000 B/row (-4.08%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 12494.000 | 12350.000 | -144.000 B/row (-1.15%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 422.042 | 444.042 | +22.000 us/row (+5.21%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2296.000 | 2248.000 | -48.000 B/row (-2.09%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 19673.000 | 19673.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 332.250 | 350.458 | +18.208 us/row (+5.48%) | 9 | slower |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2296.000 | 2248.000 | -48.000 B/row (-2.09%) | 1 | within noise |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23034.000 | 22890.000 | -144.000 B/row (-0.63%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 254.875 | 282.250 | +27.375 us/row (+10.74%) | 9 | slower |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 1624.000 | 1624.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 14728.000 | 13615.000 | -1113.000 B/row (-7.56%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 249.958 | 268.333 | +18.375 us/row (+7.35%) | 9 | slower |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 1656.000 | 1656.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15204.000 | 14275.000 | -929.000 B/row (-6.11%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 249.166 | 275.708 | +26.542 us/row (+10.65%) | 9 | slower |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 1574.000 | 1624.000 | +50.000 B/row (+3.18%) | 1 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15153.000 | 14617.000 | -536.000 B/row (-3.54%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 241.375 | 264.417 | +23.042 us/row (+9.55%) | 9 | slower |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 1656.000 | 1656.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 15573.000 | 15037.000 | -536.000 B/row (-3.44%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | elapsedUs | 438.334 | 439.041 | +0.707 us/row (+0.16%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.columns.wire | transientBytes | 23328.000 | 19807.000 | -3521.000 B/row (-15.09%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | elapsedUs | 429.125 | 425.500 | -3.625 us/row (-0.84%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-patch.document.wire | transientBytes | 24345.000 | 20801.000 | -3544.000 B/row (-14.56%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | elapsedUs | 459.417 | 463.500 | +4.083 us/row (+0.89%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | retainedBytes | 2040.000 | 2040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.typed | transientBytes | 23296.000 | 19775.000 | -3521.000 B/row (-15.11%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | elapsedUs | 458.667 | 450.250 | -8.417 us/row (-1.84%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.columns.wire | transientBytes | 23328.000 | 19807.000 | -3521.000 B/row (-15.09%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | elapsedUs | 453.750 | 440.583 | -13.167 us/row (-2.90%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | retainedBytes | 2040.000 | 2040.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.typed | transientBytes | 24313.000 | 20769.000 | -3544.000 B/row (-14.58%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | elapsedUs | 433.208 | 433.208 | +0.000 us/row (+0.00%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | bitemporal.target-replace.document.wire | transientBytes | 24345.000 | 20801.000 | -3544.000 B/row (-14.56%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 115.834 | 120.958 | +5.124 us/row (+4.42%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1600.000 | 1544.000 | -56.000 B/row (-3.50%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 8812.000 | 7860.000 | -952.000 B/row (-10.80%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 114.209 | 116.750 | +2.541 us/row (+2.22%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1600.000 | 1544.000 | -56.000 B/row (-3.50%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 9084.000 | 8268.000 | -816.000 B/row (-8.98%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 152.542 | 155.042 | +2.500 us/row (+1.64%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2272.000 | 2216.000 | -56.000 B/row (-2.46%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10573.000 | 9621.000 | -952.000 B/row (-9.00%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 151.459 | 155.833 | +4.374 us/row (+2.89%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2272.000 | 2216.000 | -56.000 B/row (-2.46%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 10729.000 | 9913.000 | -816.000 B/row (-7.61%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 200.917 | 202.417 | +1.500 us/row (+0.75%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3168.000 | 3112.000 | -56.000 B/row (-1.77%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 13866.000 | 12914.000 | -952.000 B/row (-6.87%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 197.792 | 199.500 | +1.708 us/row (+0.86%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3168.000 | 3112.000 | -56.000 B/row (-1.77%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 13952.000 | 13024.000 | -928.000 B/row (-6.65%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 92.917 | 94.875 | +1.958 us/row (+2.11%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1096.000 | 1040.000 | -56.000 B/row (-5.11%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7657.000 | 6825.000 | -832.000 B/row (-10.87%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 90.250 | 94.750 | +4.500 us/row (+4.99%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1096.000 | 1040.000 | -56.000 B/row (-5.11%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 7679.000 | 6983.000 | -696.000 B/row (-9.06%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 423.625 | 427.667 | +4.042 us/row (+0.95%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8560.000 | 8504.000 | -56.000 B/row (-0.65%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27608.000 | 26784.000 | -824.000 B/row (-2.98%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 419.333 | 430.042 | +10.709 us/row (+2.55%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8560.000 | 8504.000 | -56.000 B/row (-0.65%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 27771.000 | 27083.000 | -688.000 B/row (-2.48%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 177.167 | 183.334 | +6.167 us/row (+3.48%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 2992.000 | 2936.000 | -56.000 B/row (-1.87%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 12152.000 | 11328.000 | -824.000 B/row (-6.78%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 179.875 | 181.042 | +1.167 us/row (+0.65%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 2992.000 | 2936.000 | -56.000 B/row (-1.87%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 12451.000 | 11660.000 | -791.000 B/row (-6.35%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 159.875 | 161.666 | +1.791 us/row (+1.12%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1600.000 | 1544.000 | -56.000 B/row (-3.50%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8582.000 | 7673.000 | -909.000 B/row (-10.59%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 185.542 | 163.209 | -22.333 us/row (-12.04%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1600.000 | 1544.000 | -56.000 B/row (-3.50%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 8851.000 | 8065.000 | -786.000 B/row (-8.88%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 196.041 | 201.041 | +5.000 us/row (+2.55%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2440.000 | 2384.000 | -56.000 B/row (-2.30%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11592.000 | 10855.000 | -737.000 B/row (-6.36%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 194.916 | 205.334 | +10.418 us/row (+5.34%) | 9 | slower |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2440.000 | 2384.000 | -56.000 B/row (-2.30%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 11872.000 | 11304.000 | -568.000 B/row (-4.78%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 543.375 | 529.292 | -14.083 us/row (-2.59%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5800.000 | 5744.000 | -56.000 B/row (-0.97%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23799.000 | 23095.000 | -704.000 B/row (-2.96%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 515.834 | 527.792 | +11.958 us/row (+2.32%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5800.000 | 5744.000 | -56.000 B/row (-0.97%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 25216.000 | 24648.000 | -568.000 B/row (-2.25%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 120.458 | 121.958 | +1.500 us/row (+1.25%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 1880.000 | 1832.000 | -48.000 B/row (-2.55%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 7955.000 | 7277.000 | -678.000 B/row (-8.52%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 108.166 | 116.292 | +8.126 us/row (+7.51%) | 9 | slower |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 1912.000 | 1864.000 | -48.000 B/row (-2.51%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 8579.000 | 8141.000 | -438.000 B/row (-5.11%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 127.667 | 136.958 | +9.291 us/row (+7.28%) | 9 | slower |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 1880.000 | 1832.000 | -48.000 B/row (-2.55%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 8743.000 | 8201.000 | -542.000 B/row (-6.20%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 115.834 | 122.333 | +6.499 us/row (+5.61%) | 9 | slower |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 1912.000 | 1864.000 | -48.000 B/row (-2.51%) | 1 | within noise |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 9367.000 | 9065.000 | -302.000 B/row (-3.22%) | 9 | smaller |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.columns.wire | elapsedUs | 194.125 | 193.459 | -0.666 us/row (-0.34%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-patch.columns.wire | retainedBytes | 2480.000 | 2432.000 | -48.000 B/row (-1.94%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-patch.columns.wire | transientBytes | 14607.000 | 12752.000 | -1855.000 B/row (-12.70%) | 9 | smaller |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-patch.document.wire | elapsedUs | 219.625 | 223.584 | +3.959 us/row (+1.80%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-patch.document.wire | retainedBytes | 2480.000 | 2432.000 | -48.000 B/row (-1.94%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-patch.document.wire | transientBytes | 16723.000 | 14827.000 | -1896.000 B/row (-11.34%) | 9 | smaller |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.typed | elapsedUs | 209.375 | 198.500 | -10.875 us/row (-5.19%) | 9 | faster |
| 3.13 | keyed-write | plain.target-replace.columns.typed | retainedBytes | 2448.000 | 2400.000 | -48.000 B/row (-1.96%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-replace.columns.typed | transientBytes | 14455.000 | 12680.000 | -1775.000 B/row (-12.28%) | 9 | smaller |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.columns.wire | elapsedUs | 196.833 | 185.542 | -11.291 us/row (-5.74%) | 9 | faster |
| 3.13 | keyed-write | plain.target-replace.columns.wire | retainedBytes | 2480.000 | 2432.000 | -48.000 B/row (-1.94%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-replace.columns.wire | transientBytes | 14602.000 | 12748.000 | -1854.000 B/row (-12.70%) | 9 | smaller |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.typed | elapsedUs | 236.000 | 229.916 | -6.084 us/row (-2.58%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-replace.document.typed | retainedBytes | 2448.000 | 2400.000 | -48.000 B/row (-1.96%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-replace.document.typed | transientBytes | 16572.000 | 14756.000 | -1816.000 B/row (-10.96%) | 9 | smaller |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.target-replace.document.wire | elapsedUs | 217.958 | 218.666 | +0.708 us/row (+0.32%) | 9 | within noise |
| 3.13 | keyed-write | plain.target-replace.document.wire | retainedBytes | 2480.000 | 2432.000 | -48.000 B/row (-1.94%) | 1 | within noise |
| 3.13 | keyed-write | plain.target-replace.document.wire | transientBytes | 16718.000 | 14823.000 | -1895.000 B/row (-11.34%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 161.417 | 174.083 | +12.666 us/row (+7.85%) | 9 | slower |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 1624.000 | 1576.000 | -48.000 B/row (-2.96%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 9729.000 | 9859.000 | +130.000 B/row (+1.34%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 152.916 | 166.750 | +13.834 us/row (+9.05%) | 9 | slower |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 1656.000 | 1608.000 | -48.000 B/row (-2.90%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 10221.000 | 10463.000 | +242.000 B/row (+2.37%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 177.542 | 186.250 | +8.708 us/row (+4.90%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 1624.000 | 1576.000 | -48.000 B/row (-2.96%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 11220.000 | 10996.000 | -224.000 B/row (-2.00%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 161.792 | 177.750 | +15.958 us/row (+9.86%) | 9 | slower |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 1656.000 | 1608.000 | -48.000 B/row (-2.90%) | 1 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 11416.000 | 11360.000 | -56.000 B/row (-0.49%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 121.542 | 122.708 | +1.166 us/row (+0.96%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1824.000 | 1768.000 | -56.000 B/row (-3.07%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 10486.000 | 9739.000 | -747.000 B/row (-7.12%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 121.042 | 121.458 | +0.416 us/row (+0.34%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2016.000 | 1960.000 | -56.000 B/row (-2.78%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 10814.000 | 10099.000 | -715.000 B/row (-6.61%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 118.583 | 119.375 | +0.792 us/row (+0.67%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 1824.000 | 1768.000 | -56.000 B/row (-3.07%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 10510.000 | 9518.000 | -992.000 B/row (-9.44%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 119.083 | 121.833 | +2.750 us/row (+2.31%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 2016.000 | 1960.000 | -56.000 B/row (-2.78%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 10718.000 | 9918.000 | -800.000 B/row (-7.46%) | 9 | smaller |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | elapsedUs | 319.709 | 309.833 | -9.876 us/row (-3.09%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | retainedBytes | 2072.000 | 2024.000 | -48.000 B/row (-2.32%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-patch.columns.wire | transientBytes | 20874.000 | 18031.000 | -2843.000 B/row (-13.62%) | 9 | smaller |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-patch.document.wire | elapsedUs | 315.583 | 318.125 | +2.542 us/row (+0.81%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-patch.document.wire | retainedBytes | 2072.000 | 2024.000 | -48.000 B/row (-2.32%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-patch.document.wire | transientBytes | 21301.000 | 18632.000 | -2669.000 B/row (-12.53%) | 9 | smaller |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | elapsedUs | 340.250 | 326.500 | -13.750 us/row (-4.04%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | retainedBytes | 2040.000 | 1992.000 | -48.000 B/row (-2.35%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.typed | transientBytes | 20842.000 | 17999.000 | -2843.000 B/row (-13.64%) | 9 | smaller |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | elapsedUs | 309.250 | 307.375 | -1.875 us/row (-0.61%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | retainedBytes | 2072.000 | 2024.000 | -48.000 B/row (-2.32%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.columns.wire | transientBytes | 20874.000 | 18031.000 | -2843.000 B/row (-13.62%) | 9 | smaller |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.typed | elapsedUs | 337.750 | 333.291 | -4.459 us/row (-1.32%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.typed | retainedBytes | 2040.000 | 1992.000 | -48.000 B/row (-2.35%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.typed | transientBytes | 21269.000 | 18600.000 | -2669.000 B/row (-12.55%) | 9 | smaller |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.target-replace.document.wire | elapsedUs | 323.542 | 324.542 | +1.000 us/row (+0.31%) | 9 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.wire | retainedBytes | 2072.000 | 2024.000 | -48.000 B/row (-2.32%) | 1 | within noise |
| 3.13 | keyed-write | txtime.target-replace.document.wire | transientBytes | 21301.000 | 18632.000 | -2669.000 B/row (-12.53%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 31.333 | 31.417 | +0.084 us/row (+0.27%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 3754.000 | 3642.000 | -112.000 B/row (-2.98%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 26.000 | 26.167 | +0.167 us/row (+0.64%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 3406.000 | 3590.000 | +184.000 B/row (+5.40%) | 9 | larger |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 31.292 | 32.875 | +1.583 us/row (+5.06%) | 9 | slower |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 3756.000 | 3644.000 | -112.000 B/row (-2.98%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 25.791 | 26.042 | +0.251 us/row (+0.97%) | 9 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 3409.000 | 3593.000 | +184.000 B/row (+5.40%) | 9 | larger |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3350.250 | 3329.833 | -20.417 us (-0.61%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | retainedBytes | 426856.000 | 427360.000 | +504.000 B (+0.12%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 438984.000 | 439696.000 | +712.000 B (+0.16%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | 304.375 | 309.000 | +4.625 us (+1.52%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | 23552.000 | 24056.000 | +504.000 B (+2.14%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared.family | transientBytes | 27616.000 | 28416.000 | +800.000 B (+2.90%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 22.548 | 20.568 | -1.979 us/row (-8.78%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 918.250 | 915.438 | -2.812 B/row (-0.31%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 2114.422 | 1822.250 | -292.172 B/row (-13.82%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 23.594 | 20.944 | -2.651 us/row (-11.23%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1919.750 | 1916.938 | -2.812 B/row (-0.15%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2481.391 | 2222.328 | -259.062 B/row (-10.44%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 26.833 | 23.820 | -3.013 us/row (-11.23%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1058.000 | 1046.750 | -11.250 B/row (-1.06%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2540.562 | 2266.375 | -274.188 B/row (-10.79%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 27.749 | 24.889 | -2.859 us/row (-10.30%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2064.000 | 2052.750 | -11.250 B/row (-0.55%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 3000.938 | 2588.688 | -412.250 B/row (-13.74%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 43.646 | 40.307 | -3.339 us/row (-7.65%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1625.000 | 1580.000 | -45.000 B/row (-2.77%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 4419.250 | 3734.500 | -684.750 B/row (-15.49%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 44.599 | 41.177 | -3.422 us/row (-7.67%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2649.000 | 2604.000 | -45.000 B/row (-1.70%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 4655.750 | 3966.750 | -689.000 B/row (-14.80%) | 9 | smaller |
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
| 3.13 | wire-insert-response | response.insert.family.wire | elapsedUs | 62.667 | 61.000 | -1.667 us/row (-2.66%) | 9 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | retainedBytes | 8392.000 | 8176.000 | -216.000 B/row (-2.57%) | 1 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | transientBytes | 7712.000 | 7696.000 | -16.000 B/row (-0.21%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 180.875 | 182.083 | +1.208 us/row (+0.67%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 904.000 | 856.000 | -48.000 B/row (-5.31%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 9346.000 | 9306.000 | -40.000 B/row (-0.43%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 180.708 | 184.083 | +3.375 us/row (+1.87%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 904.000 | 856.000 | -48.000 B/row (-5.31%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 10362.000 | 10282.000 | -80.000 B/row (-0.77%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 221.583 | 218.875 | -2.708 us/row (-1.22%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 904.000 | 856.000 | -48.000 B/row (-5.31%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 7532.000 | 7631.000 | +99.000 B/row (+1.31%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 207.167 | 192.666 | -14.501 us/row (-7.00%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 904.000 | 856.000 | -48.000 B/row (-5.31%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 8457.000 | 8415.000 | -42.000 B/row (-0.50%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 236.792 | 236.708 | -0.084 us/row (-0.04%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1184.000 | 1136.000 | -48.000 B/row (-4.05%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 11958.000 | 12093.000 | +135.000 B/row (+1.13%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 219.958 | 221.542 | +1.584 us/row (+0.72%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1184.000 | 1136.000 | -48.000 B/row (-4.05%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13142.000 | 13214.000 | +72.000 B/row (+0.55%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 448.959 | 420.791 | -28.168 us/row (-6.27%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2304.000 | 2256.000 | -48.000 B/row (-2.08%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 20153.000 | 20353.000 | +200.000 B/row (+0.99%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 368.833 | 347.833 | -21.000 us/row (-5.69%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2304.000 | 2256.000 | -48.000 B/row (-2.08%) | 1 | within noise |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23626.000 | 23698.000 | +72.000 B/row (+0.30%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 288.500 | 296.208 | +7.708 us/row (+2.67%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 1640.000 | 1640.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 14648.000 | 14135.000 | -513.000 B/row (-3.50%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 284.959 | 279.250 | -5.709 us/row (-2.00%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 1672.000 | 1672.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15288.000 | 15015.000 | -273.000 B/row (-1.79%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 285.375 | 294.250 | +8.875 us/row (+3.11%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 1640.000 | 1640.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15201.000 | 15185.000 | -16.000 B/row (-0.11%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 271.583 | 282.542 | +10.959 us/row (+4.04%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 1672.000 | 1672.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 15849.000 | 15825.000 | -24.000 B/row (-0.15%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | elapsedUs | 477.208 | 453.666 | -23.542 us/row (-4.93%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.columns.wire | transientBytes | 22818.000 | 19507.000 | -3311.000 B/row (-14.51%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | elapsedUs | 483.875 | 462.458 | -21.417 us/row (-4.43%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-patch.document.wire | transientBytes | 23765.000 | 20973.000 | -2792.000 B/row (-11.75%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | elapsedUs | 505.667 | 463.334 | -42.333 us/row (-8.37%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.typed | transientBytes | 22726.000 | 19479.000 | -3247.000 B/row (-14.29%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | elapsedUs | 485.875 | 449.583 | -36.292 us/row (-7.47%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.columns.wire | transientBytes | 22818.000 | 19507.000 | -3311.000 B/row (-14.51%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | elapsedUs | 490.416 | 447.125 | -43.291 us/row (-8.83%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | retainedBytes | 2072.000 | 2072.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.typed | transientBytes | 23737.000 | 20945.000 | -2792.000 B/row (-11.76%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | elapsedUs | 478.084 | 453.416 | -24.668 us/row (-5.16%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | retainedBytes | 2104.000 | 2104.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | bitemporal.target-replace.document.wire | transientBytes | 23765.000 | 20973.000 | -2792.000 B/row (-11.75%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 138.125 | 131.667 | -6.458 us/row (-4.68%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1616.000 | 1560.000 | -56.000 B/row (-3.47%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 9436.000 | 8508.000 | -928.000 B/row (-9.83%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 136.292 | 127.125 | -9.167 us/row (-6.73%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1616.000 | 1560.000 | -56.000 B/row (-3.47%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 9836.000 | 8980.000 | -856.000 B/row (-8.70%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 175.500 | 161.375 | -14.125 us/row (-8.05%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2288.000 | 2232.000 | -56.000 B/row (-2.45%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 11293.000 | 10365.000 | -928.000 B/row (-8.22%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 172.958 | 159.459 | -13.499 us/row (-7.80%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2288.000 | 2232.000 | -56.000 B/row (-2.45%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 11577.000 | 10729.000 | -848.000 B/row (-7.32%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 223.084 | 208.542 | -14.542 us/row (-6.52%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3184.000 | 3128.000 | -56.000 B/row (-1.76%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 14634.000 | 13778.000 | -856.000 B/row (-5.85%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 224.125 | 209.292 | -14.833 us/row (-6.62%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3184.000 | 3128.000 | -56.000 B/row (-1.76%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 14744.000 | 13936.000 | -808.000 B/row (-5.48%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 113.958 | 106.917 | -7.041 us/row (-6.18%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1104.000 | 1048.000 | -56.000 B/row (-5.07%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 8217.000 | 7457.000 | -760.000 B/row (-9.25%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 113.917 | 103.500 | -10.417 us/row (-9.14%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1104.000 | 1048.000 | -56.000 B/row (-5.07%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 8367.000 | 7631.000 | -736.000 B/row (-8.80%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 452.458 | 408.416 | -44.042 us/row (-9.73%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8576.000 | 8520.000 | -56.000 B/row (-0.65%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 28200.000 | 27424.000 | -776.000 B/row (-2.75%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 452.625 | 413.542 | -39.083 us/row (-8.63%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8576.000 | 8520.000 | -56.000 B/row (-0.65%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 28491.000 | 27787.000 | -704.000 B/row (-2.47%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 203.792 | 185.458 | -18.334 us/row (-9.00%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3008.000 | 2952.000 | -56.000 B/row (-1.86%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 12744.000 | 11968.000 | -776.000 B/row (-6.09%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 200.833 | 185.209 | -15.624 us/row (-7.78%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3008.000 | 2952.000 | -56.000 B/row (-1.86%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 13203.000 | 12380.000 | -823.000 B/row (-6.23%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 187.250 | 167.542 | -19.708 us/row (-10.52%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1616.000 | 1560.000 | -56.000 B/row (-3.47%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 9238.000 | 8361.000 | -877.000 B/row (-9.49%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 186.459 | 173.500 | -12.959 us/row (-6.95%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1616.000 | 1560.000 | -56.000 B/row (-3.47%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 9635.000 | 8817.000 | -818.000 B/row (-8.49%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 220.875 | 205.417 | -15.458 us/row (-7.00%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2456.000 | 2400.000 | -56.000 B/row (-2.28%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 12280.000 | 11559.000 | -721.000 B/row (-5.87%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 220.583 | 201.667 | -18.916 us/row (-8.58%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2456.000 | 2400.000 | -56.000 B/row (-2.28%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 12656.000 | 12072.000 | -584.000 B/row (-4.61%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 554.584 | 497.417 | -57.167 us/row (-10.31%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 24455.000 | 23799.000 | -656.000 B/row (-2.68%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 561.959 | 496.875 | -65.084 us/row (-11.58%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 26000.000 | 25416.000 | -584.000 B/row (-2.25%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | elapsedUs | 511.750 | 449.834 | -61.916 us/row (-12.10%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | transientBytes | 21421.000 | 20765.000 | -656.000 B/row (-3.06%) | 9 | smaller |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | elapsedUs | 559.291 | 506.833 | -52.458 us/row (-9.38%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.columns.wire | retainedBytes | 6024.000 | 5968.000 | -56.000 B/row (-0.93%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | transientBytes | 21629.000 | 20973.000 | -656.000 B/row (-3.03%) | 9 | smaller |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | elapsedUs | 493.917 | 447.541 | -46.376 us/row (-9.39%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | transientBytes | 22366.000 | 21782.000 | -584.000 B/row (-2.61%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | elapsedUs | 553.333 | 498.459 | -54.874 us/row (-9.92%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.document.wire | retainedBytes | 6024.000 | 5968.000 | -56.000 B/row (-0.93%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | transientBytes | 22574.000 | 21990.000 | -584.000 B/row (-2.59%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | elapsedUs | 573.708 | 506.625 | -67.083 us/row (-11.69%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | transientBytes | 44867.000 | 44211.000 | -656.000 B/row (-1.46%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | elapsedUs | 739.375 | 654.042 | -85.333 us/row (-11.54%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.columns.wire | retainedBytes | 15432.000 | 15376.000 | -56.000 B/row (-0.36%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | transientBytes | 54483.000 | 53827.000 | -656.000 B/row (-1.20%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | elapsedUs | 570.625 | 505.875 | -64.750 us/row (-11.35%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | transientBytes | 47692.000 | 47108.000 | -584.000 B/row (-1.22%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | elapsedUs | 734.250 | 653.000 | -81.250 us/row (-11.07%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.document.wire | retainedBytes | 15432.000 | 15376.000 | -56.000 B/row (-0.36%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | transientBytes | 57308.000 | 56724.000 | -584.000 B/row (-1.02%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | elapsedUs | 629.500 | 557.958 | -71.542 us/row (-11.36%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | transientBytes | 33602.000 | 32946.000 | -656.000 B/row (-1.95%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | elapsedUs | 868.666 | 788.292 | -80.374 us/row (-9.25%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.columns.wire | retainedBytes | 12168.000 | 12112.000 | -56.000 B/row (-0.46%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | transientBytes | 39946.000 | 39290.000 | -656.000 B/row (-1.64%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | elapsedUs | 629.250 | 564.792 | -64.458 us/row (-10.24%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | transientBytes | 35019.000 | 34435.000 | -584.000 B/row (-1.67%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | elapsedUs | 854.291 | 774.792 | -79.499 us/row (-9.31%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.document.wire | retainedBytes | 12168.000 | 12112.000 | -56.000 B/row (-0.46%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | transientBytes | 41363.000 | 40779.000 | -584.000 B/row (-1.41%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | elapsedUs | 1034.167 | 972.667 | -61.500 us/row (-5.95%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | transientBytes | 36365.000 | 35821.000 | -544.000 B/row (-1.50%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | elapsedUs | 1853.833 | 1747.542 | -106.291 us/row (-5.73%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.columns.wire | retainedBytes | 29064.000 | 29008.000 | -56.000 B/row (-0.19%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | transientBytes | 59705.000 | 59161.000 | -544.000 B/row (-0.91%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | elapsedUs | 1046.167 | 958.958 | -87.209 us/row (-8.34%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | transientBytes | 37910.000 | 37438.000 | -472.000 B/row (-1.25%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | elapsedUs | 1860.583 | 1685.667 | -174.916 us/row (-9.40%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.document.wire | retainedBytes | 29064.000 | 29008.000 | -56.000 B/row (-0.19%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | transientBytes | 61250.000 | 60778.000 | -472.000 B/row (-0.77%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | elapsedUs | 903.042 | 830.500 | -72.542 us/row (-8.03%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.columns.typed | retainedBytes | 10424.000 | 10368.000 | -56.000 B/row (-0.54%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | transientBytes | 31157.000 | 30501.000 | -656.000 B/row (-2.11%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | elapsedUs | 1293.333 | 1190.792 | -102.541 us/row (-7.93%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.columns.wire | retainedBytes | 10632.000 | 10576.000 | -56.000 B/row (-0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | transientBytes | 31365.000 | 30709.000 | -656.000 B/row (-2.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | elapsedUs | 929.417 | 816.458 | -112.959 us/row (-12.15%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.document.typed | retainedBytes | 10424.000 | 10368.000 | -56.000 B/row (-0.54%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | transientBytes | 32190.000 | 31606.000 | -584.000 B/row (-1.81%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | elapsedUs | 1278.000 | 1173.875 | -104.125 us/row (-8.15%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.document.wire | retainedBytes | 10632.000 | 10576.000 | -56.000 B/row (-0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | transientBytes | 32398.000 | 31814.000 | -584.000 B/row (-1.80%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | elapsedUs | 574.250 | 513.208 | -61.042 us/row (-10.63%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | transientBytes | 21893.000 | 21237.000 | -656.000 B/row (-3.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | elapsedUs | 660.917 | 591.583 | -69.334 us/row (-10.49%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.columns.wire | retainedBytes | 6024.000 | 5968.000 | -56.000 B/row (-0.93%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | transientBytes | 22101.000 | 21445.000 | -656.000 B/row (-2.97%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | elapsedUs | 569.042 | 512.583 | -56.459 us/row (-9.92%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | transientBytes | 22926.000 | 22342.000 | -584.000 B/row (-2.55%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | elapsedUs | 658.708 | 584.583 | -74.125 us/row (-11.25%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.document.wire | retainedBytes | 6024.000 | 5968.000 | -56.000 B/row (-0.93%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | transientBytes | 23134.000 | 22550.000 | -584.000 B/row (-2.52%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | elapsedUs | 522.333 | 458.584 | -63.749 us/row (-12.20%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | transientBytes | 22646.000 | 21990.000 | -656.000 B/row (-2.90%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | elapsedUs | 659.000 | 599.625 | -59.375 us/row (-9.01%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.columns.wire | retainedBytes | 12152.000 | 12096.000 | -56.000 B/row (-0.46%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | transientBytes | 28942.000 | 28286.000 | -656.000 B/row (-2.27%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | elapsedUs | 522.958 | 462.792 | -60.166 us/row (-11.50%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | transientBytes | 23830.000 | 23246.000 | -584.000 B/row (-2.45%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | elapsedUs | 644.958 | 594.875 | -50.083 us/row (-7.77%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.document.wire | retainedBytes | 12152.000 | 12096.000 | -56.000 B/row (-0.46%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | transientBytes | 30126.000 | 29542.000 | -584.000 B/row (-1.94%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | elapsedUs | 533.333 | 487.417 | -45.916 us/row (-8.61%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | transientBytes | 23626.000 | 22970.000 | -656.000 B/row (-2.78%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | elapsedUs | 680.875 | 618.875 | -62.000 us/row (-9.11%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.columns.wire | retainedBytes | 12168.000 | 12112.000 | -56.000 B/row (-0.46%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | transientBytes | 29978.000 | 29322.000 | -656.000 B/row (-2.19%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | elapsedUs | 531.792 | 477.958 | -53.834 us/row (-10.12%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | transientBytes | 25006.000 | 24422.000 | -584.000 B/row (-2.34%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | elapsedUs | 685.708 | 618.125 | -67.583 us/row (-9.86%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.document.wire | retainedBytes | 12168.000 | 12112.000 | -56.000 B/row (-0.46%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | transientBytes | 31358.000 | 30774.000 | -584.000 B/row (-1.86%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | elapsedUs | 678.875 | 614.500 | -64.375 us/row (-9.48%) | 9 | faster |
| 3.14 | keyed-write | leaf.string.columns.wire | retainedBytes | 6024.000 | 5968.000 | -56.000 B/row (-0.93%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | transientBytes | 24660.000 | 24004.000 | -656.000 B/row (-2.66%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | elapsedUs | 679.500 | 629.125 | -50.375 us/row (-7.41%) | 9 | faster |
| 3.14 | keyed-write | leaf.string.document.wire | retainedBytes | 6024.000 | 5968.000 | -56.000 B/row (-0.93%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | transientBytes | 26205.000 | 25621.000 | -584.000 B/row (-2.23%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | elapsedUs | 683.208 | 622.292 | -60.916 us/row (-8.92%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | transientBytes | 36162.000 | 35506.000 | -656.000 B/row (-1.81%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | elapsedUs | 940.083 | 857.917 | -82.166 us/row (-8.74%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.columns.wire | retainedBytes | 12168.000 | 12112.000 | -56.000 B/row (-0.46%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | transientBytes | 42506.000 | 41850.000 | -656.000 B/row (-1.54%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | elapsedUs | 683.625 | 613.208 | -70.417 us/row (-10.30%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | transientBytes | 37899.000 | 37315.000 | -584.000 B/row (-1.54%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | elapsedUs | 942.583 | 865.084 | -77.499 us/row (-8.22%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.document.wire | retainedBytes | 12168.000 | 12112.000 | -56.000 B/row (-0.46%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | transientBytes | 44243.000 | 43659.000 | -584.000 B/row (-1.32%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | elapsedUs | 796.000 | 720.625 | -75.375 us/row (-9.47%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | transientBytes | 42311.000 | 41655.000 | -656.000 B/row (-1.55%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | elapsedUs | 1186.708 | 1072.042 | -114.666 us/row (-9.66%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | retainedBytes | 15240.000 | 15184.000 | -56.000 B/row (-0.37%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | transientBytes | 51979.000 | 51435.000 | -544.000 B/row (-1.05%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | elapsedUs | 789.417 | 707.084 | -82.333 us/row (-10.43%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | transientBytes | 44816.000 | 44232.000 | -584.000 B/row (-1.30%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | elapsedUs | 1184.833 | 1081.375 | -103.458 us/row (-8.73%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.document.wire | retainedBytes | 15240.000 | 15184.000 | -56.000 B/row (-0.37%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | transientBytes | 54484.000 | 54012.000 | -472.000 B/row (-0.87%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | elapsedUs | 923.375 | 819.708 | -103.667 us/row (-11.23%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.columns.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | transientBytes | 47034.000 | 46378.000 | -656.000 B/row (-1.39%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | elapsedUs | 1274.125 | 1132.959 | -141.166 us/row (-11.08%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.columns.wire | retainedBytes | 26760.000 | 26704.000 | -56.000 B/row (-0.21%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | transientBytes | 67978.000 | 67322.000 | -656.000 B/row (-0.97%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | elapsedUs | 911.583 | 816.125 | -95.458 us/row (-10.47%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.document.typed | retainedBytes | 5816.000 | 5760.000 | -56.000 B/row (-0.96%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | transientBytes | 50115.000 | 49531.000 | -584.000 B/row (-1.17%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | elapsedUs | 1279.167 | 1139.709 | -139.458 us/row (-10.90%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.document.wire | retainedBytes | 26760.000 | 26704.000 | -56.000 B/row (-0.21%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | transientBytes | 71059.000 | 70475.000 | -584.000 B/row (-0.82%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 143.708 | 132.291 | -11.417 us/row (-7.94%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 1992.000 | 1872.000 | -120.000 B/row (-6.02%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 8491.000 | 7829.000 | -662.000 B/row (-7.80%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 131.375 | 122.833 | -8.542 us/row (-6.50%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 1952.000 | 1904.000 | -48.000 B/row (-2.46%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 9263.000 | 8841.000 | -422.000 B/row (-4.56%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 147.792 | 144.375 | -3.417 us/row (-2.31%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 1920.000 | 1872.000 | -48.000 B/row (-2.50%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 9423.000 | 8849.000 | -574.000 B/row (-6.09%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 136.167 | 134.750 | -1.417 us/row (-1.04%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 1952.000 | 1904.000 | -48.000 B/row (-2.46%) | 1 | within noise |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 10195.000 | 9861.000 | -334.000 B/row (-3.28%) | 9 | smaller |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.columns.wire | elapsedUs | 229.750 | 199.250 | -30.500 us/row (-13.28%) | 9 | faster |
| 3.14 | keyed-write | plain.target-patch.columns.wire | retainedBytes | 2512.000 | 2464.000 | -48.000 B/row (-1.91%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-patch.columns.wire | transientBytes | 14371.000 | 12788.000 | -1583.000 B/row (-11.02%) | 9 | smaller |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-patch.document.wire | elapsedUs | 250.959 | 235.125 | -15.834 us/row (-6.31%) | 9 | faster |
| 3.14 | keyed-write | plain.target-patch.document.wire | retainedBytes | 2512.000 | 2464.000 | -48.000 B/row (-1.91%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-patch.document.wire | transientBytes | 16775.000 | 15215.000 | -1560.000 B/row (-9.30%) | 9 | smaller |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.typed | elapsedUs | 240.584 | 229.584 | -11.000 us/row (-4.57%) | 9 | within noise |
| 3.14 | keyed-write | plain.target-replace.columns.typed | retainedBytes | 2480.000 | 2432.000 | -48.000 B/row (-1.94%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-replace.columns.typed | transientBytes | 14223.000 | 12648.000 | -1575.000 B/row (-11.07%) | 9 | smaller |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.columns.wire | elapsedUs | 226.292 | 201.959 | -24.333 us/row (-10.75%) | 9 | faster |
| 3.14 | keyed-write | plain.target-replace.columns.wire | retainedBytes | 2512.000 | 2464.000 | -48.000 B/row (-1.91%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-replace.columns.wire | transientBytes | 14366.000 | 12784.000 | -1582.000 B/row (-11.01%) | 9 | smaller |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.typed | elapsedUs | 267.833 | 249.334 | -18.499 us/row (-6.91%) | 9 | faster |
| 3.14 | keyed-write | plain.target-replace.document.typed | retainedBytes | 2480.000 | 2432.000 | -48.000 B/row (-1.94%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-replace.document.typed | transientBytes | 16628.000 | 15076.000 | -1552.000 B/row (-9.33%) | 9 | smaller |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.target-replace.document.wire | elapsedUs | 255.084 | 232.667 | -22.417 us/row (-8.79%) | 9 | faster |
| 3.14 | keyed-write | plain.target-replace.document.wire | retainedBytes | 2512.000 | 2464.000 | -48.000 B/row (-1.91%) | 1 | within noise |
| 3.14 | keyed-write | plain.target-replace.document.wire | transientBytes | 16770.000 | 15211.000 | -1559.000 B/row (-9.30%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 188.250 | 190.917 | +2.667 us/row (+1.42%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 1640.000 | 1592.000 | -48.000 B/row (-2.93%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 9985.000 | 10555.000 | +570.000 B/row (+5.71%) | 9 | larger |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 179.292 | 175.375 | -3.917 us/row (-2.18%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 1672.000 | 1624.000 | -48.000 B/row (-2.87%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 10737.000 | 11307.000 | +570.000 B/row (+5.31%) | 9 | larger |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 204.750 | 196.709 | -8.041 us/row (-3.93%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 1640.000 | 1592.000 | -48.000 B/row (-2.93%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 11484.000 | 11556.000 | +72.000 B/row (+0.63%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 202.750 | 192.250 | -10.500 us/row (-5.18%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 1672.000 | 1624.000 | -48.000 B/row (-2.87%) | 1 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 11996.000 | 12132.000 | +136.000 B/row (+1.13%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 143.500 | 137.709 | -5.791 us/row (-4.04%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1840.000 | 1784.000 | -56.000 B/row (-3.04%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 11054.000 | 10451.000 | -603.000 B/row (-5.46%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 146.166 | 132.459 | -13.707 us/row (-9.38%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2048.000 | 1992.000 | -56.000 B/row (-2.73%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 11382.000 | 10899.000 | -483.000 B/row (-4.24%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 141.041 | 133.250 | -7.791 us/row (-5.52%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 1840.000 | 1784.000 | -56.000 B/row (-3.04%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 11126.000 | 10326.000 | -800.000 B/row (-7.19%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 146.625 | 133.708 | -12.917 us/row (-8.81%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 2048.000 | 1992.000 | -56.000 B/row (-2.73%) | 1 | within noise |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 11430.000 | 10750.000 | -680.000 B/row (-5.95%) | 9 | smaller |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | elapsedUs | 353.083 | 338.125 | -14.958 us/row (-4.24%) | 9 | within noise |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | retainedBytes | 2104.000 | 2056.000 | -48.000 B/row (-2.28%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-patch.columns.wire | transientBytes | 21546.000 | 18653.000 | -2893.000 B/row (-13.43%) | 9 | smaller |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-patch.document.wire | elapsedUs | 363.125 | 344.291 | -18.834 us/row (-5.19%) | 9 | faster |
| 3.14 | keyed-write | txtime.target-patch.document.wire | retainedBytes | 2104.000 | 2056.000 | -48.000 B/row (-2.28%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-patch.document.wire | transientBytes | 22003.000 | 19142.000 | -2861.000 B/row (-13.00%) | 9 | smaller |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | elapsedUs | 368.292 | 340.917 | -27.375 us/row (-7.43%) | 9 | faster |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | retainedBytes | 2072.000 | 2024.000 | -48.000 B/row (-2.32%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.typed | transientBytes | 21454.000 | 18625.000 | -2829.000 B/row (-13.19%) | 9 | smaller |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | elapsedUs | 352.084 | 324.459 | -27.625 us/row (-7.85%) | 9 | faster |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | retainedBytes | 2104.000 | 2056.000 | -48.000 B/row (-2.28%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.columns.wire | transientBytes | 21546.000 | 18653.000 | -2893.000 B/row (-13.43%) | 9 | smaller |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.typed | elapsedUs | 378.250 | 346.125 | -32.125 us/row (-8.49%) | 9 | faster |
| 3.14 | keyed-write | txtime.target-replace.document.typed | retainedBytes | 2072.000 | 2024.000 | -48.000 B/row (-2.32%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.typed | transientBytes | 21911.000 | 19114.000 | -2797.000 B/row (-12.77%) | 9 | smaller |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.target-replace.document.wire | elapsedUs | 372.500 | 330.916 | -41.584 us/row (-11.16%) | 9 | faster |
| 3.14 | keyed-write | txtime.target-replace.document.wire | retainedBytes | 2104.000 | 2056.000 | -48.000 B/row (-2.28%) | 1 | within noise |
| 3.14 | keyed-write | txtime.target-replace.document.wire | transientBytes | 22003.000 | 19142.000 | -2861.000 B/row (-13.00%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 37.458 | 33.833 | -3.625 us/row (-9.68%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 4066.000 | 4010.000 | -56.000 B/row (-1.38%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 30.708 | 28.208 | -2.500 us/row (-8.14%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 3502.000 | 3742.000 | +240.000 B/row (+6.85%) | 9 | larger |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 37.875 | 34.541 | -3.334 us/row (-8.80%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 4068.000 | 4012.000 | -56.000 B/row (-1.38%) | 9 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 30.583 | 28.083 | -2.500 us/row (-8.17%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 3505.000 | 3745.000 | +240.000 B/row (+6.85%) | 9 | larger |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3428.208 | 3023.916 | -404.292 us (-11.79%) | 9 | faster |
| 3.14 | model-preparation | model.prepared | retainedBytes | 438520.000 | 439024.000 | +504.000 B (+0.11%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 445000.000 | 445848.000 | +848.000 B (+0.19%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | 307.959 | 292.500 | -15.459 us (-5.02%) | 9 | faster |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | 24000.000 | 24504.000 | +504.000 B (+2.10%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared.family | transientBytes | 27704.000 | 28648.000 | +944.000 B (+3.41%) | 9 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 23.404 | 17.683 | -5.721 us/row (-24.45%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 991.969 | 989.094 | -2.875 B/row (-0.29%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 2175.711 | 1872.203 | -303.508 B/row (-13.95%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 23.458 | 18.547 | -4.911 us/row (-20.94%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1993.594 | 1990.719 | -2.875 B/row (-0.14%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2386.992 | 2317.531 | -69.461 B/row (-2.91%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 27.000 | 21.870 | -5.130 us/row (-19.00%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1160.875 | 1149.375 | -11.500 B/row (-0.99%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2534.469 | 2360.000 | -174.469 B/row (-6.88%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 27.895 | 22.158 | -5.737 us/row (-20.57%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2167.375 | 2155.875 | -11.500 B/row (-0.53%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 2961.094 | 2705.500 | -255.594 B/row (-8.63%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 44.927 | 37.547 | -7.380 us/row (-16.43%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1844.500 | 1798.500 | -46.000 B/row (-2.49%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 4587.875 | 3918.000 | -669.875 B/row (-14.60%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 44.969 | 38.016 | -6.953 us/row (-15.46%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2870.500 | 2824.500 | -46.000 B/row (-1.60%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 4832.375 | 4170.000 | -662.375 B/row (-13.71%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | elapsedUs | 114.245 | 101.766 | -12.479 us/row (-10.92%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | retainedBytes | 3268.500 | 3222.500 | -46.000 B/row (-1.41%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | transientBytes | 16991.375 | 16310.000 | -681.375 B/row (-4.01%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | elapsedUs | 112.927 | 100.792 | -12.136 us/row (-10.75%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | retainedBytes | 16744.500 | 16698.500 | -46.000 B/row (-0.27%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | transientBytes | 18863.625 | 18017.000 | -846.625 B/row (-4.49%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | elapsedUs | 322.229 | 286.214 | -36.016 us/row (-11.18%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | retainedBytes | 13068.500 | 13022.500 | -46.000 B/row (-0.35%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | transientBytes | 32708.000 | 32027.125 | -680.875 B/row (-2.08%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | elapsedUs | 321.875 | 288.635 | -33.240 us/row (-10.33%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | retainedBytes | 40560.500 | 40514.500 | -46.000 B/row (-0.11%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | transientBytes | 42835.250 | 41966.125 | -869.125 B/row (-2.03%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | elapsedUs | 369.870 | 335.849 | -34.021 us/row (-9.20%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | retainedBytes | 9668.500 | 9622.500 | -46.000 B/row (-0.48%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | transientBytes | 27958.625 | 27278.000 | -680.625 B/row (-2.43%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | elapsedUs | 371.641 | 332.339 | -39.302 us/row (-10.58%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | retainedBytes | 32936.500 | 32890.500 | -46.000 B/row (-0.14%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | transientBytes | 35213.875 | 34361.000 | -852.875 B/row (-2.42%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | elapsedUs | 711.693 | 664.948 | -46.745 us/row (-6.57%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | retainedBytes | 27268.500 | 27222.500 | -46.000 B/row (-0.17%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | transientBytes | 32979.375 | 32109.000 | -870.375 B/row (-2.64%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | elapsedUs | 714.354 | 662.182 | -52.172 us/row (-7.30%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | retainedBytes | 50920.500 | 50874.500 | -46.000 B/row (-0.09%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | transientBytes | 53384.375 | 52530.750 | -853.625 B/row (-1.60%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | elapsedUs | 585.287 | 532.552 | -52.734 us/row (-9.01%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | retainedBytes | 8068.500 | 8022.500 | -46.000 B/row (-0.57%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | transientBytes | 22397.375 | 21716.000 | -681.375 B/row (-3.04%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | elapsedUs | 581.838 | 538.484 | -43.354 us/row (-7.45%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | retainedBytes | 26152.500 | 26106.500 | -46.000 B/row (-0.18%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | transientBytes | 28308.625 | 27455.000 | -853.625 B/row (-3.02%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | elapsedUs | 263.724 | 230.114 | -33.609 us/row (-12.74%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | retainedBytes | 7876.500 | 7830.500 | -46.000 B/row (-0.58%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | transientBytes | 21620.375 | 20939.000 | -681.375 B/row (-3.15%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | elapsedUs | 262.047 | 232.536 | -29.510 us/row (-11.26%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | retainedBytes | 21352.500 | 21306.500 | -46.000 B/row (-0.22%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | transientBytes | 23499.625 | 22646.000 | -853.625 B/row (-3.63%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | elapsedUs | 160.011 | 142.771 | -17.240 us/row (-10.77%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | retainedBytes | 9668.000 | 9622.000 | -46.000 B/row (-0.48%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | transientBytes | 23400.375 | 22719.500 | -680.875 B/row (-2.91%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | elapsedUs | 158.062 | 145.042 | -13.021 us/row (-8.24%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | retainedBytes | 23144.000 | 23098.000 | -46.000 B/row (-0.20%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | transientBytes | 25279.625 | 24426.500 | -853.125 B/row (-3.37%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | elapsedUs | 167.984 | 149.854 | -18.130 us/row (-10.79%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | retainedBytes | 10052.500 | 10006.500 | -46.000 B/row (-0.46%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | transientBytes | 23789.375 | 23108.500 | -680.875 B/row (-2.86%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | elapsedUs | 167.281 | 149.526 | -17.755 us/row (-10.61%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | retainedBytes | 23528.500 | 23482.500 | -46.000 B/row (-0.20%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | transientBytes | 25668.625 | 24815.500 | -853.125 B/row (-3.32%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | elapsedUs | 148.198 | 130.792 | -17.406 us/row (-11.75%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | retainedBytes | 13444.500 | 13398.500 | -46.000 B/row (-0.34%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | transientBytes | 27166.875 | 26485.750 | -681.125 B/row (-2.51%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | elapsedUs | 149.833 | 132.740 | -17.094 us/row (-11.41%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | retainedBytes | 26920.500 | 26874.500 | -46.000 B/row (-0.17%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | transientBytes | 29055.125 | 28192.750 | -862.375 B/row (-2.97%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | elapsedUs | 469.719 | 435.354 | -34.365 us/row (-7.32%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | retainedBytes | 9668.500 | 9622.500 | -46.000 B/row (-0.48%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | transientBytes | 28926.625 | 28246.000 | -680.625 B/row (-2.35%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | elapsedUs | 475.057 | 425.198 | -49.859 us/row (-10.50%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | retainedBytes | 33896.500 | 33850.500 | -46.000 B/row (-0.14%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | transientBytes | 36181.875 | 35329.000 | -852.875 B/row (-2.36%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | elapsedUs | 690.484 | 634.412 | -56.073 us/row (-8.12%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | retainedBytes | 12868.500 | 12822.500 | -46.000 B/row (-0.36%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | transientBytes | 31762.625 | 31095.750 | -666.875 B/row (-2.10%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | elapsedUs | 693.547 | 626.781 | -66.766 us/row (-9.63%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | retainedBytes | 39400.500 | 39354.500 | -46.000 B/row (-0.12%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | transientBytes | 41705.875 | 40851.750 | -854.125 B/row (-2.05%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | elapsedUs | 424.927 | 377.953 | -46.974 us/row (-11.05%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | retainedBytes | 24863.000 | 24817.000 | -46.000 B/row (-0.19%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | transientBytes | 35352.125 | 34671.500 | -680.625 B/row (-1.93%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | elapsedUs | 426.458 | 386.536 | -39.922 us/row (-9.36%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | retainedBytes | 53123.000 | 53077.000 | -46.000 B/row (-0.09%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | transientBytes | 55375.375 | 54522.500 | -852.875 B/row (-1.54%) | 9 | within noise |
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
| 3.14 | wire-insert-response | response.insert.family.wire | elapsedUs | 66.916 | 61.916 | -5.000 us/row (-7.47%) | 9 | faster |
| 3.14 | wire-insert-response | response.insert.family.wire | retainedBytes | 9572.000 | 9356.000 | -216.000 B/row (-2.26%) | 1 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | transientBytes | 8790.000 | 8774.000 | -16.000 B/row (-0.18%) | 9 | within noise |

Deltas are advisory and never ratchet the Budget Contract.
