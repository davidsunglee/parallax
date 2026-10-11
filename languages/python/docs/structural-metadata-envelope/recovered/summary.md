# Python cost report

| Subject | Authority | Runtimes | Readings | Within | Outside | Unavailable |
|---|---|---|---:|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 596 | 87 | 3 | 0 |
| lifecycle-overhead | non-authoritative | - | 87 | 5 | 10 | 0 |
| instance-state | non-authoritative | - | 696 | 4 | 4 | 0 |
| write-lowering | non-authoritative | 3.13, 3.14 | 1542 | 0 | 0 | 0 |
| feature-boundary | non-authoritative | 3.13, 3.14 | 180 | 0 | 0 | 0 |

Budget outcomes are advisory. This collector fails only for a missing or invalid required envelope.

## Durations

Critical path: 3585.845 s, the `python-report-cost` collection span. Nested spans are included in their parents and are never summed.

| Scope | Name | Labels | Started | Seconds |
|---|---|---|---|---:|
| collection | python-report-cost | - | 2026-10-11T02:03:43.641941+00:00 | 3585.845 |
| member | snapshot-delivery | member=snapshot-delivery | 2026-10-11T02:03:43.642222+00:00 | 2984.773 |
| setup | identity | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:03:43.948464+00:00 | 0.049 |
| setup | identity | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:03:43.997515+00:00 | 0.027 |
| setup | provisioner | member=snapshot-delivery | 2026-10-11T02:03:44.024833+00:00 | 4.074 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:03:48.101655+00:00 | 113.860 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=conventional-fanout | 2026-10-11T02:03:48.101666+00:00 | 3.331 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=conventional-fanout | 2026-10-11T02:04:07.260406+00:00 | 31.427 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:05:41.961808+00:00 | 123.672 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=duplicate-include | 2026-10-11T02:05:41.961855+00:00 | 3.794 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=duplicate-include | 2026-10-11T02:06:03.267016+00:00 | 31.361 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:07:45.635110+00:00 | 98.206 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=document-heavy | 2026-10-11T02:07:45.635149+00:00 | 0.741 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=document-heavy | 2026-10-11T02:08:05.033189+00:00 | 6.033 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:09:23.841353+00:00 | 72.773 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=versioned-document | 2026-10-11T02:09:23.841392+00:00 | 0.229 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=versioned-document | 2026-10-11T02:09:39.175646+00:00 | 1.057 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:10:36.614947+00:00 | 73.245 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=bitemporal-current | 2026-10-11T02:10:36.614982+00:00 | 0.221 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=bitemporal-current | 2026-10-11T02:10:51.986827+00:00 | 1.081 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:11:49.859748+00:00 | 9.905 |
| workload | stress-document | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:11:59.764848+00:00 | 10.345 |
| workload | geometry | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:12:10.109780+00:00 | 188.347 |
| workload | plan | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:15:18.457281+00:00 | 16.866 |
| workload | control | member=snapshot-delivery, runtime=3.13 | 2026-10-11T02:15:35.323273+00:00 | 151.564 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:18:06.889632+00:00 | 121.696 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=conventional-fanout | 2026-10-11T02:18:06.889660+00:00 | 3.117 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=conventional-fanout | 2026-10-11T02:18:26.465713+00:00 | 30.573 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:20:08.585639+00:00 | 128.243 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=duplicate-include | 2026-10-11T02:20:08.585677+00:00 | 3.185 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=duplicate-include | 2026-10-11T02:20:29.478102+00:00 | 30.383 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:22:16.828664+00:00 | 99.927 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=document-heavy | 2026-10-11T02:22:16.828707+00:00 | 0.697 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=document-heavy | 2026-10-11T02:22:35.645360+00:00 | 6.068 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:23:56.755914+00:00 | 76.535 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=versioned-document | 2026-10-11T02:23:56.755951+00:00 | 0.242 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=versioned-document | 2026-10-11T02:24:11.900486+00:00 | 1.061 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:25:13.291220+00:00 | 76.726 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=bitemporal-current | 2026-10-11T02:25:13.291257+00:00 | 0.242 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=bitemporal-current | 2026-10-11T02:25:28.429720+00:00 | 1.069 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:26:30.017353+00:00 | 7.596 |
| workload | stress-document | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:26:37.613626+00:00 | 7.882 |
| workload | geometry | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:26:45.496190+00:00 | 159.954 |
| workload | leaf | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:29:25.450100+00:00 | 1290.797 |
| workload | plan | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:50:56.253738+00:00 | 15.087 |
| workload | control | member=snapshot-delivery, runtime=3.14 | 2026-10-11T02:51:11.341207+00:00 | 136.552 |
| setup | close | member=snapshot-delivery | 2026-10-11T02:53:27.973025+00:00 | 0.204 |
| member | lifecycle-overhead | member=lifecycle-overhead | 2026-10-11T02:53:28.448022+00:00 | 12.090 |
| member | instance-state | member=instance-state | 2026-10-11T02:53:40.539774+00:00 | 14.379 |
| setup | identity | member=instance-state, runtime=3.13 | 2026-10-11T02:53:40.770498+00:00 | 0.089 |
| setup | identity | member=instance-state, runtime=3.14 | 2026-10-11T02:53:40.859293+00:00 | 0.028 |
| scenario | shallow | member=instance-state, runtime=3.13 | 2026-10-11T02:53:40.887288+00:00 | 0.923 |
| scenario | wide | member=instance-state, runtime=3.13 | 2026-10-11T02:53:41.810142+00:00 | 1.088 |
| scenario | nested | member=instance-state, runtime=3.13 | 2026-10-11T02:53:42.898415+00:00 | 1.699 |
| scenario | nullable | member=instance-state, runtime=3.13 | 2026-10-11T02:53:44.597735+00:00 | 0.948 |
| scenario | partial | member=instance-state, runtime=3.13 | 2026-10-11T02:53:45.545970+00:00 | 0.887 |
| scenario | polymorphic | member=instance-state, runtime=3.13 | 2026-10-11T02:53:46.433057+00:00 | 0.879 |
| scenario | warmed | member=instance-state, runtime=3.13 | 2026-10-11T02:53:47.312242+00:00 | 0.789 |
| scenario | shallow | member=instance-state, runtime=3.14 | 2026-10-11T02:53:48.101676+00:00 | 0.792 |
| scenario | wide | member=instance-state, runtime=3.14 | 2026-10-11T02:53:48.893306+00:00 | 1.017 |
| scenario | nested | member=instance-state, runtime=3.14 | 2026-10-11T02:53:49.910427+00:00 | 1.599 |
| scenario | nullable | member=instance-state, runtime=3.14 | 2026-10-11T02:53:51.509250+00:00 | 0.881 |
| scenario | partial | member=instance-state, runtime=3.14 | 2026-10-11T02:53:52.390625+00:00 | 0.842 |
| scenario | polymorphic | member=instance-state, runtime=3.14 | 2026-10-11T02:53:53.232985+00:00 | 0.833 |
| scenario | warmed | member=instance-state, runtime=3.14 | 2026-10-11T02:53:54.066298+00:00 | 0.751 |
| member | write-lowering | member=write-lowering | 2026-10-11T02:53:54.929552+00:00 | 553.498 |
| setup | identity | member=write-lowering, runtime=3.13 | 2026-10-11T02:53:55.306025+00:00 | 0.064 |
| setup | identity | member=write-lowering, runtime=3.14 | 2026-10-11T02:53:55.369928+00:00 | 0.029 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:53:55.399203+00:00 | 0.907 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:53:56.306076+00:00 | 1.025 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:53:57.330929+00:00 | 0.860 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:53:58.191158+00:00 | 0.948 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:53:59.139275+00:00 | 1.157 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:00.296127+00:00 | 0.799 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:01.095308+00:00 | 0.988 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:02.083049+00:00 | 0.845 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:02.928051+00:00 | 0.910 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:03.838080+00:00 | 1.110 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:04.948515+00:00 | 0.799 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:05.747497+00:00 | 1.019 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:06.766726+00:00 | 0.863 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:07.629479+00:00 | 0.942 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:08.571844+00:00 | 1.146 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:09.717714+00:00 | 0.800 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:10.517528+00:00 | 0.987 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:11.504848+00:00 | 0.840 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:12.345297+00:00 | 0.910 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:13.255443+00:00 | 1.101 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:14.356482+00:00 | 0.854 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:15.210897+00:00 | 0.797 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:16.007617+00:00 | 0.861 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:16.869146+00:00 | 0.921 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:17.790416+00:00 | 0.883 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:18.673334+00:00 | 0.900 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:19.573454+00:00 | 0.762 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:20.335418+00:00 | 0.760 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:21.095519+00:00 | 0.863 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:21.958500+00:00 | 0.857 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:22.815853+00:00 | 1.132 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:23.948312+00:00 | 1.126 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:25.074175+00:00 | 0.888 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:25.961944+00:00 | 0.879 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:26.840820+00:00 | 1.273 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:28.114294+00:00 | 1.274 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:29.388138+00:00 | 0.861 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:30.248791+00:00 | 0.855 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:31.104178+00:00 | 1.000 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:32.103924+00:00 | 0.983 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:33.087104+00:00 | 1.081 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:34.167735+00:00 | 1.062 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:35.229637+00:00 | 1.449 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:36.678688+00:00 | 1.368 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:38.046497+00:00 | 1.055 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:39.102013+00:00 | 1.027 |
| case | plain.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:40.128584+00:00 | 0.876 |
| case | plain.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:41.004502+00:00 | 0.896 |
| case | plain.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:41.900845+00:00 | 0.881 |
| case | plain.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:42.781535+00:00 | 0.925 |
| case | plain.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:43.706746+00:00 | 0.937 |
| case | plain.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:44.644119+00:00 | 0.933 |
| case | txtime.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:45.577410+00:00 | 1.005 |
| case | txtime.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:46.582288+00:00 | 1.030 |
| case | txtime.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:47.612135+00:00 | 1.020 |
| case | txtime.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:48.632156+00:00 | 1.027 |
| case | txtime.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:49.658950+00:00 | 1.022 |
| case | txtime.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:50.680731+00:00 | 1.028 |
| case | bitemporal.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:51.709072+00:00 | 1.137 |
| case | bitemporal.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:52.846406+00:00 | 1.162 |
| case | bitemporal.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:54.007982+00:00 | 1.140 |
| case | bitemporal.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:55.148013+00:00 | 1.143 |
| case | bitemporal.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:56.291156+00:00 | 1.151 |
| case | bitemporal.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-11T02:54:57.442180+00:00 | 1.128 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-11T02:54:58.570365+00:00 | 1.069 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-11T02:54:59.639445+00:00 | 1.684 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-11T02:55:01.323573+00:00 | 4.103 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-11T02:55:05.426921+00:00 | 1.065 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-11T02:55:06.492219+00:00 | 1.699 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-11T02:55:08.191562+00:00 | 4.221 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.13, window=wire-insert-response | 2026-10-11T02:55:12.412299+00:00 | 0.787 |
| case | model.prepared | member=write-lowering, runtime=3.13, window=model-preparation | 2026-10-11T02:55:13.199641+00:00 | 4.899 |
| case | model.prepared.family | member=write-lowering, runtime=3.13, window=model-preparation | 2026-10-11T02:55:18.098777+00:00 | 1.024 |
| case | predicate-flush.reaching.objects-128.columns | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-11T02:55:19.123250+00:00 | 37.760 |
| case | predicate-flush.reaching.objects-128.document | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-11T02:55:56.883149+00:00 | 36.957 |
| case | predicate-flush.unchanged.objects-128.document | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-11T02:56:33.840145+00:00 | 16.984 |
| case | predicate-flush.wide.history-128.document | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-11T02:56:50.824558+00:00 | 12.030 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:02.854288+00:00 | 0.804 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:03.658117+00:00 | 0.994 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:04.652540+00:00 | 0.871 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:05.524026+00:00 | 0.939 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:06.463284+00:00 | 1.124 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:07.587561+00:00 | 0.813 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:08.400598+00:00 | 0.972 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:09.373138+00:00 | 0.846 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:10.219524+00:00 | 0.906 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:11.125574+00:00 | 1.083 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:12.209050+00:00 | 0.796 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:13.005313+00:00 | 1.011 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:14.016595+00:00 | 0.866 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:14.883063+00:00 | 0.936 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:15.819268+00:00 | 1.111 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:16.930545+00:00 | 0.803 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:17.733722+00:00 | 0.974 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:18.708103+00:00 | 0.851 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:19.559531+00:00 | 0.911 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:20.470637+00:00 | 1.072 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:21.542701+00:00 | 0.800 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:22.342465+00:00 | 0.797 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:23.139001+00:00 | 0.838 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:23.976796+00:00 | 0.838 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:24.814371+00:00 | 0.875 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:25.689632+00:00 | 0.896 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:26.585821+00:00 | 0.793 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:27.378454+00:00 | 0.780 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:28.158354+00:00 | 0.858 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:29.015901+00:00 | 0.879 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:29.895319+00:00 | 1.096 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:30.991043+00:00 | 1.085 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:32.076394+00:00 | 0.876 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:32.952246+00:00 | 0.874 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:33.826716+00:00 | 1.194 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:35.020459+00:00 | 1.199 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:36.219737+00:00 | 0.848 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:37.068173+00:00 | 0.854 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:37.922693+00:00 | 0.986 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:38.908753+00:00 | 0.970 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:39.879186+00:00 | 1.052 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:40.931196+00:00 | 1.030 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:41.961420+00:00 | 1.378 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:43.339112+00:00 | 1.302 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:44.641141+00:00 | 1.041 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:45.682543+00:00 | 0.999 |
| case | leaf.string.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:46.681862+00:00 | 1.418 |
| case | leaf.string.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:48.099731+00:00 | 1.414 |
| case | leaf.boolean.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:49.513563+00:00 | 1.044 |
| case | leaf.boolean.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:50.557660+00:00 | 1.132 |
| case | leaf.boolean.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:51.689934+00:00 | 1.039 |
| case | leaf.boolean.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:52.729267+00:00 | 1.148 |
| case | leaf.int32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:53.877659+00:00 | 1.090 |
| case | leaf.int32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:54.967424+00:00 | 1.319 |
| case | leaf.int32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:56.286295+00:00 | 1.101 |
| case | leaf.int32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:57.387768+00:00 | 1.322 |
| case | leaf.int64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:58.709913+00:00 | 1.127 |
| case | leaf.int64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:57:59.837126+00:00 | 1.342 |
| case | leaf.int64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:01.179500+00:00 | 1.116 |
| case | leaf.int64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:02.295344+00:00 | 1.344 |
| case | leaf.float32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:03.639874+00:00 | 1.626 |
| case | leaf.float32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:05.265941+00:00 | 2.132 |
| case | leaf.float32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:07.397971+00:00 | 1.656 |
| case | leaf.float32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:09.053794+00:00 | 2.131 |
| case | leaf.float64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:11.184735+00:00 | 1.192 |
| case | leaf.float64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:12.377310+00:00 | 1.342 |
| case | leaf.float64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:13.719385+00:00 | 1.218 |
| case | leaf.float64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:14.937711+00:00 | 1.337 |
| case | leaf.decimal.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:16.275003+00:00 | 1.941 |
| case | leaf.decimal.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:18.216438+00:00 | 3.443 |
| case | leaf.decimal.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:21.659551+00:00 | 1.941 |
| case | leaf.decimal.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:23.600996+00:00 | 3.429 |
| case | leaf.bytes.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:27.030038+00:00 | 1.203 |
| case | leaf.bytes.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:28.232731+00:00 | 1.482 |
| case | leaf.bytes.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:29.714870+00:00 | 1.198 |
| case | leaf.bytes.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:30.913246+00:00 | 1.460 |
| case | leaf.date.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:32.372916+00:00 | 1.293 |
| case | leaf.date.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:33.666303+00:00 | 1.733 |
| case | leaf.date.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:35.399597+00:00 | 1.302 |
| case | leaf.date.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:36.701580+00:00 | 1.738 |
| case | leaf.time.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:38.439723+00:00 | 1.337 |
| case | leaf.time.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:39.776520+00:00 | 1.730 |
| case | leaf.time.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:41.506297+00:00 | 1.334 |
| case | leaf.time.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:42.840686+00:00 | 1.730 |
| case | leaf.timestamp.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:44.570409+00:00 | 2.048 |
| case | leaf.timestamp.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:46.618668+00:00 | 3.322 |
| case | leaf.timestamp.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:49.941111+00:00 | 2.053 |
| case | leaf.timestamp.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:51.994444+00:00 | 3.347 |
| case | leaf.uuid.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:55.341943+00:00 | 1.856 |
| case | leaf.uuid.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:57.197864+00:00 | 2.415 |
| case | leaf.uuid.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:58:59.613060+00:00 | 1.846 |
| case | leaf.uuid.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:01.459218+00:00 | 2.437 |
| case | plain.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:03.896750+00:00 | 0.879 |
| case | plain.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:04.775338+00:00 | 0.896 |
| case | plain.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:05.671845+00:00 | 0.870 |
| case | plain.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:06.542013+00:00 | 0.914 |
| case | plain.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:07.456241+00:00 | 0.911 |
| case | plain.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:08.367385+00:00 | 0.921 |
| case | txtime.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:09.288738+00:00 | 0.985 |
| case | txtime.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:10.273534+00:00 | 1.013 |
| case | txtime.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:11.287002+00:00 | 0.991 |
| case | txtime.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:12.277570+00:00 | 0.993 |
| case | txtime.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:13.270808+00:00 | 1.000 |
| case | txtime.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:14.270836+00:00 | 1.003 |
| case | bitemporal.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:15.274164+00:00 | 1.103 |
| case | bitemporal.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:16.376836+00:00 | 1.115 |
| case | bitemporal.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:17.491978+00:00 | 1.108 |
| case | bitemporal.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:18.599650+00:00 | 1.115 |
| case | bitemporal.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:19.714670+00:00 | 1.107 |
| case | bitemporal.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-11T02:59:20.821752+00:00 | 1.102 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:21.923802+00:00 | 1.022 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:22.946063+00:00 | 1.519 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:24.464645+00:00 | 3.594 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:28.058430+00:00 | 1.025 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:29.083180+00:00 | 1.540 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:30.623655+00:00 | 3.696 |
| case | leaf-acquisition.string.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:34.319728+00:00 | 2.061 |
| case | leaf-acquisition.string.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:36.380540+00:00 | 2.069 |
| case | leaf-acquisition.boolean.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:38.449645+00:00 | 1.379 |
| case | leaf-acquisition.boolean.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:39.828542+00:00 | 1.393 |
| case | leaf-acquisition.int32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:41.221778+00:00 | 1.891 |
| case | leaf-acquisition.int32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:43.112802+00:00 | 1.879 |
| case | leaf-acquisition.int64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:44.991632+00:00 | 2.064 |
| case | leaf-acquisition.int64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:47.055671+00:00 | 2.041 |
| case | leaf-acquisition.float32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:49.097008+00:00 | 6.510 |
| case | leaf-acquisition.float32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T02:59:55.607392+00:00 | 6.353 |
| case | leaf-acquisition.float64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:01.960943+00:00 | 2.719 |
| case | leaf-acquisition.float64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:04.679495+00:00 | 2.719 |
| case | leaf-acquisition.decimal.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:07.398492+00:00 | 9.715 |
| case | leaf-acquisition.decimal.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:17.113430+00:00 | 9.358 |
| case | leaf-acquisition.bytes.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:26.471962+00:00 | 3.622 |
| case | leaf-acquisition.bytes.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:30.094204+00:00 | 3.571 |
| case | leaf-acquisition.date.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:33.665730+00:00 | 4.621 |
| case | leaf-acquisition.date.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:38.286291+00:00 | 4.709 |
| case | leaf-acquisition.time.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:42.994978+00:00 | 5.938 |
| case | leaf-acquisition.time.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:48.933017+00:00 | 6.015 |
| case | leaf-acquisition.timestamp.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:00:54.947628+00:00 | 14.510 |
| case | leaf-acquisition.timestamp.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:01:09.457731+00:00 | 14.331 |
| case | leaf-acquisition.uuid.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:01:23.788923+00:00 | 5.054 |
| case | leaf-acquisition.uuid.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-11T03:01:28.842595+00:00 | 4.869 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.14, window=wire-insert-response | 2026-10-11T03:01:33.711775+00:00 | 0.789 |
| case | model.prepared | member=write-lowering, runtime=3.14, window=model-preparation | 2026-10-11T03:01:34.500956+00:00 | 4.007 |
| case | model.prepared.family | member=write-lowering, runtime=3.14, window=model-preparation | 2026-10-11T03:01:38.507530+00:00 | 0.971 |
| case | predicate-flush.reaching.objects-128.columns | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-11T03:01:39.479029+00:00 | 32.826 |
| case | predicate-flush.reaching.objects-128.document | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-11T03:02:12.304700+00:00 | 31.366 |
| case | predicate-flush.unchanged.objects-128.document | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-11T03:02:43.670745+00:00 | 14.348 |
| case | predicate-flush.wide.history-128.document | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-11T03:02:58.018981+00:00 | 10.212 |
| member | feature-boundary | member=feature-boundary | 2026-10-11T03:03:08.473655+00:00 | 21.018 |
| setup | identity | member=feature-boundary, runtime=3.13 | 2026-10-11T03:03:08.691014+00:00 | 0.062 |
| setup | identity | member=feature-boundary, runtime=3.14 | 2026-10-11T03:03:08.753149+00:00 | 0.027 |
| case | predicate.shallow-scalar.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-11T03:03:08.780442+00:00 | 0.321 |
| case | predicate.shallow-scalar.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-11T03:03:09.100968+00:00 | 0.404 |
| case | predicate.scalar-any.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-11T03:03:09.504658+00:00 | 0.300 |
| case | predicate.scalar-any.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-11T03:03:09.804547+00:00 | 0.407 |
| case | predicate.nested-all.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-11T03:03:10.212044+00:00 | 0.300 |
| case | predicate.nested-all.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-11T03:03:10.512000+00:00 | 0.412 |
| case | predicate.two-hop-to-one.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-11T03:03:10.924227+00:00 | 0.315 |
| case | predicate.two-hop-to-one.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-11T03:03:11.239641+00:00 | 0.425 |
| case | predicate.quantifier-through-to-one.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-11T03:03:11.664614+00:00 | 0.307 |
| case | predicate.quantifier-through-to-one.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-11T03:03:11.971814+00:00 | 0.421 |
| case | predicate.subtype-narrowing.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-11T03:03:12.392470+00:00 | 0.306 |
| case | predicate.subtype-narrowing.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-11T03:03:12.698196+00:00 | 0.422 |
| case | scalar-collection.integer.size-0.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-11T03:03:13.120262+00:00 | 0.291 |
| case | scalar-collection.integer.size-0.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-11T03:03:13.411140+00:00 | 0.289 |
| case | scalar-collection.integer.size-8.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-11T03:03:13.699801+00:00 | 0.292 |
| case | scalar-collection.integer.size-8.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-11T03:03:13.991595+00:00 | 0.293 |
| case | scalar-collection.integer.size-128.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-11T03:03:14.284210+00:00 | 0.327 |
| case | scalar-collection.integer.size-128.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-11T03:03:14.611518+00:00 | 0.316 |
| case | scalar-collection.string.size-0.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-11T03:03:14.927963+00:00 | 0.294 |
| case | scalar-collection.string.size-0.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-11T03:03:15.221875+00:00 | 0.288 |
| case | scalar-collection.string.size-8.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-11T03:03:15.509711+00:00 | 0.294 |
| case | scalar-collection.string.size-8.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-11T03:03:15.803299+00:00 | 0.293 |
| case | scalar-collection.string.size-128.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-11T03:03:16.096618+00:00 | 0.366 |
| case | scalar-collection.string.size-128.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-11T03:03:16.462855+00:00 | 0.293 |
| case | scalar-collection.decimal.size-0.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-11T03:03:16.755787+00:00 | 0.287 |
| case | scalar-collection.decimal.size-0.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-11T03:03:17.042828+00:00 | 0.292 |
| case | scalar-collection.decimal.size-8.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-11T03:03:17.334483+00:00 | 0.318 |
| case | scalar-collection.decimal.size-8.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-11T03:03:17.652195+00:00 | 0.313 |
| case | scalar-collection.decimal.size-128.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-11T03:03:17.965439+00:00 | 0.682 |
| case | scalar-collection.decimal.size-128.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-11T03:03:18.647214+00:00 | 0.705 |
| case | predicate.shallow-scalar.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-11T03:03:19.352121+00:00 | 0.291 |
| case | predicate.shallow-scalar.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-11T03:03:19.642768+00:00 | 0.373 |
| case | predicate.scalar-any.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-11T03:03:20.015735+00:00 | 0.291 |
| case | predicate.scalar-any.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-11T03:03:20.306916+00:00 | 0.380 |
| case | predicate.nested-all.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-11T03:03:20.686699+00:00 | 0.290 |
| case | predicate.nested-all.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-11T03:03:20.976932+00:00 | 0.392 |
| case | predicate.two-hop-to-one.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-11T03:03:21.368999+00:00 | 0.301 |
| case | predicate.two-hop-to-one.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-11T03:03:21.669804+00:00 | 0.398 |
| case | predicate.quantifier-through-to-one.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-11T03:03:22.067827+00:00 | 0.297 |
| case | predicate.quantifier-through-to-one.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-11T03:03:22.365269+00:00 | 0.393 |
| case | predicate.subtype-narrowing.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-11T03:03:22.758553+00:00 | 0.297 |
| case | predicate.subtype-narrowing.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-11T03:03:23.055269+00:00 | 0.399 |
| case | scalar-collection.integer.size-0.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-11T03:03:23.454369+00:00 | 0.281 |
| case | scalar-collection.integer.size-0.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-11T03:03:23.735204+00:00 | 0.281 |
| case | scalar-collection.integer.size-8.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-11T03:03:24.015909+00:00 | 0.286 |
| case | scalar-collection.integer.size-8.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-11T03:03:24.302439+00:00 | 0.284 |
| case | scalar-collection.integer.size-128.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-11T03:03:24.586398+00:00 | 0.317 |
| case | scalar-collection.integer.size-128.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-11T03:03:24.903625+00:00 | 0.315 |
| case | scalar-collection.string.size-0.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-11T03:03:25.219123+00:00 | 0.282 |
| case | scalar-collection.string.size-0.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-11T03:03:25.501460+00:00 | 0.283 |
| case | scalar-collection.string.size-8.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-11T03:03:25.784682+00:00 | 0.286 |
| case | scalar-collection.string.size-8.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-11T03:03:26.070451+00:00 | 0.282 |
| case | scalar-collection.string.size-128.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-11T03:03:26.352935+00:00 | 0.350 |
| case | scalar-collection.string.size-128.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-11T03:03:26.703311+00:00 | 0.283 |
| case | scalar-collection.decimal.size-0.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-11T03:03:26.986832+00:00 | 0.285 |
| case | scalar-collection.decimal.size-0.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-11T03:03:27.272100+00:00 | 0.281 |
| case | scalar-collection.decimal.size-8.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-11T03:03:27.553275+00:00 | 0.302 |
| case | scalar-collection.decimal.size-8.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-11T03:03:27.855680+00:00 | 0.309 |
| case | scalar-collection.decimal.size-128.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-11T03:03:28.164269+00:00 | 0.608 |
| case | scalar-collection.decimal.size-128.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-11T03:03:28.772617+00:00 | 0.625 |
