# Python cost report

| Subject | Authority | Runtimes | Readings | Within | Outside | Unavailable |
|---|---|---|---:|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 596 | 81 | 9 | 0 |
| lifecycle-overhead | non-authoritative | - | 87 | 5 | 10 | 0 |
| instance-state | non-authoritative | - | 696 | 4 | 4 | 0 |
| write-lowering | non-authoritative | 3.13, 3.14 | 1230 | 0 | 0 | 0 |

Budget outcomes are advisory. This collector fails only for a missing or invalid required envelope.

## Durations

Critical path: 3861.749 s, the `python-report-cost` collection span. Nested spans are included in their parents and are never summed.

| Scope | Name | Labels | Started | Seconds |
|---|---|---|---|---:|
| collection | python-report-cost | - | 2026-09-29T17:05:43.532810+00:00 | 3861.749 |
| member | snapshot-delivery | member=snapshot-delivery | 2026-09-29T17:05:43.532937+00:00 | 3502.217 |
| setup | identity | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:05:43.869315+00:00 | 0.046 |
| setup | identity | member=snapshot-delivery, runtime=3.14 | 2026-09-29T17:05:43.914964+00:00 | 0.034 |
| setup | provisioner | member=snapshot-delivery | 2026-09-29T17:05:43.948810+00:00 | 3.609 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:05:47.569603+00:00 | 146.396 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=conventional-fanout | 2026-09-29T17:05:47.569614+00:00 | 3.135 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=conventional-fanout | 2026-09-29T17:06:12.374171+00:00 | 30.073 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:08:13.966056+00:00 | 154.057 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=duplicate-include | 2026-09-29T17:08:13.966098+00:00 | 3.068 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=duplicate-include | 2026-09-29T17:08:40.309436+00:00 | 29.389 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:10:48.023312+00:00 | 133.498 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=document-heavy | 2026-09-29T17:10:48.023348+00:00 | 0.715 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=document-heavy | 2026-09-29T17:11:13.594962+00:00 | 5.897 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:13:01.521515+00:00 | 105.887 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=versioned-document | 2026-09-29T17:13:01.521557+00:00 | 0.260 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=versioned-document | 2026-09-29T17:13:22.648892+00:00 | 1.116 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:14:47.408779+00:00 | 106.284 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=bitemporal-current | 2026-09-29T17:14:47.408816+00:00 | 0.263 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=bitemporal-current | 2026-09-29T17:15:08.605172+00:00 | 1.058 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:16:33.693414+00:00 | 12.614 |
| workload | stress-document | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:16:46.307858+00:00 | 13.103 |
| workload | geometry | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:16:59.414986+00:00 | 200.051 |
| workload | plan | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:20:19.466715+00:00 | 21.071 |
| workload | control | member=snapshot-delivery, runtime=3.13 | 2026-09-29T17:20:40.537943+00:00 | 178.872 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.14 | 2026-09-29T17:23:39.412202+00:00 | 155.726 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=conventional-fanout | 2026-09-29T17:23:39.412230+00:00 | 3.045 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=conventional-fanout | 2026-09-29T17:24:05.739679+00:00 | 28.936 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.14 | 2026-09-29T17:26:15.135893+00:00 | 166.617 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=duplicate-include | 2026-09-29T17:26:15.135934+00:00 | 3.078 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=duplicate-include | 2026-09-29T17:26:43.466245+00:00 | 30.687 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.14 | 2026-09-29T17:29:01.753062+00:00 | 143.776 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=document-heavy | 2026-09-29T17:29:01.753098+00:00 | 0.627 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=document-heavy | 2026-09-29T17:29:28.632195+00:00 | 5.913 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.14 | 2026-09-29T17:31:25.529893+00:00 | 117.526 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=versioned-document | 2026-09-29T17:31:25.529930+00:00 | 0.220 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=versioned-document | 2026-09-29T17:31:48.327080+00:00 | 1.033 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.14 | 2026-09-29T17:33:23.056392+00:00 | 118.044 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=bitemporal-current | 2026-09-29T17:33:23.056435+00:00 | 0.286 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=bitemporal-current | 2026-09-29T17:33:45.871456+00:00 | 1.041 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.14 | 2026-09-29T17:35:21.100604+00:00 | 10.966 |
| workload | stress-document | member=snapshot-delivery, runtime=3.14 | 2026-09-29T17:35:32.066191+00:00 | 11.480 |
| workload | geometry | member=snapshot-delivery, runtime=3.14 | 2026-09-29T17:35:43.553645+00:00 | 177.685 |
| workload | leaf | member=snapshot-delivery, runtime=3.14 | 2026-09-29T17:38:41.238773+00:00 | 1323.009 |
| workload | plan | member=snapshot-delivery, runtime=3.14 | 2026-09-29T18:00:44.253812+00:00 | 21.034 |
| workload | control | member=snapshot-delivery, runtime=3.14 | 2026-09-29T18:01:05.287615+00:00 | 180.035 |
| setup | close | member=snapshot-delivery | 2026-09-29T18:04:05.405950+00:00 | 0.153 |
| member | lifecycle-overhead | member=lifecycle-overhead | 2026-09-29T18:04:05.802741+00:00 | 12.616 |
| member | instance-state | member=instance-state | 2026-09-29T18:04:18.425304+00:00 | 14.334 |
| setup | identity | member=instance-state, runtime=3.13 | 2026-09-29T18:04:18.661026+00:00 | 0.083 |
| setup | identity | member=instance-state, runtime=3.14 | 2026-09-29T18:04:18.744193+00:00 | 0.034 |
| scenario | shallow | member=instance-state, runtime=3.13 | 2026-09-29T18:04:18.778535+00:00 | 0.875 |
| scenario | wide | member=instance-state, runtime=3.13 | 2026-09-29T18:04:19.654053+00:00 | 1.038 |
| scenario | nested | member=instance-state, runtime=3.13 | 2026-09-29T18:04:20.692390+00:00 | 1.650 |
| scenario | nullable | member=instance-state, runtime=3.13 | 2026-09-29T18:04:22.342885+00:00 | 0.882 |
| scenario | partial | member=instance-state, runtime=3.13 | 2026-09-29T18:04:23.224683+00:00 | 0.844 |
| scenario | polymorphic | member=instance-state, runtime=3.13 | 2026-09-29T18:04:24.069061+00:00 | 0.835 |
| scenario | warmed | member=instance-state, runtime=3.13 | 2026-09-29T18:04:24.904226+00:00 | 0.753 |
| scenario | shallow | member=instance-state, runtime=3.14 | 2026-09-29T18:04:25.657510+00:00 | 0.821 |
| scenario | wide | member=instance-state, runtime=3.14 | 2026-09-29T18:04:26.478910+00:00 | 1.049 |
| scenario | nested | member=instance-state, runtime=3.14 | 2026-09-29T18:04:27.528056+00:00 | 1.706 |
| scenario | nullable | member=instance-state, runtime=3.14 | 2026-09-29T18:04:29.233934+00:00 | 0.918 |
| scenario | partial | member=instance-state, runtime=3.14 | 2026-09-29T18:04:30.151924+00:00 | 0.869 |
| scenario | polymorphic | member=instance-state, runtime=3.14 | 2026-09-29T18:04:31.020515+00:00 | 0.870 |
| scenario | warmed | member=instance-state, runtime=3.14 | 2026-09-29T18:04:31.890828+00:00 | 0.784 |
| member | write-lowering | member=write-lowering | 2026-09-29T18:04:32.777423+00:00 | 332.403 |
| setup | identity | member=write-lowering, runtime=3.13 | 2026-09-29T18:04:33.167256+00:00 | 0.059 |
| setup | identity | member=write-lowering, runtime=3.14 | 2026-09-29T18:04:33.226790+00:00 | 0.034 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:33.264628+00:00 | 0.817 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:34.081197+00:00 | 0.989 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:35.070119+00:00 | 0.896 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:35.965828+00:00 | 0.936 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:36.902137+00:00 | 1.110 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:38.011965+00:00 | 0.737 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:38.748959+00:00 | 0.954 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:39.702924+00:00 | 0.854 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:40.556482+00:00 | 0.888 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:41.444573+00:00 | 1.072 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:42.516490+00:00 | 0.734 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:43.250540+00:00 | 1.004 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:44.254607+00:00 | 0.886 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:45.141142+00:00 | 0.931 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:46.072241+00:00 | 1.081 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:47.153763+00:00 | 0.744 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:47.897423+00:00 | 0.955 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:48.852385+00:00 | 0.841 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:49.693199+00:00 | 0.886 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:50.579161+00:00 | 1.058 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:51.636779+00:00 | 0.737 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:52.373373+00:00 | 0.734 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:53.107758+00:00 | 0.781 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:53.888977+00:00 | 0.773 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:54.661570+00:00 | 0.822 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:55.483544+00:00 | 0.828 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:56.311217+00:00 | 0.716 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:57.027479+00:00 | 0.711 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:57.738277+00:00 | 0.798 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:58.536543+00:00 | 0.796 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:04:59.332408+00:00 | 1.047 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:00.379541+00:00 | 1.050 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:01.429448+00:00 | 0.818 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:02.247789+00:00 | 0.818 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:03.066131+00:00 | 1.189 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:04.254735+00:00 | 1.183 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:05.437373+00:00 | 0.801 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:06.238120+00:00 | 0.795 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:07.033549+00:00 | 1.001 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:08.034207+00:00 | 0.986 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:09.020286+00:00 | 1.181 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:10.201259+00:00 | 1.162 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:11.363516+00:00 | 2.013 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:13.376914+00:00 | 1.929 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:15.306009+00:00 | 1.198 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-29T18:05:16.503979+00:00 | 1.149 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-29T18:05:17.653058+00:00 | 1.133 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-29T18:05:18.785908+00:00 | 1.958 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-29T18:05:20.744325+00:00 | 5.444 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-29T18:05:26.188377+00:00 | 1.130 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-29T18:05:27.318322+00:00 | 1.993 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-29T18:05:29.311800+00:00 | 5.484 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.13, window=wire-insert-response | 2026-09-29T18:05:34.795986+00:00 | 0.724 |
| case | model.prepared | member=write-lowering, runtime=3.13, window=model-preparation | 2026-09-29T18:05:35.519901+00:00 | 4.558 |
| case | model.prepared.family | member=write-lowering, runtime=3.13, window=model-preparation | 2026-09-29T18:05:40.078262+00:00 | 0.956 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:41.037921+00:00 | 0.775 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:41.812635+00:00 | 1.031 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:42.844165+00:00 | 0.919 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:43.763498+00:00 | 0.960 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:44.723386+00:00 | 1.117 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:45.840642+00:00 | 0.770 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:46.610953+00:00 | 0.985 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:47.595522+00:00 | 0.893 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:48.488858+00:00 | 0.919 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:49.407449+00:00 | 1.108 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:50.515136+00:00 | 0.765 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:51.280108+00:00 | 1.019 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:52.299120+00:00 | 0.914 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:53.212892+00:00 | 0.959 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:54.172042+00:00 | 1.101 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:55.272620+00:00 | 0.770 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:56.042455+00:00 | 0.986 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:57.028164+00:00 | 0.878 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:57.906423+00:00 | 0.924 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:58.830618+00:00 | 1.083 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:05:59.914112+00:00 | 0.767 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:00.681429+00:00 | 0.767 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:01.448814+00:00 | 0.809 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:02.258317+00:00 | 0.799 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:03.057610+00:00 | 0.844 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:03.901213+00:00 | 0.851 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:04.752405+00:00 | 0.745 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:05.497374+00:00 | 0.752 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:06.249307+00:00 | 0.829 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:07.078830+00:00 | 0.828 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:07.906924+00:00 | 1.053 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:08.960349+00:00 | 1.058 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:10.018330+00:00 | 0.849 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:10.867772+00:00 | 0.841 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:11.708813+00:00 | 1.181 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:12.890038+00:00 | 1.168 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:14.058349+00:00 | 0.824 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:14.882736+00:00 | 0.829 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:15.711478+00:00 | 1.026 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:16.737926+00:00 | 1.037 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:17.775379+00:00 | 1.176 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:18.951842+00:00 | 1.162 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:20.114134+00:00 | 1.899 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:22.013519+00:00 | 1.851 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:23.864365+00:00 | 1.174 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:25.038880+00:00 | 1.125 |
| case | leaf.string.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:26.164020+00:00 | 1.385 |
| case | leaf.string.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:27.549387+00:00 | 1.374 |
| case | leaf.boolean.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:28.923366+00:00 | 1.026 |
| case | leaf.boolean.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:29.949065+00:00 | 1.098 |
| case | leaf.boolean.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:31.047244+00:00 | 1.042 |
| case | leaf.boolean.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:32.089000+00:00 | 1.211 |
| case | leaf.int32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:33.300536+00:00 | 1.137 |
| case | leaf.int32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:34.437345+00:00 | 1.304 |
| case | leaf.int32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:35.741666+00:00 | 1.094 |
| case | leaf.int32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:36.835452+00:00 | 1.298 |
| case | leaf.int64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:38.133968+00:00 | 1.090 |
| case | leaf.int64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:39.223943+00:00 | 1.312 |
| case | leaf.int64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:40.536281+00:00 | 1.144 |
| case | leaf.int64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:41.679845+00:00 | 1.371 |
| case | leaf.float32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:43.050714+00:00 | 1.712 |
| case | leaf.float32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:44.763080+00:00 | 2.339 |
| case | leaf.float32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:47.102471+00:00 | 1.672 |
| case | leaf.float32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:48.774981+00:00 | 2.225 |
| case | leaf.float64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:50.999611+00:00 | 1.270 |
| case | leaf.float64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:52.269811+00:00 | 1.345 |
| case | leaf.float64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:53.614882+00:00 | 1.240 |
| case | leaf.float64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:54.855261+00:00 | 1.338 |
| case | leaf.decimal.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:56.193677+00:00 | 2.036 |
| case | leaf.decimal.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:06:58.229875+00:00 | 3.400 |
| case | leaf.decimal.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:01.630382+00:00 | 1.978 |
| case | leaf.decimal.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:03.608097+00:00 | 3.441 |
| case | leaf.bytes.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:07.049363+00:00 | 1.222 |
| case | leaf.bytes.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:08.271064+00:00 | 1.470 |
| case | leaf.bytes.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:09.740617+00:00 | 1.202 |
| case | leaf.bytes.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:10.942911+00:00 | 1.436 |
| case | leaf.date.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:12.379311+00:00 | 1.285 |
| case | leaf.date.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:13.664479+00:00 | 1.731 |
| case | leaf.date.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:15.395384+00:00 | 1.297 |
| case | leaf.date.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:16.692040+00:00 | 1.721 |
| case | leaf.time.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:18.413470+00:00 | 1.323 |
| case | leaf.time.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:19.736152+00:00 | 1.725 |
| case | leaf.time.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:21.461551+00:00 | 1.343 |
| case | leaf.time.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:22.804135+00:00 | 1.718 |
| case | leaf.timestamp.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:24.522628+00:00 | 1.881 |
| case | leaf.timestamp.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:26.403553+00:00 | 2.937 |
| case | leaf.timestamp.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:29.340167+00:00 | 1.876 |
| case | leaf.timestamp.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:31.216148+00:00 | 2.948 |
| case | leaf.uuid.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:34.164496+00:00 | 1.837 |
| case | leaf.uuid.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:36.001754+00:00 | 2.412 |
| case | leaf.uuid.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:38.413819+00:00 | 1.838 |
| case | leaf.uuid.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-29T18:07:40.251910+00:00 | 2.458 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:07:42.709562+00:00 | 1.127 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:07:43.836715+00:00 | 1.887 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:07:45.723764+00:00 | 4.921 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:07:50.644972+00:00 | 1.131 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:07:51.775789+00:00 | 1.942 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:07:53.717916+00:00 | 5.151 |
| case | leaf-acquisition.string.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:07:58.868968+00:00 | 2.128 |
| case | leaf-acquisition.string.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:00.997465+00:00 | 2.119 |
| case | leaf-acquisition.boolean.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:03.116656+00:00 | 1.471 |
| case | leaf-acquisition.boolean.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:04.588013+00:00 | 1.491 |
| case | leaf-acquisition.int32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:06.079162+00:00 | 1.993 |
| case | leaf-acquisition.int32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:08.072390+00:00 | 2.028 |
| case | leaf-acquisition.int64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:10.100404+00:00 | 2.155 |
| case | leaf-acquisition.int64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:12.255940+00:00 | 2.267 |
| case | leaf-acquisition.float32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:14.523028+00:00 | 6.515 |
| case | leaf-acquisition.float32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:21.038123+00:00 | 6.589 |
| case | leaf-acquisition.float64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:27.627565+00:00 | 2.906 |
| case | leaf-acquisition.float64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:30.533400+00:00 | 2.889 |
| case | leaf-acquisition.decimal.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:33.421984+00:00 | 9.928 |
| case | leaf-acquisition.decimal.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:43.350100+00:00 | 9.704 |
| case | leaf-acquisition.bytes.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:53.053955+00:00 | 3.612 |
| case | leaf-acquisition.bytes.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:08:56.665758+00:00 | 3.694 |
| case | leaf-acquisition.date.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:09:00.360065+00:00 | 4.902 |
| case | leaf-acquisition.date.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:09:05.262025+00:00 | 4.868 |
| case | leaf-acquisition.time.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:09:10.129670+00:00 | 6.122 |
| case | leaf-acquisition.time.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:09:16.251677+00:00 | 6.184 |
| case | leaf-acquisition.timestamp.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:09:22.435337+00:00 | 13.194 |
| case | leaf-acquisition.timestamp.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:09:35.629086+00:00 | 13.090 |
| case | leaf-acquisition.uuid.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:09:48.718826+00:00 | 5.207 |
| case | leaf-acquisition.uuid.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-29T18:09:53.926129+00:00 | 5.207 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.14, window=wire-insert-response | 2026-09-29T18:09:59.133369+00:00 | 0.757 |
| case | model.prepared | member=write-lowering, runtime=3.14, window=model-preparation | 2026-09-29T18:09:59.890206+00:00 | 4.156 |
| case | model.prepared.family | member=write-lowering, runtime=3.14, window=model-preparation | 2026-09-29T18:10:04.046536+00:00 | 0.964 |
