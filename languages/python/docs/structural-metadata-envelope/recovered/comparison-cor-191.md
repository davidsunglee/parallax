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
| - | - | cpython-3.13 | aggregate.retained.after | 3264.000 | 3312.000 | +48.000 B (+1.47%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.before | 7200.000 | 7248.000 | +48.000 B (+0.67%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.reduction | 0.547 | 0.543 | -0.004 ratio (-0.66%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.340 | 3.501 | +0.161 ratio (+4.83%) | 0 | larger |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.340 | 3.501 | +0.161 ratio (+4.83%) | 0 | larger |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.313 | 3.351 | +0.038 ratio (+1.16%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 0.522 | 0.693 | +0.172 ratio (+32.91%) | 0 | larger |
| - | - | cpython-3.13 | operation.construction.likeForLike | 0.500 | 0.661 | +0.162 ratio (+32.32%) | 0 | larger |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 1.549 | 1.550 | +0.001 ratio (+0.06%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.184 | 2.144 | -0.040 ratio (-1.82%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.184 | 2.144 | -0.040 ratio (-1.82%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.209 | 2.146 | -0.063 ratio (-2.87%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3312.000 | +48.000 B (+1.47%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.584 | -0.006 ratio (-1.02%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 1471.432 | 1657.933 | +186.502 ns (+12.67%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 6919.735 | 7035.358 | +115.623 ns (+1.67%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.directWireNs | 10597.250 | 11389.125 | +791.875 ns (+7.47%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.dumpNs | 5770.104 | 6092.333 | +322.229 ns (+5.58%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.peakBytes | 4770.000 | 4778.000 | +8.000 B (+0.17%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionNs | 14270.875 | 14895.834 | +624.959 ns (+4.38%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | 7560.000 | 7776.000 | +216.000 B (+2.86%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | 1240.000 | 1264.000 | +24.000 B (+1.94%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | 12258.998 | 12707.131 | +448.133 ns (+3.66%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | 6320.000 | 6512.000 | +192.000 B (+3.04%) | 0 | larger |
| - | - | cpython-3.13/nested | compact.readNs | 83.312 | 83.121 | -0.192 ns (-0.23%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1072.000 | +8.000 B (+0.75%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 425.885 | 262.897 | -162.988 ns (-38.27%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 3706.000 | 3706.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 425.885 | 262.897 | -162.988 ns (-38.27%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | 105.925 | 236.550 | +130.625 ns (+123.32%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 10317.575 | 9566.596 | -750.979 ns (-7.28%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2373.458 | 2660.208 | +286.750 ns (+12.08%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.peakBytes | 4960.000 | 4968.000 | +8.000 B (+0.16%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.readNs | 25.200 | 24.712 | -0.488 ns (-1.93%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2800.000 | +8.000 B (+0.29%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2168.000 | 2168.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 417.600 | 208.929 | -208.672 ns (-49.97%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 6057.817 | 6212.592 | +154.775 ns (+2.55%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2379.062 | 2651.458 | +272.395 ns (+11.45%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 26.533 | 25.575 | -0.958 ns (-3.61%) | 0 | smaller |
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
| - | - | cpython-3.13/nullable | compact.callNs | 1309.339 | 1423.679 | +114.340 ns (+8.73%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 2307.494 | 2363.404 | +55.910 ns (+2.42%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.directWireNs | 5579.396 | 6290.750 | +711.354 ns (+12.75%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1830.562 | 1838.208 | +7.646 ns (+0.42%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.peakBytes | 3464.000 | 3472.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionNs | 7539.375 | 8320.437 | +781.062 ns (+10.36%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | 2504.000 | 2624.000 | +120.000 B (+4.79%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | 472.000 | 496.000 | +24.000 B (+5.08%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | 6016.996 | 6669.479 | +652.483 ns (+10.84%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | 2032.000 | 2128.000 | +96.000 B (+4.72%) | 0 | larger |
| - | - | cpython-3.13/nullable | compact.readNs | 74.656 | 75.912 | +1.256 ns (+1.68%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 472.000 | +8.000 B (+1.72%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 233.641 | 214.640 | -19.001 ns (-8.13%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 233.641 | 214.640 | -19.001 ns (-8.13%) | 0 | smaller |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 265.614 | 235.063 | -30.552 ns (-11.50%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5215.677 | 3658.437 | -1557.240 ns (-29.86%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 855.125 | 878.833 | +23.708 ns (+2.77%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1712.000 | +8.000 B (+0.47%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 22.127 | 21.375 | -0.752 ns (-3.40%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 984.000 | +8.000 B (+0.82%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 165.896 | 214.544 | +48.648 ns (+29.32%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1191.208 | 1202.498 | +11.290 ns (+0.95%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 860.687 | 876.625 | +15.938 ns (+1.85%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 22.060 | 22.721 | +0.660 ns (+2.99%) | 0 | within noise |
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
| - | - | cpython-3.13/partial | compact.callNs | 1358.350 | 1376.983 | +18.633 ns (+1.37%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 2144.337 | 2166.746 | +22.408 ns (+1.05%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.directWireNs | 4991.438 | 5572.166 | +580.729 ns (+11.63%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.dumpNs | 1857.750 | 1835.895 | -21.855 ns (-1.18%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.peakBytes | 3432.000 | 3440.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionNs | 6969.125 | 7433.541 | +464.417 ns (+6.66%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | 2416.000 | 2536.000 | +120.000 B (+4.97%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | 384.000 | 408.000 | +24.000 B (+6.25%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | 5394.842 | 5807.571 | +412.729 ns (+7.65%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | 2032.000 | 2128.000 | +96.000 B (+4.72%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.readNs | 74.935 | 75.071 | +0.135 ns (+0.18%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 440.000 | +8.000 B (+1.85%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 218.860 | 201.789 | -17.071 ns (-7.80%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 218.860 | 201.789 | -17.071 ns (-7.80%) | 0 | smaller |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 187.077 | 199.579 | +12.502 ns (+6.68%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 4991.819 | 3306.504 | -1685.315 ns (-33.76%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.dumpNs | 891.167 | 877.000 | -14.166 ns (-1.59%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1712.000 | +8.000 B (+0.47%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 24.321 | 20.481 | -3.840 ns (-15.79%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 984.000 | +8.000 B (+0.82%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 191.492 | 253.240 | +61.748 ns (+32.25%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 945.946 | 941.406 | -4.540 ns (-0.48%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 868.479 | 870.646 | +2.167 ns (+0.25%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 22.933 | 21.281 | -1.652 ns (-7.20%) | 0 | smaller |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 1346.071 | 1309.365 | -36.706 ns (-2.73%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 2218.367 | 2245.323 | +26.956 ns (+1.22%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | 5783.750 | 6360.521 | +576.771 ns (+9.97%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1588.438 | 1685.229 | +96.791 ns (+6.09%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 3408.000 | 3416.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | 7628.708 | 8270.938 | +642.229 ns (+8.42%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | 2776.000 | 2896.000 | +120.000 B (+4.32%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | 472.000 | 496.000 | +24.000 B (+5.08%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | 5820.625 | 6298.952 | +478.327 ns (+8.22%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | 2304.000 | 2400.000 | +96.000 B (+4.17%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.readNs | 80.107 | 78.333 | -1.774 ns (-2.21%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 416.000 | +8.000 B (+1.96%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 234.066 | 216.257 | -17.809 ns (-7.61%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 234.066 | 216.257 | -17.809 ns (-7.61%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 138.725 | 219.892 | +81.167 ns (+58.51%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4085.067 | 2970.150 | -1114.917 ns (-27.29%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 786.792 | 797.792 | +11.000 ns (+1.40%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1312.000 | +8.000 B (+0.61%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 23.863 | 24.012 | +0.149 ns (+0.62%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 792.000 | +8.000 B (+1.02%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 196.121 | 201.398 | +5.277 ns (+2.69%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1057.004 | 1069.602 | +12.598 ns (+1.19%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 774.416 | 850.396 | +75.980 ns (+9.81%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 24.283 | 25.012 | +0.729 ns (+3.00%) | 0 | larger |
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
| - | - | cpython-3.13/shallow | compact.callNs | 1392.777 | 1437.385 | +44.609 ns (+3.20%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 2077.452 | 2107.990 | +30.538 ns (+1.47%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.directWireNs | 7265.021 | 7672.729 | +407.708 ns (+5.61%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1399.542 | 1426.792 | +27.250 ns (+1.95%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.peakBytes | 3384.000 | 3392.000 | +8.000 B (+0.24%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionNs | 8747.937 | 9297.188 | +549.250 ns (+6.28%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | 3358.000 | 3414.000 | +56.000 B (+1.67%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | 430.000 | 454.000 | +24.000 B (+5.58%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | 5370.629 | 5714.146 | +343.517 ns (+6.40%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | 2928.000 | 2960.000 | +32.000 B (+1.09%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.readNs | 88.635 | 88.240 | -0.396 ns (-0.45%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 392.000 | +8.000 B (+2.08%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 209.616 | 188.865 | -20.751 ns (-9.90%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 209.616 | 188.865 | -20.751 ns (-9.90%) | 0 | smaller |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 147.133 | 160.688 | +13.554 ns (+9.21%) | 0 | larger |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2716.804 | 2243.458 | -473.346 ns (-17.42%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 715.209 | 733.021 | +17.812 ns (+2.49%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1112.000 | -90.000 B (-7.49%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.readNs | 25.276 | 25.339 | +0.063 ns (+0.25%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 704.000 | +8.000 B (+1.15%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 408.000 | -98.000 B (-19.37%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 214.562 | 236.404 | +21.842 ns (+10.18%) | 0 | larger |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 785.979 | 770.638 | -15.342 ns (-1.95%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 718.188 | 748.146 | +29.959 ns (+4.17%) | 0 | larger |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 26.338 | 26.021 | -0.318 ns (-1.21%) | 0 | within noise |
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
| - | - | cpython-3.13/warmed | compact.callNs | 1586.575 | 1472.227 | -114.348 ns (-7.21%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 4130.592 | 3948.210 | -182.381 ns (-4.42%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1737.125 | 1745.000 | +7.875 ns (+0.45%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.peakBytes | 3384.000 | 3392.000 | +8.000 B (+0.24%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.readNs | 87.688 | 93.292 | +5.604 ns (+6.39%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 814.000 | +8.000 B (+0.99%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 240.703 | 194.842 | -45.861 ns (-19.05%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.transientBytes | 2578.000 | 2578.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 240.703 | 194.842 | -45.861 ns (-19.05%) | 0 | smaller |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 153.585 | 164.137 | +10.552 ns (+6.87%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 3772.644 | 3055.696 | -716.948 ns (-19.00%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 707.937 | 727.500 | +19.562 ns (+2.76%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1502.000 | +8.000 B (+0.54%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 25.859 | 24.656 | -1.203 ns (-4.65%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1030.000 | +8.000 B (+0.78%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 169.441 | 210.971 | +41.530 ns (+24.51%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1701.954 | 1501.779 | -200.175 ns (-11.76%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 704.771 | 733.292 | +28.521 ns (+4.05%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1736.000 | -26.000 B (-1.48%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 26.630 | 26.542 | -0.088 ns (-0.33%) | 0 | within noise |
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
| - | - | cpython-3.13/wide | compact.callNs | 1364.521 | 1419.927 | +55.406 ns (+4.06%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 2637.167 | 2671.219 | +34.052 ns (+1.29%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.directWireNs | 6880.459 | 7375.521 | +495.062 ns (+7.20%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.dumpNs | 2417.041 | 2525.250 | +108.208 ns (+4.48%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.peakBytes | 3512.000 | 3520.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionNs | 9253.855 | 9907.479 | +653.624 ns (+7.06%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | 3240.000 | 3360.000 | +120.000 B (+3.70%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | 664.000 | 688.000 | +24.000 B (+3.61%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | 7309.587 | 8153.844 | +844.256 ns (+11.55%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | 2576.000 | 2672.000 | +96.000 B (+3.73%) | 0 | larger |
| - | - | cpython-3.13/wide | compact.readNs | 82.273 | 79.952 | -2.322 ns (-2.82%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 520.000 | +8.000 B (+1.56%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 196.700 | 202.323 | +5.623 ns (+2.86%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 196.700 | 202.323 | +5.623 ns (+2.86%) | 0 | within noise |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 30.806 | 202.687 | +171.881 ns (+557.95%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 7771.485 | 5073.938 | -2697.548 ns (-34.71%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1184.459 | 1237.750 | +53.292 ns (+4.50%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1680.000 | +16.000 B (+0.96%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 24.100 | 21.348 | -2.753 ns (-11.42%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 984.000 | +8.000 B (+0.82%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 696.000 | +8.000 B (+1.16%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 219.250 | 233.592 | +14.342 ns (+6.54%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1775.417 | 1794.283 | +18.867 ns (+1.06%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1126.312 | 1180.063 | +53.750 ns (+4.77%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 23.921 | 22.806 | -1.115 ns (-4.66%) | 0 | smaller |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.320 | 3.143 | -0.177 ratio (-5.33%) | 0 | smaller |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.320 | 3.143 | -0.177 ratio (-5.33%) | 0 | smaller |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.284 | 3.122 | -0.161 ratio (-4.92%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 0.508 | 0.710 | +0.202 ratio (+39.85%) | 0 | larger |
| - | - | cpython-3.14 | operation.construction.likeForLike | 0.488 | 0.682 | +0.194 ratio (+39.68%) | 0 | larger |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 1.473 | 1.517 | +0.044 ratio (+3.00%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.151 | 2.131 | -0.020 ratio (-0.92%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.151 | 2.131 | -0.020 ratio (-0.92%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.186 | 2.112 | -0.074 ratio (-3.39%) | 0 | smaller |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3640.000 | +48.000 B (+1.34%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.557 | -0.006 ratio (-1.04%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 1597.398 | 1606.002 | +8.605 ns (+0.54%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 6653.790 | 5945.165 | -708.625 ns (-10.65%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.directWireNs | 11388.479 | 10652.271 | -736.208 ns (-6.46%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.dumpNs | 6027.395 | 5701.708 | -325.687 ns (-5.40%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/nested | compact.peakBytes | 5034.000 | 5042.000 | +8.000 B (+0.16%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionNs | 15389.229 | 14106.479 | -1282.750 ns (-8.34%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | 8450.000 | 8674.000 | +224.000 B (+2.65%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | 1248.000 | 1272.000 | +24.000 B (+1.92%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | 13335.406 | 12201.127 | -1134.279 ns (-8.51%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | 7202.000 | 7402.000 | +200.000 B (+2.78%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.readNs | 85.679 | 80.267 | -5.413 ns (-6.32%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1240.000 | +8.000 B (+0.65%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 317.822 | 66.545 | -251.276 ns (-79.06%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 3802.000 | 3802.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 317.822 | 66.545 | -251.276 ns (-79.06%) | 0 | smaller |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 97.054 | 6.767 | -90.287 ns (-93.03%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 10885.092 | 8688.650 | -2196.442 ns (-20.18%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 2543.729 | 2501.896 | -41.833 ns (-1.64%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5184.000 | 5192.000 | +8.000 B (+0.15%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.readNs | 26.342 | 25.425 | -0.917 ns (-3.48%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2928.000 | +8.000 B (+0.27%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2264.000 | 2264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 238.071 | 176.602 | -61.469 ns (-25.82%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 6299.804 | 5665.190 | -634.615 ns (-10.07%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 2465.104 | 2531.688 | +66.584 ns (+2.70%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4744.000 | 4744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 25.688 | 24.892 | -0.796 ns (-3.10%) | 0 | smaller |
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
| - | - | cpython-3.14/nullable | compact.callNs | 1387.052 | 1307.873 | -79.179 ns (-5.71%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 2320.427 | 2093.960 | -226.467 ns (-9.76%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.directWireNs | 5765.604 | 5675.437 | -90.167 ns (-1.56%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.dumpNs | 1813.438 | 1676.063 | -137.375 ns (-7.58%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.peakBytes | 3672.000 | 3680.000 | +8.000 B (+0.22%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionNs | 8073.063 | 7294.729 | -778.334 ns (-9.64%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | 2736.000 | 2864.000 | +128.000 B (+4.68%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | 480.000 | 504.000 | +24.000 B (+5.00%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | 6529.865 | 6038.258 | -491.606 ns (-7.53%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | 2256.000 | 2360.000 | +104.000 B (+4.61%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.readNs | 78.273 | 69.181 | -9.092 ns (-11.62%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 504.000 | +8.000 B (+1.61%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 233.380 | 190.006 | -43.375 ns (-18.59%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 233.380 | 190.006 | -43.375 ns (-18.59%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 136.987 | 213.498 | +76.510 ns (+55.85%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 5262.117 | 3014.981 | -2247.135 ns (-42.70%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 888.250 | 788.063 | -100.187 ns (-11.28%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1840.000 | +8.000 B (+0.44%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 24.467 | 23.160 | -1.306 ns (-5.34%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1008.000 | +8.000 B (+0.80%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 198.346 | 204.390 | +6.044 ns (+3.05%) | 0 | larger |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1237.029 | 1049.569 | -187.460 ns (-15.15%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 897.979 | 822.584 | -75.395 ns (-8.40%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 24.223 | 21.800 | -2.423 ns (-10.00%) | 0 | smaller |
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
| - | - | cpython-3.14/partial | compact.callNs | 1426.656 | 1206.944 | -219.713 ns (-15.40%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 2156.552 | 2046.431 | -110.121 ns (-5.11%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.directWireNs | 5136.313 | 5084.188 | -52.125 ns (-1.01%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.dumpNs | 1857.896 | 1712.208 | -145.688 ns (-7.84%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.peakBytes | 3576.000 | 3584.000 | +8.000 B (+0.22%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionNs | 7203.854 | 6761.396 | -442.459 ns (-6.14%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | 2616.000 | 2744.000 | +128.000 B (+4.89%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | 392.000 | 416.000 | +24.000 B (+6.12%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | 5734.333 | 5411.706 | -322.627 ns (-5.63%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | 2224.000 | 2328.000 | +104.000 B (+4.68%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.readNs | 79.108 | 73.923 | -5.185 ns (-6.55%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 472.000 | +8.000 B (+1.72%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 214.278 | 187.316 | -26.962 ns (-12.58%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 214.278 | 187.316 | -26.962 ns (-12.58%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 181.619 | 184.608 | +2.990 ns (+1.65%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 4941.298 | 2794.704 | -2146.594 ns (-43.44%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 901.000 | 796.291 | -104.709 ns (-11.62%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1840.000 | +8.000 B (+0.44%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 22.660 | 22.923 | +0.263 ns (+1.16%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1008.000 | +8.000 B (+0.80%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 230.394 | 209.879 | -20.515 ns (-8.90%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 1001.648 | 853.558 | -148.090 ns (-14.78%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 899.250 | 777.667 | -121.584 ns (-13.52%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 24.969 | 23.823 | -1.146 ns (-4.59%) | 0 | smaller |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 1421.756 | 1353.358 | -68.398 ns (-4.81%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 2213.744 | 2026.454 | -187.290 ns (-8.46%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | 5840.730 | 5720.188 | -120.542 ns (-2.06%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1695.812 | 1476.271 | -219.541 ns (-12.95%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 3552.000 | 3560.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | 8177.750 | 7240.750 | -937.000 ns (-11.46%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | 2984.000 | 3112.000 | +128.000 B (+4.29%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | 480.000 | 504.000 | +24.000 B (+5.00%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | 6253.440 | 5672.975 | -580.465 ns (-9.28%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | 2504.000 | 2608.000 | +104.000 B (+4.15%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.readNs | 86.920 | 71.679 | -15.241 ns (-17.53%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 448.000 | +8.000 B (+1.82%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 219.298 | 186.627 | -32.671 ns (-14.90%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 219.298 | 186.627 | -32.671 ns (-14.90%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 208.482 | 197.914 | -10.567 ns (-5.07%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4029.248 | 2531.606 | -1497.642 ns (-37.17%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 824.750 | 738.625 | -86.125 ns (-10.44%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1440.000 | +8.000 B (+0.56%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 27.179 | 24.512 | -2.667 ns (-9.81%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 816.000 | +8.000 B (+0.99%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 197.971 | 184.640 | -13.331 ns (-6.73%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1119.071 | 996.235 | -122.835 ns (-10.98%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 826.666 | 746.833 | -79.833 ns (-9.66%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 26.559 | 24.015 | -2.545 ns (-9.58%) | 0 | smaller |
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
| - | - | cpython-3.14/shallow | compact.callNs | 1442.716 | 1298.904 | -143.812 ns (-9.97%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 2091.679 | 1954.783 | -136.896 ns (-6.54%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.directWireNs | 7253.563 | 7350.750 | +97.188 ns (+1.34%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1402.125 | 1252.959 | -149.166 ns (-10.64%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/shallow | compact.peakBytes | 3528.000 | 3536.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionNs | 9067.604 | 8358.687 | -708.917 ns (-7.82%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | 3662.000 | 3718.000 | +56.000 B (+1.53%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | 438.000 | 462.000 | +24.000 B (+5.48%) | 0 | larger |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | 5764.892 | 5455.567 | -309.325 ns (-5.37%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | 3224.000 | 3256.000 | +32.000 B (+0.99%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.readNs | 88.974 | 83.922 | -5.052 ns (-5.68%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 424.000 | +8.000 B (+1.92%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 217.524 | 180.527 | -36.997 ns (-17.01%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 217.524 | 180.527 | -36.997 ns (-17.01%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 203.252 | 192.596 | -10.656 ns (-5.24%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 2762.873 | 1892.612 | -870.260 ns (-31.50%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 731.792 | 654.666 | -77.125 ns (-10.54%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1232.000 | -90.000 B (-6.81%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.readNs | 27.057 | 25.083 | -1.974 ns (-7.30%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 728.000 | +8.000 B (+1.11%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 504.000 | -98.000 B (-16.28%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 208.529 | 185.558 | -22.971 ns (-11.02%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 819.763 | 736.192 | -83.571 ns (-10.19%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 719.104 | 695.125 | -23.979 ns (-3.33%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 27.661 | 27.812 | +0.151 ns (+0.55%) | 0 | within noise |
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
| - | - | cpython-3.14/warmed | compact.callNs | 1519.006 | 1472.306 | -46.700 ns (-3.07%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 4263.015 | 3633.006 | -630.008 ns (-14.78%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1785.625 | 1603.396 | -182.229 ns (-10.21%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.peakBytes | 3528.000 | 3536.000 | +8.000 B (+0.23%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.readNs | 88.958 | 78.005 | -10.953 ns (-12.31%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 846.000 | +8.000 B (+0.95%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 268.272 | 200.439 | -67.833 ns (-25.29%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.transientBytes | 2690.000 | 2690.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 268.272 | 200.439 | -67.833 ns (-25.29%) | 0 | smaller |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 132.360 | 196.929 | +64.569 ns (+48.78%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 3897.015 | 2698.675 | -1198.340 ns (-30.75%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 751.042 | 671.333 | -79.709 ns (-10.61%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1678.000 | +8.000 B (+0.48%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 28.438 | 25.000 | -3.437 ns (-12.09%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1054.000 | +8.000 B (+0.76%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 205.705 | 206.552 | +0.848 ns (+0.41%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1755.837 | 1366.677 | -389.160 ns (-22.16%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 731.875 | 668.396 | -63.479 ns (-8.67%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 30.641 | 25.057 | -5.583 ns (-18.22%) | 0 | smaller |
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
| - | - | cpython-3.14/wide | compact.callNs | 1485.202 | 1457.496 | -27.706 ns (-1.87%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 2531.902 | 2353.962 | -177.940 ns (-7.03%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.directWireNs | 7024.791 | 6862.854 | -161.937 ns (-2.31%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.dumpNs | 2403.625 | 2225.520 | -178.104 ns (-7.41%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.peakBytes | 3720.000 | 3728.000 | +8.000 B (+0.22%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionNs | 9818.000 | 8923.563 | -894.437 ns (-9.11%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | 3488.000 | 3616.000 | +128.000 B (+3.67%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | 672.000 | 696.000 | +24.000 B (+3.57%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | 7855.685 | 7140.658 | -715.027 ns (-9.10%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | 2816.000 | 2920.000 | +104.000 B (+3.69%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.readNs | 82.836 | 75.225 | -7.611 ns (-9.19%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 552.000 | +8.000 B (+1.47%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 219.275 | 146.377 | -72.898 ns (-33.24%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 219.275 | 146.377 | -72.898 ns (-33.24%) | 0 | smaller |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 220.702 | 111.179 | -109.523 ns (-49.62%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 7487.965 | 4190.029 | -3297.935 ns (-44.04%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1177.687 | 1111.354 | -66.333 ns (-5.63%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 144.000 | +8.000 B (+5.88%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1800.000 | +16.000 B (+0.90%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 23.443 | 23.406 | -0.036 ns (-0.16%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1008.000 | +8.000 B (+0.80%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 792.000 | +8.000 B (+1.02%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 253.521 | 187.385 | -66.135 ns (-26.09%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 1719.229 | 1520.990 | -198.240 ns (-11.53%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1144.000 | 1074.896 | -69.104 ns (-6.04%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 23.717 | 23.135 | -0.582 ns (-2.45%) | 0 | within noise |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.263 | 3.082 | -0.182 us/event (-5.56%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 3.726 | 3.760 | +0.034 us/event (+0.92%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.271 | 0.261 | -0.010 ratio (-3.67%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.021 | 0.020 | -0.001 ratio (-5.42%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.068 | 0.065 | -0.003 ratio (-5.09%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.004 | 0.004 | -0.000 ratio (-5.53%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.170 | 0.163 | -0.007 ratio (-4.38%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | observed.p50 | 428.584 | 416.916 | -11.668 us (-2.72%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p95 | 445.500 | 440.083 | -5.417 us (-1.22%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 91.375 | 86.292 | -5.083 us (-5.56%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 104.334 | 105.292 | +0.958 us (+0.92%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.271 | 0.261 | -0.010 ratio (-3.64%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.309 | 0.319 | +0.010 ratio (+3.10%) | 0 | larger |
| - | - | Safe logging alone, at INFO | plain.p50 | 337.167 | 330.541 | -6.626 us (-1.97%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | plain.p95 | 350.958 | 347.875 | -3.083 us (-0.88%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.271 | 0.261 | -0.010 ratio (-3.62%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.269 | 0.265 | -0.004 ratio (-1.60%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.341 | 2.222 | -0.119 us/event (-5.09%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 2.832 | 2.787 | -0.045 us/event (-1.58%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.195 | 0.189 | -0.006 ratio (-3.09%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.015 | 0.014 | -0.001 ratio (-4.94%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.049 | 0.047 | -0.002 ratio (-4.59%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | -0.000 ratio (-5.05%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.122 | 0.118 | -0.005 ratio (-3.85%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | observed.p50 | 401.917 | 391.667 | -10.250 us (-2.55%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p95 | 420.750 | 411.791 | -8.959 us (-2.13%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 65.542 | 62.208 | -3.334 us (-5.09%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 79.291 | 78.042 | -1.249 us (-1.58%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.195 | 0.189 | -0.006 ratio (-3.08%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.235 | 0.236 | +0.001 ratio (+0.46%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | plain.p50 | 336.250 | 329.333 | -6.917 us (-2.06%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | plain.p95 | 350.958 | 346.250 | -4.708 us (-1.34%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.195 | 0.189 | -0.006 ratio (-3.08%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.199 | 0.189 | -0.010 ratio (-4.81%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 3.990 | 3.732 | -0.257 us/event (-6.45%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.973 | 4.503 | -0.470 us/event (-9.46%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.330 | 0.315 | -0.014 ratio (-4.29%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.026 | 0.024 | -0.002 ratio (-6.29%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.083 | 0.078 | -0.005 ratio (-5.91%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-6.42%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.207 | 0.197 | -0.011 ratio (-5.10%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | observed.p50 | 450.750 | 436.209 | -14.541 us (-3.23%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | observed.p95 | 479.333 | 463.291 | -16.042 us (-3.35%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 111.708 | 104.499 | -7.209 us (-6.45%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 139.250 | 126.083 | -13.167 us (-9.46%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.330 | 0.315 | -0.014 ratio (-4.36%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.406 | 0.378 | -0.029 ratio (-7.08%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | plain.p50 | 338.958 | 331.292 | -7.666 us (-2.26%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | plain.p95 | 352.375 | 351.959 | -0.416 us (-0.12%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.330 | 0.317 | -0.013 ratio (-3.98%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.360 | 0.316 | -0.044 ratio (-12.20%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 3.807 | 3.560 | -0.247 us/event (-6.49%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 4.613 | 4.415 | -0.198 us/event (-4.29%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.314 | 0.301 | -0.013 ratio (-4.11%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.025 | 0.023 | -0.002 ratio (-6.31%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.080 | 0.075 | -0.005 ratio (-5.90%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-6.45%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.198 | 0.188 | -0.010 ratio (-5.01%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 445.584 | 430.583 | -15.001 us (-3.37%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 473.917 | 460.000 | -13.917 us (-2.94%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 106.583 | 99.667 | -6.916 us (-6.49%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 129.166 | 123.625 | -5.541 us (-4.29%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.315 | 0.301 | -0.014 ratio (-4.31%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.377 | 0.374 | -0.003 ratio (-0.73%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 339.042 | 330.625 | -8.417 us (-2.48%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 353.916 | 353.417 | -0.499 us (-0.14%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.314 | 0.302 | -0.012 ratio (-3.79%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.339 | 0.302 | -0.037 ratio (-11.06%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.435 | 1.390 | -0.045 us/event (-3.11%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 1.998 | 2.040 | +0.042 us/event (+2.09%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.120 | 0.118 | -0.001 ratio (-1.15%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.009 | 0.009 | -0.000 ratio (-2.97%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.030 | 0.029 | -0.001 ratio (-2.63%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-3.08%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.075 | 0.074 | -0.001 ratio (-1.89%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p50 | 376.375 | 368.500 | -7.875 us (-2.09%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p95 | 396.459 | 392.625 | -3.834 us (-0.97%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 40.167 | 38.916 | -1.251 us (-3.11%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 55.958 | 57.125 | +1.167 us (+2.09%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.120 | 0.118 | -0.002 ratio (-1.40%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.166 | 0.172 | +0.006 ratio (+3.56%) | 0 | larger |
| - | - | one Handler that keeps nothing | plain.p50 | 336.125 | 329.458 | -6.667 us (-1.98%) | 0 | within noise |
| - | - | one Handler that keeps nothing | plain.p95 | 355.125 | 344.750 | -10.375 us (-2.92%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.120 | 0.119 | -0.001 ratio (-1.04%) | 0 | within noise |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.116 | 0.139 | +0.022 ratio (+19.31%) | 0 | larger |
| - | - | workload | events | 28.000 | 28.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | workload | statements | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |

## snapshot-delivery

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 10118.791 | 8714.250 | -1404.541 us (-13.88%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1450.010 | 1254.299 | -195.711 KiB (-13.50%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 693.328 | 571.453 | -121.875 KiB (-17.58%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 100875.375 | 87603.625 | -13271.750 us (-13.16%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 12653.846 | 11236.408 | -1417.438 KiB (-11.20%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 6931.836 | 5713.086 | -1218.750 KiB (-17.58%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 20897.416 | 15438.833 | -5458.583 us (-26.12%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 445.783 | 368.260 | -77.523 KiB (-17.39%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.458 | 2.849 | -0.609 KiB (-17.62%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 117012.542 | 99425.250 | -17587.292 us (-15.03%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 822.721 | 751.002 | -71.719 KiB (-8.72%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.489 | 2.880 | -0.609 KiB (-17.46%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8355.667 | 7585.416 | -770.251 us (-9.22%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1250.123 | 1071.404 | -178.719 KiB (-14.30%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 477.848 | 374.723 | -103.125 KiB (-21.58%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 83704.458 | 76393.166 | -7311.292 us (-8.73%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11112.811 | 9881.357 | -1231.453 KiB (-11.08%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4775.730 | 3744.480 | -1031.250 KiB (-21.59%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 19543.125 | 14492.500 | -5050.625 us (-25.84%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 392.021 | 308.131 | -83.891 KiB (-21.40%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.524 | 2.009 | -0.516 KiB (-20.43%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 101946.125 | 92672.416 | -9273.709 us (-9.10%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 821.428 | 750.037 | -71.391 KiB (-8.69%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.556 | 2.040 | -0.516 KiB (-20.18%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 18218.583 | 16818.708 | -1399.875 us (-7.68%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1352.424 | 1190.525 | -161.898 KiB (-11.97%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 708.953 | 587.078 | -121.875 KiB (-17.19%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 181144.667 | 180408.750 | -735.917 us (-0.41%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12299.947 | 11894.070 | -405.877 KiB (-3.30%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7088.086 | 5869.336 | -1218.750 KiB (-17.19%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 28165.292 | 24739.250 | -3426.042 us (-12.16%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 568.674 | 480.854 | -87.820 KiB (-15.44%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.536 | 2.927 | -0.609 KiB (-17.23%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 191903.042 | 177233.291 | -14669.751 us (-7.64%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 985.643 | 848.072 | -137.570 KiB (-13.96%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.567 | 2.958 | -0.609 KiB (-17.08%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 16167.042 | 15095.250 | -1071.792 us (-6.63%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1199.549 | 1190.955 | -8.594 KiB (-0.72%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 501.285 | 398.160 | -103.125 KiB (-20.57%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 160817.625 | 160763.000 | -54.625 us (-0.03%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12300.377 | 11894.500 | -405.877 KiB (-3.30%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5010.105 | 3978.855 | -1031.250 KiB (-20.58%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 26131.958 | 21834.167 | -4297.791 us (-16.45%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 533.678 | 447.271 | -86.406 KiB (-16.19%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.642 | 2.126 | -0.516 KiB (-19.52%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 171902.042 | 163284.958 | -8617.084 us (-5.01%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 982.014 | 844.389 | -137.625 KiB (-14.01%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.673 | 2.157 | -0.516 KiB (-19.29%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6047.917 | 5647.958 | -399.959 us (-6.61%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 476.559 | 416.355 | -60.203 KiB (-12.63%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 227.253 | 186.347 | -40.906 KiB (-18.00%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 845.875 | 775.500 | -70.375 us (-8.32%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 72.854 | 63.848 | -9.007 KiB (-12.36%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 28.146 | 22.997 | -5.148 KiB (-18.29%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4493.291 | 4483.416 | -9.875 us (-0.22%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 410.364 | 353.724 | -56.641 KiB (-13.80%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 186.823 | 152.917 | -33.906 KiB (-18.15%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 671.333 | 647.583 | -23.750 us (-3.54%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 65.379 | 57.004 | -8.375 KiB (-12.81%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.200 | 18.911 | -4.289 KiB (-18.49%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8757.458 | 8026.834 | -730.624 us (-8.34%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 606.505 | 533.407 | -73.098 KiB (-12.05%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 293.815 | 242.112 | -51.703 KiB (-17.60%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1242.166 | 1125.000 | -117.166 us (-9.43%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 92.004 | 79.926 | -12.078 KiB (-13.13%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 36.802 | 30.255 | -6.547 KiB (-17.79%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6888.417 | 7094.625 | +206.208 us (+2.99%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 550.426 | 484.859 | -65.566 KiB (-11.91%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 257.698 | 217.042 | -40.656 KiB (-15.78%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 995.458 | 998.708 | +3.250 us (+0.33%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 86.378 | 75.542 | -10.836 KiB (-12.54%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.388 | 27.224 | -5.164 KiB (-15.94%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10797.917 | 10782.708 | -15.209 us (-0.14%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 765.693 | 665.822 | -99.871 KiB (-13.04%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 384.511 | 317.901 | -66.609 KiB (-17.32%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1607.625 | 1404.792 | -202.833 us (-12.62%) | 9 | faster |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 113.556 | 97.728 | -15.828 KiB (-13.94%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 48.544 | 40.114 | -8.430 KiB (-17.37%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8466.167 | 8197.583 | -268.584 us (-3.17%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 703.224 | 613.082 | -90.142 KiB (-12.82%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 333.909 | 281.347 | -52.562 KiB (-15.74%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1262.500 | 1211.000 | -51.500 us (-4.08%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 106.775 | 92.494 | -14.281 KiB (-13.38%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.247 | 35.591 | -6.656 KiB (-15.76%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 434.381 | 295.050 | -139.331 KiB (-32.08%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 295.456 | 133.645 | -161.812 KiB (-54.77%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.557 | 0.481 | -0.076 ms (-13.65%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.810 | 0.679 | -0.130 ms (-16.09%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 5.037 | 4.293 | -0.744 ms (-14.78%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 39189.752 | 46008.297 | +6818.545 roots/s (+17.40%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 5.550 | 4.856 | -0.694 ms (-12.50%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 36620.533 | 41395.363 | +4774.830 roots/s (+13.04%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 8.106 | 7.035 | -1.071 ms (-13.21%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 25150.773 | 28795.105 | +3644.332 roots/s (+14.49%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 231.412 | 154.026 | -77.386 KiB (-33.44%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 45.315 | 43.581 | -1.734 KiB (-3.83%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 85.505 | 70.605 | -14.899 KiB (-17.43%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 10.883 | 9.012 | -1.871 KiB (-17.19%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1289.925 | 1111.526 | -178.398 KiB (-13.83%) | 3 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.973 | 418.848 | -103.125 KiB (-19.76%) | 3 | smaller |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.728 | 0.705 | -0.023 ms (-3.16%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.043 | 1.089 | +0.045 ms (+4.33%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 8.686 | 7.781 | -0.905 ms (-10.42%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23203.202 | 25008.597 | +1805.395 roots/s (+7.78%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 9.410 | 8.502 | -0.908 ms (-9.65%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 21264.154 | 23076.480 | +1812.326 roots/s (+8.52%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 12.187 | 11.728 | -0.459 ms (-3.76%) | 9 | within noise |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 16571.096 | 17564.209 | +993.114 roots/s (+5.99%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 705.499 | 575.624 | -129.875 KiB (-18.41%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 31.946 | 27.556 | -4.391 KiB (-13.74%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 199.487 | 163.854 | -35.633 KiB (-17.86%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.491 | 4.486 | +0.995 KiB (+28.50%) | 6 | larger |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1717.600 | 1504.769 | -212.831 KiB (-12.39%) | 3 | smaller |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.690 | 766.512 | -103.179 KiB (-11.86%) | 3 | smaller |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.878 | 0.829 | -0.049 ms (-5.55%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.208 | 1.838 | -0.370 ms (-16.76%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 23.411 | 20.821 | -2.590 ms (-11.06%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 8490.962 | 9717.681 | +1226.719 roots/s (+14.45%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 24.175 | 21.154 | -3.021 ms (-12.50%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8296.388 | 9490.949 | +1194.561 roots/s (+14.40%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 27.044 | 23.924 | -3.120 ms (-11.54%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 7383.502 | 8311.631 | +928.128 roots/s (+12.57%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1143.415 | 915.995 | -227.420 KiB (-19.89%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 57.243 | 53.433 | -3.811 KiB (-6.66%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 307.840 | 258.652 | -49.188 KiB (-15.98%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 6.164 | 7.256 | +1.092 KiB (+17.71%) | 6 | larger |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1280.452 | 1272.241 | -8.211 KiB (-0.64%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 545.004 | 441.879 | -103.125 KiB (-18.92%) | 3 | smaller |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.848 | 0.792 | -0.056 ms (-6.55%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.513 | 1.353 | -0.160 ms (-10.55%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 16.584 | 16.138 | -0.446 ms (-2.69%) | 9 | within noise |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 12235.066 | 13017.655 | +782.589 roots/s (+6.40%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 16.216 | 14.679 | -1.538 ms (-9.48%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12351.938 | 13614.704 | +1262.766 roots/s (+10.22%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 19.307 | 17.863 | -1.444 ms (-7.48%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10478.221 | 11132.887 | +654.666 roots/s (+6.25%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1139.675 | 1027.323 | -112.352 KiB (-9.86%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 40.712 | 36.142 | -4.570 KiB (-11.23%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 313.190 | 275.261 | -37.930 KiB (-12.11%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 3.812 | 5.111 | +1.300 KiB (+34.10%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 302.880 | 246.513 | -56.367 KiB (-18.61%) | 3 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.809 | 104.621 | -67.188 KiB (-39.11%) | 3 | smaller |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.490 | 0.454 | -0.036 ms (-7.40%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.725 | 0.620 | -0.105 ms (-14.52%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.342 | 4.675 | -0.667 ms (-12.49%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 36814.338 | 42113.021 | +5298.683 roots/s (+14.39%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 5.921 | 5.192 | -0.729 ms (-12.32%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 33828.784 | 37474.819 | +3646.035 roots/s (+10.78%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 8.434 | 7.451 | -0.983 ms (-11.66%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 24077.167 | 26787.658 | +2710.490 roots/s (+11.26%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 193.528 | 148.924 | -44.604 KiB (-23.05%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 27.891 | 32.499 | +4.608 KiB (+16.52%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 69.677 | 63.119 | -6.558 KiB (-9.41%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 1.921 | 2.805 | +0.884 KiB (+46.01%) | 6 | larger |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.222 | 4.587 | -1.635 us/projection (-26.27%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 161803.707 | 207848.210 | +46044.503 projections/s (+28.46%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.348 | 35.277 | -8.070 KiB (-18.62%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 47.183 | 41.591 | -5.592 KiB (-11.85%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 566.688 | 402.938 | -163.750 B/projection (-28.90%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 126.875 | 161.500 | +34.625 B/projection (+27.29%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.398 | 5.480 | -1.917 us/projection (-25.92%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 133425.897 | 184926.214 | +51500.317 projections/s (+38.60%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 47.434 | 34.973 | -12.461 KiB (-26.27%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 61.369 | 56.559 | -4.811 KiB (-7.84%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 581.688 | 402.938 | -178.750 B/projection (-30.73%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 177.250 | 156.625 | -20.625 B/projection (-11.64%) | 3 | smaller |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.701 | 8.059 | -0.642 ms (-7.38%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 22735.778 | 23580.039 | +844.262 roots/s (+3.71%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.740 | 9.045 | -0.695 ms (-7.14%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20701.077 | 22185.759 | +1484.681 roots/s (+7.17%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.881 | 15.588 | -1.293 ms (-7.66%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 12089.919 | 12964.634 | +874.715 roots/s (+7.24%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 16.878 | 15.658 | -1.220 ms (-7.23%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 11744.872 | 12692.671 | +947.799 roots/s (+8.07%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 32.358 | 30.451 | -1.908 us/root (-5.90%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 99.004 | 92.527 | -6.477 KiB (-6.54%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.852 | 48.102 | -2.750 KiB (-5.41%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 34.210 | 30.927 | -3.283 us/root (-9.60%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 103.316 | 97.816 | -5.500 KiB (-5.32%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.852 | 48.102 | -2.750 KiB (-5.41%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 47.181 | 45.365 | -1.816 us/root (-3.85%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 147.043 | 140.879 | -6.164 KiB (-4.19%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.977 | 85.227 | -2.750 KiB (-3.13%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 48.129 | 45.284 | -2.845 us/root (-5.91%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 150.992 | 145.562 | -5.430 KiB (-3.60%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.977 | 85.227 | -2.750 KiB (-3.13%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 65.573 | 65.116 | -0.457 us/root (-0.70%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 218.461 | 213.141 | -5.320 KiB (-2.44%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.477 | 134.727 | -2.750 KiB (-2.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 66.971 | 66.570 | -0.401 us/root (-0.60%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 221.883 | 216.805 | -5.078 KiB (-2.29%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.477 | 134.727 | -2.750 KiB (-2.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 24.328 | 22.576 | -1.753 us/root (-7.20%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 62.293 | 56.250 | -6.043 KiB (-9.70%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.102 | 21.352 | -2.750 KiB (-11.41%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 24.643 | 22.458 | -2.185 us/root (-8.87%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 68.605 | 63.391 | -5.215 KiB (-7.60%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.102 | 21.352 | -2.750 KiB (-11.41%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 152.691 | 149.901 | -2.790 us/root (-1.83%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 625.758 | 619.754 | -6.004 KiB (-0.96%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.102 | 425.352 | -2.750 KiB (-0.64%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 151.609 | 152.038 | +0.428 us/root (+0.28%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 629.699 | 624.512 | -5.188 KiB (-0.82%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.102 | 425.352 | -2.750 KiB (-0.64%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 57.185 | 54.430 | -2.755 us/root (-4.82%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 195.082 | 189.039 | -6.043 KiB (-3.10%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.102 | 122.352 | -2.750 KiB (-2.20%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 56.809 | 55.426 | -1.383 us/root (-2.43%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 198.129 | 192.926 | -5.203 KiB (-2.63%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.102 | 122.352 | -2.750 KiB (-2.20%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 46.348 | 47.905 | +1.557 us/root (+3.36%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 128.688 | 122.391 | -6.298 KiB (-4.89%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.945 | 33.195 | -2.750 KiB (-7.65%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 47.410 | 47.475 | +0.065 us/root (+0.14%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 133.001 | 127.719 | -5.282 KiB (-3.97%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.945 | 33.195 | -2.750 KiB (-7.65%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 55.465 | 53.928 | -1.536 us/root (-2.77%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 219.008 | 212.914 | -6.094 KiB (-2.78%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.727 | 133.977 | -2.750 KiB (-2.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 56.281 | 53.911 | -2.370 us/root (-4.21%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 222.836 | 217.594 | -5.242 KiB (-2.35%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.727 | 133.977 | -2.750 KiB (-2.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 143.681 | 144.549 | +0.868 us/root (+0.60%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 761.578 | 755.484 | -6.094 KiB (-0.80%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.227 | 477.477 | -2.750 KiB (-0.57%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 145.512 | 154.578 | +9.066 us/root (+6.23%) | 9 | slower |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 765.406 | 760.164 | -5.242 KiB (-0.68%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.227 | 477.477 | -2.750 KiB (-0.57%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 253.125 | 272.500 | +19.375 us (+7.65%) | 9 | slower |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 37.383 | 29.957 | -7.426 KiB (-19.86%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 28.672 | 21.801 | -6.871 KiB (-23.96%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 366.959 | 357.666 | -9.293 us (-2.53%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 50.452 | 39.827 | -10.625 KiB (-21.06%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 40.022 | 30.296 | -9.727 KiB (-24.30%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 488.292 | 464.875 | -23.417 us (-4.80%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 62.865 | 49.057 | -13.809 KiB (-21.97%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 50.850 | 38.268 | -12.582 KiB (-24.74%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 89.500 | 93.708 | +4.208 us (+4.70%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 20.526 | 18.269 | -2.258 KiB (-11.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 13.761 | 10.979 | -2.781 KiB (-20.21%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 89.542 | 87.333 | -2.209 us (-2.47%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 20.432 | 18.279 | -2.152 KiB (-10.53%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 13.916 | 11.244 | -2.672 KiB (-19.20%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 87.875 | 84.709 | -3.166 us (-3.60%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 20.526 | 18.269 | -2.258 KiB (-11.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 13.761 | 10.979 | -2.781 KiB (-20.21%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 90.208 | 87.916 | -2.292 us (-2.54%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 20.432 | 18.283 | -2.148 KiB (-10.52%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 13.916 | 11.244 | -2.672 KiB (-19.20%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 90.666 | 87.958 | -2.708 us (-2.99%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 20.527 | 18.270 | -2.258 KiB (-11.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 13.762 | 10.980 | -2.781 KiB (-20.21%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 91.292 | 87.708 | -3.584 us (-3.93%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 20.433 | 18.284 | -2.148 KiB (-10.51%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 13.917 | 11.245 | -2.672 KiB (-19.20%) | 3 | smaller |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 11.333 | 2.291 | -9.042 us (-79.78%) | 9 | faster |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 15.625 | 2.750 | -12.875 us (-82.40%) | 9 | faster |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 19.958 | 3.291 | -16.667 us (-83.51%) | 9 | faster |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.closed.retainedKiB | 71.484 | 68.234 | -3.250 KiB (-4.55%) | 3 | smaller |
| 3.13 | result-held-metadata | control-held | large.shared.retainedKiB | 50.789 | 47.539 | -3.250 KiB (-6.40%) | 3 | smaller |
| 3.13 | result-held-metadata | control-held | small.closed.retainedKiB | 118.438 | 98.938 | -19.500 KiB (-16.46%) | 3 | smaller |
| 3.13 | result-held-metadata | control-held | small.shared.retainedKiB | 111.070 | 91.570 | -19.500 KiB (-17.56%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 10078.291 | 8436.500 | -1641.791 us (-16.29%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1353.777 | 1203.014 | -150.764 KiB (-11.14%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 741.773 | 610.523 | -131.250 KiB (-17.69%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 102325.083 | 83852.958 | -18472.125 us (-18.05%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 13108.117 | 11596.275 | -1511.842 KiB (-11.53%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 7416.219 | 6103.719 | -1312.500 KiB (-17.70%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 22166.000 | 16754.167 | -5411.833 us (-24.42%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 176.418 | 146.013 | -30.405 KiB (-17.23%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.700 | 3.044 | -0.656 KiB (-17.74%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 118863.334 | 97825.125 | -21038.209 us (-17.70%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 181.324 | 152.325 | -28.999 KiB (-15.99%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.731 | 3.075 | -0.656 KiB (-17.59%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8574.208 | 7084.417 | -1489.791 us (-17.38%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1183.411 | 1049.976 | -133.436 KiB (-11.28%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 487.230 | 374.730 | -112.500 KiB (-23.09%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 84907.166 | 70427.417 | -14479.749 us (-17.05%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11348.603 | 10022.753 | -1325.850 KiB (-11.68%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4869.488 | 3744.488 | -1125.000 KiB (-23.10%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 20663.500 | 14995.083 | -5668.417 us (-27.43%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 178.630 | 149.850 | -28.780 KiB (-16.11%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.571 | 2.009 | -0.562 KiB (-21.88%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 104313.167 | 89648.666 | -14664.501 us (-14.06%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 180.536 | 151.756 | -28.780 KiB (-15.94%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.603 | 2.040 | -0.562 KiB (-21.61%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 18634.375 | 15795.625 | -2838.750 us (-15.23%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1297.602 | 1256.340 | -41.262 KiB (-3.18%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 758.961 | 627.711 | -131.250 KiB (-17.29%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 186578.541 | 158185.458 | -28393.083 us (-15.22%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12963.753 | 12557.527 | -406.226 KiB (-3.13%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7588.094 | 6275.594 | -1312.500 KiB (-17.30%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 30258.750 | 22884.000 | -7374.750 us (-24.37%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 283.668 | 252.505 | -31.163 KiB (-10.99%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.786 | 3.130 | -0.656 KiB (-17.33%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 196406.625 | 162607.000 | -33799.625 us (-17.21%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 287.590 | 257.833 | -29.757 KiB (-10.35%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.817 | 3.161 | -0.656 KiB (-17.19%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 16756.292 | 14235.000 | -2521.292 us (-15.05%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1265.931 | 1257.033 | -8.897 KiB (-0.70%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 510.668 | 398.168 | -112.500 KiB (-22.03%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 164455.250 | 149873.584 | -14581.666 us (-8.87%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12964.446 | 12558.221 | -406.226 KiB (-3.13%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5103.863 | 3978.863 | -1125.000 KiB (-22.04%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 27902.750 | 22314.375 | -5588.375 us (-20.03%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 282.653 | 253.014 | -29.640 KiB (-10.49%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.688 | 2.126 | -0.562 KiB (-20.92%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 179903.500 | 150020.709 | -29882.791 us (-16.61%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 284.216 | 254.514 | -29.702 KiB (-10.45%) | 3 | smaller |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.720 | 2.157 | -0.562 KiB (-20.68%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6034.583 | 4990.583 | -1044.000 us (-17.30%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 402.667 | 348.185 | -54.482 KiB (-13.53%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 245.097 | 201.019 | -44.078 KiB (-17.98%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 870.084 | 727.666 | -142.418 us (-16.37%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 70.104 | 61.504 | -8.600 KiB (-12.27%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 34.177 | 28.630 | -5.547 KiB (-16.23%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4499.875 | 3843.917 | -655.958 us (-14.58%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 360.000 | 312.854 | -47.146 KiB (-13.10%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 190.003 | 152.925 | -37.078 KiB (-19.51%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 693.583 | 592.958 | -100.625 us (-14.51%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 61.960 | 54.595 | -7.365 KiB (-11.89%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.606 | 18.919 | -4.688 KiB (-19.86%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8947.042 | 7936.542 | -1010.500 us (-11.29%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 531.295 | 469.438 | -61.857 KiB (-11.64%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 317.237 | 261.519 | -55.719 KiB (-17.56%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1324.541 | 1251.667 | -72.874 us (-5.50%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 86.798 | 77.737 | -9.061 KiB (-10.44%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 42.489 | 35.435 | -7.055 KiB (-16.60%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6811.833 | 5901.791 | -910.042 us (-13.36%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 496.995 | 446.466 | -50.529 KiB (-10.17%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 261.722 | 217.050 | -44.672 KiB (-17.07%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 1031.750 | 890.125 | -141.625 us (-13.73%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 81.553 | 73.828 | -7.725 KiB (-9.47%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.903 | 27.231 | -5.672 KiB (-17.24%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 11008.375 | 9456.292 | -1552.083 us (-14.10%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 686.104 | 603.621 | -82.482 KiB (-12.02%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 415.769 | 343.972 | -71.797 KiB (-17.27%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1576.167 | 1354.250 | -221.917 us (-14.08%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 106.569 | 93.884 | -12.686 KiB (-11.90%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 54.958 | 45.872 | -9.086 KiB (-16.53%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8692.333 | 7446.833 | -1245.500 us (-14.33%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 638.780 | 570.142 | -68.639 KiB (-10.75%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 339.104 | 281.354 | -57.750 KiB (-17.03%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1307.042 | 1121.625 | -185.417 us (-14.19%) | 9 | faster |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 100.372 | 89.460 | -10.912 KiB (-10.87%) | 3 | smaller |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.911 | 35.599 | -7.312 KiB (-17.04%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 386.686 | 245.376 | -141.310 KiB (-36.54%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 299.688 | 132.455 | -167.233 KiB (-55.80%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.523 | 0.518 | -0.005 ms (-0.95%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.811 | 0.661 | -0.150 ms (-18.46%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 5.163 | 4.084 | -1.079 ms (-20.90%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 39521.786 | 49174.290 | +9652.504 roots/s (+24.42%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 5.715 | 4.529 | -1.185 ms (-20.74%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 35831.320 | 45147.145 | +9315.825 roots/s (+26.00%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 8.106 | 6.645 | -1.461 ms (-18.02%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 24774.963 | 29932.466 | +5157.504 roots/s (+20.82%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 214.543 | 159.319 | -55.224 KiB (-25.74%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 40.480 | 39.667 | -0.813 KiB (-2.01%) | 6 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 77.941 | 66.470 | -11.472 KiB (-14.72%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 15.609 | 11.367 | -4.242 KiB (-27.18%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1224.021 | 1091.086 | -132.936 KiB (-10.86%) | 3 | smaller |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.383 | 418.883 | -112.500 KiB (-21.17%) | 3 | smaller |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.743 | 0.565 | -0.178 ms (-23.95%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.116 | 0.913 | -0.203 ms (-18.20%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 8.673 | 7.200 | -1.472 ms (-16.98%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 22885.586 | 27757.538 | +4871.952 roots/s (+21.29%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 9.525 | 7.639 | -1.886 ms (-19.80%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 21040.913 | 25732.849 | +4691.936 roots/s (+22.30%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 12.411 | 9.834 | -2.577 ms (-20.77%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 15829.411 | 20051.215 | +4221.804 roots/s (+26.67%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 667.924 | 571.597 | -96.327 KiB (-14.42%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 34.473 | 29.325 | -5.147 KiB (-14.93%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 191.596 | 162.628 | -28.968 KiB (-15.12%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.597 | 4.545 | +0.948 KiB (+26.36%) | 6 | larger |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1770.636 | 1477.900 | -292.735 KiB (-16.53%) | 3 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.759 | 771.251 | -112.508 KiB (-12.73%) | 3 | smaller |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.856 | 0.748 | -0.108 ms (-12.64%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.203 | 1.789 | -0.413 ms (-18.77%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 23.307 | 19.067 | -4.240 ms (-18.19%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 8507.848 | 10469.194 | +1961.346 roots/s (+23.05%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 24.139 | 20.141 | -3.998 ms (-16.56%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8232.344 | 10092.642 | +1860.298 roots/s (+22.60%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 27.603 | 22.780 | -4.823 ms (-17.47%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 7312.481 | 8816.706 | +1504.226 roots/s (+20.57%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1177.754 | 944.572 | -233.182 KiB (-19.80%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 58.687 | 54.428 | -4.259 KiB (-7.26%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 317.093 | 265.509 | -51.584 KiB (-16.27%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 6.336 | 7.330 | +0.994 KiB (+15.69%) | 6 | larger |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1347.291 | 1338.964 | -8.327 KiB (-0.62%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.414 | 441.914 | -112.500 KiB (-20.29%) | 3 | smaller |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.857 | 0.858 | +0.000 ms (+0.03%) | 9 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.610 | 1.443 | -0.166 ms (-10.34%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 16.680 | 14.170 | -2.509 ms (-15.04%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 11941.249 | 14073.976 | +2132.728 roots/s (+17.86%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 17.392 | 13.853 | -3.539 ms (-20.35%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12470.026 | 14385.643 | +1915.617 roots/s (+15.36%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 19.528 | 17.265 | -2.263 ms (-11.59%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10288.308 | 11624.247 | +1335.938 roots/s (+12.99%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1145.486 | 1033.448 | -112.038 KiB (-9.78%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 43.727 | 38.556 | -5.171 KiB (-11.83%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 307.869 | 278.679 | -29.190 KiB (-9.48%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 3.948 | 5.201 | +1.253 KiB (+31.73%) | 6 | larger |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 278.097 | 196.410 | -81.687 KiB (-29.37%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 174.946 | 104.688 | -70.259 KiB (-40.16%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.491 | 0.454 | -0.037 ms (-7.55%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.722 | 0.618 | -0.103 ms (-14.33%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 5.518 | 4.404 | -1.115 ms (-20.20%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 36853.622 | 45319.781 | +8466.159 roots/s (+22.97%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 5.947 | 5.067 | -0.880 ms (-14.80%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 33536.413 | 40685.552 | +7149.138 roots/s (+21.32%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 8.635 | 7.349 | -1.286 ms (-14.89%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 23533.565 | 27443.312 | +3909.748 roots/s (+16.61%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 200.928 | 153.020 | -47.908 KiB (-23.84%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 28.921 | 27.016 | -1.905 KiB (-6.59%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 67.291 | 58.934 | -8.357 KiB (-12.42%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 1.944 | 2.863 | +0.919 KiB (+47.26%) | 6 | larger |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.143 | 4.207 | -1.936 us/projection (-31.51%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 164736.163 | 234432.249 | +69696.086 projections/s (+42.31%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.496 | 36.918 | -8.578 KiB (-18.85%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 51.560 | 45.772 | -5.787 KiB (-11.22%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 599.672 | 419.938 | -179.734 B/projection (-29.97%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 128.266 | 170.750 | +42.484 B/projection (+33.12%) | 3 | larger |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.661 | 5.003 | -2.658 us/projection (-34.70%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 131788.931 | 200548.365 | +68759.434 projections/s (+52.17%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 49.652 | 36.613 | -13.039 KiB (-26.26%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 66.832 | 61.943 | -4.889 KiB (-7.31%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 615.672 | 419.938 | -195.734 B/projection (-31.79%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 178.766 | 165.875 | -12.891 B/projection (-7.21%) | 3 | smaller |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.821 | 7.387 | -1.435 ms (-16.26%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 22435.044 | 27269.162 | +4834.119 roots/s (+21.55%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.798 | 8.121 | -1.677 ms (-17.11%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20345.880 | 24488.047 | +4142.167 roots/s (+20.36%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.921 | 14.426 | -2.495 ms (-14.74%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 11830.032 | 13886.880 | +2056.848 roots/s (+17.39%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 17.183 | 14.503 | -2.680 ms (-15.60%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 11518.111 | 13763.875 | +2245.763 roots/s (+19.50%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-boolean | columns.elapsedUsPerRoot | 110.827 | 103.276 | -7.551 us/root (-6.81%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-boolean | columns.peakKiB | 447.188 | 439.901 | -7.287 KiB (-1.63%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.retainedKiB | 162.484 | 159.484 | -3.000 KiB (-1.85%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.elapsedUsPerRoot | 112.803 | 103.137 | -9.667 us/root (-8.57%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-boolean | document.peakKiB | 451.212 | 444.925 | -6.287 KiB (-1.39%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.retainedKiB | 162.484 | 159.484 | -3.000 KiB (-1.85%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.elapsedUsPerRoot | 399.061 | 350.977 | -48.085 us/root (-12.05%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-bytes | columns.peakKiB | 954.355 | 947.990 | -6.365 KiB (-0.67%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.retainedKiB | 313.047 | 310.047 | -3.000 KiB (-0.96%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.elapsedUsPerRoot | 403.560 | 354.074 | -49.486 us/root (-12.26%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-bytes | document.peakKiB | 958.113 | 951.490 | -6.623 KiB (-0.69%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.retainedKiB | 313.047 | 310.047 | -3.000 KiB (-0.96%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.elapsedUsPerRoot | 427.151 | 386.794 | -40.357 us/root (-9.45%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-date | columns.peakKiB | 773.853 | 767.776 | -6.076 KiB (-0.79%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.retainedKiB | 192.965 | 189.965 | -3.000 KiB (-1.55%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.elapsedUsPerRoot | 429.876 | 432.684 | +2.807 us/root (+0.65%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.peakKiB | 777.649 | 771.315 | -6.334 KiB (-0.81%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.retainedKiB | 192.965 | 189.965 | -3.000 KiB (-1.55%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.elapsedUsPerRoot | 935.033 | 872.038 | -62.995 us/root (-6.74%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-decimal | columns.peakKiB | 1300.483 | 1293.759 | -6.725 KiB (-0.52%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.retainedKiB | 271.797 | 268.797 | -3.000 KiB (-1.10%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.elapsedUsPerRoot | 938.210 | 859.160 | -79.049 us/root (-8.43%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-decimal | document.peakKiB | 1304.312 | 1297.587 | -6.725 KiB (-0.52%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.retainedKiB | 271.797 | 268.797 | -3.000 KiB (-1.10%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.elapsedUsPerRoot | 811.590 | 740.673 | -70.917 us/root (-8.74%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float32 | columns.peakKiB | 691.443 | 685.078 | -6.365 KiB (-0.92%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.retainedKiB | 211.984 | 208.984 | -3.000 KiB (-1.42%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.elapsedUsPerRoot | 811.738 | 744.378 | -67.361 us/root (-8.30%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float32 | document.peakKiB | 695.201 | 688.578 | -6.623 KiB (-0.95%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.retainedKiB | 211.984 | 208.984 | -3.000 KiB (-1.42%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.elapsedUsPerRoot | 322.350 | 279.826 | -42.525 us/root (-13.19%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-float64 | columns.peakKiB | 657.537 | 651.172 | -6.365 KiB (-0.97%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.retainedKiB | 211.984 | 208.984 | -3.000 KiB (-1.42%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.elapsedUsPerRoot | 318.831 | 340.111 | +21.280 us/root (+6.67%) | 9 | slower |
| 3.14 | provider-free-delivery | leaf-float64 | document.peakKiB | 661.295 | 654.672 | -6.623 KiB (-1.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.retainedKiB | 211.984 | 208.984 | -3.000 KiB (-1.42%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.elapsedUsPerRoot | 159.543 | 144.773 | -14.770 us/root (-9.26%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int32 | columns.peakKiB | 639.337 | 632.050 | -7.287 KiB (-1.14%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.retainedKiB | 354.480 | 351.480 | -3.000 KiB (-0.85%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.elapsedUsPerRoot | 158.440 | 144.806 | -13.634 us/root (-8.61%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int32 | document.peakKiB | 643.360 | 637.073 | -6.287 KiB (-0.98%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.retainedKiB | 354.480 | 351.480 | -3.000 KiB (-0.85%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.elapsedUsPerRoot | 165.767 | 150.198 | -15.569 us/root (-9.39%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int64 | columns.peakKiB | 651.306 | 644.019 | -7.287 KiB (-1.12%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.retainedKiB | 366.484 | 363.484 | -3.000 KiB (-0.82%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.elapsedUsPerRoot | 164.014 | 150.216 | -13.798 us/root (-8.41%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-int64 | document.peakKiB | 655.329 | 649.042 | -6.287 KiB (-0.96%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.retainedKiB | 366.484 | 363.484 | -3.000 KiB (-0.82%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.elapsedUsPerRoot | 567.331 | 505.074 | -62.257 us/root (-10.97%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-time | columns.peakKiB | 829.834 | 823.469 | -6.365 KiB (-0.77%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.retainedKiB | 277.984 | 274.984 | -3.000 KiB (-1.08%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.elapsedUsPerRoot | 570.586 | 508.408 | -62.178 us/root (-10.90%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-time | document.peakKiB | 833.592 | 826.969 | -6.623 KiB (-0.79%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.retainedKiB | 277.984 | 274.984 | -3.000 KiB (-1.08%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.elapsedUsPerRoot | 1007.112 | 755.023 | -252.089 us/root (-25.03%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.peakKiB | 933.672 | 930.834 | -2.838 KiB (-0.30%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.retainedKiB | 302.832 | 301.736 | -1.096 KiB (-0.36%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.elapsedUsPerRoot | 1002.125 | 757.583 | -244.542 us/root (-24.40%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-timestamp | document.peakKiB | 937.430 | 931.648 | -5.781 KiB (-0.62%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.retainedKiB | 303.223 | 299.734 | -3.488 KiB (-1.15%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.elapsedUsPerRoot | 572.010 | 528.056 | -43.954 us/root (-7.68%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-uuid | columns.peakKiB | 1279.028 | 1272.265 | -6.764 KiB (-0.53%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.retainedKiB | 321.297 | 318.297 | -3.000 KiB (-0.93%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.elapsedUsPerRoot | 575.331 | 547.742 | -27.589 us/root (-4.80%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.peakKiB | 1282.856 | 1276.022 | -6.834 KiB (-0.53%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.retainedKiB | 321.297 | 318.297 | -3.000 KiB (-0.93%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 32.935 | 28.589 | -4.346 us/root (-13.20%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 97.325 | 90.562 | -6.764 KiB (-6.95%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.109 | 48.109 | -3.000 KiB (-5.87%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 33.327 | 28.482 | -4.845 us/root (-14.54%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 101.036 | 94.202 | -6.834 KiB (-6.76%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.109 | 48.109 | -3.000 KiB (-5.87%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 49.228 | 42.766 | -6.462 us/root (-13.13%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 148.214 | 142.028 | -6.186 KiB (-4.17%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.234 | 85.234 | -3.000 KiB (-3.40%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 50.056 | 42.562 | -7.494 us/root (-14.97%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 151.401 | 145.364 | -6.037 KiB (-3.99%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.234 | 85.234 | -3.000 KiB (-3.40%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 68.637 | 60.348 | -8.289 us/root (-12.08%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 223.218 | 217.618 | -5.600 KiB (-2.51%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.734 | 134.734 | -3.000 KiB (-2.18%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 69.491 | 60.781 | -8.710 us/root (-12.53%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 227.249 | 221.524 | -5.725 KiB (-2.52%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.734 | 134.734 | -3.000 KiB (-2.18%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 24.827 | 20.488 | -4.339 us/root (-17.48%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 61.062 | 53.623 | -7.439 KiB (-12.18%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.359 | 21.359 | -3.000 KiB (-12.32%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 25.079 | 20.398 | -4.681 us/root (-18.66%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 67.422 | 60.990 | -6.432 KiB (-9.54%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.359 | 21.359 | -3.000 KiB (-12.32%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 155.384 | 151.094 | -4.290 us/root (-2.76%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 629.829 | 622.698 | -7.131 KiB (-1.13%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.359 | 425.359 | -3.000 KiB (-0.70%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 157.099 | 140.975 | -16.124 us/root (-10.26%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 633.739 | 627.507 | -6.232 KiB (-0.98%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.359 | 425.359 | -3.000 KiB (-0.70%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 58.341 | 51.773 | -6.568 us/root (-11.26%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 198.134 | 190.972 | -7.162 KiB (-3.61%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.359 | 122.359 | -3.000 KiB (-2.39%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 59.613 | 51.677 | -7.936 us/root (-13.31%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 201.552 | 195.390 | -6.162 KiB (-3.06%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.359 | 122.359 | -3.000 KiB (-2.39%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 47.898 | 44.294 | -3.604 us/root (-7.52%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 127.213 | 120.545 | -6.668 KiB (-5.24%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.203 | 33.203 | -3.000 KiB (-8.29%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 50.958 | 44.324 | -6.634 us/root (-13.02%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 130.924 | 124.225 | -6.699 KiB (-5.12%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.203 | 33.203 | -3.000 KiB (-8.29%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 56.552 | 49.687 | -6.865 us/root (-12.14%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 222.470 | 215.183 | -7.287 KiB (-3.28%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.984 | 133.984 | -3.000 KiB (-2.19%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 56.302 | 49.824 | -6.478 us/root (-11.51%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 226.376 | 220.089 | -6.287 KiB (-2.78%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.984 | 133.984 | -3.000 KiB (-2.19%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 148.523 | 133.557 | -14.966 us/root (-10.08%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 765.188 | 757.901 | -7.287 KiB (-0.95%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.484 | 477.484 | -3.000 KiB (-0.62%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 147.060 | 132.089 | -14.971 us/root (-10.18%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 769.095 | 762.808 | -6.287 KiB (-0.82%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.484 | 477.484 | -3.000 KiB (-0.62%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 258.583 | 232.667 | -25.916 us (-10.02%) | 9 | faster |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 37.547 | 30.238 | -7.309 KiB (-19.47%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 29.992 | 22.730 | -7.262 KiB (-24.21%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 379.709 | 342.417 | -37.292 us (-9.82%) | 9 | faster |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 50.483 | 40.038 | -10.445 KiB (-20.69%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 41.921 | 31.601 | -10.320 KiB (-24.62%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 498.875 | 443.000 | -55.875 us (-11.20%) | 9 | faster |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 62.709 | 48.908 | -13.801 KiB (-22.01%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 53.326 | 39.947 | -13.379 KiB (-25.09%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 91.583 | 81.792 | -9.791 us (-10.69%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 21.005 | 18.310 | -2.695 KiB (-12.83%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.981 | 11.888 | -3.094 KiB (-20.65%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 93.292 | 84.666 | -8.626 us (-9.25%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 21.168 | 18.457 | -2.711 KiB (-12.81%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 15.145 | 12.176 | -2.969 KiB (-19.60%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 91.458 | 82.042 | -9.416 us (-10.30%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 21.005 | 18.310 | -2.695 KiB (-12.83%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.981 | 11.888 | -3.094 KiB (-20.65%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 93.875 | 85.291 | -8.584 us (-9.14%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 21.164 | 18.457 | -2.707 KiB (-12.79%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 15.145 | 12.176 | -2.969 KiB (-19.60%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 91.875 | 81.333 | -10.542 us (-11.47%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 21.006 | 18.311 | -2.695 KiB (-12.83%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.982 | 11.889 | -3.094 KiB (-20.65%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 93.000 | 84.208 | -8.792 us (-9.45%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 21.169 | 18.458 | -2.711 KiB (-12.81%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 15.146 | 12.177 | -2.969 KiB (-19.60%) | 3 | smaller |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 15.166 | 1.917 | -13.249 us (-87.36%) | 9 | faster |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 20.959 | 2.250 | -18.709 us (-89.26%) | 9 | faster |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 26.959 | 2.709 | -24.250 us (-89.95%) | 9 | faster |
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
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 210.416 | 173.000 | -37.416 us/row (-17.78%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 1432.000 | 840.000 | -592.000 B/row (-41.34%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 10866.000 | 9028.000 | -1838.000 B/row (-16.92%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 212.083 | 174.833 | -37.250 us/row (-17.56%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 1432.000 | 840.000 | -592.000 B/row (-41.34%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 11114.000 | 10005.000 | -1109.000 B/row (-9.98%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 315.250 | 220.458 | -94.792 us/row (-30.07%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 1432.000 | 840.000 | -592.000 B/row (-41.34%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 8956.000 | 7402.000 | -1554.000 B/row (-17.35%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 289.541 | 193.333 | -96.208 us/row (-33.23%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 1432.000 | 840.000 | -592.000 B/row (-41.34%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 9201.000 | 8123.000 | -1078.000 B/row (-11.72%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 357.667 | 231.292 | -126.375 us/row (-35.33%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1712.000 | 1120.000 | -592.000 B/row (-34.58%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 12574.000 | 11792.000 | -782.000 B/row (-6.22%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 339.000 | 209.708 | -129.292 us/row (-38.14%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1712.000 | 1120.000 | -592.000 B/row (-34.58%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13350.000 | 12850.000 | -500.000 B/row (-3.75%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 936.833 | 452.292 | -484.541 us/row (-51.72%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2832.000 | 2240.000 | -592.000 B/row (-20.90%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 20857.000 | 20108.000 | -749.000 B/row (-3.59%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 860.292 | 360.750 | -499.542 us/row (-58.07%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2832.000 | 2240.000 | -592.000 B/row (-20.90%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23890.000 | 23390.000 | -500.000 B/row (-2.09%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 287.250 | 261.709 | -25.541 us/row (-8.89%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 2160.000 | 1616.000 | -544.000 B/row (-25.19%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15296.000 | 18635.000 | +3339.000 B/row (+21.83%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 282.958 | 253.083 | -29.875 us/row (-10.56%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 2288.000 | 1648.000 | -640.000 B/row (-27.97%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16140.000 | 19095.000 | +2955.000 B/row (+18.31%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 283.625 | 259.208 | -24.417 us/row (-8.61%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 2160.000 | 1616.000 | -544.000 B/row (-25.19%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15481.000 | 17830.000 | +2349.000 B/row (+15.17%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 276.875 | 251.417 | -25.458 us/row (-9.19%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 2288.000 | 1648.000 | -640.000 B/row (-27.97%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 16221.000 | 18274.000 | +2053.000 B/row (+12.66%) | 9 | larger |
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
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 111.708 | 124.833 | +13.125 us/row (+11.75%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1648.000 | 1544.000 | -104.000 B/row (-6.31%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 8580.000 | 7892.000 | -688.000 B/row (-8.02%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 112.125 | 125.000 | +12.875 us/row (+11.48%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1648.000 | 1544.000 | -104.000 B/row (-6.31%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 8852.000 | 8292.000 | -560.000 B/row (-6.33%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 149.750 | 163.000 | +13.250 us/row (+8.85%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2320.000 | 2216.000 | -104.000 B/row (-4.48%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10341.000 | 9653.000 | -688.000 B/row (-6.65%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 145.459 | 159.916 | +14.457 us/row (+9.94%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2320.000 | 2216.000 | -104.000 B/row (-4.48%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 10497.000 | 9937.000 | -560.000 B/row (-5.33%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 194.375 | 209.209 | +14.834 us/row (+7.63%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3216.000 | 3112.000 | -104.000 B/row (-3.23%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 13466.000 | 12882.000 | -584.000 B/row (-4.34%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 194.375 | 211.291 | +16.916 us/row (+8.70%) | 9 | slower |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3216.000 | 3112.000 | -104.000 B/row (-3.23%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 13552.000 | 12992.000 | -560.000 B/row (-4.13%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 90.125 | 100.292 | +10.167 us/row (+11.28%) | 9 | slower |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1144.000 | 1040.000 | -104.000 B/row (-9.09%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7425.000 | 6857.000 | -568.000 B/row (-7.65%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 87.125 | 103.417 | +16.292 us/row (+18.70%) | 9 | slower |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1144.000 | 1040.000 | -104.000 B/row (-9.09%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 7447.000 | 7007.000 | -440.000 B/row (-5.91%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 420.833 | 436.583 | +15.750 us/row (+3.74%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8608.000 | 8504.000 | -104.000 B/row (-1.21%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27376.000 | 26816.000 | -560.000 B/row (-2.05%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 418.167 | 436.291 | +18.124 us/row (+4.33%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8608.000 | 8504.000 | -104.000 B/row (-1.21%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 27539.000 | 27107.000 | -432.000 B/row (-1.57%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 175.125 | 186.708 | +11.583 us/row (+6.61%) | 9 | slower |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3040.000 | 2936.000 | -104.000 B/row (-3.42%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 11920.000 | 11360.000 | -560.000 B/row (-4.70%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 173.167 | 188.666 | +15.499 us/row (+8.95%) | 9 | slower |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3040.000 | 2936.000 | -104.000 B/row (-3.42%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 12219.000 | 11684.000 | -535.000 B/row (-4.38%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 159.750 | 166.291 | +6.541 us/row (+4.09%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1648.000 | 1544.000 | -104.000 B/row (-6.31%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8350.000 | 7705.000 | -645.000 B/row (-7.72%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 156.042 | 169.042 | +13.000 us/row (+8.33%) | 9 | slower |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1648.000 | 1544.000 | -104.000 B/row (-6.31%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 8619.000 | 8089.000 | -530.000 B/row (-6.15%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 210.708 | 206.291 | -4.417 us/row (-2.10%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2488.000 | 2384.000 | -104.000 B/row (-4.18%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11360.000 | 10887.000 | -473.000 B/row (-4.16%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 190.833 | 207.416 | +16.583 us/row (+8.69%) | 9 | slower |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2488.000 | 2384.000 | -104.000 B/row (-4.18%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 11640.000 | 11328.000 | -312.000 B/row (-2.68%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 517.416 | 536.666 | +19.250 us/row (+3.72%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5848.000 | 5744.000 | -104.000 B/row (-1.78%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23567.000 | 23127.000 | -440.000 B/row (-1.87%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 515.958 | 534.708 | +18.750 us/row (+3.63%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5848.000 | 5744.000 | -104.000 B/row (-1.78%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 24984.000 | 24672.000 | -312.000 B/row (-1.25%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 156.291 | 128.375 | -27.916 us/row (-17.86%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 1968.000 | 1832.000 | -136.000 B/row (-6.91%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 9139.000 | 7237.000 | -1902.000 B/row (-20.81%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 142.458 | 118.000 | -24.458 us/row (-17.17%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 2000.000 | 1864.000 | -136.000 B/row (-6.80%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 9459.000 | 8085.000 | -1374.000 B/row (-14.53%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 161.750 | 138.167 | -23.583 us/row (-14.58%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 1968.000 | 1832.000 | -136.000 B/row (-6.91%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 9927.000 | 8161.000 | -1766.000 B/row (-17.79%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 148.167 | 126.958 | -21.209 us/row (-14.31%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 2000.000 | 1864.000 | -136.000 B/row (-6.80%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 10247.000 | 9009.000 | -1238.000 B/row (-12.08%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 193.125 | 181.084 | -12.041 us/row (-6.23%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 2160.000 | 1568.000 | -592.000 B/row (-27.41%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 11217.000 | 10306.000 | -911.000 B/row (-8.12%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 177.250 | 172.791 | -4.459 us/row (-2.52%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 2192.000 | 1600.000 | -592.000 B/row (-27.01%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 11517.000 | 10894.000 | -623.000 B/row (-5.41%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 202.459 | 197.334 | -5.125 us/row (-2.53%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 2160.000 | 1568.000 | -592.000 B/row (-27.41%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 11668.000 | 11500.000 | -168.000 B/row (-1.44%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 191.667 | 183.042 | -8.625 us/row (-4.50%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 2192.000 | 1600.000 | -592.000 B/row (-27.01%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 12096.000 | 11848.000 | -248.000 B/row (-2.05%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 116.541 | 125.291 | +8.750 us/row (+7.51%) | 9 | slower |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1872.000 | 1768.000 | -104.000 B/row (-5.56%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 10118.000 | 9851.000 | -267.000 B/row (-2.64%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 119.375 | 126.834 | +7.459 us/row (+6.25%) | 9 | slower |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1872.000 | 1960.000 | +88.000 B/row (+4.70%) | 1 | larger |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 10302.000 | 10211.000 | -91.000 B/row (-0.88%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 114.625 | 126.667 | +12.042 us/row (+10.51%) | 9 | slower |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 1872.000 | 1768.000 | -104.000 B/row (-5.56%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 10142.000 | 9574.000 | -568.000 B/row (-5.60%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 117.834 | 127.042 | +9.208 us/row (+7.81%) | 9 | slower |
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
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 87.083 | 34.292 | -52.791 us/row (-60.62%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 7168.000 | 3642.000 | -3526.000 B/row (-49.19%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 72.292 | 28.834 | -43.458 us/row (-60.11%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 7184.000 | 3502.000 | -3682.000 B/row (-51.25%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 87.542 | 34.084 | -53.458 us/row (-61.07%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 7168.000 | 3644.000 | -3524.000 B/row (-49.16%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 73.750 | 28.958 | -44.792 us/row (-60.73%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 7184.000 | 3505.000 | -3679.000 B/row (-51.21%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3374.875 | 3356.791 | -18.084 us (-0.54%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | retainedBytes | 426776.000 | 436748.000 | +9972.000 B (+2.34%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 438904.000 | 449012.000 | +10108.000 B (+2.30%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | 303.791 | 310.167 | +6.376 us (+2.10%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | 23472.000 | 24438.000 | +966.000 B (+4.12%) | 1 | larger |
| 3.13 | model-preparation | model.prepared.family | transientBytes | 27536.000 | 28798.000 | +1262.000 B (+4.58%) | 9 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 24.915 | 19.848 | -5.067 us/row (-20.34%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 911.875 | 924.125 | +12.250 B/row (+1.34%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 2003.484 | 1823.188 | -180.297 B/row (-9.00%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 25.822 | 20.999 | -4.823 us/row (-18.68%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1913.375 | 1925.625 | +12.250 B/row (+0.64%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2469.828 | 2222.328 | -247.500 B/row (-10.02%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 29.440 | 24.043 | -5.397 us/row (-18.33%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1032.500 | 1081.500 | +49.000 B/row (+4.75%) | 1 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2650.812 | 2266.375 | -384.438 B/row (-14.50%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 31.432 | 25.003 | -6.430 us/row (-20.46%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2038.500 | 2087.500 | +49.000 B/row (+2.40%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 3010.688 | 2588.688 | -422.000 B/row (-14.02%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 49.818 | 42.750 | -7.068 us/row (-14.19%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1523.000 | 1719.000 | +196.000 B/row (+12.87%) | 1 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 4640.250 | 3734.500 | -905.750 B/row (-19.52%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 49.557 | 42.208 | -7.349 us/row (-14.83%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2547.000 | 2743.000 | +196.000 B/row (+7.70%) | 1 | larger |
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
| 3.13 | wire-insert-response | response.insert.family.wire | elapsedUs | 63.292 | 64.584 | +1.292 us/row (+2.04%) | 9 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | retainedBytes | 7528.000 | 9312.000 | +1784.000 B/row (+23.70%) | 1 | larger |
| 3.13 | wire-insert-response | response.insert.family.wire | transientBytes | 7616.000 | 7696.000 | +80.000 B/row (+1.05%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 235.292 | 189.958 | -45.334 us/row (-19.27%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 1440.000 | 848.000 | -592.000 B/row (-41.11%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 11034.000 | 9708.000 | -1326.000 B/row (-12.02%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 239.167 | 194.167 | -45.000 us/row (-18.82%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 1440.000 | 848.000 | -592.000 B/row (-41.11%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 11554.000 | 10845.000 | -709.000 B/row (-6.14%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 361.333 | 226.833 | -134.500 us/row (-37.22%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 1440.000 | 848.000 | -592.000 B/row (-41.11%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 9220.000 | 8122.000 | -1098.000 B/row (-11.91%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 321.875 | 202.750 | -119.125 us/row (-37.01%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 1440.000 | 848.000 | -592.000 B/row (-41.11%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 9649.000 | 8979.000 | -670.000 B/row (-6.94%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 385.167 | 246.125 | -139.042 us/row (-36.10%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1720.000 | 1128.000 | -592.000 B/row (-34.42%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 12926.000 | 12584.000 | -342.000 B/row (-2.65%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 370.000 | 233.834 | -136.166 us/row (-36.80%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1720.000 | 1128.000 | -592.000 B/row (-34.42%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13854.000 | 13778.000 | -76.000 B/row (-0.55%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 995.667 | 435.750 | -559.917 us/row (-56.24%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2840.000 | 2248.000 | -592.000 B/row (-20.85%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 23617.000 | 20844.000 | -2773.000 B/row (-11.74%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 920.042 | 366.750 | -553.292 us/row (-60.14%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2840.000 | 2248.000 | -592.000 B/row (-20.85%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 26834.000 | 24262.000 | -2572.000 B/row (-9.58%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 318.209 | 277.000 | -41.209 us/row (-12.95%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 2176.000 | 1632.000 | -544.000 B/row (-25.00%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 14896.000 | 19475.000 | +4579.000 B/row (+30.74%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 318.084 | 262.625 | -55.459 us/row (-17.44%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 2304.000 | 1664.000 | -640.000 B/row (-27.78%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16004.000 | 20099.000 | +4095.000 B/row (+25.59%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 311.750 | 274.250 | -37.500 us/row (-12.03%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 2176.000 | 1632.000 | -544.000 B/row (-25.00%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15217.000 | 18534.000 | +3317.000 B/row (+21.80%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 311.458 | 264.084 | -47.374 us/row (-15.21%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 2304.000 | 1664.000 | -640.000 B/row (-27.78%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 16325.000 | 19142.000 | +2817.000 B/row (+17.26%) | 9 | larger |
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
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 130.291 | 140.292 | +10.001 us/row (+7.68%) | 9 | slower |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1704.000 | 1560.000 | -144.000 B/row (-8.45%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 9116.000 | 8556.000 | -560.000 B/row (-6.14%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 130.208 | 135.250 | +5.042 us/row (+3.87%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1704.000 | 1560.000 | -144.000 B/row (-8.45%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 9516.000 | 9020.000 | -496.000 B/row (-5.21%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 165.709 | 168.458 | +2.749 us/row (+1.66%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2376.000 | 2232.000 | -144.000 B/row (-6.06%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10973.000 | 10413.000 | -560.000 B/row (-5.10%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 168.000 | 169.709 | +1.709 us/row (+1.02%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2376.000 | 2232.000 | -144.000 B/row (-6.06%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 11257.000 | 10769.000 | -488.000 B/row (-4.34%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 213.709 | 210.417 | -3.292 us/row (-1.54%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3272.000 | 3128.000 | -144.000 B/row (-4.40%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 14186.000 | 13754.000 | -432.000 B/row (-3.05%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 215.375 | 208.292 | -7.083 us/row (-3.29%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3272.000 | 3128.000 | -144.000 B/row (-4.40%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 14360.000 | 13912.000 | -448.000 B/row (-3.12%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 109.000 | 112.084 | +3.084 us/row (+2.83%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1192.000 | 1048.000 | -144.000 B/row (-12.08%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7961.000 | 7457.000 | -504.000 B/row (-6.33%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 107.959 | 113.583 | +5.624 us/row (+5.21%) | 9 | slower |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1192.000 | 1048.000 | -144.000 B/row (-12.08%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 8047.000 | 7671.000 | -376.000 B/row (-4.67%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 448.250 | 421.333 | -26.917 us/row (-6.00%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8664.000 | 8520.000 | -144.000 B/row (-1.66%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27944.000 | 27472.000 | -472.000 B/row (-1.69%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 447.458 | 416.875 | -30.583 us/row (-6.83%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8664.000 | 8520.000 | -144.000 B/row (-1.66%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 28171.000 | 27827.000 | -344.000 B/row (-1.22%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 197.250 | 190.375 | -6.875 us/row (-3.49%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3096.000 | 2952.000 | -144.000 B/row (-4.65%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 12488.000 | 12016.000 | -472.000 B/row (-3.78%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 193.458 | 192.500 | -0.958 us/row (-0.50%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3096.000 | 2952.000 | -144.000 B/row (-4.65%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 12883.000 | 12420.000 | -463.000 B/row (-3.59%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 181.000 | 189.583 | +8.583 us/row (+4.74%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1704.000 | 1560.000 | -144.000 B/row (-8.45%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8918.000 | 8409.000 | -509.000 B/row (-5.71%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 179.875 | 173.375 | -6.500 us/row (-3.61%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1704.000 | 1560.000 | -144.000 B/row (-8.45%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 9315.000 | 8857.000 | -458.000 B/row (-4.92%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 212.000 | 205.875 | -6.125 us/row (-2.89%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2544.000 | 2400.000 | -144.000 B/row (-5.66%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11960.000 | 11607.000 | -353.000 B/row (-2.95%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 214.250 | 215.291 | +1.041 us/row (+0.49%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2544.000 | 2400.000 | -144.000 B/row (-5.66%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 12336.000 | 12112.000 | -224.000 B/row (-1.82%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 550.917 | 498.750 | -52.167 us/row (-9.47%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 24135.000 | 23847.000 | -288.000 B/row (-1.19%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 552.667 | 516.791 | -35.876 us/row (-6.49%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 25680.000 | 25456.000 | -224.000 B/row (-0.87%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | elapsedUs | 486.917 | 448.209 | -38.708 us/row (-7.95%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | transientBytes | 21101.000 | 20813.000 | -288.000 B/row (-1.36%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | elapsedUs | 555.333 | 510.709 | -44.624 us/row (-8.04%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.columns.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | transientBytes | 21197.000 | 21021.000 | -176.000 B/row (-0.83%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | elapsedUs | 489.708 | 457.875 | -31.833 us/row (-6.50%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | transientBytes | 22046.000 | 21822.000 | -224.000 B/row (-1.02%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | elapsedUs | 547.875 | 507.500 | -40.375 us/row (-7.37%) | 9 | faster |
| 3.14 | keyed-write | leaf.boolean.document.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | transientBytes | 22142.000 | 22030.000 | -112.000 B/row (-0.51%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | elapsedUs | 566.333 | 508.458 | -57.875 us/row (-10.22%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | transientBytes | 44547.000 | 44259.000 | -288.000 B/row (-0.65%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | elapsedUs | 736.291 | 684.667 | -51.624 us/row (-7.01%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.columns.wire | retainedBytes | 15312.000 | 15376.000 | +64.000 B/row (+0.42%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | transientBytes | 54051.000 | 53875.000 | -176.000 B/row (-0.33%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | elapsedUs | 559.542 | 518.167 | -41.375 us/row (-7.39%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | transientBytes | 47372.000 | 47148.000 | -224.000 B/row (-0.47%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | elapsedUs | 727.417 | 669.834 | -57.583 us/row (-7.92%) | 9 | faster |
| 3.14 | keyed-write | leaf.bytes.document.wire | retainedBytes | 15312.000 | 15376.000 | +64.000 B/row (+0.42%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | transientBytes | 56876.000 | 56764.000 | -112.000 B/row (-0.20%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | elapsedUs | 622.833 | 561.250 | -61.583 us/row (-9.89%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | transientBytes | 33282.000 | 32994.000 | -288.000 B/row (-0.87%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | elapsedUs | 855.584 | 775.417 | -80.167 us/row (-9.37%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.columns.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | transientBytes | 39514.000 | 39338.000 | -176.000 B/row (-0.45%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | elapsedUs | 630.834 | 566.208 | -64.626 us/row (-10.24%) | 9 | faster |
| 3.14 | keyed-write | leaf.date.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | transientBytes | 34699.000 | 34475.000 | -224.000 B/row (-0.65%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | elapsedUs | 842.583 | 804.375 | -38.208 us/row (-4.53%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | transientBytes | 40931.000 | 40819.000 | -112.000 B/row (-0.27%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | elapsedUs | 1075.208 | 950.333 | -124.875 us/row (-11.61%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | transientBytes | 36141.000 | 35869.000 | -272.000 B/row (-0.75%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | elapsedUs | 1894.208 | 1689.292 | -204.916 us/row (-10.82%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.columns.wire | retainedBytes | 28944.000 | 29008.000 | +64.000 B/row (+0.22%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | transientBytes | 59337.000 | 59209.000 | -128.000 B/row (-0.22%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | elapsedUs | 1056.458 | 948.167 | -108.291 us/row (-10.25%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | transientBytes | 37686.000 | 37478.000 | -208.000 B/row (-0.55%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | elapsedUs | 1878.375 | 1697.959 | -180.416 us/row (-9.60%) | 9 | faster |
| 3.14 | keyed-write | leaf.decimal.document.wire | retainedBytes | 28944.000 | 29008.000 | +64.000 B/row (+0.22%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | transientBytes | 60818.000 | 60818.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | elapsedUs | 1021.792 | 829.458 | -192.334 us/row (-18.82%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.columns.typed | retainedBytes | 10512.000 | 10368.000 | -144.000 B/row (-1.37%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | transientBytes | 30837.000 | 30549.000 | -288.000 B/row (-0.93%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | elapsedUs | 1517.958 | 1190.500 | -327.458 us/row (-21.57%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.columns.wire | retainedBytes | 10512.000 | 10576.000 | +64.000 B/row (+0.61%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | transientBytes | 30997.000 | 30757.000 | -240.000 B/row (-0.77%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | elapsedUs | 892.792 | 837.250 | -55.542 us/row (-6.22%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.document.typed | retainedBytes | 10512.000 | 10368.000 | -144.000 B/row (-1.37%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | transientBytes | 31870.000 | 31646.000 | -224.000 B/row (-0.70%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | elapsedUs | 1302.333 | 1194.583 | -107.750 us/row (-8.27%) | 9 | faster |
| 3.14 | keyed-write | leaf.float32.document.wire | retainedBytes | 10512.000 | 10576.000 | +64.000 B/row (+0.61%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | transientBytes | 31966.000 | 31854.000 | -112.000 B/row (-0.35%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | elapsedUs | 578.334 | 515.500 | -62.834 us/row (-10.86%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | transientBytes | 21573.000 | 21285.000 | -288.000 B/row (-1.34%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | elapsedUs | 677.500 | 585.125 | -92.375 us/row (-13.63%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.columns.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | transientBytes | 21669.000 | 21493.000 | -176.000 B/row (-0.81%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | elapsedUs | 569.167 | 522.542 | -46.625 us/row (-8.19%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | transientBytes | 22606.000 | 22382.000 | -224.000 B/row (-0.99%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | elapsedUs | 656.500 | 588.750 | -67.750 us/row (-10.32%) | 9 | faster |
| 3.14 | keyed-write | leaf.float64.document.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | transientBytes | 22702.000 | 22590.000 | -112.000 B/row (-0.49%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | elapsedUs | 509.958 | 481.916 | -28.042 us/row (-5.50%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | transientBytes | 22326.000 | 22038.000 | -288.000 B/row (-1.29%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | elapsedUs | 644.708 | 610.875 | -33.833 us/row (-5.25%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.columns.wire | retainedBytes | 12032.000 | 12096.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | transientBytes | 28510.000 | 28334.000 | -176.000 B/row (-0.62%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | elapsedUs | 510.041 | 471.750 | -38.291 us/row (-7.51%) | 9 | faster |
| 3.14 | keyed-write | leaf.int32.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | transientBytes | 23510.000 | 23286.000 | -224.000 B/row (-0.95%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | elapsedUs | 651.375 | 627.250 | -24.125 us/row (-3.70%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | retainedBytes | 12032.000 | 12096.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | transientBytes | 29694.000 | 29582.000 | -112.000 B/row (-0.38%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | elapsedUs | 531.625 | 492.500 | -39.125 us/row (-7.36%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | transientBytes | 23306.000 | 23018.000 | -288.000 B/row (-1.24%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | elapsedUs | 678.250 | 644.084 | -34.166 us/row (-5.04%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.columns.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | transientBytes | 29546.000 | 29370.000 | -176.000 B/row (-0.60%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | elapsedUs | 540.000 | 487.292 | -52.708 us/row (-9.76%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | transientBytes | 24686.000 | 24462.000 | -224.000 B/row (-0.91%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | elapsedUs | 703.417 | 623.500 | -79.917 us/row (-11.36%) | 9 | faster |
| 3.14 | keyed-write | leaf.int64.document.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | transientBytes | 30926.000 | 30814.000 | -112.000 B/row (-0.36%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | elapsedUs | 673.458 | 627.958 | -45.500 us/row (-6.76%) | 9 | faster |
| 3.14 | keyed-write | leaf.string.columns.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | transientBytes | 24228.000 | 24052.000 | -176.000 B/row (-0.73%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | elapsedUs | 672.125 | 616.291 | -55.834 us/row (-8.31%) | 9 | faster |
| 3.14 | keyed-write | leaf.string.document.wire | retainedBytes | 5904.000 | 5968.000 | +64.000 B/row (+1.08%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | transientBytes | 25773.000 | 25661.000 | -112.000 B/row (-0.43%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | elapsedUs | 678.625 | 625.625 | -53.000 us/row (-7.81%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | transientBytes | 35842.000 | 35554.000 | -288.000 B/row (-0.80%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | elapsedUs | 945.166 | 861.000 | -84.166 us/row (-8.90%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.columns.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | transientBytes | 42138.000 | 41898.000 | -240.000 B/row (-0.57%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | elapsedUs | 683.708 | 632.541 | -51.167 us/row (-7.48%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | transientBytes | 37579.000 | 37355.000 | -224.000 B/row (-0.60%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | elapsedUs | 935.250 | 848.458 | -86.792 us/row (-9.28%) | 9 | faster |
| 3.14 | keyed-write | leaf.time.document.wire | retainedBytes | 12048.000 | 12112.000 | +64.000 B/row (+0.53%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | transientBytes | 43811.000 | 43699.000 | -112.000 B/row (-0.26%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | elapsedUs | 957.542 | 713.834 | -243.708 us/row (-25.45%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | transientBytes | 41991.000 | 41703.000 | -288.000 B/row (-0.69%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | elapsedUs | 1443.750 | 1090.209 | -353.541 us/row (-24.49%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | retainedBytes | 15120.000 | 15184.000 | +64.000 B/row (+0.42%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | transientBytes | 51611.000 | 51483.000 | -128.000 B/row (-0.25%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | elapsedUs | 942.875 | 710.500 | -232.375 us/row (-24.65%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | transientBytes | 44496.000 | 44272.000 | -224.000 B/row (-0.50%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | elapsedUs | 1452.667 | 1073.791 | -378.876 us/row (-26.08%) | 9 | faster |
| 3.14 | keyed-write | leaf.timestamp.document.wire | retainedBytes | 15120.000 | 15184.000 | +64.000 B/row (+0.42%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | transientBytes | 54052.000 | 54052.000 | +0.000 B/row (+0.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | elapsedUs | 913.000 | 820.500 | -92.500 us/row (-10.13%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.columns.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | transientBytes | 46714.000 | 46426.000 | -288.000 B/row (-0.62%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | elapsedUs | 1264.291 | 1177.541 | -86.750 us/row (-6.86%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.columns.wire | retainedBytes | 26640.000 | 26704.000 | +64.000 B/row (+0.24%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | transientBytes | 67610.000 | 67370.000 | -240.000 B/row (-0.35%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | elapsedUs | 917.083 | 812.250 | -104.833 us/row (-11.43%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.document.typed | retainedBytes | 5904.000 | 5760.000 | -144.000 B/row (-2.44%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | transientBytes | 49795.000 | 49571.000 | -224.000 B/row (-0.45%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | elapsedUs | 1266.167 | 1184.208 | -81.959 us/row (-6.47%) | 9 | faster |
| 3.14 | keyed-write | leaf.uuid.document.wire | retainedBytes | 26640.000 | 26704.000 | +64.000 B/row (+0.24%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | transientBytes | 70627.000 | 70515.000 | -112.000 B/row (-0.16%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 180.667 | 134.167 | -46.500 us/row (-25.74%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 2064.000 | 1872.000 | -192.000 B/row (-9.30%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 9683.000 | 7797.000 | -1886.000 B/row (-19.48%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 170.250 | 124.250 | -46.000 us/row (-27.02%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 2024.000 | 1904.000 | -120.000 B/row (-5.93%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 10163.000 | 8793.000 | -1370.000 B/row (-13.48%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 188.208 | 149.666 | -38.542 us/row (-20.48%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 1992.000 | 1872.000 | -120.000 B/row (-6.02%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 10535.000 | 8705.000 | -1830.000 B/row (-17.37%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 173.750 | 142.833 | -30.917 us/row (-17.79%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 2024.000 | 1904.000 | -120.000 B/row (-5.93%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 11015.000 | 9701.000 | -1314.000 B/row (-11.93%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 221.959 | 196.125 | -25.834 us/row (-11.64%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 2176.000 | 1584.000 | -592.000 B/row (-27.21%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 11489.000 | 11058.000 | -431.000 B/row (-3.75%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 204.125 | 187.041 | -17.084 us/row (-8.37%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 2208.000 | 1616.000 | -592.000 B/row (-26.81%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 11949.000 | 11794.000 | -155.000 B/row (-1.30%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 236.667 | 207.125 | -29.542 us/row (-12.48%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 2176.000 | 1584.000 | -592.000 B/row (-27.21%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 11948.000 | 12124.000 | +176.000 B/row (+1.47%) | 9 | within noise |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 229.042 | 206.250 | -22.792 us/row (-9.95%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 2208.000 | 1616.000 | -592.000 B/row (-26.81%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 12536.000 | 12684.000 | +148.000 B/row (+1.18%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 134.875 | 138.167 | +3.292 us/row (+2.44%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1928.000 | 1784.000 | -144.000 B/row (-7.47%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 10550.000 | 10587.000 | +37.000 B/row (+0.35%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 139.000 | 144.833 | +5.833 us/row (+4.20%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1928.000 | 1992.000 | +64.000 B/row (+3.32%) | 1 | larger |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 10670.000 | 11035.000 | +365.000 B/row (+3.42%) | 9 | larger |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 133.958 | 134.958 | +1.000 us/row (+0.75%) | 9 | within noise |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 1928.000 | 1784.000 | -144.000 B/row (-7.47%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 10702.000 | 10342.000 | -360.000 B/row (-3.36%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 136.042 | 138.500 | +2.458 us/row (+1.81%) | 9 | within noise |
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
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 97.417 | 37.041 | -60.376 us/row (-61.98%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 7744.000 | 4010.000 | -3734.000 B/row (-48.22%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 84.625 | 31.084 | -53.541 us/row (-63.27%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 7856.000 | 3646.000 | -4210.000 B/row (-53.59%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 97.834 | 36.834 | -61.000 us/row (-62.35%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 7744.000 | 4012.000 | -3732.000 B/row (-48.19%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 84.042 | 31.833 | -52.209 us/row (-62.12%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 7856.000 | 3649.000 | -4207.000 B/row (-53.55%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3321.958 | 3076.917 | -245.041 us (-7.38%) | 9 | faster |
| 3.14 | model-preparation | model.prepared | retainedBytes | 438440.000 | 448988.000 | +10548.000 B (+2.41%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 444984.000 | 455812.000 | +10828.000 B (+2.43%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | 311.625 | 295.250 | -16.375 us (-5.25%) | 9 | faster |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | 23920.000 | 24910.000 | +990.000 B (+4.14%) | 1 | larger |
| 3.14 | model-preparation | model.prepared.family | transientBytes | 27688.000 | 29054.000 | +1366.000 B (+4.93%) | 9 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 24.938 | 17.566 | -7.371 us/row (-29.56%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 985.594 | 999.508 | +13.914 B/row (+1.41%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 2050.805 | 1873.516 | -177.289 B/row (-8.64%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 25.788 | 18.302 | -7.485 us/row (-29.03%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1987.219 | 2001.133 | +13.914 B/row (+0.70%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2436.273 | 2318.906 | -117.367 B/row (-4.82%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 29.803 | 23.445 | -6.358 us/row (-21.33%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1135.375 | 1191.031 | +55.656 B/row (+4.90%) | 1 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2696.094 | 2361.500 | -334.594 B/row (-12.41%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 30.316 | 22.370 | -7.947 us/row (-26.21%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2141.875 | 2197.531 | +55.656 B/row (+2.60%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 3022.219 | 2711.000 | -311.219 B/row (-10.30%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 49.339 | 38.333 | -11.005 us/row (-22.31%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1742.500 | 1965.125 | +222.625 B/row (+12.78%) | 1 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 4822.375 | 3924.000 | -898.375 B/row (-18.63%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 50.938 | 38.823 | -12.115 us/row (-23.78%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2768.500 | 2991.125 | +222.625 B/row (+8.04%) | 1 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 5052.875 | 4192.000 | -860.875 B/row (-17.04%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | elapsedUs | 118.818 | 101.922 | -16.896 us/row (-14.22%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | retainedBytes | 3166.500 | 3389.125 | +222.625 B/row (+7.03%) | 1 | larger |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | transientBytes | 17259.375 | 16362.000 | -897.375 B/row (-5.20%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | elapsedUs | 117.375 | 102.292 | -15.083 us/row (-12.85%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | retainedBytes | 16642.500 | 16865.125 | +222.625 B/row (+1.34%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | transientBytes | 19092.625 | 18039.000 | -1053.625 B/row (-5.52%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | elapsedUs | 331.250 | 285.281 | -45.969 us/row (-13.88%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | retainedBytes | 12966.500 | 13189.125 | +222.625 B/row (+1.72%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | transientBytes | 32976.000 | 32079.125 | -896.875 B/row (-2.72%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | elapsedUs | 329.901 | 287.661 | -42.240 us/row (-12.80%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | retainedBytes | 40458.500 | 40681.125 | +222.625 B/row (+0.55%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | transientBytes | 43064.250 | 41988.125 | -1076.125 B/row (-2.50%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | elapsedUs | 389.057 | 340.698 | -48.359 us/row (-12.43%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | retainedBytes | 9566.500 | 9789.125 | +222.625 B/row (+2.33%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | transientBytes | 28226.625 | 27330.000 | -896.625 B/row (-3.18%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | elapsedUs | 377.651 | 335.958 | -41.693 us/row (-11.04%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | retainedBytes | 32834.500 | 33057.125 | +222.625 B/row (+0.68%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | transientBytes | 35442.875 | 34383.000 | -1059.875 B/row (-2.99%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | elapsedUs | 722.505 | 646.719 | -75.787 us/row (-10.49%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | retainedBytes | 27166.500 | 27389.125 | +222.625 B/row (+0.82%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | transientBytes | 33197.375 | 32145.000 | -1052.375 B/row (-3.17%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | elapsedUs | 733.615 | 651.781 | -81.833 us/row (-11.15%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | retainedBytes | 50818.500 | 51041.125 | +222.625 B/row (+0.44%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | transientBytes | 53602.375 | 52536.750 | -1065.625 B/row (-1.99%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | elapsedUs | 588.302 | 537.375 | -50.927 us/row (-8.66%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | retainedBytes | 7966.500 | 8189.125 | +222.625 B/row (+2.79%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | transientBytes | 22665.375 | 21768.000 | -897.375 B/row (-3.96%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | elapsedUs | 602.010 | 536.443 | -65.568 us/row (-10.89%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | retainedBytes | 26050.500 | 26273.125 | +222.625 B/row (+0.85%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | transientBytes | 28537.625 | 27477.000 | -1060.625 B/row (-3.72%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | elapsedUs | 270.812 | 234.177 | -36.635 us/row (-13.53%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | retainedBytes | 7774.500 | 7997.125 | +222.625 B/row (+2.86%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | transientBytes | 21888.375 | 20991.000 | -897.375 B/row (-4.10%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | elapsedUs | 267.339 | 227.349 | -39.990 us/row (-14.96%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | retainedBytes | 21250.500 | 21473.125 | +222.625 B/row (+1.05%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | transientBytes | 23728.625 | 22668.000 | -1060.625 B/row (-4.47%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | elapsedUs | 167.781 | 145.776 | -22.005 us/row (-13.12%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | retainedBytes | 9566.000 | 9788.625 | +222.625 B/row (+2.33%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | transientBytes | 23668.375 | 22771.500 | -896.875 B/row (-3.79%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | elapsedUs | 168.359 | 144.026 | -24.333 us/row (-14.45%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | retainedBytes | 23042.000 | 23264.625 | +222.625 B/row (+0.97%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | transientBytes | 25508.625 | 24448.500 | -1060.125 B/row (-4.16%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | elapsedUs | 171.906 | 151.583 | -20.323 us/row (-11.82%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | retainedBytes | 9950.500 | 10173.125 | +222.625 B/row (+2.24%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | transientBytes | 24057.375 | 23160.500 | -896.875 B/row (-3.73%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | elapsedUs | 182.224 | 150.573 | -31.651 us/row (-17.37%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | retainedBytes | 23426.500 | 23649.125 | +222.625 B/row (+0.95%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | transientBytes | 25897.625 | 24837.500 | -1060.125 B/row (-4.09%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | elapsedUs | 153.182 | 131.375 | -21.807 us/row (-14.24%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | retainedBytes | 13342.500 | 13565.125 | +222.625 B/row (+1.67%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | transientBytes | 27434.875 | 26537.750 | -897.125 B/row (-3.27%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | elapsedUs | 154.651 | 131.708 | -22.943 us/row (-14.84%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | retainedBytes | 26818.500 | 27041.125 | +222.625 B/row (+0.83%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | transientBytes | 29284.125 | 28214.750 | -1069.375 B/row (-3.65%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | elapsedUs | 479.099 | 421.750 | -57.349 us/row (-11.97%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | retainedBytes | 9566.500 | 9789.125 | +222.625 B/row (+2.33%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | transientBytes | 29194.625 | 28298.000 | -896.625 B/row (-3.07%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | elapsedUs | 482.990 | 425.516 | -57.474 us/row (-11.90%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | retainedBytes | 33794.500 | 34017.125 | +222.625 B/row (+0.66%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | transientBytes | 36410.875 | 35351.000 | -1059.875 B/row (-2.91%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | elapsedUs | 819.667 | 621.297 | -198.370 us/row (-24.20%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | retainedBytes | 12766.500 | 12989.125 | +222.625 B/row (+1.74%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | transientBytes | 32030.625 | 31132.750 | -897.875 B/row (-2.80%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | elapsedUs | 808.391 | 625.463 | -182.927 us/row (-22.63%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | retainedBytes | 39298.500 | 39521.125 | +222.625 B/row (+0.57%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | transientBytes | 41934.875 | 40873.750 | -1061.125 B/row (-2.53%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | elapsedUs | 433.552 | 382.693 | -50.859 us/row (-11.73%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | retainedBytes | 24761.000 | 24983.625 | +222.625 B/row (+0.90%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | transientBytes | 35620.125 | 34723.500 | -896.625 B/row (-2.52%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | elapsedUs | 435.786 | 382.854 | -52.932 us/row (-12.15%) | 9 | faster |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | retainedBytes | 53021.000 | 53243.625 | +222.625 B/row (+0.42%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | transientBytes | 55604.375 | 54544.500 | -1059.875 B/row (-1.91%) | 9 | within noise |
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
| 3.14 | wire-insert-response | response.insert.family.wire | elapsedUs | 64.750 | 65.167 | +0.417 us/row (+0.64%) | 9 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | retainedBytes | 8748.000 | 10713.000 | +1965.000 B/row (+22.46%) | 1 | larger |
| 3.14 | wire-insert-response | response.insert.family.wire | transientBytes | 8718.000 | 8774.000 | +56.000 B/row (+0.64%) | 9 | within noise |

Deltas are advisory and never ratchet the Budget Contract.
