# Python cost report comparison

Timing deltas within 5% and byte deltas within 3% are read as noise; count deltas are exact. A cell present on one side alone, or whose unit differs, is not compared.

- The head capture is amended: envelopes re-classified under a later Budget Contract after the run its provenance names, recorded in the adjustment of conditions.json.

## instance-state

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| - | - | cpython-3.13 | aggregate.bare.after | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.before | 6384.000 | 6384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.bare.reduction | 0.617 | 0.617 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.before | 7200.000 | 7200.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | aggregate.retained.reduction | 0.547 | 0.547 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.armAgainstArm | 3.491 | 3.435 | -0.056 ratio (-1.59%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.likeForLike | 3.491 | 3.435 | -0.056 ratio (-1.59%) | 0 | within noise |
| - | - | cpython-3.13 | operation.attribute-read.vsOrdinary | 3.402 | 3.304 | -0.098 ratio (-2.88%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.armAgainstArm | 0.509 | 0.506 | -0.003 ratio (-0.58%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.likeForLike | 0.490 | 0.487 | -0.003 ratio (-0.58%) | 0 | within noise |
| - | - | cpython-3.13 | operation.construction.vsOrdinary | 1.536 | 1.531 | -0.005 ratio (-0.32%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.armAgainstArm | 2.146 | 2.086 | -0.059 ratio (-2.77%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.likeForLike | 2.146 | 2.086 | -0.059 ratio (-2.77%) | 0 | within noise |
| - | - | cpython-3.13 | operation.serialization.vsOrdinary | 2.157 | 2.150 | -0.007 ratio (-0.33%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.after | 3264.000 | 3264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.before | 7960.000 | 7960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13 | vsOrdinary.retained.reduction | 0.590 | 0.590 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.bareBytes | 928.000 | 928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.callNs | 1510.108 | 1511.600 | +1.492 ns (+0.10%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.constructNs | 6811.038 | 6859.150 | +48.112 ns (+0.71%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.directWireNs | 10584.791 | 10529.646 | -55.145 ns (-0.52%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.dumpNs | 5916.395 | 5913.500 | -2.895 ns (-0.05%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.peakBytes | 4770.000 | 4770.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionNs | 14179.750 | 14493.708 | +313.958 ns (+2.21%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionPeakBytes | 7560.000 | 7560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionRetainedBytes | 1240.000 | 1240.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionReuseNs | 12181.296 | 12462.306 | +281.010 ns (+2.31%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.projectionTransientBytes | 6320.000 | 6320.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.readNs | 85.100 | 82.917 | -2.183 ns (-2.57%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.retainedBytes | 1064.000 | 1064.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.scaffoldingNs | 343.561 | 333.533 | -10.028 ns (-2.92%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.transientBytes | 3706.000 | 3706.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | compact.unreproducedNs | 343.561 | 333.533 | -10.028 ns (-2.92%) | 0 | within noise |
| - | - | cpython-3.13/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.bareBytes | 2656.000 | 2656.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.callNs | 93.333 | 301.813 | +208.480 ns (+223.37%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.constructNs | 10265.000 | 10196.229 | -68.771 ns (-0.67%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.dumpNs | 2526.896 | 2733.896 | +207.000 ns (+8.19%) | 0 | larger |
| - | - | cpython-3.13/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.peakBytes | 4960.000 | 4960.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.readNs | 25.196 | 25.267 | +0.071 ns (+0.28%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.retainedBytes | 2792.000 | 2792.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | legacy.transientBytes | 2168.000 | 2168.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.bareBytes | 3080.000 | 3080.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.callNs | 281.133 | 279.450 | -1.684 ns (-0.60%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.constructNs | 6079.742 | 6004.842 | -74.900 ns (-1.23%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.dumpNs | 2531.125 | 2507.604 | -23.521 ns (-0.93%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nested | ordinary.peakBytes | 4416.000 | 4416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nested | ordinary.readNs | 26.296 | 26.238 | -0.058 ns (-0.22%) | 0 | within noise |
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
| - | - | cpython-3.13/nullable | compact.callNs | 1361.179 | 1357.081 | -4.098 ns (-0.30%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.constructNs | 2298.321 | 2309.002 | +10.681 ns (+0.46%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.directWireNs | 5515.459 | 5603.125 | +87.666 ns (+1.59%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.dumpNs | 1803.146 | 1804.042 | +0.896 ns (+0.05%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionNs | 7853.875 | 7729.916 | -123.959 ns (-1.58%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionPeakBytes | 2504.000 | 2504.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionRetainedBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionReuseNs | 6005.642 | 6160.725 | +155.083 ns (+2.58%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.projectionTransientBytes | 2032.000 | 2032.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.readNs | 75.127 | 75.042 | -0.085 ns (-0.11%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.scaffoldingNs | 211.975 | 217.895 | +5.920 ns (+2.79%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | compact.unreproducedNs | 211.975 | 217.895 | +5.920 ns (+2.79%) | 0 | within noise |
| - | - | cpython-3.13/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.callNs | 261.804 | 152.692 | -109.112 ns (-41.68%) | 0 | smaller |
| - | - | cpython-3.13/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.constructNs | 5431.612 | 5517.350 | +85.737 ns (+1.58%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.dumpNs | 868.333 | 894.145 | +25.812 ns (+2.97%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.readNs | 20.717 | 20.773 | +0.056 ns (+0.27%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.callNs | 214.400 | 205.505 | -8.896 ns (-4.15%) | 0 | smaller |
| - | - | cpython-3.13/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.constructNs | 1208.683 | 1258.225 | +49.542 ns (+4.10%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.dumpNs | 861.354 | 917.521 | +56.167 ns (+6.52%) | 0 | larger |
| - | - | cpython-3.13/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/nullable | ordinary.peakBytes | 2496.000 | 2496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/nullable | ordinary.readNs | 21.413 | 25.175 | +3.762 ns (+17.57%) | 0 | larger |
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
| - | - | cpython-3.13/partial | compact.callNs | 1345.192 | 1350.704 | +5.512 ns (+0.41%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.constructNs | 2149.287 | 2115.358 | -33.929 ns (-1.58%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.directWireNs | 5017.396 | 4997.854 | -19.542 ns (-0.39%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.dumpNs | 1831.895 | 1850.667 | +18.771 ns (+1.02%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.peakBytes | 3432.000 | 3432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionNs | 6946.229 | 7016.083 | +69.854 ns (+1.01%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionPeakBytes | 2416.000 | 2416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionRetainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionReuseNs | 5357.465 | 5503.931 | +146.467 ns (+2.73%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.projectionTransientBytes | 2032.000 | 2032.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.readNs | 75.433 | 75.848 | +0.415 ns (+0.55%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.retainedBytes | 432.000 | 432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.scaffoldingNs | 213.566 | 227.251 | +13.685 ns (+6.41%) | 0 | larger |
| - | - | cpython-3.13/partial | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | compact.unreproducedNs | 213.566 | 227.251 | +13.685 ns (+6.41%) | 0 | larger |
| - | - | cpython-3.13/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.callNs | 264.500 | 185.791 | -78.709 ns (-29.76%) | 0 | smaller |
| - | - | cpython-3.13/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.constructNs | 5074.187 | 5140.500 | +66.313 ns (+1.31%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.dumpNs | 867.417 | 886.312 | +18.896 ns (+2.18%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.peakBytes | 1704.000 | 1704.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.readNs | 21.052 | 22.808 | +1.756 ns (+8.34%) | 0 | larger |
| - | - | cpython-3.13/partial | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | legacy.transientBytes | 728.000 | 728.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.callNs | 203.019 | 215.685 | +12.666 ns (+6.24%) | 0 | larger |
| - | - | cpython-3.13/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.constructNs | 951.440 | 943.794 | -7.646 ns (-0.80%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.dumpNs | 886.667 | 905.021 | +18.355 ns (+2.07%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/partial | ordinary.peakBytes | 1608.000 | 1608.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/partial | ordinary.readNs | 21.596 | 22.717 | +1.121 ns (+5.19%) | 0 | larger |
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
| - | - | cpython-3.13/polymorphic | compact.callNs | 1284.673 | 1349.902 | +65.229 ns (+5.08%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.constructNs | 2229.744 | 2204.452 | -25.292 ns (-1.13%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.directWireNs | 5794.813 | 5720.709 | -74.104 ns (-1.28%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.dumpNs | 1591.000 | 1648.417 | +57.417 ns (+3.61%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.peakBytes | 3408.000 | 3408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionNs | 7573.729 | 7754.458 | +180.729 ns (+2.39%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionPeakBytes | 2776.000 | 2776.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionRetainedBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionReuseNs | 5794.523 | 5872.456 | +77.933 ns (+1.34%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.projectionTransientBytes | 2304.000 | 2304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.readNs | 80.211 | 77.402 | -2.810 ns (-3.50%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.retainedBytes | 408.000 | 408.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.scaffoldingNs | 214.131 | 197.811 | -16.320 ns (-7.62%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | compact.unreproducedNs | 214.131 | 197.811 | -16.320 ns (-7.62%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.bareBytes | 648.000 | 648.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.callNs | 150.506 | 129.542 | -20.964 ns (-13.93%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.constructNs | 4170.160 | 4221.125 | +50.964 ns (+1.22%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.dumpNs | 794.625 | 809.271 | +14.646 ns (+1.84%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.peakBytes | 1304.000 | 1304.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.readNs | 23.931 | 22.583 | -1.348 ns (-5.63%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | legacy.retainedBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | legacy.transientBytes | 520.000 | 520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.bareBytes | 1160.000 | 1160.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.callNs | 190.210 | 151.420 | -38.790 ns (-20.39%) | 0 | smaller |
| - | - | cpython-3.13/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.constructNs | 1046.144 | 1106.663 | +60.519 ns (+5.78%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.dumpNs | 769.125 | 816.646 | +47.521 ns (+6.18%) | 0 | larger |
| - | - | cpython-3.13/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/polymorphic | ordinary.peakBytes | 2448.000 | 2448.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/polymorphic | ordinary.readNs | 24.164 | 22.152 | -2.012 ns (-8.33%) | 0 | smaller |
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
| - | - | cpython-3.13/shallow | compact.callNs | 1333.219 | 1345.796 | +12.577 ns (+0.94%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.constructNs | 2054.344 | 2038.287 | -16.056 ns (-0.78%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.directWireNs | 6941.729 | 7142.750 | +201.021 ns (+2.90%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.dumpNs | 1354.375 | 1390.520 | +36.145 ns (+2.67%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.peakBytes | 3384.000 | 3384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionNs | 8690.083 | 8957.354 | +267.271 ns (+3.08%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.projectionPeakBytes | 3358.000 | 3358.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionRetainedBytes | 430.000 | 430.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.projectionReuseNs | 5279.383 | 5507.196 | +227.812 ns (+4.32%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.projectionTransientBytes | 2928.000 | 2928.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.readNs | 88.714 | 87.662 | -1.052 ns (-1.19%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.retainedBytes | 384.000 | 384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.scaffoldingNs | 204.991 | 213.771 | +8.780 ns (+4.28%) | 0 | larger |
| - | - | cpython-3.13/shallow | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | compact.unreproducedNs | 204.991 | 213.771 | +8.780 ns (+4.28%) | 0 | larger |
| - | - | cpython-3.13/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.callNs | 188.856 | 196.475 | +7.618 ns (+4.03%) | 0 | larger |
| - | - | cpython-3.13/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.constructNs | 2789.769 | 2772.858 | -16.910 ns (-0.61%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.dumpNs | 700.834 | 718.354 | +17.520 ns (+2.50%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.peakBytes | 1202.000 | 1202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.readNs | 25.375 | 25.891 | +0.516 ns (+2.03%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.retainedBytes | 696.000 | 696.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | legacy.transientBytes | 506.000 | 506.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.bareBytes | 560.000 | 560.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.callNs | 175.575 | 223.743 | +48.168 ns (+27.43%) | 0 | larger |
| - | - | cpython-3.13/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.constructNs | 781.092 | 799.090 | +17.998 ns (+2.30%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.dumpNs | 714.250 | 723.145 | +8.895 ns (+1.25%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/shallow | ordinary.peakBytes | 1416.000 | 1416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/shallow | ordinary.readNs | 25.943 | 25.984 | +0.042 ns (+0.16%) | 0 | within noise |
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
| - | - | cpython-3.13/warmed | compact.callNs | 1586.002 | 1765.196 | +179.194 ns (+11.30%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.constructNs | 4176.831 | 4122.992 | -53.840 ns (-1.29%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.dumpNs | 1718.479 | 1784.438 | +65.958 ns (+3.84%) | 0 | larger |
| - | - | cpython-3.13/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.peakBytes | 3384.000 | 3384.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.readNs | 91.828 | 90.021 | -1.807 ns (-1.97%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.retainedBytes | 806.000 | 806.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.scaffoldingNs | 245.993 | 241.403 | -4.589 ns (-1.87%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.transientBytes | 2578.000 | 2578.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | compact.unreproducedNs | 245.993 | 241.403 | -4.589 ns (-1.87%) | 0 | within noise |
| - | - | cpython-3.13/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.bareBytes | 886.000 | 886.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.callNs | 85.595 | 89.135 | +3.540 ns (+4.14%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.constructNs | 3910.550 | 3932.156 | +21.606 ns (+0.55%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.dumpNs | 711.521 | 736.375 | +24.854 ns (+3.49%) | 0 | larger |
| - | - | cpython-3.13/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.peakBytes | 1494.000 | 1494.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.readNs | 25.302 | 25.474 | +0.172 ns (+0.68%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.retainedBytes | 1022.000 | 1022.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | legacy.transientBytes | 472.000 | 472.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.bareBytes | 798.000 | 798.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.callNs | 190.673 | 190.548 | -0.125 ns (-0.07%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.constructNs | 1759.035 | 1745.244 | -13.792 ns (-0.78%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.dumpNs | 716.437 | 726.042 | +9.604 ns (+1.34%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/warmed | ordinary.peakBytes | 1762.000 | 1762.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/warmed | ordinary.readNs | 25.870 | 25.760 | -0.109 ns (-0.42%) | 0 | within noise |
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
| - | - | cpython-3.13/wide | compact.callNs | 1382.158 | 1327.054 | -55.104 ns (-3.99%) | 0 | smaller |
| - | - | cpython-3.13/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.constructNs | 2612.904 | 2608.737 | -4.167 ns (-0.16%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.directWireNs | 6881.542 | 6761.542 | -120.000 ns (-1.74%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.dumpNs | 2407.542 | 2428.646 | +21.104 ns (+0.88%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.peakBytes | 3512.000 | 3512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionNs | 9286.730 | 9387.542 | +100.812 ns (+1.09%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionPeakBytes | 3240.000 | 3240.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionRetainedBytes | 664.000 | 664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionReuseNs | 7323.435 | 7442.610 | +119.175 ns (+1.63%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.projectionTransientBytes | 2576.000 | 2576.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.readNs | 79.258 | 79.270 | +0.012 ns (+0.01%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.retainedBytes | 512.000 | 512.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.scaffoldingNs | 216.351 | 222.688 | +6.337 ns (+2.93%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.transientBytes | 3000.000 | 3000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | compact.unreproducedNs | 216.351 | 222.688 | +6.337 ns (+2.93%) | 0 | within noise |
| - | - | cpython-3.13/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.bareBytes | 840.000 | 840.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.callNs | 210.731 | 121.927 | -88.804 ns (-42.14%) | 0 | smaller |
| - | - | cpython-3.13/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.constructNs | 7945.623 | 7994.156 | +48.533 ns (+0.61%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.dumpNs | 1187.958 | 1164.791 | -23.167 ns (-1.95%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.peakBytes | 1664.000 | 1664.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.readNs | 22.345 | 21.880 | -0.465 ns (-2.08%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.retainedBytes | 976.000 | 976.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | legacy.transientBytes | 688.000 | 688.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.bareBytes | 1352.000 | 1352.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.callNs | 167.508 | 197.073 | +29.564 ns (+17.65%) | 0 | larger |
| - | - | cpython-3.13/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.constructNs | 1754.929 | 1733.323 | -21.606 ns (-1.23%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.dumpNs | 1145.666 | 1122.083 | -23.583 ns (-2.06%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.13/wide | ordinary.peakBytes | 3360.000 | 3360.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.13/wide | ordinary.readNs | 22.819 | 22.457 | -0.362 ns (-1.59%) | 0 | within noise |
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
| - | - | cpython-3.14 | operation.attribute-read.armAgainstArm | 3.170 | 3.330 | +0.160 ratio (+5.05%) | 0 | larger |
| - | - | cpython-3.14 | operation.attribute-read.likeForLike | 3.170 | 3.330 | +0.160 ratio (+5.05%) | 0 | larger |
| - | - | cpython-3.14 | operation.attribute-read.vsOrdinary | 3.132 | 3.337 | +0.205 ratio (+6.56%) | 0 | larger |
| - | - | cpython-3.14 | operation.construction.armAgainstArm | 0.493 | 0.496 | +0.003 ratio (+0.57%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.likeForLike | 0.474 | 0.477 | +0.003 ratio (+0.58%) | 0 | within noise |
| - | - | cpython-3.14 | operation.construction.vsOrdinary | 1.478 | 1.504 | +0.025 ratio (+1.72%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.armAgainstArm | 2.148 | 2.110 | -0.038 ratio (-1.77%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.likeForLike | 2.148 | 2.110 | -0.038 ratio (-1.77%) | 0 | within noise |
| - | - | cpython-3.14 | operation.serialization.vsOrdinary | 2.156 | 2.132 | -0.023 ratio (-1.08%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.after | 3592.000 | 3592.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.before | 8208.000 | 8208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14 | vsOrdinary.retained.reduction | 0.562 | 0.562 | +0.000 ratio (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.bareBytes | 1096.000 | 1096.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.callNs | 1612.133 | 1618.333 | +6.200 ns (+0.38%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.constructNs | 6584.346 | 6679.833 | +95.488 ns (+1.45%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.directWireNs | 11369.937 | 11578.167 | +208.230 ns (+1.83%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.dumpNs | 6112.042 | 6245.375 | +133.333 ns (+2.18%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.peakBytes | 5034.000 | 5034.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionNs | 15238.083 | 15489.771 | +251.688 ns (+1.65%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionPeakBytes | 8450.000 | 8450.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionRetainedBytes | 1248.000 | 1248.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionReuseNs | 13305.879 | 13486.942 | +181.062 ns (+1.36%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.projectionTransientBytes | 7202.000 | 7202.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.readNs | 85.400 | 90.992 | +5.592 ns (+6.55%) | 0 | larger |
| - | - | cpython-3.14/nested | compact.retainedBytes | 1232.000 | 1232.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.scaffoldingNs | 299.568 | 279.522 | -20.046 ns (-6.69%) | 0 | smaller |
| - | - | cpython-3.14/nested | compact.transientBytes | 3802.000 | 3802.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | compact.unreproducedNs | 299.568 | 279.522 | -20.046 ns (-6.69%) | 0 | smaller |
| - | - | cpython-3.14/nested | fields | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.bareBytes | 2784.000 | 2784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.callNs | 286.002 | 23.081 | -262.921 ns (-91.93%) | 0 | smaller |
| - | - | cpython-3.14/nested | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.constructNs | 11036.498 | 10971.815 | -64.683 ns (-0.59%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.dumpNs | 2614.709 | 2678.042 | +63.333 ns (+2.42%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.peakBytes | 5184.000 | 5184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.readNs | 26.550 | 27.300 | +0.750 ns (+2.82%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.retainedBytes | 2920.000 | 2920.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | legacy.transientBytes | 2264.000 | 2264.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.bareBytes | 3208.000 | 3208.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.callNs | 237.058 | 167.004 | -70.054 ns (-29.55%) | 0 | smaller |
| - | - | cpython-3.14/nested | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.constructNs | 6220.192 | 6292.163 | +71.971 ns (+1.16%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.dumpNs | 2616.834 | 2662.625 | +45.792 ns (+1.75%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nested | ordinary.peakBytes | 4744.000 | 4744.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nested | ordinary.readNs | 26.600 | 26.596 | -0.004 ns (-0.02%) | 0 | within noise |
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
| - | - | cpython-3.14/nullable | compact.callNs | 1495.450 | 1405.802 | -89.648 ns (-5.99%) | 0 | smaller |
| - | - | cpython-3.14/nullable | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.constructNs | 2282.300 | 2294.656 | +12.356 ns (+0.54%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.directWireNs | 5842.479 | 5955.917 | +113.438 ns (+1.94%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.dumpNs | 1866.854 | 1854.187 | -12.667 ns (-0.68%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.peakBytes | 3672.000 | 3672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionNs | 8009.479 | 8266.166 | +256.687 ns (+3.20%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.projectionPeakBytes | 2736.000 | 2736.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionRetainedBytes | 480.000 | 480.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.projectionReuseNs | 6510.885 | 6769.844 | +258.958 ns (+3.98%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.projectionTransientBytes | 2256.000 | 2256.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.readNs | 78.090 | 81.923 | +3.833 ns (+4.91%) | 0 | larger |
| - | - | cpython-3.14/nullable | compact.retainedBytes | 496.000 | 496.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.scaffoldingNs | 207.017 | 207.943 | +0.927 ns (+0.45%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | compact.unreproducedNs | 207.017 | 207.943 | +0.927 ns (+0.45%) | 0 | within noise |
| - | - | cpython-3.14/nullable | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.callNs | 228.417 | 261.771 | +33.354 ns (+14.60%) | 0 | larger |
| - | - | cpython-3.14/nullable | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.constructNs | 5485.271 | 5475.187 | -10.083 ns (-0.18%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.dumpNs | 919.938 | 927.458 | +7.520 ns (+0.82%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.readNs | 23.906 | 23.733 | -0.173 ns (-0.72%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.callNs | 199.567 | 206.906 | +7.339 ns (+3.68%) | 0 | larger |
| - | - | cpython-3.14/nullable | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.constructNs | 1269.329 | 1225.594 | -43.735 ns (-3.45%) | 0 | smaller |
| - | - | cpython-3.14/nullable | ordinary.dumpNs | 902.437 | 922.479 | +20.042 ns (+2.22%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/nullable | ordinary.peakBytes | 2600.000 | 2600.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/nullable | ordinary.readNs | 25.490 | 26.615 | +1.125 ns (+4.41%) | 0 | larger |
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
| - | - | cpython-3.14/partial | compact.callNs | 1393.679 | 1416.419 | +22.740 ns (+1.63%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.cells | 12.000 | 12.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.constructNs | 2160.925 | 2205.498 | +44.573 ns (+2.06%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.directWireNs | 5146.896 | 5284.875 | +137.979 ns (+2.68%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.dumpNs | 1856.479 | 1897.375 | +40.896 ns (+2.20%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.peakBytes | 3576.000 | 3576.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionNs | 7238.375 | 7676.062 | +437.687 ns (+6.05%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.projectionPeakBytes | 2616.000 | 2616.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionRetainedBytes | 392.000 | 392.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.projectionReuseNs | 5729.500 | 5934.242 | +204.742 ns (+3.57%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.projectionTransientBytes | 2224.000 | 2224.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.readNs | 78.333 | 81.215 | +2.881 ns (+3.68%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.retainedBytes | 464.000 | 464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.scaffoldingNs | 225.827 | 234.961 | +9.134 ns (+4.04%) | 0 | larger |
| - | - | cpython-3.14/partial | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | compact.unreproducedNs | 225.827 | 234.961 | +9.134 ns (+4.04%) | 0 | larger |
| - | - | cpython-3.14/partial | fields | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.callNs | 203.819 | 142.048 | -61.771 ns (-30.31%) | 0 | smaller |
| - | - | cpython-3.14/partial | legacy.cells | 11.000 | 11.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.constructNs | 5016.285 | 5241.952 | +225.667 ns (+4.50%) | 0 | larger |
| - | - | cpython-3.14/partial | legacy.dumpNs | 906.021 | 960.770 | +54.750 ns (+6.04%) | 0 | larger |
| - | - | cpython-3.14/partial | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.peakBytes | 1832.000 | 1832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.readNs | 23.579 | 26.888 | +3.308 ns (+14.03%) | 0 | larger |
| - | - | cpython-3.14/partial | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | legacy.transientBytes | 832.000 | 832.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.callNs | 207.912 | 216.577 | +8.665 ns (+4.17%) | 0 | larger |
| - | - | cpython-3.14/partial | ordinary.cells | 10.000 | 10.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.constructNs | 956.233 | 962.444 | +6.210 ns (+0.65%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.dumpNs | 886.021 | 916.479 | +30.458 ns (+3.44%) | 0 | larger |
| - | - | cpython-3.14/partial | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/partial | ordinary.peakBytes | 1712.000 | 1712.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/partial | ordinary.readNs | 24.787 | 23.600 | -1.188 ns (-4.79%) | 0 | smaller |
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
| - | - | cpython-3.14/polymorphic | compact.callNs | 1412.710 | 1400.962 | -11.748 ns (-0.83%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.cells | 9.000 | 9.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.constructNs | 2200.894 | 2219.975 | +19.081 ns (+0.87%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.directWireNs | 5838.000 | 5872.771 | +34.771 ns (+0.60%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.dumpNs | 1663.354 | 1659.270 | -4.084 ns (-0.25%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.peakBytes | 3552.000 | 3552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionNs | 7873.729 | 7950.395 | +76.666 ns (+0.97%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionPeakBytes | 2984.000 | 2984.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionRetainedBytes | 480.000 | 480.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionReuseNs | 6209.098 | 6306.252 | +97.154 ns (+1.56%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.projectionTransientBytes | 2504.000 | 2504.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.readNs | 80.229 | 86.869 | +6.640 ns (+8.28%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | compact.retainedBytes | 440.000 | 440.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.scaffoldingNs | 229.962 | 224.560 | -5.402 ns (-2.35%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | compact.unreproducedNs | 229.962 | 224.560 | -5.402 ns (-2.35%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | fields | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.bareBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.callNs | 208.190 | 222.656 | +14.466 ns (+6.95%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | legacy.cells | 8.000 | 8.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.constructNs | 4026.873 | 4142.010 | +115.138 ns (+2.86%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.dumpNs | 800.416 | 820.979 | +20.563 ns (+2.57%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.peakBytes | 1432.000 | 1432.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.readNs | 26.458 | 25.818 | -0.640 ns (-2.42%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.retainedBytes | 808.000 | 808.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.bareBytes | 1184.000 | 1184.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.callNs | 189.569 | 273.131 | +83.563 ns (+44.08%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | ordinary.cells | 7.000 | 7.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.constructNs | 1095.723 | 1056.806 | -38.917 ns (-3.55%) | 0 | smaller |
| - | - | cpython-3.14/polymorphic | ordinary.dumpNs | 799.375 | 832.500 | +33.125 ns (+4.14%) | 0 | larger |
| - | - | cpython-3.14/polymorphic | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/polymorphic | ordinary.peakBytes | 2552.000 | 2552.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/polymorphic | ordinary.readNs | 25.988 | 27.378 | +1.390 ns (+5.35%) | 0 | larger |
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
| - | - | cpython-3.14/shallow | compact.callNs | 1412.962 | 1352.048 | -60.915 ns (-4.31%) | 0 | smaller |
| - | - | cpython-3.14/shallow | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.constructNs | 2106.996 | 2145.535 | +38.540 ns (+1.83%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.directWireNs | 7209.312 | 7203.020 | -6.292 ns (-0.09%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.dumpNs | 1423.708 | 1421.979 | -1.729 ns (-0.12%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.peakBytes | 3528.000 | 3528.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionNs | 9139.458 | 9155.167 | +15.709 ns (+0.17%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionPeakBytes | 3662.000 | 3662.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionRetainedBytes | 438.000 | 438.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionReuseNs | 5694.348 | 5839.987 | +145.640 ns (+2.56%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.projectionTransientBytes | 3224.000 | 3224.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.readNs | 87.552 | 94.490 | +6.937 ns (+7.92%) | 0 | larger |
| - | - | cpython-3.14/shallow | compact.retainedBytes | 416.000 | 416.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.scaffoldingNs | 211.997 | 234.559 | +22.561 ns (+10.64%) | 0 | larger |
| - | - | cpython-3.14/shallow | compact.transientBytes | 3112.000 | 3112.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | compact.unreproducedNs | 211.997 | 234.559 | +22.561 ns (+10.64%) | 0 | larger |
| - | - | cpython-3.14/shallow | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.callNs | 180.077 | 244.502 | +64.425 ns (+35.78%) | 0 | larger |
| - | - | cpython-3.14/shallow | legacy.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.constructNs | 2839.360 | 2838.352 | -1.008 ns (-0.04%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.dumpNs | 735.291 | 741.521 | +6.229 ns (+0.85%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.peakBytes | 1322.000 | 1322.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.readNs | 28.766 | 27.516 | -1.250 ns (-4.35%) | 0 | smaller |
| - | - | cpython-3.14/shallow | legacy.retainedBytes | 720.000 | 720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | legacy.transientBytes | 602.000 | 602.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.bareBytes | 584.000 | 584.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.callNs | 204.050 | 185.250 | -18.800 ns (-9.21%) | 0 | smaller |
| - | - | cpython-3.14/shallow | ordinary.cells | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.constructNs | 810.783 | 825.583 | +14.800 ns (+1.83%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.dumpNs | 744.417 | 743.563 | -0.854 ns (-0.11%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/shallow | ordinary.peakBytes | 1520.000 | 1520.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/shallow | ordinary.readNs | 28.047 | 26.901 | -1.146 ns (-4.09%) | 0 | smaller |
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
| - | - | cpython-3.14/warmed | compact.callNs | 1688.460 | 1662.490 | -25.971 ns (-1.54%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.constructNs | 4229.227 | 4272.510 | +43.283 ns (+1.02%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.dumpNs | 1742.666 | 1775.666 | +33.000 ns (+1.89%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.peakBytes | 3528.000 | 3528.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.readNs | 89.443 | 97.667 | +8.224 ns (+9.19%) | 0 | larger |
| - | - | cpython-3.14/warmed | compact.retainedBytes | 838.000 | 838.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.scaffoldingNs | 233.228 | 226.794 | -6.433 ns (-2.76%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.transientBytes | 2690.000 | 2690.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | compact.unreproducedNs | 233.228 | 226.794 | -6.433 ns (-2.76%) | 0 | within noise |
| - | - | cpython-3.14/warmed | fields | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.bareBytes | 910.000 | 910.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.callNs | 145.202 | 200.100 | +54.898 ns (+37.81%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.cells | 6.000 | 6.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.constructNs | 3949.131 | 4087.588 | +138.456 ns (+3.51%) | 0 | larger |
| - | - | cpython-3.14/warmed | legacy.dumpNs | 734.000 | 736.146 | +2.146 ns (+0.29%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.peakBytes | 1670.000 | 1670.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.readNs | 28.370 | 26.354 | -2.016 ns (-7.10%) | 0 | smaller |
| - | - | cpython-3.14/warmed | legacy.retainedBytes | 1046.000 | 1046.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | legacy.transientBytes | 624.000 | 624.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.bareBytes | 822.000 | 822.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.callNs | 211.746 | 215.577 | +3.831 ns (+1.81%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.cells | 5.000 | 5.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.constructNs | 1787.546 | 1856.152 | +68.606 ns (+3.84%) | 0 | larger |
| - | - | cpython-3.14/warmed | ordinary.dumpNs | 722.416 | 738.666 | +16.250 ns (+2.25%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/warmed | ordinary.peakBytes | 1872.000 | 1872.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/warmed | ordinary.readNs | 28.609 | 27.594 | -1.016 ns (-3.55%) | 0 | smaller |
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
| - | - | cpython-3.14/wide | compact.callNs | 1450.754 | 1420.681 | -30.073 ns (-2.07%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.cells | 18.000 | 18.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.constructNs | 2547.913 | 2560.944 | +13.031 ns (+0.51%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.directWireNs | 6998.604 | 7035.646 | +37.042 ns (+0.53%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.dumpNs | 2421.084 | 2318.146 | -102.938 ns (-4.25%) | 0 | smaller |
| - | - | cpython-3.14/wide | compact.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.peakBytes | 3720.000 | 3720.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionNs | 9612.125 | 9676.063 | +63.937 ns (+0.67%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionPeakBytes | 3488.000 | 3488.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionRetainedBytes | 672.000 | 672.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionReuseNs | 7785.492 | 7966.462 | +180.971 ns (+2.32%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.projectionTransientBytes | 2816.000 | 2816.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.readNs | 80.668 | 84.440 | +3.772 ns (+4.68%) | 0 | larger |
| - | - | cpython-3.14/wide | compact.retainedBytes | 544.000 | 544.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.scaffoldingNs | 227.277 | 223.902 | -3.376 ns (-1.49%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.transientBytes | 3176.000 | 3176.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | compact.unreproducedNs | 227.277 | 223.902 | -3.376 ns (-1.49%) | 0 | within noise |
| - | - | cpython-3.14/wide | fields | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.bareBytes | 864.000 | 864.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.callNs | 204.417 | 307.442 | +103.025 ns (+50.40%) | 0 | larger |
| - | - | cpython-3.14/wide | legacy.cells | 17.000 | 17.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.constructNs | 7885.833 | 7866.204 | -19.629 ns (-0.25%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.dumpNs | 1168.229 | 1169.750 | +1.521 ns (+0.13%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.lifecycleBytes | 136.000 | 136.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.peakBytes | 1784.000 | 1784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.readNs | 25.401 | 24.880 | -0.521 ns (-2.05%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.retainedBytes | 1000.000 | 1000.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.scaffoldingNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | legacy.transientBytes | 784.000 | 784.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | legacy.unreproducedNs | 0.000 | 0.000 | +0.000 ns | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.bareBytes | 1376.000 | 1376.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.callNs | 171.269 | 220.946 | +49.676 ns (+29.00%) | 0 | larger |
| - | - | cpython-3.14/wide | ordinary.cells | 16.000 | 16.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.constructNs | 1745.148 | 1679.138 | -66.010 ns (-3.78%) | 0 | smaller |
| - | - | cpython-3.14/wide | ordinary.dumpNs | 1168.230 | 1142.458 | -25.771 ns (-2.21%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.lifecycleBytes | 0.000 | 0.000 | +0.000 B | 0 | incomparable |
| - | - | cpython-3.14/wide | ordinary.peakBytes | 3464.000 | 3464.000 | +0.000 B (+0.00%) | 0 | within noise |
| - | - | cpython-3.14/wide | ordinary.readNs | 25.645 | 24.719 | -0.926 ns (-3.61%) | 0 | smaller |
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
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p50 | 3.299 | 3.295 | -0.004 us/event (-0.14%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | dispatchPerEvent.p95 | 3.698 | 3.804 | +0.106 us/event (+2.86%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.0us | 0.271 | 0.257 | -0.014 ratio (-5.10%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | latencyProjection.1000us | 0.021 | 0.021 | -0.000 ratio (-0.54%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.250us | 0.069 | 0.068 | -0.001 ratio (-1.45%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-0.22%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | latencyProjection.50us | 0.171 | 0.165 | -0.006 ratio (-3.32%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | observed.p50 | 433.208 | 451.292 | +18.084 us (+4.17%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | observed.p95 | 444.875 | 470.458 | +25.583 us (+5.75%) | 0 | slower |
| - | - | Safe logging alone, at INFO | pairedDelta.p50 | 92.375 | 92.250 | -0.125 us (-0.14%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedDelta.p95 | 103.542 | 106.500 | +2.958 us (+2.86%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | pairedOverhead.p50 | 0.271 | 0.257 | -0.014 ratio (-5.07%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | pairedOverhead.p95 | 0.304 | 0.298 | -0.006 ratio (-1.93%) | 0 | within noise |
| - | - | Safe logging alone, at INFO | plain.p50 | 340.833 | 358.667 | +17.834 us (+5.23%) | 0 | slower |
| - | - | Safe logging alone, at INFO | plain.p95 | 349.416 | 394.917 | +45.501 us (+13.02%) | 0 | slower |
| - | - | Safe logging alone, at INFO | rankedOverhead.p50 | 0.271 | 0.258 | -0.013 ratio (-4.72%) | 0 | smaller |
| - | - | Safe logging alone, at INFO | rankedOverhead.p95 | 0.273 | 0.191 | -0.082 ratio (-29.98%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p50 | 2.375 | 2.385 | +0.010 us/event (+0.44%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | dispatchPerEvent.p95 | 2.696 | 3.917 | +1.220 us/event (+45.25%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | latencyProjection.0us | 0.196 | 0.187 | -0.009 ratio (-4.54%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | latencyProjection.1000us | 0.015 | 0.015 | +0.000 ratio (+0.03%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.250us | 0.050 | 0.049 | -0.000 ratio (-0.87%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.5000us | 0.003 | 0.003 | +0.000 ratio (+0.35%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | latencyProjection.50us | 0.123 | 0.120 | -0.003 ratio (-2.75%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p50 | 406.375 | 424.292 | +17.917 us (+4.41%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | observed.p95 | 417.791 | 468.209 | +50.418 us (+12.07%) | 0 | slower |
| - | - | Safe logging alone, discarding every record | pairedDelta.p50 | 66.500 | 66.792 | +0.292 us (+0.44%) | 0 | within noise |
| - | - | Safe logging alone, discarding every record | pairedDelta.p95 | 75.500 | 109.666 | +34.166 us (+45.25%) | 0 | slower |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p50 | 0.196 | 0.187 | -0.009 ratio (-4.44%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | pairedOverhead.p95 | 0.221 | 0.307 | +0.086 ratio (+38.86%) | 0 | larger |
| - | - | Safe logging alone, discarding every record | plain.p50 | 339.833 | 357.541 | +17.708 us (+5.21%) | 0 | slower |
| - | - | Safe logging alone, discarding every record | plain.p95 | 348.750 | 372.792 | +24.042 us (+6.89%) | 0 | slower |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p50 | 0.196 | 0.187 | -0.009 ratio (-4.65%) | 0 | smaller |
| - | - | Safe logging alone, discarding every record | rankedOverhead.p95 | 0.198 | 0.256 | +0.058 ratio (+29.29%) | 0 | larger |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p50 | 3.988 | 3.987 | -0.002 us/event (-0.04%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | dispatchPerEvent.p95 | 4.429 | 4.929 | +0.500 us/event (+11.29%) | 0 | larger |
| - | - | fan-out of three, tracing every root | latencyProjection.0us | 0.327 | 0.310 | -0.017 ratio (-5.26%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | latencyProjection.1000us | 0.026 | 0.026 | -0.000 ratio (-0.47%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.250us | 0.083 | 0.082 | -0.001 ratio (-1.42%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-0.13%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | latencyProjection.50us | 0.206 | 0.199 | -0.007 ratio (-3.39%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | observed.p50 | 453.000 | 472.084 | +19.084 us (+4.21%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | observed.p95 | 466.417 | 500.083 | +33.666 us (+7.22%) | 0 | slower |
| - | - | fan-out of three, tracing every root | pairedDelta.p50 | 111.667 | 111.625 | -0.042 us (-0.04%) | 0 | within noise |
| - | - | fan-out of three, tracing every root | pairedDelta.p95 | 124.000 | 138.000 | +14.000 us (+11.29%) | 0 | slower |
| - | - | fan-out of three, tracing every root | pairedOverhead.p50 | 0.327 | 0.310 | -0.017 ratio (-5.17%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | pairedOverhead.p95 | 0.365 | 0.381 | +0.017 ratio (+4.54%) | 0 | larger |
| - | - | fan-out of three, tracing every root | plain.p50 | 341.166 | 359.959 | +18.793 us (+5.51%) | 0 | slower |
| - | - | fan-out of three, tracing every root | plain.p95 | 347.708 | 382.000 | +34.292 us (+9.86%) | 0 | slower |
| - | - | fan-out of three, tracing every root | rankedOverhead.p50 | 0.328 | 0.311 | -0.016 ratio (-4.97%) | 0 | smaller |
| - | - | fan-out of three, tracing every root | rankedOverhead.p95 | 0.341 | 0.309 | -0.032 ratio (-9.46%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p50 | 3.830 | 3.815 | -0.015 us/event (-0.39%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | dispatchPerEvent.p95 | 4.476 | 4.954 | +0.478 us/event (+10.67%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.0us | 0.314 | 0.297 | -0.017 ratio (-5.40%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.1000us | 0.025 | 0.025 | -0.000 ratio (-0.80%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.250us | 0.080 | 0.079 | -0.001 ratio (-1.71%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.5000us | 0.005 | 0.005 | -0.000 ratio (-0.48%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | latencyProjection.50us | 0.198 | 0.191 | -0.007 ratio (-3.61%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | observed.p50 | 448.459 | 466.583 | +18.124 us (+4.04%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | observed.p95 | 471.625 | 501.333 | +29.708 us (+6.30%) | 0 | slower |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p50 | 107.250 | 106.833 | -0.417 us (-0.39%) | 0 | within noise |
| - | - | fan-out of three, tracing one root in 10 | pairedDelta.p95 | 125.334 | 138.709 | +13.375 us (+10.67%) | 0 | slower |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p50 | 0.315 | 0.298 | -0.017 ratio (-5.39%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | pairedOverhead.p95 | 0.364 | 0.384 | +0.020 ratio (+5.52%) | 0 | larger |
| - | - | fan-out of three, tracing one root in 10 | plain.p50 | 341.583 | 359.667 | +18.084 us (+5.29%) | 0 | slower |
| - | - | fan-out of three, tracing one root in 10 | plain.p95 | 348.166 | 383.250 | +35.084 us (+10.08%) | 0 | slower |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p50 | 0.313 | 0.297 | -0.016 ratio (-4.99%) | 0 | smaller |
| - | - | fan-out of three, tracing one root in 10 | rankedOverhead.p95 | 0.355 | 0.308 | -0.046 ratio (-13.11%) | 0 | smaller |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p50 | 1.442 | 1.458 | +0.016 us/event (+1.13%) | 0 | within noise |
| - | - | one Handler that keeps nothing | dispatchPerEvent.p95 | 1.757 | 1.942 | +0.185 us/event (+10.50%) | 0 | larger |
| - | - | one Handler that keeps nothing | latencyProjection.0us | 0.119 | 0.114 | -0.005 ratio (-4.06%) | 0 | smaller |
| - | - | one Handler that keeps nothing | latencyProjection.1000us | 0.009 | 0.009 | +0.000 ratio (+0.71%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.250us | 0.030 | 0.030 | -0.000 ratio (-0.23%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.5000us | 0.002 | 0.002 | +0.000 ratio (+1.04%) | 0 | within noise |
| - | - | one Handler that keeps nothing | latencyProjection.50us | 0.075 | 0.073 | -0.002 ratio (-2.20%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p50 | 379.959 | 398.875 | +18.916 us (+4.98%) | 0 | within noise |
| - | - | one Handler that keeps nothing | observed.p95 | 389.875 | 415.833 | +25.958 us (+6.66%) | 0 | slower |
| - | - | one Handler that keeps nothing | pairedDelta.p50 | 40.375 | 40.833 | +0.458 us (+1.13%) | 0 | within noise |
| - | - | one Handler that keeps nothing | pairedDelta.p95 | 49.208 | 54.375 | +5.167 us (+10.50%) | 0 | slower |
| - | - | one Handler that keeps nothing | pairedOverhead.p50 | 0.119 | 0.114 | -0.005 ratio (-4.04%) | 0 | smaller |
| - | - | one Handler that keeps nothing | pairedOverhead.p95 | 0.145 | 0.152 | +0.007 ratio (+4.73%) | 0 | larger |
| - | - | one Handler that keeps nothing | plain.p50 | 339.375 | 357.750 | +18.375 us (+5.41%) | 0 | slower |
| - | - | one Handler that keeps nothing | plain.p95 | 347.291 | 395.834 | +48.543 us (+13.98%) | 0 | slower |
| - | - | one Handler that keeps nothing | rankedOverhead.p50 | 0.120 | 0.115 | -0.005 ratio (-3.87%) | 0 | smaller |
| - | - | one Handler that keeps nothing | rankedOverhead.p95 | 0.123 | 0.051 | -0.072 ratio (-58.80%) | 0 | smaller |
| - | - | workload | events | 28.000 | 28.000 | +0.000 count (+0.00%) | 0 | within noise |
| - | - | workload | statements | 4.000 | 4.000 | +0.000 count (+0.00%) | 0 | within noise |

## snapshot-delivery

| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 10138.708 | 9772.042 | -366.666 us (-3.62%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1450.010 | 1458.229 | +8.219 KiB (+0.57%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 693.328 | 693.328 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 108094.083 | 96231.000 | -11863.083 us (-10.97%) | 9 | faster |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 12653.846 | 12761.182 | +107.336 KiB (+0.85%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 6931.836 | 6931.836 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 16391.250 | 16006.083 | -385.167 us (-2.35%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 445.783 | 407.869 | -37.914 KiB (-8.51%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.458 | 3.458 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 112916.791 | 110287.500 | -2629.291 us (-2.33%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 822.721 | 831.072 | +8.352 KiB (+1.02%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.489 | 3.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8400.375 | 8172.875 | -227.500 us (-2.71%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1250.123 | 1257.873 | +7.750 KiB (+0.62%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 477.848 | 477.848 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 82689.917 | 81282.125 | -1407.792 us (-1.70%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11112.811 | 11219.584 | +106.773 KiB (+0.96%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4775.730 | 4775.730 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 14724.625 | 14601.833 | -122.792 us (-0.83%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 392.021 | 346.607 | -45.414 KiB (-11.58%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.524 | 2.524 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 97425.000 | 94919.125 | -2505.875 us (-2.57%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 821.428 | 829.779 | +8.352 KiB (+1.02%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.556 | 2.556 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 18118.292 | 17721.292 | -397.000 us (-2.19%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1352.424 | 1352.416 | -0.008 KiB (-0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 708.953 | 708.953 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 181561.375 | 176574.792 | -4986.583 us (-2.75%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12299.947 | 12956.229 | +656.281 KiB (+5.34%) | 3 | larger |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7088.086 | 7088.086 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 23970.166 | 23541.417 | -428.749 us (-1.79%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 568.674 | 516.408 | -52.266 KiB (-9.19%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.536 | 3.536 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 184055.375 | 181084.333 | -2971.042 us (-1.61%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 985.643 | 935.533 | -50.109 KiB (-5.08%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.567 | 3.567 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 16157.750 | 15614.250 | -543.500 us (-3.36%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1199.549 | 1265.205 | +65.656 KiB (+5.47%) | 3 | larger |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 501.285 | 501.285 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 157777.041 | 153783.958 | -3993.083 us (-2.53%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12300.377 | 12956.658 | +656.281 KiB (+5.34%) | 3 | larger |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5010.105 | 5010.105 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 21807.291 | 21430.959 | -376.332 us (-1.73%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 533.678 | 481.248 | -52.430 KiB (-9.82%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.642 | 2.642 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 166378.958 | 162065.333 | -4313.625 us (-2.59%) | 9 | within noise |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 982.014 | 931.740 | -50.273 KiB (-5.12%) | 3 | smaller |
| 3.13 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.673 | 2.673 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6079.666 | 6035.667 | -43.999 us (-0.72%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 476.559 | 471.098 | -5.461 KiB (-1.15%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 227.253 | 227.253 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 842.167 | 836.166 | -6.001 us (-0.71%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 72.854 | 70.972 | -1.883 KiB (-2.58%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 28.146 | 28.146 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4487.167 | 4410.500 | -76.667 us (-1.71%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 410.364 | 405.091 | -5.273 KiB (-1.29%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 186.823 | 186.823 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 668.125 | 668.958 | +0.833 us (+0.12%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 65.379 | 63.684 | -1.695 KiB (-2.59%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.200 | 23.200 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 8657.667 | 8451.917 | -205.750 us (-2.38%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 606.505 | 594.528 | -11.977 KiB (-1.97%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 293.815 | 293.815 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1229.625 | 1215.791 | -13.834 us (-1.13%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 92.004 | 88.605 | -3.398 KiB (-3.69%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 36.802 | 36.802 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6805.541 | 6664.084 | -141.457 us (-2.08%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 550.426 | 538.793 | -11.633 KiB (-2.11%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 257.698 | 257.698 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 1009.125 | 977.459 | -31.666 us (-3.14%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 86.378 | 83.323 | -3.055 KiB (-3.54%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.388 | 32.388 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10743.458 | 10535.208 | -208.250 us (-1.94%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 765.693 | 743.076 | -22.617 KiB (-2.95%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 384.511 | 384.511 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1517.166 | 1548.625 | +31.459 us (+2.07%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 113.556 | 108.657 | -4.898 KiB (-4.31%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 48.544 | 48.544 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8440.291 | 8280.833 | -159.458 us (-1.89%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 703.224 | 682.031 | -21.192 KiB (-3.01%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 333.909 | 333.909 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1257.042 | 1238.041 | -19.001 us (-1.51%) | 9 | within noise |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 106.775 | 102.377 | -4.398 KiB (-4.12%) | 3 | smaller |
| 3.13 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.247 | 42.247 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 433.007 | 436.927 | +3.920 KiB (+0.91%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 295.412 | 298.581 | +3.169 KiB (+1.07%) | 3 | within noise |
| 3.13 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.501 | 0.893 | +0.392 ms (+78.18%) | 9 | slower |
| 3.13 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.736 | 0.732 | -0.004 ms (-0.49%) | 9 | within noise |
| 3.13 | live-delivery | bitemporal-current | live.eager.maxMs | 5.085 | 4.812 | -0.273 ms (-5.38%) | 9 | faster |
| 3.13 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 39309.466 | 35952.632 | -3356.834 roots/s (-8.54%) | 9 | slower |
| 3.13 | live-delivery | bitemporal-current | live.page128.maxMs | 5.561 | 6.146 | +0.585 ms (+10.52%) | 9 | slower |
| 3.13 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 36340.511 | 29586.162 | -6754.348 roots/s (-18.59%) | 9 | slower |
| 3.13 | live-delivery | bitemporal-current | live.page32.maxMs | 7.376 | 8.764 | +1.388 ms (+18.81%) | 9 | slower |
| 3.13 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 24922.507 | 21610.718 | -3311.789 roots/s (-13.29%) | 9 | slower |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 232.833 | 232.728 | -0.105 KiB (-0.05%) | 6 | within noise |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 43.103 | 53.406 | +10.304 KiB (+23.91%) | 6 | larger |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 86.093 | 82.885 | -3.208 KiB (-3.73%) | 6 | smaller |
| 3.13 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 12.164 | 12.408 | +0.244 KiB (+2.01%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1289.925 | 1301.722 | +11.797 KiB (+0.91%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 521.973 | 521.973 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.673 | 1.226 | +0.553 ms (+82.13%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 1.086 | 2.166 | +1.080 ms (+99.41%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | live.eager.maxMs | 8.610 | 11.054 | +2.443 ms (+28.38%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 23401.622 | 18563.711 | -4837.912 roots/s (-20.67%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | live.page128.maxMs | 9.393 | 12.880 | +3.487 ms (+37.12%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 21562.663 | 15495.818 | -6066.845 roots/s (-28.14%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | live.page32.maxMs | 12.608 | 20.735 | +8.128 ms (+64.47%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 16483.969 | 9733.762 | -6750.208 roots/s (-40.95%) | 9 | slower |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 705.499 | 709.538 | +4.039 KiB (+0.57%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 31.946 | 31.876 | -0.070 KiB (-0.22%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 199.487 | 198.792 | -0.695 KiB (-0.35%) | 6 | within noise |
| 3.13 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.491 | 3.491 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | eagerMemory.peakKiB | 1717.554 | 1632.014 | -85.540 KiB (-4.98%) | 3 | smaller |
| 3.13 | live-delivery | document-heavy | eagerMemory.retainedKiB | 869.741 | 869.688 | -0.054 KiB (-0.01%) | 3 | within noise |
| 3.13 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.837 | 1.448 | +0.610 ms (+72.90%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.165 | 3.307 | +1.143 ms (+52.78%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.eager.maxMs | 23.432 | 24.942 | +1.510 ms (+6.44%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 8618.554 | 7953.683 | -664.871 roots/s (-7.71%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.page128.maxMs | 23.894 | 27.224 | +3.329 ms (+13.93%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8302.401 | 7421.414 | -880.987 roots/s (-10.61%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.page32.maxMs | 26.905 | 35.532 | +8.627 ms (+32.06%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 7409.225 | 5578.288 | -1830.937 roots/s (-24.71%) | 9 | slower |
| 3.13 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1143.466 | 1093.716 | -49.750 KiB (-4.35%) | 6 | smaller |
| 3.13 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 60.523 | 60.242 | -0.281 KiB (-0.46%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 307.846 | 302.795 | -5.051 KiB (-1.64%) | 6 | within noise |
| 3.13 | live-delivery | document-heavy | streamedMemory.retainedKiB | 6.146 | 6.259 | +0.113 KiB (+1.84%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1280.452 | 1346.202 | +65.750 KiB (+5.13%) | 3 | larger |
| 3.13 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 545.004 | 545.004 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.879 | 1.802 | +0.923 ms (+104.96%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.544 | 2.982 | +1.438 ms (+93.16%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.eager.maxMs | 16.227 | 19.590 | +3.363 ms (+20.73%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 11783.768 | 10473.032 | -1310.736 roots/s (-11.12%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page128.maxMs | 15.961 | 20.046 | +4.084 ms (+25.59%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 12528.973 | 10000.875 | -2528.098 roots/s (-20.18%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page32.maxMs | 19.033 | 28.162 | +9.129 ms (+47.96%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10524.862 | 7069.521 | -3455.340 roots/s (-32.83%) | 9 | slower |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1139.675 | 1140.448 | +0.773 KiB (+0.07%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 40.712 | 40.657 | -0.055 KiB (-0.13%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 313.190 | 304.167 | -9.023 KiB (-2.88%) | 6 | within noise |
| 3.13 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 3.812 | 3.812 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.peakKiB | 302.834 | 303.146 | +0.312 KiB (+0.10%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | eagerMemory.retainedKiB | 171.809 | 171.809 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.400 | 0.845 | +0.444 ms (+110.90%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.649 | 1.180 | +0.531 ms (+81.75%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.eager.maxMs | 5.244 | 5.805 | +0.561 ms (+10.70%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 37934.166 | 35458.371 | -2475.795 roots/s (-6.53%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.page128.maxMs | 5.654 | 7.576 | +1.923 ms (+34.01%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 34824.246 | 26872.387 | -7951.859 roots/s (-22.83%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.page32.maxMs | 7.850 | 12.167 | +4.316 ms (+54.98%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 25260.499 | 16494.561 | -8765.938 roots/s (-34.70%) | 9 | slower |
| 3.13 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 193.528 | 183.950 | -9.578 KiB (-4.95%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 35.106 | 27.911 | -7.195 KiB (-20.50%) | 6 | smaller |
| 3.13 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 69.660 | 69.903 | +0.243 KiB (+0.35%) | 6 | within noise |
| 3.13 | live-delivery | versioned-document | streamedMemory.retainedKiB | 1.926 | 1.878 | -0.048 KiB (-2.48%) | 6 | within noise |
| 3.13 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.345 | 4.758 | -1.587 us/projection (-25.01%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 163143.780 | 209150.326 | +46006.545 projections/s (+28.20%) | 9 | faster |
| 3.13 | positional-materialization | stress-columns | stress.peakFor64KiB | 43.348 | 40.973 | -2.375 KiB (-5.48%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.preparedSetKiB | 47.183 | 43.269 | -3.914 KiB (-8.30%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.retainedBPerProjection | 566.688 | 489.688 | -77.000 B/projection (-13.59%) | 3 | smaller |
| 3.13 | positional-materialization | stress-columns | stress.transientBPerProjection | 126.875 | 165.875 | +39.000 B/projection (+30.74%) | 3 | larger |
| 3.13 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.347 | 5.882 | -1.465 us/projection (-19.94%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 136618.440 | 168310.303 | +31691.863 projections/s (+23.20%) | 9 | faster |
| 3.13 | positional-materialization | stress-document | stress.peakFor64KiB | 47.434 | 44.074 | -3.359 KiB (-7.08%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.preparedSetKiB | 61.369 | 57.549 | -3.820 KiB (-6.23%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.retainedBPerProjection | 581.688 | 489.688 | -92.000 B/projection (-15.82%) | 3 | smaller |
| 3.13 | positional-materialization | stress-document | stress.transientBPerProjection | 177.250 | 215.500 | +38.250 B/projection (+21.58%) | 3 | larger |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 8.678 | 8.423 | -0.255 ms (-2.94%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 23049.109 | 23638.332 | +589.223 roots/s (+2.56%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 9.614 | 9.472 | -0.142 ms (-1.48%) | 9 | within noise |
| 3.13 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 20635.397 | 21202.163 | +566.766 roots/s (+2.75%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.535 | 16.077 | -0.458 ms (-2.77%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 12126.296 | 12408.808 | +282.513 roots/s (+2.33%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 16.678 | 16.301 | -0.378 ms (-2.27%) | 9 | within noise |
| 3.13 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 11932.343 | 12217.813 | +285.469 roots/s (+2.39%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 32.525 | 32.409 | -0.116 us/root (-0.36%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.peakKiB | 99.004 | 98.004 | -1.000 KiB (-1.01%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 50.852 | 50.852 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 32.776 | 31.681 | -1.095 us/root (-3.34%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.peakKiB | 103.316 | 101.879 | -1.438 KiB (-1.39%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-1 | document.retainedKiB | 50.852 | 50.852 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 47.617 | 46.023 | -1.594 us/root (-3.35%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.peakKiB | 147.043 | 145.523 | -1.520 KiB (-1.03%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 87.977 | 87.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 47.147 | 46.134 | -1.013 us/root (-2.15%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.peakKiB | 150.992 | 149.555 | -1.438 KiB (-0.95%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-4 | document.retainedKiB | 87.977 | 87.977 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 65.646 | 64.022 | -1.624 us/root (-2.47%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.peakKiB | 218.461 | 215.844 | -2.617 KiB (-1.20%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.477 | 137.477 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 67.285 | 66.169 | -1.116 us/root (-1.66%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.peakKiB | 221.883 | 218.680 | -3.203 KiB (-1.44%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.477 | 137.477 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 24.202 | 22.737 | -1.465 us/root (-6.05%) | 9 | faster |
| 3.13 | provider-free-delivery | read-many-0 | columns.peakKiB | 62.293 | 61.480 | -0.812 KiB (-1.30%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.102 | 24.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 24.853 | 23.712 | -1.141 us/root (-4.59%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.peakKiB | 68.605 | 67.355 | -1.250 KiB (-1.82%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.102 | 24.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 152.355 | 148.395 | -3.961 us/root (-2.60%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.peakKiB | 625.758 | 622.762 | -2.996 KiB (-0.48%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.102 | 428.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 151.146 | 147.612 | -3.534 us/root (-2.34%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.peakKiB | 629.699 | 626.293 | -3.406 KiB (-0.54%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.102 | 428.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 56.049 | 56.095 | +0.046 us/root (+0.08%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.peakKiB | 195.082 | 192.648 | -2.434 KiB (-1.25%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.102 | 125.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 56.990 | 54.724 | -2.266 us/root (-3.98%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.peakKiB | 198.129 | 194.863 | -3.266 KiB (-1.65%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.102 | 125.102 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 47.100 | 44.643 | -2.457 us/root (-5.22%) | 9 | faster |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 128.688 | 127.688 | -1.000 KiB (-0.78%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 35.945 | 35.945 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 47.395 | 45.499 | -1.896 us/root (-4.00%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.peakKiB | 133.001 | 131.563 | -1.438 KiB (-1.08%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 35.945 | 35.945 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 55.443 | 54.224 | -1.219 us/root (-2.20%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.peakKiB | 219.008 | 215.922 | -3.086 KiB (-1.41%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.727 | 136.727 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 54.898 | 53.339 | -1.560 us/root (-2.84%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.peakKiB | 222.836 | 219.312 | -3.523 KiB (-1.58%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.727 | 136.727 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 144.585 | 141.611 | -2.974 us/root (-2.06%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.peakKiB | 761.578 | 758.492 | -3.086 KiB (-0.41%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.227 | 480.227 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 143.919 | 143.264 | -0.655 us/root (-0.46%) | 9 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.peakKiB | 765.406 | 761.883 | -3.523 KiB (-0.46%) | 3 | within noise |
| 3.13 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.227 | 480.227 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 249.625 | 260.709 | +11.084 us (+4.44%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 37.383 | 32.547 | -4.836 KiB (-12.94%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 28.672 | 25.070 | -3.602 KiB (-12.56%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 374.958 | 371.000 | -3.958 us (-1.06%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 50.452 | 44.538 | -5.914 KiB (-11.72%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 40.022 | 35.562 | -4.461 KiB (-11.15%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 486.208 | 491.917 | +5.709 us (+1.17%) | 9 | within noise |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 62.865 | 55.873 | -6.992 KiB (-11.12%) | 3 | smaller |
| 3.13 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 50.850 | 45.529 | -5.320 KiB (-10.46%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 90.541 | 88.875 | -1.666 us (-1.84%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 20.526 | 19.706 | -0.820 KiB (-4.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 13.761 | 13.073 | -0.688 KiB (-5.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 91.917 | 92.833 | +0.916 us (+1.00%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-1 | document.peakKiB | 20.428 | 19.611 | -0.816 KiB (-4.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 13.912 | 13.229 | -0.684 KiB (-4.91%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 90.875 | 87.458 | -3.417 us (-3.76%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 20.526 | 19.706 | -0.820 KiB (-4.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 13.761 | 13.073 | -0.688 KiB (-5.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 91.875 | 92.708 | +0.833 us (+0.91%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-depth-8 | document.peakKiB | 20.432 | 19.611 | -0.820 KiB (-4.01%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 13.916 | 13.229 | -0.688 KiB (-4.94%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 91.166 | 88.042 | -3.124 us (-3.43%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | columns.peakKiB | 20.527 | 19.707 | -0.820 KiB (-4.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 13.762 | 13.074 | -0.688 KiB (-5.00%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.elapsedUs | 91.916 | 89.375 | -2.541 us (-2.76%) | 9 | within noise |
| 3.13 | read-plan-compilation | plan-width-64 | document.peakKiB | 20.433 | 19.612 | -0.820 KiB (-4.01%) | 3 | smaller |
| 3.13 | read-plan-compilation | plan-width-64 | document.retainedKiB | 13.917 | 13.229 | -0.688 KiB (-4.94%) | 3 | smaller |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 11.583 | 11.625 | +0.042 us (+0.36%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 16.042 | 15.584 | -0.458 us (-2.86%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 20.125 | 19.875 | -0.250 us (-1.24%) | 9 | within noise |
| 3.13 | read-plan-reuse | control-guarded-3 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.closed.retainedKiB | 71.484 | 71.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | large.shared.retainedKiB | 50.789 | 50.789 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | small.closed.retainedKiB | 118.438 | 118.438 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.13 | result-held-metadata | control-held | small.shared.retainedKiB | 111.070 | 111.070 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.elapsedUs | 10004.125 | 10038.375 | +34.250 us (+0.34%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.peakKiB | 1353.777 | 1426.754 | +72.977 KiB (+5.39%) | 3 | larger |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots200.retainedKiB | 741.773 | 741.773 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.elapsedUs | 101223.208 | 101349.208 | +126.000 us (+0.12%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.peakKiB | 13108.117 | 13230.781 | +122.664 KiB (+0.94%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.eager.roots2000.retainedKiB | 7416.219 | 7416.219 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.elapsedUs | 17346.250 | 17583.708 | +237.458 us (+1.37%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.peakKiB | 176.418 | 185.645 | +9.227 KiB (+5.23%) | 3 | larger |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots200.retainedKiB | 3.700 | 3.700 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.elapsedUs | 113887.958 | 114362.625 | +474.667 us (+0.42%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.peakKiB | 181.324 | 190.551 | +9.227 KiB (+5.09%) | 3 | larger |
| 3.14 | control-delivery | control-delivery-conventional-fanout | typed.page32.roots2000.retainedKiB | 3.731 | 3.731 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.elapsedUs | 8462.625 | 8335.084 | -127.541 us (-1.51%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.peakKiB | 1183.411 | 1256.114 | +72.703 KiB (+6.14%) | 3 | larger |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots200.retainedKiB | 487.230 | 487.230 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.elapsedUs | 84571.125 | 83609.833 | -961.292 us (-1.14%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.peakKiB | 11348.603 | 11470.993 | +122.391 KiB (+1.08%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.eager.roots2000.retainedKiB | 4869.488 | 4869.488 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.elapsedUs | 15562.208 | 17507.792 | +1945.584 us (+12.50%) | 9 | slower |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.peakKiB | 178.630 | 187.856 | +9.227 KiB (+5.17%) | 3 | larger |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots200.retainedKiB | 2.571 | 2.571 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.elapsedUs | 99169.875 | 98713.167 | -456.708 us (-0.46%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.peakKiB | 180.536 | 189.763 | +9.227 KiB (+5.11%) | 3 | larger |
| 3.14 | control-delivery | control-delivery-conventional-fanout | wire.page32.roots2000.retainedKiB | 2.603 | 2.603 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.elapsedUs | 18556.083 | 18504.125 | -51.958 us (-0.28%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.peakKiB | 1297.602 | 1359.469 | +61.867 KiB (+4.77%) | 3 | larger |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots200.retainedKiB | 758.961 | 758.961 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.elapsedUs | 207415.542 | 186914.542 | -20501.000 us (-9.88%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.peakKiB | 12963.753 | 13713.808 | +750.055 KiB (+5.79%) | 3 | larger |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.eager.roots2000.retainedKiB | 7588.094 | 7588.094 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.elapsedUs | 24813.625 | 24974.000 | +160.375 us (+0.65%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.peakKiB | 283.668 | 285.020 | +1.352 KiB (+0.48%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots200.retainedKiB | 3.786 | 3.786 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.elapsedUs | 190624.875 | 189200.791 | -1424.084 us (-0.75%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.peakKiB | 287.590 | 288.941 | +1.352 KiB (+0.47%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | typed.page32.roots2000.retainedKiB | 3.817 | 3.817 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.elapsedUs | 16610.000 | 16172.416 | -437.584 us (-2.63%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.peakKiB | 1265.931 | 1340.985 | +75.055 KiB (+5.93%) | 3 | larger |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots200.retainedKiB | 510.668 | 510.668 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.elapsedUs | 162377.625 | 159251.791 | -3125.834 us (-1.93%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.peakKiB | 12964.446 | 13714.501 | +750.055 KiB (+5.79%) | 3 | larger |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.eager.roots2000.retainedKiB | 5103.863 | 5103.863 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.elapsedUs | 23036.500 | 22943.291 | -93.209 us (-0.40%) | 9 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.peakKiB | 282.653 | 284.005 | +1.352 KiB (+0.48%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots200.retainedKiB | 2.688 | 2.688 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.elapsedUs | 182174.500 | 169425.917 | -12748.583 us (-7.00%) | 9 | faster |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.peakKiB | 284.216 | 285.567 | +1.352 KiB (+0.48%) | 3 | within noise |
| 3.14 | control-delivery | control-delivery-duplicate-include | wire.page32.roots2000.retainedKiB | 2.720 | 2.720 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.elapsedUs | 6005.834 | 6054.875 | +49.041 us (+0.82%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.peakKiB | 402.667 | 419.644 | +16.977 KiB (+4.22%) | 3 | larger |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots256.retainedKiB | 245.097 | 245.097 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.elapsedUs | 872.750 | 868.958 | -3.792 us (-0.43%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.peakKiB | 70.104 | 71.268 | +1.164 KiB (+1.66%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | typed.eager.roots32.retainedKiB | 34.177 | 34.177 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.elapsedUs | 4434.542 | 4400.750 | -33.792 us (-0.76%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.peakKiB | 360.000 | 377.164 | +17.164 KiB (+4.77%) | 3 | larger |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots256.retainedKiB | 190.003 | 190.003 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.elapsedUs | 686.625 | 687.208 | +0.583 us (+0.08%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.peakKiB | 61.960 | 63.312 | +1.352 KiB (+2.18%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-1 | wire.eager.roots32.retainedKiB | 23.606 | 23.606 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.elapsedUs | 9140.709 | 8834.292 | -306.417 us (-3.35%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.peakKiB | 531.295 | 541.584 | +10.289 KiB (+1.94%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots256.retainedKiB | 317.237 | 317.237 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.elapsedUs | 1257.083 | 1250.042 | -7.041 us (-0.56%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.peakKiB | 86.798 | 87.712 | +0.914 KiB (+1.05%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | typed.eager.roots32.retainedKiB | 42.489 | 42.489 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.elapsedUs | 6693.625 | 6707.209 | +13.584 us (+0.20%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.peakKiB | 496.995 | 508.909 | +11.914 KiB (+2.40%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots256.retainedKiB | 261.722 | 261.722 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.elapsedUs | 1022.334 | 1017.417 | -4.917 us (-0.48%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.peakKiB | 81.553 | 82.717 | +1.164 KiB (+1.43%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-2 | wire.eager.roots32.retainedKiB | 32.903 | 32.903 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.elapsedUs | 10976.500 | 10990.208 | +13.708 us (+0.12%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.peakKiB | 686.104 | 700.338 | +14.234 KiB (+2.07%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots256.retainedKiB | 415.769 | 415.769 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.elapsedUs | 1571.542 | 1558.458 | -13.084 us (-0.83%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.peakKiB | 106.569 | 107.241 | +0.672 KiB (+0.63%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | typed.eager.roots32.retainedKiB | 54.958 | 54.958 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.elapsedUs | 8555.167 | 8550.667 | -4.500 us (-0.05%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.peakKiB | 638.780 | 657.265 | +18.484 KiB (+2.89%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots256.retainedKiB | 339.104 | 339.104 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.elapsedUs | 1277.084 | 1286.375 | +9.291 us (+0.73%) | 9 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.peakKiB | 100.372 | 101.388 | +1.016 KiB (+1.01%) | 3 | within noise |
| 3.14 | control-delivery | control-guarded-3 | wire.eager.roots32.retainedKiB | 42.911 | 42.911 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.peakKiB | 395.411 | 399.661 | +4.250 KiB (+1.07%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | eagerMemory.retainedKiB | 298.570 | 300.279 | +1.709 KiB (+0.57%) | 3 | within noise |
| 3.14 | live-delivery | bitemporal-current | firstResult.page1.maxMs | 0.530 | 0.501 | -0.029 ms (-5.46%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | firstResult.page32.maxMs | 0.765 | 0.792 | +0.027 ms (+3.55%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.eager.maxMs | 5.138 | 5.085 | -0.053 ms (-1.04%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.eager.minRootsPerSecond | 37022.756 | 40010.331 | +2987.575 roots/s (+8.07%) | 9 | faster |
| 3.14 | live-delivery | bitemporal-current | live.page128.maxMs | 5.619 | 5.653 | +0.034 ms (+0.61%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page128.minRootsPerSecond | 36076.663 | 35912.826 | -163.837 roots/s (-0.45%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page32.maxMs | 8.085 | 8.115 | +0.030 ms (+0.37%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | live.page32.minRootsPerSecond | 25413.500 | 25032.072 | -381.428 roots/s (-1.50%) | 9 | within noise |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page128PeakKiB | 214.200 | 229.209 | +15.009 KiB (+7.01%) | 6 | larger |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page1PeakKiB | 43.921 | 42.509 | -1.412 KiB (-3.22%) | 6 | smaller |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.page32PeakKiB | 76.287 | 79.099 | +2.812 KiB (+3.69%) | 6 | larger |
| 3.14 | live-delivery | bitemporal-current | streamedMemory.retainedKiB | 12.428 | 14.100 | +1.672 KiB (+13.45%) | 6 | larger |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.peakKiB | 1224.021 | 1300.178 | +76.156 KiB (+6.22%) | 3 | larger |
| 3.14 | live-delivery | conventional-fanout | eagerMemory.retainedKiB | 531.383 | 531.383 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | conventional-fanout | firstResult.page1.maxMs | 0.667 | 1.258 | +0.591 ms (+88.67%) | 9 | slower |
| 3.14 | live-delivery | conventional-fanout | firstResult.page32.maxMs | 0.994 | 2.204 | +1.209 ms (+121.62%) | 9 | slower |
| 3.14 | live-delivery | conventional-fanout | live.eager.maxMs | 8.815 | 10.854 | +2.039 ms (+23.13%) | 9 | slower |
| 3.14 | live-delivery | conventional-fanout | live.eager.minRootsPerSecond | 22775.152 | 18282.721 | -4492.432 roots/s (-19.73%) | 9 | slower |
| 3.14 | live-delivery | conventional-fanout | live.page128.maxMs | 9.254 | 13.084 | +3.830 ms (+41.38%) | 9 | slower |
| 3.14 | live-delivery | conventional-fanout | live.page128.minRootsPerSecond | 21608.773 | 15533.377 | -6075.396 roots/s (-28.12%) | 9 | slower |
| 3.14 | live-delivery | conventional-fanout | live.page32.maxMs | 11.920 | 21.295 | +9.376 ms (+78.66%) | 9 | slower |
| 3.14 | live-delivery | conventional-fanout | live.page32.minRootsPerSecond | 17235.311 | 10337.409 | -6897.902 roots/s (-40.02%) | 9 | slower |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page128PeakKiB | 667.924 | 713.650 | +45.727 KiB (+6.85%) | 6 | larger |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page1PeakKiB | 34.473 | 34.637 | +0.164 KiB (+0.48%) | 6 | within noise |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.page32PeakKiB | 191.596 | 201.010 | +9.414 KiB (+4.91%) | 6 | larger |
| 3.14 | live-delivery | conventional-fanout | streamedMemory.retainedKiB | 3.597 | 3.597 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | eagerMemory.peakKiB | 1770.685 | 1683.489 | -87.195 KiB (-4.92%) | 3 | smaller |
| 3.14 | live-delivery | document-heavy | eagerMemory.retainedKiB | 883.711 | 883.713 | +0.002 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | document-heavy | firstResult.page1.maxMs | 0.799 | 1.699 | +0.900 ms (+112.63%) | 9 | slower |
| 3.14 | live-delivery | document-heavy | firstResult.page32.maxMs | 2.199 | 3.303 | +1.104 ms (+50.19%) | 9 | slower |
| 3.14 | live-delivery | document-heavy | live.eager.maxMs | 23.432 | 25.480 | +2.048 ms (+8.74%) | 9 | slower |
| 3.14 | live-delivery | document-heavy | live.eager.minRootsPerSecond | 8510.126 | 7703.455 | -806.670 roots/s (-9.48%) | 9 | slower |
| 3.14 | live-delivery | document-heavy | live.page128.maxMs | 24.274 | 27.272 | +2.998 ms (+12.35%) | 9 | slower |
| 3.14 | live-delivery | document-heavy | live.page128.minRootsPerSecond | 8211.445 | 7314.609 | -896.836 roots/s (-10.92%) | 9 | slower |
| 3.14 | live-delivery | document-heavy | live.page32.maxMs | 27.605 | 35.088 | +7.482 ms (+27.10%) | 9 | slower |
| 3.14 | live-delivery | document-heavy | live.page32.minRootsPerSecond | 7359.852 | 5659.583 | -1700.269 roots/s (-23.10%) | 9 | slower |
| 3.14 | live-delivery | document-heavy | streamedMemory.page128PeakKiB | 1177.861 | 1127.760 | -50.102 KiB (-4.25%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.page1PeakKiB | 59.062 | 54.548 | -4.514 KiB (-7.64%) | 6 | smaller |
| 3.14 | live-delivery | document-heavy | streamedMemory.page32PeakKiB | 317.229 | 311.277 | -5.951 KiB (-1.88%) | 6 | within noise |
| 3.14 | live-delivery | document-heavy | streamedMemory.retainedKiB | 6.274 | 6.226 | -0.049 KiB (-0.78%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | eagerMemory.peakKiB | 1347.291 | 1422.533 | +75.242 KiB (+5.58%) | 3 | larger |
| 3.14 | live-delivery | duplicate-include | eagerMemory.retainedKiB | 554.414 | 554.414 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | duplicate-include | firstResult.page1.maxMs | 0.727 | 1.786 | +1.059 ms (+145.61%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | firstResult.page32.maxMs | 1.515 | 2.750 | +1.234 ms (+81.46%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.eager.maxMs | 17.473 | 19.900 | +2.427 ms (+13.89%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.eager.minRootsPerSecond | 11458.555 | 10658.519 | -800.036 roots/s (-6.98%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.page128.maxMs | 16.913 | 20.787 | +3.875 ms (+22.91%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.page128.minRootsPerSecond | 11767.042 | 9681.479 | -2085.563 roots/s (-17.72%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.page32.maxMs | 19.365 | 25.601 | +6.237 ms (+32.21%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | live.page32.minRootsPerSecond | 10242.666 | 6433.083 | -3809.583 roots/s (-37.19%) | 9 | slower |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page128PeakKiB | 1145.486 | 1154.088 | +8.602 KiB (+0.75%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page1PeakKiB | 43.727 | 43.953 | +0.227 KiB (+0.52%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.page32PeakKiB | 307.869 | 309.721 | +1.852 KiB (+0.60%) | 6 | within noise |
| 3.14 | live-delivery | duplicate-include | streamedMemory.retainedKiB | 3.948 | 3.948 | +0.000 KiB (+0.00%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | eagerMemory.peakKiB | 278.097 | 265.734 | -12.362 KiB (-4.45%) | 3 | smaller |
| 3.14 | live-delivery | versioned-document | eagerMemory.retainedKiB | 175.000 | 175.000 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | live-delivery | versioned-document | firstResult.page1.maxMs | 0.526 | 0.804 | +0.278 ms (+52.92%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | firstResult.page32.maxMs | 0.776 | 1.164 | +0.388 ms (+50.02%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.eager.maxMs | 5.423 | 5.929 | +0.505 ms (+9.32%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.eager.minRootsPerSecond | 34188.034 | 33668.855 | -519.179 roots/s (-1.52%) | 9 | within noise |
| 3.14 | live-delivery | versioned-document | live.page128.maxMs | 6.576 | 7.570 | +0.995 ms (+15.13%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.page128.minRootsPerSecond | 31431.917 | 25535.583 | -5896.334 roots/s (-18.76%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.page32.maxMs | 9.395 | 12.637 | +3.242 ms (+34.51%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | live.page32.minRootsPerSecond | 21728.306 | 15613.920 | -6114.386 roots/s (-28.14%) | 9 | slower |
| 3.14 | live-delivery | versioned-document | streamedMemory.page128PeakKiB | 200.928 | 190.998 | -9.930 KiB (-4.94%) | 6 | smaller |
| 3.14 | live-delivery | versioned-document | streamedMemory.page1PeakKiB | 31.434 | 30.581 | -0.853 KiB (-2.71%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.page32PeakKiB | 67.442 | 66.568 | -0.874 KiB (-1.30%) | 6 | within noise |
| 3.14 | live-delivery | versioned-document | streamedMemory.retainedKiB | 1.998 | 1.944 | -0.054 KiB (-2.69%) | 6 | within noise |
| 3.14 | positional-materialization | stress-columns | stress.maxUsPerProjection | 6.167 | 4.858 | -1.309 us/projection (-21.23%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.minProjectionsPerSecond | 163543.580 | 207455.416 | +43911.835 projections/s (+26.85%) | 9 | faster |
| 3.14 | positional-materialization | stress-columns | stress.peakFor64KiB | 45.496 | 43.371 | -2.125 KiB (-4.67%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.preparedSetKiB | 51.560 | 47.646 | -3.914 KiB (-7.59%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.retainedBPerProjection | 599.672 | 519.672 | -80.000 B/projection (-13.34%) | 3 | smaller |
| 3.14 | positional-materialization | stress-columns | stress.transientBPerProjection | 128.266 | 174.266 | +46.000 B/projection (+35.86%) | 3 | larger |
| 3.14 | positional-materialization | stress-document | stress.maxUsPerProjection | 7.609 | 6.230 | -1.379 us/projection (-18.12%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.minProjectionsPerSecond | 132129.034 | 160384.128 | +28255.094 projections/s (+21.38%) | 9 | faster |
| 3.14 | positional-materialization | stress-document | stress.peakFor64KiB | 49.652 | 46.512 | -3.141 KiB (-6.33%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.preparedSetKiB | 66.832 | 63.027 | -3.805 KiB (-5.69%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.retainedBPerProjection | 615.672 | 519.672 | -96.000 B/projection (-15.59%) | 3 | smaller |
| 3.14 | positional-materialization | stress-document | stress.transientBPerProjection | 178.766 | 224.516 | +45.750 B/projection (+25.59%) | 3 | larger |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.maxMs | 9.370 | 8.636 | -0.734 ms (-7.83%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.eager.minRootsPerSecond | 21259.443 | 23033.957 | +1774.513 roots/s (+8.35%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.maxMs | 10.511 | 9.700 | -0.811 ms (-7.72%) | 9 | faster |
| 3.14 | provider-free-delivery | conventional-fanout | providerFreeCpu.page32.minRootsPerSecond | 18977.883 | 20615.987 | +1638.104 roots/s (+8.63%) | 9 | faster |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.maxMs | 16.850 | 16.610 | -0.240 ms (-1.42%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.eager.minRootsPerSecond | 11857.385 | 12053.003 | +195.618 roots/s (+1.65%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.maxMs | 17.084 | 16.970 | -0.114 ms (-0.67%) | 9 | within noise |
| 3.14 | provider-free-delivery | duplicate-include | providerFreeCpu.page32.minRootsPerSecond | 11708.516 | 11915.223 | +206.707 roots/s (+1.77%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.elapsedUsPerRoot | 110.372 | 109.316 | -1.056 us/root (-0.96%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.peakKiB | 447.188 | 443.915 | -3.273 KiB (-0.73%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | columns.retainedKiB | 162.484 | 162.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.elapsedUsPerRoot | 111.878 | 109.526 | -2.352 us/root (-2.10%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.peakKiB | 451.212 | 447.438 | -3.773 KiB (-0.84%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-boolean | document.retainedKiB | 162.484 | 162.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.elapsedUsPerRoot | 398.772 | 396.335 | -2.438 us/root (-0.61%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.peakKiB | 954.355 | 952.168 | -2.188 KiB (-0.23%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | columns.retainedKiB | 313.047 | 313.047 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.elapsedUsPerRoot | 433.339 | 398.477 | -34.862 us/root (-8.04%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-bytes | document.peakKiB | 958.113 | 955.738 | -2.375 KiB (-0.25%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-bytes | document.retainedKiB | 313.047 | 313.047 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.elapsedUsPerRoot | 428.729 | 421.161 | -7.568 us/root (-1.77%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.peakKiB | 773.853 | 770.540 | -3.312 KiB (-0.43%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | columns.retainedKiB | 192.965 | 192.965 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.elapsedUsPerRoot | 425.526 | 466.042 | +40.516 us/root (+9.52%) | 9 | slower |
| 3.14 | provider-free-delivery | leaf-date | document.peakKiB | 777.649 | 774.337 | -3.312 KiB (-0.43%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-date | document.retainedKiB | 192.965 | 192.965 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.elapsedUsPerRoot | 1055.738 | 919.889 | -135.849 us/root (-12.87%) | 9 | faster |
| 3.14 | provider-free-delivery | leaf-decimal | columns.peakKiB | 1300.483 | 1298.812 | -1.672 KiB (-0.13%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | columns.retainedKiB | 271.797 | 271.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.elapsedUsPerRoot | 936.435 | 921.395 | -15.040 us/root (-1.61%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.peakKiB | 1304.312 | 1302.640 | -1.672 KiB (-0.13%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-decimal | document.retainedKiB | 271.797 | 271.797 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.elapsedUsPerRoot | 808.819 | 856.643 | +47.824 us/root (+5.91%) | 9 | slower |
| 3.14 | provider-free-delivery | leaf-float32 | columns.peakKiB | 691.443 | 689.256 | -2.188 KiB (-0.32%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | columns.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.elapsedUsPerRoot | 812.609 | 798.594 | -14.016 us/root (-1.72%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.peakKiB | 695.201 | 692.826 | -2.375 KiB (-0.34%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float32 | document.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.elapsedUsPerRoot | 317.669 | 315.036 | -2.633 us/root (-0.83%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.peakKiB | 657.537 | 655.350 | -2.188 KiB (-0.33%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | columns.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.elapsedUsPerRoot | 319.878 | 316.471 | -3.406 us/root (-1.06%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.peakKiB | 661.295 | 658.920 | -2.375 KiB (-0.36%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-float64 | document.retainedKiB | 211.984 | 211.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.elapsedUsPerRoot | 156.155 | 153.753 | -2.402 us/root (-1.54%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.peakKiB | 639.337 | 636.063 | -3.273 KiB (-0.51%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | columns.retainedKiB | 354.480 | 354.480 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.elapsedUsPerRoot | 156.876 | 154.862 | -2.014 us/root (-1.28%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.peakKiB | 643.360 | 639.587 | -3.773 KiB (-0.59%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int32 | document.retainedKiB | 354.480 | 354.480 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.elapsedUsPerRoot | 165.079 | 159.978 | -5.102 us/root (-3.09%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.peakKiB | 651.306 | 648.032 | -3.273 KiB (-0.50%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | columns.retainedKiB | 366.484 | 366.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.elapsedUsPerRoot | 164.833 | 161.039 | -3.794 us/root (-2.30%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.peakKiB | 655.329 | 651.556 | -3.773 KiB (-0.58%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-int64 | document.retainedKiB | 366.484 | 366.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.elapsedUsPerRoot | 566.598 | 560.288 | -6.310 us/root (-1.11%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.peakKiB | 829.834 | 827.646 | -2.188 KiB (-0.26%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | columns.retainedKiB | 277.984 | 277.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.elapsedUsPerRoot | 566.158 | 560.087 | -6.070 us/root (-1.07%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.peakKiB | 833.592 | 831.217 | -2.375 KiB (-0.28%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-time | document.retainedKiB | 277.984 | 277.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.elapsedUsPerRoot | 841.789 | 831.596 | -10.193 us/root (-1.21%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.peakKiB | 956.719 | 954.629 | -2.090 KiB (-0.22%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | columns.retainedKiB | 302.979 | 302.881 | -0.098 KiB (-0.03%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.elapsedUsPerRoot | 847.491 | 837.633 | -9.858 us/root (-1.16%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.peakKiB | 960.525 | 957.174 | -3.352 KiB (-0.35%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-timestamp | document.retainedKiB | 303.027 | 302.979 | -0.049 KiB (-0.02%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.elapsedUsPerRoot | 577.779 | 568.125 | -9.654 us/root (-1.67%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.peakKiB | 1279.028 | 1277.356 | -1.672 KiB (-0.13%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | columns.retainedKiB | 321.297 | 321.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.elapsedUsPerRoot | 576.022 | 584.577 | +8.555 us/root (+1.49%) | 9 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.peakKiB | 1282.856 | 1281.185 | -1.672 KiB (-0.13%) | 3 | within noise |
| 3.14 | provider-free-delivery | leaf-uuid | document.retainedKiB | 321.297 | 321.297 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.elapsedUsPerRoot | 32.863 | 31.801 | -1.063 us/root (-3.23%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.peakKiB | 97.325 | 95.653 | -1.672 KiB (-1.72%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | columns.retainedKiB | 51.109 | 51.109 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.elapsedUsPerRoot | 33.620 | 32.689 | -0.931 us/root (-2.77%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.peakKiB | 101.036 | 99.364 | -1.672 KiB (-1.65%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-1 | document.retainedKiB | 51.109 | 51.109 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.elapsedUsPerRoot | 47.891 | 47.227 | -0.664 us/root (-1.39%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.peakKiB | 148.214 | 145.800 | -2.414 KiB (-1.63%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | columns.retainedKiB | 88.234 | 88.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.elapsedUsPerRoot | 48.647 | 47.710 | -0.938 us/root (-1.93%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.peakKiB | 151.401 | 149.038 | -2.363 KiB (-1.56%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-4 | document.retainedKiB | 88.234 | 88.234 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.elapsedUsPerRoot | 68.923 | 67.020 | -1.904 us/root (-2.76%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.peakKiB | 223.218 | 220.546 | -2.672 KiB (-1.20%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | columns.retainedKiB | 137.734 | 137.734 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.elapsedUsPerRoot | 68.695 | 68.369 | -0.327 us/root (-0.48%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.peakKiB | 227.249 | 223.866 | -3.383 KiB (-1.49%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-depth-8 | document.retainedKiB | 137.734 | 137.734 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.elapsedUsPerRoot | 24.316 | 23.216 | -1.100 us/root (-4.52%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.peakKiB | 61.062 | 60.078 | -0.984 KiB (-1.61%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | columns.retainedKiB | 24.359 | 24.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.elapsedUsPerRoot | 24.865 | 23.648 | -1.216 us/root (-4.89%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.peakKiB | 67.422 | 65.938 | -1.484 KiB (-2.20%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-0 | document.retainedKiB | 24.359 | 24.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.elapsedUsPerRoot | 154.587 | 153.488 | -1.099 us/root (-0.71%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.peakKiB | 629.829 | 626.806 | -3.023 KiB (-0.48%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | columns.retainedKiB | 428.359 | 428.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.elapsedUsPerRoot | 155.785 | 155.052 | -0.733 us/root (-0.47%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.peakKiB | 633.739 | 630.091 | -3.648 KiB (-0.58%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-32 | document.retainedKiB | 428.359 | 428.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.elapsedUsPerRoot | 58.184 | 56.141 | -2.043 us/root (-3.51%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.peakKiB | 198.134 | 195.532 | -2.602 KiB (-1.31%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | columns.retainedKiB | 125.359 | 125.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.elapsedUsPerRoot | 58.388 | 56.773 | -1.615 us/root (-2.77%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.peakKiB | 201.552 | 198.052 | -3.500 KiB (-1.74%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-many-8 | document.retainedKiB | 125.359 | 125.359 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.elapsedUsPerRoot | 48.576 | 47.689 | -0.887 us/root (-1.83%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.peakKiB | 127.213 | 125.541 | -1.672 KiB (-1.31%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | columns.retainedKiB | 36.203 | 36.203 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.elapsedUsPerRoot | 48.583 | 48.272 | -0.311 us/root (-0.64%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.peakKiB | 130.924 | 129.252 | -1.672 KiB (-1.28%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-sparse-64 | document.retainedKiB | 36.203 | 36.203 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.elapsedUsPerRoot | 55.711 | 55.055 | -0.656 us/root (-1.18%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.peakKiB | 222.470 | 219.196 | -3.273 KiB (-1.47%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | columns.retainedKiB | 136.984 | 136.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.elapsedUsPerRoot | 56.578 | 55.411 | -1.167 us/root (-2.06%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.peakKiB | 226.376 | 222.603 | -3.773 KiB (-1.67%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-16 | document.retainedKiB | 136.984 | 136.984 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.elapsedUsPerRoot | 145.680 | 144.081 | -1.599 us/root (-1.10%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.peakKiB | 765.188 | 761.915 | -3.273 KiB (-0.43%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | columns.retainedKiB | 480.484 | 480.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.elapsedUsPerRoot | 147.206 | 145.944 | -1.262 us/root (-0.86%) | 9 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.peakKiB | 769.095 | 765.321 | -3.773 KiB (-0.49%) | 3 | within noise |
| 3.14 | provider-free-delivery | read-width-64 | document.retainedKiB | 480.484 | 480.484 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.elapsedUs | 257.250 | 254.625 | -2.625 us (-1.02%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.peakKiB | 37.547 | 33.055 | -4.492 KiB (-11.96%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-1 | plan.cold.retainedKiB | 29.992 | 26.398 | -3.594 KiB (-11.98%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.elapsedUs | 377.792 | 379.333 | +1.541 us (+0.41%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.peakKiB | 50.483 | 45.179 | -5.305 KiB (-10.51%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-2 | plan.cold.retainedKiB | 41.921 | 37.507 | -4.414 KiB (-10.53%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.elapsedUs | 499.584 | 499.791 | +0.207 us (+0.04%) | 9 | within noise |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.peakKiB | 62.709 | 56.186 | -6.523 KiB (-10.40%) | 3 | smaller |
| 3.14 | read-plan-compilation | control-guarded-3 | plan.cold.retainedKiB | 53.326 | 48.092 | -5.234 KiB (-9.82%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.elapsedUs | 92.208 | 91.042 | -1.166 us (-1.26%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.peakKiB | 21.005 | 20.060 | -0.945 KiB (-4.50%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | columns.retainedKiB | 14.981 | 14.286 | -0.695 KiB (-4.64%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.elapsedUs | 93.792 | 93.167 | -0.625 us (-0.67%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-1 | document.peakKiB | 21.168 | 20.082 | -1.086 KiB (-5.13%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-1 | document.retainedKiB | 15.145 | 14.449 | -0.695 KiB (-4.59%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.elapsedUs | 90.833 | 91.083 | +0.250 us (+0.28%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.peakKiB | 21.005 | 20.060 | -0.945 KiB (-4.50%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | columns.retainedKiB | 14.981 | 14.286 | -0.695 KiB (-4.64%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.elapsedUs | 93.042 | 92.041 | -1.001 us (-1.08%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-depth-8 | document.peakKiB | 21.168 | 20.082 | -1.086 KiB (-5.13%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-depth-8 | document.retainedKiB | 15.145 | 14.449 | -0.695 KiB (-4.59%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.elapsedUs | 92.041 | 91.500 | -0.541 us (-0.59%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | columns.peakKiB | 21.006 | 20.061 | -0.945 KiB (-4.50%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | columns.retainedKiB | 14.982 | 14.287 | -0.695 KiB (-4.64%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.elapsedUs | 93.333 | 93.500 | +0.167 us (+0.18%) | 9 | within noise |
| 3.14 | read-plan-compilation | plan-width-64 | document.peakKiB | 21.169 | 20.083 | -1.086 KiB (-5.13%) | 3 | smaller |
| 3.14 | read-plan-compilation | plan-width-64 | document.retainedKiB | 15.146 | 14.450 | -0.695 KiB (-4.59%) | 3 | smaller |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.elapsedUs | 15.250 | 15.459 | +0.209 us (+1.37%) | 9 | within noise |
| 3.14 | read-plan-reuse | control-guarded-1 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.elapsedUs | 21.000 | 21.250 | +0.250 us (+1.19%) | 9 | within noise |
| 3.14 | read-plan-reuse | control-guarded-2 | plan.warm.retainedKiB | 0.062 | 0.062 | +0.000 KiB (+0.00%) | 3 | within noise |
| 3.14 | read-plan-reuse | control-guarded-3 | plan.warm.elapsedUs | 26.792 | 27.291 | +0.499 us (+1.86%) | 9 | within noise |
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
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 212.333 | 153.000 | -59.333 us/row (-27.94%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 1432.000 | 896.000 | -536.000 B/row (-37.43%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 10866.000 | 8962.000 | -1904.000 B/row (-17.52%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 212.667 | 163.875 | -48.792 us/row (-22.94%) | 9 | faster |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 1432.000 | 896.000 | -536.000 B/row (-37.43%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 11114.000 | 9778.000 | -1336.000 B/row (-12.02%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 312.500 | 194.541 | -117.959 us/row (-37.75%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 1432.000 | 896.000 | -536.000 B/row (-37.43%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 8956.000 | 7052.000 | -1904.000 B/row (-21.26%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 289.541 | 174.750 | -114.791 us/row (-39.65%) | 9 | faster |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 1432.000 | 896.000 | -536.000 B/row (-37.43%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 9201.000 | 7865.000 | -1336.000 B/row (-14.52%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 353.417 | 208.125 | -145.292 us/row (-41.11%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1712.000 | 1176.000 | -536.000 B/row (-31.31%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 12574.000 | 11390.000 | -1184.000 B/row (-9.42%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 341.417 | 194.208 | -147.209 us/row (-43.12%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1712.000 | 1176.000 | -536.000 B/row (-31.31%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13350.000 | 12494.000 | -856.000 B/row (-6.41%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 945.166 | 422.042 | -523.124 us/row (-55.35%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2832.000 | 2296.000 | -536.000 B/row (-18.93%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 20857.000 | 19673.000 | -1184.000 B/row (-5.68%) | 9 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 865.041 | 332.250 | -532.791 us/row (-61.59%) | 9 | faster |
| 3.13 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2832.000 | 2296.000 | -536.000 B/row (-18.93%) | 1 | smaller |
| 3.13 | keyed-write | ancestor.width-64.document.typed | transientBytes | 23890.000 | 23034.000 | -856.000 B/row (-3.58%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 286.959 | 254.875 | -32.084 us/row (-11.18%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 2160.000 | 1624.000 | -536.000 B/row (-24.81%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 15296.000 | 14728.000 | -568.000 B/row (-3.71%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 277.166 | 249.958 | -27.208 us/row (-9.82%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 2288.000 | 1656.000 | -632.000 B/row (-27.62%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16140.000 | 15204.000 | -936.000 B/row (-5.80%) | 9 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 279.333 | 249.166 | -30.167 us/row (-10.80%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 2160.000 | 1574.000 | -586.000 B/row (-27.13%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15481.000 | 15153.000 | -328.000 B/row (-2.12%) | 9 | within noise |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 270.083 | 241.375 | -28.708 us/row (-10.63%) | 9 | faster |
| 3.13 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 2288.000 | 1656.000 | -632.000 B/row (-27.62%) | 1 | smaller |
| 3.13 | keyed-write | bitemporal.interior.document.wire | transientBytes | 16221.000 | 15573.000 | -648.000 B/row (-3.99%) | 9 | smaller |
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
| 3.13 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 110.459 | 115.834 | +5.375 us/row (+4.87%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1648.000 | 1600.000 | -48.000 B/row (-2.91%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 8580.000 | 8812.000 | +232.000 B/row (+2.70%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 110.375 | 114.209 | +3.834 us/row (+3.47%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1648.000 | 1600.000 | -48.000 B/row (-2.91%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-1.document.typed | transientBytes | 8852.000 | 9084.000 | +232.000 B/row (+2.62%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 145.542 | 152.542 | +7.000 us/row (+4.81%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2320.000 | 2272.000 | -48.000 B/row (-2.07%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10341.000 | 10573.000 | +232.000 B/row (+2.24%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 146.500 | 151.459 | +4.959 us/row (+3.38%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2320.000 | 2272.000 | -48.000 B/row (-2.07%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-4.document.typed | transientBytes | 10497.000 | 10729.000 | +232.000 B/row (+2.21%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 193.167 | 200.917 | +7.750 us/row (+4.01%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3216.000 | 3168.000 | -48.000 B/row (-1.49%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 13466.000 | 13866.000 | +400.000 B/row (+2.97%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 191.750 | 197.792 | +6.042 us/row (+3.15%) | 9 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3216.000 | 3168.000 | -48.000 B/row (-1.49%) | 1 | within noise |
| 3.13 | keyed-write | geometry.depth-8.document.typed | transientBytes | 13552.000 | 13952.000 | +400.000 B/row (+2.95%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 88.667 | 92.917 | +4.250 us/row (+4.79%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1144.000 | 1096.000 | -48.000 B/row (-4.20%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7425.000 | 7657.000 | +232.000 B/row (+3.12%) | 9 | larger |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-0.document.typed | elapsedUs | 86.792 | 90.250 | +3.458 us/row (+3.98%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1144.000 | 1096.000 | -48.000 B/row (-4.20%) | 1 | smaller |
| 3.13 | keyed-write | geometry.many-0.document.typed | transientBytes | 7447.000 | 7679.000 | +232.000 B/row (+3.12%) | 9 | larger |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 414.292 | 423.625 | +9.333 us/row (+2.25%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8608.000 | 8560.000 | -48.000 B/row (-0.56%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27376.000 | 27608.000 | +232.000 B/row (+0.85%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-32.document.typed | elapsedUs | 412.250 | 419.333 | +7.083 us/row (+1.72%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8608.000 | 8560.000 | -48.000 B/row (-0.56%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-32.document.typed | transientBytes | 27539.000 | 27771.000 | +232.000 B/row (+0.84%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 171.333 | 177.167 | +5.834 us/row (+3.41%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3040.000 | 2992.000 | -48.000 B/row (-1.58%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.columns.typed | transientBytes | 11920.000 | 12152.000 | +232.000 B/row (+1.95%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.many-8.document.typed | elapsedUs | 173.208 | 179.875 | +6.667 us/row (+3.85%) | 9 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3040.000 | 2992.000 | -48.000 B/row (-1.58%) | 1 | within noise |
| 3.13 | keyed-write | geometry.many-8.document.typed | transientBytes | 12219.000 | 12451.000 | +232.000 B/row (+1.90%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 156.708 | 159.875 | +3.167 us/row (+2.02%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1648.000 | 1600.000 | -48.000 B/row (-2.91%) | 1 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8350.000 | 8582.000 | +232.000 B/row (+2.78%) | 9 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 153.625 | 185.542 | +31.917 us/row (+20.78%) | 9 | slower |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1648.000 | 1600.000 | -48.000 B/row (-2.91%) | 1 | within noise |
| 3.13 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 8619.000 | 8851.000 | +232.000 B/row (+2.69%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 191.084 | 196.041 | +4.957 us/row (+2.59%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2488.000 | 2440.000 | -48.000 B/row (-1.93%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11360.000 | 11592.000 | +232.000 B/row (+2.04%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-16.document.typed | elapsedUs | 190.208 | 194.916 | +4.708 us/row (+2.48%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2488.000 | 2440.000 | -48.000 B/row (-1.93%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-16.document.typed | transientBytes | 11640.000 | 11872.000 | +232.000 B/row (+1.99%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 514.542 | 543.375 | +28.833 us/row (+5.60%) | 9 | slower |
| 3.13 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5848.000 | 5800.000 | -48.000 B/row (-0.82%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.columns.typed | transientBytes | 23567.000 | 23799.000 | +232.000 B/row (+0.98%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | geometry.width-64.document.typed | elapsedUs | 516.792 | 515.834 | -0.958 us/row (-0.19%) | 9 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5848.000 | 5800.000 | -48.000 B/row (-0.82%) | 1 | within noise |
| 3.13 | keyed-write | geometry.width-64.document.typed | transientBytes | 24984.000 | 25216.000 | +232.000 B/row (+0.93%) | 9 | within noise |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.typed | elapsedUs | 156.209 | 120.458 | -35.751 us/row (-22.89%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.typed | retainedBytes | 1968.000 | 1880.000 | -88.000 B/row (-4.47%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.typed | transientBytes | 9139.000 | 7955.000 | -1184.000 B/row (-12.96%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.columns.wire | elapsedUs | 141.000 | 108.166 | -32.834 us/row (-23.29%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.columns.wire | retainedBytes | 2000.000 | 1912.000 | -88.000 B/row (-4.40%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.columns.wire | transientBytes | 9459.000 | 8579.000 | -880.000 B/row (-9.30%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.typed | elapsedUs | 163.792 | 127.667 | -36.125 us/row (-22.06%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.typed | retainedBytes | 1968.000 | 1880.000 | -88.000 B/row (-4.47%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.typed | transientBytes | 9927.000 | 8743.000 | -1184.000 B/row (-11.93%) | 9 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | plain.changed.document.wire | elapsedUs | 146.042 | 115.834 | -30.208 us/row (-20.68%) | 9 | faster |
| 3.13 | keyed-write | plain.changed.document.wire | retainedBytes | 2000.000 | 1912.000 | -88.000 B/row (-4.40%) | 1 | smaller |
| 3.13 | keyed-write | plain.changed.document.wire | transientBytes | 10247.000 | 9367.000 | -880.000 B/row (-8.59%) | 9 | smaller |
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
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.typed | elapsedUs | 192.000 | 161.417 | -30.583 us/row (-15.93%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.typed | retainedBytes | 2160.000 | 1624.000 | -536.000 B/row (-24.81%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.typed | transientBytes | 11217.000 | 9729.000 | -1488.000 B/row (-13.27%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.columns.wire | elapsedUs | 180.833 | 152.916 | -27.917 us/row (-15.44%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.columns.wire | retainedBytes | 2192.000 | 1656.000 | -536.000 B/row (-24.45%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.columns.wire | transientBytes | 11517.000 | 10221.000 | -1296.000 B/row (-11.25%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.typed | elapsedUs | 201.958 | 177.542 | -24.416 us/row (-12.09%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.typed | retainedBytes | 2160.000 | 1624.000 | -536.000 B/row (-24.81%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.typed | transientBytes | 11668.000 | 11220.000 | -448.000 B/row (-3.84%) | 9 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.changed.document.wire | elapsedUs | 187.958 | 161.792 | -26.166 us/row (-13.92%) | 9 | faster |
| 3.13 | keyed-write | txtime.changed.document.wire | retainedBytes | 2192.000 | 1656.000 | -536.000 B/row (-24.45%) | 1 | smaller |
| 3.13 | keyed-write | txtime.changed.document.wire | transientBytes | 12096.000 | 11416.000 | -680.000 B/row (-5.62%) | 9 | smaller |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.typed | elapsedUs | 113.167 | 121.542 | +8.375 us/row (+7.40%) | 9 | slower |
| 3.13 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1872.000 | 1824.000 | -48.000 B/row (-2.56%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.typed | transientBytes | 10118.000 | 10486.000 | +368.000 B/row (+3.64%) | 9 | larger |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.columns.wire | elapsedUs | 116.292 | 121.042 | +4.750 us/row (+4.08%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1872.000 | 2016.000 | +144.000 B/row (+7.69%) | 1 | larger |
| 3.13 | keyed-write | txtime.opening.columns.wire | transientBytes | 10302.000 | 10814.000 | +512.000 B/row (+4.97%) | 9 | larger |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.typed | elapsedUs | 111.458 | 118.583 | +7.125 us/row (+6.39%) | 9 | slower |
| 3.13 | keyed-write | txtime.opening.document.typed | retainedBytes | 1872.000 | 1824.000 | -48.000 B/row (-2.56%) | 1 | within noise |
| 3.13 | keyed-write | txtime.opening.document.typed | transientBytes | 10142.000 | 10510.000 | +368.000 B/row (+3.63%) | 9 | larger |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.13 | keyed-write | txtime.opening.document.wire | elapsedUs | 114.083 | 119.083 | +5.000 us/row (+4.38%) | 9 | within noise |
| 3.13 | keyed-write | txtime.opening.document.wire | retainedBytes | 1872.000 | 2016.000 | +144.000 B/row (+7.69%) | 1 | larger |
| 3.13 | keyed-write | txtime.opening.document.wire | transientBytes | 10262.000 | 10718.000 | +456.000 B/row (+4.44%) | 9 | larger |
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
| 3.13 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 85.833 | 31.333 | -54.500 us/row (-63.50%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 7168.000 | 3754.000 | -3414.000 B/row (-47.63%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 72.584 | 26.000 | -46.584 us/row (-64.18%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 7184.000 | 3406.000 | -3778.000 B/row (-52.59%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 86.542 | 31.292 | -55.250 us/row (-63.84%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.typed | transientBytes | 7168.000 | 3756.000 | -3412.000 B/row (-47.60%) | 9 | smaller |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.13 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 73.417 | 25.791 | -47.626 us/row (-64.87%) | 9 | faster |
| 3.13 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.13 | keyed-write | txtime.unchanged.document.wire | transientBytes | 7184.000 | 3409.000 | -3775.000 B/row (-52.55%) | 9 | smaller |
| 3.13 | model-preparation | model.prepared | elapsedUs | 3301.625 | 3350.250 | +48.625 us (+1.47%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared | retainedBytes | 426776.000 | 426856.000 | +80.000 B (+0.02%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared | transientBytes | 438904.000 | 438984.000 | +80.000 B (+0.02%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | elapsedUs | 304.833 | 304.375 | -0.458 us (-0.15%) | 9 | within noise |
| 3.13 | model-preparation | model.prepared.family | retainedBytes | 23472.000 | 23552.000 | +80.000 B (+0.34%) | 1 | within noise |
| 3.13 | model-preparation | model.prepared.family | transientBytes | 27536.000 | 27616.000 | +80.000 B (+0.29%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 24.610 | 22.548 | -2.062 us/row (-8.38%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 911.875 | 918.250 | +6.375 B/row (+0.70%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 2003.484 | 2114.422 | +110.938 B/row (+5.54%) | 9 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 25.523 | 23.594 | -1.929 us/row (-7.56%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1913.375 | 1919.750 | +6.375 B/row (+0.33%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2469.828 | 2481.391 | +11.562 B/row (+0.47%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 29.146 | 26.833 | -2.312 us/row (-7.93%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1032.500 | 1058.000 | +25.500 B/row (+2.47%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2650.812 | 2540.562 | -110.250 B/row (-4.16%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 30.404 | 27.749 | -2.655 us/row (-8.73%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2038.500 | 2064.000 | +25.500 B/row (+1.25%) | 1 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 3010.688 | 3000.938 | -9.750 B/row (-0.32%) | 9 | within noise |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 48.323 | 43.646 | -4.677 us/row (-9.68%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1523.000 | 1625.000 | +102.000 B/row (+6.70%) | 1 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 4640.250 | 4419.250 | -221.000 B/row (-4.76%) | 9 | smaller |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 49.375 | 44.599 | -4.776 us/row (-9.67%) | 9 | faster |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2547.000 | 2649.000 | +102.000 B/row (+4.00%) | 1 | larger |
| 3.13 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 4862.750 | 4655.750 | -207.000 B/row (-4.26%) | 9 | smaller |
| 3.13 | wire-insert-response | response.insert.family.wire | elapsedUs | 61.708 | 62.667 | +0.959 us/row (+1.55%) | 9 | within noise |
| 3.13 | wire-insert-response | response.insert.family.wire | retainedBytes | 7528.000 | 8392.000 | +864.000 B/row (+11.48%) | 1 | larger |
| 3.13 | wire-insert-response | response.insert.family.wire | transientBytes | 7616.000 | 7712.000 | +96.000 B/row (+1.26%) | 9 | within noise |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | elapsedUs | 234.500 | 180.875 | -53.625 us/row (-22.87%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | retainedBytes | 1440.000 | 904.000 | -536.000 B/row (-37.22%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.columns.typed | transientBytes | 11034.000 | 9346.000 | -1688.000 B/row (-15.30%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | elapsedUs | 237.375 | 180.708 | -56.667 us/row (-23.87%) | 9 | faster |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | retainedBytes | 1440.000 | 904.000 | -536.000 B/row (-37.22%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.depth-1.document.typed | transientBytes | 11554.000 | 10362.000 | -1192.000 B/row (-10.32%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | elapsedUs | 342.750 | 221.583 | -121.167 us/row (-35.35%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | retainedBytes | 1440.000 | 904.000 | -536.000 B/row (-37.22%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.columns.typed | transientBytes | 9220.000 | 7532.000 | -1688.000 B/row (-18.31%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | elapsedUs | 318.208 | 207.167 | -111.041 us/row (-34.90%) | 9 | faster |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | retainedBytes | 1440.000 | 904.000 | -536.000 B/row (-37.22%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.sparse-64.document.typed | transientBytes | 9649.000 | 8457.000 | -1192.000 B/row (-12.35%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | elapsedUs | 383.334 | 236.792 | -146.542 us/row (-38.23%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | retainedBytes | 1720.000 | 1184.000 | -536.000 B/row (-31.16%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.columns.typed | transientBytes | 12926.000 | 11958.000 | -968.000 B/row (-7.49%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-16.document.typed | elapsedUs | 372.500 | 219.958 | -152.542 us/row (-40.95%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-16.document.typed | retainedBytes | 1720.000 | 1184.000 | -536.000 B/row (-31.16%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-16.document.typed | transientBytes | 13854.000 | 13142.000 | -712.000 B/row (-5.14%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | elapsedUs | 998.333 | 448.959 | -549.374 us/row (-55.03%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | retainedBytes | 2840.000 | 2304.000 | -536.000 B/row (-18.87%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.columns.typed | transientBytes | 23617.000 | 20153.000 | -3464.000 B/row (-14.67%) | 9 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | ancestor.width-64.document.typed | elapsedUs | 912.750 | 368.833 | -543.917 us/row (-59.59%) | 9 | faster |
| 3.14 | keyed-write | ancestor.width-64.document.typed | retainedBytes | 2840.000 | 2304.000 | -536.000 B/row (-18.87%) | 1 | smaller |
| 3.14 | keyed-write | ancestor.width-64.document.typed | transientBytes | 26834.000 | 23626.000 | -3208.000 B/row (-11.95%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | elapsedUs | 313.792 | 288.500 | -25.292 us/row (-8.06%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | retainedBytes | 2176.000 | 1640.000 | -536.000 B/row (-24.63%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.typed | transientBytes | 14896.000 | 14648.000 | -248.000 B/row (-1.66%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedDocument | 12.000 | 12.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.encodeManagedMany | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | elapsedUs | 308.417 | 284.959 | -23.458 us/row (-7.61%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | retainedBytes | 2304.000 | 1672.000 | -632.000 B/row (-27.43%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.columns.wire | transientBytes | 16004.000 | 15288.000 | -716.000 B/row (-4.47%) | 9 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.typed | elapsedUs | 310.083 | 285.375 | -24.708 us/row (-7.97%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.typed | retainedBytes | 2176.000 | 1640.000 | -536.000 B/row (-24.63%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.typed | transientBytes | 15217.000 | 15201.000 | -16.000 B/row (-0.11%) | 9 | within noise |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | bitemporal.interior.document.wire | elapsedUs | 298.583 | 271.583 | -27.000 us/row (-9.04%) | 9 | faster |
| 3.14 | keyed-write | bitemporal.interior.document.wire | retainedBytes | 2304.000 | 1672.000 | -632.000 B/row (-27.43%) | 1 | smaller |
| 3.14 | keyed-write | bitemporal.interior.document.wire | transientBytes | 16325.000 | 15849.000 | -476.000 B/row (-2.92%) | 9 | within noise |
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
| 3.14 | keyed-write | geometry.depth-1.columns.typed | elapsedUs | 130.458 | 138.125 | +7.667 us/row (+5.88%) | 9 | slower |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | retainedBytes | 1704.000 | 1616.000 | -88.000 B/row (-5.16%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.columns.typed | transientBytes | 9116.000 | 9436.000 | +320.000 B/row (+3.51%) | 9 | larger |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-1.document.typed | elapsedUs | 130.458 | 136.292 | +5.834 us/row (+4.47%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-1.document.typed | retainedBytes | 1704.000 | 1616.000 | -88.000 B/row (-5.16%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-1.document.typed | transientBytes | 9516.000 | 9836.000 | +320.000 B/row (+3.36%) | 9 | larger |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedDocument | 6.000 | 6.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | elapsedUs | 170.875 | 175.500 | +4.625 us/row (+2.71%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | retainedBytes | 2376.000 | 2288.000 | -88.000 B/row (-3.70%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.columns.typed | transientBytes | 10973.000 | 11293.000 | +320.000 B/row (+2.92%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedDocument | 7.000 | 7.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-4.document.typed | elapsedUs | 167.416 | 172.958 | +5.542 us/row (+3.31%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-4.document.typed | retainedBytes | 2376.000 | 2288.000 | -88.000 B/row (-3.70%) | 1 | smaller |
| 3.14 | keyed-write | geometry.depth-4.document.typed | transientBytes | 11257.000 | 11577.000 | +320.000 B/row (+2.84%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | elapsedUs | 218.500 | 223.084 | +4.584 us/row (+2.10%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | retainedBytes | 3272.000 | 3184.000 | -88.000 B/row (-2.69%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.columns.typed | transientBytes | 14186.000 | 14634.000 | +448.000 B/row (+3.16%) | 9 | larger |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedDocument | 11.000 | 11.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.depth-8.document.typed | elapsedUs | 214.416 | 224.125 | +9.709 us/row (+4.53%) | 9 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | retainedBytes | 3272.000 | 3184.000 | -88.000 B/row (-2.69%) | 1 | within noise |
| 3.14 | keyed-write | geometry.depth-8.document.typed | transientBytes | 14360.000 | 14744.000 | +384.000 B/row (+2.67%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedDocument | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.columns.typed | elapsedUs | 108.375 | 113.958 | +5.583 us/row (+5.15%) | 9 | slower |
| 3.14 | keyed-write | geometry.many-0.columns.typed | retainedBytes | 1192.000 | 1104.000 | -88.000 B/row (-7.38%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.columns.typed | transientBytes | 7961.000 | 8217.000 | +256.000 B/row (+3.22%) | 9 | larger |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedDocument | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-0.document.typed | elapsedUs | 106.084 | 113.917 | +7.833 us/row (+7.38%) | 9 | slower |
| 3.14 | keyed-write | geometry.many-0.document.typed | retainedBytes | 1192.000 | 1104.000 | -88.000 B/row (-7.38%) | 1 | smaller |
| 3.14 | keyed-write | geometry.many-0.document.typed | transientBytes | 8047.000 | 8367.000 | +320.000 B/row (+3.98%) | 9 | larger |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedDocument | 33.000 | 33.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.columns.typed | elapsedUs | 440.500 | 452.458 | +11.958 us/row (+2.71%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | retainedBytes | 8664.000 | 8576.000 | -88.000 B/row (-1.02%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.columns.typed | transientBytes | 27944.000 | 28200.000 | +256.000 B/row (+0.92%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedDocument | 34.000 | 34.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-32.document.typed | elapsedUs | 442.667 | 452.625 | +9.958 us/row (+2.25%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | retainedBytes | 8664.000 | 8576.000 | -88.000 B/row (-1.02%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-32.document.typed | transientBytes | 28171.000 | 28491.000 | +320.000 B/row (+1.14%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedDocument | 9.000 | 9.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.columns.typed | elapsedUs | 192.458 | 203.792 | +11.334 us/row (+5.89%) | 9 | slower |
| 3.14 | keyed-write | geometry.many-8.columns.typed | retainedBytes | 3096.000 | 3008.000 | -88.000 B/row (-2.84%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.columns.typed | transientBytes | 12488.000 | 12744.000 | +256.000 B/row (+2.05%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedDocument | 10.000 | 10.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.many-8.document.typed | elapsedUs | 193.459 | 200.833 | +7.374 us/row (+3.81%) | 9 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | retainedBytes | 3096.000 | 3008.000 | -88.000 B/row (-2.84%) | 1 | within noise |
| 3.14 | keyed-write | geometry.many-8.document.typed | transientBytes | 12883.000 | 13203.000 | +320.000 B/row (+2.48%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | elapsedUs | 181.917 | 187.250 | +5.333 us/row (+2.93%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | retainedBytes | 1704.000 | 1616.000 | -88.000 B/row (-5.16%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.columns.typed | transientBytes | 8918.000 | 9238.000 | +320.000 B/row (+3.59%) | 9 | larger |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | elapsedUs | 180.708 | 186.459 | +5.751 us/row (+3.18%) | 9 | within noise |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | retainedBytes | 1704.000 | 1616.000 | -88.000 B/row (-5.16%) | 1 | smaller |
| 3.14 | keyed-write | geometry.sparse-64.document.typed | transientBytes | 9315.000 | 9635.000 | +320.000 B/row (+3.44%) | 9 | larger |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.columns.typed | elapsedUs | 217.875 | 220.875 | +3.000 us/row (+1.38%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.columns.typed | retainedBytes | 2544.000 | 2456.000 | -88.000 B/row (-3.46%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.columns.typed | transientBytes | 11960.000 | 12280.000 | +320.000 B/row (+2.68%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-16.document.typed | elapsedUs | 214.084 | 220.583 | +6.499 us/row (+3.04%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-16.document.typed | retainedBytes | 2544.000 | 2456.000 | -88.000 B/row (-3.46%) | 1 | smaller |
| 3.14 | keyed-write | geometry.width-16.document.typed | transientBytes | 12336.000 | 12656.000 | +320.000 B/row (+2.59%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.columns.typed | elapsedUs | 553.375 | 554.584 | +1.209 us/row (+0.22%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.columns.typed | transientBytes | 24135.000 | 24455.000 | +320.000 B/row (+1.33%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | geometry.width-64.document.typed | elapsedUs | 553.584 | 561.959 | +8.375 us/row (+1.51%) | 9 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | geometry.width-64.document.typed | transientBytes | 25680.000 | 26000.000 | +320.000 B/row (+1.25%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.typed | elapsedUs | 486.666 | 511.750 | +25.084 us/row (+5.15%) | 9 | slower |
| 3.14 | keyed-write | leaf.boolean.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.typed | transientBytes | 21101.000 | 21421.000 | +320.000 B/row (+1.52%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.columns.wire | elapsedUs | 551.000 | 559.291 | +8.291 us/row (+1.50%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | retainedBytes | 5904.000 | 6024.000 | +120.000 B/row (+2.03%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.columns.wire | transientBytes | 21197.000 | 21629.000 | +432.000 B/row (+2.04%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.typed | elapsedUs | 487.084 | 493.917 | +6.833 us/row (+1.40%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.typed | transientBytes | 22046.000 | 22366.000 | +320.000 B/row (+1.45%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.boolean.document.wire | elapsedUs | 554.625 | 553.333 | -1.292 us/row (-0.23%) | 9 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | retainedBytes | 5904.000 | 6024.000 | +120.000 B/row (+2.03%) | 1 | within noise |
| 3.14 | keyed-write | leaf.boolean.document.wire | transientBytes | 22142.000 | 22574.000 | +432.000 B/row (+1.95%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.typed | elapsedUs | 561.750 | 573.708 | +11.958 us/row (+2.13%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.typed | transientBytes | 44547.000 | 44867.000 | +320.000 B/row (+0.72%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.columns.wire | elapsedUs | 726.500 | 739.375 | +12.875 us/row (+1.77%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | retainedBytes | 15312.000 | 15432.000 | +120.000 B/row (+0.78%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.columns.wire | transientBytes | 54051.000 | 54483.000 | +432.000 B/row (+0.80%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.typed | elapsedUs | 570.083 | 570.625 | +0.542 us/row (+0.10%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.typed | transientBytes | 47372.000 | 47692.000 | +320.000 B/row (+0.68%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.bytes.document.wire | elapsedUs | 726.333 | 734.250 | +7.917 us/row (+1.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | retainedBytes | 15312.000 | 15432.000 | +120.000 B/row (+0.78%) | 1 | within noise |
| 3.14 | keyed-write | leaf.bytes.document.wire | transientBytes | 56876.000 | 57308.000 | +432.000 B/row (+0.76%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.typed | elapsedUs | 627.875 | 629.500 | +1.625 us/row (+0.26%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.typed | transientBytes | 33282.000 | 33602.000 | +320.000 B/row (+0.96%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.columns.wire | elapsedUs | 851.583 | 868.666 | +17.083 us/row (+2.01%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | retainedBytes | 12048.000 | 12168.000 | +120.000 B/row (+1.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.columns.wire | transientBytes | 39514.000 | 39946.000 | +432.000 B/row (+1.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.typed | elapsedUs | 626.083 | 629.250 | +3.167 us/row (+0.51%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.typed | transientBytes | 34699.000 | 35019.000 | +320.000 B/row (+0.92%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.date.document.wire | elapsedUs | 857.708 | 854.291 | -3.417 us/row (-0.40%) | 9 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | retainedBytes | 12048.000 | 12168.000 | +120.000 B/row (+1.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.date.document.wire | transientBytes | 40931.000 | 41363.000 | +432.000 B/row (+1.06%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.typed | elapsedUs | 1038.125 | 1034.167 | -3.958 us/row (-0.38%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.typed | transientBytes | 36141.000 | 36365.000 | +224.000 B/row (+0.62%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.columns.wire | elapsedUs | 1858.834 | 1853.833 | -5.001 us/row (-0.27%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | retainedBytes | 28944.000 | 29064.000 | +120.000 B/row (+0.41%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.columns.wire | transientBytes | 59337.000 | 59705.000 | +368.000 B/row (+0.62%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.typed | elapsedUs | 1040.875 | 1046.167 | +5.292 us/row (+0.51%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.typed | transientBytes | 37686.000 | 37910.000 | +224.000 B/row (+0.59%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.decimal.document.wire | elapsedUs | 1864.625 | 1860.583 | -4.042 us/row (-0.22%) | 9 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | retainedBytes | 28944.000 | 29064.000 | +120.000 B/row (+0.41%) | 1 | within noise |
| 3.14 | keyed-write | leaf.decimal.document.wire | transientBytes | 60818.000 | 61250.000 | +432.000 B/row (+0.71%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.typed | elapsedUs | 893.833 | 903.042 | +9.209 us/row (+1.03%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | retainedBytes | 10512.000 | 10424.000 | -88.000 B/row (-0.84%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.typed | transientBytes | 30837.000 | 31157.000 | +320.000 B/row (+1.04%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.columns.wire | elapsedUs | 1279.500 | 1293.333 | +13.833 us/row (+1.08%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | retainedBytes | 10512.000 | 10632.000 | +120.000 B/row (+1.14%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.columns.wire | transientBytes | 30997.000 | 31365.000 | +368.000 B/row (+1.19%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.typed | elapsedUs | 900.416 | 929.417 | +29.001 us/row (+3.22%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | retainedBytes | 10512.000 | 10424.000 | -88.000 B/row (-0.84%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.typed | transientBytes | 31870.000 | 32190.000 | +320.000 B/row (+1.00%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float32.document.wire | elapsedUs | 1287.000 | 1278.000 | -9.000 us/row (-0.70%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | retainedBytes | 10512.000 | 10632.000 | +120.000 B/row (+1.14%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float32.document.wire | transientBytes | 31966.000 | 32398.000 | +432.000 B/row (+1.35%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.typed | elapsedUs | 566.583 | 574.250 | +7.667 us/row (+1.35%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.typed | transientBytes | 21573.000 | 21893.000 | +320.000 B/row (+1.48%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.columns.wire | elapsedUs | 651.834 | 660.917 | +9.083 us/row (+1.39%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | retainedBytes | 5904.000 | 6024.000 | +120.000 B/row (+2.03%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.columns.wire | transientBytes | 21669.000 | 22101.000 | +432.000 B/row (+1.99%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.typed | elapsedUs | 559.125 | 569.042 | +9.917 us/row (+1.77%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.typed | transientBytes | 22606.000 | 22926.000 | +320.000 B/row (+1.42%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.float64.document.wire | elapsedUs | 653.834 | 658.708 | +4.874 us/row (+0.75%) | 9 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | retainedBytes | 5904.000 | 6024.000 | +120.000 B/row (+2.03%) | 1 | within noise |
| 3.14 | keyed-write | leaf.float64.document.wire | transientBytes | 22702.000 | 23134.000 | +432.000 B/row (+1.90%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.typed | elapsedUs | 509.334 | 522.333 | +12.999 us/row (+2.55%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.typed | transientBytes | 22326.000 | 22646.000 | +320.000 B/row (+1.43%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.columns.wire | elapsedUs | 650.959 | 659.000 | +8.041 us/row (+1.24%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | retainedBytes | 12032.000 | 12152.000 | +120.000 B/row (+1.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.columns.wire | transientBytes | 28510.000 | 28942.000 | +432.000 B/row (+1.52%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.typed | elapsedUs | 508.500 | 522.958 | +14.458 us/row (+2.84%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.typed | transientBytes | 23510.000 | 23830.000 | +320.000 B/row (+1.36%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int32.document.wire | elapsedUs | 650.958 | 644.958 | -6.000 us/row (-0.92%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | retainedBytes | 12032.000 | 12152.000 | +120.000 B/row (+1.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int32.document.wire | transientBytes | 29694.000 | 30126.000 | +432.000 B/row (+1.45%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.typed | elapsedUs | 532.833 | 533.333 | +0.500 us/row (+0.09%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.typed | transientBytes | 23306.000 | 23626.000 | +320.000 B/row (+1.37%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.columns.wire | elapsedUs | 675.834 | 680.875 | +5.041 us/row (+0.75%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | retainedBytes | 12048.000 | 12168.000 | +120.000 B/row (+1.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.columns.wire | transientBytes | 29546.000 | 29978.000 | +432.000 B/row (+1.46%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.typed | elapsedUs | 523.000 | 531.792 | +8.792 us/row (+1.68%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.typed | transientBytes | 24686.000 | 25006.000 | +320.000 B/row (+1.30%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.int64.document.wire | elapsedUs | 675.667 | 685.708 | +10.041 us/row (+1.49%) | 9 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | retainedBytes | 12048.000 | 12168.000 | +120.000 B/row (+1.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.int64.document.wire | transientBytes | 30926.000 | 31358.000 | +432.000 B/row (+1.40%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.columns.wire | elapsedUs | 678.750 | 678.875 | +0.125 us/row (+0.02%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | retainedBytes | 5904.000 | 6024.000 | +120.000 B/row (+2.03%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.columns.wire | transientBytes | 24228.000 | 24660.000 | +432.000 B/row (+1.78%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.string.document.wire | elapsedUs | 669.375 | 679.500 | +10.125 us/row (+1.51%) | 9 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | retainedBytes | 5904.000 | 6024.000 | +120.000 B/row (+2.03%) | 1 | within noise |
| 3.14 | keyed-write | leaf.string.document.wire | transientBytes | 25773.000 | 26205.000 | +432.000 B/row (+1.68%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.typed | elapsedUs | 675.291 | 683.208 | +7.917 us/row (+1.17%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.typed | transientBytes | 35842.000 | 36162.000 | +320.000 B/row (+0.89%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.columns.wire | elapsedUs | 928.958 | 940.083 | +11.125 us/row (+1.20%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | retainedBytes | 12048.000 | 12168.000 | +120.000 B/row (+1.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.columns.wire | transientBytes | 42138.000 | 42506.000 | +368.000 B/row (+0.87%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.typed | elapsedUs | 687.250 | 683.625 | -3.625 us/row (-0.53%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.typed | transientBytes | 37579.000 | 37899.000 | +320.000 B/row (+0.85%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.time.document.wire | elapsedUs | 935.667 | 942.583 | +6.916 us/row (+0.74%) | 9 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | retainedBytes | 12048.000 | 12168.000 | +120.000 B/row (+1.00%) | 1 | within noise |
| 3.14 | keyed-write | leaf.time.document.wire | transientBytes | 43811.000 | 44243.000 | +432.000 B/row (+0.99%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | elapsedUs | 790.125 | 796.000 | +5.875 us/row (+0.74%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.typed | transientBytes | 41991.000 | 42311.000 | +320.000 B/row (+0.76%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | elapsedUs | 1180.625 | 1186.708 | +6.083 us/row (+0.52%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | retainedBytes | 15120.000 | 15240.000 | +120.000 B/row (+0.79%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.columns.wire | transientBytes | 51611.000 | 51979.000 | +368.000 B/row (+0.71%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.typed | elapsedUs | 783.000 | 789.417 | +6.417 us/row (+0.82%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.typed | transientBytes | 44496.000 | 44816.000 | +320.000 B/row (+0.72%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.timestamp.document.wire | elapsedUs | 1189.708 | 1184.833 | -4.875 us/row (-0.41%) | 9 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | retainedBytes | 15120.000 | 15240.000 | +120.000 B/row (+0.79%) | 1 | within noise |
| 3.14 | keyed-write | leaf.timestamp.document.wire | transientBytes | 54052.000 | 54484.000 | +432.000 B/row (+0.80%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.typed | elapsedUs | 911.375 | 923.375 | +12.000 us/row (+1.32%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.typed | transientBytes | 46714.000 | 47034.000 | +320.000 B/row (+0.69%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedDocument | 3.000 | 3.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.columns.wire | elapsedUs | 1270.542 | 1274.125 | +3.583 us/row (+0.28%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | retainedBytes | 26640.000 | 26760.000 | +120.000 B/row (+0.45%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.columns.wire | transientBytes | 67610.000 | 67978.000 | +368.000 B/row (+0.54%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.typed | elapsedUs | 906.167 | 911.583 | +5.416 us/row (+0.60%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | retainedBytes | 5904.000 | 5816.000 | -88.000 B/row (-1.49%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.typed | transientBytes | 49795.000 | 50115.000 | +320.000 B/row (+0.64%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | leaf.uuid.document.wire | elapsedUs | 1269.875 | 1279.167 | +9.292 us/row (+0.73%) | 9 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | retainedBytes | 26640.000 | 26760.000 | +120.000 B/row (+0.45%) | 1 | within noise |
| 3.14 | keyed-write | leaf.uuid.document.wire | transientBytes | 70627.000 | 71059.000 | +432.000 B/row (+0.61%) | 9 | within noise |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.typed | elapsedUs | 179.750 | 143.708 | -36.042 us/row (-20.05%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.typed | retainedBytes | 2064.000 | 1992.000 | -72.000 B/row (-3.49%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.typed | transientBytes | 9683.000 | 8491.000 | -1192.000 B/row (-12.31%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.columns.wire | elapsedUs | 172.791 | 131.375 | -41.416 us/row (-23.97%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.columns.wire | retainedBytes | 2024.000 | 1952.000 | -72.000 B/row (-3.56%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.columns.wire | transientBytes | 10163.000 | 9263.000 | -900.000 B/row (-8.86%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.typed | elapsedUs | 186.791 | 147.792 | -38.999 us/row (-20.88%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.typed | retainedBytes | 1992.000 | 1920.000 | -72.000 B/row (-3.61%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.typed | transientBytes | 10535.000 | 9423.000 | -1112.000 B/row (-10.56%) | 9 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | plain.changed.document.wire | elapsedUs | 171.708 | 136.167 | -35.541 us/row (-20.70%) | 9 | faster |
| 3.14 | keyed-write | plain.changed.document.wire | retainedBytes | 2024.000 | 1952.000 | -72.000 B/row (-3.56%) | 1 | smaller |
| 3.14 | keyed-write | plain.changed.document.wire | transientBytes | 11015.000 | 10195.000 | -820.000 B/row (-7.44%) | 9 | smaller |
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
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.typed | elapsedUs | 219.458 | 188.250 | -31.208 us/row (-14.22%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.typed | retainedBytes | 2176.000 | 1640.000 | -536.000 B/row (-24.63%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.typed | transientBytes | 11489.000 | 9985.000 | -1504.000 B/row (-13.09%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.columns.wire | elapsedUs | 202.875 | 179.292 | -23.583 us/row (-11.62%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.columns.wire | retainedBytes | 2208.000 | 1672.000 | -536.000 B/row (-24.28%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.columns.wire | transientBytes | 11949.000 | 10737.000 | -1212.000 B/row (-10.14%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.typed | elapsedUs | 230.125 | 204.750 | -25.375 us/row (-11.03%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.typed | retainedBytes | 2176.000 | 1640.000 | -536.000 B/row (-24.63%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.typed | transientBytes | 11948.000 | 11484.000 | -464.000 B/row (-3.88%) | 9 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.applyPatches | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.changed.document.wire | elapsedUs | 219.500 | 202.750 | -16.750 us/row (-7.63%) | 9 | faster |
| 3.14 | keyed-write | txtime.changed.document.wire | retainedBytes | 2208.000 | 1672.000 | -536.000 B/row (-24.28%) | 1 | smaller |
| 3.14 | keyed-write | txtime.changed.document.wire | transientBytes | 12536.000 | 11996.000 | -540.000 B/row (-4.31%) | 9 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.typed | elapsedUs | 136.459 | 143.500 | +7.041 us/row (+5.16%) | 9 | slower |
| 3.14 | keyed-write | txtime.opening.columns.typed | retainedBytes | 1928.000 | 1840.000 | -88.000 B/row (-4.56%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.columns.typed | transientBytes | 10550.000 | 11054.000 | +504.000 B/row (+4.78%) | 9 | larger |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedDocument | 4.000 | 4.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.columns.wire | elapsedUs | 137.000 | 146.166 | +9.166 us/row (+6.69%) | 9 | slower |
| 3.14 | keyed-write | txtime.opening.columns.wire | retainedBytes | 1928.000 | 2048.000 | +120.000 B/row (+6.22%) | 1 | larger |
| 3.14 | keyed-write | txtime.opening.columns.wire | transientBytes | 10670.000 | 11382.000 | +712.000 B/row (+6.67%) | 9 | larger |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.typed | elapsedUs | 132.084 | 141.041 | +8.957 us/row (+6.78%) | 9 | slower |
| 3.14 | keyed-write | txtime.opening.document.typed | retainedBytes | 1928.000 | 1840.000 | -88.000 B/row (-4.56%) | 1 | smaller |
| 3.14 | keyed-write | txtime.opening.document.typed | transientBytes | 10702.000 | 11126.000 | +424.000 B/row (+3.96%) | 9 | larger |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedDocument | 5.000 | 5.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.encodeManagedMany | 1.000 | 1.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | calls.occurrenceShape | 2.000 | 2.000 | +0.000 calls/row (+0.00%) | 1 | exact |
| 3.14 | keyed-write | txtime.opening.document.wire | elapsedUs | 137.750 | 146.625 | +8.875 us/row (+6.44%) | 9 | slower |
| 3.14 | keyed-write | txtime.opening.document.wire | retainedBytes | 1928.000 | 2048.000 | +120.000 B/row (+6.22%) | 1 | larger |
| 3.14 | keyed-write | txtime.opening.document.wire | transientBytes | 10798.000 | 11430.000 | +632.000 B/row (+5.85%) | 9 | larger |
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
| 3.14 | keyed-write | txtime.unchanged.columns.typed | elapsedUs | 97.125 | 37.458 | -59.667 us/row (-61.43%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.typed | transientBytes | 7744.000 | 4066.000 | -3678.000 B/row (-47.49%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | elapsedUs | 82.834 | 30.708 | -52.126 us/row (-62.93%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.columns.wire | transientBytes | 7856.000 | 3502.000 | -4354.000 B/row (-55.42%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.typed | elapsedUs | 97.042 | 37.875 | -59.167 us/row (-60.97%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.typed | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.typed | transientBytes | 7744.000 | 4068.000 | -3676.000 B/row (-47.47%) | 9 | smaller |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.applyPatches | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.detachJsonContainer | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedDocument | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.encodeManagedMany | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | calls.occurrenceShape | 0.000 | 0.000 | +0.000 calls/row | 1 | exact |
| 3.14 | keyed-write | txtime.unchanged.document.wire | elapsedUs | 83.250 | 30.583 | -52.667 us/row (-63.26%) | 9 | faster |
| 3.14 | keyed-write | txtime.unchanged.document.wire | retainedBytes | 32.000 | 32.000 | +0.000 B/row (+0.00%) | 1 | within noise |
| 3.14 | keyed-write | txtime.unchanged.document.wire | transientBytes | 7856.000 | 3505.000 | -4351.000 B/row (-55.38%) | 9 | smaller |
| 3.14 | model-preparation | model.prepared | elapsedUs | 3316.333 | 3428.208 | +111.875 us (+3.37%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared | retainedBytes | 438440.000 | 438520.000 | +80.000 B (+0.02%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared | transientBytes | 444984.000 | 445000.000 | +16.000 B (+0.00%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | elapsedUs | 313.208 | 307.959 | -5.249 us (-1.68%) | 9 | within noise |
| 3.14 | model-preparation | model.prepared.family | retainedBytes | 23920.000 | 24000.000 | +80.000 B (+0.33%) | 1 | within noise |
| 3.14 | model-preparation | model.prepared.family | transientBytes | 27688.000 | 27704.000 | +16.000 B (+0.06%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | elapsedUs | 24.527 | 23.404 | -1.123 us/row (-4.58%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | retainedBytes | 985.594 | 991.969 | +6.375 B/row (+0.65%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.columns | transientBytes | 2050.805 | 2175.711 | +124.906 B/row (+6.09%) | 9 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | elapsedUs | 25.059 | 23.458 | -1.600 us/row (-6.39%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | retainedBytes | 1987.219 | 1993.594 | +6.375 B/row (+0.32%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-128.document | transientBytes | 2436.273 | 2386.992 | -49.281 B/row (-2.02%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | elapsedUs | 29.635 | 27.000 | -2.635 us/row (-8.89%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | retainedBytes | 1135.375 | 1160.875 | +25.500 B/row (+2.25%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.columns | transientBytes | 2696.094 | 2534.469 | -161.625 B/row (-5.99%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | elapsedUs | 29.749 | 27.895 | -1.854 us/row (-6.23%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | retainedBytes | 2141.875 | 2167.375 | +25.500 B/row (+1.19%) | 1 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-32.document | transientBytes | 3022.219 | 2961.094 | -61.125 B/row (-2.02%) | 9 | within noise |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | elapsedUs | 49.297 | 44.927 | -4.370 us/row (-8.86%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | retainedBytes | 1742.500 | 1844.500 | +102.000 B/row (+5.85%) | 1 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-8.columns | transientBytes | 4822.375 | 4587.875 | -234.500 B/row (-4.86%) | 9 | smaller |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | elapsedUs | 51.656 | 44.969 | -6.688 us/row (-12.95%) | 9 | faster |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | retainedBytes | 2768.500 | 2870.500 | +102.000 B/row (+3.68%) | 1 | larger |
| 3.14 | predicate-acquisition | acquisition.rows-8.document | transientBytes | 5052.875 | 4832.375 | -220.500 B/row (-4.36%) | 9 | smaller |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | elapsedUs | 116.854 | 114.245 | -2.609 us/row (-2.23%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | retainedBytes | 3166.500 | 3268.500 | +102.000 B/row (+3.22%) | 1 | larger |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.columns | transientBytes | 17259.375 | 16991.375 | -268.000 B/row (-1.55%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | elapsedUs | 116.344 | 112.927 | -3.417 us/row (-2.94%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | retainedBytes | 16642.500 | 16744.500 | +102.000 B/row (+0.61%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.boolean.rows-8.document | transientBytes | 19092.625 | 18863.625 | -229.000 B/row (-1.20%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | elapsedUs | 328.193 | 322.229 | -5.964 us/row (-1.82%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | retainedBytes | 12966.500 | 13068.500 | +102.000 B/row (+0.79%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.columns | transientBytes | 32976.000 | 32708.000 | -268.000 B/row (-0.81%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | elapsedUs | 323.781 | 321.875 | -1.906 us/row (-0.59%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | retainedBytes | 40458.500 | 40560.500 | +102.000 B/row (+0.25%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.bytes.rows-8.document | transientBytes | 43064.250 | 42835.250 | -229.000 B/row (-0.53%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | elapsedUs | 376.760 | 369.870 | -6.891 us/row (-1.83%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | retainedBytes | 9566.500 | 9668.500 | +102.000 B/row (+1.07%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.columns | transientBytes | 28226.625 | 27958.625 | -268.000 B/row (-0.95%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | elapsedUs | 374.734 | 371.641 | -3.094 us/row (-0.83%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | retainedBytes | 32834.500 | 32936.500 | +102.000 B/row (+0.31%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.date.rows-8.document | transientBytes | 35442.875 | 35213.875 | -229.000 B/row (-0.65%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | elapsedUs | 727.167 | 711.693 | -15.474 us/row (-2.13%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | retainedBytes | 27166.500 | 27268.500 | +102.000 B/row (+0.38%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.columns | transientBytes | 33197.375 | 32979.375 | -218.000 B/row (-0.66%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | elapsedUs | 723.906 | 714.354 | -9.552 us/row (-1.32%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | retainedBytes | 50818.500 | 50920.500 | +102.000 B/row (+0.20%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.decimal.rows-8.document | transientBytes | 53602.375 | 53384.375 | -218.000 B/row (-0.41%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | elapsedUs | 596.948 | 585.287 | -11.661 us/row (-1.95%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | retainedBytes | 7966.500 | 8068.500 | +102.000 B/row (+1.28%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.columns | transientBytes | 22665.375 | 22397.375 | -268.000 B/row (-1.18%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | elapsedUs | 593.438 | 581.838 | -11.599 us/row (-1.95%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | retainedBytes | 26050.500 | 26152.500 | +102.000 B/row (+0.39%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float32.rows-8.document | transientBytes | 28537.625 | 28308.625 | -229.000 B/row (-0.80%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | elapsedUs | 270.953 | 263.724 | -7.229 us/row (-2.67%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | retainedBytes | 7774.500 | 7876.500 | +102.000 B/row (+1.31%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.columns | transientBytes | 21888.375 | 21620.375 | -268.000 B/row (-1.22%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | elapsedUs | 269.849 | 262.047 | -7.802 us/row (-2.89%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | retainedBytes | 21250.500 | 21352.500 | +102.000 B/row (+0.48%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.float64.rows-8.document | transientBytes | 23728.625 | 23499.625 | -229.000 B/row (-0.97%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | elapsedUs | 167.995 | 160.011 | -7.984 us/row (-4.75%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | retainedBytes | 9566.000 | 9668.000 | +102.000 B/row (+1.07%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.columns | transientBytes | 23668.375 | 23400.375 | -268.000 B/row (-1.13%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | elapsedUs | 164.484 | 158.062 | -6.422 us/row (-3.90%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | retainedBytes | 23042.000 | 23144.000 | +102.000 B/row (+0.44%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int32.rows-8.document | transientBytes | 25508.625 | 25279.625 | -229.000 B/row (-0.90%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | elapsedUs | 173.974 | 167.984 | -5.990 us/row (-3.44%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | retainedBytes | 9950.500 | 10052.500 | +102.000 B/row (+1.03%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.columns | transientBytes | 24057.375 | 23789.375 | -268.000 B/row (-1.11%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | elapsedUs | 172.458 | 167.281 | -5.177 us/row (-3.00%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | retainedBytes | 23426.500 | 23528.500 | +102.000 B/row (+0.44%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.int64.rows-8.document | transientBytes | 25897.625 | 25668.625 | -229.000 B/row (-0.88%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | elapsedUs | 154.141 | 148.198 | -5.943 us/row (-3.86%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | retainedBytes | 13342.500 | 13444.500 | +102.000 B/row (+0.76%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.columns | transientBytes | 27434.875 | 27166.875 | -268.000 B/row (-0.98%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | elapsedUs | 152.604 | 149.833 | -2.771 us/row (-1.82%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | retainedBytes | 26818.500 | 26920.500 | +102.000 B/row (+0.38%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.string.rows-8.document | transientBytes | 29284.125 | 29055.125 | -229.000 B/row (-0.78%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | elapsedUs | 483.812 | 469.719 | -14.094 us/row (-2.91%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | retainedBytes | 9566.500 | 9668.500 | +102.000 B/row (+1.07%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.columns | transientBytes | 29194.625 | 28926.625 | -268.000 B/row (-0.92%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | elapsedUs | 481.630 | 475.057 | -6.573 us/row (-1.36%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | retainedBytes | 33794.500 | 33896.500 | +102.000 B/row (+0.30%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.time.rows-8.document | transientBytes | 36410.875 | 36181.875 | -229.000 B/row (-0.63%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | elapsedUs | 694.406 | 690.484 | -3.922 us/row (-0.56%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | retainedBytes | 12766.500 | 12868.500 | +102.000 B/row (+0.80%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.columns | transientBytes | 32030.625 | 31762.625 | -268.000 B/row (-0.84%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | elapsedUs | 709.208 | 693.547 | -15.662 us/row (-2.21%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | retainedBytes | 39298.500 | 39400.500 | +102.000 B/row (+0.26%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.timestamp.rows-8.document | transientBytes | 41934.875 | 41705.875 | -229.000 B/row (-0.55%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | elapsedUs | 431.104 | 424.927 | -6.177 us/row (-1.43%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | retainedBytes | 24761.000 | 24863.000 | +102.000 B/row (+0.41%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.columns | transientBytes | 35620.125 | 35352.125 | -268.000 B/row (-0.75%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | elapsedUs | 428.849 | 426.458 | -2.391 us/row (-0.56%) | 9 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | retainedBytes | 53021.000 | 53123.000 | +102.000 B/row (+0.19%) | 1 | within noise |
| 3.14 | predicate-acquisition | leaf-acquisition.uuid.rows-8.document | transientBytes | 55604.375 | 55375.375 | -229.000 B/row (-0.41%) | 9 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | elapsedUs | 63.917 | 66.916 | +2.999 us/row (+4.69%) | 9 | within noise |
| 3.14 | wire-insert-response | response.insert.family.wire | retainedBytes | 8748.000 | 9572.000 | +824.000 B/row (+9.42%) | 1 | larger |
| 3.14 | wire-insert-response | response.insert.family.wire | transientBytes | 8718.000 | 8790.000 | +72.000 B/row (+0.83%) | 9 | within noise |

Deltas are advisory and never ratchet the Budget Contract.
