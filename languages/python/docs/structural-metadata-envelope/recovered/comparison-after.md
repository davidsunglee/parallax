# Python cost report comparison

Timing deltas within 5% and byte deltas within 3% are read as noise; count deltas are exact. A cell present on one side alone, or whose unit differs, is not compared.

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
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.398 | 3.409 | +0.011 ratio (+0.31%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.398 | 3.409 | +0.011 ratio (+0.31%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.425 | 3.427 | +0.002 ratio (+0.06%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 1.068 | 0.507 | -0.561 ratio (-52.51%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.likeForLike | 1.023 | 0.487 | -0.537 ratio (-52.44%) | 0 | smaller |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 2.790 | 1.554 | -1.235 ratio (-44.29%) | 0 | smaller |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.223 | 2.191 | -0.032 ratio (-1.42%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.223 | 2.191 | -0.032 ratio (-1.42%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.245 | 2.214 | -0.031 ratio (-1.39%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 18871.582 | 1410.723 | -17460.859 ns (-92.52%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 17478.835 | 7011.965 | -10466.871 ns (-59.88%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.dumpNs | 6237.312 | 6097.709 | -139.604 ns (-2.24%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 7754.000 | 4770.000 | -2984.000 B (-38.48%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/nested | compact.readNs | 88.292 | 86.679 | -1.613 ns (-1.83%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 691.459 | 535.942 | -155.517 ns (-22.49%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.transientBytes | 6690.000 | 3706.000 | -2984.000 B (-44.60%) | 0 | smaller |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 691.459 | 535.942 | -155.517 ns (-22.49%) | 0 | smaller |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | -126.869 | 96.925 | +223.794 ns (-176.40%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 14641.494 | 10448.825 | -4192.669 ns (-28.64%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2513.083 | 2521.063 | +7.979 ns (+0.32%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 5184.000 | 4960.000 | -224.000 B (-4.32%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.readNs | 28.658 | 25.350 | -3.308 ns (-11.54%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2392.000 | 2168.000 | -224.000 B (-9.36%) | 0 | smaller |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 301.811 | 502.717 | +200.906 ns (+66.57%) | 0 | larger |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 9662.669 | 6085.971 | -3576.698 ns (-37.02%) | 0 | smaller |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2578.646 | 2508.375 | -70.271 ns (-2.73%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 27.921 | 25.067 | -2.854 ns (-10.22%) | 0 | smaller |
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
| - | - | cpython-3.13/nullable | compact.callNs | 14391.654 | 1396.802 | -12994.852 ns (-90.29%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 5486.429 | 2331.510 | -3154.919 ns (-57.50%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1952.437 | 1813.042 | -139.396 ns (-7.14%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 5320.000 | 3464.000 | -1856.000 B (-34.89%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/nullable | compact.readNs | 81.460 | 74.375 | -7.085 ns (-8.70%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 199.359 | 200.953 | +1.594 ns (+0.80%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.transientBytes | 4856.000 | 3000.000 | -1856.000 B (-38.22%) | 0 | smaller |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 199.359 | 200.953 | +1.594 ns (+0.80%) | 0 | within noise |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 39.779 | 301.983 | +262.205 ns (+659.16%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5679.992 | 5533.454 | -146.538 ns (-2.58%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 914.042 | 913.229 | -0.813 ns (-0.09%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 22.362 | 23.212 | +0.850 ns (+3.80%) | 0 | larger |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 196.598 | 204.381 | +7.783 ns (+3.96%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1274.006 | 1209.931 | -64.075 ns (-5.03%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 874.583 | 852.625 | -21.958 ns (-2.51%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 22.196 | 22.242 | +0.046 ns (+0.21%) | 0 | within noise |
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
| - | - | cpython-3.13/partial | compact.callNs | 14267.177 | 1317.304 | -12949.873 ns (-90.77%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 4981.469 | 2151.987 | -2829.481 ns (-56.80%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.dumpNs | 1965.562 | 1847.688 | -117.875 ns (-6.00%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 5264.000 | 3432.000 | -1832.000 B (-34.80%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/partial | compact.readNs | 82.337 | 75.960 | -6.377 ns (-7.75%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 244.266 | 173.646 | -70.620 ns (-28.91%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.transientBytes | 4832.000 | 3000.000 | -1832.000 B (-37.91%) | 0 | smaller |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 244.266 | 173.646 | -70.620 ns (-28.91%) | 0 | smaller |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 233.269 | 127.858 | -105.411 ns (-45.19%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5336.315 | 5183.433 | -152.881 ns (-2.86%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.dumpNs | 919.854 | 869.604 | -50.250 ns (-5.46%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 23.354 | 22.721 | -0.633 ns (-2.71%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 191.050 | 210.785 | +19.735 ns (+10.33%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 988.950 | 933.715 | -55.235 ns (-5.59%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 937.917 | 907.145 | -30.771 ns (-3.28%) | 0 | smaller |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 25.221 | 22.556 | -2.665 ns (-10.56%) | 0 | smaller |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 32657.117 | 1355.612 | -31301.504 ns (-95.85%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 4887.196 | 2190.137 | -2697.058 ns (-55.19%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1737.041 | 1679.479 | -57.562 ns (-3.31%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 7832.000 | 3408.000 | -4424.000 B (-56.49%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/polymorphic | compact.readNs | 85.277 | 78.479 | -6.798 ns (-7.97%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 276.815 | 209.193 | -67.622 ns (-24.43%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 7424.000 | 3000.000 | -4424.000 B (-59.59%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 276.815 | 209.193 | -67.622 ns (-24.43%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 63.748 | 167.016 | +103.268 ns (+161.99%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4305.190 | 4179.817 | -125.373 ns (-2.91%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 831.104 | 793.584 | -37.521 ns (-4.51%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 25.569 | 23.777 | -1.792 ns (-7.01%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 178.725 | 227.492 | +48.767 ns (+27.29%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1108.629 | 1038.342 | -70.288 ns (-6.34%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 811.500 | 774.875 | -36.625 ns (-4.51%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 25.229 | 23.390 | -1.839 ns (-7.29%) | 0 | smaller |
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
| - | - | cpython-3.13/shallow | compact.callNs | 11920.544 | 1333.829 | -10586.715 ns (-88.81%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 3999.519 | 2043.483 | -1956.035 ns (-48.91%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1484.938 | 1413.125 | -71.812 ns (-4.84%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 5216.000 | 3384.000 | -1832.000 B (-35.12%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/shallow | compact.readNs | 96.542 | 88.286 | -8.255 ns (-8.55%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 83.619 | 195.927 | +112.308 ns (+134.31%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.transientBytes | 4832.000 | 3000.000 | -1832.000 B (-37.91%) | 0 | smaller |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 83.619 | 195.927 | +112.308 ns (+134.31%) | 0 | larger |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 195.321 | 165.016 | -30.304 ns (-15.52%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2795.221 | 2763.192 | -32.029 ns (-1.15%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 759.250 | 710.375 | -48.875 ns (-6.44%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 28.802 | 25.328 | -3.474 ns (-12.06%) | 0 | smaller |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 203.525 | 208.808 | +5.283 ns (+2.60%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 799.933 | 790.692 | -9.242 ns (-1.16%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 707.333 | 726.854 | +19.521 ns (+2.76%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 26.792 | 26.464 | -0.328 ns (-1.22%) | 0 | within noise |
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
| - | - | cpython-3.13/warmed | compact.callNs | 12265.302 | 1671.787 | -10593.515 ns (-86.37%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 6552.990 | 4069.796 | -2483.194 ns (-37.89%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1990.291 | 1706.167 | -284.125 ns (-14.28%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 5400.000 | 3384.000 | -2016.000 B (-37.33%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.readNs | 104.578 | 91.458 | -13.120 ns (-12.55%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 0.895 | 204.991 | +204.096 ns (+22815.28%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.transientBytes | 4594.000 | 2578.000 | -2016.000 B (-43.88%) | 0 | smaller |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 0.895 | 204.991 | +204.096 ns (+22815.28%) | 0 | larger |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 169.190 | 86.840 | -82.350 ns (-48.67%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 4079.935 | 3875.160 | -204.775 ns (-5.02%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 763.730 | 722.750 | -40.979 ns (-5.37%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 28.505 | 26.641 | -1.865 ns (-6.54%) | 0 | smaller |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 144.296 | 215.877 | +71.581 ns (+49.61%) | 0 | larger |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1796.704 | 1734.748 | -61.956 ns (-3.45%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 759.500 | 703.813 | -55.688 ns (-7.33%) | 0 | smaller |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 27.323 | 26.005 | -1.318 ns (-4.82%) | 0 | smaller |
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
| - | - | cpython-3.13/wide | compact.callNs | 16785.929 | 1422.117 | -15363.813 ns (-91.53%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 7172.842 | 2603.821 | -4569.021 ns (-63.70%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.dumpNs | 2678.417 | 2478.062 | -200.354 ns (-7.48%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 5680.000 | 3512.000 | -2168.000 B (-38.17%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.13/wide | compact.readNs | 86.197 | 78.932 | -7.264 ns (-8.43%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 299.291 | 206.955 | -92.336 ns (-30.85%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.transientBytes | 5168.000 | 3000.000 | -2168.000 B (-41.95%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 299.291 | 206.955 | -92.336 ns (-30.85%) | 0 | smaller |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 139.269 | 345.452 | +206.183 ns (+148.05%) | 0 | larger |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 8455.481 | 8043.423 | -412.058 ns (-4.87%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1286.146 | 1188.021 | -98.125 ns (-7.63%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 24.316 | 21.224 | -3.092 ns (-12.72%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 111.317 | 233.750 | +122.433 ns (+109.99%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1941.371 | 1738.271 | -203.100 ns (-10.46%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1242.855 | 1155.209 | -87.646 ns (-7.05%) | 0 | smaller |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 24.501 | 21.143 | -3.358 ns (-13.71%) | 0 | smaller |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.247 | 3.126 | -0.121 ratio (-3.73%) | 0 | smaller |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.247 | 3.126 | -0.121 ratio (-3.73%) | 0 | smaller |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.098 | 3.021 | -0.077 ratio (-2.49%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 1.088 | 0.520 | -0.569 ratio (-52.25%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.likeForLike | 1.015 | 0.499 | -0.515 ratio (-50.78%) | 0 | smaller |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 2.746 | 1.483 | -1.263 ratio (-45.99%) | 0 | smaller |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.087 | 2.124 | +0.038 ratio (+1.80%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.087 | 2.124 | +0.038 ratio (+1.80%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.074 | 2.147 | +0.073 ratio (+3.53%) | 0 | larger |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 24692.729 | 1468.871 | -23223.858 ns (-94.05%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 20878.667 | 5910.171 | -14968.496 ns (-71.69%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.dumpNs | 7870.292 | 5495.396 | -2374.896 ns (-30.18%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 8002.000 | 5034.000 | -2968.000 B (-37.09%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/nested | compact.readNs | 114.287 | 77.979 | -36.308 ns (-31.77%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 564.031 | 247.412 | -316.619 ns (-56.14%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 6770.000 | 3802.000 | -2968.000 B (-43.84%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 564.031 | 247.412 | -316.619 ns (-56.14%) | 0 | smaller |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 401.642 | 26.427 | -375.215 ns (-93.42%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 17835.650 | 9416.740 | -8418.910 ns (-47.20%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.dumpNs | 3424.896 | 2403.354 | -1021.542 ns (-29.83%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5440.000 | 5184.000 | -256.000 B (-4.71%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.readNs | 35.383 | 25.242 | -10.142 ns (-28.66%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2520.000 | 2264.000 | -256.000 B (-10.16%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 411.300 | 216.900 | -194.400 ns (-47.26%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 11723.471 | 5636.683 | -6086.787 ns (-51.92%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 3369.500 | 2394.604 | -974.896 ns (-28.93%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4696.000 | 4744.000 | +48.000 B (+1.02%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 35.863 | 25.071 | -10.792 ns (-30.09%) | 0 | smaller |
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
| - | - | cpython-3.14/nullable | compact.callNs | 17801.646 | 1351.073 | -16450.573 ns (-92.41%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 6787.021 | 2023.802 | -4763.219 ns (-70.18%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.dumpNs | 2161.021 | 1630.646 | -530.375 ns (-24.54%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 5760.000 | 3672.000 | -2088.000 B (-36.25%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/nullable | compact.readNs | 91.058 | 69.081 | -21.977 ns (-24.14%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 970.944 | 159.800 | -811.144 ns (-83.54%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.transientBytes | 5264.000 | 3176.000 | -2088.000 B (-39.67%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 970.944 | 159.800 | -811.144 ns (-83.54%) | 0 | smaller |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 2.873 | 163.588 | +160.714 ns (+5593.78%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 6864.460 | 4512.037 | -2352.423 ns (-34.27%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 1234.771 | 811.146 | -423.625 ns (-34.31%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 31.771 | 21.065 | -10.706 ns (-33.70%) | 0 | smaller |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 224.621 | 185.135 | -39.486 ns (-17.58%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1625.567 | 1058.781 | -566.785 ns (-34.87%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 1228.667 | 789.417 | -439.250 ns (-35.75%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 33.969 | 22.044 | -11.925 ns (-35.11%) | 0 | smaller |
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
| - | - | cpython-3.14/partial | compact.callNs | 15459.554 | 1366.290 | -14093.264 ns (-91.16%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 5175.196 | 1944.565 | -3230.631 ns (-62.43%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.dumpNs | 1994.979 | 1653.771 | -341.208 ns (-17.10%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 5720.000 | 3576.000 | -2144.000 B (-37.48%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/partial | compact.readNs | 85.102 | 68.660 | -16.442 ns (-19.32%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 436.468 | 194.108 | -242.360 ns (-55.53%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.transientBytes | 5256.000 | 3112.000 | -2144.000 B (-40.79%) | 0 | smaller |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 436.468 | 194.108 | -242.360 ns (-55.53%) | 0 | smaller |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 297.675 | 212.635 | -85.040 ns (-28.57%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 5521.471 | 4319.135 | -1202.335 ns (-21.78%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.dumpNs | 1041.166 | 797.208 | -243.958 ns (-23.43%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 26.198 | 22.775 | -3.423 ns (-13.07%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 224.871 | 189.004 | -35.867 ns (-15.95%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 1092.233 | 862.725 | -229.508 ns (-21.01%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 1040.062 | 793.875 | -246.187 ns (-23.67%) | 0 | smaller |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 28.698 | 26.887 | -1.810 ns (-6.31%) | 0 | smaller |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 33101.823 | 1235.654 | -31866.169 ns (-96.27%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 4952.302 | 1969.346 | -2982.956 ns (-60.23%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1813.291 | 1510.292 | -303.000 ns (-16.71%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 8008.000 | 3552.000 | -4456.000 B (-55.64%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/polymorphic | compact.readNs | 88.384 | 71.958 | -16.426 ns (-18.58%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 261.167 | 216.673 | -44.494 ns (-17.04%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 7568.000 | 3112.000 | -4456.000 B (-58.88%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 261.167 | 216.673 | -44.494 ns (-17.04%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 227.552 | 232.298 | +4.745 ns (+2.09%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4130.990 | 3539.848 | -591.142 ns (-14.31%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 871.625 | 730.417 | -141.208 ns (-16.20%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 27.449 | 25.461 | -1.988 ns (-7.24%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 237.894 | 170.596 | -67.298 ns (-28.29%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1161.690 | 1002.362 | -159.327 ns (-13.72%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 870.417 | 721.813 | -148.604 ns (-17.07%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 27.048 | 26.170 | -0.878 ns (-3.25%) | 0 | smaller |
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
| - | - | cpython-3.14/shallow | compact.callNs | 15580.568 | 1273.392 | -14307.176 ns (-91.83%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 5538.515 | 1868.462 | -3670.052 ns (-66.26%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1977.833 | 1262.792 | -715.041 ns (-36.15%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 5624.000 | 3528.000 | -2096.000 B (-37.27%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/shallow | compact.readNs | 126.552 | 81.974 | -44.578 ns (-35.23%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 362.157 | 196.959 | -165.198 ns (-45.61%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.transientBytes | 5208.000 | 3112.000 | -2096.000 B (-40.25%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 362.157 | 196.959 | -165.198 ns (-45.61%) | 0 | smaller |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 299.025 | 235.032 | -63.993 ns (-21.40%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 3599.121 | 2381.885 | -1217.235 ns (-33.82%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 973.437 | 673.792 | -299.646 ns (-30.78%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 35.609 | 25.979 | -9.630 ns (-27.04%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 275.798 | 191.004 | -84.794 ns (-30.74%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 1083.598 | 735.413 | -348.185 ns (-32.13%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 971.354 | 661.063 | -310.292 ns (-31.94%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 37.057 | 24.990 | -12.068 ns (-32.56%) | 0 | smaller |
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
| - | - | cpython-3.14/warmed | compact.callNs | 12499.865 | 1539.671 | -10960.194 ns (-87.68%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 6534.948 | 3775.954 | -2758.994 ns (-42.22%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1912.042 | 1563.000 | -349.041 ns (-18.25%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 5808.000 | 3528.000 | -2280.000 B (-39.26%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.readNs | 95.068 | 79.734 | -15.333 ns (-16.13%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 338.304 | 194.362 | -143.942 ns (-42.55%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.transientBytes | 4970.000 | 2690.000 | -2280.000 B (-45.88%) | 0 | smaller |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 338.304 | 194.362 | -143.942 ns (-42.55%) | 0 | smaller |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 21.692 | 110.521 | +88.829 ns (+409.50%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 4204.829 | 3511.792 | -693.037 ns (-16.48%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 811.916 | 669.730 | -142.187 ns (-17.51%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 30.213 | 25.375 | -4.838 ns (-16.01%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 209.983 | 191.004 | -18.979 ns (-9.04%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1870.975 | 1627.413 | -243.562 ns (-13.02%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 834.208 | 669.355 | -164.854 ns (-19.76%) | 0 | smaller |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 30.953 | 25.141 | -5.813 ns (-18.78%) | 0 | smaller |
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
| - | - | cpython-3.14/wide | compact.callNs | 20412.692 | 1309.342 | -19103.350 ns (-93.59%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 9127.433 | 2280.512 | -6846.921 ns (-75.01%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.directWireNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.dumpNs | 3182.479 | 2165.958 | -1016.521 ns (-31.94%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 6000.000 | 3720.000 | -2280.000 B (-38.00%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.projectionNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | | | | | missing on base |
| - | - | cpython-3.14/wide | compact.readNs | 112.039 | 76.122 | -35.917 ns (-32.06%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 887.816 | 225.760 | -662.056 ns (-74.57%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.transientBytes | 5456.000 | 3176.000 | -2280.000 B (-41.79%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 887.816 | 225.760 | -662.056 ns (-74.57%) | 0 | smaller |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 154.294 | 357.871 | +203.577 ns (+131.94%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 10254.477 | 6615.900 | -3638.577 ns (-35.48%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1559.542 | 1042.396 | -517.145 ns (-33.16%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 33.746 | 22.087 | -11.659 ns (-34.55%) | 0 | smaller |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 374.873 | 175.394 | -199.479 ns (-53.21%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 2415.940 | 1490.127 | -925.813 ns (-38.32%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1682.854 | 1029.625 | -653.229 ns (-38.82%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 36.668 | 22.402 | -14.266 ns (-38.90%) | 0 | smaller |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.308 | 3.123 | -0.185 us/event (-5.58%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 4.007 | 3.798 | -0.210 us/event (-5.24%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.226 | 0.264 | +0.037 ratio (+16.38%) | 0 | larger |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.021 | 0.020 | -0.001 ratio (-3.90%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.066 | 0.066 | -0.000 ratio (-0.11%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.005 | 0.004 | -0.000 ratio (-5.22%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.152 | 0.164 | +0.012 ratio (+8.12%) | 0 | larger |
| - | - | Safe logging alone, at INFO | observed.p50 | 501.167 | 419.375 | -81.792 us (-16.32%) | 0 | faster |
| - | - | Safe logging alone, at INFO | observed.p95 | 531.167 | 444.000 | -87.167 us (-16.41%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 92.625 | 87.458 | -5.167 us (-5.58%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 112.208 | 106.333 | -5.875 us (-5.24%) | 0 | faster |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.227 | 0.264 | +0.037 ratio (+16.38%) | 0 | larger |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.275 | 0.320 | +0.045 ratio (+16.36%) | 0 | larger |
| - | - | Safe logging alone, at INFO | plain.p50 | 408.959 | 331.792 | -77.167 us (-18.87%) | 0 | faster |
| - | - | Safe logging alone, at INFO | plain.p95 | 439.167 | 351.834 | -87.333 us (-19.89%) | 0 | faster |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.225 | 0.264 | +0.038 ratio (+17.08%) | 0 | larger |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.209 | 0.262 | +0.052 ratio (+25.05%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.377 | 2.228 | -0.149 us/event (-6.26%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 3.141 | 2.905 | -0.237 us/event (-7.53%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.163 | 0.189 | +0.026 ratio (+16.02%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.015 | 0.014 | -0.001 ratio (-4.56%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.047 | 0.047 | -0.000 ratio (-0.73%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | -0.000 ratio (-5.90%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.109 | 0.118 | +0.008 ratio (+7.62%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | observed.p50 | 475.125 | 392.916 | -82.209 us (-17.30%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | observed.p95 | 508.375 | 416.834 | -91.541 us (-18.01%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 66.543 | 62.375 | -4.168 us (-6.26%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 87.959 | 81.333 | -6.626 us (-7.53%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.164 | 0.189 | +0.025 ratio (+15.33%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.214 | 0.245 | +0.031 ratio (+14.25%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | plain.p50 | 408.958 | 330.416 | -78.542 us (-19.21%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | plain.p95 | 435.458 | 350.667 | -84.791 us (-19.47%) | 0 | faster |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.162 | 0.189 | +0.027 ratio (+16.91%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.167 | 0.189 | +0.021 ratio (+12.68%) | 0 | larger |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 4.185 | 3.759 | -0.426 us/event (-10.17%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.966 | 4.436 | -0.530 us/event (-10.67%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.271 | 0.317 | +0.045 ratio (+16.76%) | 0 | larger |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.026 | 0.024 | -0.002 ratio (-8.10%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.082 | 0.079 | -0.003 ratio (-3.45%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.006 | 0.005 | -0.001 ratio (-9.73%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.185 | 0.198 | +0.012 ratio (+6.64%) | 0 | larger |
| - | - | fan-out of three, tracing every root | observed.p50 | 550.041 | 438.208 | -111.833 us (-20.33%) | 0 | faster |
| - | - | fan-out of three, tracing every root | observed.p95 | 582.375 | 464.875 | -117.500 us (-20.18%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 117.167 | 105.250 | -11.917 us (-10.17%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 139.042 | 124.209 | -14.833 us (-10.67%) | 0 | faster |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.273 | 0.316 | +0.044 ratio (+15.98%) | 0 | larger |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.324 | 0.370 | +0.046 ratio (+14.10%) | 0 | larger |
| - | - | fan-out of three, tracing every root | plain.p50 | 432.167 | 332.500 | -99.667 us (-23.06%) | 0 | faster |
| - | - | fan-out of three, tracing every root | plain.p95 | 460.167 | 353.750 | -106.417 us (-23.13%) | 0 | faster |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.273 | 0.318 | +0.045 ratio (+16.56%) | 0 | larger |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.266 | 0.314 | +0.049 ratio (+18.29%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 4.116 | 3.624 | -0.493 us/event (-11.97%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 5.153 | 4.362 | -0.792 us/event (-15.36%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.263 | 0.305 | +0.042 ratio (+16.04%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.026 | 0.023 | -0.003 ratio (-9.82%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.080 | 0.076 | -0.004 ratio (-4.98%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.006 | 0.005 | -0.001 ratio (-11.51%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.181 | 0.191 | +0.010 ratio (+5.52%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 554.125 | 433.792 | -120.333 us (-21.72%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 597.583 | 462.000 | -135.583 us (-22.69%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 115.250 | 101.459 | -13.791 us (-11.97%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 144.291 | 122.125 | -22.166 us (-15.36%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.265 | 0.305 | +0.040 ratio (+15.10%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.330 | 0.364 | +0.033 ratio (+10.08%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 438.208 | 332.458 | -105.750 us (-24.13%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 462.417 | 353.291 | -109.126 us (-23.60%) | 0 | faster |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.265 | 0.305 | +0.040 ratio (+15.23%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.292 | 0.308 | +0.015 ratio (+5.27%) | 0 | larger |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.501 | 1.406 | -0.095 us/event (-6.34%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 2.237 | 2.115 | -0.122 us/event (-5.45%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.104 | 0.119 | +0.016 ratio (+14.94%) | 0 | larger |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.010 | 0.009 | -0.000 ratio (-4.72%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.030 | 0.030 | -0.000 ratio (-1.06%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | -0.000 ratio (-5.99%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.070 | 0.074 | +0.005 ratio (+6.91%) | 0 | larger |
| - | - | one Handler that keeps nothing | observed.p50 | 446.542 | 369.083 | -77.459 us (-17.35%) | 0 | faster |
| - | - | one Handler that keeps nothing | observed.p95 | 478.250 | 397.000 | -81.250 us (-16.99%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 42.041 | 39.376 | -2.665 us (-6.34%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 62.625 | 59.209 | -3.416 us (-5.45%) | 0 | faster |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.104 | 0.120 | +0.016 ratio (+14.91%) | 0 | larger |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.156 | 0.178 | +0.022 ratio (+13.84%) | 0 | larger |
| - | - | one Handler that keeps nothing | plain.p50 | 404.708 | 329.792 | -74.916 us (-18.51%) | 0 | faster |
| - | - | one Handler that keeps nothing | plain.p95 | 433.250 | 352.917 | -80.333 us (-18.54%) | 0 | faster |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.103 | 0.119 | +0.016 ratio (+15.26%) | 0 | larger |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.104 | 0.125 | +0.021 ratio (+20.26%) | 0 | larger |
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
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 466.314 | 420.996 | -45.318 KiB (-9.72%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 313.757 | 297.176 | -16.581 KiB (-5.28%) | 3 | smaller |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.589 | 0.404 | -0.185 ms (-31.37%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 1.002 | 0.644 | -0.357 ms (-35.66%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 6.405 | 4.702 | -1.703 ms (-26.59%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 29634.753 | 41835.166 | +12200.413 roots/s (+41.17%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 6.948 | 5.521 | -1.427 ms (-20.54%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 28618.445 | 39126.180 | +10507.735 roots/s (+36.72%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 9.328 | 7.383 | -1.945 ms (-20.85%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 21608.580 | 26522.121 | +4913.542 roots/s (+22.74%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 279.798 | 219.224 | -60.574 KiB (-21.65%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 42.406 | 44.738 | +2.332 KiB (+5.50%) | 6 | larger |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 101.862 | 80.877 | -20.985 KiB (-20.60%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 20.794 | 10.950 | -9.844 KiB (-47.34%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1324.136 | 1232.261 | -91.875 KiB (-6.94%) | 3 | smaller |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.957 | 521.973 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.742 | 0.669 | -0.074 ms (-9.93%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.304 | 1.095 | -0.208 ms (-15.99%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 10.349 | 8.562 | -1.786 ms (-17.26%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 19481.468 | 23464.883 | +3983.416 roots/s (+20.45%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 11.242 | 9.210 | -2.032 ms (-18.07%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 17979.884 | 21969.674 | +3989.789 roots/s (+22.19%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 14.188 | 11.890 | -2.299 ms (-16.20%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 13776.674 | 16446.692 | +2670.018 roots/s (+19.38%) | 9 | faster |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 730.601 | 667.897 | -62.703 KiB (-8.58%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 35.688 | 29.220 | -6.469 KiB (-18.13%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 207.229 | 188.167 | -19.062 KiB (-9.20%) | 6 | smaller |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.772 | 5.002 | +1.229 KiB (+32.59%) | 6 | larger |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1745.881 | 1586.600 | -159.281 KiB (-9.12%) | 3 | smaller |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.726 | 869.645 | -0.081 KiB (-0.01%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.890 | 0.827 | -0.063 ms (-7.09%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.568 | 2.010 | -0.558 ms (-21.74%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 27.760 | 24.528 | -3.232 ms (-11.64%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7235.410 | 8276.547 | +1041.137 roots/s (+14.39%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 28.160 | 24.768 | -3.392 ms (-12.05%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 7092.681 | 4285.806 | -2806.875 roots/s (-39.57%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 31.429 | 26.212 | -5.217 ms (-16.60%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6451.084 | 7103.954 | +652.870 roots/s (+10.12%) | 9 | faster |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1164.776 | 1038.502 | -126.274 KiB (-10.84%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 51.764 | 57.180 | +5.416 KiB (+10.46%) | 6 | larger |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 314.458 | 290.226 | -24.232 KiB (-7.71%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 14.881 | 7.715 | -7.166 KiB (-48.16%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1324.800 | 1289.960 | -34.840 KiB (-2.63%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 544.988 | 545.004 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 1.053 | 0.817 | -0.236 ms (-22.42%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.944 | 1.505 | -0.438 ms (-22.55%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 17.778 | 16.068 | -1.710 ms (-9.62%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 10899.282 | 12382.304 | +1483.022 roots/s (+13.61%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 18.119 | 15.987 | -2.132 ms (-11.77%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11205.214 | 12533.160 | +1327.947 roots/s (+11.85%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 20.693 | 19.309 | -1.384 ms (-6.69%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 9422.925 | 10585.605 | +1162.680 roots/s (+12.34%) | 9 | faster |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1159.917 | 1132.808 | -27.109 KiB (-2.34%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 45.501 | 38.103 | -7.398 KiB (-16.26%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 320.151 | 302.128 | -18.023 KiB (-5.63%) | 6 | smaller |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.093 | 5.627 | +1.534 KiB (+37.49%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 320.560 | 292.653 | -27.906 KiB (-8.71%) | 3 | smaller |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.927 | 171.863 | -0.063 KiB (-0.04%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.503 | 0.469 | -0.033 ms (-6.64%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.751 | 0.656 | -0.095 ms (-12.61%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.943 | 5.041 | -0.902 ms (-15.18%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 33750.050 | 38832.441 | +5082.391 roots/s (+15.06%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 6.536 | 5.543 | -0.993 ms (-15.20%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 31093.720 | 36056.338 | +4962.618 roots/s (+15.96%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 9.011 | 7.790 | -1.221 ms (-13.55%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 23247.140 | 25027.245 | +1780.106 roots/s (+7.66%) | 9 | faster |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 197.614 | 177.098 | -20.517 KiB (-10.38%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 29.255 | 32.916 | +3.661 KiB (+12.51%) | 6 | larger |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 70.800 | 68.241 | -2.559 KiB (-3.61%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 4.384 | 3.137 | -1.247 KiB (-28.45%) | 6 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 8.857 | 4.667 | -4.190 us/projection (-47.31%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 112576.953 | 216124.980 | +103548.027 projections/s (+91.98%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.527 | 35.895 | -7.633 KiB (-17.54%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 38.371 | 41.653 | +3.282 KiB (+8.55%) | 3 | larger |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 579.062 | 434.312 | -144.750 B/projection (-25.00%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 117.375 | 140.000 | +22.625 B/projection (+19.28%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 11.585 | 5.863 | -5.721 us/projection (-49.39%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 83072.003 | 173637.952 | +90565.949 projections/s (+109.02%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 48.465 | 39.090 | -9.375 KiB (-19.34%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 52.425 | 56.621 | +4.196 KiB (+8.00%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 594.062 | 434.312 | -159.750 B/projection (-26.89%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 181.375 | 191.125 | +9.750 B/projection (+5.38%) | 3 | larger |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 11.025 | 8.672 | -2.354 ms (-21.35%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18221.091 | 23259.194 | +5038.103 roots/s (+27.65%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 12.187 | 9.412 | -2.775 ms (-22.77%) | 9 | faster |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 17067.092 | 21571.094 | +4504.002 roots/s (+26.39%) | 9 | faster |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 19.115 | 41.159 | +22.044 ms (+115.32%) | 9 | slower |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10839.986 | 11292.948 | +452.962 roots/s (+4.18%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 18.921 | 18.319 | -0.602 ms (-3.18%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10269.950 | 11340.306 | +1070.356 roots/s (+10.42%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 40.715 | 31.158 | -9.557 us/root (-23.47%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 109.926 | 96.629 | -13.297 KiB (-12.10%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.836 | 50.852 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 39.986 | 31.879 | -8.107 us/root (-20.27%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 109.887 | 101.980 | -7.906 KiB (-7.19%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.836 | 50.852 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 64.849 | 45.652 | -19.197 us/root (-29.60%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 158.391 | 144.445 | -13.945 KiB (-8.80%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.961 | 87.977 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 60.378 | 46.732 | -13.646 us/root (-22.60%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 158.352 | 149.680 | -8.672 KiB (-5.48%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.961 | 87.977 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 86.342 | 66.025 | -20.318 us/root (-23.53%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 231.688 | 215.234 | -16.453 KiB (-7.10%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.461 | 137.477 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 86.714 | 66.078 | -20.635 us/root (-23.80%) | 9 | faster |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 230.594 | 218.836 | -11.758 KiB (-5.10%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.461 | 137.477 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 28.583 | 22.723 | -5.861 us/root (-20.50%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 67.684 | 60.105 | -7.578 KiB (-11.20%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.086 | 24.102 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 29.099 | 23.576 | -5.523 us/root (-18.98%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 73.395 | 67.457 | -5.938 KiB (-8.09%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.086 | 24.102 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 210.102 | 151.103 | -58.999 us/root (-28.08%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 635.336 | 621.332 | -14.004 KiB (-2.20%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.086 | 428.102 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 203.781 | 151.561 | -52.220 us/root (-25.63%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 635.074 | 626.340 | -8.734 KiB (-1.38%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.086 | 428.102 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 77.548 | 55.909 | -21.639 us/root (-27.90%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 205.840 | 191.219 | -14.621 KiB (-7.10%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.086 | 125.102 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 72.871 | 56.190 | -16.681 us/root (-22.89%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 204.754 | 194.910 | -9.844 KiB (-4.81%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.086 | 125.102 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 85.674 | 46.861 | -38.814 us/root (-45.30%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 139.610 | 126.313 | -13.297 KiB (-9.52%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.930 | 35.945 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 86.104 | 47.641 | -38.464 us/root (-44.67%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 139.571 | 131.665 | -7.906 KiB (-5.66%) | 3 | smaller |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.930 | 35.945 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 69.785 | 72.888 | +3.103 us/root (+4.45%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 220.773 | 214.492 | -6.281 KiB (-2.85%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.711 | 136.727 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 69.517 | 55.242 | -14.275 us/root (-20.53%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 224.289 | 219.359 | -4.930 KiB (-2.20%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.711 | 136.727 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 185.600 | 149.339 | -36.262 us/root (-19.54%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 763.344 | 757.062 | -6.281 KiB (-0.82%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.211 | 480.227 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 184.986 | 148.568 | -36.418 us/root (-19.69%) | 9 | faster |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 766.859 | 761.930 | -4.930 KiB (-0.64%) | 3 | within noise |
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
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 111.834 | 82.541 | -29.293 us (-26.19%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 22.851 | 17.167 | -5.684 KiB (-24.87%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.796 | 10.972 | -3.824 KiB (-25.85%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 113.667 | 83.375 | -30.292 us (-26.65%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 22.811 | 17.182 | -5.629 KiB (-24.68%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 14.943 | 11.236 | -3.707 KiB (-24.81%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 113.292 | 80.709 | -32.583 us (-28.76%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 22.851 | 17.167 | -5.684 KiB (-24.87%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.796 | 10.968 | -3.828 KiB (-25.87%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 108.041 | 82.750 | -25.291 us (-23.41%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 22.811 | 17.182 | -5.629 KiB (-24.68%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 14.943 | 11.236 | -3.707 KiB (-24.81%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 113.708 | 80.000 | -33.708 us (-29.64%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 22.852 | 17.168 | -5.684 KiB (-24.87%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.797 | 10.973 | -3.824 KiB (-25.84%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 113.125 | 84.542 | -28.583 us (-25.27%) | 9 | faster |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 22.812 | 17.183 | -5.629 KiB (-24.68%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 14.944 | 11.237 | -3.707 KiB (-24.81%) | 3 | smaller |
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
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 428.647 | 379.533 | -49.114 KiB (-11.46%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 315.032 | 290.361 | -24.671 KiB (-7.83%) | 3 | smaller |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.629 | 0.497 | -0.132 ms (-20.94%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.999 | 0.672 | -0.327 ms (-32.73%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 6.401 | 4.354 | -2.047 ms (-31.97%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 30791.140 | 45704.717 | +14913.577 roots/s (+48.43%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 7.006 | 4.989 | -2.017 ms (-28.79%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 26565.569 | 40878.896 | +14313.327 roots/s (+53.88%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 9.283 | 7.195 | -2.087 ms (-22.48%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 21629.609 | 27860.974 | +6231.365 roots/s (+28.81%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 283.894 | 196.382 | -87.512 KiB (-30.83%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 41.839 | 41.003 | -0.836 KiB (-2.00%) | 6 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 97.434 | 73.391 | -24.043 KiB (-24.68%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 11.091 | 13.382 | +2.291 KiB (+20.66%) | 6 | larger |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1259.475 | 1221.868 | -37.606 KiB (-2.99%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.363 | 531.383 | +0.020 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.745 | 0.692 | -0.052 ms (-7.01%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.242 | 1.033 | -0.209 ms (-16.81%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 10.320 | 7.763 | -2.557 ms (-24.78%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 19245.961 | 25919.608 | +6673.647 roots/s (+34.68%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 11.378 | 8.596 | -2.783 ms (-24.46%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 17819.290 | 23447.802 | +5628.513 roots/s (+31.59%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 13.934 | 11.350 | -2.584 ms (-18.55%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 14376.939 | 17592.212 | +3215.273 roots/s (+22.36%) | 9 | faster |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 693.486 | 665.918 | -27.568 KiB (-3.98%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 38.004 | 31.732 | -6.271 KiB (-16.50%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 199.057 | 188.973 | -10.084 KiB (-5.07%) | 6 | smaller |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.897 | 5.107 | +1.210 KiB (+31.04%) | 6 | larger |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1799.189 | 1629.948 | -169.241 KiB (-9.41%) | 3 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.792 | 883.808 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.917 | 0.801 | -0.116 ms (-12.68%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.602 | 1.910 | -0.692 ms (-26.59%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 27.572 | 20.263 | -7.309 ms (-26.51%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 7310.543 | 9808.169 | +2497.626 roots/s (+34.16%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 28.458 | 21.165 | -7.293 ms (-25.63%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 6855.086 | 9382.330 | +2527.244 roots/s (+36.87%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 31.617 | 23.969 | -7.648 ms (-24.19%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 6371.118 | 8361.859 | +1990.742 roots/s (+31.25%) | 9 | faster |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1199.479 | 1066.283 | -133.196 KiB (-11.10%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 52.436 | 53.752 | +1.316 KiB (+2.51%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 323.017 | 297.457 | -25.560 KiB (-7.91%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 14.800 | 7.949 | -6.851 KiB (-46.29%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1393.275 | 1356.667 | -36.608 KiB (-2.63%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.398 | 554.414 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.932 | 0.843 | -0.089 ms (-9.53%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.808 | 1.428 | -0.380 ms (-21.02%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 18.021 | 14.849 | -3.173 ms (-17.60%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 11214.115 | 13457.479 | +2243.364 roots/s (+20.00%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 18.141 | 14.628 | -3.513 ms (-19.37%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11213.145 | 13452.726 | +2239.581 roots/s (+19.97%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 21.074 | 18.029 | -3.045 ms (-14.45%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 9434.964 | 11218.597 | +1783.633 roots/s (+18.90%) | 9 | faster |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1166.908 | 1145.230 | -21.678 KiB (-1.86%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 48.164 | 41.182 | -6.982 KiB (-14.50%) | 6 | smaller |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 314.291 | 307.629 | -6.662 KiB (-2.12%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 4.218 | 5.764 | +1.546 KiB (+36.65%) | 6 | larger |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 298.886 | 253.656 | -45.229 KiB (-15.13%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 175.188 | 174.895 | -0.293 KiB (-0.17%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.484 | 0.466 | -0.018 ms (-3.76%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.791 | 0.619 | -0.171 ms (-21.68%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 5.941 | 4.736 | -1.205 ms (-20.28%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 33274.643 | 38246.710 | +4972.067 roots/s (+14.94%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 6.452 | 5.402 | -1.050 ms (-16.27%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 30586.301 | 37572.211 | +6985.910 roots/s (+22.84%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 8.753 | 7.783 | -0.970 ms (-11.08%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 22743.749 | 25095.677 | +2351.928 roots/s (+10.34%) | 9 | faster |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 205.014 | 183.117 | -21.896 KiB (-10.68%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 32.738 | 28.152 | -4.586 KiB (-14.01%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 68.316 | 64.733 | -3.583 KiB (-5.24%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 7.323 | 3.064 | -4.259 KiB (-58.15%) | 6 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 9.527 | 4.280 | -5.247 us/projection (-55.07%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 103364.857 | 231743.784 | +128378.927 projections/s (+124.20%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.730 | 37.535 | -8.195 KiB (-17.92%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 42.299 | 45.827 | +3.528 KiB (+8.34%) | 3 | larger |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 604.438 | 460.703 | -143.734 B/projection (-23.78%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 127.250 | 139.859 | +12.609 B/projection (+9.91%) | 3 | larger |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 13.040 | 5.381 | -7.660 us/projection (-58.74%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 77220.921 | 187545.799 | +110324.878 projections/s (+142.87%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 50.730 | 40.730 | -10.000 KiB (-19.71%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 57.438 | 61.998 | +4.560 KiB (+7.94%) | 3 | larger |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 620.438 | 460.703 | -159.734 B/projection (-25.75%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 191.250 | 190.984 | -0.266 B/projection (-0.14%) | 3 | within noise |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 10.662 | 7.782 | -2.880 ms (-27.01%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 18814.012 | 25748.171 | +6934.159 roots/s (+36.86%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 11.854 | 8.596 | -3.258 ms (-27.49%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 16940.479 | 23220.152 | +6279.674 roots/s (+37.07%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 18.564 | 15.248 | -3.316 ms (-17.86%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 10724.244 | 13162.839 | +2438.594 roots/s (+22.74%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 19.102 | 15.156 | -3.946 ms (-20.66%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 10481.036 | 13153.027 | +2671.991 roots/s (+25.49%) | 9 | faster |
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
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 42.305 | 28.849 | -13.456 us/root (-31.81%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 107.686 | 95.539 | -12.146 KiB (-11.28%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.094 | 51.109 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 43.870 | 29.180 | -14.690 us/root (-33.49%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 107.646 | 99.250 | -8.396 KiB (-7.80%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.094 | 51.109 | +0.016 KiB (+0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 65.863 | 43.197 | -22.667 us/root (-34.41%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 159.933 | 145.752 | -14.181 KiB (-8.87%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.219 | 88.234 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 64.232 | 42.566 | -21.665 us/root (-33.73%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 158.776 | 149.158 | -9.618 KiB (-6.06%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.219 | 88.234 | +0.016 KiB (+0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 94.495 | 60.350 | -34.145 us/root (-36.13%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 236.351 | 220.354 | -15.997 KiB (-6.77%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.719 | 137.734 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 101.875 | 60.478 | -41.397 us/root (-40.64%) | 9 | faster |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 235.710 | 224.174 | -11.536 KiB (-4.89%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.719 | 137.734 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 30.083 | 20.944 | -9.139 us/root (-30.38%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 66.598 | 58.370 | -8.228 KiB (-12.35%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.344 | 24.359 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 28.160 | 21.388 | -6.772 us/root (-24.05%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 72.309 | 65.917 | -6.392 KiB (-8.84%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.344 | 24.359 | +0.016 KiB (+0.06%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 253.326 | 140.773 | -112.552 us/root (-44.43%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 639.807 | 624.949 | -14.857 KiB (-2.32%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.344 | 428.359 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 208.587 | 141.229 | -67.358 us/root (-32.29%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 639.416 | 629.922 | -9.494 KiB (-1.48%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.344 | 428.359 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 72.326 | 52.576 | -19.750 us/root (-27.31%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 208.990 | 193.785 | -15.205 KiB (-7.28%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.344 | 125.359 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 72.182 | 52.224 | -19.958 us/root (-27.65%) | 9 | faster |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 208.279 | 197.992 | -10.287 KiB (-4.94%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.344 | 125.359 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 88.043 | 44.882 | -43.161 us/root (-49.02%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 137.534 | 125.427 | -12.107 KiB (-8.80%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.188 | 36.203 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 84.397 | 45.529 | -38.868 us/root (-46.05%) | 9 | faster |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 137.495 | 129.138 | -8.357 KiB (-6.08%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.188 | 36.203 | +0.016 KiB (+0.04%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 66.646 | 50.009 | -16.637 us/root (-24.96%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 224.299 | 217.340 | -6.959 KiB (-3.10%) | 3 | smaller |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.969 | 136.984 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 85.613 | 50.155 | -35.458 us/root (-41.42%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 227.814 | 222.434 | -5.381 KiB (-2.36%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.969 | 136.984 | +0.016 KiB (+0.01%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 201.048 | 133.833 | -67.215 us/root (-33.43%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 767.150 | 760.059 | -7.092 KiB (-0.92%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.469 | 480.484 | +0.016 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 194.021 | 132.728 | -61.293 us/root (-31.59%) | 9 | faster |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 770.666 | 765.152 | -5.514 KiB (-0.72%) | 3 | within noise |
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
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 116.584 | 82.917 | -33.667 us (-28.88%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 23.821 | 17.204 | -6.617 KiB (-27.78%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 16.188 | 11.880 | -4.309 KiB (-26.62%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 112.666 | 85.417 | -27.249 us (-24.19%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 23.977 | 17.348 | -6.629 KiB (-27.65%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 16.344 | 12.168 | -4.176 KiB (-25.55%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 116.709 | 77.292 | -39.417 us (-33.77%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 23.821 | 17.204 | -6.617 KiB (-27.78%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 16.188 | 11.880 | -4.309 KiB (-26.62%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 116.500 | 78.166 | -38.334 us (-32.90%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 23.977 | 17.352 | -6.625 KiB (-27.63%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 16.344 | 12.168 | -4.176 KiB (-25.55%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 110.292 | 78.750 | -31.542 us (-28.60%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 23.822 | 17.205 | -6.617 KiB (-27.78%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 16.189 | 11.877 | -4.312 KiB (-26.64%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 117.500 | 82.292 | -35.208 us (-29.96%) | 9 | faster |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 23.978 | 17.353 | -6.625 KiB (-27.63%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 16.345 | 12.169 | -4.176 KiB (-25.55%) | 3 | smaller |
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
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 211.333 | 177.250 | -34.083 us/row (-16.13%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 3536.000 | 848.000 | -2688.000 B/row (-76.02%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 14602.000 | 9036.000 | -5566.000 B/row (-38.12%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 224.583 | 183.834 | -40.749 us/row (-18.14%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 3586.000 | 848.000 | -2738.000 B/row (-76.35%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 14602.000 | 10013.000 | -4589.000 B/row (-31.43%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 284.750 | 224.833 | -59.917 us/row (-21.04%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 3536.000 | 848.000 | -2688.000 B/row (-76.02%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 14602.000 | 7410.000 | -7192.000 B/row (-49.25%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 266.500 | 200.500 | -66.000 us/row (-24.77%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 3486.000 | 848.000 | -2638.000 B/row (-75.67%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 14552.000 | 8131.000 | -6421.000 B/row (-44.12%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 321.666 | 232.167 | -89.499 us/row (-27.82%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 4426.000 | 1128.000 | -3298.000 B/row (-74.51%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 15442.000 | 11800.000 | -3642.000 B/row (-23.59%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 304.917 | 214.000 | -90.917 us/row (-29.82%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 4326.000 | 1128.000 | -3198.000 B/row (-73.93%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 15442.000 | 12858.000 | -2584.000 B/row (-16.73%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 726.292 | 445.250 | -281.042 us/row (-38.70%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 7736.000 | 2248.000 | -5488.000 B/row (-70.94%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 25739.000 | 20116.000 | -5623.000 B/row (-21.85%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 648.833 | 363.125 | -285.708 us/row (-44.03%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 7736.000 | 2248.000 | -5488.000 B/row (-70.94%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23874.000 | 23398.000 | -476.000 B/row (-1.99%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 283.416 | 280.916 | -2.500 us/row (-0.88%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 5646.000 | 1624.000 | -4022.000 B/row (-71.24%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15866.000 | 18643.000 | +2777.000 B/row (+17.50%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 277.250 | 256.542 | -20.708 us/row (-7.47%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5642.000 | 1656.000 | -3986.000 B/row (-70.65%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15748.000 | 19119.000 | +3371.000 B/row (+21.41%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 287.625 | 269.416 | -18.209 us/row (-6.33%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 5696.000 | 1624.000 | -4072.000 B/row (-71.49%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15075.000 | 17838.000 | +2763.000 B/row (+18.33%) | 9 | larger |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 266.791 | 254.042 | -12.749 us/row (-4.78%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5592.000 | 1656.000 | -3936.000 B/row (-70.39%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 14922.000 | 18314.000 | +3392.000 B/row (+22.73%) | 9 | larger |
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
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 178.458 | 124.000 | -54.458 us/row (-30.52%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 2472.000 | 1544.000 | -928.000 B/row (-37.54%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 14690.000 | 7892.000 | -6798.000 B/row (-46.28%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 179.250 | 124.000 | -55.250 us/row (-30.82%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 2422.000 | 1544.000 | -878.000 B/row (-36.25%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 14690.000 | 8292.000 | -6398.000 B/row (-43.55%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 217.667 | 160.042 | -57.625 us/row (-26.47%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 3194.000 | 2216.000 | -978.000 B/row (-30.62%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 15426.000 | 9653.000 | -5773.000 B/row (-37.42%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 213.000 | 157.541 | -55.459 us/row (-26.04%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 3194.000 | 2216.000 | -978.000 B/row (-30.62%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 15426.000 | 9937.000 | -5489.000 B/row (-35.58%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 265.917 | 208.459 | -57.458 us/row (-21.61%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 4040.000 | 3112.000 | -928.000 B/row (-22.97%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 16746.000 | 12882.000 | -3864.000 B/row (-23.07%) | 9 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 280.167 | 209.583 | -70.584 us/row (-25.19%) | 9 | faster |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 4040.000 | 3112.000 | -928.000 B/row (-22.97%) | 1 | smaller |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 16746.000 | 12992.000 | -3754.000 B/row (-22.42%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 152.417 | 96.833 | -55.584 us/row (-36.47%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1968.000 | 1040.000 | -928.000 B/row (-47.15%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 14186.000 | 6857.000 | -7329.000 B/row (-51.66%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 145.583 | 100.125 | -45.458 us/row (-31.22%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 2018.000 | 1040.000 | -978.000 B/row (-48.46%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 14186.000 | 7007.000 | -7179.000 B/row (-50.61%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 530.750 | 439.625 | -91.125 us/row (-17.17%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 9432.000 | 8504.000 | -928.000 B/row (-9.84%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27242.000 | 26816.000 | -426.000 B/row (-1.56%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 524.375 | 434.334 | -90.041 us/row (-17.17%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 9432.000 | 8504.000 | -928.000 B/row (-9.84%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 27429.000 | 27107.000 | -322.000 B/row (-1.17%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 265.208 | 185.833 | -79.375 us/row (-29.93%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3914.000 | 2936.000 | -978.000 B/row (-24.99%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 16082.000 | 11360.000 | -4722.000 B/row (-29.36%) | 9 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 260.708 | 184.541 | -76.167 us/row (-29.22%) | 9 | faster |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3914.000 | 2936.000 | -978.000 B/row (-24.99%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 16082.000 | 11684.000 | -4398.000 B/row (-27.35%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 239.000 | 167.667 | -71.333 us/row (-29.85%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 2522.000 | 1544.000 | -978.000 B/row (-38.78%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 14690.000 | 7705.000 | -6985.000 B/row (-47.55%) | 9 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 236.875 | 166.083 | -70.792 us/row (-29.89%) | 9 | faster |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 2472.000 | 1544.000 | -928.000 B/row (-37.54%) | 1 | smaller |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 14690.000 | 8089.000 | -6601.000 B/row (-44.94%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 266.250 | 205.625 | -60.625 us/row (-22.77%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 3312.000 | 2384.000 | -928.000 B/row (-28.02%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 15530.000 | 10887.000 | -4643.000 B/row (-29.90%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 266.041 | 204.084 | -61.957 us/row (-23.29%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 3362.000 | 2384.000 | -978.000 B/row (-29.09%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 15530.000 | 11328.000 | -4202.000 B/row (-27.06%) | 9 | smaller |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 642.875 | 536.792 | -106.083 us/row (-16.50%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 6672.000 | 5744.000 | -928.000 B/row (-13.91%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23321.000 | 23127.000 | -194.000 B/row (-0.83%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 647.584 | 533.833 | -113.751 us/row (-17.57%) | 9 | faster |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 6722.000 | 5744.000 | -978.000 B/row (-14.55%) | 1 | smaller |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 24874.000 | 24672.000 | -202.000 B/row (-0.81%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 171.750 | 127.375 | -44.375 us/row (-25.84%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 3024.000 | 1832.000 | -1192.000 B/row (-39.42%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 15138.000 | 7245.000 | -7893.000 B/row (-52.14%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 154.458 | 117.209 | -37.249 us/row (-24.12%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 2824.000 | 1864.000 | -960.000 B/row (-33.99%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 14938.000 | 8109.000 | -6829.000 B/row (-45.72%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 177.250 | 136.958 | -40.292 us/row (-22.73%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 2974.000 | 1832.000 | -1142.000 B/row (-38.40%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 15138.000 | 8169.000 | -6969.000 B/row (-46.04%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 149.042 | 124.750 | -24.292 us/row (-16.30%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 2824.000 | 1864.000 | -960.000 B/row (-33.99%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 14938.000 | 9033.000 | -5905.000 B/row (-39.53%) | 9 | smaller |
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
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 204.542 | 186.250 | -18.292 us/row (-8.94%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 3710.000 | 1576.000 | -2134.000 B/row (-57.52%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 14826.000 | 10314.000 | -4512.000 B/row (-30.43%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 186.875 | 180.750 | -6.125 us/row (-3.28%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3610.000 | 1608.000 | -2002.000 B/row (-55.46%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 14626.000 | 10918.000 | -3708.000 B/row (-25.35%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 224.083 | 203.958 | -20.125 us/row (-8.98%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 3710.000 | 1576.000 | -2134.000 B/row (-57.52%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 14826.000 | 11508.000 | -3318.000 B/row (-22.38%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 187.959 | 188.125 | +0.166 us/row (+0.09%) | 9 | within noise |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 3610.000 | 1608.000 | -2002.000 B/row (-55.46%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 14626.000 | 11872.000 | -2754.000 B/row (-18.83%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 168.750 | 124.792 | -43.958 us/row (-26.05%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 2744.000 | 1768.000 | -976.000 B/row (-35.57%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 15042.000 | 9851.000 | -5191.000 B/row (-34.51%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 157.167 | 125.250 | -31.917 us/row (-20.31%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2612.000 | 1960.000 | -652.000 B/row (-24.96%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 14810.000 | 10211.000 | -4599.000 B/row (-31.05%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 176.166 | 123.250 | -52.916 us/row (-30.04%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 2744.000 | 1768.000 | -976.000 B/row (-35.57%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 15042.000 | 9574.000 | -5468.000 B/row (-36.35%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 149.834 | 127.292 | -22.542 us/row (-15.04%) | 9 | faster |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 2612.000 | 1960.000 | -652.000 B/row (-24.96%) | 1 | smaller |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 14810.000 | 9974.000 | -4836.000 B/row (-32.65%) | 9 | smaller |
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
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 206.542 | 31.834 | -174.708 us/row (-84.59%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 3810.000 | 32.000 | -3778.000 B/row (-99.16%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 14826.000 | 3642.000 | -11184.000 B/row (-75.44%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 178.875 | 27.000 | -151.875 us/row (-84.91%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 3560.000 | 32.000 | -3528.000 B/row (-99.10%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 14626.000 | 3590.000 | -11036.000 B/row (-75.45%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 211.209 | 32.459 | -178.750 us/row (-84.63%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 3760.000 | 32.000 | -3728.000 B/row (-99.15%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 14826.000 | 3644.000 | -11182.000 B/row (-75.42%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeMany | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.entityShape | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 185.292 | 26.875 | -158.417 us/row (-85.50%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3510.000 | 32.000 | -3478.000 B/row (-99.09%) | 1 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 14626.000 | 3593.000 | -11033.000 B/row (-75.43%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3738.167 | 3354.667 | -383.500 us (-10.26%) | 9 | faster |
| 3.13 | model-preparation | model.prepared | retainedBytes | 415992.000 | 427360.000 | +11368.000 B (+2.73%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 436760.000 | 439696.000 | +2936.000 B (+0.67%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | | | | | missing on base |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | | | | | missing on base |
| 3.13 | model-preparation | model.prepared.family | transientBytes | | | | | missing on base |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 107.878 | 19.936 | -87.942 us/row (-81.52%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1583.117 | 915.500 | -667.617 B/row (-42.17%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3677.125 | 1822.250 | -1854.875 B/row (-50.44%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 104.444 | 20.653 | -83.791 us/row (-80.23%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2767.531 | 1917.000 | -850.531 B/row (-30.73%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5831.492 | 2222.328 | -3609.164 B/row (-61.89%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 111.323 | 24.969 | -86.354 us/row (-77.57%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1738.469 | 1047.000 | -691.469 B/row (-39.77%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4206.812 | 2266.375 | -1940.438 B/row (-46.13%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 110.220 | 26.461 | -83.759 us/row (-75.99%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2921.812 | 2053.000 | -868.812 B/row (-29.74%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6271.688 | 2588.688 | -3683.000 B/row (-58.72%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 125.089 | 40.896 | -84.193 us/row (-67.31%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2368.000 | 1581.000 | -787.000 B/row (-33.23%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 5907.625 | 3734.500 | -2173.125 B/row (-36.79%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 134.464 | 42.021 | -92.443 us/row (-68.75%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3568.125 | 2605.000 | -963.125 B/row (-26.99%) | 1 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 7988.000 | 3966.750 | -4021.250 B/row (-50.34%) | 9 | smaller |
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
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 248.000 | 184.708 | -63.292 us/row (-25.52%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 3632.000 | 856.000 | -2776.000 B/row (-76.43%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 15066.000 | 9716.000 | -5350.000 B/row (-35.51%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 242.583 | 195.875 | -46.708 us/row (-19.25%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 3632.000 | 856.000 | -2776.000 B/row (-76.43%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 15066.000 | 10853.000 | -4213.000 B/row (-27.96%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 324.250 | 222.167 | -102.083 us/row (-31.48%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 3682.000 | 856.000 | -2826.000 B/row (-76.75%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 15066.000 | 8130.000 | -6936.000 B/row (-46.04%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 309.833 | 207.709 | -102.124 us/row (-32.96%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 3632.000 | 856.000 | -2776.000 B/row (-76.43%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 15066.000 | 8987.000 | -6079.000 B/row (-40.35%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 345.583 | 233.250 | -112.333 us/row (-32.51%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 4422.000 | 1136.000 | -3286.000 B/row (-74.31%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 15970.000 | 12592.000 | -3378.000 B/row (-21.15%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 339.375 | 215.875 | -123.500 us/row (-36.39%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 4422.000 | 1136.000 | -3286.000 B/row (-74.31%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 15970.000 | 13786.000 | -2184.000 B/row (-13.68%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 753.250 | 429.291 | -323.959 us/row (-43.01%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 7832.000 | 2256.000 | -5576.000 B/row (-71.20%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 26259.000 | 20852.000 | -5407.000 B/row (-20.59%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 712.292 | 348.041 | -364.251 us/row (-51.14%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 7932.000 | 2256.000 | -5676.000 B/row (-71.56%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 24604.000 | 24270.000 | -334.000 B/row (-1.36%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 314.959 | 277.958 | -37.001 us/row (-11.75%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 6008.000 | 1640.000 | -4368.000 B/row (-72.70%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15890.000 | 19483.000 | +3593.000 B/row (+22.61%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 295.542 | 263.250 | -32.292 us/row (-10.93%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 5746.000 | 1672.000 | -4074.000 B/row (-70.90%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 15702.000 | 20123.000 | +4421.000 B/row (+28.16%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 331.333 | 274.041 | -57.292 us/row (-17.29%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 5908.000 | 1640.000 | -4268.000 B/row (-72.24%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15440.000 | 18542.000 | +3102.000 B/row (+20.09%) | 9 | larger |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 300.166 | 254.625 | -45.541 us/row (-15.17%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 5696.000 | 1672.000 | -4024.000 B/row (-70.65%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 15370.000 | 19182.000 | +3812.000 B/row (+24.80%) | 9 | larger |
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
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 191.459 | 133.250 | -58.209 us/row (-30.40%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 2528.000 | 1560.000 | -968.000 B/row (-38.29%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 15186.000 | 8556.000 | -6630.000 B/row (-43.66%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 191.916 | 130.291 | -61.625 us/row (-32.11%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 2528.000 | 1560.000 | -968.000 B/row (-38.29%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 15186.000 | 9020.000 | -6166.000 B/row (-40.60%) | 9 | smaller |
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
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 3200.000 | 2232.000 | -968.000 B/row (-30.25%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 15858.000 | 10413.000 | -5445.000 B/row (-34.34%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 234.709 | 166.083 | -68.626 us/row (-29.24%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 3200.000 | 2232.000 | -968.000 B/row (-30.25%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 15858.000 | 10769.000 | -5089.000 B/row (-32.09%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 301.584 | 206.333 | -95.251 us/row (-31.58%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 4096.000 | 3128.000 | -968.000 B/row (-23.63%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 17234.000 | 13754.000 | -3480.000 B/row (-20.19%) | 9 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 295.167 | 207.833 | -87.334 us/row (-29.59%) | 9 | faster |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 4096.000 | 3128.000 | -968.000 B/row (-23.63%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 17234.000 | 13912.000 | -3322.000 B/row (-19.28%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 166.458 | 108.167 | -58.291 us/row (-35.02%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 2016.000 | 1048.000 | -968.000 B/row (-48.02%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 14674.000 | 7457.000 | -7217.000 B/row (-49.18%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 165.458 | 108.000 | -57.458 us/row (-34.73%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1966.000 | 1048.000 | -918.000 B/row (-46.69%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 14674.000 | 7671.000 | -7003.000 B/row (-47.72%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 557.666 | 424.667 | -132.999 us/row (-23.85%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 9488.000 | 8520.000 | -968.000 B/row (-10.20%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27746.000 | 27472.000 | -274.000 B/row (-0.99%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 578.167 | 411.083 | -167.084 us/row (-28.90%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 9488.000 | 8520.000 | -968.000 B/row (-10.20%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 27925.000 | 27827.000 | -98.000 B/row (-0.35%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 268.583 | 188.500 | -80.083 us/row (-29.82%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3920.000 | 2952.000 | -968.000 B/row (-24.69%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 16578.000 | 12016.000 | -4562.000 B/row (-27.52%) | 9 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 264.167 | 187.708 | -76.459 us/row (-28.94%) | 9 | faster |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3920.000 | 2952.000 | -968.000 B/row (-24.69%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 16578.000 | 12420.000 | -4158.000 B/row (-25.08%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 277.917 | 174.041 | -103.876 us/row (-37.38%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 2528.000 | 1560.000 | -968.000 B/row (-38.29%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 15186.000 | 8409.000 | -6777.000 B/row (-44.63%) | 9 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 274.292 | 171.000 | -103.292 us/row (-37.66%) | 9 | faster |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 2528.000 | 1560.000 | -968.000 B/row (-38.29%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 15186.000 | 8857.000 | -6329.000 B/row (-41.68%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 301.833 | 205.208 | -96.625 us/row (-32.01%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 3368.000 | 2400.000 | -968.000 B/row (-28.74%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 16090.000 | 11607.000 | -4483.000 B/row (-27.86%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 290.458 | 206.375 | -84.083 us/row (-28.95%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 3368.000 | 2400.000 | -968.000 B/row (-28.74%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 16090.000 | 12112.000 | -3978.000 B/row (-24.72%) | 9 | smaller |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 689.041 | 497.291 | -191.750 us/row (-27.83%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 6678.000 | 5760.000 | -918.000 B/row (-13.75%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23817.000 | 23847.000 | +30.000 B/row (+0.13%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 708.292 | 504.125 | -204.167 us/row (-28.83%) | 9 | faster |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 6728.000 | 5760.000 | -968.000 B/row (-14.39%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 25434.000 | 25456.000 | +22.000 B/row (+0.09%) | 9 | within noise |
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
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 190.333 | 134.584 | -55.749 us/row (-29.29%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 3062.000 | 1872.000 | -1190.000 B/row (-38.86%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 15666.000 | 7805.000 | -7861.000 B/row (-50.18%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 166.708 | 127.083 | -39.625 us/row (-23.77%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 2854.000 | 1904.000 | -950.000 B/row (-33.29%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 15406.000 | 8817.000 | -6589.000 B/row (-42.77%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 196.667 | 151.625 | -45.042 us/row (-22.90%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 3112.000 | 1872.000 | -1240.000 B/row (-39.85%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 15666.000 | 8713.000 | -6953.000 B/row (-44.38%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 173.333 | 136.458 | -36.875 us/row (-21.27%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 2904.000 | 1904.000 | -1000.000 B/row (-34.44%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 15406.000 | 9725.000 | -5681.000 B/row (-36.88%) | 9 | smaller |
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
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 222.250 | 195.292 | -26.958 us/row (-12.13%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 3906.000 | 1592.000 | -2314.000 B/row (-59.24%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 15290.000 | 11066.000 | -4224.000 B/row (-27.63%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 205.208 | 187.250 | -17.958 us/row (-8.75%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 3548.000 | 1624.000 | -1924.000 B/row (-54.23%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 15030.000 | 11818.000 | -3212.000 B/row (-21.37%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 239.292 | 202.708 | -36.584 us/row (-15.29%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 3856.000 | 1592.000 | -2264.000 B/row (-58.71%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 15290.000 | 12132.000 | -3158.000 B/row (-20.65%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 212.458 | 194.625 | -17.833 us/row (-8.39%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 3698.000 | 1624.000 | -2074.000 B/row (-56.08%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 15030.000 | 12708.000 | -2322.000 B/row (-15.45%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 192.958 | 135.000 | -57.958 us/row (-30.04%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 2900.000 | 1784.000 | -1116.000 B/row (-38.48%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 15554.000 | 10587.000 | -4967.000 B/row (-31.93%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 170.125 | 136.083 | -34.042 us/row (-20.01%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 2560.000 | 1992.000 | -568.000 B/row (-22.19%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 15266.000 | 11035.000 | -4231.000 B/row (-27.72%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 192.667 | 145.250 | -47.417 us/row (-24.61%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 2900.000 | 1784.000 | -1116.000 B/row (-38.48%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 15554.000 | 10342.000 | -5212.000 B/row (-33.51%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 0.000 | 2.000 | +2.000 calls/row | 1 | changed |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 168.917 | 138.625 | -30.292 us/row (-17.93%) | 9 | faster |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 2660.000 | 1992.000 | -668.000 B/row (-25.11%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 15266.000 | 10766.000 | -4500.000 B/row (-29.48%) | 9 | smaller |
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
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 224.667 | 34.125 | -190.542 us/row (-84.81%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 3856.000 | 32.000 | -3824.000 B/row (-99.17%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 15290.000 | 4010.000 | -11280.000 B/row (-73.77%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 202.459 | 27.750 | -174.709 us/row (-86.29%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 3748.000 | 32.000 | -3716.000 B/row (-99.15%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 15030.000 | 3742.000 | -11288.000 B/row (-75.10%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 223.916 | 34.167 | -189.749 us/row (-84.74%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 3806.000 | 32.000 | -3774.000 B/row (-99.16%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 15290.000 | 4012.000 | -11278.000 B/row (-73.76%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeDocument | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | | | | | missing on base |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeMany | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.entityShape | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.shapeOfDeclaration | | | | | missing on head |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 201.917 | 28.333 | -173.584 us/row (-85.97%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 3698.000 | 32.000 | -3666.000 B/row (-99.13%) | 1 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 15030.000 | 3745.000 | -11285.000 B/row (-75.08%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3673.291 | 3005.750 | -667.541 us (-18.17%) | 9 | faster |
| 3.14 | model-preparation | model.prepared | retainedBytes | 427016.000 | 439024.000 | +12008.000 B (+2.81%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 435016.000 | 445848.000 | +10832.000 B (+2.49%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | | | | | missing on base |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | | | | | missing on base |
| 3.14 | model-preparation | model.prepared.family | transientBytes | | | | | missing on base |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 100.807 | 17.707 | -83.100 us/row (-82.43%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 1616.133 | 989.156 | -626.977 B/row (-38.79%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 3675.094 | 1872.203 | -1802.891 B/row (-49.06%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 109.202 | 18.230 | -90.972 us/row (-83.31%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 2808.484 | 1990.781 | -817.703 B/row (-29.12%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 5837.680 | 2317.531 | -3520.148 B/row (-60.30%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 110.827 | 21.729 | -89.098 us/row (-80.39%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1810.688 | 1149.625 | -661.062 B/row (-36.51%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 4231.000 | 2360.000 | -1871.000 B/row (-44.22%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 119.014 | 22.277 | -96.737 us/row (-81.28%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 3008.031 | 2156.125 | -851.906 B/row (-28.32%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 6331.812 | 2705.500 | -3626.312 B/row (-57.27%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 131.417 | 37.911 | -93.505 us/row (-71.15%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 2552.000 | 1799.500 | -752.500 B/row (-29.49%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 6091.375 | 3918.000 | -2173.375 B/row (-35.68%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 136.656 | 39.984 | -96.672 us/row (-70.74%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 3788.750 | 2825.500 | -963.250 B/row (-25.42%) | 1 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 8209.750 | 4170.000 | -4039.750 B/row (-49.21%) | 9 | smaller |
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
| 3.14 | wire-insert-response | response.insert.family.wire | elapsedUs | | | | | missing on base |
| 3.14 | wire-insert-response | response.insert.family.wire | retainedBytes | | | | | missing on base |
| 3.14 | wire-insert-response | response.insert.family.wire | transientBytes | | | | | missing on base |

Deltas are advisory and never ratchet the Budget Contract.
